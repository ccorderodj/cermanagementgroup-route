"""
Continuidad de sesión para operaciones largas (D-09).

El problema que resuelve
-------------------------
`cer_access_token` dura `ACCESS_TOKEN_EXPIRE_MINUTES` (24 h por defecto) desde
el login, sin renovación: es el único mecanismo de expiración del sistema, y
así se queda —ver `app/routers_api/users/auth.py`—. Eso basta para el uso de
oficina, pero CER Route introduce sesiones operativas largas: una Jornada
(Work Session) puede seguir `ACTIVE` doce horas o más, y un supervisor que la
empezó a las 7 de la mañana no puede encontrarse expulsado a mitad de tarde
solo porque el reloj del token, no su trabajo, llegó a las 24 horas.

La decisión (D-09)
-------------------
**Sesión deslizante, no un segundo token.** No se introduce un refresh token,
ni una lista de revocación, ni un segundo secreto. Se reutiliza exactamente lo
que ya existe —`create_access_token`, `set_access_cookie`, `decode_access_token`—
y lo único nuevo es *cuándo* se reemite: en cada petición autenticada que
responde con éxito, si al testigo le queda menos de la mitad de su vida útil,
se emite uno nuevo con la misma identidad y una expiración fresca.

Por qué esto y no un refresh token
-----------------------------------
Un refresh token añade superficie: un segundo secreto que proteger, un
mecanismo de revocación que mantener, y una ruta de ataque nueva si se hace
mal. Nada de eso es necesario para el requisito real —"un supervisor que
trabaja activamente no debe ver caducar su sesión"—, que la ventana deslizante
resuelve reutilizando el mismo esquema de firma y las mismas comprobaciones de
`get_current_user` en cada petición. La propiedad de seguridad no cambia: sigue
habiendo exactamente un motivo de salida (expiración), y sigue verificándose
`Users.is_active` / `UserCompany.is_active` contra la base en cada petición, sin
caché. Lo único que se mueve es el reloj desde el que se cuenta: de "desde el
login" a "desde la última actividad".

El límite, dicho con honestidad
---------------------------------
Un dispositivo inactivo más tiempo del que le queda a su testigo sí expira: es
la salida por inactividad, no un defecto. Es idéntica a la que ya existía —"la
expiración es la única salida"—, solo que ahora se mide desde la última
petición, no desde el login. Un supervisor que cierra la aplicación y no vuelve
a abrirla en 24 h tendrá que volver a entrar; su Jornada sigue en la base tal
cual la dejó y `GET /worksessions/current` la recupera en cuanto vuelve a
autenticarse (ver `app/routers_api/worksessions/router.py`).

El testigo CSRF viaja con la misma vida útil que el de acceso
----------------------------------------------------------------
`set_csrf_cookie` fija su `Max-Age` con la misma fórmula que la cookie de
acceso. Si solo se deslizara el testigo de acceso, el CSRF caducaría primero y
toda escritura empezaría a fallar con la sesión todavía viva. Por eso esta
renovación reemite **también** el `Max-Age` del CSRF —nunca su valor: cambiar
el valor invalidaría peticiones en curso, el mismo motivo por el que
`AppMiddleware` no lo regenera si ya existe—.
"""

from __future__ import annotations

from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.core.security.cookies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    set_access_cookie,
    set_csrf_cookie,
)
from app.exceptions import AuthenticationError
from app.routers_api.users.auth import create_access_token


def _debe_renovarse(payload: dict) -> bool:
    """Si al testigo le queda menos de la mitad de su vida útil."""
    expira = payload.get("exp")
    if not expira:
        return False

    restante = int(expira) - int(datetime.now(timezone.utc).timestamp())
    mitad_de_vida = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 / 2
    return restante < mitad_de_vida


class SlidingSessionMiddleware(BaseHTTPMiddleware):
    """Extiende la sesión de quien está trabajando activamente.

    Solo actúa sobre respuestas que ya tuvieron éxito (`< 400`): una petición
    rechazada por el testigo no debe, además, emitir uno nuevo. Un testigo
    ausente, manipulado o ya expirado se ignora en silencio — `get_current_user`
    ya lo habrá rechazado con 401 antes de que esto se ejecute, y no es este
    middleware quien decide autorización, solo continuidad.
    """

    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get(ACCESS_COOKIE_NAME)
        response: Response = await call_next(request)

        if not token or response.status_code >= 400:
            return response

        from app.routers_api.users.dependencies import decode_access_token

        try:
            payload = decode_access_token(token)
        except AuthenticationError:
            return response

        if not _debe_renovarse(payload):
            return response

        nuevo_token = create_access_token({"sub": payload["sub"]})
        set_access_cookie(response, nuevo_token)

        csrf_actual = request.cookies.get(CSRF_COOKIE_NAME)
        if csrf_actual:
            set_csrf_cookie(response, csrf_actual)

        return response
