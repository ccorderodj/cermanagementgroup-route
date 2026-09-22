from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Longitud mínima para contraseñas nuevas. No se imponen reglas de composición:
# alargar bate a complicar, y las reglas de "un símbolo y un número" empujan a
# patrones predecibles.
MIN_PASSWORD_LENGTH = 10


class SUserAuth(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)


class SPasswordResetRequest(BaseModel):
    """Petición de enlace de recuperación."""

    email: EmailStr


class SPasswordResetConfirm(BaseModel):
    """Canje del enlace por una contraseña nueva."""

    token: str = Field(min_length=1)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class SGenericAck(BaseModel):
    """Respuesta deliberadamente no informativa.

    La usa el inicio del flujo de recuperación: contestar distinto según el
    correo exista o no convertiría el endpoint en un comprobador de cuentas.
    """

    success: bool = True
    detail: str = (
        "If the address belongs to an account in this company, "
        "a password reset link has been sent."
    )


class SUserProfileResponse(BaseModel):
    id: int
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    gender: bool

    model_config = ConfigDict(from_attributes=True)


class SUserProfileUpdate(BaseModel):
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    gender: bool
    new_password: Optional[str] = Field(default=None, min_length=MIN_PASSWORD_LENGTH)

    model_config = ConfigDict(from_attributes=True)
