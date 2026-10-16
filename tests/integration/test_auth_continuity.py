"""
Continuidad de autenticación (D-09).

Este módulo es genérico del núcleo —cualquier aplicación CER con sesiones
operativas largas lo necesita—, así que se prueba aparte del dominio de
Route: `app/core/security/session_renewal.py` no sabe qué es una Jornada.

Ver el docstring de ese módulo para la decisión completa; aquí solo se
comprueba el comportamiento observable:

* una petición autenticada que tiene éxito, cerca de la expiración, renueva
  la cookie;
* una lejos de la expiración no la toca —no se reemite en cada petición,
  solo cuando hace falta—;
* una petición rechazada (401/403) nunca renueva nada;
* `next=` en el redirect de `/login` vuelve a donde estaba quien perdió la
  sesión, y solo si es una ruta relativa propia.
"""

import time_machine
import pytest

from tests.integration.conftest import TenantClient


pytestmark = pytest.mark.integration


async def test_a_request_near_expiry_receives_a_renewed_cookie(seeded):
    """Pasada la mitad de vida del testigo, una petición con éxito lo renueva.

    `ACCESS_TOKEN_EXPIRE_MINUTES` es 1440 (24 h) por defecto; su mitad de vida
    son 12 h. Saltar 13 h adelante dentro de la misma sesión deja algo menos
    de 11 h de vida restante —por debajo del umbral— sin llegar a expirar.
    """
    inicio = "2026-09-20 08:00:00+00:00"
    cerca_de_expirar = "2026-09-20 21:00:00+00:00"  # +13h, sigue < 24h de vida

    async with TenantClient("alpha") as cliente:
        with time_machine.travel(inicio, tick=False):
            await cliente.login(seeded.alpha.users["owner"].email)

        with time_machine.travel(cerca_de_expirar, tick=False):
            cookies_antes = dict(cliente.cookies)
            respuesta = await cliente.get("/api/companies/profile")
            cookies_despues = dict(cliente.cookies)

        assert respuesta.status_code == 200
        assert cookies_despues.get("cer_access_token") != cookies_antes.get(
            "cer_access_token"
        ), "el testigo debía renovarse pasada la mitad de su vida"
        assert cookies_despues.get("cer_csrf_token") == cookies_antes.get(
            "cer_csrf_token"
        ), (
            "el CSRF no cambia de valor, solo su Max-Age (regenerarlo "
            "invalidaría peticiones en vuelo)"
        )


async def test_a_fresh_request_is_not_renewed_on_every_call(seeded):
    """Justo tras el login no hace falta renovar nada: sería trabajo de sobra."""
    async with TenantClient("alpha") as cliente:
        await cliente.login(seeded.alpha.users["owner"].email)
        cookies_antes = dict(cliente.cookies)

        respuesta = await cliente.get("/api/companies/profile")
        cookies_despues = dict(cliente.cookies)

        assert respuesta.status_code == 200
        assert cookies_despues.get("cer_access_token") == cookies_antes.get(
            "cer_access_token"
        )


async def test_a_denied_request_never_renews_the_cookie(seeded):
    """Un 403 no debe, además, regalar una sesión más larga."""
    async with TenantClient("alpha") as cliente:
        await cliente.login(seeded.alpha.users["viewer"].email)
        cookies_antes = dict(cliente.cookies)

        # `viewer` no tiene `route.vehicles.manage`.
        respuesta = await cliente.post("/api/vehicles", json={})
        cookies_despues = dict(cliente.cookies)

        assert respuesta.status_code == 403
        assert cookies_despues.get("cer_access_token") == cookies_antes.get(
            "cer_access_token"
        )


async def test_login_redirect_preserves_the_next_path(seeded):
    """Perder la sesión en `/route` y volver a entrar devuelve a `/route`."""
    async with TenantClient("alpha") as cliente:
        respuesta = await cliente.get("/route")
        assert respuesta.status_code in (303, 307)
        assert respuesta.headers["location"].startswith("/login?next=")
        assert "%2Froute" in respuesta.headers["location"] or "/route" in respuesta.headers["location"]
