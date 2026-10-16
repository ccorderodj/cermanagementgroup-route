"""
Autorización por permisos.

Cómo se resuelve lo que puede hacer un usuario en la compañía activa:

    user_company (activa)  ->  role (de ESA compañía)  ->  role_permission  ->  permission

Los permisos se recalculan **contra la base en cada petición**. La cookie
`user_data` lleva una copia para que la interfaz sepa qué pintar, pero no se
consulta nunca aquí: es del cliente, y el cliente puede editarla.

`Users.is_superuser` cortocircuita la comprobación. Es privilegio de plataforma,
no un permiso de tenant: no está en el catálogo, no se puede conceder desde
ninguna API de tenant y no se puede pedir con `require_permissions` (D6).
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from app.core.db.session import db_session
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.models import UserCompany
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from app.routers_api.users.dependencies import get_current_membership, get_current_user
from app.routers_api.users.models import Users


async def get_user_permissions(*, user_id: int, company_id: int) -> set[str]:
    """Permisos efectivos del usuario en esa compañía.

    El filtro por `Role.company_id` es redundante con el de `UserCompany`
    —la restricción compuesta de la base ya garantiza que el rol pertenece a la
    misma compañía— pero se mantiene explícito: si algún día esa restricción se
    perdiera en una migración, la consulta seguiría sin cruzar tenants.
    """
    async with db_session() as session:
        stmt = (
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserCompany, UserCompany.role_id == Role.id)
            .where(
                UserCompany.user_id == user_id,
                UserCompany.company_id == company_id,
                UserCompany.is_active.is_(True),
                Role.company_id == company_id,
                Role.is_active.is_(True),
                RolePermission.is_active.is_(True),
                Permission.is_active.is_(True),
            )
        )
        result = await session.execute(stmt)
        return {name for name in result.scalars().all() if name}


async def get_user_role_names(*, user_id: int, company_id: int) -> list[str]:
    async with db_session() as session:
        stmt = (
            select(Role.name)
            .join(UserCompany, UserCompany.role_id == Role.id)
            .where(
                UserCompany.user_id == user_id,
                UserCompany.company_id == company_id,
                UserCompany.is_active.is_(True),
                Role.company_id == company_id,
                Role.is_active.is_(True),
            )
        )
        result = await session.execute(stmt)
        return [name for name in result.scalars().all() if name]


def has_permissions(required_permissions: list[str]) -> Callable:
    """Dependencia que **informa** de si el usuario tiene los permisos.

    `require_permissions` corta con 403: sirve cuando la petición entera está
    prohibida. Hay casos en los que la petición es legítima y lo que cambia es
    qué campos lleva la respuesta —la tarifa de facturación de un perfil de
    puesto es visible para finanzas y no para el resto—. Cortar ahí dejaría sin
    perfiles de puesto a quien solo no puede ver el importe.

    Devuelve un booleano y el handler decide. La decisión sigue siendo del
    servidor: el campo no viaja, así que no basta con abrir las herramientas de
    desarrollo para verlo. Ocultar en el frontend es experiencia de usuario, no
    un control (D8).

    `tests/test_permission_catalog.py` reconoce esta función igual que a
    `require_permissions`, así que una capacidad usada solo aquí sigue contando
    como exigida y una que no exista sigue haciendo fallar el test.
    """

    async def _dependency(
        current_user: Users = Depends(get_current_user),
        current_company: TenantContext = Depends(get_company_required),
        _membership: UserCompany = Depends(get_current_membership),
    ) -> bool:
        if current_user.is_superuser:
            return True

        required = set(required_permissions)
        if not required:
            return True

        granted = await get_user_permissions(
            user_id=current_user.id,
            company_id=current_company.id,
        )
        return required.issubset(granted)

    return _dependency


def require_permissions(
    required_permissions: list[str],
    require_all: bool = True,
) -> Callable:
    """Dependencia que exige permisos en la compañía activa.

    Depende de `get_current_membership`, así que antes de mirar ningún permiso
    ya se ha comprobado que la identidad global esté activa y que la pertenencia
    a esta compañía también lo esté (D7). Un usuario suspendido en este tenant
    recibe 403 por no tener acceso, no un confuso "te faltan permisos".
    """

    async def _dependency(
        current_user: Users = Depends(get_current_user),
        current_company: TenantContext = Depends(get_company_required),
        _membership: UserCompany = Depends(get_current_membership),
    ) -> None:
        if current_user.is_superuser:
            return

        required = set(required_permissions)
        if not required:
            return

        granted = await get_user_permissions(
            user_id=current_user.id,
            company_id=current_company.id,
        )

        if require_all:
            missing = required - granted
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing permissions: {', '.join(sorted(missing))}",
                )
        elif not (required & granted):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(required))}",
            )

    return _dependency
