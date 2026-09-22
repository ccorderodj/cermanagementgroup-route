"""
Endpoints de autenticación que se sirven SIN sesión.

Este es el único módulo cuyos endpoints pueden colgar del router público, y
están enumerados uno a uno a propósito. Antes se incluía el router completo de
`users` bajo `/public`, lo que publicaba también `register`, `change-password`
y el perfil sin que nadie lo hubiera decidido (AUD-SEC-002).

Regla permanente: **un router público declara endpoints, nunca un router de
dominio que mezcle lo público con lo privado.**
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.security.cookies import clear_session_cookies, set_access_cookie, set_csrf_cookie
from app.core.security.csrf import generate_csrf_token
from app.logger import logger
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.users.auth import create_access_token, verify_and_upgrade_password
from app.routers_api.users.dao import UsersDAO
from app.routers_api.users.password_reset import (
    confirm_password_reset,
    request_password_reset,
)
from app.routers_api.users.schemas import (
    SGenericAck,
    SPasswordResetConfirm,
    SPasswordResetRequest,
    SUserAuth,
)


router = APIRouter(prefix="/auth", tags=["Public Auth"])


# Una sola respuesta para "no existe", "está desactivado", "no pertenece a esta
# compañía" y "la contraseña no es correcta". Distinguirlas convertía el login
# en un comprobador de direcciones (AUD-BE-006).
INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
)


@router.post("/login")
async def login(
    response: Response,
    user_data: SUserAuth,
    current_company: TenantContext = Depends(get_company_required),
):
    user = await UsersDAO.find_login_candidate(
        email=user_data.email,
        company_id=current_company.id,
    )

    if user is None:
        # Se gasta el tiempo de una verificación igualmente para que la
        # respuesta no sea perceptiblemente más rápida cuando no hay cuenta.
        verify_and_upgrade_password(user_data.password, None)
        logger.info("LOGIN | fallido en company_id=%s", current_company.id)
        raise INVALID_CREDENTIALS

    is_valid, upgraded_hash = verify_and_upgrade_password(
        user_data.password,
        user.password,
    )

    if not is_valid:
        logger.info("LOGIN | contrasena incorrecta user_id=%s", user.id)
        raise INVALID_CREDENTIALS

    # El hash antiguo (PBKDF2 de un Django viejo) se sustituye por Argon2id en
    # el momento en que se demuestra que la contraseña es correcta. El usuario
    # no se entera y no hay que forzar ningún cambio (D9).
    if upgraded_hash:
        await UsersDAO.set_password_hash(user.id, upgraded_hash)
        logger.info("LOGIN | hash migrado a argon2id user_id=%s", user.id)

    await UsersDAO.touch_last_login(user.id, datetime.now(timezone.utc))

    access_token = create_access_token({"sub": str(user.id)})
    set_access_cookie(response, access_token)
    set_csrf_cookie(response, generate_csrf_token())

    # El token va solo en la cookie HttpOnly. Devolverlo también en el cuerpo
    # anulaba el motivo de marcarla HttpOnly (AUD-SEC-017).
    return {"success": True}


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookies(response)
    return {"success": True}


@router.post("/password-reset", response_model=SGenericAck)
async def password_reset_request(
    payload: SPasswordResetRequest,
    current_company: TenantContext = Depends(get_company_required),
):
    """Pide un enlace de recuperación. Responde igual exista o no la cuenta."""
    await request_password_reset(email=payload.email, company=current_company)
    return SGenericAck()


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    payload: SPasswordResetConfirm,
    response: Response,
    current_company: TenantContext = Depends(get_company_required),
):
    """Canjea el enlace por una contraseña nueva. El enlace queda inutilizable."""
    await confirm_password_reset(
        raw_token=payload.token,
        new_password=payload.password,
        company=current_company,
    )

    # Cambiar la contraseña cierra la sesión: quien la cambió por haberla
    # perdido no debería seguir teniendo abierta la anterior.
    clear_session_cookies(response)
    return {"success": True, "detail": "Password changed successfully"}
