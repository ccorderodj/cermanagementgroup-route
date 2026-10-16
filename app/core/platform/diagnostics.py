"""
Diagnostics: cada comprobación, su resultado, su historial y su alerta.

Qué se comprueba
----------------
* **Infraestructura**: la base de datos.
* **Integraciones**, con lo configurado en Settings: el correo abre sesión sin
  mandar nada; el almacén escribe, lee y borra una sonda y confirma que el
  bucket **no** es público; el escáner rechaza el archivo de prueba EICAR y
  acepta uno limpio.
* **Integridad** (S4): disparadores de evidencia, versión de la base, catálogo de
  permisos y llave maestra.
* **Planificador**: que haya latido reciente.

Reglas
------
* Ninguna comprobación muta estado de negocio. La única escritura es la sonda del
  almacén, en su propio prefijo, y se borra.
* Todas tienen tiempo límite.
* El error se sanea: sale una categoría y una frase, nunca la excepción cruda,
  que en un fallo de SMTP puede llevar el usuario y en uno de base de datos la
  cadena de conexión.
* Cada ejecución se guarda en `platform_health_check_run` (append-only), y la
  fila de estado se actualiza.
* Una comprobación programada que pasa de sana a fallida avisa por correo a los
  administradores de plataforma (S7).
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.core.platform import integrity
from app.core.platform.models import PlatformHealthCheck, PlatformHealthCheckRun
from app.database import async_session_maker
from app.logger import logger

TIMEOUT_SECONDS = 25
HEALTHY = "healthy"
DEGRADED = "degraded"
AUTH_FAILED = "auth_failed"
UNREACHABLE = "unreachable"
NOT_APPLICABLE = "not_applicable"
#: Estados que son un fallo **por sí mismos**: la capacidad está configurada y
#: no responde como debería.
FAILURES = (DEGRADED, AUTH_FAILED, UNREACHABLE)


def es_regresion(anterior: str | None, estado: str) -> bool:
    """¿Algo que estaba sano dejó de estarlo?

    Por qué no basta con `estado in FAILURES`
    ------------------------------------------
    `not_applicable` significa «no está configurado», y como estado **inicial**
    es correcto y no es una alarma: que todavía no se haya configurado el correo
    no es un incidente, es una decisión pendiente.

    Pero pasar de `healthy` a `not_applicable` es otra cosa distinta: algo que
    **estaba** configurado dejó de estarlo. Eso no es una ausencia, es una
    pérdida — y es exactamente el evento que hay que oír.

    Ocurrió en campo. La integración de routing desapareció, el chequeo lo
    detectó en la ejecución siguiente y lo repitió **77 veces durante seis
    días** sin avisar a nadie, porque `not_applicable` no estaba en `FAILURES`.
    Se descubrió porque alguien miró una pantalla llena de ceros.

    La regla correcta es más simple que cualquier lista de estados: **estaba
    sano y ya no lo está**. Así, un estado nuevo que se añada mañana queda
    cubierto sin que nadie tenga que acordarse de incluirlo aquí.
    """
    return anterior == HEALTHY and estado != HEALTHY


SCHEDULER_KEY = "platform.scheduler"
HEARTBEAT_KEY = "platform.scheduler_heartbeat"


@dataclass(frozen=True)
class CheckDefinition:
    key: str
    title: str
    kind: str
    summary: str
    #: Nombre de la función de este módulo que la ejecuta. Se resuelve al llamar,
    #: así un test puede sustituirla.
    runner: str


@dataclass(frozen=True)
class RunOutcome:
    key: str
    status: str
    detail: str
    checked_at: datetime
    duration_ms: int
    previous_status: str | None


# ══ Comprobaciones ═══════════════════════════════════════════════════════════════


async def _database() -> tuple[str, str]:
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))
    return HEALTHY, "Answered SELECT 1."


def _email_check_sync(key: str, *, not_configured_detail: str) -> tuple[str, str]:
    from app.core.email import backends

    backend = backends.backend_from_platform_config(key)
    if backend is None:
        return NOT_APPLICABLE, not_configured_detail
    try:
        backend.check()
    except backends.EmailAuthFailed as exc:
        return AUTH_FAILED, str(exc)
    except backends.EmailUnreachable as exc:
        return UNREACHABLE, str(exc)
    return HEALTHY, f"Connected and authenticated with {backend.name}. No message was sent."


def _email_sync() -> tuple[str, str]:
    return _email_check_sync("email", not_configured_detail="Email is not configured in Settings.")


async def _email() -> tuple[str, str]:
    return await asyncio.to_thread(_email_sync)


def _email_fallback_sync() -> tuple[str, str]:
    return _email_check_sync(
        "email_fallback", not_configured_detail="No fallback email provider is configured in Settings."
    )


async def _email_fallback() -> tuple[str, str]:
    return await asyncio.to_thread(_email_fallback_sync)


def _storage_sync() -> tuple[str, str]:
    from app.core.storage.base import LocalFileStorage, S3CompatibleStorage, get_storage

    almacen = get_storage()
    if isinstance(almacen, S3CompatibleStorage):
        from botocore.exceptions import ClientError

        sonda = almacen.probe_key()
        try:
            almacen.put_existing(storage_key=sonda, data=b"probe", content_type="text/plain")
            if almacen.open(sonda) != b"probe":
                return DEGRADED, "The probe object did not read back as written."
            publico = almacen.is_publicly_readable(sonda)
            almacen.delete_probe(sonda)
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "")
            if codigo in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied", "403"):
                return AUTH_FAILED, f"The bucket rejected the configured keys ({codigo})."
            if codigo == "NoSuchBucket":
                return UNREACHABLE, "The configured bucket does not exist."
            return UNREACHABLE, f"The storage service answered with an error ({codigo or 'unknown'})."
        except Exception:
            return UNREACHABLE, "The storage endpoint did not answer."
        if publico:
            return DEGRADED, (
                "The bucket is publicly readable: anyone could read the stored files. Make it private."
            )
        return HEALTHY, "Wrote, read and removed a probe object; anonymous reads are refused."

    if isinstance(almacen, LocalFileStorage):
        carpeta = almacen.root / ".healthcheck"
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            archivo = carpeta / "probe.tmp"
            archivo.write_bytes(b"probe")
            leido = archivo.read_bytes()
            archivo.unlink()
        except OSError:
            return UNREACHABLE, "Could not write to the local storage root."
        if leido != b"probe":
            return DEGRADED, "The probe file did not read back as written."
        return HEALTHY, (
            "Wrote and removed a probe file on the local disk. Local storage does not "
            "support more than one application instance."
        )
    return NOT_APPLICABLE, "No storage adapter to check."


async def _storage() -> tuple[str, str]:
    return await asyncio.to_thread(_storage_sync)


def _scanner_sync() -> tuple[str, str]:
    from app.core.storage.scanning import (
        NotConfiguredScanner,
        ScannerAuthFailed,
        ScannerUnavailable,
        ScanVerdict,
        eicar_test_file,
        get_scanner,
    )

    escaner = get_scanner()
    if isinstance(escaner, NotConfiguredScanner):
        return NOT_APPLICABLE, "No malware scanner is configured. Uploaded documents stay quarantined."
    try:
        prueba = escaner.scan(data=eicar_test_file(), content_type="text/plain")
        limpio = escaner.scan(data=b"CER diagnostics clean sample\n", content_type="text/plain")
    except ScannerAuthFailed:
        return AUTH_FAILED, "The scanner rejected its credentials."
    except ScannerUnavailable:
        return UNREACHABLE, "The scanner did not answer."
    if prueba.verdict != ScanVerdict.REJECTED:
        return DEGRADED, "The scanner did not detect the standard EICAR test file."
    if limpio.verdict != ScanVerdict.CLEAN:
        return DEGRADED, "The scanner flagged a harmless sample."
    return HEALTHY, f"{escaner.name} detected the EICAR test file and passed a clean sample."


async def _scanner() -> tuple[str, str]:
    return await asyncio.to_thread(_scanner_sync)


async def _scheduler() -> tuple[str, str]:
    async with async_session_maker() as session:
        latido = await session.scalar(
            select(PlatformHealthCheck.last_checked_at).where(
                PlatformHealthCheck.capability_key == HEARTBEAT_KEY
            )
        )
    if latido is None:
        return NOT_APPLICABLE, "No scheduler has run against this database yet."
    edad = datetime.now(timezone.utc) - latido
    if edad > timedelta(minutes=5):
        return DEGRADED, f"The last scheduler heartbeat was {int(edad.total_seconds() // 60)} minutes ago."
    return HEALTHY, "The scheduler is running."


async def _road_routing() -> tuple[str, str]:
    """Pide una ruta corta y conocida, y comprueba que la respuesta es creíble.

    Por qué una ruta de verdad y no un ping
    ---------------------------------------
    Un motor de routing puede responder `200 OK` y devolver una distancia de
    otro continente: es el modo de fallo que describe `OsrmRouter` —el que no
    rompe nada y miente—. Preguntar si el puerto está abierto no detecta nada
    de eso.

    Así que se pide una ruta entre dos puntos cuya separación en línea recta se
    conoce, y se comprueba lo único que es imposible falsear: **por carretera
    no se puede ir menos que en línea recta**. Si el motor ajustó las
    coordenadas a un grafo que no cubre la zona, o si alguien invirtió
    latitud y longitud en un adaptador, la relación se rompe y esto lo ve.

    Dónde está el punto de prueba
    -----------------------------
    Times Square → Bryant Park, Manhattan. No se elige por bonito: tiene que
    ser un sitio que cualquier extracto de Estados Unidos cubra, para que un
    `no hay carretera` signifique de verdad que el motor no sirve y no que el
    mapa desplegado es de otra región.

    Un motor auto-alojado con un extracto de otro país responderá
    `NoSegment`, y eso es correcto: ese despliegue **no** puede calcular las
    rutas de CER tampoco.
    """
    from decimal import Decimal

    from app.routers_api.mileage.routing import (
        Punto,
        RoutingUnavailable,
        UnconfiguredRouter,
        get_road_router,
        haversine_meters,
    )

    motor = get_road_router()
    if isinstance(motor, UnconfiguredRouter):
        return (
            NOT_APPLICABLE,
            "No routing engine is configured, so trip mileage stays pending.",
        )

    a = Punto(latitude=Decimal("40.758000"), longitude=Decimal("-73.985500"))
    b = Punto(latitude=Decimal("40.753600"), longitude=Decimal("-73.983300"))

    try:
        resultado = await motor.distance(a, b)
    except RoutingUnavailable as fallo:
        # Transitorio es "ahora no"; permanente es "esta configuración no
        # sirve". Son dos problemas distintos y se informan distinto.
        if fallo.transient:
            return UNREACHABLE, f"The routing engine did not answer: {fallo}"
        return AUTH_FAILED, f"The routing engine rejected the request: {fallo}"
    except Exception as fallo:  # noqa: BLE001
        return UNREACHABLE, f"The routing engine failed: {fallo}"

    recta = haversine_meters(a, b)
    if resultado.distance_meters < recta:
        # Geométricamente imposible. Casi siempre significa coordenadas
        # invertidas o un extracto que no cubre la zona.
        return (
            DEGRADED,
            f"{motor.name} returned {resultado.distance_meters} m for a "
            f"{recta} m straight line, which is impossible by road.",
        )

    return (
        HEALTHY,
        f"{motor.name} answered {resultado.distance_meters} m "
        f"({resultado.method}) for a known {recta} m straight line.",
    )


async def _triggers() -> tuple[str, str]:
    return await integrity.check_protection_triggers()


async def _migrations() -> tuple[str, str]:
    return await integrity.check_migrations()


async def _rbac() -> tuple[str, str]:
    return await integrity.check_rbac_catalog()


async def _master_key() -> tuple[str, str]:
    return await integrity.check_master_key()


CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition("infra.database", "PostgreSQL", "infrastructure",
                    "The database that holds every record and every audit event.", "_database"),
    CheckDefinition("email", "Outbound email", "integration",
                    "Signs in to the configured mail service without sending anything.", "_email"),
    CheckDefinition("email_fallback", "Outbound email — fallback provider", "integration",
                    "Signs in to the fallback mail service without sending anything.", "_email_fallback"),
    CheckDefinition("document_storage", "Document storage", "integration",
                    "Writes, reads and removes a probe, and confirms the bucket is private.", "_storage"),
    CheckDefinition("malware_scanner", "Malware scanning", "integration",
                    "Scans the EICAR test file, which must be rejected, and a clean sample.", "_scanner"),
    CheckDefinition("road_routing", "Road routing engine", "integration",
                    "Asks for a short known route and checks the answer is not shorter than the straight line.", "_road_routing"),
    CheckDefinition("integrity.protection_triggers", "Evidence protection", "integrity",
                    "The database triggers that stop signatures and evidence from being rewritten.", "_triggers"),
    CheckDefinition("integrity.migrations", "Database version", "integrity",
                    "The database schema is the one the code expects.", "_migrations"),
    CheckDefinition("integrity.rbac_catalog", "Permission catalog", "integrity",
                    "Every capability in the code is seeded, and nothing else is active.", "_rbac"),
    CheckDefinition("integrity.master_key", "Credential encryption", "integrity",
                    "The master key works and every stored credential decrypts.", "_master_key"),
    CheckDefinition(SCHEDULER_KEY, "Scheduler", "platform",
                    "Runs scheduled checks, quarantine rescans and reminders.", "_scheduler"),
)

BY_KEY: dict[str, CheckDefinition] = {c.key: c for c in CHECKS}


# ══ Ejecución ════════════════════════════════════════════════════════════════════


async def _record(
    *, key: str, status: str, detail: str, checked_at: datetime, duration_ms: int,
    trigger: str, actor_user_id: int | None,
) -> str | None:
    async with async_session_maker() as session:
        anterior = await session.scalar(
            select(PlatformHealthCheck.last_status).where(PlatformHealthCheck.capability_key == key)
        )
        actualizar = {
            "last_status": status,
            "last_detail": detail,
            "last_checked_at": checked_at,
            "last_checked_by_user_id": actor_user_id,
        }
        if status == HEALTHY:
            actualizar["last_success_at"] = checked_at
        await session.execute(
            pg_insert(PlatformHealthCheck)
            .values(capability_key=key, last_success_at=checked_at if status == HEALTHY else None, **{
                k: v for k, v in actualizar.items() if k != "last_success_at"
            })
            .on_conflict_do_update(index_elements=[PlatformHealthCheck.capability_key], set_=actualizar)
        )
        await session.execute(
            insert(PlatformHealthCheckRun).values(
                capability_key=key, status=status, detail=detail, checked_at=checked_at,
                duration_ms=duration_ms, actor_user_id=actor_user_id, trigger=trigger,
            )
        )
        await session.commit()
    return anterior


async def run_check(
    key: str, *, trigger: str = "manual", actor_user_id: int | None = None, alert: bool = False
) -> RunOutcome:
    definicion = BY_KEY[key]
    funcion = getattr(sys.modules[__name__], definicion.runner)
    inicio = time.monotonic()
    try:
        estado, detalle = await asyncio.wait_for(funcion(), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        estado, detalle = UNREACHABLE, f"No answer within {TIMEOUT_SECONDS}s."
    except Exception:
        logger.exception("DIAGNOSTICS | check %s failed unexpectedly", key)
        estado, detalle = UNREACHABLE, "The check failed unexpectedly. See the server log."
    duracion = int((time.monotonic() - inicio) * 1000)
    ahora = datetime.now(timezone.utc)

    anterior = await _record(
        key=key, status=estado, detail=detalle, checked_at=ahora, duration_ms=duracion,
        trigger=trigger, actor_user_id=actor_user_id,
    )
    if alert and es_regresion(anterior, estado):
        # El asunto distingue las dos regresiones porque la accion es distinta:
        # una pide investigar por que falla; la otra, volver a configurarlo.
        perdida = estado == NOT_APPLICABLE
        titular = "is no longer configured" if perdida else "is failing"
        explicacion = (
            f"{definicion.title} was configured and working, and the scheduled "
            f"check now reports that it is not configured at all. Something "
            f"removed it."
            if perdida
            else f"{definicion.title} was healthy and the scheduled check now "
            f"reports {estado}."
        )
        await notify_platform_admins(
            subject=f"{settings.APP_NAME} — {definicion.title} {titular}",
            body=(
                f"{explicacion}\n\n{detalle}\n\n"
                "Open Diagnostics to see the history."
            ),
        )
    return RunOutcome(key, estado, detalle, ahora, duracion, anterior)


async def run_all(
    *, trigger: str = "manual", actor_user_id: int | None = None, alert: bool = False
) -> list[RunOutcome]:
    return [
        await run_check(c.key, trigger=trigger, actor_user_id=actor_user_id, alert=alert)
        for c in CHECKS
    ]


async def notify_platform_admins(*, subject: str, body: str) -> int:
    """Correo a cada administrador de plataforma activo. Un fallo no interrumpe nada."""
    from app.core.email.backends import send_email
    from app.routers_api.users.models import Users

    async with async_session_maker() as session:
        correos = (
            await session.execute(
                select(Users.email).where(Users.is_superuser.is_(True), Users.is_active.is_(True))
            )
        ).scalars().all()
    enviados = 0
    for correo in correos:
        try:
            await asyncio.to_thread(send_email, to=correo, subject=subject, body=body)
            enviados += 1
        except Exception:
            logger.warning("DIAGNOSTICS | alert to a platform admin failed", exc_info=True)
    return enviados


async def write_heartbeat() -> None:
    ahora = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        await session.execute(
            pg_insert(PlatformHealthCheck)
            .values(capability_key=HEARTBEAT_KEY, last_status=HEALTHY, last_detail="heartbeat",
                    last_checked_at=ahora, last_success_at=ahora)
            .on_conflict_do_update(
                index_elements=[PlatformHealthCheck.capability_key],
                set_={"last_checked_at": ahora, "last_success_at": ahora},
            )
        )
        await session.commit()
