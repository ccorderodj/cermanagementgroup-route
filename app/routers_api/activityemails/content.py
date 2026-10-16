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
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import BusinessEnum


class ActivityEmailType(BusinessEnum):
    """Los dos correos aprobados (BR-01). Cerrados: los define el producto."""

    MIDDAY_MOTIVATION = "midday_motivation"
    END_OF_DAY_RECOGNITION = "end_of_day_recognition"


#: Límites del asunto y del cuerpo. El asunto es una sola línea: un salto de
#: línea en una cabecera de correo es inyección de cabeceras.
SUBJECT_MAX = 200
BODY_MAX = 5000

#: Marcador de vista previa. Ningún dato de ejemplo se enseña sin él.
SAMPLE_LABEL = "Ejemplo / Vista previa"


@dataclass(frozen=True)
class TemplateSpec:
    type: ActivityEmailType
    label: str
    schedule_label: str
    default_subject: str
    default_body: str
    #: Variables que admite el cuerpo.
    body_tokens: tuple[str, ...]
    #: Las que el cuerpo no puede perder (BR-07).
    required_tokens: tuple[str, ...]


#: Variables que admite el asunto: sólo el nombre. Un bloque de recuento en el
#: asunto sería una línea de varias filas.
SUBJECT_TOKENS: tuple[str, ...] = ("user_first_name",)

TOKEN_HELP: dict[str, str] = {
    "user_first_name": "Nombre de pila de la persona (si falta: «colega»)",
    "midday_activity_block": "Resumen breve de las actividades completadas hasta mediodía",
    "day_activity_block": "Resumen breve de las actividades completadas en la jornada",
    "week_activity_block": "Total de actividades completadas en la semana, por categoría general",
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

SPECS: dict[str, TemplateSpec] = {
    ActivityEmailType.MIDDAY_MOTIVATION: TemplateSpec(
        type=ActivityEmailType.MIDDAY_MOTIVATION,
        label="Midday Motivation",
        schedule_label="12:00 p.m.",
        default_subject="¡Buen trabajo! Sigamos adelante 💪",
        default_body=_MIDDAY_BODY,
        body_tokens=("user_first_name", "midday_activity_block"),
        required_tokens=("midday_activity_block",),
    ),
    ActivityEmailType.END_OF_DAY_RECOGNITION: TemplateSpec(
        type=ActivityEmailType.END_OF_DAY_RECOGNITION,
        label="End of Day Recognition",
        schedule_label="End Work + 20 min",
        default_subject="¡Jornada finalizada! Este es tu avance de hoy 🌟",
        default_body=_END_OF_DAY_BODY,
        body_tokens=("user_first_name", "day_activity_block", "week_activity_block"),
        required_tokens=("day_activity_block", "week_activity_block"),
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


def _marcadores(valor: str) -> list[str]:
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
    fuera = sorted(set(_marcadores(subject)) - set(SUBJECT_TOKENS))
    if fuera:
        errores.append(("subject", f"Unsupported variable(s) in the subject: {', '.join(fuera)}."))

    if not body.strip():
        errores.append(("body", "The body cannot be empty."))
    elif len(body) > BODY_MAX:
        errores.append(("body", f"The body cannot exceed {BODY_MAX} characters."))
    errores += _texto_libre("body", body)
    usados = _marcadores(body)
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
    return errores


def render(valor: str, valores: dict[str, str]) -> str:
    """Sustituye cada marcador permitido por su valor. Sin evaluación."""
    return _TOKEN.sub(lambda m: valores.get(m.group(1), m.group(0)), valor)
