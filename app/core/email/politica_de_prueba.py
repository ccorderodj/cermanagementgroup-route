"""
Reglas comunes de los envíos de **prueba** (RTE-MAIL-UNIFIED-01, CP1).

Las comparten la prueba del proveedor (T0, plataforma) y las de las plantillas
(T1-T4, Activity Emails), para que no haya dos políticas distintas:

* **Destinos cerrados:** el propio correo de quien prueba y
  `MAIL_TEST_RECIPIENTS`. Ningún destino libre.
* **Presupuesto compartido:** `LIMITE` pruebas por persona cada `VENTANA`,
  sumando todos los caminos. Se **reserva antes de mandar**, dentro de un
  candado consultivo de PostgreSQL por persona: dos réplicas o dos clics a la
  vez no pueden pasar los dos con el último hueco.
* **Marcado:** «[TEST]» una sola vez en el asunto, banner
  «CORREO DE PRUEBA — datos ficticios» y cabecera `X-CER-Route-Test`.
* **Resultado honesto:** del `name` del backend que lo tomó. `console` y
  `memory` nunca cuentan como salida real; nada cuenta como «entregado».
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from sqlalchemy import func, select, text, update

from app.config import settings
from app.core.db.session import transaction
from app.core.email.models import MailTestOutcome, MailTestSend

LIMITE = 5
VENTANA = timedelta(minutes=15)
CABECERA = "X-CER-Route-Test"
PREFIJO = "[TEST] "
BANNER = "*** CORREO DE PRUEBA — datos ficticios. No corresponde a la actividad de ninguna persona. ***\n\n"

#: Espacio del candado consultivo (`pg_advisory_xact_lock(espacio, actor)`).
_CANDADO = 7_310_041

_SIN_SALIDA = {
    "console": MailTestOutcome.NOT_SENT_DEVELOPMENT_BACKEND,
    "memory": MailTestOutcome.CAPTURED_BY_TEST_BACKEND,
}


def correo_valido(email: str | None) -> bool:
    if not email:
        return False
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return False
    return True


def destinos_permitidos(propio: str | None) -> list[str]:
    """El propio correo (si es válido) y la lista configurada, sin repetir."""
    lista: list[str] = []
    if propio and correo_valido(propio):
        lista.append(propio.strip().lower())
    for d in settings.MAIL_TEST_RECIPIENTS.split(","):
        d = d.strip().lower()
        if d and correo_valido(d) and d not in lista:
            lista.append(d)
    return lista


def exigir_destino(destino: str, permitidos: list[str]) -> str:
    limpio = destino.strip().lower()
    if limpio not in permitidos:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test emails can only go to your own address or an approved test recipient.",
        )
    return limpio


def asunto(texto: str) -> str:
    """«[TEST]» exactamente una vez, aunque el texto ya lo traiga."""
    limpio = texto
    while limpio.startswith(PREFIJO):
        limpio = limpio[len(PREFIJO):]
    return PREFIJO + limpio


def resultado_de(backend: str) -> str:
    return _SIN_SALIDA.get(backend, MailTestOutcome.ACCEPTED_BY_PROVIDER).value


async def reservar(
    *, actor_user_id: int, company_id: int | None, channel: str, target: str, destination: str
) -> int:
    """Ocupa un hueco del presupuesto o responde 429. Devuelve la fila reservada."""
    desde = datetime.now(timezone.utc) - VENTANA
    async with transaction() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k, :a)"), {"k": _CANDADO, "a": actor_user_id}
        )
        usados = await session.scalar(
            select(func.count()).select_from(MailTestSend).where(
                MailTestSend.actor_user_id == actor_user_id,
                MailTestSend.created_at >= desde,
            )
        )
        if int(usados or 0) >= LIMITE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Test limit reached: {LIMITE} every {int(VENTANA.total_seconds() // 60)} minutes.",
            )
        fila = MailTestSend(
            actor_user_id=actor_user_id,
            company_id=company_id,
            channel=channel,
            target=target,
            destination=destination,
            outcome=MailTestOutcome.PENDING.value,
        )
        session.add(fila)
        await session.flush()
        return fila.id


async def cerrar(fila_id: int, *, outcome: str, backend: str | None) -> None:
    async with transaction() as session:
        await session.execute(
            update(MailTestSend)
            .where(MailTestSend.id == fila_id)
            .values(outcome=outcome, backend=backend, finished_at=func.now())
        )
