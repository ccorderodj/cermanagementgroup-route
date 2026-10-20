"""Reportes estratégicos para mandos (RTE-MAIL-UNIFIED-01 V1.2, CP2).

Organigrama de `test_org_hierarchy`: CEO → COO → RM-A → (OSM-A, SUP-A);
CEO → RM-B → SUP-B; COO → SUP-C; CEO → Sales-A.

* Las cuatro plantillas: las estratégicas se editan, previsualizan y
  restauran sin tocar las motivacionales, y al revés.
* Destinatarios estratégicos: sólo mandos, apagados, independientes de los
  motivacionales, con la cobertura real (CEO incluye Sales; COO no) y el alcance
  de quien administra (un COO sólo gestiona a su RM).
* El generador con datos reales: CEO ve a Sales y el COO no; el mando no sale
  en su propio reporte; ninguna nota real sale; el resumen del equipo cuadra
  con las personas y no cuenta dos veces.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.routers_api.activityemails import content, strategic
from tests.integration.test_activity_emails import _como, _conceder, _eventos, _plantillas
from tests.integration.test_org_hierarchy import _ejecutar, _filas, _organigrama, _persona
from tests.integration.test_reports import MIERCOLES, _jornada

pytestmark = pytest.mark.integration

PLANTILLAS = "/api/activity-emails/templates"
MANDOS = "/api/activity-emails/strategic-recipients"
MEDIODIA = "strategic_midday_report"
CIERRE = "strategic_end_of_day_report"


async def _mandos(cliente, **params) -> dict[int, dict]:
    r = await cliente.get(MANDOS, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return {f["user_id"]: f for f in r.json()["results"]}


# ── Plantillas ──────────────────────────────────────────────────────────────


async def test_cuatro_plantillas_y_las_estrategicas_aisladas(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    t = await _plantillas(alpha_client)
    assert t[MEDIODIA]["group"] == t[CIERRE]["group"] == "strategic"
    assert t[CIERRE]["subject"] == content.spec(CIERRE).default_subject
    assert {x["token"] for x in t[CIERRE]["tokens"] if x["required"]} == {"per_person_report", "team_weekly_summary"}
    assert t[MEDIODIA]["subject_tokens"] == ["manager_first_name", "report_period_label"]

    body = content.spec(CIERRE).default_body.replace("Hola,", "Buenas,")
    r = await alpha_client.put(f"{PLANTILLAS}/{CIERRE}", json={"subject": "Cierre {{report_period_label}}", "body": body, "version": 0})
    assert r.status_code == 200, r.text
    t = await _plantillas(alpha_client)
    assert t[CIERRE]["is_default"] is False
    for otra in ("midday_motivation", "end_of_day_recognition", MEDIODIA):
        assert t[otra]["is_default"] is True, otra

    r = await alpha_client.post(f"{PLANTILLAS}/{CIERRE}/restore-default", json={"version": 1})
    assert r.status_code == 200 and r.json()["is_default"] is True
    assert [e.action for e in await _eventos("activity_email_template")] == ["update", "restore_default"]


async def test_no_se_puede_quitar_ni_mover_el_resumen(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    for body in (
        "Hola\n{{per_person_report}}",
        "{{team_weekly_summary}}\n{{per_person_report}}",
        "Hola\n{{team_weekly_summary}}",
    ):
        r = await alpha_client.put(f"{PLANTILLAS}/{CIERRE}", json={"subject": "x", "body": body, "version": 0})
        assert r.status_code == 422, body
    r = await alpha_client.put(
        f"{PLANTILLAS}/{MEDIODIA}",
        json={"subject": "x", "body": "{{per_person_report}}\n{{team_weekly_summary}}", "version": 0},
    )
    assert r.status_code == 422


async def test_vista_previa_ficticia(seeded, alpha_client):
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    for tipo, con_equipo in ((MEDIODIA, False), (CIERRE, True)):
        s = content.spec(tipo)
        r = await alpha_client.post(f"{PLANTILLAS}/{tipo}/preview", json={"subject": s.default_subject, "body": s.default_body})
        assert r.status_code == 200, r.text
        cuerpo = r.json()["body"]
        assert r.json()["sample_label"] == "Ejemplo / Vista previa"
        assert "Ana Ejemplo" in cuerpo and "Luis Muestra" in cuerpo
        assert ("Team Weekly Summary" in cuerpo) is con_equipo
        assert r.json()["subject"].endswith("14/10/2026")
    assert await _filas("SELECT 1 FROM activity_email_template") == []


# ── Destinatarios estratégicos ──────────────────────────────────────────────


async def test_mandos_apagados_con_su_cobertura_real(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    u = seeded.alpha.users
    filas = await _mandos(alpha_client)
    # Mandos y administradores: hoy el CEO lo representa un administrador.
    assert set(filas) == {u["ceo"].id, u["coo"].id, u["rm_a"].id, u["rm_b"].id, u["owner"].id, u["admin"].id}
    assert u["sales_a"].id not in filas and u["sup_a"].id not in filas, "sólo mandos y administradores"
    assert filas[u["ceo"].id]["coverage"] == 8, "todo el organigrama, Sales incluido"
    assert filas[u["admin"].id]["coverage"] == 9, "un administrador: toda la jerarquía vigente, CEO incluido"
    assert filas[u["coo"].id]["coverage"] == 4, "RM-A, OSM-A, SUP-A, SUP-C; sin Sales"
    assert filas[u["rm_a"].id]["coverage"] == 2
    assert all(not f["strategic_midday_enabled"] and not f["strategic_end_of_day_enabled"] for f in filas.values())
    assert not set(filas) & {x.id for x in seeded.beta.users.values()}


async def test_interruptores_estrategicos_independientes(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    coo = seeded.alpha.users["coo"].id
    r = await alpha_client.put(f"{MANDOS}/{coo}", json={"strategic_end_of_day_enabled": True, "version": 0})
    assert r.status_code == 200, r.text
    assert r.json()["strategic_end_of_day_enabled"] is True and r.json()["strategic_midday_enabled"] is False
    pref = (await _filas(
        "SELECT midday_enabled, end_of_day_enabled, strategic_midday_enabled, strategic_end_of_day_enabled "
        "FROM activity_email_preference WHERE user_id = :u", u=coo,
    ))[0]
    assert (pref.midday_enabled, pref.end_of_day_enabled, pref.strategic_midday_enabled) == (False, False, False)
    assert pref.strategic_end_of_day_enabled is True
    evento = (await _eventos("activity_email_preference"))[-1]
    assert evento.changes == {"strategic_end_of_day_enabled": {"old": False, "new": True}}
    assert (await alpha_client.put(f"{MANDOS}/{coo}", json={"strategic_midday_enabled": True, "version": 0})).status_code == 409
    assert (await alpha_client.put(f"{MANDOS}/{coo}", json={"version": 1})).status_code == 400
    assert (await alpha_client.put(f"{MANDOS}/{coo}", json={"midday_enabled": True, "version": 1})).status_code == 422


async def test_quien_no_es_mando_o_no_tiene_equipo(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _persona(alpha_client, seeded, "rm_c", "Regional Manager", "coo")
    await _conceder(seeded, "route_admin")
    await _como(alpha_client, seeded, "route_admin")
    u = seeded.alpha.users
    filas = await _mandos(alpha_client)
    assert filas[u["rm_c"].id]["ineligible_reason"] == "no_team"
    r = await alpha_client.put(f"{MANDOS}/{u['rm_c'].id}", json={"strategic_midday_enabled": True, "version": 0})
    assert r.status_code == 409
    for no_mando in (u["sup_a"].id, u["sales_a"].id, seeded.beta.users["ceo_base"].id, 999999):
        r = await alpha_client.put(f"{MANDOS}/{no_mando}", json={"strategic_midday_enabled": True, "version": 0})
        assert r.status_code == 404, no_mando


async def test_un_coo_que_administra_solo_ve_a_su_rama(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _conceder(seeded, "COO")
    await _como(alpha_client, seeded, "coo")
    u = seeded.alpha.users
    filas = await _mandos(alpha_client)
    assert set(filas) == {u["rm_a"].id}, "ni el CEO, ni RM-B, ni él mismo"
    r = await alpha_client.put(f"{MANDOS}/{u['rm_b'].id}", json={"strategic_midday_enabled": True, "version": 0})
    assert r.status_code == 404


async def test_sin_la_capacidad_403(seeded, alpha_client):
    await _como(alpha_client, seeded, "route_admin")
    assert (await alpha_client.get(MANDOS)).status_code == 403
    r = await alpha_client.put(f"{MANDOS}/{seeded.alpha.users['ceo_base'].id}", json={"strategic_midday_enabled": True, "version": 0})
    assert r.status_code == 403


# ── El generador con datos reales ───────────────────────────────────────────


async def _reporte(seeded, mando: str, *, cierre: bool = True) -> strategic.Reporte:
    return await strategic.construir(
        company_id=seeded.alpha.id,
        manager_user_id=seeded.alpha.users[mando].id,
        cierre=cierre,
        dia=MIERCOLES,
        corte=datetime(2030, 1, 1, tzinfo=timezone.utc),
        inicio_semana=strategic.lunes_de(MIERCOLES),
    )


async def test_alcance_del_reporte_y_notas_retenidas(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    for usuario, millas in (("sup_a", "12.0"), ("sales_a", "8.0"), ("sup_b", "5.0")):
        await _jornada(alpha_client, seeded, usuario=usuario, millas=millas)
    await _ejecutar("UPDATE activity_execution SET notes = 'Nota confidencial del cliente'")

    u = seeded.alpha.users
    ceo = await _reporte(seeded, "ceo")
    ids = {p.user_id for p in ceo.personas}
    assert u["sales_a"].id in ids and u["ceo"].id not in ids, "CEO ve Sales; no se incluye a sí mismo"
    assert len(ids) == len(ceo.personas), "nadie dos veces"

    coo = await _reporte(seeded, "coo")
    ids_coo = {p.user_id for p in coo.personas}
    assert u["sales_a"].id not in ids_coo and u["sup_b"].id not in ids_coo and u["coo"].id not in ids_coo
    assert u["sup_a"].id in ids_coo

    rm = await _reporte(seeded, "rm_a")
    assert {p.user_id for p in rm.personas} == {u["osm_a"].id, u["sup_a"].id}

    texto = strategic.render_personas(ceo) + strategic.render_equipo(ceo)
    assert "Nota confidencial" not in texto
    assert "Detalle no incluido en el correo" in texto


async def test_resumen_del_equipo_cuadra_con_los_datos_reales(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    for usuario, millas in (("sup_a", "12.0"), ("sup_c", "7.5"), ("osm_a", "3.0")):
        await _jornada(alpha_client, seeded, usuario=usuario, millas=millas)
    coo = await _reporte(seeded, "coo")
    personas, filas = strategic.resumen_del_equipo(coo)
    total = strategic._total(filas)
    individuales = [strategic._total(p.semana) for p in coo.personas if p.semana]
    assert personas == 3
    assert total.eventos == sum(t.eventos for t in individuales) == 3
    assert total.millas == sum(t.millas for t in individuales)
    assert str(total.millas) == "22.5"

    mediodia = await _reporte(seeded, "coo", cierre=False)
    assert all(p.semana == [] for p in mediodia.personas)
    valores = strategic.valores(mediodia, manager_first_name="Coo", generado="x")
    assert "team_weekly_summary" not in valores
