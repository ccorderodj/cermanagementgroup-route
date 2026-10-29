"""RTE-MAIL-CLOSE-01 · CP1: corte, roster y horarios.

* T1/T3: lo que se ve a las 12:00 es lo que se sabía a las 12:00 (una
  actividad 11:30–13:26 sigue «En curso», sin duración).
* T2: End Work + 20 min exactos; dos sesiones; jornada que cruza medianoche.
* T4: 19:00 locales fijas; ni antes aunque el equipo cierre, ni después aunque
  queden jornadas abiertas.
* Roster: personas activas del alcance, con o sin jornada; nunca «Ausente».
* Alcance: un administrador (hoy, el CEO) ve Sales; el COO no.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routers_api.activityemails import delivery, strategic
from tests.integration.test_activity_email_delivery import (  # noqa: F401 — fixtures
    DIA,
    EST_FIN,
    EST_MEDIODIA,
    MOT_FIN,
    MOT_MEDIODIA,
    ZONA,
    _activar,
    _jornada_en,
    _utc,
    _zona_de_la_compania,
    automatico,
    envio_real,
)
from tests.integration.test_org_hierarchy import _ejecutar, _organigrama

pytestmark = pytest.mark.integration

# Miércoles 14-10-2026 en Nueva York (EDT, UTC-4): 12:00 = 16:00 UTC; 19:00 = 23:00 UTC.
MEDIODIA_UTC = _utc(16)
CIERRE_UTC = _utc(23)


async def _ev(seeded, usuario: str, tipo: str, ahora: datetime, dia=DIA):
    return await delivery.evaluar(
        company_id=seeded.alpha.id, report_type=tipo, recipient_user_id=seeded.alpha.users[usuario].id,
        operational_date=dia, ahora=ahora,
    )


# ── El corte de mediodía ────────────────────────────────────────────────────


def test_al_corte_recorta_una_copia_sin_tocar_el_original():
    corte = MEDIODIA_UTC
    base = dict(
        trip_started_at=_utc(15, 5), arrived_at=_utc(15, 30), metros=8000, mileage_state="calculated",
        pendiente=False, execution_id=1, activity_started_at=_utc(15, 31), session_ended=True, session_id=7,
    )
    abierta = {**base, "activity_ended_at": _utc(17, 26, ), "segundos": 6900}
    terminada = {**base, "execution_id": 2, "activity_started_at": _utc(14, 4, ),
                 "activity_ended_at": _utc(15, 15) + timedelta(seconds=50), "segundos": 4250}
    sin_llegar = {**base, "execution_id": None, "trip_started_at": _utc(15, 50), "arrived_at": _utc(16, 20),
                  "activity_started_at": None, "activity_ended_at": None, "segundos": 0}
    despues = {**base, "trip_started_at": _utc(16, 5), "activity_ended_at": None, "segundos": 0}

    # La jornada cerró a las 21:00 UTC: a las 12:00 seguía abierta.
    filas = strategic._al_corte([abierta, terminada, sin_llegar, despues], corte, {7: _utc(21)})

    assert len(filas) == 3, "lo que empezó después del corte no existe"
    a, t, s = filas
    assert a["activity_ended_at"] is None and a["segundos"] == 0 and a["session_ended"] is False
    assert t["segundos"] == 71 * 60, "minutos de reloj: 10:04–11:15 = 1h 11m"
    assert s["metros"] == 0 and s["mileage_state"] is None and s["pendiente"] is True
    assert abierta["activity_ended_at"] == _utc(17, 26) and abierta["segundos"] == 6900, "el original no cambia"
    assert strategic._detalle({**a, "time_zone": ZONA, "utc_offset_minutes": None, "notes": None,
                               "purpose": "office", "session_date": DIA}).estado == "En curso"

    # Si la jornada ya había cerrado antes del corte, no se afirma que siga en ejecución.
    (cerrada, *_) = strategic._al_corte([{**base, "activity_ended_at": None, "segundos": 0}], corte,
                                        {7: _utc(15, 45)})
    assert cerrada["session_ended"] is True
    assert strategic._detalle({**cerrada, "time_zone": ZONA, "utc_offset_minutes": None, "notes": None,
                               "purpose": "office", "session_date": DIA}).estado == "Sin cierre registrado"


async def test_actividad_que_cruza_el_mediodia_no_sale_finalizada(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)
    # 11:30–13:26 locales (15:31–17:26 UTC): a las 12:00 sigue abierta.
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(15), fin_actividad=_utc(17, 26),
                      fin_jornada=_utc(21))
    await _activar(seeded, "sup_a", "midday_enabled")

    t1 = await _ev(seeded, "sup_a", MOT_MEDIODIA, _utc(22))
    assert t1.reporte.reason_code == "no_activity", "T1 no cuenta lo que terminó después de las 12:00"

    t3 = await _ev(seeded, "coo", EST_MEDIODIA, _utc(22))
    cuerpo = t3.reporte.body
    assert "En curso" in cuerpo and "Finalizada" not in cuerpo.split("SUP_A Org")[1].split("■")[0]
    assert "1h 55m" not in cuerpo and "1h 56m" not in cuerpo, "ninguna duración posterior al corte"
    assert "Jornada: Inicio 11:00 AM · En curso" in cuerpo
    assert t3.reporte.cutoff_at == MEDIODIA_UTC


# ── T2: End Work + 20 ───────────────────────────────────────────────────────


async def test_t2_a_los_20_minutos_con_dos_sesiones(seeded, alpha_client, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(17))
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(18), fin_actividad=_utc(19), fin_jornada=_utc(20))
    await _activar(seeded, "supervisor", "end_of_day_enabled")

    a = await _ev(seeded, "supervisor", MOT_FIN, _utc(20, 19))
    assert a.reporte.due_at == _utc(20, 20), "20 min tras el cierre de la **última** sesión"
    assert a.can_send is False and a.blocked_reason == "not_due_yet"
    b = await _ev(seeded, "supervisor", MOT_FIN, _utc(20, 20))
    assert b.can_send is True
    assert "- 2 visitas a clientes." in b.reporte.body


async def test_t2_de_una_jornada_que_cruza_la_medianoche(seeded, alpha_client, automatico, outbox):
    # 23:00–00:30 locales: la jornada es del día 14 aunque termine el 15.
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(3, dia=DIA + timedelta(days=1)),
                      fin_actividad=_utc(4, dia=DIA + timedelta(days=1)),
                      fin_jornada=_utc(4, 30, dia=DIA + timedelta(days=1)))
    await _activar(seeded, "supervisor", "end_of_day_enabled")
    vence = _utc(4, 50, dia=DIA + timedelta(days=1))

    assert (await _ev(seeded, "supervisor", MOT_FIN, vence)).reporte.due_at == vence
    antes = await delivery.despachar_vencidos(ahora=vence - timedelta(minutes=1))
    assert antes.accepted == 0
    resumen = await delivery.despachar_vencidos(ahora=vence)
    assert resumen.accepted == 1, resumen.linea()
    assert len(outbox.outbox) == 1


# ── T4: 19:00 fijas ─────────────────────────────────────────────────────────


async def test_t4_no_se_adelanta_aunque_el_equipo_haya_cerrado(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(20))
    await _activar(seeded, "coo", "strategic_end_of_day_enabled")

    a = await _ev(seeded, "coo", EST_FIN, CIERRE_UTC - timedelta(minutes=1))
    assert a.reporte.due_at == CIERRE_UTC and a.reporte.provisional is True
    assert a.can_send is False
    b = await _ev(seeded, "coo", EST_FIN, CIERRE_UTC)
    assert b.can_send is True, b.blocked_reason
    assert b.reporte.cutoff_at == CIERRE_UTC


async def test_t4_sale_a_las_19_con_jornadas_abiertas_y_sin_inicio(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(20))
    # SUP-C sigue trabajando a las 19:00 y cierra a las 19:30 (23:30 UTC).
    await _jornada_en(alpha_client, seeded, "sup_c", inicio=_utc(14), fin_actividad=_utc(16),
                      fin_jornada=_utc(23, 30))
    await _activar(seeded, "coo", "strategic_end_of_day_enabled")

    ev = await _ev(seeded, "coo", EST_FIN, _utc(23, 45))
    assert ev.can_send is True, ev.blocked_reason
    cuerpo = ev.reporte.body
    bloques = {b.split("\n")[0]: b for b in cuerpo.split("■ ")[1:]}
    sup_a = next(b for t, b in bloques.items() if t.startswith("SUP_A Org"))
    sup_c = next(b for t, b in bloques.items() if t.startswith("SUP_C Org"))
    osm_a = next(b for t, b in bloques.items() if t.startswith("OSM_A Org"))
    assert "Jornada: Inicio 9:00 AM · Fin 4:00 PM · Finalizada · Jornada registrada 7h 00m" in sup_a
    assert "Jornada: Inicio 10:00 AM · En curso · Jornada registrada al corte 9h 00m" in sup_c, \
        "foto de las 19:00: el cierre de las 19:30 no se conoce todavía"
    assert "Jornada: Sin registro de inicio al corte" in osm_a
    assert "Ausente" not in cuerpo and "Absent" not in cuerpo
    assert cuerpo.count("Team Weekly Summary") == 1
    assert cuerpo.index("Executive Snapshot") < cuerpo.index("■ ") < cuerpo.index("Team Weekly Summary")
    assert "Personas en el reporte: 4 | Sin registro de inicio: 2 | En curso: 1 | Finalizadas: 1" in cuerpo


async def test_t4_sin_zona_pide_configuracion(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    ev = await _ev(seeded, "coo", EST_FIN, CIERRE_UTC)
    assert ev.reporte.reason_code == "configuration_required" and ev.can_send is False


# ── Roster y alcance ────────────────────────────────────────────────────────


async def test_admin_representa_al_ceo_y_ve_sales_el_coo_no(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)
    u = seeded.alpha.users

    _, admin = await strategic.roster(seeded.alpha.id, u["admin"].id)
    _, coo = await strategic.roster(seeded.alpha.id, u["coo"].id)
    ids_admin = {p[0] for p in admin}
    ids_coo = {p[0] for p in coo}
    assert u["sales_a"].id in ids_admin and u["ceo"].id in ids_admin and u["admin"].id not in ids_admin
    assert u["sales_a"].id not in ids_coo
    assert not ids_admin & {x.id for x in seeded.beta.users.values()}, "sólo el tenant explícito"

    # Una persona suspendida en la compañía sale del roster.
    await _ejecutar("UPDATE user_company SET is_active = false WHERE user_id = :u AND company_id = :c",
                    u=u["sup_c"].id, c=seeded.alpha.id)
    _, coo = await strategic.roster(seeded.alpha.id, u["coo"].id)
    assert u["sup_c"].id not in {p[0] for p in coo}

    ev = await _ev(seeded, "admin", EST_FIN, CIERRE_UTC)
    assert "SALES_A Org" in ev.reporte.body


async def test_los_totales_cuadran_en_minutos_de_reloj(seeded, alpha_client, envio_real):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)
    # Segundos sueltos: 9:31:00–10:04:40 (33 min de reloj, 33.7 reales).
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(13),
                      fin_actividad=_utc(14, 4) + timedelta(seconds=40), fin_jornada=_utc(20))
    reporte = await strategic.construir(
        company_id=seeded.alpha.id, manager_user_id=seeded.alpha.users["coo"].id, cierre=True,
        dia=DIA, corte=CIERRE_UTC, inicio_semana=strategic.lunes_de(DIA),
    )
    sup_a = next(p for p in reporte.personas if p.user_id == seeded.alpha.users["sup_a"].id)
    assert [d.duracion for d in sup_a.detalles] == ["33m"]
    assert strategic._total(sup_a.dia).segundos == 33 * 60
    _, filas = strategic.resumen_del_equipo(reporte)
    assert strategic._total(filas).segundos == sum(strategic._total(p.semana).segundos for p in reporte.personas)


async def test_zona_operativa_de_la_compania_en_el_perfil(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    perfil = (await alpha_client.get("/api/companies/profile")).json()
    assert perfil["operational_time_zone"] is None
    cuerpo = {"name": perfil["name"], "operational_time_zone": "America/Chicago"}
    r = await alpha_client.put("/api/companies/profile", json=cuerpo)
    assert r.status_code == 200 and r.json()["operational_time_zone"] == "America/Chicago"
    malo = await alpha_client.put("/api/companies/profile", json={**cuerpo, "operational_time_zone": "Mars/Base"})
    assert malo.status_code == 422
    vacio = await alpha_client.put("/api/companies/profile", json={**cuerpo, "operational_time_zone": ""})
    assert vacio.json()["operational_time_zone"] is None


async def test_el_perfil_sigue_sin_aceptar_dominio_ni_subdominio(seeded, alpha_client):
    """D5: el formulario ya no los envía; el servidor los sigue rechazando."""
    await alpha_client.login(seeded.alpha.users["owner"].email)
    perfil = (await alpha_client.get("/api/companies/profile")).json()
    r = await alpha_client.put("/api/companies/profile", json={"name": perfil["name"], "subdomain": "otro"})
    assert r.status_code == 422
