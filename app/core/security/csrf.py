"""
Protección CSRF por doble envío (double-submit cookie).

Por qué hace falta
------------------
La sesión viaja en una cookie, así que el navegador la adjunta sola a cualquier
petición hacia este origen — incluida una lanzada desde otro sitio. `SameSite=lax`
frena la mayor parte de los casos, pero es una política del navegador, no un
control de la aplicación: no cubre navegadores antiguos ni subdominios hermanos,
y aquí **cada tenant es un subdominio del mismo dominio base**, que es justo
donde `lax` deja de aislar.

Lo que había antes no era protección
------------------------------------
El frontend enviaba `X-CSRFToken: window.csrfToken`, pero `window.csrfToken` no
se asignaba en ninguna plantilla, así que la cabecera iba siempre vacía; y el
backend no comprobaba ninguna cabecera. Era una fachada (AUD-SEC-021).

Cómo funciona ahora
-------------------
1. El servidor emite la cookie `cer_csrf_token` con un valor aleatorio, legible
   por JavaScript.
2. Axios lee esa cookie y la copia en la cabecera `X-CSRF-Token`.
3. Este middleware exige, en todo método que muta estado, que la cabecera exista
   y coincida con la cookie.

Un sitio de terceros puede provocar la petición, pero **no puede leer la cookie**
(política de mismo origen), así que no puede construir la cabecera. Falla cerrado:
si falta cualquiera de las dos partes, la petición se rechaza con 403.
"""

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security.cookies import CSRF_COOKIE_NAME


CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Valida el doble envío en los métodos que mutan estado.

    Se monta sobre la aplicación de API. Las páginas son de solo lectura (GET),
    así que no necesitan la comprobación.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)

        # Única exención: rutas servidor-a-servidor autenticadas por firma HMAC
        # (webhooks entrantes). No llevan cookie de sesión, así que el ataque
        # que el doble envío previene —usar la cookie de otro— no existe, y la
        # firma ya prueba el origen. La lista vive junto a esas rutas.
        from app.core.integration.router import SIGNATURE_AUTHENTICATED_PREFIXES

        ruta = request.scope.get("path", "")
        raiz = request.scope.get("root_path", "")
        if raiz and ruta.startswith(raiz):
            ruta = ruta[len(raiz):]
        if ruta.startswith(SIGNATURE_AUTHENTICATED_PREFIXES):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)

        if not cookie_token or not header_token:
            return self._rejected(
                "Missing CSRF token. The browser must send the "
                f"{CSRF_HEADER_NAME} header matching the {CSRF_COOKIE_NAME} cookie."
            )

        # Comparación en tiempo constante: el testigo es un secreto por sesión.
        if not secrets.compare_digest(cookie_token, header_token):
            return self._rejected("CSRF token mismatch.")

        return await call_next(request)

    @staticmethod
    def _rejected(detail: str) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": detail})
