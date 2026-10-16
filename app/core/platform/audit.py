"""
Traza de plataforma: quién cambió qué en la configuración del despliegue.

Registra lo que el doc 03 del paquete exige para toda acción interna —usuario,
rol, sesión y dispositivo— además del identificador de la petición, que permite
cruzar la fila con el log del servidor.

Se escribe **dentro** de la transacción del cambio, como `record_event`: la
traza y el cambio se confirman o se deshacen juntos.
"""

from __future__ import annotations

from typing import Any, Mapping

from fastapi import Request
from sqlalchemy import insert

from app.core.db.session import db_session
from app.core.platform.models import PlatformAuditEvent

#: Lo que aparece en la traza en lugar del valor de un secreto.
REDACTED = "changed"


def _request_id(request: Request | None) -> str | None:
    try:
        from asgi_correlation_id import correlation_id

        valor = correlation_id.get()
    except Exception:
        valor = None
    if not valor and request is not None:
        valor = request.headers.get("x-request-id")
    return (valor or None) and str(valor)[:64]


async def record_platform_event(
    *,
    request: Request | None,
    actor,
    action: str,
    target: str,
    changes: Mapping[str, Any] | None = None,
) -> None:
    ip = request.client.host if request is not None and request.client else None
    agente = request.headers.get("user-agent") if request is not None else None
    async with db_session() as session:
        await session.execute(
            insert(PlatformAuditEvent).values(
                actor_user_id=getattr(actor, "id", None),
                actor_role="platform_admin" if getattr(actor, "is_superuser", False) else None,
                action=action,
                target=target,
                changes=dict(changes) if changes else None,
                request_id=_request_id(request),
                ip=ip[:64] if ip else None,
                user_agent=agente[:300] if agente else None,
            )
        )
        await session.commit()
