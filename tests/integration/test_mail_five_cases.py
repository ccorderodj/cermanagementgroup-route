"""Los cinco envíos de prueba (RTE-MAIL-UNIFIED-01 V1.2, CP3).

| Caso | Camino | Contenido |
|---|---|---|
| T0 | Platform › Outbound email › Send Test Email | genérico, destino escrito |
| T1 | Midday Motivation › Send test | plantilla guardada, datos ficticios |
| T2 | End of Day Recognition › Send test | ídem, día y semana |
| T3 | Strategic Midday Report › Send test | dos personas ficticias, sin resumen semanal |
| T4 | Strategic End-of-Day Report › Send test | personas + **un** Team Weekly Summary al final |

Los cinco van marcados («[TEST]» una vez, banner y cabecera), comparten **el
mismo** presupuesto de 5 cada 15 minutos y no tocan preferencias, jornadas ni
actividades. Ninguno lleva datos reales.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.core.email import backends
from tests.integration.test_activity_emails import _como, _conceder
from tests.integration.test_org_hierarchy import _filas

pytestmark = pytest.mark.integration

BUZON = "qa@cer-test.example.com"
T0 = "/api/platform/integrations/email/test-message"
PLANTILLA = "/api/activity-emails/templates/{}/test-send"
CASOS = {
    "T1": "midday_motivation",
    "T2": "end_of_day_recognition",
    "T3": "strategic_midday_report",
    "T4": "strategic_end_of_day_report",
}


@pytest.fixture
def proveedor(monkeypatch):
    memoria = backends.MemoryEmailBackend()
    monkeypatch.setattr(backends, "backend_from_platform_config", lambda key="email": memoria if key == "email" else None)
    monkeypatch.setattr(settings, "MAIL_TEST_RECIPIENTS", BUZON)
    backends.set_email_backend(memoria)
    yield memoria
    backends.set_email_backend(None)


async def test_los_cinco_casos(seeded, alpha_client, proveedor):
    await alpha_client.login(seeded.platform_admin.email)
    estado_antes = await _filas(
        "SELECT (SELECT count(*) FROM work_session) j, (SELECT count(*) FROM activity_execution) a, "
        "(SELECT count(*) FROM activity_email_preference) p"
    )

    r = await alpha_client.post(T0, json={"to": BUZON})
    assert r.status_code == 200, r.text
    for caso, tipo in CASOS.items():
        r = await alpha_client.post(PLANTILLA.format(tipo), json={"to": BUZON})
        assert r.status_code == 200, (caso, r.text)
        assert r.json()["delivered_confirmed"] is False

    mensajes = proveedor.outbox
    assert len(mensajes) == 5
    t0, t1, t2, t3, t4 = mensajes
    for m in mensajes:
        assert m.to == BUZON
        assert m.subject.startswith("[TEST] ") and m.subject.count("[TEST]") == 1
        assert m.body.startswith("*** CORREO DE PRUEBA — datos ficticios")
        assert "X-CER-Route-Test" in m.headers
        assert "{{" not in m.subject + m.body

    assert t0.subject == "[TEST] CER Route — Email integration"
    assert "María" in t1.body and "Hasta ahora has realizado" in t1.body
    assert "Tu semana hasta hoy" in t2.body
    for estrategico in (t3, t4):
        assert "Ana Ejemplo" in estrategico.body and "Luis Muestra" in estrategico.body
        assert "Activity Breakdown" in estrategico.body and "Activity Details" in estrategico.body
    assert "Team Weekly Summary" not in t3.body
    assert t4.body.count("Team Weekly Summary") == 1
    assert t4.body.index("Team Weekly Summary") > t4.body.rindex("Weekly Activity Summary")

    # Un sexto, por cualquier camino, ya no cabe: el presupuesto es uno.
    assert (await alpha_client.post(PLANTILLA.format(CASOS["T4"]), json={"to": BUZON})).status_code == 429
    assert (await alpha_client.post(T0, json={"to": BUZON})).status_code == 429

    assert await _filas(
        "SELECT (SELECT count(*) FROM work_session) j, (SELECT count(*) FROM activity_execution) a, "
        "(SELECT count(*) FROM activity_email_preference) p"
    ) == estado_antes
    canales = sorted((f.channel, f.target) for f in await _filas("SELECT channel, target FROM mail_test_send"))
    assert canales == sorted([("provider", "email"), *(("template", t) for t in CASOS.values())])


async def test_t3_t4_destinos_cerrados_para_el_tenant(seeded, alpha_client, proveedor):
    """El destino libre es sólo de T0 y de la plataforma: las plantillas no."""
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    for tipo in (CASOS["T3"], CASOS["T4"]):
        r = await alpha_client.post(PLANTILLA.format(tipo), json={"to": "externo@otro-dominio.com"})
        assert r.status_code == 403
    assert (await alpha_client.post(T0, json={"to": BUZON})).status_code == 403, "T0 no es del tenant"
    assert proveedor.outbox == []
