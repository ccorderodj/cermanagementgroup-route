"""
El patron server-route + page-key.

`CheckNameRoute` copia el `name=` de la ruta FastAPI a `request.state.url_name`,
y `CustomTemplates` lo inyecta en el contexto de Jinja para que la plantilla lo
imprima en `data-current-page`. Ese valor es lo que React usa para decidir que
componente montar.

La cadena tiene que decir lo mismo en cuatro sitios —ruta, enum `ComponentRoot`,
`RootComponents` y plantilla— o la pagina sale en blanco sin lanzar ningun error.
Como ese fallo es silencioso, hay un test que compara las cuatro fuentes:
`tests/test_page_wiring.py`.
"""

from typing import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates

from app.core.identity import app_identity
from app.logger import logger


class CheckNameRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            route = request.scope.get("route")
            url_name = getattr(route, "name", None) if route else None

            request.state.url_name = url_name

            if url_name is None:
                # Sin nombre de ruta no hay page-key, y React no monta nada.
                logger.warning(
                    "PAGE | ruta sin name= path=%s: la pagina saldra vacia",
                    request.url.path,
                )

            return await original_route_handler(request)

        return custom_route_handler


class CustomTemplates(Jinja2Templates):
    """Plantillas con `app` (identidad del proyecto) disponible en todas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env.globals["app"] = app_identity()

    def TemplateResponse(
        self,
        *,
        request: Request,
        name: str,
        context: dict | None = None,
        **kwargs,
    ):
        context = context or {}
        context["url_name"] = getattr(request.state, "url_name", None)
        return super().TemplateResponse(
            request=request,
            name=name,
            context=context,
            **kwargs,
        )
