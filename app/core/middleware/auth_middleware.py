"""
Sesión de las páginas HTML.

Además de decidir quién pasa, **resuelve la sesión una sola vez** y la deja en
`request.state` para que el resto de la cadena la reutilice. Antes había tres
implementaciones distintas de la validación del token —esta, la de
`BaseMiddleware` y la de la dependencia de API— cada una con su propio manejo de
errores: un token manipulado se le reportaba al usuario como "expirado"
(AUD-BE-033).

Comprobaciones que faltaban y ahora se hacen (D7, AUD-SEC-018):

* que el usuario **exista** — un token firmado para un id borrado daba acceso al
  HTML de todas las pantallas de administración;
* que su identidad de plataforma esté **activa**;
* que su pertenencia a la compañía del subdominio esté **activa**.

Los archivos estáticos salen por la puerta rápida antes de tocar la base.
"""

from urllib.parse import quote

from fastapi import status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.security.cookies import ACCESS_COOKIE_NAME, clear_session_cookies
from app.exceptions import AuthenticationError
from app.routers_api.users.dao import UsersDAO
from app.routers_api.users.dependencies import decode_access_token


class AuthMiddleware(BaseHTTPMiddleware):
    """Puerta de las páginas."""

    PUBLIC_PATHS = frozenset(
        {
            "/login",
            "/password-reset",
            "/change-password",
        }
    )

    #: Como `PUBLIC_PATHS`, para rutas con identificador en el path. Una
    #: aplicación que publique páginas anónimas con id las declara aquí.
    PUBLIC_PATH_PREFIXES: tuple[str, ...] = ()

    # Estando dentro, estas rutas no tienen sentido: llevan al panel.
    AUTHENTICATED_REDIRECT_PATHS = frozenset(
        {
            "/",
            "/login",
            "/password-reset",
            "/change-password",
        }
    )

    @staticmethod
    def _is_static(path: str) -> bool:
        return path.startswith("/static") or path == "/favicon.ico"

    async def dispatch(self, request, call_next):
        path = request.url.path

        # Salida rápida: un asset no necesita sesión ni consulta a la base.
        # Que esto estuviera después de la carga de sesión costaba tres
        # consultas por archivo (AUD-BE-026).
        if self._is_static(path):
            request.state.user = None
            request.state.membership = None
            return await call_next(request)

        request.state.user = None
        request.state.membership = None

        token = request.cookies.get(ACCESS_COOKIE_NAME)

        if not token:
            if path in self.PUBLIC_PATHS or path.startswith(self.PUBLIC_PATH_PREFIXES):
                return await call_next(request)
            return self._redirect_to_login(next_path=path)

        user, membership = await self._load_session(request, token)

        if user is None:
            # Token inválido, expirado, de un usuario borrado o desactivado, o
            # de alguien sin pertenencia activa a esta compañía. Todos acaban en
            # el mismo sitio: fuera, y con las cookies limpias.
            if path in self.PUBLIC_PATHS:
                response = await call_next(request)
                clear_session_cookies(response)
                return response
            return self._redirect_to_login(clear_cookies=True, next_path=path)

        request.state.user = user
        request.state.membership = membership

        if path in self.AUTHENTICATED_REDIRECT_PATHS:
            return RedirectResponse(
                url=settings.DEFAULT_AUTHENTICATED_PATH,
                status_code=status.HTTP_303_SEE_OTHER,
            )

        return await call_next(request)

    @staticmethod
    async def _load_session(request, token: str):
        try:
            payload = decode_access_token(token)
        except AuthenticationError:
            return None, None

        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            return None, None

        user = await UsersDAO.find_active_by_id(user_id)
        if user is None:
            return None, None

        company = getattr(request.state, "company", None)
        if company is None:
            return user, None

        membership = await UsersDAO.find_active_membership(
            user_id=user.id,
            company_id=company.id,
        )
        if membership is None:
            # Identidad válida, pero sin acceso a este tenant.
            return None, None

        return user, membership

    @staticmethod
    def _redirect_to_login(clear_cookies: bool = False, next_path: str | None = None):
        """Vuelve a `/login`, recordando adónde iba quien perdió la sesión.

        `next_path` es una ruta relativa de esta misma aplicación —nunca una
        URL absoluta—, así que no hay redirección abierta que explotar: se
        construye aquí a partir de `request.url.path`, no de un valor que
        llegue del cliente.
        """
        url = "/login"
        if next_path and next_path not in AuthMiddleware.PUBLIC_PATHS:
            url = f"/login?next={quote(next_path, safe='')}"

        response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
        if clear_cookies:
            clear_session_cookies(response)
        return response
