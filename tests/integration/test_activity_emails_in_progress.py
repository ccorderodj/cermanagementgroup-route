"""Actividades iniciadas y sin finalizar en los correos de mediodía y cierre.

* Finalizada: iniciada y terminada antes del corte. Cuenta y suma tiempo.
* En curso: iniciada antes del corte, sin terminar, con la jornada abierta.
* Sin cierre registrado: la jornada cerró sin terminar la actividad.
* Iniciada después del corte: no existe en ese reporte.

Las abiertas se cuentan **aparte** (`0 (+1)`), sin hora de fin ni duración.
"""

from __future__ import annotations

import pytest

from app.routers_api.activityemails import strategic
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
    envio_real,
)
from tests.integration.test_mail_close_cp1 import CIERRE_UTC, MEDIODIA_UTC, _ev
from tests.integration.test_org_hierarchy import _ejecutar, _organigrama

pytestmark = pytest.mark.integration


async def _reporte(seeded, corte, *, cierre: bool):
    reporte = await strategic.construir(
        company_id=seeded.alpha.id, manager_user_id=seeded.alpha.users["coo"].id, cierre=cierre,
        dia=DIA, corte=corte, inicio_semana=strategic.lunes_de(DIA),
    )
    return next(p for p in reporte.personas if p.user_id == seeded.alpha.users["sup_a"].id)


async def _sin_terminar(jornada: int) -> None:
    """La jornada cerró con la actividad abierta. End Work lo impide hoy
    (`has_unresolved_work`); el estado sólo llega con datos de antes de esa
    guarda, y el correo tiene que decirlo sin inventar un fin."""
    await _ejecutar(
        "UPDATE activity_execution SET status = 'in_progress', ended_at = NULL, terminal_action = NULL, "
        "outcome_standard_value_id = NULL "
        "WHERE trip_id IN (SELECT id FROM trip WHERE work_session_id = :j)",
        j=jornada,
    )


async def _preparar(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _zona_de_la_compania(seeded, ZONA)


# ── Estratégico ─────────────────────────────────────────────────────────────


async def test_1140_a_1215_en_curso_a_mediodia_y_finalizada_al_cierre(seeded, alpha_client, envio_real):
    await _preparar(seeded, alpha_client)
    # Actividad 11:40–12:15 locales (15:40–16:15 UTC).
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(15, 9), fin_actividad=_utc(16, 15),
                      fin_jornada=_utc(21))

    mediodia = await _reporte(seeded, MEDIODIA_UTC, cierre=False)
    total = strategic._total(mediodia.dia)
    assert (total.eventos, total.abiertas, total.segundos) == (0, 1, 0), "no cuenta como finalizada"
    (d,) = mediodia.detalles
    assert (d.estado, d.fin, d.duracion) == ("En curso", "", ""), "ni hora de fin ni duración inventadas"

    cuerpo = (await _ev(seeded, "coo", EST_MEDIODIA, _utc(22))).reporte.body
    assert "0 (+1)" in cuerpo and strategic.LEYENDA_ABIERTAS in cuerpo
    assert "Actividades finalizadas: 0 | Iniciadas sin finalizar: 1" in cuerpo

    cierre = await _reporte(seeded, CIERRE_UTC, cierre=True)
    total = strategic._total(cierre.dia)
    assert (total.eventos, total.abiertas, total.segundos) == (1, 0, 35 * 60)
    assert [x.estado for x in cierre.detalles] == ["Finalizada"], "una sola fila: sin duplicados"
    cuerpo = (await _ev(seeded, "coo", EST_FIN, CIERRE_UTC)).reporte.body
    assert "(+1)" not in cuerpo and strategic.LEYENDA_ABIERTAS not in cuerpo


async def test_iniciada_despues_del_corte_no_existe_aunque_se_genere_tarde(seeded, alpha_client, envio_real):
    await _preparar(seeded, alpha_client)
    # Viaje 11:45, actividad 12:11 locales: después del corte de mediodía.
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(15, 40), fin_actividad=_utc(17),
                      fin_jornada=_utc(21))

    mediodia = await _reporte(seeded, MEDIODIA_UTC, cierre=False)
    total = strategic._total(mediodia.dia)
    assert (total.eventos, total.abiertas) == (0, 0)
    assert mediodia.detalles == []


async def test_abierta_a_las_19_con_la_jornada_abierta_sale_en_curso(seeded, alpha_client, envio_real):
    await _preparar(seeded, alpha_client)
    # Actividad desde las 18:31 locales; ni la actividad ni la jornada cierran.
    await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(22), fin_actividad=None, fin_jornada=None)

    cierre = await _reporte(seeded, CIERRE_UTC, cierre=True)
    total = strategic._total(cierre.dia)
    assert (total.eventos, total.abiertas, total.segundos) == (0, 1, 0)
    assert [(d.estado, d.fin, d.duracion) for d in cierre.detalles] == [("En curso", "", "")]


async def test_jornada_cerrada_con_la_actividad_sin_terminar(seeded, alpha_client, envio_real):
    await _preparar(seeded, alpha_client)
    jornada = await _jornada_en(alpha_client, seeded, "sup_a", inicio=_utc(13), fin_actividad=_utc(15),
                                fin_jornada=_utc(20))
    await _sin_terminar(jornada)

    cierre = await _reporte(seeded, CIERRE_UTC, cierre=True)
    total = strategic._total(cierre.dia)
    assert (total.eventos, total.abiertas, total.segundos) == (0, 1, 0)
    assert [(d.estado, d.fin, d.duracion) for d in cierre.detalles] == [("Sin cierre registrado", "", "")], \
        "no se afirma que siga en ejecución"


# ── Motivacional ────────────────────────────────────────────────────────────


async def test_motivacional_cuenta_las_abiertas_aparte(seeded, alpha_client, envio_real):
    # 9:00–11:00 terminada; 11:40 abierta a las 12:00 y la jornada sigue.
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(14),
                      fin_jornada=_utc(15))
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(15, 9), fin_actividad=_utc(16, 15),
                      fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _activar(seeded, "supervisor", "end_of_day_enabled")

    cuerpo = (await _ev(seeded, "supervisor", MOT_MEDIODIA, _utc(22))).reporte.body
    assert "- 1 visita a cliente." in cuerpo, "sólo la finalizada"
    assert "- 1 actividad en curso." in cuerpo

    cuerpo = (await _ev(seeded, "supervisor", MOT_FIN, _utc(21, 20))).reporte.body
    assert "- 2 visitas a clientes." in cuerpo and "en curso" not in cuerpo


async def test_motivacional_jornada_cerrada_sin_terminar(seeded, alpha_client, envio_real):
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(14),
                      fin_jornada=_utc(14, 30))
    jornada = await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(14, 40),
                                fin_actividad=_utc(15, 30), fin_jornada=_utc(15, 45))
    await _sin_terminar(jornada)
    await _activar(seeded, "supervisor", "end_of_day_enabled")

    cuerpo = (await _ev(seeded, "supervisor", MOT_FIN, _utc(16, 5))).reporte.body
    assert "- 1 visita a cliente." in cuerpo
    assert "- 1 actividad iniciada sin finalizar." in cuerpo and "en curso" not in cuerpo


async def test_motivacional_decide_por_la_jornada_de_cada_actividad(seeded, alpha_client, envio_real):
    # Una abandonada en una jornada ya cerrada y otra en curso en la jornada
    # siguiente, que sigue abierta: cada una con su estado, no las dos «en curso».
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(12), fin_actividad=_utc(13),
                      fin_jornada=_utc(13, 10))
    cerrada = await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(13, 20),
                                fin_actividad=_utc(14), fin_jornada=_utc(14, 30))
    await _sin_terminar(cerrada)
    await _jornada_en(alpha_client, seeded, "supervisor", inicio=_utc(14, 40), fin_actividad=None,
                      fin_jornada=None)
    await _activar(seeded, "supervisor", "midday_enabled")

    cuerpo = (await _ev(seeded, "supervisor", MOT_MEDIODIA, _utc(22))).reporte.body
    assert "- 1 visita a cliente." in cuerpo
    assert "- 1 actividad en curso." in cuerpo
    assert "- 1 actividad iniciada sin finalizar." in cuerpo
