"""
Contraseñas y tokens de sesión.

Dos decisiones que conviene tener a la vista:

1. **Argon2id** es el esquema con el que se guardan las contraseñas nuevas. El
   esquema anterior (`django_pbkdf2_sha256` con 29.000 iteraciones, heredado de
   un sistema Django antiguo) se mantiene **solo para poder verificar** los
   hashes que ya están en la base. Cuando alguien entra con uno de ellos, se
   vuelve a calcular en Argon2id y se guarda: la migración ocurre sola, sin
   pedirle a nadie que cambie su contraseña.

2. El token de sesión se firma con `SECRET_KEY`, cuya validez comprueba
   `app/config.py` al arrancar. No hay refresh ni revocación: la expiración es
   la única salida, así que se mantiene corta y configurable.
"""

from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.config import settings


# `deprecated` marca el esquema legacy: `verify_and_update` devuelve un hash
# nuevo cada vez que verifica uno de ellos.
pwd_context = CryptContext(
    schemes=["argon2", "django_pbkdf2_sha256"],
    deprecated=["django_pbkdf2_sha256"],
    argon2__type="ID",
    argon2__memory_cost=65536,   # 64 MiB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def get_password_hash(password: str) -> str:
    """Hash Argon2id de una contraseña nueva."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Comprueba una contraseña contra su hash, sea Argon2id o el legacy.

    Un usuario sin contraseña (`password IS NULL`) no puede entrar, pero la
    comprobación se hace igualmente contra un hash ficticio para que el tiempo
    de respuesta no delate si la cuenta existe.
    """
    if not hashed_password:
        pwd_context.dummy_verify()
        return False

    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Hash con un formato que ningún esquema reconoce: no es válido.
        return False


def verify_and_upgrade_password(
    plain_password: str,
    hashed_password: str | None,
) -> tuple[bool, str | None]:
    """Verifica y, si el hash es del esquema antiguo, devuelve el nuevo.

    Returns:
        `(es_correcta, hash_nuevo_o_None)`. El segundo elemento solo trae valor
        cuando hay que persistir un rehash.
    """
    if not hashed_password:
        pwd_context.dummy_verify()
        return False, None

    try:
        ok, new_hash = pwd_context.verify_and_update(plain_password, hashed_password)
    except ValueError:
        return False, None

    return bool(ok), new_hash


def create_access_token(data: dict) -> str:
    """Token de sesión firmado. `sub` es el id de usuario como cadena."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
        }
    )

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
