"""Plantillas de los correos de actividad: validación y vista previa, sin base.

RTE-NOT-01 §5 y BR-06/BR-07: sólo las variables de la lista, los bloques de
actividad obligatorios, texto plano sin HTML ni enlaces, asunto de una línea y
una vista previa que sólo sustituye marcadores con datos ficticios.
"""

from __future__ import annotations

import pytest

from app.core.rbac.catalog import CAPABILITY_NAMES, CAPACIDADES_A_DEMANDA, DEFAULT_ROLES, capabilities_for
from app.routers_api.activityemails import content
from app.routers_api.activityemails.content import ActivityEmailType

MEDIODIA = ActivityEmailType.MIDDAY_MOTIVATION.value
FIN = ActivityEmailType.END_OF_DAY_RECOGNITION.value


def _errores(tipo: str, *, subject: str | None = None, body: str | None = None) -> list[tuple[str, str]]:
    s = content.spec(tipo)
    return content.validate(
        tipo,
        subject=s.default_subject if subject is None else subject,
        body=s.default_body if body is None else body,
    )


def test_los_textos_aprobados_son_validos_y_literales():
    assert _errores(MEDIODIA) == []
    assert _errores(FIN) == []
    assert content.spec(MEDIODIA).default_subject == "¡Buen trabajo! Sigamos adelante 💪"
    assert content.spec(FIN).default_subject == "¡Jornada finalizada! Este es tu avance de hoy 🌟"
    assert "{{midday_activity_block}}" in content.spec(MEDIODIA).default_body
    assert "{{day_activity_block}}" in content.spec(FIN).default_body
    assert "{{week_activity_block}}" in content.spec(FIN).default_body


def test_solo_dos_tipos():
    assert set(ActivityEmailType.values()) == {"midday_motivation", "end_of_day_recognition"}


@pytest.mark.parametrize(
    ("tipo", "body", "fragmento"),
    [
        (MEDIODIA, "Hola {{user_first_name}}", "midday_activity_block"),
        (FIN, "Hola {{day_activity_block}}", "week_activity_block"),
        (FIN, "Hola {{week_activity_block}}", "day_activity_block"),
    ],
)
def test_no_se_puede_quitar_el_bloque_de_actividad(tipo, body, fragmento):
    errores = _errores(tipo, body=body)
    assert any(campo == "body" and fragmento in msg for campo, msg in errores), errores


@pytest.mark.parametrize(
    "body",
    [
        "{{midday_activity_block}} {{customer_name}}",
        "{{midday_activity_block}} {{miles}}",
        # Un bloque de fin de jornada en el de mediodía: existe, pero no aquí.
        "{{midday_activity_block}} {{week_activity_block}}",
    ],
)
def test_variables_desconocidas_o_de_otra_plantilla(body):
    errores = _errores(MEDIODIA, body=body)
    assert any("Unsupported variable" in m for _, m in errores), errores


@pytest.mark.parametrize(
    "body",
    [
        "{{midday_activity_block}} {{ user.first_name }}",
        "{{midday_activity_block}} {% if x %}hola{% endif %}",
        "{{midday_activity_block}} {{user_first_name",
        "{{midday_activity_block}} user_first_name}}",
    ],
)
def test_sintaxis_mal_formada(body):
    errores = _errores(MEDIODIA, body=body)
    assert any("Malformed placeholder" in m for _, m in errores), errores


@pytest.mark.parametrize(
    "body",
    [
        "{{midday_activity_block}} <script>alert(1)</script>",
        "{{midday_activity_block}} <b>hola</b>",
        "{{midday_activity_block}} <!-- x -->",
    ],
)
def test_html_rechazado(body):
    assert any("HTML" in m for _, m in _errores(MEDIODIA, body=body))


@pytest.mark.parametrize("enlace", ["https://x.example", "http://x", "www.x.com", "javascript:alert(1)"])
def test_enlaces_rechazados(enlace):
    assert any("Links" in m for _, m in _errores(MEDIODIA, body=f"{{{{midday_activity_block}}}} {enlace}"))


@pytest.mark.parametrize(
    ("subject", "fragmento"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("Hola\nBcc: otro@x.com", "single line"),
        ("Hola\rX", "single line"),
        ("x" * 201, "exceed"),
        ("Hola {{midday_activity_block}}", "Unsupported variable"),
    ],
)
def test_asunto(subject, fragmento):
    errores = _errores(MEDIODIA, subject=subject)
    assert any(campo == "subject" and fragmento in m for campo, m in errores), errores


def test_cuerpo_vacio_o_largo():
    assert any("empty" in m for _, m in _errores(MEDIODIA, body="  "))
    largo = "{{midday_activity_block}}" + "x" * 5000
    assert any("exceed" in m for _, m in _errores(MEDIODIA, body=largo))


def test_utf8_y_emojis_se_conservan():
    body = "¡Ánimo, {{user_first_name}}! 💪🌟\n{{midday_activity_block}}\nñ ü é"
    assert _errores(MEDIODIA, body=body) == []
    hecho = content.render(body, content.SAMPLE_VALUES)
    assert hecho.startswith("¡Ánimo, María! 💪🌟")
    assert hecho.endswith("ñ ü é")


def test_render_solo_sustituye_marcadores():
    texto = "{{user_first_name}} {{ user_first_name }} {{otro}} {user_first_name}"
    assert content.render(texto, {"user_first_name": "Ana"}) == "Ana Ana {{otro}} {user_first_name}"
    # Un valor con llaves no se vuelve a evaluar.
    assert content.render("{{user_first_name}}", {"user_first_name": "{{x}}"}) == "{{x}}"


def test_la_capacidad_es_a_demanda():
    assert "route.activityemails.manage" in CAPABILITY_NAMES
    assert "route.activityemails.manage" in CAPACIDADES_A_DEMANDA
    for plantilla in DEFAULT_ROLES:
        assert "route.activityemails.manage" not in capabilities_for(plantilla), plantilla.name
