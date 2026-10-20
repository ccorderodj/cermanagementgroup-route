"""
Captura periódica de ubicación (RTE-LOC-02): configuración por compañía e
ingesta de muestras.

Las mismas reglas de confianza que la evidencia de eventos
(`location/service.py`), aplicadas a otra tabla:

* compañía y usuario salen de la sesión; la jornada tiene que ser **del usuario
  autenticado** en esta compañía, y si no, 404 (no se confirma que exista);
* la hora de captura no puede estar más de 5 min en el futuro ni tener más de
  30 días (los mismos márgenes que `_validar_hora_de_captura`), y tiene que caer
  dentro de la jornada (±5 min de deriva);
* la precisión tiene que cumplir el umbral de un punto fresco de la política
  `route_location` (100 m por defecto): un punto peor no sirve para reconstruir
  nada y no se guarda;
* idempotencia por `(company_id, client_sample_id)`: reenviar devuelve
  `duplicate`, nunca una segunda fila.

Con la captura **apagada**, la ingesta responde 409 `periodic_capture_disabled`
y no guarda nada: lo que el dispositivo tenga en cola se queda allí.

Nunca se registran coordenadas en los logs: sólo recuentos.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.audit.service import record_event
from app.core.dao.concurrency import ensure_version
from app.core.db.session import db_session, transaction
from app.core.platform.config_service import platform_config
from app.logger import logger
from app.routers_api.locationcapture.models import (
    INTERVALO_POR_DEFECTO,
    VERSION_DEL_AVISO,
    LocationCaptureSetting,
    LocationNoticeAck,
    LocationSample,
)
from app.routers_api.locationcapture.schemas import CaptureSettingUpdate, SampleResult, SamplesIn
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus

DERIVA = timedelta(minutes=5)
ANTIGUEDAD_MAXIMA = timedelta(days=30)


def _lectura(fila: LocationCaptureSetting | None) -> dict:
    if fila is None:
        return {
            "enabled": False, "interval_seconds": INTERVALO_POR_DEFECTO, "version": 0,
            "updated_at": None, "updated_by_user_id": None,
        }
    return {
        "enabled": fila.enabled, "interval_seconds": fila.interval_seconds, "version": fila.version,
        "updated_at": fila.updated_at, "updated_by_user_id": fila.updated_by_user_id,
    }


async def leer(company_id: int) -> dict:
    """La configuración efectiva de la compañía (apagada si no hay fila)."""
    async with db_session() as session:
        return _lectura(await session.get(LocationCaptureSetting, company_id))


async def guardar(*, company_id: int, actor_user_id: int, cambio: CaptureSettingUpdate) -> dict:
    """Guarda con bloqueo optimista y deja la auditoría (actor, antes, después)."""
    async with transaction() as session:
        fila = await session.get(LocationCaptureSetting, company_id, with_for_update=True)
        ensure_version(current=fila.version if fila else 0, expected=cambio.version)
        antes = _lectura(fila)
        if fila is None:
            fila = LocationCaptureSetting(company_id=company_id, version=1)
            session.add(fila)
        else:
            fila.version += 1
        fila.enabled = cambio.enabled
        fila.interval_seconds = cambio.interval_seconds
        fila.updated_by_user_id = actor_user_id
        await session.flush()
        await session.refresh(fila)
        despues = _lectura(fila)
    await record_event(
        company_id=company_id,
        entity_type="location_capture_setting",
        entity_id=company_id,
        action="update",
        actor_user_id=actor_user_id,
        summary=f"Periodic location capture: enabled={cambio.enabled} interval={cambio.interval_seconds}s",
        changes={
            campo: {"old": antes[campo], "new": despues[campo]}
            for campo in ("enabled", "interval_seconds")
            if antes[campo] != despues[campo]
        },
    )
    return despues


async def aviso_pendiente(*, company_id: int, user_id: int) -> bool:
    """Si esta persona todavía no vio la versión actual del aviso."""
    async with db_session() as session:
        return await session.get(LocationNoticeAck, (company_id, user_id, VERSION_DEL_AVISO)) is None


async def marcar_aviso_visto(*, company_id: int, user_id: int) -> None:
    """Guarda que la vio. Idempotente: pulsar dos veces deja una sola fila."""
    async with transaction() as session:
        await session.execute(
            pg_insert(LocationNoticeAck)
            .values(company_id=company_id, user_id=user_id, notice_version=VERSION_DEL_AVISO)
            .on_conflict_do_nothing()
        )


def _motivo(muestra, *, jornada: WorkSession, recibido: datetime, umbral: int) -> str | None:
    capturada = muestra.device_captured_at
    if capturada > recibido + DERIVA:
        return "future_timestamp"
    if recibido - capturada > ANTIGUEDAD_MAXIMA:
        return "stale"
    fin = jornada.ended_at if jornada.status == WorkSessionStatus.ENDED.value else recibido
    if capturada < jornada.started_at - DERIVA or capturada > fin + DERIVA:
        return "outside_session"
    if muestra.accuracy_m > umbral:
        return "low_accuracy"
    return None


async def ingerir(*, company_id: int, user_id: int, lote: SamplesIn, recibido: datetime) -> list[SampleResult]:
    configuracion = await leer(company_id)
    if not configuracion["enabled"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "periodic_capture_disabled",
                    "message": "Periodic location capture is off for this company."},
        )
    async with db_session() as session:
        jornada = await session.scalar(
            select(WorkSession).where(
                WorkSession.id == lote.work_session_id,
                WorkSession.company_id == company_id,
                WorkSession.user_id == user_id,
            )
        )
    if jornada is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work session not found.")

    umbral = platform_config.policy("route_location")["fresh_max_accuracy_m"]
    resultados: dict = {}
    aceptables = []
    for muestra in lote.samples:
        if muestra.client_sample_id in resultados:
            continue  # repetida dentro del mismo lote
        motivo = _motivo(muestra, jornada=jornada, recibido=recibido, umbral=umbral)
        if motivo:
            resultados[muestra.client_sample_id] = SampleResult(
                client_sample_id=muestra.client_sample_id, status="rejected", reason=motivo)
            continue
        resultados[muestra.client_sample_id] = SampleResult(
            client_sample_id=muestra.client_sample_id, status="duplicate")
        aceptables.append({
            "company_id": company_id, "work_session_id": jornada.id, "user_id": user_id,
            "client_sample_id": muestra.client_sample_id, "latitude": muestra.latitude,
            "longitude": muestra.longitude, "accuracy_m": muestra.accuracy_m,
            "device_captured_at": muestra.device_captured_at, "server_received_at": recibido,
            "interval_seconds_applied": configuracion["interval_seconds"],
        })
    if aceptables:
        async with transaction() as session:
            nuevas = (
                await session.scalars(
                    pg_insert(LocationSample)
                    .values(aceptables)
                    .on_conflict_do_nothing(constraint="uq_location_sample_client_id")
                    .returning(LocationSample.client_sample_id)
                )
            ).all()
        for cid in nuevas:
            resultados[cid] = SampleResult(client_sample_id=cid, status="accepted")

    salida = list(resultados.values())
    cuenta = {s: sum(1 for r in salida if r.status == s) for s in ("accepted", "duplicate", "rejected")}
    logger.info(
        "LOCATION SAMPLES | company=%s session=%s accepted=%s duplicate=%s rejected=%s",
        company_id, jornada.id, cuenta["accepted"], cuenta["duplicate"], cuenta["rejected"],
    )
    return salida
