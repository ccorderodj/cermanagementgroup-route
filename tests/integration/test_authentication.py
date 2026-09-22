"""
Autenticación: quién entra, quién no, y qué se le cuenta al que no.

Cubre los dos fallos que la auditoría encontró en este flujo:

* el login no comprobaba **ninguna** de las dos banderas de actividad, así que
  "suspender el acceso" desde la pantalla de gestión no suspendía nada
  (AUD-BE-032);
* la respuesta distinguía "ese correo no existe" (404) de "contraseña
  incorrecta" (401), lo que convertía el formulario en un comprobador de
  cuentas (AUD-BE-006).
"""

import pytest

from tests.integration.conftest import TEST_PASSWORD


pytestmark = pytest.mark.integration


async def test_valid_login_sets_session_and_csrf_cookies(seeded, alpha_client):
    response = await alpha_client.login(seeded.alpha.users["owner"].email)

    assert response.status_code == 200
    assert response.json() == {"success": True}

    assert alpha_client.cookies.get("cer_access_token")
    assert alpha_client.cookies.get("cer_csrf_token")


async def test_login_does_not_return_the_token_in_the_body(seeded, alpha_client):
    """El token va solo en la cookie HttpOnly.

    Devolverlo también en el cuerpo anulaba el motivo de marcarla HttpOnly:
    cualquier XSS que alcanzara la respuesta del login se lo llevaba
    (AUD-SEC-017).
    """
    response = await alpha_client.login(seeded.alpha.users["owner"].email)

    body = response.text
    assert "access_token" not in body
    assert "eyJ" not in body  # cabecera de un JWT en base64


async def test_wrong_password_is_rejected(seeded, alpha_client):
    response = await alpha_client.login(
        seeded.alpha.users["owner"].email,
        password="not-the-password",
    )
    assert response.status_code == 401


async def test_unknown_email_and_wrong_password_are_indistinguishable(seeded, alpha_client):
    """Mismo código y mismo mensaje: el endpoint no confirma qué cuentas existen."""
    unknown = await alpha_client.login("nobody@alpha.example.com")
    wrong = await alpha_client.login(
        seeded.alpha.users["owner"].email,
        password="not-the-password",
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


async def test_user_disabled_on_the_platform_cannot_log_in(seeded, alpha_client):
    """`Users.is_active = False` cierra el acceso a toda la plataforma (D7)."""
    response = await alpha_client.login(seeded.alpha.users["disabled"].email)

    assert response.status_code == 401
    assert not alpha_client.cookies.get("cer_access_token")


async def test_suspended_membership_cannot_log_in_to_that_tenant(seeded, alpha_client):
    """`UserCompany.is_active = False` cierra el acceso a ESA compañía.

    Es el caso que la pantalla de gestión ofrece como "suspender acceso" y que
    antes no tenía ningún efecto.
    """
    response = await alpha_client.login(seeded.alpha.users["suspended"].email)

    assert response.status_code == 401
    assert not alpha_client.cookies.get("cer_access_token")


async def test_a_user_of_another_company_cannot_log_in_here(seeded, alpha_client):
    """Las credenciales de beta no sirven en alpha aunque sean válidas."""
    response = await alpha_client.login(seeded.beta.users["owner"].email)
    assert response.status_code == 401


async def test_authenticated_request_reaches_the_api(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/api/auth/profile")
    assert response.status_code == 200
    assert response.json()["email"] == seeded.alpha.users["owner"].email


async def test_request_without_session_is_rejected(seeded, alpha_client):
    response = await alpha_client.get("/api/auth/profile")
    assert response.status_code == 401


async def test_invalid_signature_is_rejected(seeded, alpha_client):
    """Un token firmado con otra clave no vale.

    Es el escenario del hallazgo crítico: mientras `SECRET_KEY` fue un
    placeholder publicado, cualquiera podía producir una firma válida.
    """
    alpha_client.cookies.set(
        "cer_access_token",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjo0MTAyNDQ0ODAwfQ.forged",
        domain="alpha.localhost",
    )

    response = await alpha_client.get("/api/auth/profile")
    assert response.status_code == 401


async def test_expired_token_is_rejected(seeded, alpha_client, monkeypatch):
    from app.config import settings
    from app.routers_api.users.auth import create_access_token

    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
    expired = create_access_token({"sub": str(seeded.alpha.users["owner"].id)})

    alpha_client.cookies.set("cer_access_token", expired, domain="alpha.localhost")

    response = await alpha_client.get("/api/auth/profile")
    assert response.status_code == 401


async def test_logout_clears_the_session(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    assert (await alpha_client.get("/api/auth/profile")).status_code == 200

    await alpha_client.post("/api/public/auth/logout")

    assert (await alpha_client.get("/api/auth/profile")).status_code == 401


async def test_legacy_pbkdf2_hash_is_upgraded_to_argon2_on_login(seeded, alpha_client):
    """Migración transparente del esquema de hash (D9).

    Un usuario cuya contraseña sigue guardada con el PBKDF2 heredado entra con
    normalidad, y al hacerlo su hash queda reescrito en Argon2id. Nadie tiene
    que cambiar de contraseña.
    """
    from passlib.context import CryptContext
    from sqlalchemy import select, update

    from app.database import async_session_maker
    from app.routers_api.users.models import Users

    legacy_context = CryptContext(schemes=["django_pbkdf2_sha256"])
    user = seeded.alpha.users["manager"]

    async with async_session_maker() as session:
        await session.execute(
            update(Users)
            .where(Users.id == user.id)
            .values(password=legacy_context.hash(TEST_PASSWORD))
        )
        await session.commit()

        stored = await session.scalar(select(Users.password).where(Users.id == user.id))
        assert stored.startswith("pbkdf2_sha256$")

    response = await alpha_client.login(user.email)
    assert response.status_code == 200

    async with async_session_maker() as session:
        stored = await session.scalar(select(Users.password).where(Users.id == user.id))

    assert stored.startswith("$argon2id$"), (
        "El hash legacy debería haberse reescrito en Argon2id al iniciar sesión."
    )


async def test_last_login_is_recorded(seeded, alpha_client):
    """`last_login` existía y no se escribía nunca (AUD-BE-031)."""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.routers_api.users.models import Users

    user = seeded.alpha.users["viewer"]

    async with async_session_maker() as session:
        before = await session.scalar(select(Users.last_login).where(Users.id == user.id))
    assert before is None

    await alpha_client.login(user.email)

    async with async_session_maker() as session:
        after = await session.scalar(select(Users.last_login).where(Users.id == user.id))
    assert after is not None


async def test_the_context_cookies_are_readable_by_a_browser(seeded, alpha_client):
    """`user_data` y `app_data` deben viajar en caracteres validos de cookie.

    El JSON en crudo lleva comillas y comas, y Starlette lo emite entonces como
    cadena entrecomillada con barras invertidas (`\054`). La barra invertida no
    es un `cookie-octet` valido (RFC 6265) y Chrome **descarta la cookie
    entera**: el frontend se quedaba sin barra lateral, sin nombre de usuario y
    sin un solo permiso, y ningun typecheck ni test de API lo notaba porque el
    servidor respondia perfectamente.

    Se comprueba sobre la cabecera `set-cookie` en bruto, que es lo que ve el
    navegador, y no sobre el valor ya normalizado por el cliente HTTP.
    """
    from urllib.parse import unquote

    await alpha_client.login(seeded.alpha.users["owner"].email)
    response = await alpha_client.get("/admin/security/users/list")

    cabeceras = [
        value for key, value in response.headers.multi_items()
        if key.lower() == "set-cookie"
    ]
    contexto = [h for h in cabeceras if h.startswith(("user_data=", "app_data="))]
    assert contexto, "La respuesta no trae las cookies de contexto."

    for cabecera in contexto:
        nombre, _, resto = cabecera.partition("=")
        valor = resto.split(";")[0]
        assert "\\" not in valor, (
            f"La cookie {nombre} lleva barras invertidas: el navegador la "
            f"descarta y la interfaz se queda sin contexto. {valor[:80]}"
        )
        assert '"' not in valor.strip('"'), (
            f"La cookie {nombre} lleva comillas dentro del valor: {valor[:80]}"
        )

    user_data = next(h for h in contexto if h.startswith("user_data="))
    valor = user_data.partition("=")[2].split(";")[0].strip('"')
    import json as _json

    datos = _json.loads(unquote(valor))
    assert datos["email"] == seeded.alpha.users["owner"].email
    assert isinstance(datos["permissions"], list) and datos["permissions"], (
        "El propietario deberia llegar con sus capacidades para que la interfaz "
        "sepa que pintar."
    )


async def test_an_exempt_path_never_overwrites_app_data_with_an_empty_company(
    seeded, alpha_client,
):
    """El navegador pide `/favicon.ico` solo, sin que la SPA lo sepa.

    `CompanyResolverMiddleware` exime esa ruta a propósito -- no hay tenant que
    resolver para un icono que es igual para todos. Si esa respuesta también
    escribiera `app_data`, ganaría la que el navegador procese al final: a
    veces la página real, a veces esta, vacía -- el nombre y el logo de la
    compañía desaparecían al azar. Esta ruta no debe traer la cookie en
    absoluto, para que nunca pueda pisar la que sí trae una página real.
    """
    respuesta = await alpha_client.get("/favicon.ico")

    cabeceras = [
        value for key, value in respuesta.headers.multi_items()
        if key.lower() == "set-cookie"
    ]
    assert not [h for h in cabeceras if h.startswith("app_data=")], (
        "Una ruta sin compañía no debe escribir app_data: pisaría la cookie "
        "de la página real con una compañía vacía."
    )


async def test_a_static_asset_does_not_delete_the_user_context(seeded, alpha_client):
    """Cargar `main.js` no puede dejar al usuario sin contexto.

    `AuthMiddleware` no resuelve la sesion para `/static`, asi que esas
    peticiones llegaban a `LoggedinMiddleware` sin usuario y su rama `else`
    borraba `user_data`. La pagina la ponia y el primer asset la quitaba: la
    interfaz se quedaba sin barra lateral y sin permisos aunque la sesion fuera
    perfectamente valida.
    """
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/static/javascript/css/main.css")
    borrados = [
        value for key, value in response.headers.multi_items()
        if key.lower() == "set-cookie" and value.startswith("user_data=")
    ]

    assert not borrados, (
        "Una respuesta de /static toca la cookie `user_data`. Si la borra, la "
        f"interfaz pierde el contexto del usuario: {borrados}"
    )
