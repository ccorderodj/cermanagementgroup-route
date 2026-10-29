"""
Contenido de los correos de actividad (RTE-NOT-01): plantillas, variables y
vista previa.

Lo que este módulo es
---------------------
La **única** definición de qué puede decir un correo de actividad: los dos
tipos aprobados, su texto por defecto, las variables que cada uno admite y las
que no puede perder. El servicio valida contra esto al guardar y la vista previa
renderiza con esto; el motor de envío (RTE-NOT-02/03) resolverá las mismas
variables con datos reales.

Texto plano, sustitución explícita
----------------------------------
Una plantilla es texto plano con marcadores `{{variable}}`. No hay motor de
plantillas ni evaluación: renderizar es reemplazar cada marcador permitido por su
valor, y nada más. Por eso se rechaza al guardar cualquier cosa que parezca otra
sintaxis (`{%`, llaves sueltas), HTML o un enlace: lo que no se puede expresar
no se puede inyectar.

Las variables nunca llevan datos sensibles (BR-06): ni ubicaciones, ni millas,
ni clientes, ni empleados, ni horas exactas, ni rankings. Sólo el nombre de pila
y bloques de recuento por categoría.

Sin actividades, no hay correo
------------------------------
Decisión del PO (16-10-2026): sin actividad **no se envía** el correo; no se
manda una versión «sin recuento». Mediodía sale si la persona inició al menos
una actividad antes de las 12:00, terminada o no (regla del PO tras MR !118);
las abiertas se enseñan aparte, nunca como hechas. Fin de jornada sigue
pidiendo al menos una completada en la jornada cerrada. `TemplateSpec.send_condition` lo dice en pantalla y es el
contrato del motor de envío (RTE-NOT-02/03), que es quien lo aplicará.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import BusinessEnum


class ActivityEmailType(BusinessEnum):
    """Los correos aprobados. Cerrados: los define el producto.

    Dos motivacionales (RTE-NOT-01) y dos reportes estratégicos para mandos
    (RTE-MAIL-UNIFIED-01 V1.2).
    """

    MIDDAY_MOTIVATION = "midday_motivation"
    END_OF_DAY_RECOGNITION = "end_of_day_recognition"
    STRATEGIC_MIDDAY_REPORT = "strategic_midday_report"
    STRATEGIC_END_OF_DAY_REPORT = "strategic_end_of_day_report"


class ActivityEmailGroup(BusinessEnum):
    MOTIVATIONAL = "motivational"
    STRATEGIC = "strategic"


#: Límites del asunto y del cuerpo. El asunto es una sola línea: un salto de
#: línea en una cabecera de correo es inyección de cabeceras.
SUBJECT_MAX = 200
BODY_MAX = 5000

#: Marcador de vista previa. Ningún dato de ejemplo se enseña sin él.
SAMPLE_LABEL = "Ejemplo / Vista previa"


@dataclass(frozen=True)
class TemplateSpec:
    type: ActivityEmailType
    group: ActivityEmailGroup
    label: str
    schedule_label: str
    default_subject: str
    default_body: str
    #: Variables que admite el cuerpo.
    body_tokens: tuple[str, ...]
    #: Las que el cuerpo no puede perder (BR-07).
    required_tokens: tuple[str, ...]
    #: Cuándo se envía (y cuándo no): ver «Sin actividades, no hay correo».
    send_condition: str
    #: Variables que admite el asunto.
    subject_tokens: tuple[str, ...]
    #: Bloques generados que deben aparecer **una sola vez y en este orden**.
    ordered_blocks: tuple[str, ...] = ()


#: Variables que admite el asunto de los motivacionales: sólo el nombre. Un
#: bloque de recuento en el asunto sería una línea de varias filas.
SUBJECT_TOKENS: tuple[str, ...] = ("user_first_name",)
#: Las de los reportes estratégicos: el mando y el periodo.
STRATEGIC_SUBJECT_TOKENS: tuple[str, ...] = ("manager_first_name", "report_period_label")

TOKEN_HELP: dict[str, str] = {
    "user_first_name": "Nombre de pila de la persona (si falta: «colega»)",
    "midday_activity_block": "Resumen breve de las actividades completadas hasta mediodía",
    "day_activity_block": "Resumen breve de las actividades completadas en la jornada",
    "week_activity_block": "Total de actividades completadas en la semana, por categoría general",
    "manager_first_name": "Nombre de pila del mando que recibe el reporte",
    "report_period_label": "Fecha del reporte",
    "report_generated_at": "Momento en que se generó el reporte",
    "executive_snapshot": "Resumen del equipo al corte: personas, sin inicio, en curso, finalizadas, eventos y millas",
    "per_person_report": "Un bloque por persona del equipo: jornada, desglose del día y detalle de actividades",
    "team_weekly_summary": "Resumen semanal del equipo, al final, sin contar a nadie dos veces",
    "week_period_label": "Fechas de la semana del reporte",
}

_MIDDAY_BODY = """¡Vas haciendo un gran trabajo!

Hola, {{user_first_name}}:

Ya estamos a mitad del día y queremos recordarte que cada actividad cuenta.

{{midday_activity_block}}

Cada visita, cada conversación y cada esfuerzo contribuyen a nuestros objetivos.

¡Continúa con esa energía y que tengas una excelente tarde!

CER Management Group"""

_END_OF_DAY_BODY = """¡Excelente esfuerzo hoy!

Hola, {{user_first_name}}:

Has finalizado una jornada más. Gracias por tu dedicación y compromiso.

{{day_activity_block}}

{{week_activity_block}}

El trabajo constante construye grandes resultados. Gracias por todo lo que aportas.

¡Descansa y recarga energías para tu próxima jornada!

CER Management Group"""

_STRATEGIC_MIDDAY_BODY = """Hola, {{manager_first_name}}:

Compartimos el avance operativo registrado por las personas bajo tu supervisión hasta las 12:00 p. m. de hoy.

{{executive_snapshot}}

{{per_person_report}}

Este reporte refleja únicamente la actividad registrada en CER Route hasta el momento del corte. La información en curso o pendiente de cierre se identifica como tal.

CER Route"""

_STRATEGIC_END_OF_DAY_BODY = """Hola, {{manager_first_name}}:

Compartimos el resumen de las actividades registradas hoy por las personas bajo tu supervisión hasta las 7:00 p. m., junto con su acumulado de la semana.

{{executive_snapshot}}

{{per_person_report}}

{{team_weekly_summary}}

Los datos corresponden a la información registrada y autorizada en CER Route al momento de generar el reporte. Las actividades pendientes de cierre o medición se indican expresamente.

CER Route"""

#: Lo que dice cada reporte estratégico sobre su envío. Las notas reales no
#: salen por correo hasta DP-NOTES.
_NOTAS = "Real activity notes are not included until the notes policy is approved."

SPECS: dict[str, TemplateSpec] = {
    ActivityEmailType.MIDDAY_MOTIVATION: TemplateSpec(
        type=ActivityEmailType.MIDDAY_MOTIVATION,
        group=ActivityEmailGroup.MOTIVATIONAL,
        label="Midday Motivation",
        schedule_label="12:00 p.m.",
        default_subject="¡Buen trabajo! Sigamos adelante 💪",
        default_body=_MIDDAY_BODY,
        body_tokens=("user_first_name", "midday_activity_block"),
        required_tokens=("midday_activity_block",),
        send_condition=(
            "Sent if the person started at least one activity before noon, completed or not; "
            "unfinished ones are shown apart, never as done. No activities, no email."
        ),
        subject_tokens=SUBJECT_TOKENS,
    ),
    ActivityEmailType.END_OF_DAY_RECOGNITION: TemplateSpec(
        type=ActivityEmailType.END_OF_DAY_RECOGNITION,
        group=ActivityEmailGroup.MOTIVATIONAL,
        label="End of Day Recognition",
        schedule_label="End Work + 20 min",
        default_subject="¡Jornada finalizada! Este es tu avance de hoy 🌟",
        default_body=_END_OF_DAY_BODY,
        body_tokens=("user_first_name", "day_activity_block", "week_activity_block"),
        required_tokens=("day_activity_block", "week_activity_block"),
        send_condition=(
            "Sent only if the person completed at least one activity during the closed workday. "
            "No activities, no email."
        ),
        subject_tokens=SUBJECT_TOKENS,
    ),
    ActivityEmailType.STRATEGIC_MIDDAY_REPORT: TemplateSpec(
        type=ActivityEmailType.STRATEGIC_MIDDAY_REPORT,
        group=ActivityEmailGroup.STRATEGIC,
        label="Strategic Midday Report",
        schedule_label="12:00 p.m. (reporting time)",
        default_subject="CER Route | Reporte operativo de mediodía — {{report_period_label}}",
        default_body=_STRATEGIC_MIDDAY_BODY,
        body_tokens=(
            "manager_first_name", "report_period_label", "report_generated_at",
            "executive_snapshot", "per_person_report",
        ),
        required_tokens=("per_person_report",),
        send_condition=(
            "For enabled managers at 12:00 p.m. in their time zone: one block per active team member, "
            "including people who have not started, as they stood at noon. No weekly team block. " + _NOTAS
        ),
        subject_tokens=STRATEGIC_SUBJECT_TOKENS,
        ordered_blocks=("per_person_report",),
    ),
    ActivityEmailType.STRATEGIC_END_OF_DAY_REPORT: TemplateSpec(
        type=ActivityEmailType.STRATEGIC_END_OF_DAY_REPORT,
        group=ActivityEmailGroup.STRATEGIC,
        label="Strategic End-of-Day Report",
        schedule_label="7:00 p.m. (reporting time)",
        default_subject="CER Route | Resumen del día y acumulado semanal — {{report_period_label}}",
        default_body=_STRATEGIC_END_OF_DAY_BODY,
        body_tokens=(
            "manager_first_name", "report_period_label", "report_generated_at",
            "executive_snapshot", "per_person_report", "team_weekly_summary", "week_period_label",
        ),
        required_tokens=("per_person_report", "team_weekly_summary"),
        send_condition=(
            "One consolidated email per enabled manager and day at 7:00 p.m. in their time zone, "
            "never earlier and never delayed by open workdays: people still working show as in "
            "progress. Ends with the Team Weekly Summary. " + _NOTAS
        ),
        subject_tokens=STRATEGIC_SUBJECT_TOKENS,
        ordered_blocks=("per_person_report", "team_weekly_summary"),
    ),
}

#: Valores **ficticios** de la vista previa (sección 6). Nunca datos reales.
SAMPLE_VALUES: dict[str, str] = {
    "user_first_name": "María",
    "midday_activity_block": (
        "Hasta ahora has realizado:\n"
        "- 2 visitas a clientes.\n"
        "- 1 actividad de reclutamiento.\n"
        "- 1 gestión de seguimiento."
    ),
    "day_activity_block": (
        "Tu día en resumen:\n"
        "- 3 visitas.\n"
        "- 2 gestiones.\n"
        "- 1 actividad de reclutamiento."
    ),
    "week_activity_block": (
        "Tu semana hasta hoy:\n"
        "18 actividades realizadas durante la semana en visitas, reclutamiento y "
        "gestiones operativas."
    ),
}

#: Un marcador bien formado: `{{ nombre }}` con letras minúsculas y guiones bajos.
_TOKEN = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
#: HTML: una etiqueta, un comentario o una declaración.
_HTML = re.compile(r"<\s*[/!a-zA-Z]")
#: Un enlace web. V1 no admite enlaces (sección 8).
_LINK = re.compile(r"(?i)\b(?:https?://|www\.|javascript:|data:)")


def spec(template_type: str) -> TemplateSpec:
    return SPECS[ActivityEmailType(template_type)]


def sample_values(template_type: str) -> dict[str, str]:
    """Los valores **ficticios** de la vista previa y de las pruebas."""
    s = spec(template_type)
    if s.group == ActivityEmailGroup.MOTIVATIONAL:
        return SAMPLE_VALUES
    from app.routers_api.activityemails.strategic import valores_de_demostracion

    return valores_de_demostracion(s.type == ActivityEmailType.STRATEGIC_END_OF_DAY_REPORT)


def _texto_libre(campo: str, valor: str) -> list[tuple[str, str]]:
    errores: list[tuple[str, str]] = []
    if _HTML.search(valor):
        errores.append((campo, "HTML is not allowed: templates are plain text."))
    if _LINK.search(valor):
        errores.append((campo, "Links are not allowed in activity emails."))
    # Lo que queda entre llaves después de quitar los marcadores bien formados
    # es otra sintaxis o un marcador roto: `{{ user.name }}`, `{% if %}`, `{{x`.
    sin_marcadores = _TOKEN.sub("", valor)
    if any(s in sin_marcadores for s in ("{{", "}}", "{%", "%}")):
        errores.append((campo, "Malformed placeholder: use {{variable}} with a supported name."))
    return errores


def marcadores(valor: str) -> list[str]:
    return [m.group(1) for m in _TOKEN.finditer(valor)]


def validate(template_type: str, *, subject: str, body: str) -> list[tuple[str, str]]:
    """Errores por campo (`subject` / `body`); lista vacía si es válido."""
    s = spec(template_type)
    errores: list[tuple[str, str]] = []

    if not subject.strip():
        errores.append(("subject", "The subject cannot be empty."))
    elif len(subject) > SUBJECT_MAX:
        errores.append(("subject", f"The subject cannot exceed {SUBJECT_MAX} characters."))
    if "\r" in subject or "\n" in subject:
        errores.append(("subject", "The subject must be a single line."))
    errores += _texto_libre("subject", subject)
    fuera = sorted(set(marcadores(subject)) - set(s.subject_tokens))
    if fuera:
        errores.append(("subject", f"Unsupported variable(s) in the subject: {', '.join(fuera)}."))

    if not body.strip():
        errores.append(("body", "The body cannot be empty."))
    elif len(body) > BODY_MAX:
        errores.append(("body", f"The body cannot exceed {BODY_MAX} characters."))
    errores += _texto_libre("body", body)
    usados = marcadores(body)
    fuera = sorted(set(usados) - set(s.body_tokens))
    if fuera:
        errores.append(("body", f"Unsupported variable(s) for this email: {', '.join(fuera)}."))
    faltan = [t for t in s.required_tokens if t not in usados]
    if faltan:
        errores.append((
            "body",
            "The activity summary is required: keep "
            + ", ".join(f"{{{{{t}}}}}" for t in faltan)
            + ".",
        ))
    # Los bloques generados de los reportes: una vez cada uno y en su orden (el
    # resumen del equipo, siempre después de las personas).
    if s.ordered_blocks and not faltan:
        repetidos = [t for t in s.ordered_blocks if usados.count(t) > 1]
        if repetidos:
            errores.append(("body", "Each report block can appear only once: " + ", ".join(repetidos) + "."))
        elif [t for t in usados if t in s.ordered_blocks] != list(s.ordered_blocks):
            errores.append(("body", "The Team Weekly Summary must come after the per-person report."))
    return errores


def render(valor: str, valores: dict[str, str]) -> str:
    """Sustituye cada marcador permitido por su valor. Sin evaluación."""
    return _TOKEN.sub(lambda m: valores.get(m.group(1), m.group(0)), valor)
