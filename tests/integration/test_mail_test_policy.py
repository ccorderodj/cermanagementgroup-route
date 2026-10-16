"""Política común de las pruebas de correo (RTE-MAIL-UNIFIED-01, CP1).

T0 (proveedor, Platform) y T1/T2 (plantillas, Activity Emails) comparten:

* destinos cerrados en las plantillas: el propio correo o `MAIL_TEST_RECIPIENTS`
  (en T0 el administrador de plataforma escribe la dirección, V1.2);
* **un solo presupuesto** de 5 pruebas cada 15 minutos por persona, sumando
  los dos caminos, correcto con peticiones simultáneas;
* «[TEST]» una sola vez, banner y cabecera `X-CER-Route-Test`;
* resultado honesto y sin respaldo oculto en T0: si el proveedor elegido no
  está configurado es `not_configured`, aunque el de respaldo sí lo esté.
"""

from __future__ import annotations

import asyncio

import pytest

from app.config import settings
from app.core.email import backends
from app.routers_api.activityemails import content
from tests.integration.test_activity_emails import _conceder, _como
from tests.integration.test_org_hierarchy import _filas

pytestmark = pytest.mark.integration

T0 = "/api/platform/integrations/{}/test-message"
T0_DESTINOS = "/api/platform/integrations/{}/test-targets"
T1 = "/api/activity-emails/templates/midday_motivation/test-send"
BUZON = "qa@cer-test.example.com"


class _ProveedorQueRechaza(backends.EmailBackend):
    name = "m365_oauth"
    sender = "no-reply@cer-test.example.com"

    def send(self, message):
        raise backends.EmailAuthFailed("AADSTS7000215 invalid_client secret=abc123 tenant=xyz")


@pytest.fixture
def buzon(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_TEST_RECIPIENTS", BUZON)


@pytest.fixture
def proveedor(monkeypatch):
    """El proveedor «email» configurado, capturando en memoria."""
    memoria = backends.MemoryEmailBackend()
    monkeypatch.setattr(
        backends, "backend_from_platform_config", lambda key="email": memoria if key == "email" else None
    )
    return memoria


async def _como_plataforma(seeded, cliente):
    await cliente.login(seeded.platform_admin.email)


# ── T0: autorización y destinos ─────────────────────────────────────────────


async def test_t0_solo_administracion_de_plataforma(seeded, alpha_client, buzon, proveedor):
    assert (await alpha_client.post(T0.format("email"), json={"to": BUZON})).status_code == 401
    await _conceder(seeded, "route_admin")
    for actor in ("owner", "admin", "route_admin"):
        await _como(alpha_client, seeded, actor)
        assert (await alpha_client.post(T0.format("email"), json={"to": BUZON})).status_code == 403, actor
        assert (await alpha_client.get(T0_DESTINOS.format("email"))).status_code == 403, actor
    assert proveedor.outbox == []


async def test_t0_destino_escrito_por_el_administrador(seeded, alpha_client, buzon, proveedor):
    """V1.2: en T0 el administrador de plataforma escribe la dirección; las
    sugerencias siguen siendo el propio correo y `MAIL_TEST_RECIPIENTS`."""
    await _como_plataforma(seeded, alpha_client)
    destinos = (await alpha_client.get(T0_DESTINOS.format("email"))).json()
    assert destinos["recipients"] == [seeded.platform_admin.email.lower(), BUZON]

    r = await alpha_client.post(T0.format("email"), json={"to": "  Externo.QA@Otro-Dominio.com "})
    assert r.status_code == 200, r.text
    assert r.json()["to"] == "externo.qa@otro-dominio.com"
    assert proveedor.last_for("externo.qa@otro-dominio.com") is not None

    for malo in (
        "no-es-correo", "a@b", "x@y.com\nBcc: z@w.com", "a@b.com, c@d.com", "<a@b.com>",
        "a@b.com;c@d.com", "x" * 250 + "@b.com",
    ):
        assert (await alpha_client.post(T0.format("email"), json={"to": malo})).status_code == 422, malo
    assert (await alpha_client.post(T0.format("email"), json={"to": BUZON, "cc": "x@y.com"})).status_code == 422
    assert (await alpha_client.post(T0.format("email"), json={"to": BUZON, "bcc": "x@y.com"})).status_code == 422
    assert (await alpha_client.post(T0.format("storage"), json={"to": BUZON})).status_code == 404
    assert len(proveedor.outbox) == 1
    assert len(await _filas("SELECT 1 FROM mail_test_send")) == 1, "los rechazos no consumen presupuesto"


async def test_t0_marcado_y_resultado_honesto(seeded, alpha_client, buzon, proveedor):
    await _como_plataforma(seeded, alpha_client)
    r = await alpha_client.post(T0.format("email"), json={"to": BUZON.upper()})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "outcome": "captured_by_test_backend", "to": BUZON, "backend": "memory", "delivered_confirmed": False,
    }
    m = proveedor.last_for(BUZON)
    assert m.subject == "[TEST] CER Route — Email integration"
    assert m.body.startswith("*** CORREO DE PRUEBA — datos ficticios")
    assert m.headers == {"X-CER-Route-Test": "provider; email"}
    fila = (await _filas("SELECT channel, target, destination, outcome, backend, finished_at FROM mail_test_send"))[0]
    assert (fila.channel, fila.target, fila.destination, fila.outcome, fila.backend) == (
        "provider", "email", BUZON, "captured_by_test_backend", "memory",
    )
    assert fila.finished_at is not None


async def test_t0_sin_respaldo_oculto(seeded, alpha_client, buzon, monkeypatch):
    """Si el elegido no está configurado, no se prueba en silencio el de respaldo."""
    respaldo = backends.MemoryEmailBackend()
    monkeypatch.setattr(
        backends, "backend_from_platform_config", lambda key="email": respaldo if key == "email_fallback" else None
    )
    await _como_plataforma(seeded, alpha_client)
    r = await alpha_client.post(T0.format("email"), json={"to": BUZON})
    assert r.status_code == 409
    assert r.json()["detail"]["outcome"] == "not_configured"
    assert respaldo.outbox == []
    assert await _filas("SELECT 1 FROM mail_test_send") == [], "no consume presupuesto"


async def test_t0_credenciales_malas_sin_filtrar(seeded, alpha_client, buzon, monkeypatch):
    monkeypatch.setattr(backends, "backend_from_platform_config", lambda key="email": _ProveedorQueRechaza())
    await _como_plataforma(seeded, alpha_client)
    r = await alpha_client.post(T0.format("email"), json={"to": BUZON})
    assert r.status_code == 502
    assert r.json()["detail"]["outcome"] == "failed_auth"
    for secreto in ("AADSTS", "invalid_client", "abc123", "xyz"):
        assert secreto not in r.text
    eventos = await _filas(
        "SELECT action, changes FROM platform_audit_event WHERE action LIKE 'email.test%' ORDER BY id"
    )
    assert eventos[-1].action == "email.test_failed"
    assert "AADSTS" not in str(eventos[-1].changes) and "abc123" not in str(eventos[-1].changes)
    assert (await _filas("SELECT outcome FROM mail_test_send"))[0].outcome == "failed_auth"


# ── Presupuesto compartido ──────────────────────────────────────────────────


async def test_presupuesto_compartido_entre_t0_y_plantillas(seeded, alpha_client, buzon, proveedor, outbox):
    """3 de plantilla + 2 de proveedor agotan el mismo presupuesto."""
    await _como_plataforma(seeded, alpha_client)
    for _ in range(3):
        assert (await alpha_client.post(T1, json={"to": BUZON})).status_code == 200
    for _ in range(2):
        assert (await alpha_client.post(T0.format("email"), json={"to": BUZON})).status_code == 200
    assert (await alpha_client.post(T1, json={"to": BUZON})).status_code == 429
    assert (await alpha_client.post(T0.format("email"), json={"to": BUZON})).status_code == 429
    canales = sorted(f.channel for f in await _filas("SELECT channel FROM mail_test_send"))
    assert canales == ["provider", "provider", "template", "template", "template"]


async def test_presupuesto_con_peticiones_simultaneas(seeded, alpha_client, buzon, outbox):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    respuestas = await asyncio.gather(*(alpha_client.post(T1, json={"to": BUZON}) for _ in range(9)))
    codigos = sorted(r.status_code for r in respuestas)
    assert codigos == [200] * 5 + [429] * 4, codigos
    assert len(outbox.outbox) == 5
    assert len(await _filas("SELECT 1 FROM mail_test_send")) == 5


async def test_test_una_sola_vez_en_el_asunto(seeded, alpha_client, buzon, outbox):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    s = content.spec("midday_motivation")
    assert (await alpha_client.put(
        "/api/activity-emails/templates/midday_motivation",
        json={"subject": "[TEST] Hola {{user_first_name}}", "body": s.default_body, "version": 0},
    )).status_code == 200
    r = await alpha_client.post(T1, json={"to": BUZON})
    assert r.status_code == 200
    assert r.json()["subject"] == "[TEST] Hola María"
    assert r.json()["backend"] == "memory"
