"""
El contexto de la petición que la auditoría necesita (WP-9).

`record_event` se llama desde DAOs y servicios que no reciben la petición. En vez
de pasar IP y user agent por todas las capas, un middleware ASGI los deja en una
variable de contexto al entrar y `record_event` los lee.

La IP
-----
Detrás del balanceador de DigitalOcean la dirección del socket es la del proxy,
así que en producción se toma el primer valor de `X-Forwarded-For`, que es el que
pone ese proxy. Fuera de producción no hay proxy de confianza y esa cabecera la
puede escribir cualquiera: se usa la del socket. Es un dato informativo para la
traza, no un control de acceso.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class RequestContext:
    ip_address: str | None
    user_agent: str | None


_contexto: ContextVar[RequestContext | None] = ContextVar("audit_request_context", default=None)


def current_request_context() -> RequestContext | None:
    return _contexto.get()


class AuditRequestContextMiddleware:
    """ASGI puro, para que la variable de contexto llegue intacta al endpoint."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        cabeceras = {
            clave.decode("latin-1").lower(): valor.decode("latin-1")
            for clave, valor in scope.get("headers") or []
        }
        ip = None
        reenviada = cabeceras.get("x-forwarded-for", "")
        if settings.is_production and reenviada:
            ip = reenviada.split(",")[0].strip()
        elif scope.get("client"):
            ip = scope["client"][0]
        agente = cabeceras.get("user-agent") or None
        token = _contexto.set(
            RequestContext(
                ip_address=ip[:64] if ip else None,
                user_agent=agente[:300] if agente else None,
            )
        )
        try:
            await self.app(scope, receive, send)
        finally:
            _contexto.reset(token)
