"""Envío real de los correos de actividad (RTE-MAIL-CP4-01/02).

Un solo registro (`activity_email_delivery`) y un solo despacho para el botón
«Send now», el programador interno y el cron de DigitalOcean. Se comprueba:

* la ventana: mediodía con corte fijo a las 12:00 locales; antes, sólo vista
  parcial; fin de jornada a los 20 min del último cierre, y aplazado si se
  vuelve a abrir;
* sin actividad no hay motivacional; ninguna nota real sale;
* permisos separados (`preview`, `send`), alcance y otro tenant;
* todo apagado por defecto: sin `MAIL_REAL_SEND_TYPES` nada sale;
* idempotencia: doble clic, cron + manual, reintentos, resultado incierto,
  reserva caducada; el dry-run no escribe; la ventana de recuperación.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.core.email import backends
from app.routers_api.activityemails import delivery
from app.routers_api.activityemails.jobs import main as job_main
from tests.integration.test_activity_emails import _como, _conceder
from tests.integration.test_activity_explorer import _fechar_jornada, _jornada_con_parada
from tests.integration.test_org_hierarchy import _ejecutar, _filas, _organigrama

pytestmark = pytest.mark.integration

ZONA = "America/New_York"
DIA = date(2026, 10, 14)  # miércoles; EDT (UTC-4): las 12:00 locales son las 16:00 UTC
MEDIODIA_UTC = datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)
PREVIEW = "/api/activity-emails/reports/preview"
SEND = "/api/activity-emails/reports/send"
RESEND = "/api/activity-emails/reports/resend"
HISTORIAL = "/api/activity-emails/reports/deliveries"
MOT_MEDIODIA = "midday_motivation"
MOT_FIN = "end_of_day_recognition"
EST_MEDIODIA = "strategic_midday_report"
EST_FIN = "strategic_end_of_day_report"


def _utc(h: int, m: int = 0, dia: date = DIA) -> datetime:
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=timezone.utc)


async def _jornada_en(cliente, seeded, usuario: str, *, inicio: datetime, fin_actividad: datetime | None,
                      fin_jornada: datetime | None, notas: str | None = None) -> int:
    """Una jornada con una actividad, colocada en el tiempo del test."""
    hecho = await _jornada_con_parada(
        cliente, seeded, usuario=usuario, terminar=fin_actividad is not None, notas=notas,
        cerrar_jornada=fin_jornada is not None,
    )
    jornada = hecho["jornada"]["id"]
    await _fechar_jornada(jornada, DIA)
    await _ejecutar(
        "UPDATE work_session SET started_at = :s, ended_at = CASE WHEN ended_at IS NULL THEN NULL ELSE CAST(:e AS timestamptz) END, "
        "start_time_zone = :z WHERE id = :j",
        s=inicio, e=fin_jornada, z=ZONA, j=jornada,
    )
    await _ejecutar(
        "UPDATE trip SET started_at = :s, arrived_at = CASE WHEN arrived_at IS NULL THEN NULL ELSE CAST(:a AS timestamptz) END "
        "WHERE work_session_id = :j",
        s=inicio + timedelta(minutes=5), a=inicio + timedelta(minutes=30), j=jornada,
    )
    await _ejecutar(
        "UPDATE activity_execution SET started_at = :s, ended_at = CASE WHEN ended_at IS NULL THEN NULL ELSE CAST(:e AS timestamptz) END "
        "WHERE trip_id IN (SELECT id FROM trip WHERE work_session_id = :j)",
        s=inicio + timedelta(minutes=31), e=fin_actividad, j=jornada,
    )
    return jornada


async def _activar(seeded, usuario: str, campo: str) -> None:
    await _ejecutar(
        f"INSERT INTO activity_email_preference (company_id, user_id, {campo}) VALUES (:c, :u, true) "
        f"ON CONFLICT (company_id, user_id) DO UPDATE SET {campo} = true",
        c=seeded.alpha.id, u=seeded.alpha.users[usuario].id,
    )


async def _capacidades(seeded, rol: str, *nombres: str) -> None:
    for n in nombres:
        await _ejecutar(
            "INSERT INTO role_permission (role_id, permission_id, is_active, created_at, updated_at) "
            "SELECT :r, id, true, now(), now() FROM permission WHERE name = :n",
            r=seeded.alpha.roles[rol], n=n,
        )


async def _zona_de_la_compania(seeded, zona: str | None) -> None:
    await _ejecutar("UPDATE company SET operational_time_zone = :z WHERE id = :c", z=zona, c=seeded.alpha.id)


def _pedido(seeded, usuario: str, tipo: str, dia: date = DIA) -> dict:
    return {"report_type": tipo, "recipient_user_id": seeded.alpha.users[usuario].id, "operational_date": dia.isoformat()}


@pytest.fixture
def envio_real(monkeypatch):
    """Envío real habilitado para los cuatro tipos (sólo en el test)."""
    monkeypatch.setattr(settings, "MAIL_REAL_SEND_TYPES", f"{MOT_MEDIODIA},{MOT_FIN},{EST_MEDIODIA},{EST_FIN}")


@pytest.fixture
def automatico(monkeypatch, envio_real):
    monkeypatch.setattr(settings, "MAIL_AUTOMATION_ENABLED", True)
    monkeypatch.setattr(settings, "MAIL_AUTOMATION_DRY_RUN", False)
    monkeypatch.setattr(settings, "MAIL_RECOVERY_WINDOW_HOURS", 2)


async def _preparar_admin(seeded, cliente, *capacidades):
    await _capacidades(seeded, "route_admin", *capacidades)
    await _como(cliente, seeded, "route_admin")


# ── Permisos y contrato ─────────────────────────────────────────────────────


async def test_permisos_separados_y_alcance(seeded, alpha_client, outbox):
    await _como(alpha_client, seeded, "route_admin")
    assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).status_code == 403
    await _capacidades(seeded, "route_admin", "route.activityemails.preview")
    assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).status_code == 200
    assert (await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).status_code == 403, \
        "ver no autoriza a enviar"
    otro = {"report_type": MOT_MEDIODIA, "recipient_user_id": seeded.beta.users["supervisor"].id,
            "operational_date": DIA.isoformat()}
    assert (await alpha_client.post(PREVIEW, json=otro)).status_code == 404
    malo = {**_pedido(seeded, "supervisor", MOT_MEDIODIA), "email": "x@y.com"}
    assert (await alpha_client.post(PREVIEW, json=malo)).status_code == 422
    raro = _pedido(seeded, "supervisor", "weekly_digest")
    assert (await alpha_client.post(PREVIEW, json=raro)).status_code == 404
    assert outbox.outbox == []
    assert await _filas("SELECT 1 FROM activity_email_delivery") == []


async def test_un_coo_no_ve_fuera_de_su_rama(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _capacidades(seeded, "COO", "route.activityemails.preview")
    await _como(alpha_client, seeded, "coo")
    assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, "sales_a", MOT_MEDIODIA))).status_code == 404
    assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, "rm_b", EST_MEDIODIA))).status_code == 404
    # Su propio reporte, sí.
    assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, "coo", EST_MEDIODIA))).status_code == 200


async def test_generate_report_ofrece_el_propio_reporte_sin_tocar_la_configuracion(seeded, alpha_client):
    """La lista de «Generate report» incluye a quien la abre; la de configurar
    destinatarios, no (un mando no se activa sus propios correos)."""
    await _organigrama(alpha_client, seeded, perfiles=False)
    lista = "/api/activity-emails/strategic-recipients"
    for clave, rol in (("ceo", "CEO"), ("coo", "COO")):
        await _capacidades(seeded, rol, "route.activityemails.manage", "route.activityemails.preview")
        await _como(alpha_client, seeded, clave)
        yo = seeded.alpha.users[clave].id

        configurar = await alpha_client.get(lista, params={"page_size": 100})
        assert configurar.status_code == 200
        assert yo not in {f["user_id"] for f in configurar.json()["results"]}

        generar = await alpha_client.get(lista, params={"page_size": 100, "include_self": "true"})
        assert generar.status_code == 200
        ids = {f["user_id"] for f in generar.json()["results"]}
        assert yo in ids, f"{clave} no puede elegirse para su propio reporte"
        if clave == "coo":
            assert seeded.alpha.users["ceo"].id not in ids, "incluirse no amplía la rama"
            assert seeded.alpha.users["rm_b"].id not in ids
        assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, clave, EST_MEDIODIA))).status_code == 200
    assert (await alpha_client.post(PREVIEW, json=_pedido(seeded, "ceo", EST_MEDIODIA))).status_code == 404


# ── Ventanas y contenido real ───────────────────────────────────────────────


async def test_mediodia_con_corte_fijo_a_las_12(seeded, alpha_client):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _preparar_admin(seeded, alpha_client, "route.activityemails.preview")
    r = await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["time_zone"] == ZONA and v["provisional"] is False and v["eligible"] is True
    assert datetime.fromisoformat(v["cutoff_at"]) == MEDIODIA_UTC
    assert v["activity_count"] == 1
    assert v["subject"] == "¡Buen trabajo! Sigamos adelante 💪"
    assert "Hasta ahora has realizado:\n- 1 visita a cliente." in v["body"]
    for prohibido in ("Miles", "millas", "Notas", "ABC Manufacturing", "{{"):
        assert prohibido not in v["body"]
    assert v["can_send"] is False and v["blocked_reason"] == "real_send_disabled", "apagado por defecto"
    assert await _filas("SELECT 1 FROM activity_email_delivery") == [], "la vista previa no escribe"


async def test_actividad_despues_del_mediodia_no_cuenta(seeded, alpha_client):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(17), fin_jornada=_utc(21))
    ev = await delivery.evaluar(
        company_id=seeded.alpha.id, report_type=MOT_MEDIODIA,
        recipient_user_id=seeded.alpha.users["supervisor"].id, operational_date=DIA, ahora=_utc(22),
    )
    assert ev.reporte.eligible is False and ev.reporte.reason_code == "no_activity"


async def test_antes_del_mediodia_solo_vista_parcial(seeded, alpha_client, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(12), fin_actividad=_utc(13), fin_jornada=None)
    await _activar(seeded, "supervisor", "midday_enabled")
    ev = await delivery.evaluar(
        company_id=seeded.alpha.id, report_type=MOT_MEDIODIA,
        recipient_user_id=seeded.alpha.users["supervisor"].id, operational_date=DIA, ahora=_utc(14),
    )
    assert ev.reporte.provisional is True and ev.reporte.cutoff_at == _utc(14)
    assert ev.can_send is False and ev.blocked_reason == "partial_window"


async def test_fin_de_jornada_a_los_20_minutos_y_aplazado_si_reabre(seeded, alpha_client, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(20))
    await _activar(seeded, "supervisor", "end_of_day_enabled")
    uid = seeded.alpha.users["supervisor"].id

    async def ev(ahora):
        return await delivery.evaluar(company_id=seeded.alpha.id, report_type=MOT_FIN, recipient_user_id=uid,
                                      operational_date=DIA, ahora=ahora)

    a = await ev(_utc(20, 19))
    assert a.reporte.due_at == _utc(20, 20) and a.blocked_reason == "not_due_yet"
    b = await ev(_utc(20, 21))
    assert b.can_send is True
    assert "Tu día en resumen:" in b.reporte.body and "Tu semana hasta hoy:" in b.reporte.body

    # Vuelve a abrir una jornada el mismo día: deja de estar cerrado.
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(20, 10), fin_actividad=None, fin_jornada=None)
    c = await ev(_utc(20, 25))
    assert c.reporte.provisional is True and c.can_send is False


async def test_estrategicos_con_su_equipo_y_sin_notas(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(20),
                      notas="Nota confidencial del cliente")
    await _preparar_admin(seeded, alpha_client, "route.activityemails.preview")
    sin_zona = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "coo", EST_MEDIODIA))).json()
    assert sin_zona["reason_code"] == "configuration_required", "nunca la zona más frecuente del equipo"
    await _zona_de_la_compania(seeded, ZONA)
    m = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "coo", EST_MEDIODIA))).json()
    assert m["coverage"] == 4 and "Team Weekly Summary" not in m["body"]
    assert "SUP_A Org" in m["body"]
    f = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "coo", EST_FIN))).json()
    assert f["provisional"] is False
    assert datetime.fromisoformat(f["due_at"]) == _utc(23), "19:00 de Nueva York, no el cierre del equipo + 20"
    assert f["body"].count("Team Weekly Summary") == 1
    for texto in (m["body"], f["body"]):
        assert "Nota confidencial" not in texto
        assert "Detalle no incluido en el correo" in texto


# ── «Send now» ──────────────────────────────────────────────────────────────


async def test_send_now_apagado_por_defecto(seeded, alpha_client, outbox):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _preparar_admin(seeded, alpha_client, "route.activityemails.send")
    r = await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "real_send_disabled"
    assert outbox.outbox == []


async def test_send_now_envia_una_vez_y_queda_en_el_historial(seeded, alpha_client, outbox, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _preparar_admin(seeded, alpha_client, "route.activityemails.send", "route.activityemails.preview")
    pedido = {**_pedido(seeded, "supervisor", MOT_MEDIODIA), "reason": "El cron no corrió"}

    r = await alpha_client.post(SEND, json=pedido)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "recipient_not_enabled"
    await _activar(seeded, "supervisor", "midday_enabled")

    r = await alpha_client.post(SEND, json=pedido)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted_by_provider" and r.json()["source"] == "manual"
    assert r.json()["destination_masked"].startswith("s***r@")
    m = outbox.last_for(seeded.alpha.users["supervisor"].email)
    assert m.subject == "¡Buen trabajo! Sigamos adelante 💪" and "[TEST]" not in m.subject
    assert m.headers == {"X-CER-Route-Report": MOT_MEDIODIA}

    otra = await alpha_client.post(SEND, json=pedido)
    assert otra.status_code == 409 and otra.json()["detail"]["code"] == "already_sent"
    assert len(outbox.outbox) == 1

    h = (await alpha_client.get(HISTORIAL, params={"operational_date": DIA.isoformat()})).json()
    assert [(x["report_type"], x["status"]) for x in h] == [(MOT_MEDIODIA, "accepted_by_provider")]
    fila = (await _filas("SELECT request_reason, requested_by_user_id FROM activity_email_delivery"))[0]
    assert fila.request_reason == "El cron no corrió"
    evento = (await _filas(
        "SELECT action, changes FROM audit_event WHERE entity_type = 'activity_email_delivery'"))[0]
    assert evento.action == "accepted_by_provider" and "body" not in evento.changes


async def test_doble_clic_un_solo_correo(seeded, alpha_client, outbox, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _preparar_admin(seeded, alpha_client, "route.activityemails.send")
    r = await asyncio.gather(*(alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA)) for _ in range(3)))
    assert sorted(x.status_code for x in r) == [200, 409, 409]
    assert len(outbox.outbox) == 1
    assert len(await _filas("SELECT 1 FROM activity_email_delivery")) == 1


async def test_fallo_del_proveedor_y_reintento_sobre_el_mismo_registro(seeded, alpha_client, envio_real):
    class _Caido(backends.EmailBackend):
        name = "m365_oauth"

        def send(self, message):
            raise backends.EmailUnreachable("raw secret text", step="smtp_unreachable")

    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _preparar_admin(seeded, alpha_client, "route.activityemails.send")
    backends.set_email_backend(_Caido())
    try:
        r = await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    finally:
        backends.set_email_backend(None)
    assert r.status_code == 200 and r.json()["status"] == "retryable_failure"
    assert r.json()["reason_code"] == "smtp_unreachable" and "secret" not in r.text

    memoria = backends.MemoryEmailBackend()
    backends.set_email_backend(memoria)
    try:
        r = await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    finally:
        backends.set_email_backend(None)
    assert r.json()["status"] == "accepted_by_provider" and r.json()["attempt_count"] == 2
    assert len(await _filas("SELECT 1 FROM activity_email_delivery")) == 1


async def test_tiempo_agotado_es_incierto_y_no_se_reenvia(seeded, alpha_client, envio_real, outbox):
    class _Lento(backends.EmailBackend):
        name = "m365_oauth"

        def send(self, message):
            raise backends.EmailUnreachable("t", step="smtp_timeout")

    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _preparar_admin(seeded, alpha_client, "route.activityemails.send")
    backends.set_email_backend(_Lento())
    try:
        r = await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    finally:
        backends.set_email_backend(None)
    assert r.json()["status"] == "unknown_outcome"
    otra = await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    assert otra.status_code == 409 and otra.json()["detail"]["code"] == "needs_reconciliation"

    # Quien comprobó que no llegó puede reenviarlo a mano, con su permiso.
    backends.set_email_backend(outbox)
    await _capacidades(seeded, "route_admin", "route.activityemails.resend")
    r = await alpha_client.post(RESEND, json={**_pedido(seeded, "supervisor", MOT_MEDIODIA), "expected_resends": 0})
    assert r.status_code == 200 and r.json()["status"] == "accepted_by_provider"
    assert len(outbox.outbox) == 1


# ── «Resend» ────────────────────────────────────────────────────────────────


async def _enviado(seeded, cliente):
    """Un motivacional de mediodía ya aceptado por el proveedor."""
    await _jornada_en(cliente, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _preparar_admin(seeded, cliente, "route.activityemails.send", "route.activityemails.preview")
    r = await cliente.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    assert r.status_code == 200 and r.json()["status"] == "accepted_by_provider"


def _reenvio(seeded, vistos: int, **extra) -> dict:
    return {**_pedido(seeded, "supervisor", MOT_MEDIODIA), "expected_resends": vistos, **extra}


async def test_reenvio_solo_con_su_permiso_y_numerado(seeded, alpha_client, outbox, envio_real):
    await _enviado(seeded, alpha_client)
    assert (await alpha_client.post(RESEND, json=_reenvio(seeded, 0))).status_code == 403, "enviar no autoriza a reenviar"

    await _capacidades(seeded, "route_admin", "route.activityemails.resend")
    vista = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).json()
    assert vista["can_send"] is False and vista["blocked_reason"] == "already_sent"
    assert vista["can_resend"] is True and vista["resends"] == []

    r = await alpha_client.post(RESEND, json=_reenvio(seeded, 0, reason="No le llegó"))
    assert r.status_code == 200, r.text
    assert r.json()["sequence"] == 1 and r.json()["status"] == "accepted_by_provider"
    assert r.json()["destination_masked"].startswith("s***r@")
    assert len(outbox.outbox) == 2
    assert outbox.outbox[-1].headers == {"X-CER-Route-Report": MOT_MEDIODIA}

    # Quien no vio el primer reenvío no manda otro sin querer.
    otra = await alpha_client.post(RESEND, json=_reenvio(seeded, 0))
    assert otra.status_code == 409 and otra.json()["detail"]["code"] == "resend_conflict"
    # El interruptor de la persona no cuenta: sólo el permiso.
    await _ejecutar("UPDATE activity_email_preference SET midday_enabled = false")
    r = await alpha_client.post(RESEND, json=_reenvio(seeded, 1))
    assert r.status_code == 200 and r.json()["sequence"] == 2
    assert len(outbox.outbox) == 3

    vista = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).json()
    assert [x["sequence"] for x in vista["resends"]] == [1, 2]
    filas = await _filas("SELECT sequence, request_reason FROM activity_email_resend ORDER BY sequence")
    assert [(f.sequence, f.request_reason) for f in filas] == [(1, "No le llegó"), (2, None)]
    eventos = await _filas("SELECT action, changes FROM audit_event WHERE entity_type = 'activity_email_resend'")
    assert len(eventos) == 2 and all("body" not in e.changes for e in eventos)
    # La entrega original no cambia: sigue siendo una sola.
    assert len(await _filas("SELECT 1 FROM activity_email_delivery")) == 1


async def test_no_se_reenvia_lo_que_no_salio(seeded, alpha_client, outbox, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _preparar_admin(seeded, alpha_client, "route.activityemails.resend", "route.activityemails.preview")
    r = await alpha_client.post(RESEND, json=_reenvio(seeded, 0))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "resend_not_sent_yet"
    vista = (await alpha_client.post(PREVIEW, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))).json()
    assert vista["can_resend"] is False and vista["can_send"] is True
    assert outbox.outbox == []


async def test_reenvio_respeta_el_interruptor_por_tipo_y_otro_tenant(seeded, alpha_client, outbox, envio_real, monkeypatch):
    await _enviado(seeded, alpha_client)
    await _capacidades(seeded, "route_admin", "route.activityemails.resend")
    otro = {**_reenvio(seeded, 0), "recipient_user_id": seeded.beta.users["supervisor"].id}
    assert (await alpha_client.post(RESEND, json=otro)).status_code == 404
    monkeypatch.setattr(settings, "MAIL_REAL_SEND_TYPES", "")
    r = await alpha_client.post(RESEND, json=_reenvio(seeded, 0))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "real_send_disabled"
    assert len(outbox.outbox) == 1


async def test_doble_clic_un_solo_reenvio(seeded, alpha_client, outbox, envio_real):
    await _enviado(seeded, alpha_client)
    await _capacidades(seeded, "route_admin", "route.activityemails.resend")
    r = await asyncio.gather(*(alpha_client.post(RESEND, json=_reenvio(seeded, 0)) for _ in range(3)))
    assert sorted(x.status_code for x in r) == [200, 409, 409]
    assert len(outbox.outbox) == 2
    assert len(await _filas("SELECT 1 FROM activity_email_resend")) == 1


async def test_la_base_rechaza_un_reenvio_duplicado_o_sin_numero(seeded, alpha_client, outbox, envio_real):
    await _enviado(seeded, alpha_client)
    entrega = (await _filas("SELECT id, company_id FROM activity_email_delivery"))[0]
    sql = (
        "INSERT INTO activity_email_resend (company_id, delivery_id, sequence, status) "
        "VALUES (:c, :d, :n, 'accepted_by_provider')"
    )
    await _ejecutar(sql, c=entrega.company_id, d=entrega.id, n=1)
    with pytest.raises(IntegrityError):
        await _ejecutar(sql, c=entrega.company_id, d=entrega.id, n=1)
    with pytest.raises(IntegrityError):
        await _ejecutar(sql, c=entrega.company_id, d=entrega.id, n=0)
    with pytest.raises(IntegrityError):
        await _ejecutar(
            "INSERT INTO activity_email_resend (company_id, delivery_id, sequence, status) "
            "VALUES (:c, :d, 2, 'delivered')",
            c=entrega.company_id, d=entrega.id,
        )


# ── El barrido (programador interno y cron) ─────────────────────────────────


async def test_automatizacion_apagada_y_dry_run_no_escriben(seeded, alpha_client, outbox, envio_real, monkeypatch):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    apagado = await delivery.despachar_vencidos(ahora=MEDIODIA_UTC + timedelta(minutes=5))
    assert apagado.enabled is False and apagado.checked == 0

    monkeypatch.setattr(settings, "MAIL_AUTOMATION_ENABLED", True)
    ensayo = await delivery.despachar_vencidos(ahora=MEDIODIA_UTC + timedelta(minutes=5))
    assert ensayo.dry_run is True and ensayo.would_send == 1
    assert outbox.outbox == [] and await _filas("SELECT 1 FROM activity_email_delivery") == []


async def test_cron_y_boton_no_duplican(seeded, alpha_client, outbox, automatico):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _activar(seeded, "supervisor", "end_of_day_enabled")

    a = await delivery.despachar_vencidos(ahora=MEDIODIA_UTC + timedelta(minutes=3), source="reconcile")
    assert a.accepted == 1
    b = await delivery.despachar_vencidos(ahora=MEDIODIA_UTC + timedelta(minutes=4), source="schedule")
    assert b.accepted == 0, "el segundo reloj encuentra la entrega hecha"

    await _preparar_admin(seeded, alpha_client, "route.activityemails.send")
    r = await alpha_client.post(SEND, json=_pedido(seeded, "supervisor", MOT_MEDIODIA))
    assert r.json()["detail"]["code"] == "already_sent"

    # Fin de jornada: vence a las 21:20 y sale una vez.
    c = await delivery.despachar_vencidos(ahora=_utc(21, 21))
    assert c.accepted == 1
    assert sorted(m.subject for m in outbox.outbox) == sorted([
        "¡Buen trabajo! Sigamos adelante 💪", "¡Jornada finalizada! Este es tu avance de hoy 🌟",
    ])


async def test_sin_actividad_queda_omitido_con_su_motivo(seeded, alpha_client, outbox, automatico):
    jornada = await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15),
                                fin_jornada=_utc(21))
    # Un viaje a casa no es una actividad: el día queda sin actividades.
    await _ejecutar("UPDATE trip SET current_purpose = 'home' WHERE work_session_id = :j", j=jornada)
    await _activar(seeded, "supervisor", "end_of_day_enabled")
    r = await delivery.despachar_vencidos(ahora=_utc(21, 25))
    assert r.skipped == 1 and outbox.outbox == []
    fila = (await _filas("SELECT status, reason_code FROM activity_email_delivery"))[0]
    assert (fila.status, fila.reason_code) == ("skipped", "no_activity")


async def test_ventana_de_recuperacion_no_manda_correos_viejos(seeded, alpha_client, outbox, automatico):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    r = await delivery.despachar_vencidos(ahora=MEDIODIA_UTC + timedelta(hours=3))
    assert r.due == 0 and outbox.outbox == []


async def test_una_reserva_caducada_queda_como_incierta(seeded, alpha_client, outbox, automatico):
    uid = seeded.alpha.users["supervisor"].id
    await _ejecutar(
        "INSERT INTO activity_email_delivery (company_id, recipient_user_id, report_type, operational_date, "
        "status, source, attempt_count, lease_expires_at) VALUES (:c, :u, :t, :d, 'claimed', 'schedule', 1, :l)",
        c=seeded.alpha.id, u=uid, t=MOT_MEDIODIA, d=DIA, l=_utc(16, 1),
    )
    await delivery.despachar_vencidos(ahora=_utc(16, 30))
    fila = (await _filas("SELECT status, reason_code FROM activity_email_delivery"))[0]
    assert (fila.status, fila.reason_code) == ("unknown_outcome", "lease_expired")
    assert outbox.outbox == []


async def test_el_comando_del_cron_termina_bien(seeded):
    """Como lo ejecuta DigitalOcean: un proceso aparte, una pasada, código 0."""
    proceso = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.routers_api.activityemails.jobs", "--once",
        env={**os.environ, "MODE": "TEST"},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    salida, _ = await asyncio.wait_for(proceso.communicate(), timeout=120)
    assert proceso.returncode == 0, salida.decode(errors="replace")[-2000:]
    assert "MAIL DISPATCH | source=reconcile enabled=False" in salida.decode(errors="replace")


def test_el_comando_exige_once():
    with pytest.raises(SystemExit):
        job_main([])
