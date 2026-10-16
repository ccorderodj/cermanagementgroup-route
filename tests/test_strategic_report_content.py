"""Reportes estratégicos: plantillas, bloques obligatorios y render, sin base.

RTE-MAIL-UNIFIED-01 V1.2 (CP2): textos aprobados de V1.1; `per_person_report`
obligatorio en los dos; `team_weekly_summary` obligatorio sólo en el cierre,
una vez y **después** de las personas; el mediodía no lo admite; la
demostración tiene dos personas y el resumen del equipo cuadra con ellas.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.routers_api.activityemails import content, strategic

MEDIODIA = "strategic_midday_report"
CIERRE = "strategic_end_of_day_report"


def _errores(tipo: str, *, subject: str | None = None, body: str | None = None):
    s = content.spec(tipo)
    return content.validate(
        tipo,
        subject=s.default_subject if subject is None else subject,
        body=s.default_body if body is None else body,
    )


def test_textos_aprobados_v11():
    assert content.spec(MEDIODIA).default_subject == (
        "CER Route | Reporte operativo de mediodía — {{report_period_label}}"
    )
    assert content.spec(CIERRE).default_subject == (
        "CER Route | Resumen del día y acumulado semanal — {{report_period_label}}"
    )
    assert _errores(MEDIODIA) == [] and _errores(CIERRE) == []
    assert content.spec(MEDIODIA).group == content.spec(CIERRE).group == "strategic"
    assert content.spec("midday_motivation").group == "motivational"


@pytest.mark.parametrize("tipo", [MEDIODIA, CIERRE])
def test_el_reporte_por_persona_no_se_puede_quitar(tipo):
    body = content.spec(tipo).default_body.replace("{{per_person_report}}", "")
    assert any("per_person_report" in m for _, m in _errores(tipo, body=body))


def test_el_resumen_del_equipo_es_obligatorio_en_el_cierre_y_no_cabe_en_el_mediodia():
    sin = content.spec(CIERRE).default_body.replace("{{team_weekly_summary}}", "")
    assert any("team_weekly_summary" in m for _, m in _errores(CIERRE, body=sin))
    con = content.spec(MEDIODIA).default_body + "\n{{team_weekly_summary}}"
    assert any("Unsupported variable" in m for _, m in _errores(MEDIODIA, body=con))


def test_el_resumen_va_despues_y_una_sola_vez():
    al_reves = "{{team_weekly_summary}}\n{{per_person_report}}"
    assert any("must come after" in m for _, m in _errores(CIERRE, body=al_reves))
    doble = "{{per_person_report}}\n{{team_weekly_summary}}\n{{team_weekly_summary}}"
    assert any("only once" in m for _, m in _errores(CIERRE, body=doble))


def test_variables_del_asunto_por_grupo():
    assert _errores(MEDIODIA, subject="Hola {{manager_first_name}} {{report_period_label}}") == []
    assert any("Unsupported" in m for _, m in _errores(MEDIODIA, subject="{{user_first_name}}"))
    assert any("Unsupported" in m for _, m in _errores("midday_motivation", subject="{{report_period_label}}"))


def test_demo_de_mediodia_dos_personas_sin_resumen_semanal():
    v = content.sample_values(MEDIODIA)
    texto = content.render(content.spec(MEDIODIA).default_body, v)
    assert "■ Ana Ejemplo · Supervisor" in texto and "■ Luis Muestra · OSM" in texto
    assert "Team Weekly Summary" not in texto and "Weekly Activity Summary" not in texto
    assert "En curso" in texto, "lo que sigue abierto se dice"
    assert "No disponible" in texto, "sin coste no se inventa un cero"
    assert "{{" not in texto


def test_demo_de_cierre_resumen_al_final_una_vez():
    texto = content.render(content.spec(CIERRE).default_body, content.sample_values(CIERRE))
    assert texto.count("Team Weekly Summary") == 1
    assert texto.index("Team Weekly Summary") > texto.rindex("Weekly Activity Summary")
    assert texto.index("Team Weekly Summary") < texto.index("Los datos corresponden")
    assert "Personas con actividad registrada en la semana: 2" in texto


def test_el_resumen_del_equipo_cuadra_con_las_personas():
    reporte = strategic._demo(cierre=True)
    personas, filas = strategic.resumen_del_equipo(reporte)
    assert personas == 2
    total = strategic._total(filas)
    individuales = [strategic._total(p.semana) for p in reporte.personas]
    assert total.eventos == sum(t.eventos for t in individuales)
    assert total.millas == sum((t.millas for t in individuales), Decimal("0"))
    assert total.segundos == sum(t.segundos for t in individuales)
    # Una persona sin coste: el total es parcial, no un cero inventado.
    assert total.parcial is True and total.coste == Decimal("39.40")


def test_ninguna_nota_real_sale_por_correo():
    assert strategic.nota_para_correo("El cliente X debe 4.000 USD") == "Detalle no incluido en el correo"
    assert strategic.nota_para_correo("   ") == "Sin notas registradas"
    assert strategic.nota_para_correo(None) == "Sin notas registradas"


def test_sin_personas_o_sin_actividad():
    vacio = strategic.Reporte(cierre=True, dia=strategic._DEMO_DIA, inicio_semana=strategic._DEMO_LUNES, personas=[])
    assert strategic.render_personas(vacio) == "Sin personas autorizadas para el reporte"
    assert "Sin personas autorizadas" in strategic.render_equipo(vacio)
    sola = strategic.Persona(user_id=1, nombre="X", cargo="Supervisor")
    con_una = strategic.Reporte(
        cierre=True, dia=strategic._DEMO_DIA, inicio_semana=strategic._DEMO_LUNES, personas=[sola]
    )
    assert "Sin actividades registradas para el período" in strategic.render_personas(con_una)
    assert "Sin actividades registradas para el período" in strategic.render_equipo(con_una)


def test_un_valor_con_llaves_no_se_evalua():
    v = dict(content.sample_values(MEDIODIA), manager_first_name="{{per_person_report}}")
    texto = content.render("Hola {{manager_first_name}}", v)
    assert texto == "Hola {{per_person_report}}"
