"""
Idempotencia: la misma clave produce la misma respuesta, una sola vez.

Un emisor que reintenta (red caída, timeout, 5xx) no puede saber si la primera
vez se procesó. Con `Idempotency-Key` el receptor recuerda la respuesta y la
devuelve sin volver a ejecutar la operación.

    registro = await claim(scope="orders.create", company_id=c.id, key=k, request_body=cuerpo)
    if registro.replay:
        return JSONResponse(registro.body, status_code=registro.status)
    ... ejecutar ...
    await remember(scope=..., company_id=..., key=k, request_body=cuerpo, status=201, body=respuesta)

Reglas:

* La misma clave con **otro cuerpo** es un error del cliente (422): reutilizó
  una clave para una operación distinta.
* La clave caduca a las `IDEMPOTENCY_TTL_HOURS`.
* La unicidad la garantiza la base (`uq_idempotency_record_scope_key`), no una
  lectura previa: dos peticiones simultáneas no pueden registrarse las dos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.core.db.session import db_session
from app.core.integration.models import IdempotencyRecord
from app.core.integration.signatures import body_sha256

IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 200


@dataclass(frozen=True)
class Replay:
    replay: bool
    status: int | None = None
    body: Any = None


def _validate_key(key: str | None) -> str:
    if not key or not key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The {IDEMPOTENCY_HEADER} header is required for this operation.",
        )
    key = key.strip()
    if len(key) > MAX_KEY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{IDEMPOTENCY_HEADER} must be at most {MAX_KEY_LENGTH} characters.",
        )
    return key


async def claim(*, scope: str, company_id: int | None, key: str | None, request_body: bytes) -> Replay:
    """¿Ya se respondió a esta clave? Si sí, devuelve la respuesta recordada."""
    key = _validate_key(key)
    huella = body_sha256(request_body)
    ahora = datetime.now(timezone.utc)
    async with db_session() as session:
        registro = await session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.company_id == (company_id or 0),
                IdempotencyRecord.key == key,
                IdempotencyRecord.expires_at > ahora,
            )
        )
    if registro is None:
        return Replay(replay=False)
    if registro.request_sha256 != huella:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This {IDEMPOTENCY_HEADER} was already used with a different request.",
        )
    return Replay(replay=True, status=registro.response_status, body=registro.response_body)


async def remember(
    *,
    scope: str,
    company_id: int | None,
    key: str | None,
    request_body: bytes,
    status_code: int,
    body: Any,
) -> bool:
    """Guarda la respuesta. Devuelve `False` si otra petición la guardó antes."""
    key = _validate_key(key)
    ahora = datetime.now(timezone.utc)
    async with db_session() as session:
        await session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.company_id == (company_id or 0),
                IdempotencyRecord.key == key,
                IdempotencyRecord.expires_at <= ahora,
            )
        )
        resultado = await session.execute(
            insert(IdempotencyRecord)
            .values(
                scope=scope,
                company_id=company_id or 0,
                key=key,
                request_sha256=body_sha256(request_body),
                response_status=status_code,
                response_body=body,
                expires_at=ahora + timedelta(hours=settings.IDEMPOTENCY_TTL_HOURS),
            )
            .on_conflict_do_nothing(constraint="uq_idempotency_record_scope_key")
        )
        await session.commit()
    return bool(resultado.rowcount)


async def purge_expired() -> int:
    async with db_session() as session:
        resultado = await session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.expires_at <= datetime.now(timezone.utc)
            )
        )
        await session.commit()
    return resultado.rowcount or 0
