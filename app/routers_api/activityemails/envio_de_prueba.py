"""
Prueba controlada de los correos de actividad (RTE-MAIL-TEST-01, endurecida en
RTE-MAIL-UNIFIED-01 CP1).

Manda **una** plantilla, con su texto guardado y **datos ficticios**, a un
destinatario de prueba autorizado. Sirve para comprobar que el proveedor
configurado acepta el correo y cómo se ve en una bandeja real, sin tocar a
ninguna persona real.

Destinos, presupuesto, marcado y resultado son los de
`app/core/email/politica_de_prueba.py`, **los mismos** que la prueba del
proveedor en Platform: no hay una segunda política.

Aislado: no lee ni cambia preferencias de destinatarios, ni jornadas, ni
actividades, y no ocupa ninguna clave de «un correo al día» (el motor de envío
todavía no existe).
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.core.audit.service import record_event
from app.core.db.session import db_session
from app.core.email import backends
from app.core.email import politica_de_prueba as politica
from app.core.email.models import MailTestChannel, MailTestOutcome
from app.routers_api.activityemails import content
from app.routers_api.activityemails.service import ActivityEmailService
from app.routers_api.users.models import Users

LIMITE = politica.LIMITE
VENTANA = politica.VENTANA


async def destinatarios_de_prueba(*, actor_user_id: int) -> list[str]:
    """Las direcciones a las que este actor puede mandar una prueba."""
    async with db_session() as session:
        propio = await session.scalar(select(Users.email).where(Users.id == actor_user_id))
    return politica.destinos_permitidos(propio)


def proveedor_configurado() -> bool:
    """Si hay un proveedor real (Settings o SMTP del entorno). Sin detalles."""
    return bool(
        backends.backend_from_platform_config("email")
        or backends.backend_from_platform_config("email_fallback")
        or settings.EMAIL_BACKEND == "smtp"
    )


async def enviar_prueba(*, company_id: int, actor_user_id: int, template_type: str, to: str) -> dict:
    plantilla = await ActivityEmailService.get_template(company_id=company_id, template_type=template_type)
    destino = politica.exigir_destino(to, await destinatarios_de_prueba(actor_user_id=actor_user_id))
    fila = await politica.reservar(
        actor_user_id=actor_user_id,
        company_id=company_id,
        channel=MailTestChannel.TEMPLATE.value,
        target=template_type,
        destination=destino,
    )

    asunto = politica.asunto(content.render(plantilla["subject"], content.SAMPLE_VALUES))
    cuerpo = politica.BANNER + content.render(plantilla["body"], content.SAMPLE_VALUES)
    error = None
    backend = None
    try:
        backend = await asyncio.to_thread(
            backends.send_email,
            to=destino,
            subject=asunto,
            body=cuerpo,
            headers={politica.CABECERA: f"activity-email; {template_type}"},
        )
        resultado = politica.resultado_de(backend)
    except backends.EmailAuthFailed:
        resultado, error = MailTestOutcome.FAILED_AUTH.value, "The mail provider rejected the configured credentials."
    except backends.EmailUnreachable:
        resultado, error = MailTestOutcome.FAILED_UNREACHABLE.value, "The mail provider could not be reached."
    await politica.cerrar(fila, outcome=resultado, backend=backend)

    # Sólo metadatos: ni el cuerpo ni el texto del proveedor (puede repetir
    # identificadores de la cuenta).
    await record_event(
        company_id=company_id,
        entity_type="activity_email_test",
        entity_id=actor_user_id,
        action="test_send",
        actor_user_id=actor_user_id,
        summary=f"Test of '{plantilla['label']}' to {destino}: {resultado}",
        changes={
            "template_type": {"old": None, "new": template_type},
            "to": {"old": None, "new": destino},
            "outcome": {"old": None, "new": resultado},
            "backend": {"old": None, "new": backend},
        },
    )
    if error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"outcome": resultado, "message": error})
    return {
        "outcome": resultado,
        "to": destino,
        "subject": asunto,
        "backend": backend,
        "delivered_confirmed": False,
    }
