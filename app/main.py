"""
Composición de la aplicación.

Tres aplicaciones FastAPI anidadas, igual que antes — la arquitectura no se ha
tocado, se ha ordenado:

    app (raíz)          SecurityHeaders -> TrustedHost -> CORS -> GZip
                        -> CompanyResolver
     |-- /health        liveness / readiness, SIN resolver tenant
     |-- /metrics       Prometheus, SIN resolver tenant, opcional por config
     |-- /api           API JSON
     |    |-- api_router          privado, exige sesión
     |    +-- api_router_public   lista blanca de endpoints públicos
     +-- /              páginas HTML + estáticos

El orden de montaje (`/api` antes que `/`) es imprescindible: `Mount("")` captura
todo lo demás.

Sobre el orden de los middleware
--------------------------------
Starlette ejecuta en orden **inverso** al de registro: el último registrado es el
más externo. Aquí se registra al revés a propósito para que la ejecución quede
en el orden que se lee arriba.

Dos cosas que ese orden arregla:

* `AuthMiddleware` ahora corre **antes** que `LoggedinMiddleware` y deja el
  usuario resuelto en `request.state`, así que la sesión se carga una sola vez
  por petición en lugar de tres consultas por cada archivo estático
  (AUD-BE-026).
* `/health` y `/metrics` quedan fuera de `CompanyResolverMiddleware`: son
  infraestructura, y antes devolvían 404 si la petición no traía un subdominio
  de compañía válido — justo lo que hace un orquestador (D11, AUD-ARCH-003).
"""

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
import mimetypes

# Un módulo `.mjs` (p. ej. el worker de una librería JS) sólo arranca si se
# sirve como JavaScript. Python lo adivina según el sistema operativo (en
# Windows sale `text/plain`), así que se fija aquí.
mimetypes.add_type("text/javascript", ".mjs")
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.trustedhost import TrustedHostMiddleware
from asgi_correlation_id import CorrelationIdMiddleware

from app.core.audit.context import AuditRequestContextMiddleware

from app.config import settings
from app.core.exceptions import handler
from app.core.middleware import (
    app_middleware,
    auth_middleware,
    company_resolver_middleware,
    cors_middleware,
    exception_middleware,
    gzip_middleware,
    loggedin_middleware,
)
from app.core.middleware.security_headers_middleware import (
    SecurityHeadersMiddleware,
)
from app.core.middleware.query_performance_middleware import query_performance_middleware
from app.core.security.csrf import CsrfMiddleware
from app.core.security.session_renewal import SlidingSessionMiddleware
from app.logger import logger
from app.routers_api.api import api_router
from app.routers_api_public.api import api_router_public
from app.core.integration.router import router as integration_router_v1
from app.routers_health.router import router as health_router
from app.routers_pages.page import page_router


# ── Aplicación raíz ─────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_TITLE,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Registro en orden inverso al de ejecución (ver docstring).
app.add_middleware(company_resolver_middleware.CompanyResolverMiddleware)
gzip_middleware.add(app)
cors_middleware.add(app)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
# El mas externo: una respuesta sin cabeceras de seguridad es una respuesta
# sin cabeceras de seguridad tambien cuando es un 400 de TrustedHost.
app.add_middleware(SecurityHeadersMiddleware)
# Aún más externo: cada petición lleva un `X-Request-ID` desde que entra, y la
# traza de plataforma lo guarda para cruzar un cambio con el log del servidor.
# IP y user agent para la traza (WP-9). Por dentro del de `X-Request-ID`, así
# que cuando corre ya hay identificador de petición.
app.add_middleware(AuditRequestContextMiddleware)
app.add_middleware(CorrelationIdMiddleware)


# ── Configuración de plataforma (fase 12) ───────────────────────────────────
#
# Al arrancar se carga la instantánea de integraciones y políticas, y se escucha
# `NOTIFY platform_config_changed` para enterarse de lo que cambian las demás
# instancias. En TEST no: cada test escribe y refresca por su cuenta, y una
# escucha viva entre tests sería estado compartido.
_config_listener_stop = None


@app.on_event("startup")
async def _platform_config_startup() -> None:
    import asyncio

    from app.core.platform.config_service import listen_for_changes, platform_config

    global _config_listener_stop
    if settings.is_testing:
        return
    try:
        await platform_config.refresh()
    except Exception:
        logger.warning("PLATFORM | could not load platform configuration at startup", exc_info=True)
    _config_listener_stop = asyncio.Event()
    asyncio.get_running_loop().create_task(listen_for_changes(_config_listener_stop))
    if settings.PLATFORM_SCHEDULER_ENABLED:
        from app.core.platform.scheduler import platform_scheduler
        from app.routers_api.mileage.jobs import register_route_jobs

        # Antes de arrancar: `register` solo se lee en `start()`.
        register_route_jobs()
        await platform_scheduler.start()


@app.on_event("startup")
async def _odometer_ocr_startup() -> None:
    """Enchufa el lector de odómetro, si hay uno que enchufar (RTE10-A01 FR-01).

    Se decide por **presencia del binario**, no por configuración: una imagen
    sin el paquete de sistema se queda con `NoSuggestionReader` y se comporta
    exactamente igual que antes de este checkpoint, que es lo que mantiene
    verde la línea base certificada. Anunciar un OCR que no está instalado sólo
    produciría un fallo por foto.

    En TEST no se enchufa nada a propósito. La suite registra su propio
    adaptador con `set_odometer_reader` cuando quiere probar una sugerencia
    concreta, y un Tesseract real en la máquina de quien ejecuta los tests haría
    que el resultado dependiera de qué tiene instalado.
    """
    from app.routers_api.odometer.ocr import set_odometer_reader
    from app.routers_api.odometer.ocr_tesseract import (
        TesseractReader,
        tesseract_disponible,
    )

    if settings.is_testing or not settings.ODOMETER_OCR_ENABLED:
        return

    binario = settings.ODOMETER_OCR_BINARY
    if not tesseract_disponible(binario):
        logger.info(
            "ODOMETER OCR | '%s' no está instalado; sin sugerencias y el "
            "supervisor teclea la lectura, que es el camino normal",
            binario,
        )
        return

    set_odometer_reader(
        TesseractReader(
            binary=binario,
            timeout_seconds=settings.ODOMETER_OCR_TIMEOUT_SECONDS,
        )
    )
    logger.info("ODOMETER OCR | lector activo: tesseract (%s)", binario)


@app.on_event("shutdown")
async def _platform_config_shutdown() -> None:
    if _config_listener_stop is not None:
        _config_listener_stop.set()
    if settings.PLATFORM_SCHEDULER_ENABLED and not settings.is_testing:
        from app.core.platform.scheduler import platform_scheduler

        await platform_scheduler.shutdown()


# Infraestructura: no depende del tenant.
app.include_router(health_router)

if settings.ENABLE_METRICS:

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── Aplicación de páginas ───────────────────────────────────────────────────

frontend = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

gzip_middleware.add(frontend)
frontend.add_middleware(app_middleware.AppMiddleware)
frontend.add_middleware(loggedin_middleware.LoggedinMiddleware)
frontend.add_middleware(auth_middleware.AuthMiddleware)

frontend.include_router(page_router)
frontend.mount("/static", StaticFiles(directory="app/static"), "static")
handler.register_page_error_handlers(frontend)


# ── Aplicación de API ───────────────────────────────────────────────────────
#
# La documentación OpenAPI describe toda la superficie de la API. Se publica
# sola en DEV; en TEST y PROD hay que pedirla con ENABLE_API_DOCS (D4).
#
# `redoc_url` era "/docs", el mismo valor que `docs_url`: se registraban dos
# rutas con el mismo path y ReDoc quedaba inalcanzable (AUD-BE-004).
api = FastAPI(
    title=f"{settings.APP_NAME} API",
    description=(
        f"API de {settings.APP_TITLE}. `/api/<módulo>` es la API interna de la "
        "interfaz; `/api/v1/...` es la API versionada entre aplicaciones "
        "(ver docs/INTEGRATION_GUIDE.md)."
    ),
    root_path="/api",
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

gzip_middleware.add(api)
api.add_middleware(CsrfMiddleware)
api.add_middleware(exception_middleware.ExceptionMiddleware)
# Sesión deslizante (D-09): ver app/core/security/session_renewal.py.
api.add_middleware(SlidingSessionMiddleware)
api.middleware("http")(query_performance_middleware)

handler.register_api_error_handlers(api)
api.include_router(api_router)
api.include_router(api_router_public)
# La API versionada entre aplicaciones (`/api/v1`). Sin sesión de usuario: cada
# endpoint trae su autenticación (firma HMAC), ver `app/core/integration/router.py`.
api.include_router(integration_router_v1)


# `/api` antes que `/`: el segundo captura todo lo que no case con el primero.
app.mount("/api", app=api)
app.mount("/", app=frontend)


logger.info(
    "APP | mode=%s docs=%s metrics=%s base_domain=%s",
    settings.MODE,
    settings.docs_enabled,
    settings.ENABLE_METRICS,
    settings.BASE_DOMAIN,
)
