"""
Recuperación de contraseña (D3).

    solicitar
      -> respuesta idéntica exista o no la cuenta
      -> token aleatorio de 256 bits
      -> en la base se guarda solo su SHA-256
      -> caduca a los PASSWORD_RESET_TOKEN_MINUTES
      -> se canjea UNA vez
      -> al canjearlo se borra

Cuatro decisiones que merecen quedar explicadas:

**La respuesta no distingue.** `POST /password-reset` contesta siempre lo mismo.
Si contestara "ese correo no existe" sería un comprobador de cuentas gratuito.

**El token no se guarda en claro.** En la base va su SHA-256. Quien consiga
leer la tabla `user` no obtiene con ello enlaces utilizables. No hace falta
Argon2 aquí: el token ya tiene 256 bits de entropía, no hay nada que adivinar.

**Un solo uso.** Al canjearlo se limpian el hash y la caducidad, así que el
mismo enlace no sirve dos veces —ni siquiera si sigue dentro de su ventana.

**Alcance de compañía.** El token se emite para un usuario que pertenece a la
compañía del subdominio desde el que se pidió. Se comprueba también al canjear.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update

from app.config import settings
from app.core.db.session import transaction
from app.core.email.backends import send_email
from app.logger import logger
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.auth import get_password_hash
from app.routers_api.users.models import Users


TOKEN_BYTES = 32  # 256 bits


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _build_reset_url(company: TenantContext, raw_token: str) -> str:
    host = company.subdomain or ""
    base = f"{host}.{settings.BASE_DOMAIN}" if host else settings.BASE_DOMAIN
    scheme = "https" if settings.is_production else "http"
    return f"{scheme}://{base}/change-password?token={raw_token}"


async def request_password_reset(*, email: str, company: TenantContext) -> None:
    """Emite un enlace si procede. No informa de nada al llamador."""
    normalized = (email or "").strip().lower()

    async with transaction() as session:
        user = await session.scalar(
            select(Users)
            .join(UserCompany, UserCompany.user_id == Users.id)
            .where(
                Users.email.ilike(normalized),
                Users.is_active.is_(True),
                UserCompany.company_id == company.id,
                UserCompany.is_active.is_(True),
            )
            .limit(1)
        )

        if user is None:
            # Sin cuenta utilizable no se emite nada, pero el endpoint responde
            # igual que si la hubiera.
            logger.info(
                "PASSWORD RESET | solicitado para una direccion sin cuenta activa "
                "en company_id=%s",
                company.id,
            )
            return

        raw_token = secrets.token_urlsafe(TOKEN_BYTES)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_MINUTES
        )

        await session.execute(
            update(Users)
            .where(Users.id == user.id)
            .values(
                reset_token_hash=_hash_token(raw_token),
                reset_token_expires_at=expires_at,
            )
        )

        # El token viaja únicamente en el correo. En el log queda que se emitió,
        # nunca su valor.
        send_email(
            to=user.email,
            subject=f"{company.name} — Password reset",
            body=(
                f"Hello {user.first_name},\n\n"
                "We received a request to reset your password. "
                "Open the link below to choose a new one:\n\n"
                f"{_build_reset_url(company, raw_token)}\n\n"
                f"The link expires in {settings.PASSWORD_RESET_TOKEN_MINUTES} minutes "
                "and can only be used once.\n\n"
                "If you did not request this, you can ignore this message.\n"
            ),
        )

        logger.info(
            "PASSWORD RESET | enlace emitido user_id=%s company_id=%s",
            user.id,
            company.id,
        )


async def confirm_password_reset(
    *,
    raw_token: str,
    new_password: str,
    company: TenantContext,
) -> None:
    """Canjea el enlace por una contraseña nueva. Lanza 400 si no es válido."""
    token_hash = _hash_token((raw_token or "").strip())
    now = datetime.now(timezone.utc)

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This password reset link is invalid or has expired.",
    )

    async with transaction() as session:
        user = await session.scalar(
            select(Users)
            .join(UserCompany, UserCompany.user_id == Users.id)
            .where(
                Users.reset_token_hash == token_hash,
                Users.is_active.is_(True),
                UserCompany.company_id == company.id,
                UserCompany.is_active.is_(True),
            )
            .limit(1)
        )

        if user is None or user.reset_token_expires_at is None:
            raise invalid

        expires_at = user.reset_token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            raise invalid

        await session.execute(
            update(Users)
            .where(Users.id == user.id)
            .values(
                password=get_password_hash(new_password),
                # Un solo uso: el enlace deja de servir en cuanto se canjea.
                reset_token_hash=None,
                reset_token_expires_at=None,
            )
        )

        logger.info("PASSWORD RESET | contrasena cambiada user_id=%s", user.id)
