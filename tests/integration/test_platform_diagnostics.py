"""
WP-4: Diagnostics, verificación y el veredicto único de preparación.

Lo que se congela:

* **Un gate de integración sólo se cierra verificando**, y verificar ejecuta la
  comprobación de verdad. Configurar no basta (S1).
* **La preparación no se declara con OD-15 abierta**, aunque todo lo demás esté
  verde.
* **Integridad en vivo** (S4): los disparadores, la versión y el catálogo, contra
  la base de pruebas real.
* **Historial append-only** y alerta al pasar de sano a fallido (S7).
* La postura no revela la clave de firma.
* Sólo administración de plataforma.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.core.email import backends
from app.core.platform import diagnostics, secrets
from app.core.platform.integrity import EXPECTED_TRIGGERS
from app.core.platform.models import PlatformAuditEvent, PlatformHealthCheckRun
from app.database import async_session_maker

SMTP = {
    "provider": "smtp_basic",
    "config": {"host": "smtp.example.com", "port": 587, "use_tls": "true",
               "username": "apikey", "sender": "no-reply@example.com"},
}


@pytest.fixture
def master_key(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", secrets.generate_master_key())
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")


async def _correo_configurado(client):
    assert (await client.put("/api/platform/integrations/email", json=SMTP)).status_code == 200
    assert (await client.put(
        "/api/platform/integrations/email/secrets/password", json={"value": "smtp-password-value"}
    )).status_code == 200


def _gate(informe, clave):
    return next(g for g in informe["gates"] if g["key"] == clave)


async def test_readiness_is_not_declared_while_a_blocking_gate_is_open(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)

    informe = (await alpha_client.get("/api/platform/readiness")).json()

    assert informe["production_ready"] is False
    correo = _gate(informe, "email")
    assert correo["status"] == "open" and correo["blocks_production"] is True
    # La base no trae gates de dominio: sólo infraestructura y seguridad.
    assert {g["key"] for g in informe["gates"]} == {
        "email", "document_storage", "malware_scanner", "credential_encryption",
        "evidence_integrity", "security_posture",
    }


async def test_configuring_is_not_enough_verifying_closes_the_gate(
    seeded, alpha_client, master_key, monkeypatch
):
    await alpha_client.login(seeded.platform_admin.email)
    await _correo_configurado(alpha_client)
    assert _gate((await alpha_client.get("/api/platform/readiness")).json(), "email")["status"] == "open"

    monkeypatch.setattr(backends.SmtpEmailBackend, "check", lambda self: None)
    verificado = await alpha_client.post("/api/platform/integrations/email/verify")

    assert verificado.status_code == 200, verificado.text
    cuerpo = verificado.json()
    assert cuerpo["check"]["status"] == "healthy"
    assert cuerpo["integration"]["status"] == "verified"
    assert _gate((await alpha_client.get("/api/platform/readiness")).json(), "email")["status"] == "closed"


async def test_a_failed_verification_leaves_the_gate_open_and_records_why(
    seeded, alpha_client, master_key, monkeypatch
):
    await alpha_client.login(seeded.platform_admin.email)
    await _correo_configurado(alpha_client)

    def _rechaza(self):
        raise backends.EmailAuthFailed("The mail server rejected the configured credentials.")

    monkeypatch.setattr(backends.SmtpEmailBackend, "check", _rechaza)
    respuesta = await alpha_client.post("/api/platform/integrations/email/verify")

    assert respuesta.json()["check"]["status"] == "auth_failed"
    assert respuesta.json()["integration"]["verified_at"] is None
    historial = (await alpha_client.get("/api/platform/diagnostics/email/history")).json()
    assert historial[0]["trigger"] == "verify" and historial[0]["status"] == "auth_failed"
    async with async_session_maker() as session:
        acciones = (await session.execute(select(PlatformAuditEvent.action))).scalars().all()
    assert "integration.verification_failed" in acciones


async def test_an_incomplete_integration_cannot_be_verified(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    assert (await alpha_client.put("/api/platform/integrations/email", json=SMTP)).status_code == 200

    respuesta = await alpha_client.post("/api/platform/integrations/email/verify")

    assert respuesta.status_code == 409
    assert "SMTP password" in respuesta.text


async def test_a_test_message_goes_through_the_configured_backend(
    seeded, alpha_client, master_key, monkeypatch
):
    await alpha_client.login(seeded.platform_admin.email)
    await _correo_configurado(alpha_client)
    memoria = backends.MemoryEmailBackend()
    monkeypatch.setattr(backends, "backend_from_platform_config", lambda key="email": memoria)

    respuesta = await alpha_client.post(
        "/api/platform/integrations/email/test-message", json={"to": "ops@example.com"}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert memoria.last_for("ops@example.com") is not None


async def test_integrity_checks_pass_against_the_real_test_database(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)

    resultados = {
        r["capability_key"]: r
        for r in (await alpha_client.post("/api/platform/diagnostics/run-all")).json()
    }

    assert resultados["infra.database"]["status"] == "healthy"
    assert resultados["integrity.protection_triggers"]["status"] == "healthy", resultados["integrity.protection_triggers"]
    assert resultados["integrity.migrations"]["status"] == "healthy", resultados["integrity.migrations"]
    assert resultados["integrity.rbac_catalog"]["status"] == "healthy", resultados["integrity.rbac_catalog"]
    assert resultados["integrity.master_key"]["status"] == "healthy"
    assert resultados["email"]["status"] == "not_applicable"
    assert resultados["malware_scanner"]["status"] == "not_applicable"


async def test_a_disabled_protection_trigger_is_detected(seeded, alpha_client, master_key):
    async with async_session_maker() as session:
        await session.execute(text("ALTER TABLE audit_event DISABLE TRIGGER trg_audit_event_append_only"))
        await session.commit()
    try:
        estado, detalle = await diagnostics._triggers()
    finally:
        async with async_session_maker() as session:
            await session.execute(text("ALTER TABLE audit_event ENABLE TRIGGER trg_audit_event_append_only"))
            await session.commit()

    assert estado == "degraded"
    assert "trg_audit_event_append_only" in detalle


async def test_the_check_history_cannot_be_rewritten(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)
    await alpha_client.post("/api/platform/diagnostics/infra.database/run")

    async with async_session_maker() as session:
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text("UPDATE platform_health_check_run SET status = 'healthy'"))
        await session.rollback()


async def test_a_scheduled_check_that_starts_failing_alerts_platform_admins(
    seeded, master_key, monkeypatch, outbox
):
    estados = iter([("healthy", "ok"), ("unreachable", "down")])

    async def _falso():
        return next(estados)

    monkeypatch.setattr(diagnostics, "_database", _falso)
    await diagnostics.run_check("infra.database", trigger="scheduled", alert=True)
    await diagnostics.run_check("infra.database", trigger="scheduled", alert=True)

    aviso = outbox.last_for(seeded.platform_admin.email)
    assert aviso is not None and "PostgreSQL is failing" in aviso.subject
    async with async_session_maker() as session:
        disparos = (await session.execute(select(PlatformHealthCheckRun.trigger))).scalars().all()
    assert disparos == ["scheduled", "scheduled"]


async def test_the_posture_never_reveals_the_signing_key(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.platform_admin.email)

    respuesta = await alpha_client.get("/api/platform/posture")

    assert respuesta.status_code == 200
    assert settings.SECRET_KEY not in respuesta.text
    assert settings.PLATFORM_MASTER_KEY not in respuesta.text
    assert {p["key"] for p in respuesta.json()} >= {"secure_cookies", "api_docs", "master_key"}


async def test_a_company_owner_cannot_see_or_run_diagnostics(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    for metodo, url in (
        ("get", "/api/platform/readiness"), ("get", "/api/platform/diagnostics"),
        ("post", "/api/platform/diagnostics/run-all"), ("post", "/api/platform/integrations/email/verify"),
    ):
        assert (await getattr(alpha_client, metodo)(url)).status_code == 403, url


async def test_the_scheduler_has_a_single_leader(seeded):
    from app.core.platform.scheduler import PlatformScheduler
    from app.database import DATABASE_URL

    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    uno, otro = PlatformScheduler(), PlatformScheduler()
    try:
        assert await uno.try_leadership(dsn) is True
        assert await otro.try_leadership(dsn) is False
        await uno.release()
        assert await otro.try_leadership(dsn) is True
    finally:
        await uno.release()
        await otro.release()


def test_every_trigger_created_by_a_migration_is_watched():
    """Cada disparador que crea una migración está en la lista que vigila Diagnostics.

    Las migraciones pueden escribir el nombre literal (`CREATE TRIGGER trg_x`) o
    generarlo desde `APPEND_ONLY_TABLES` (`trg_{tabla}_append_only`); se cubren
    las dos formas.
    """
    import importlib.util

    migraciones = Path(__file__).resolve().parents[2] / "app" / "migrations" / "versions"
    creados = set()
    for fichero in migraciones.glob("*.py"):
        texto = fichero.read_text(encoding="utf-8")
        for nombre in re.findall(r"CREATE TRIGGER\s+(trg_[a-z0-9_]+)", texto):
            if not nombre.endswith("_"):
                creados.add(nombre)
        if "APPEND_ONLY_TABLES" in texto:
            spec = importlib.util.spec_from_file_location(f"_mig_{fichero.stem}", fichero)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            for tabla in modulo.APPEND_ONLY_TABLES:
                creados |= {f"trg_{tabla}_append_only", f"trg_{tabla}_no_truncate"}
    assert creados, "no se encontraron disparadores en las migraciones"
    assert creados <= set(EXPECTED_TRIGGERS), f"sin vigilar: {sorted(creados - set(EXPECTED_TRIGGERS))}"
    assert set(EXPECTED_TRIGGERS) <= creados, f"vigilados pero no creados: {sorted(set(EXPECTED_TRIGGERS) - creados)}"

# ── Perder una configuración es una regresión, no una ausencia ──────────────


async def test_perder_una_configuracion_avisa_a_los_administradores(
    seeded, master_key, monkeypatch, outbox
):
    """`healthy` -> `not_applicable` es una pérdida, y hay que oírla.

    Es el caso que ocurrió en campo: la integración de routing desapareció, el
    chequeo lo detectó en la ejecución siguiente y lo repitió 77 veces durante
    seis días sin avisar, porque `not_applicable` no estaba en `FAILURES`. Se
    descubrió mirando una pantalla llena de ceros.
    """
    estados = iter([("healthy", "answering"), ("not_applicable", "no engine")])

    async def _falso():
        return next(estados)

    monkeypatch.setattr(diagnostics, "_road_routing", _falso)
    await diagnostics.run_check("road_routing", trigger="scheduled", alert=True)
    await diagnostics.run_check("road_routing", trigger="scheduled", alert=True)

    aviso = outbox.last_for(seeded.platform_admin.email)
    assert aviso is not None, (
        "la configuración se perdió y nadie recibió nada: vuelve el silencio "
        "de seis días"
    )
    assert "is no longer configured" in aviso.subject, aviso.subject
    assert "Something removed it" in aviso.body


async def test_no_configurado_desde_el_principio_no_es_una_alarma(
    seeded, master_key, monkeypatch, outbox
):
    """El control negativo, y es el que hace válido al test anterior.

    Que una capacidad opcional nunca se haya configurado no es un incidente: es
    una decisión pendiente. Si esto avisara, cada instalación nueva empezaría
    mandando correos por el correo que todavía no existe.
    """

    async def _falso():
        return ("not_applicable", "no engine")

    monkeypatch.setattr(diagnostics, "_road_routing", _falso)
    await diagnostics.run_check("road_routing", trigger="scheduled", alert=True)
    await diagnostics.run_check("road_routing", trigger="scheduled", alert=True)

    assert outbox.last_for(seeded.platform_admin.email) is None, (
        "avisó de algo que nunca estuvo configurado"
    )


async def test_recuperarse_tampoco_es_una_alarma(
    seeded, master_key, monkeypatch, outbox
):
    """Volver a estar sano no avisa. El aviso es de lo que se rompe."""
    estados = iter([("not_applicable", "no engine"), ("healthy", "answering")])

    async def _falso():
        return next(estados)

    monkeypatch.setattr(diagnostics, "_road_routing", _falso)
    await diagnostics.run_check("road_routing", trigger="scheduled", alert=True)
    await diagnostics.run_check("road_routing", trigger="scheduled", alert=True)

    assert outbox.last_for(seeded.platform_admin.email) is None


def test_la_regla_es_estaba_sano_y_ya_no():
    """La regla, fijada sin base de datos ni correo.

    Si alguien añade un estado nuevo mañana, queda cubierto sin tener que
    acordarse de incluirlo en ninguna lista — que es justo lo que falló.
    """
    assert diagnostics.es_regresion("healthy", "not_applicable") is True
    assert diagnostics.es_regresion("healthy", "degraded") is True
    assert diagnostics.es_regresion("healthy", "unreachable") is True
    assert diagnostics.es_regresion("healthy", "auth_failed") is True
    assert diagnostics.es_regresion("healthy", "un_estado_futuro") is True

    assert diagnostics.es_regresion("healthy", "healthy") is False
    assert diagnostics.es_regresion(None, "not_applicable") is False
    assert diagnostics.es_regresion("not_applicable", "not_applicable") is False
    assert diagnostics.es_regresion("degraded", "unreachable") is False
    assert diagnostics.es_regresion("not_applicable", "healthy") is False
