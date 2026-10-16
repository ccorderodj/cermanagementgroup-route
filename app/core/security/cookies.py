"""
Cookies de sesión y de contexto.

Un único sitio donde se decide cómo se emiten, para que ninguna ruta pueda
olvidarse de `HttpOnly` o de `Secure`. Los atributos dependen del entorno:
`Secure` exige HTTPS, así que en desarrollo sobre `http://cer.localhost` no se
puede poner o el navegador descarta la cookie.

Cinco cookies, con cinco propósitos distintos:

* `cer_access_token`  el token de sesión del personal de CER. **HttpOnly**:
                      JavaScript no la ve.
* `cer_csrf_token`    el testigo CSRF. Legible por JS a propósito, porque Axios
                      tiene que copiarla a la cabecera `X-CSRF-Token`.
* `user_data` / `app_data`  pistas para pintar la interfaz. **Nunca** son
                      fuente de autorización: el backend recalcula permisos
                      contra la base en cada petición.
"""

from starlette.responses import Response

from app.config import settings


ACCESS_COOKIE_NAME = "cer_access_token"
CSRF_COOKIE_NAME = "cer_csrf_token"
USER_DATA_COOKIE_NAME = "user_data"
APP_DATA_COOKIE_NAME = "app_data"

# Las cookies de contexto caducan solas por si la sesión se pierde sin logout.
CONTEXT_COOKIE_MAX_AGE = 86400


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    """Testigo CSRF. `httponly=False` es intencionado: Axios debe leerlo."""
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def set_context_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=CONTEXT_COOKIE_MAX_AGE,
    )


def clear_session_cookies(response: Response) -> None:
    for name in (
        ACCESS_COOKIE_NAME,
        CSRF_COOKIE_NAME,
        USER_DATA_COOKIE_NAME,
        APP_DATA_COOKIE_NAME,
    ):
        response.delete_cookie(name, path="/")
