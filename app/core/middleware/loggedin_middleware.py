"""
Cookie `user_data`: pistas para pintar la interfaz.

**No es una fuente de autorización.** El navegador puede editarla, así que el
backend recalcula permisos contra la base en cada petición
(`require_permissions`). Lo que hay aquí sirve para que el sidebar sepa qué
mostrar y la pantalla sepa a quién saluda — nada más.

La sesión NO se vuelve a resolver aquí: `AuthMiddleware` ya dejó el usuario y su
pertenencia en `request.state`. Antes este middleware corría **por delante** de
la autenticación y repetía por su cuenta la búsqueda del usuario, así que cada
petición —incluida la de cada archivo estático— costaba tres consultas
adicionales (AUD-BE-026).
"""

import json
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.security.cookies import USER_DATA_COOKIE_NAME, set_context_cookie
from app.routers_api.users.permissions import get_user_permissions, get_user_role_names


class LoggedinMiddleware(BaseHTTPMiddleware):
    @staticmethod
    def _is_static(path: str) -> bool:
        """Mismos caminos que ignora `AuthMiddleware`.

        Tiene que ser la misma lista: `AuthMiddleware` no resuelve la sesion
        para los estaticos, asi que aqui llegaban SIN usuario y el `else` de
        abajo borraba la cookie. La pagina la ponia y el primer `main.js` la
        quitaba, de modo que el navegador acababa sin contexto de usuario: sin
        barra lateral, sin nombre y sin permisos. El servidor respondia bien y
        ningun test de API lo veia.
        """
        return path.startswith("/static") or path == "/favicon.ico"

    async def dispatch(self, request, call_next):
        if self._is_static(request.url.path):
            return await call_next(request)

        user = getattr(request.state, "user", None)
        company = getattr(request.state, "company", None)

        user_data = None
        # Se dejan también en `request.state` para que las rutas de página
        # comprueben permisos sin volver a consultarlos.
        request.state.permissions = set()
        request.state.groups = []

        if user is not None and company is not None:
            permissions = sorted(
                await get_user_permissions(user_id=user.id, company_id=company.id)
            )
            groups = sorted(
                await get_user_role_names(user_id=user.id, company_id=company.id)
            )

            request.state.permissions = set(permissions)
            request.state.groups = groups

            user_data = {
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username,
                "email": user.email,
                "gender": user.gender,
                "permissions": permissions,
                "groups": groups,
                # Informativo para la interfaz. La autorización real de las
                # operaciones de plataforma la comprueba el backend.
                "is_superuser": user.is_superuser,
            }

        response: Response = await call_next(request)

        if user_data:
            # `quote(...)`, igual que `app_data`. El JSON en crudo lleva
            # comillas y comas, y Starlette entonces emite el valor como
            # cadena entrecomillada con barras invertidas:
            #
            #     user_data="{\"user_id\":1,\"first_name\":\"CER\"...}"
            #
            # La barra invertida no es un `cookie-octet` valido (RFC 6265), asi
            # que Chrome descarta la cookie entera. El efecto no era sutil: el
            # frontend se quedaba SIN contexto de usuario —sin barra lateral,
            # sin nombre y sin un solo permiso— y todo elemento condicionado por
            # `hasUserPermission` desaparecia. Se veia en el navegador y no lo
            # detectaba ningun typecheck.
            set_context_cookie(
                response,
                USER_DATA_COOKIE_NAME,
                quote(json.dumps(user_data, separators=(",", ":"))),
            )
        else:
            response.delete_cookie(USER_DATA_COOKIE_NAME, path="/")

        return response
