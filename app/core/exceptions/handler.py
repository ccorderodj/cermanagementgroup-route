"""
Handlers de error por aplicación.

Las páginas y la API fallan de formas distintas y deben contestar distinto: una
pantalla necesita HTML que el navegador sepa mostrar; una llamada de Axios
necesita JSON con la misma forma que el resto de la API.

`403` en páginas se renderiza como una pantalla de acceso denegado en lugar de
un cuerpo vacío: es lo que ve un usuario que llega por URL directa a una
pantalla para la que no tiene permiso (D25 del encargo, AUD-BE-001).
"""

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.utils.web_routers import CustomTemplates


_templates = CustomTemplates(directory="app/templates")


def register_page_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(status.HTTP_404_NOT_FOUND)
    async def not_found(request: Request, exc: Exception):
        return _render("404.html", request, status.HTTP_404_NOT_FOUND)

    @app.exception_handler(status.HTTP_403_FORBIDDEN)
    async def forbidden(request: Request, exc: Exception):
        detail = getattr(exc, "detail", None)
        return _render(
            "403.html",
            request,
            status.HTTP_403_FORBIDDEN,
            detail=detail if isinstance(detail, str) else None,
        )


def register_api_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def api_http_exception(request: Request, exc: StarletteHTTPException):
        # Un 401 sobre una navegación HTML no debe devolver el cuerpo JSON: el
        # navegador lo mostraría como texto plano en la pantalla.
        if (
            exc.status_code == status.HTTP_401_UNAUTHORIZED
            and "text/html" in request.headers.get("accept", "")
        ):
            return JSONResponse(status_code=exc.status_code, content=None)

        return await http_exception_handler(request, exc)


def _render(
    template_name: str,
    request: Request,
    status_code: int,
    detail: str | None = None,
) -> HTMLResponse:
    template = _templates.get_template(template_name)
    content = template.render(request=request, detail=detail, url_name=None)
    return HTMLResponse(content=content, status_code=status_code)
