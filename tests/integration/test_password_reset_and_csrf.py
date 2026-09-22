"""
Recuperación de contraseña y protección CSRF.

Recuperación (D3)
-----------------
El flujo estaba muerto: el endpoint que emitía los tokens llevaba comentado
desde antes de la auditoría, mientras el que los consumía seguía publicado sin
autenticación. Reconstruido, se comprueban las cuatro propiedades que lo hacen
seguro: respuesta no enumerable, token que no se guarda en claro, caducidad y
un solo uso.

CSRF (AUD-SEC-021)
------------------
Antes era una fachada: el frontend enviaba `X-CSRFToken: window.csrfToken`, una
variable que no se asignaba en ninguna parte, y el backend no comprobaba nada.
Ahora hay doble envío y falla cerrado.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.routers_api.users.models import Users
from app.routers_api.users.password_reset import _hash_token
from tests.integration.conftest import TEST_PASSWORD


pytestmark = pytest.mark.integration


# ── Recuperación de contraseña ──────────────────────────────────────────────


async def test_reset_request_answers_the_same_whether_the_account_exists(
    seeded, alpha_client, outbox,
):
    existing = await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": seeded.alpha.users["owner"].email},
    )
    unknown = await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": "nobody@alpha.example.com"},
    )

    assert existing.status_code == unknown.status_code == 200
    assert existing.json() == unknown.json()

    # Y sin embargo solo se envió un correo.
    assert len(outbox.outbox) == 1


async def test_the_token_is_not_stored_in_plain_text(seeded, alpha_client, outbox):
    user = seeded.alpha.users["owner"]

    await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": user.email},
    )

    message = outbox.last_for(user.email)
    assert message is not None
    raw_token = message.body.split("token=")[1].split()[0]

    async with async_session_maker() as session:
        stored = await session.scalar(
            select(Users.reset_token_hash).where(Users.id == user.id)
        )

    assert stored is not None
    assert stored != raw_token, "El token está guardado en claro."
    assert stored == _hash_token(raw_token)


async def test_the_reset_link_lets_the_user_set_a_new_password(
    seeded, alpha_client, outbox,
):
    user = seeded.alpha.users["viewer"]
    new_password = "BrandNewPassword456!"

    await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": user.email},
    )
    raw_token = outbox.last_for(user.email).body.split("token=")[1].split()[0]

    confirmed = await alpha_client.post(
        "/api/public/auth/password-reset/confirm",
        json={"token": raw_token, "password": new_password},
    )
    assert confirmed.status_code == 200

    # El confirm cierra la sesion y borra el testigo CSRF. Un navegador vuelve
    # a la pantalla de acceso y recibe uno nuevo; sin esto, el login siguiente
    # se rechazaria con 403 y el test no llegaria a comprobar la contrasena.
    await alpha_client.reload_login_page()

    assert (await alpha_client.login(user.email, TEST_PASSWORD)).status_code == 401
    assert (await alpha_client.login(user.email, new_password)).status_code == 200


async def test_the_link_can_only_be_used_once(seeded, alpha_client, outbox):
    user = seeded.alpha.users["viewer"]

    await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": user.email},
    )
    raw_token = outbox.last_for(user.email).body.split("token=")[1].split()[0]

    first = await alpha_client.post(
        "/api/public/auth/password-reset/confirm",
        json={"token": raw_token, "password": "FirstAttempt123!"},
    )
    assert first.status_code == 200

    await alpha_client.reload_login_page()

    second = await alpha_client.post(
        "/api/public/auth/password-reset/confirm",
        json={"token": raw_token, "password": "SecondAttempt123!"},
    )
    assert second.status_code == 400


async def test_an_expired_link_is_rejected(seeded, alpha_client, outbox):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    user = seeded.alpha.users["viewer"]

    await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": user.email},
    )
    raw_token = outbox.last_for(user.email).body.split("token=")[1].split()[0]

    async with async_session_maker() as session:
        await session.execute(
            update(Users)
            .where(Users.id == user.id)
            .values(
                reset_token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
            )
        )
        await session.commit()

    response = await alpha_client.post(
        "/api/public/auth/password-reset/confirm",
        json={"token": raw_token, "password": "TooLatePassword123!"},
    )
    assert response.status_code == 400


async def test_a_token_from_another_company_does_not_work(seeded, tenant_client, outbox):
    """El enlace se emite para un usuario de un tenant y solo sirve ahí."""
    beta_user = seeded.beta.users["viewer"]

    async with tenant_client("beta") as beta:
        await beta.post(
            "/api/public/auth/password-reset",
            json={"email": beta_user.email},
        )
        raw_token = outbox.last_for(beta_user.email).body.split("token=")[1].split()[0]

    async with tenant_client("alpha") as alpha:
        response = await alpha.post(
            "/api/public/auth/password-reset/confirm",
            json={"token": raw_token, "password": "CrossTenant123!"},
        )

    assert response.status_code == 400


async def test_no_reset_link_is_issued_for_a_suspended_membership(
    seeded, alpha_client, outbox,
):
    await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": seeded.alpha.users["suspended"].email},
    )
    assert outbox.outbox == []


async def test_a_short_password_is_rejected(seeded, alpha_client, outbox):
    user = seeded.alpha.users["viewer"]

    await alpha_client.post(
        "/api/public/auth/password-reset",
        json={"email": user.email},
    )
    raw_token = outbox.last_for(user.email).body.split("token=")[1].split()[0]

    response = await alpha_client.post(
        "/api/public/auth/password-reset/confirm",
        json={"token": raw_token, "password": "short"},
    )
    assert response.status_code == 422


# ── CSRF ────────────────────────────────────────────────────────────────────


async def test_a_mutating_request_without_the_csrf_header_is_rejected(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    # Se envía sin pasar por el helper que añade la cabecera.
    response = await alpha_client._client.put(  # noqa: SLF001 - se prueba justo eso
        "/api/companies/profile",
        json={"name": "No CSRF"},
    )

    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


async def test_a_mismatched_csrf_token_is_rejected(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client._client.put(  # noqa: SLF001
        "/api/companies/profile",
        json={"name": "Wrong CSRF"},
        headers={"X-CSRF-Token": "not-the-token"},
    )

    assert response.status_code == 403


async def test_reads_do_not_require_a_csrf_token(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client._client.get("/api/roles")  # noqa: SLF001
    assert response.status_code == 200


async def test_the_csrf_cookie_is_issued_by_loading_a_page(alpha_client):
    """La emite `AppMiddleware` en cualquier respuesta de página.

    Es lo que garantiza que el navegador tenga el testigo antes de la primera
    petición mutante.
    """
    assert alpha_client.cookies.get("cer_csrf_token")
