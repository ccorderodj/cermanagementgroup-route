"""
API versionada entre aplicaciones: `/api/v1/...`.

Convención (ver `docs/INTEGRATION_GUIDE.md`):

* `/api/<módulo>/...` es la API **interna** de la propia interfaz. Puede cambiar
  con la interfaz, porque se despliegan juntas.
* `/api/v1/...` es el **contrato** con otras aplicaciones. No se rompe: un
  cambio incompatible es `/api/v2`, y las dos conviven mientras las
  contrapartes migran.

Aquí no hay sesión de usuario. La autenticación de cada endpoint es propia
—firma HMAC del webhook— y está en el endpoint, no en el router: por eso este
router se monta aparte del privado y del público, y `tests/test_public_surface.py`
lo enumera.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.integration.webhooks import InboundRejected, receive_inbound
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required

API_VERSION = "v1"

router = APIRouter(prefix=f"/{API_VERSION}", tags=["Integration API v1"])

#: Rutas de este router autenticadas por firma y no por cookie. El middleware
#: CSRF las exime por prefijo: una contraparte servidor-a-servidor no tiene
#: cookie ni testigo CSRF, y su firma ya prueba el origen.
SIGNATURE_AUTHENTICATED_PREFIXES: tuple[str, ...] = ("/v1/webhooks/inbound/",)


@router.get("/meta", name="integration_meta")
async def integration_meta(
    current_company: TenantContext = Depends(get_company_required),
) -> dict:
    """Quién soy y qué versión del contrato hablo. Sin datos del tenant."""
    return {
        "app_name": settings.APP_NAME,
        "api_version": API_VERSION,
        "tenant": current_company.subdomain,
    }


@router.post("/webhooks/inbound/{public_id}", name="webhook_inbound", status_code=202)
async def webhook_inbound(
    request: Request,
    public_id: str = Path(..., min_length=4, max_length=40),
    current_company: TenantContext = Depends(get_company_required),
) -> JSONResponse:
    body = await request.body()
    try:
        resultado = await receive_inbound(
            company_id=current_company.id,
            public_id=public_id,
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
    except InboundRejected as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=202,
        content={"status": resultado.status, "event_id": resultado.event_id},
    )
