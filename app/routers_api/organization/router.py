"""
API de la estructura organizacional de CER Route: cargo y superior.

Las mismas capacidades que la administración de usuarios —`users.read` para
leer, `users.update` para cambiar— y la misma delegación: un `route_manager`
sólo ve y cambia a quienes puede gestionar, sólo asigna cargos por debajo del
suyo y sólo bajo un superior de su rama. Fuera de eso, 404 o 403. Nadie cambia
su propio cargo.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.organization import delegation as delegada
from app.routers_api.organization import service
from app.routers_api.organization.models import ETIQUETA, NIVEL
from app.routers_api.organization.schemas import (
    OrgAssignmentRead,
    OrgAssignmentWrite,
    OrgOptions,
    OrgPositionOption,
    OrgSuperiorOption,
)
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions

router = APIRouter(prefix="/route/organization", tags=["Route · Organization"])


async def _lectura(company_id: int, user_ids: set[int] | None) -> list[OrgAssignmentRead]:
    actuales = await service.vigentes(company_id)
    if user_ids is not None:
        actuales = {u: a for u, a in actuales.items() if u in user_ids}
    gente = await service.nombres(
        company_id,
        set(actuales) | {a.superior_user_id for a in actuales.values() if a.superior_user_id},
    )
    return [
        OrgAssignmentRead(
            user_id=a.user_id,
            name=gente.get(a.user_id, ""),
            position=a.position,
            position_label=ETIQUETA[a.position],
            superior_user_id=a.superior_user_id,
            superior_name=gente.get(a.superior_user_id) if a.superior_user_id else None,
            version=a.version,
        )
        for a in sorted(actuales.values(), key=lambda a: (-NIVEL[a.position], a.user_id))
    ]


@router.get("", response_model=list[OrgAssignmentRead])
async def listar(
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[OrgAssignmentRead]:
    """Los cargos vigentes que este actor puede ver."""
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    return await _lectura(company.id, await delegada.gestionables(d, company_id=company.id))


@router.get("/options", response_model=OrgOptions)
async def opciones(
    user_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.read"])),
    company: TenantContext = Depends(get_company_required),
) -> OrgOptions:
    """Cargos y superiores que este actor puede asignar a esta persona (o a una
    nueva, sin `user_id`)."""
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    actuales = await service.vigentes(company.id)
    actual = None
    excluidos: set[int] = set()
    if user_id is not None:
        await delegada.exigir_objetivo(d, company_id=company.id, user_id=user_id)
        # Ni la propia persona ni quien cuelga de ella pueden ser su superior.
        excluidos = {user_id} | service.descendientes(actuales, user_id)
        actual = next(iter(await _lectura(company.id, {user_id})), None)
    posibles = d.superiores_posibles()
    candidatos = {
        u: a
        for u, a in actuales.items()
        if u not in excluidos and (posibles is None or u in posibles)
    }
    gente = await service.nombres(company.id, set(candidatos))
    return OrgOptions(
        positions=[
            OrgPositionOption(code=p, label=ETIQUETA[p], level=NIVEL[p])
            for p in d.cargos_asignables
        ],
        superiors=[
            OrgSuperiorOption(
                user_id=u, name=gente.get(u, ""), position=a.position, level=NIVEL[a.position]
            )
            for u, a in sorted(candidatos.items(), key=lambda t: (-NIVEL[t[1].position], t[0]))
        ],
        superior_required=not d.tenant,
        current=actual,
    )


@router.put("/{user_id}", response_model=OrgAssignmentRead)
async def asignar(
    user_id: int,
    payload: OrgAssignmentWrite,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update"])),
    company: TenantContext = Depends(get_company_required),
) -> OrgAssignmentRead:
    """Fija el cargo y el superior vigentes de una persona."""
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    await delegada.exigir_objetivo(d, company_id=company.id, user_id=user_id)
    delegada.exigir_asignacion(
        d, position=payload.position, superior_user_id=payload.superior_user_id
    )
    if not d.tenant:
        rol = await service.rol_en_compania(company_id=company.id, user_id=user_id)
        delegada.exigir_rol(d, role_name=rol, position=payload.position)
    await service.asignar(
        company_id=company.id,
        actor_user_id=current_user.id,
        user_id=user_id,
        position=payload.position,
        superior_user_id=payload.superior_user_id,
        expected_version=payload.version,
        reason=payload.reason,
    )
    return (await _lectura(company.id, {user_id}))[0]


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retirar(
    user_id: int,
    version: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update"])),
    company: TenantContext = Depends(get_company_required),
) -> None:
    """Quita el cargo vigente. Con subordinados directos, 409."""
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    await delegada.exigir_objetivo(d, company_id=company.id, user_id=user_id)
    await service.retirar(
        company_id=company.id,
        actor_user_id=current_user.id,
        user_id=user_id,
        expected_version=version,
    )
