"""
Metadatos de integración: `integration_event`, append-only.

Se registra cada mensaje que entra o sale —aceptado, duplicado, rechazado o
encolado— con su identificador de correlación y la huella del cuerpo. Es la
respuesta a «¿nos llegó ese evento de la otra aplicación, y qué hicimos?» sin
copiar datos de dominio a una tabla transversal.
"""

from __future__ import annotations

from sqlalchemy import insert

from app.core.db.session import db_session
from app.core.integration.models import IntegrationEvent


def current_request_id() -> str | None:
    try:
        from asgi_correlation_id import correlation_id

        valor = correlation_id.get()
    except Exception:
        valor = None
    return str(valor)[:64] if valor else None


async def record_integration_event(
    *,
    direction: str,
    status: str,
    company_id: int | None = None,
    endpoint_id: int | None = None,
    counterpart_app: str | None = None,
    event_id: str | None = None,
    event_type: str | None = None,
    correlation_id: str | None = None,
    payload_sha256: str | None = None,
    detail: str | None = None,
) -> None:
    async with db_session() as session:
        await session.execute(
            insert(IntegrationEvent).values(
                company_id=company_id,
                endpoint_id=endpoint_id,
                direction=direction,
                counterpart_app=(counterpart_app or None) and counterpart_app[:80],
                event_id=(event_id or None) and event_id[:64],
                event_type=(event_type or None) and event_type[:120],
                status=status,
                request_id=current_request_id(),
                correlation_id=(correlation_id or None) and correlation_id[:64],
                payload_sha256=payload_sha256,
                detail=detail,
            )
        )
        await session.commit()
