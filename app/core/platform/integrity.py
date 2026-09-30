"""
Los controles que dan valor legal a la evidencia, comprobados en vivo (S4).

Diagnostics medía conectividad —¿contesta el correo?— pero no lo que hace que
un expediente firmado siga siendo prueba: que la firma no se pueda reescribir,
que la base esté en la versión del código, que los permisos sean los del
catálogo. Si alguien desactivara un disparador desde una consola, la pantalla
seguiría en verde. Ahora no.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.core.platform.secrets import current_key_id, master_key_status, seal, unseal
from app.database import async_session_maker

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Los disparadores que protegen la evidencia. Si falta uno o está desactivado,
#: la garantía correspondiente dejó de existir aunque el código no haya
#: cambiado. `tests/test_platform_integrity_catalog.py` exige que cada
#: `CREATE TRIGGER` de las migraciones esté en esta lista.
EXPECTED_TRIGGERS: tuple[str, ...] = (
    "trg_audit_event_append_only",
    "trg_audit_event_no_truncate",
    "trg_integration_event_append_only",
    "trg_integration_event_no_truncate",
    "trg_platform_audit_event_append_only",
    "trg_platform_audit_event_no_truncate",
    "trg_platform_health_check_run_append_only",
    "trg_platform_health_check_run_no_truncate",
    # RTE06. La evidencia de ubicación y la provenance de cada tramo son hechos
    # medidos: si alguien desactivara estos disparadores, un kilometraje
    # histórico se podría reescribir sin que nada protestara, que es justo lo
    # que §27 prohíbe.
    "trg_location_fix_append_only",
    "trg_location_fix_no_truncate",
    "trg_trip_mileage_segment_append_only",
    "trg_trip_mileage_segment_no_truncate",
    # El de `missing_location_event` no es el genérico: admite `UPDATE` de los
    # campos de notificación y rechaza todo lo demás. Se vigila igual — que
    # exista y esté activo es lo que garantiza que el hecho no se reescriba.
    "trg_missing_location_event_append_only",
    "trg_missing_location_event_no_truncate",
)

HEALTHY, DEGRADED, NOT_APPLICABLE = "healthy", "degraded", "not_applicable"


async def check_protection_triggers() -> tuple[str, str]:
    async with async_session_maker() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT t.tgname, t.tgenabled FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid = t.tgrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public' "
                    "WHERE NOT t.tgisinternal"
                )
            )
        ).all()
    presentes = {nombre: estado for nombre, estado in filas}
    faltan = [t for t in EXPECTED_TRIGGERS if t not in presentes]
    # `D` = desactivado. `O`, `R` y `A` disparan.
    desactivados = [t for t in EXPECTED_TRIGGERS if presentes.get(t) in ("D", b"D")]
    if faltan or desactivados:
        partes = []
        if faltan:
            partes.append(f"missing: {', '.join(faltan)}")
        if desactivados:
            partes.append(f"disabled: {', '.join(desactivados)}")
        return DEGRADED, "Evidence protection is not in place — " + "; ".join(partes) + "."
    return HEALTHY, f"All {len(EXPECTED_TRIGGERS)} evidence protection triggers are installed and enabled."


def _code_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(REPO_ROOT / "app" / "alembic.ini"))
    ubicacion = config.get_main_option("script_location") or "app/migrations"
    if not Path(ubicacion).is_absolute():
        config.set_main_option("script_location", str(REPO_ROOT / ubicacion))
    return ScriptDirectory.from_config(config).get_current_head()


async def check_migrations() -> tuple[str, str]:
    cabecera = _code_head()
    async with async_session_maker() as session:
        base = await session.scalar(text("SELECT version_num FROM alembic_version"))
    if base != cabecera:
        return DEGRADED, (
            f"The database is at {base} but the code expects {cabecera}. "
            "Run the migrations before serving traffic."
        )
    return HEALTHY, f"The database schema matches the code ({cabecera})."


async def check_rbac_catalog() -> tuple[str, str]:
    from app.core.rbac.catalog import CAPABILITY_NAMES

    async with async_session_maker() as session:
        activas = set(
            (await session.execute(text("SELECT name FROM permission WHERE is_active"))).scalars()
        )
    faltan = sorted(set(CAPABILITY_NAMES) - activas)
    sobran = sorted(activas - set(CAPABILITY_NAMES))
    if faltan or sobran:
        partes = []
        if faltan:
            partes.append(f"{len(faltan)} capabilities are not seeded ({', '.join(faltan[:5])}…)")
        if sobran:
            partes.append(f"{len(sobran)} active permissions are not in the catalog")
        return DEGRADED, "; ".join(partes) + ". Run the bootstrap."
    return HEALTHY, f"The {len(CAPABILITY_NAMES)} catalog capabilities match the database."


async def check_master_key() -> tuple[str, str]:
    async with async_session_maker() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT s.name, s.ciphertext, s.nonce, s.key_id, i.key FROM platform_secret s "
                    "JOIN platform_integration i ON i.id = s.integration_id"
                )
            )
        ).all()

    if not master_key_status()["present"]:
        if filas:
            return DEGRADED, (
                f"PLATFORM_MASTER_KEY is not configured: {len(filas)} stored credentials cannot be read."
            )
        return DEGRADED, "PLATFORM_MASTER_KEY is not configured, so no credential can be stored."

    canario = seal(integration_key="diagnostics", secret_name="canary", plaintext="canary")
    if unseal(
        integration_key="diagnostics", secret_name="canary", ciphertext=canario.ciphertext,
        nonce=canario.nonce, stored_key_id=canario.key_id,
    ) != "canary":
        return DEGRADED, "The master key did not round-trip a test value."

    ilegibles = []
    antiguas = 0
    for nombre, cifrado, nonce, key_id, integracion in filas:
        try:
            unseal(
                integration_key=integracion, secret_name=nombre, ciphertext=bytes(cifrado),
                nonce=bytes(nonce), stored_key_id=key_id,
            )
        except Exception:
            ilegibles.append(f"{integracion}:{nombre}")
        if key_id != current_key_id():
            antiguas += 1
    if ilegibles:
        return DEGRADED, f"These credentials do not decrypt with the configured keys: {', '.join(ilegibles)}."
    if antiguas:
        return DEGRADED, (
            f"{antiguas} credentials are still encrypted with the previous key. Run the rotation command."
        )
    return HEALTHY, f"The master key works and all {len(filas)} stored credentials decrypt."
