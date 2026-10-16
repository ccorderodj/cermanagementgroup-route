"""Prueba controlada de los correos de actividad (RTE-MAIL-TEST-01).

* Sólo con `route.activityemails.manage`; sin sesión 401, sin capacidad 403.
* Destino cerrado: el propio correo o `MAIL_TEST_RECIPIENTS`; cualquier otro
  (otra persona del tenant, otro tenant, uno inventado) es 403 y no sale nada.
* El mensaje va marcado: «[TEST]», aviso en el cuerpo, cabecera
  `X-CER-Route-Test`, datos ficticios y el texto **guardado**.
* El resultado es honesto: un backend de pruebas no es «aceptado»; un
  proveedor que acepta no es «entregado»; un fallo de credenciales es 502 sin
  filtrar el texto del proveedor.
* Límite de 5 cada 15 minutos; cada intento queda auditado.
* No toca preferencias, jornadas ni actividades.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.core.email import backends
from app.routers_api.activityemails import content
from tests.integration.test_activity_emails import _conceder, _como, _eventos
from tests.integration.test_org_hierarchy import _filas

pytestmark = pytest.mark.integration

OBJETIVOS = "/api/activity-emails/test-targets"
PRUEBA = "/api/activity-emails/templates/{}/test-send"
MEDIODIA = "midday_motivation"
FIN = "end_of_day_recognition"


class _ProveedorQueAcepta(backends.MemoryEmailBackend):
    name = "smtp_basic"


class _ProveedorQueRechaza(backends.EmailBackend):
    name = "m365_oauth"

    def send(self, message):
        raise backends.EmailAuthFailed("Microsoft Entra ID refused the token request (invalid_client) secret=abc123")


@pytest.fixture
def lista_de_prueba(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_TEST_RECIPIENTS", "qa@cer-test.example.com, no-es-correo, QA2@cer-test.example.com")


async def _preparar(seeded, cliente):
    await _conceder(seeded, "route_admin")
    await _como(cliente, seeded, "route_admin")
    return seeded.alpha.users["route_admin"].email


async def test_sin_sesion_o_sin_capacidad(seeded, alpha_client):
    assert (await alpha_client.get(OBJETIVOS)).status_code == 401
    await _como(alpha_client, seeded, "route_admin")
    assert (await alpha_client.get(OBJETIVOS)).status_code == 403
    r = await alpha_client.post(PRUEBA.format(MEDIODIA), json={"to": seeded.alpha.users["route_admin"].email})
    assert r.status_code == 403


async def test_destinatarios_propio_y_lista(seeded, alpha_client, lista_de_prueba):
    propio = await _preparar(seeded, alpha_client)
    r = await alpha_client.get(OBJETIVOS)
    assert r.status_code == 200
    datos = r.json()
    assert datos["recipients"] == [propio, "qa@cer-test.example.com", "qa2@cer-test.example.com"]
    assert datos["provider_configured"] is False
    assert datos["limit"] == 5 and datos["window_minutes"] == 15


async def test_prueba_marcada_con_datos_ficticios_y_texto_guardado(seeded, alpha_client, outbox):
    propio = await _preparar(seeded, alpha_client)
    s = content.spec(MEDIODIA)
    guardado = s.default_body.replace("¡Vas haciendo", "¡Sigues haciendo")
    assert (await alpha_client.put(
        f"/api/activity-emails/templates/{MEDIODIA}",
        json={"subject": s.default_subject, "body": guardado, "version": 0},
    )).status_code == 200

    r = await alpha_client.post(PRUEBA.format(MEDIODIA), json={"to": propio.upper()})
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "captured_by_test_backend"
    assert r.json()["delivered_confirmed"] is False

    mensaje = outbox.last_for(propio)
    assert mensaje is not None and len(outbox.outbox) == 1
    assert mensaje.subject == "[TEST] ¡Buen trabajo! Sigamos adelante 💪"
    assert mensaje.headers == {"X-CER-Route-Test": f"activity-email; {MEDIODIA}"}
    assert mensaje.body.startswith("*** CORREO DE PRUEBA")
    assert "¡Sigues haciendo" in mensaje.body, "usa el texto guardado"
    assert "Hola, María:" in mensaje.body and "2 visitas a clientes" in mensaje.body
    assert "{{" not in mensaje.body

    evento = (await _eventos("activity_email_test"))[0]
    assert evento.action == "test_send"
    assert evento.changes["outcome"]["new"] == "captured_by_test_backend"
    assert evento.changes["to"]["new"] == propio
    assert "body" not in evento.changes


async def test_destinos_no_autorizados(seeded, alpha_client, outbox, lista_de_prueba):
    await _preparar(seeded, alpha_client)
    for destino in (
        seeded.alpha.users["supervisor"].email,
        seeded.beta.users["route_admin"].email,
        "cualquiera@gmail.com",
        "qa@cer-test.example.com, otro@x.com",
    ):
        r = await alpha_client.post(PRUEBA.format(FIN), json={"to": destino})
        assert r.status_code == 403, destino
    assert outbox.outbox == []
    r = await alpha_client.post(PRUEBA.format(FIN), json={"to": "qa2@cer-test.example.com"})
    assert r.status_code == 200
    assert (await alpha_client.post(PRUEBA.format(FIN), json={"to": "x", "cc": "y@z.com"})).status_code == 422
    assert (await alpha_client.post(PRUEBA.format("weekly"), json={"to": "qa2@cer-test.example.com"})).status_code == 404


async def test_aceptado_por_el_proveedor_no_es_entregado(seeded, alpha_client):
    propio = await _preparar(seeded, alpha_client)
    proveedor = _ProveedorQueAcepta()
    backends.set_email_backend(proveedor)
    try:
        r = await alpha_client.post(PRUEBA.format(FIN), json={"to": propio})
    finally:
        backends.set_email_backend(None)
    assert r.status_code == 200
    assert r.json()["outcome"] == "accepted_by_provider"
    assert r.json()["delivered_confirmed"] is False
    assert proveedor.last_for(propio).subject.startswith("[TEST] ¡Jornada finalizada!")


async def test_credenciales_malas_502_sin_filtrar(seeded, alpha_client):
    propio = await _preparar(seeded, alpha_client)
    backends.set_email_backend(_ProveedorQueRechaza())
    try:
        r = await alpha_client.post(PRUEBA.format(MEDIODIA), json={"to": propio})
    finally:
        backends.set_email_backend(None)
    assert r.status_code == 502
    assert r.json()["detail"]["outcome"] == "failed_auth"
    assert "secret" not in r.text and "invalid_client" not in r.text
    evento = (await _eventos("activity_email_test"))[0]
    assert evento.changes["outcome"]["new"] == "failed_auth"
    assert "secret" not in str(evento.changes)


async def test_limite_de_pruebas(seeded, alpha_client, outbox):
    propio = await _preparar(seeded, alpha_client)
    for _ in range(5):
        assert (await alpha_client.post(PRUEBA.format(MEDIODIA), json={"to": propio})).status_code == 200
    r = await alpha_client.post(PRUEBA.format(MEDIODIA), json={"to": propio})
    assert r.status_code == 429
    assert len(outbox.outbox) == 5
    assert len(await _eventos("activity_email_test")) == 5


async def test_no_toca_preferencias_jornadas_ni_actividades(seeded, alpha_client, outbox):
    propio = await _preparar(seeded, alpha_client)
    antes = await _filas(
        "SELECT (SELECT count(*) FROM work_session) AS j, (SELECT count(*) FROM activity_execution) AS a"
    )
    assert (await alpha_client.post(PRUEBA.format(FIN), json={"to": propio})).status_code == 200
    assert await _filas("SELECT 1 FROM activity_email_preference") == []
    despues = await _filas(
        "SELECT (SELECT count(*) FROM work_session) AS j, (SELECT count(*) FROM activity_execution) AS a"
    )
    assert antes == despues
