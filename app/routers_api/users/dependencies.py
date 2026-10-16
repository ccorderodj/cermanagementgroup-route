"""
Dependencias de sesión, identidad y contexto de tenant.

La cadena completa que atraviesa una petición autenticada de la API es:

    cookie cer_access_token
      -> get_token          el token existe
      -> get_current_user   la firma es válida, el usuario existe y está ACTIVO
      -> get_current_membership  el usuario pertenece a la compañía del subdominio
                                 y esa pertenencia está ACTIVA

Los dos niveles de "activo" son deliberados y distintos (D7):

* `Users.is_active`        identidad de plataforma. Si está en `False` el
                           usuario no entra en ninguna parte.
* `UserCompany.is_active`  pertenencia a UNA compañía. Si está en `False` el
                           usuario sigue existiendo y puede entrar a otros
                           tenants, pero no a este.

Antes ninguno de los dos se comprobaba al iniciar sesión, así que "suspender el
acceso" desde la pantalla de gestión no suspendía nada.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import settings
from app.exceptions import (
    IncorrectTokenFormatException,
    TokenAbsentException,
    TokenExpiredException,
    UserIsNotPresentException,
)
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.dao import UsersDAO
from app.routers_api.users.models import Users


ACCESS_COOKIE_NAME = "cer_access_token"


def decode_access_token(token: str) -> dict:
    """Valida firma y expiración. Única implementación en todo el proyecto.

    Antes había tres copias de esta lógica (middleware de páginas, middleware de
    sesión y dependencia de API), cada una con un manejo de errores distinto:
    un token manipulado se reportaba al usuario como "expirado".
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise IncorrectTokenFormatException from exc

    expire = payload.get("exp")
    if not expire:
        raise IncorrectTokenFormatException

    if int(expire) < int(datetime.now(timezone.utc).timestamp()):
        raise TokenExpiredException

    if not payload.get("sub"):
        raise IncorrectTokenFormatException

    return payload


def get_token(request: Request) -> str:
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise TokenAbsentException
    return token


async def get_current_user(token: str = Depends(get_token)) -> Users:
    payload = decode_access_token(token)

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise IncorrectTokenFormatException from exc

    user = await UsersDAO.find_active_by_id(user_id)
    if not user:
        # Cubre tres casos con la misma respuesta a propósito: usuario borrado,
        # usuario desactivado globalmente, o `sub` inventado.
        raise UserIsNotPresentException

    return user


async def get_current_membership(
    current_user: Users = Depends(get_current_user),
    current_company: TenantContext = Depends(get_company_required),
) -> UserCompany:
    """La pertenencia activa del usuario a la compañía del subdominio.

    Es la puerta de entrada al tenant: sin membresía activa, el usuario no puede
    leer ni escribir nada de esta compañía aunque su identidad sea válida.
    """
    membership = await UsersDAO.find_active_membership(
        user_id=current_user.id,
        company_id=current_company.id,
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this company",
        )

    return membership


async def require_platform_admin(
    current_user: Users = Depends(get_current_user),
) -> Users:
    """Operaciones de administración de plataforma, por encima de cualquier tenant (D6).

    `Users.is_superuser` es privilegio global: no se asigna ni se modifica desde
    ninguna API de tenant, y no forma parte del catálogo de permisos. Es lo que
    separa "administrar mi compañía" de "administrar la plataforma".
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to platform administrators",
        )
    return current_user
