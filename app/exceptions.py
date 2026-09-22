"""
Excepciones de la aplicación.

Son **clases**, no instancias de módulo. Antes eran objetos creados una sola vez
y compartidos por todas las peticiones concurrentes (`raise TokenAbsentException`
sin paréntesis), lo que además impedía adjuntarles contexto (AUD-BE-010).

También se retiraron `RoomCannotBeBooked`, `RoomFullyBooked`,
`HotelNotFoundException` y `EmployeeCannotBeCreated`: venían de un tutorial de
reservas hoteleras y no las usaba nadie (AUD-LEG-007).
"""

from fastapi import HTTPException, status


class AuthenticationError(HTTPException):
    """Base de los fallos de autenticación. Siempre 401."""

    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Not authenticated"

    def __init__(self, detail: str | None = None):
        super().__init__(
            status_code=self.status_code,
            detail=detail or self.detail,
        )


class TokenAbsentException(AuthenticationError):
    detail = "Not authenticated"


class TokenExpiredException(AuthenticationError):
    detail = "Session expired"


class IncorrectTokenFormatException(AuthenticationError):
    """Token con firma inválida, malformado o sin los campos esperados.

    El mensaje no distingue el motivo: para quien lo envía, "tu sesión no vale"
    es toda la información que le corresponde.
    """

    detail = "Invalid session"


class UserIsNotPresentException(AuthenticationError):
    """El token es válido pero no hay detrás un usuario utilizable.

    Cubre tres casos con la misma respuesta a propósito: usuario borrado,
    desactivado en la plataforma, o un `sub` que nunca existió.
    """

    detail = "Invalid session"


class UserAlreadyExistsException(HTTPException):
    def __init__(self, detail: str = "The user already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
