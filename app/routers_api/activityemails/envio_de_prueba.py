"""
Prueba controlada de los correos de actividad (RTE-MAIL-TEST-01).

Manda **una** plantilla, con su texto guardado y **datos ficticios**, a un
destinatario de prueba autorizado. Sirve para comprobar que el proveedor
configurado acepta el correo y cómo se ve en una bandeja real, sin tocar a
ninguna persona real.

Las barreras
------------
* **Destino cerrado.** Sólo el propio correo de quien prueba o una dirección de
  `MAIL_TEST_RECIPIENTS`. Nunca un destino libre, ni copia, ni copia oculta.
* **Marcado como prueba.** «[TEST]» en el asunto, un aviso al principio del
  cuerpo y la cabecera `X-CER-Route-Test`.
* **Aislado.** No lee ni cambia preferencias de destinatarios, ni jornadas, ni
  actividades, y no ocupa ninguna clave de «un correo al día»: el motor de
  envío (RTE-NOT-02/03) no existe todavía y, cuando exista, una prueba no
  contará como el envío del día.
* **Límite.** `LIMITE` pruebas por persona cada `VENTANA`, contadas en la
  auditoría, que es duradera y compartida entre réplicas.
* **Honesto.** El resultado distingue «aceptado por el proveedor» de «no salió
  del servidor» (backend de desarrollo) y de los fallos. **Nunca** dice
  «entregado»: eso sólo lo sabe la bandeja de destino.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.config import settings
from app.core.audit.models import AuditEvent
from app.core.audit.service import record_event
from app.core.db.session import db_session
from app.core.email import backends
from app.routers_api.activityemails import content
from app.routers_api.activityemails.service import ActivityEmailService, correo_valido
from app.routers_api.users.models import Users

LIMITE = 5
VENTANA = timedelta(minutes=15)
CABECERA = "X-CER-Route-Test"
AVISO = (
    "*** CORREO DE PRUEBA — datos ficticios ({etiqueta}). "
    "No corresponde a la actividad de ninguna persona. ***\n\n"
)

#: Backends que no mandan nada fuera del servidor.
_SIN_SALIDA = {"console": "not_sent_development_backend", "memory": "captured_by_test_backend"}


class Outcome:
    ACCEPTED = "accepted_by_provider"
    NOT_SENT_DEV = "not_sent_development_backend"
    CAPTURED = "captured_by_test_backend"
    FAILED_AUTH = "failed_auth"
    FAILED_UNREACHABLE = "failed_unreachable"


def _lista_configurada() -> list[str]:
    return [
        d.strip().lower()
        for d in settings.MAIL_TEST_RECIPIENTS.split(",")
        if d.strip() and correo_valido(d.strip())
    ]


async def destinatarios_de_prueba(*, actor_user_id: int) -> list[str]:
    """Las direcciones a las que este actor puede mandar una prueba."""
    async with db_session() as session:
        propio = await session.scalar(select(Users.email).where(Users.id == actor_user_id))
    lista = []
    if propio and correo_valido(propio):
        lista.append(propio.lower())
    for d in _lista_configurada():
        if d not in lista:
            lista.append(d)
    return lista


def proveedor_configurado() -> bool:
    """Si hay un proveedor real (Settings o SMTP del entorno). Sin detalles."""
    return bool(
        backends.backend_from_platform_config("email")
        or backends.backend_from_platform_config("email_fallback")
        or settings.EMAIL_BACKEND == "smtp"
    )


async def _pruebas_recientes(*, company_id: int, actor_user_id: int) -> int:
    desde = datetime.now(timezone.utc) - VENTANA
    async with db_session() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.company_id == company_id,
                    AuditEvent.entity_type == "activity_email_test",
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.occurred_at >= desde,
                )
            )
            or 0
        )


async def enviar_prueba(*, company_id: int, actor_user_id: int, template_type: str, to: str) -> dict:
    plantilla = await ActivityEmailService.get_template(company_id=company_id, template_type=template_type)
    destino = to.strip().lower()
    if destino not in await destinatarios_de_prueba(actor_user_id=actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test emails can only go to your own address or an approved test recipient.",
        )
    if await _pruebas_recientes(company_id=company_id, actor_user_id=actor_user_id) >= LIMITE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Test limit reached: {LIMITE} every {int(VENTANA.total_seconds() // 60)} minutes.",
        )

    asunto = "[TEST] " + content.render(plantilla["subject"], content.SAMPLE_VALUES)
    cuerpo = AVISO.format(etiqueta=content.SAMPLE_LABEL) + content.render(plantilla["body"], content.SAMPLE_VALUES)
    error = None
    backend = None
    try:
        backend = await asyncio.to_thread(
            backends.send_email,
            to=destino,
            subject=asunto,
            body=cuerpo,
            headers={CABECERA: f"activity-email; {template_type}"},
        )
        resultado = _SIN_SALIDA.get(backend, Outcome.ACCEPTED)
    except backends.EmailAuthFailed:
        resultado, error = Outcome.FAILED_AUTH, "The mail provider rejected the configured credentials."
    except backends.EmailUnreachable:
        resultado, error = Outcome.FAILED_UNREACHABLE, "The mail provider could not be reached."

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
        "delivered_confirmed": False,
    }
