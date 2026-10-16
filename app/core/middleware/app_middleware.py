"""
Cookie `app_data` y emisión del testigo CSRF.

`app_data` lleva la identidad visual del tenant —nombre, logo, colores de
marca— para que la interfaz pueda pintarse sin una llamada extra. Es una pista,
no una autorización.

Aquí también se emite el testigo **CSRF**, y este es el sitio correcto: toda
sesión empieza cargando una página, así que al llegar a la primera petición
mutante de la API el navegador ya tiene la cookie que Axios copiará en la
cabecera `X-CSRF-Token`. Si ya hay una, se respeta: regenerarla en cada
respuesta invalidaría las peticiones en vuelo.

Nunca se pisa `app_data` con una compañía vacía
-------------------------------------------------
`request.state.company` es `None` en las rutas que `CompanyResolverMiddleware`
exime (`/favicon.ico`, `/health`, `/metrics`) — no hay tenant que resolver para
ellas. El navegador pide `/favicon.ico` solo, sin que la SPA lo sepa ni lo
espere, en cualquier momento después de cargar una página real. Si esa
respuesta también escribiera `app_data`, ganaría la que el navegador procese
al final: a veces la página real, a veces el favicon vacío — una carrera que
se traducía en el nombre y el logo de la compañía desapareciendo al azar, sin
ningún error visible. La cookie sólo se escribe cuando de verdad hay una
compañía que describir.
"""

import json
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.core.security.cookies import (
    APP_DATA_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    set_context_cookie,
    set_csrf_cookie,
)
from app.core.identity import app_identity
from app.core.security.csrf import generate_csrf_token


class AppMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        company = getattr(request.state, "company", None)

        app_data = {
            **app_identity(),
            "mode": settings.MODE,
            "company_id": getattr(company, "id", None),
            "company_name": getattr(company, "name", None),
            "subdomain": getattr(request.state, "subdomain", None),
            "address": getattr(company, "address", None),
            "email": getattr(company, "email", None),
            "phone_secondary": getattr(company, "phone_secondary", None),
            "website": getattr(company, "website", None),
            "logo_url": getattr(company, "logo_url", None),
            "brand_primary_color": getattr(company, "brand_primary_color", None),
            "brand_secondary_color": getattr(company, "brand_secondary_color", None),
            "pdf_text_color": getattr(company, "pdf_text_color", None),
            "pdf_muted_text_color": getattr(company, "pdf_muted_text_color", None),
            "pdf_surface_color": getattr(company, "pdf_surface_color", None),
        }

        request.state.app_data = app_data

        response: Response = await call_next(request)

        if company is not None:
            set_context_cookie(
                response,
                APP_DATA_COOKIE_NAME,
                quote(json.dumps(app_data)),
            )

        if not request.cookies.get(CSRF_COOKIE_NAME):
            set_csrf_cookie(response, generate_csrf_token())

        return response
