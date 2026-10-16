"""
Resolución del tenant a partir del subdominio.

    cer.localhost:8000  ->  subdomain "cer"  ->  company_id 1

El tenant sale de la cabecera `Host`, nunca de un parámetro que envíe el
cliente. Esa decisión estaba bien y se conserva.

Tres cambios respecto a la versión anterior:

* **Rutas de infraestructura exentas.** `/health` y `/metrics` ya no pasan por
  aquí: son sondas de un orquestador, que no conoce ningún subdominio y recibía
  404 (D11, AUD-ARCH-003).
* **Caché de resolución.** Antes se consultaba `company` en cada petición,
  archivos estáticos incluidos (AUD-BE-013). Ahora hay una caché con vencimiento
  corto e invalidación explícita cuando cambia el perfil de una compañía.
* **El 404 no refleja lo recibido.** El mensaje ya no incrusta el subdominio que
  vino en la cabecera (AUD-SEC-022).

Lo que la caché NO guarda: nada de permisos ni de roles. Cachear autorización es
como se producen los privilegios obsoletos; aquí solo se guarda la identidad del
tenant, que cambia cuando alguien edita el perfil y se invalida ahí mismo.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.config import settings
from app.logger import logger
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dao import CompaniesDAO


# Rutas que no pertenecen a ninguna compañía.
EXEMPT_PATHS = frozenset({"/health", "/health/ready", "/metrics", "/favicon.ico"})

# Los archivos estáticos son los mismos para todos los tenants: resolver la
# compañía para servir un .js es una consulta a la base por cada asset de cada
# carga de página.
EXEMPT_PREFIXES = ("/static/",)

CACHE_TTL_SECONDS = 60

_cache: dict[str, tuple[float, TenantContext]] = {}


def invalidate_tenant_cache(subdomain: str | None = None) -> None:
    """Olvida lo cacheado. Se llama al cambiar el perfil de una compañía."""
    if subdomain is None:
        _cache.clear()
        return
    _cache.pop(subdomain.strip().lower(), None)


async def _resolve(subdomain: str) -> TenantContext | None:
    cached = _cache.get(subdomain)
    if cached is not None:
        expires_at, tenant = cached
        if expires_at > time.monotonic():
            return tenant
        _cache.pop(subdomain, None)

    row = await CompaniesDAO.find_by_subdomain(subdomain)
    if row is None:
        return None

    tenant = TenantContext.from_row(row)
    _cache[subdomain] = (time.monotonic() + CACHE_TTL_SECONDS, tenant)
    return tenant


class CompanyResolverMiddleware(BaseHTTPMiddleware):
    BASE_DOMAIN = settings.BASE_DOMAIN

    def normalize_host(self, host: str) -> str:
        return (host or "").split(":")[0].lower().strip()

    def extract_subdomain(self, host: str) -> str | None:
        host = self.normalize_host(host)
        suffix = "." + self.BASE_DOMAIN
        if host.endswith(suffix):
            sub = host[: -len(suffix)]
            return sub or None
        return None

    @staticmethod
    def _is_exempt(path: str) -> bool:
        return path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES)

    async def dispatch(self, request: Request, call_next):
        if self._is_exempt(request.url.path):
            request.state.subdomain = None
            request.state.company = None
            return await call_next(request)

        subdomain = self.extract_subdomain(request.headers.get("host", ""))

        request.state.subdomain = subdomain
        request.state.company = None

        if not subdomain:
            logger.warning("TENANT | peticion sin subdominio path=%s", request.url.path)
            return self._not_found(
                "The company subdomain is required to reach this application."
            )

        tenant = await _resolve(subdomain)
        if tenant is None:
            logger.warning("TENANT | subdominio desconocido")
            return self._not_found("This company does not exist.")

        request.state.company = tenant
        return await call_next(request)

    @staticmethod
    def _not_found(message: str) -> HTMLResponse:
        # Sin interpolar nada de la petición: el subdominio llega en una
        # cabecera que el cliente controla.
        return HTMLResponse(
            status_code=404,
            content=(
                "<!doctype html><html><head><title>Company not found</title></head>"
                "<body><h2>Company not found</h2>"
                f"<p>{message}</p></body></html>"
            ),
        )
