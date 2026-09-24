"""
Gestión de usuarios de la compañía activa.

Un usuario y su rol en la compañía son **un solo concepto** desde el punto de
vista de quien administra: `user_company` es una tabla puente, un detalle de
normalización, no algo que deba administrarse por separado. Por eso este módulo
expone una sola familia de endpoints —siempre con alcance de la compañía
activa— y resuelve el join aquí, en vez de obligar al frontend a cruzar dos
listados.

Dos límites que este módulo no puede cruzar:

* **No concede privilegio de plataforma.** `is_superuser` no está en ningún
  schema de entrada (D6, AUD-SEC-012).
* **No desactiva identidades.** Suspender actúa sobre la pertenencia a esta
  compañía; la identidad global es administración de plataforma (D7).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core import schema
from app.core.audit.service import diff, record_event
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.usermanagement.dao import UserManagementDAO
from app.routers_api.usermanagement.schemas import (
    UserAccessUpdate,
    UserManagementCreate,
    UserManagementRead,
    UserManagementUpdate,
    UsersPaginationParams,
)
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("/pagination")
async def get_users_pagination(
    request: Request,
    params: UsersPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["users.read"])),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[UserManagementRead]:
    """Usuarios de la compañía activa, ya con su rol resuelto."""
    page = await UserManagementDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=company.id,
        q=params.q,
        is_active=params.is_active,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=[UserManagementRead.model_validate(row) for row in page.items],
        request=request,
    )
    return schema.PaginatedResponse[UserManagementRead](**paginator.to_response())


#: Campos que se comparan para la traza. `password` **no** está aquí: su valor
#: no se registra ni siquiera cifrado, y que haya cambiado se deduce del evento.
_CAMPOS_AUDITADOS = ("username", "email", "first_name", "last_name", "gender", "role_id")


def _instantanea(usuario: dict) -> dict:
    return {campo: usuario.get(campo) for campo in _CAMPOS_AUDITADOS}


@router.post("")
async def create_user(
    payload: UserManagementCreate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.create"])),
    company: TenantContext = Depends(get_company_required),
) -> UserManagementRead:
    """Crea el usuario y su pertenencia a la compañía en una sola operación."""
    created = await UserManagementDAO.create_user_with_company_role(
        company_id=company.id,
        **payload.model_dump(),
    )

    # Dar de alta a alguien en un tenant es de las operaciones más sensibles que
    # hay —concede acceso— y no dejaba traza. Se registra con el mismo mecanismo
    # que el resto del sistema, no con uno propio.
    await record_event(
        company_id=company.id,
        entity_type="user",
        entity_id=created["id"],
        action="create",
        actor_user_id=current_user.id,
        summary=f"User {created.get('email') or created['username']} added to the company",
        changes={
            campo: {"old": None, "new": valor}
            for campo, valor in _instantanea(created).items()
        },
    )
    return UserManagementRead.model_validate(created)


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    payload: UserManagementUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update"])),
    company: TenantContext = Depends(get_company_required),
) -> UserManagementRead:
    """Actualiza los datos del usuario y, si viene, su rol en la compañía."""
    data = payload.model_dump(exclude_unset=True)
    cambia_contrasena = data.get("password") is not None

    antes = await UserManagementDAO.find_for_company(
        user_id=user_id, company_id=company.id
    )

    updated = await UserManagementDAO.update_user_in_company(
        user_id=user_id,
        company_id=company.id,
        role_id=data.pop("role_id", None),
        password=data.pop("password", None),
        **data,
    )

    delta = diff(_instantanea(antes or {}), _instantanea(updated))
    if cambia_contrasena:
        # Que la contraseña cambió es auditable; su valor, no.
        delta["password"] = {"old": None, "new": "(changed)"}

    if delta:
        await record_event(
            company_id=company.id,
            entity_type="user",
            entity_id=user_id,
            action="update",
            actor_user_id=current_user.id,
            summary=f"User {updated.get('email') or updated['username']} updated",
            changes=delta,
        )
    return UserManagementRead.model_validate(updated)


@router.put("/{user_id}/access")
async def set_user_access(
    user_id: int,
    payload: UserAccessUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update"])),
    company: TenantContext = Depends(get_company_required),
) -> UserManagementRead:
    """Activa o suspende el acceso del usuario **a esta compañía**.

    El usuario sigue existiendo en la plataforma y puede seguir entrando a otros
    tenants donde su pertenencia siga activa.
    """
    updated = await UserManagementDAO.set_membership_access(
        user_id=user_id,
        company_id=company.id,
        is_active=payload.is_active,
    )

    await record_event(
        company_id=company.id,
        entity_type="user",
        entity_id=user_id,
        action="activate" if payload.is_active else "deactivate",
        actor_user_id=current_user.id,
        summary=(
            f"Access to this company {'restored for' if payload.is_active else 'suspended for'} "
            f"{updated.get('email') or updated['username']}"
        ),
        changes={"is_active": {"old": not payload.is_active, "new": payload.is_active}},
    )
    return UserManagementRead.model_validate(updated)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_from_company(
    user_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.delete"])),
    company: TenantContext = Depends(get_company_required),
) -> None:
    """Retira a la persona de **esta** compañía. No borra su identidad.

    Distinto de suspender: suspender deja al usuario en la administración, con
    su acceso cortado y reversible; retirar lo saca de la experiencia normal
    del tenant. La identidad de plataforma no se toca, así que quien pertenezca
    a otras compañías sigue entrando en ellas con normalidad.

    Nadie puede retirarse a sí mismo: dejaría al administrador fuera de la
    pantalla desde la que acaba de actuar, y si era el último con la capacidad,
    a la compañía sin nadie que pueda administrarla.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot remove your own access to this company.",
        )

    retirado = await UserManagementDAO.delete_membership(
        user_id=user_id, company_id=company.id
    )

    await record_event(
        company_id=company.id,
        entity_type="user",
        entity_id=user_id,
        action="delete",
        actor_user_id=current_user.id,
        summary=(
            f"{retirado.get('email') or retirado['username']} removed from this company"
        ),
        # Queda en la traza quién era y con qué rol: la pantalla ya no lo
        # muestra, y sin esto no habría forma de reconstruirlo después.
        changes={
            "membership": {"old": "active", "new": None},
            "role_id": {"old": retirado.get("role_id"), "new": None},
            "email": {"old": retirado.get("email"), "new": None},
        },
    )
