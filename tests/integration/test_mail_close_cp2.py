"""RTE-MAIL-CLOSE-01 · CP2: estado operativo leído y Delivery History.

* `/status`: proveedor (Verify), interruptores, tipos activos y la última
  pasada vista de cada reloj; nada de «automatización pendiente» fijo.
* `/history`: entregas y reenvíos con disparador, corte, zona, estado, motivo
  legible, próximo reintento y retraso; filtros y alcance; sin contenido.
* Nada se pierde en silencio: sin zona queda `configuration_required`; fuera
  de la ventana de recuperación queda `recovery_window_expired`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.routers_api.activityemails import delivery
from tests.integration.test_activity_email_delivery import (  # noqa: F401 — fixtures
    DIA,
    EST_MEDIODIA,
    MOT_FIN,
    MOT_MEDIODIA,
    PREVIEW,
    RESEND,
    SEND,
    ZONA,
    _activar,
    _capacidades,
    _jornada_en,
    _pedido,
    _utc,
    _zona_de_la_compania,
    automatico,
    envio_real,
)
from tests.integration.test_activity_emails import _como
from tests.integration.test_org_hierarchy import _filas, _organigrama

pytestmark = pytest.mark.integration

ESTADO = "/api/activity-emails/status"
HISTORIA = "/api/activity-emails/history"


async def _admin(seeded, cliente, *mas):
    await _capacidades(seeded, "route_admin", "route.activityemails.manage", *mas)
    await _como(cliente, seeded, "route_admin")


async def test_estado_leido_del_servidor(seeded, alpha_client, envio_real):
    await _como(alpha_client, seeded, "route_admin")
    assert (await alpha_client.get(ESTADO)).status_code == 403
    await _admin(seeded, alpha_client)
    e = (await alpha_client.get(ESTADO)).json()
    assert e["automation_enabled"] is False and e["dry_run"] is True
    assert e["real_send_types"] == sorted([MOT_MEDIODIA, MOT_FIN, EST_MEDIODIA, "strategic_end_of_day_report"])
    assert e["runs"] == [], "ningún reloj visto todavía: la pantalla no puede afirmar que el job corre"
    assert "secret" not in str(e).lower() and "password" not in str(e).lower()

    await delivery.despachar_vencidos(source="reconcile")
    e = (await alpha_client.get(ESTADO)).json()
    assert [(r["source"], r["outcome"], r["enabled"]) for r in e["runs"]] == [("reconcile", "completed", False)]


async def test_historial_con_reenvios_filtros_y_sin_contenido(seeded, alpha_client, outbox, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _admin(seeded, alpha_client, "route.activityemails.send", "route.activityemails.resend")
    assert (await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).status_code == 200
    assert (await alpha_client.post(RESEND, json={**_pedido(seeded, "supervisor", MOT_MEDIODIA),
                                                  "expected_resends": 0})).status_code == 200

    h = (await alpha_client.get(HISTORIA)).json()
    assert h["count"] == 1
    fila = h["results"][0]
    assert fila["recipient_name"] == "Supervisor Tester" and fila["source"] == "manual"
    assert fila["status"] == "accepted_by_provider" and fila["time_zone"] == ZONA
    assert fila["cutoff_at"] and fila["due_at"] and fila["delay_seconds"] is None, "el retraso es de los automáticos"
    assert [(r["sequence"], r["status"]) for r in fila["resends"]] == [(1, "accepted_by_provider")]
    texto = str(h)
    for prohibido in ("subject", "body", "notes", "@alpha"):
        assert prohibido not in texto

    assert (await alpha_client.get(HISTORIA, params={"trigger": "resend"})).json()["count"] == 1
    assert (await alpha_client.get(HISTORIA, params={"trigger": "scheduler"})).json()["count"] == 0
    assert (await alpha_client.get(HISTORIA, params={"report_type": MOT_FIN})).json()["count"] == 0
    assert (await alpha_client.get(HISTORIA, params={"date_from": (DIA + timedelta(days=1)).isoformat()})).json()["count"] == 0
    assert (await alpha_client.get(HISTORIA, params={"report_type": "weekly"})).status_code == 404


async def test_historial_acotado_a_la_rama(seeded, alpha_client, outbox, envio_real):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)
    await _jornada_en(alpha_client, seeded, "sup_b", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "sup_b", "midday_enabled")
    await _admin(seeded, alpha_client, "route.activityemails.send")
    assert (await alpha_client.post(SEND, json=_pedido(seeded, "sup_b", MOT_MEDIODIA))).status_code == 200

    await _capacidades(seeded, "COO", "route.activityemails.manage")
    await _como(alpha_client, seeded, "coo")
    assert (await alpha_client.get(HISTORIA)).json()["count"] == 0, "SUP-B no es de la rama del COO"


async def test_sin_zona_queda_pendiente_y_a_la_vista(seeded, alpha_client, automatico, outbox):
    await _organigrama(alpha_client, seeded)
    await _activar(seeded, "coo", "strategic_midday_enabled")
    r = await delivery.despachar_vencidos(ahora=_utc(17))
    assert r.config_required == 1 and r.accepted == 0
    fila = (await _filas("SELECT status, reason_code FROM activity_email_delivery"))[0]
    assert (fila.status, fila.reason_code) == ("pending", "configuration_required")

    # Alguien fija la zona: la pasada siguiente lo manda sobre la misma fila.
    await _zona_de_la_compania(seeded, ZONA)
    r = await delivery.despachar_vencidos(ahora=_utc(17))
    assert r.accepted == 1, r.linea()
    assert len(await _filas("SELECT 1 FROM activity_email_delivery")) == 1
    await _admin(seeded, alpha_client)
    fila = (await alpha_client.get(HISTORIA)).json()["results"][0]
    assert fila["source"] == "schedule" and fila["delay_seconds"] == 3600, "salió una hora tarde y se ve"


async def test_fuera_de_la_ventana_queda_registrado_no_se_pierde_en_silencio(seeded, alpha_client, automatico, outbox):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    r = await delivery.despachar_vencidos(ahora=_utc(19))  # 3 h después del mediodía; ventana de 2 h
    assert r.expired == 1 and r.accepted == 0 and outbox.outbox == []
    fila = (await _filas("SELECT status, reason_code FROM activity_email_delivery"))[0]
    assert (fila.status, fila.reason_code) == ("skipped", "recovery_window_expired")
    await _admin(seeded, alpha_client, "route.activityemails.preview")
    h = (await alpha_client.get(HISTORIA)).json()["results"][0]
    assert "recovery window" in h["reason_message"]
    vista = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).json()
    assert vista["delivery"]["status"] == "skipped"
