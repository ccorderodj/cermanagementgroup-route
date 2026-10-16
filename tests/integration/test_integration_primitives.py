"""
Primitivas de integración entre aplicaciones, contra la aplicación real.

* Administración de endpoints: capacidades, secreto devuelto una sola vez, auditoría.
* Webhook entrante: firma, anti-replay, aislamiento de tenant, deduplicación,
  manejador registrado, sin CSRF (servidor a servidor), correlación.
* Webhook saliente: encolado, firma verificable por la contraparte, reintentos
  con espera y fallo definitivo.
* Idempotencia y `integration_event` append-only.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.core.audit.models import AuditEvent
from app.core.integration import idempotency, webhooks
from app.core.integration.models import IntegrationEvent, WebhookDelivery
from app.core.integration.signatures import build_header, verify
from app.core.platform import secrets
from app.database import async_session_maker

pytestmark = pytest.mark.integration


@pytest.fixture
def master_key(monkeypatch):
    clave = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", clave)
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")
    return clave


@pytest.fixture
def clean_handlers():
    antes = dict(webhooks.INBOUND_HANDLERS)
    yield webhooks.INBOUND_HANDLERS
    webhooks.INBOUND_HANDLERS.clear()
    webhooks.INBOUND_HANDLERS.update(antes)


def _server_client(subdomain: str) -> AsyncClient:
    """Una contraparte servidor a servidor: sin cookies, sin testigo CSRF."""
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url=f"http://{subdomain}.{settings.BASE_DOMAIN}")


async def _create_endpoint(client, **overrides) -> dict:
    cuerpo = {"name": "Staffing inbound", "direction": "inbound", "counterpart_app": "cer-staffing",
              "event_types": []}
    cuerpo.update(overrides)
    respuesta = await client.post("/api/integrations/webhook-endpoints", json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _send(subdomain: str, public_id: str, secret: str, payload: dict, *, event_id="evt_1",
                event_type="staffing.employee.hired", timestamp=None, extra_headers=None):
    cuerpo = json.dumps(payload).encode("utf-8")
    cabeceras = {
        "Content-Type": "application/json",
        "X-CER-Signature": build_header(secret, cuerpo, timestamp=timestamp),
        "X-CER-Event-Id": event_id,
        "X-CER-Event-Type": event_type,
        "X-CER-Source-App": "cer-staffing",
        **(extra_headers or {}),
    }
    async with _server_client(subdomain) as cliente:
        return await cliente.post(f"/api/v1/webhooks/inbound/{public_id}", content=cuerpo, headers=cabeceras)


async def _events(**filters) -> list[IntegrationEvent]:
    async with async_session_maker() as session:
        consulta = select(IntegrationEvent).order_by(IntegrationEvent.id)
        for campo, valor in filters.items():
            consulta = consulta.where(getattr(IntegrationEvent, campo) == valor)
        return list((await session.execute(consulta)).scalars())


# ── Administración ──────────────────────────────────────────────────────────


async def test_the_signing_secret_is_returned_only_once(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    creado = await _create_endpoint(alpha_client)

    assert creado["signing_secret"].startswith("whsec_")
    assert creado["inbound_path"] == f"/api/v1/webhooks/inbound/{creado['public_id']}"
    listado = (await alpha_client.get("/api/integrations/webhook-endpoints")).json()
    assert [e["public_id"] for e in listado] == [creado["public_id"]]
    assert "signing_secret" not in listado[0]

    async with async_session_maker() as session:
        guardado = await session.scalar(text("SELECT secret_ciphertext FROM webhook_endpoint"))
        evento = await session.scalar(
            select(AuditEvent).where(AuditEvent.entity_type == "webhook_endpoint", AuditEvent.action == "create")
        )
    assert creado["signing_secret"].encode() not in bytes(guardado)
    assert evento is not None


async def test_managing_endpoints_requires_the_capability(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["manager"].email)
    assert (await alpha_client.get("/api/integrations/webhook-endpoints")).status_code == 200
    denegado = await alpha_client.post(
        "/api/integrations/webhook-endpoints",
        json={"name": "x", "direction": "inbound", "counterpart_app": "y", "event_types": []},
    )
    assert denegado.status_code == 403

    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (await alpha_client.get("/api/integrations/webhook-endpoints")).status_code == 403


async def test_an_endpoint_update_honours_the_version(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    creado = await _create_endpoint(alpha_client, direction="outbound", url="https://example.com/hook",
                                    name="Out")
    cambio = {"name": "Out", "url": "https://example.com/hook2", "event_types": [], "is_active": True}
    primero = await alpha_client.put(f"/api/integrations/webhook-endpoints/{creado['id']}",
                                     json={**cambio, "version": creado["version"]})
    assert primero.status_code == 200, primero.text
    viejo = await alpha_client.put(f"/api/integrations/webhook-endpoints/{creado['id']}",
                                   json={**cambio, "version": creado["version"]})
    assert viejo.status_code == 409


# ── Entrantes ───────────────────────────────────────────────────────────────


async def test_a_signed_event_is_accepted_and_recorded_once(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)

    primera = await _send("alpha", ep["public_id"], ep["signing_secret"], {"employee": 7},
                          extra_headers={"X-Correlation-ID": "corr-123"})
    assert primera.status_code == 202, primera.text
    assert primera.json() == {"status": "unhandled", "event_id": "evt_1"}

    repetida = await _send("alpha", ep["public_id"], ep["signing_secret"], {"employee": 7})
    assert repetida.status_code == 202
    assert repetida.json()["status"] == "duplicate"

    eventos = await _events(direction="inbound")
    assert [e.status for e in eventos] == ["unhandled", "duplicate"]
    assert eventos[0].correlation_id == "corr-123"
    assert eventos[0].company_id == seeded.alpha.id


async def test_a_registered_handler_runs_exactly_once(seeded, alpha_client, master_key, clean_handlers):
    recibidos = []

    @webhooks.register_inbound_handler("staffing.employee.hired")
    async def _on_hired(evento):
        recibidos.append(evento)

    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)
    for _ in range(2):
        respuesta = await _send("alpha", ep["public_id"], ep["signing_secret"], {"employee": 9})
        assert respuesta.status_code == 202

    assert len(recibidos) == 1
    assert recibidos[0].payload == {"employee": 9} and recibidos[0].company_id == seeded.alpha.id


async def test_a_bad_signature_is_rejected_and_audited(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)

    respuesta = await _send("alpha", ep["public_id"], "whsec_wrong", {"x": 1})
    assert respuesta.status_code == 401
    viejo = await _send("alpha", ep["public_id"], ep["signing_secret"], {"x": 1},
                        timestamp=int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()))
    assert viejo.status_code == 401
    assert [e.status for e in await _events(direction="inbound")] == ["rejected", "rejected"]


async def test_an_endpoint_of_another_tenant_is_not_reachable(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)

    respuesta = await _send("beta", ep["public_id"], ep["signing_secret"], {"x": 1})
    assert respuesta.status_code == 401


async def test_inbound_webhooks_need_no_csrf_but_session_writes_still_do(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)
    assert (await _send("alpha", ep["public_id"], ep["signing_secret"], {"x": 1})).status_code == 202

    async with _server_client("alpha") as sin_csrf:
        respuesta = await sin_csrf.post("/api/public/auth/login", json={"email": "a@b.c", "password": "x"})
    assert respuesta.status_code == 403


async def test_a_rotated_secret_invalidates_the_old_one(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)
    rotado = (await alpha_client.post(f"/api/integrations/webhook-endpoints/{ep['id']}/rotate-secret")).json()

    assert (await _send("alpha", ep["public_id"], ep["signing_secret"], {"x": 1}, event_id="a")).status_code == 401
    assert (await _send("alpha", ep["public_id"], rotado["signing_secret"], {"x": 1}, event_id="b")).status_code == 202


# ── Salientes ───────────────────────────────────────────────────────────────


async def test_an_outbound_event_is_delivered_signed(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client, name="Payroll out", direction="outbound",
                                url="https://payroll.example.com/hooks", event_types=["core.user.created"])
    await _create_endpoint(alpha_client, name="Other out", direction="outbound",
                           url="https://other.example.com/hooks", event_types=["core.other.thing"])

    event_id = await webhooks.enqueue_outbound(
        company_id=seeded.alpha.id, event_type="core.user.created", payload={"user": 1},
        correlation_id="corr-out",
    )
    recibidas = []

    def responder(request: httpx.Request) -> httpx.Response:
        verify(ep["signing_secret"], request.headers["X-CER-Signature"], request.content, tolerance_seconds=60)
        recibidas.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        informe = await webhooks.deliver_due(client=cliente)

    assert informe.delivered == 1
    assert len(recibidas) == 1, "sólo el endpoint suscrito recibe el evento"
    peticion = recibidas[0]
    assert peticion.headers["X-CER-Event-Id"] == event_id
    assert peticion.headers["X-Correlation-ID"] == "corr-out"
    assert json.loads(peticion.content) == {"user": 1}


async def test_a_failing_delivery_is_retried_then_marked_failed(seeded, alpha_client, master_key, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_MAX_ATTEMPTS", 2)
    await alpha_client.login(seeded.alpha.users["owner"].email)
    await _create_endpoint(alpha_client, name="Flaky", direction="outbound", url="https://flaky.example.com/h")
    await webhooks.enqueue_outbound(company_id=seeded.alpha.id, event_type="core.user.created", payload={})

    transporte = httpx.MockTransport(lambda request: httpx.Response(500))
    async with httpx.AsyncClient(transport=transporte) as cliente:
        primera = await webhooks.deliver_due(client=cliente)
        assert primera.retried == 1
        async with async_session_maker() as session:
            entrega = await session.scalar(select(WebhookDelivery))
            assert entrega.status == "pending" and entrega.next_attempt_at > datetime.now(timezone.utc)
            await session.execute(update(WebhookDelivery).values(next_attempt_at=datetime.now(timezone.utc)))
            await session.commit()
        segunda = await webhooks.deliver_due(client=cliente)

    assert segunda.failed == 1
    async with async_session_maker() as session:
        entrega = await session.scalar(select(WebhookDelivery))
    assert entrega.status == "failed" and entrega.attempts == 2 and entrega.last_status_code == 500


# ── Idempotencia y append-only ──────────────────────────────────────────────


async def test_an_idempotency_key_replays_and_refuses_another_body(seeded):
    assert (await idempotency.claim(scope="t.op", company_id=seeded.alpha.id, key="k1", request_body=b"a")).replay is False
    await idempotency.remember(scope="t.op", company_id=seeded.alpha.id, key="k1", request_body=b"a",
                               status_code=201, body={"id": 5})
    repeticion = await idempotency.claim(scope="t.op", company_id=seeded.alpha.id, key="k1", request_body=b"a")
    assert repeticion.replay and repeticion.status == 201 and repeticion.body == {"id": 5}

    with pytest.raises(Exception) as fallo:
        await idempotency.claim(scope="t.op", company_id=seeded.alpha.id, key="k1", request_body=b"b")
    assert getattr(fallo.value, "status_code", None) == 422
    # Otro tenant, misma clave: independiente.
    assert (await idempotency.claim(scope="t.op", company_id=seeded.beta.id, key="k1", request_body=b"b")).replay is False


async def test_integration_events_cannot_be_rewritten(seeded, alpha_client, master_key):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    ep = await _create_endpoint(alpha_client)
    await _send("alpha", ep["public_id"], ep["signing_secret"], {"x": 1})

    async with async_session_maker() as session:
        with pytest.raises(DBAPIError):
            await session.execute(update(IntegrationEvent).values(status="accepted"))
            await session.commit()
