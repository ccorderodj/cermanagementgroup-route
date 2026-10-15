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

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.organization import delegation as delegada
from app.routers_api.organization import service
from app.routers_api.organization import succession as sucesion
from app.routers_api.organization.contract_guard import exigir_relevo_en_cargo
from app.routers_api.organization.models import (
    CARGO_DE_ROL,
    ETIQUETA,
    NIVEL,
    PADRES_PERMITIDOS,
)
from app.routers_api.organization.schemas import (
    OrgAssignmentRead,
    OrgAssignmentWrite,
    OrgOptions,
    OrgPositionOption,
    OrgSuperiorOption,
    SuccessionInfo,
    SuccessionMove,
    SuccessionPerson,
    SuccessionPlanRead,
    SuccessionWrite,
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
    # Sólo quien puede recibir subordinados: el servicio rechaza un superior
    # suspendido, así que ofrecerlo era prometer algo que después falla (H-3).
    miembros = await service.pertenencias(company.id)
    candidatos = {
        u: a
        for u, a in actuales.items()
        if u not in excluidos
        and (posibles is None or u in posibles)
        and u in miembros
        and miembros[u].activa
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
        role_positions=dict(CARGO_DE_ROL),
        allowed_parents={c: sorted(p) for c, p in PADRES_PERMITIDOS.items()},
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
    previa = (await service.vigentes(company.id)).get(user_id)
    # CEO y COO se relevan, no se reasignan (V1.5). Sobre uno mismo decide el
    # servicio con su 403: nadie cambia su propio cargo.
    if user_id != current_user.id:
        exigir_relevo_en_cargo(
            previo=previa.position if previa else None,
            nuevo=payload.position,
            cambia_superior=previa is not None
            and previa.superior_user_id != payload.superior_user_id,
        )
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
    """Quita el cargo vigente. Con subordinados directos, 409. CEO y COO, por
    «Retire / Replace manager» (V1.5)."""
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    await delegada.exigir_objetivo(d, company_id=company.id, user_id=user_id)
    previa = (await service.vigentes(company.id)).get(user_id)
    if previa is not None:
        exigir_relevo_en_cargo(previo=previa.position, nuevo=None)
    await service.retirar(
        company_id=company.id,
        actor_user_id=current_user.id,
        user_id=user_id,
        expected_version=version,
    )


# ── Continuidad: retirar o sustituir a un responsable (V1.4) ────────────────


def _persona(gente: dict[int, str], user_id: int, cargo: str | None) -> SuccessionPerson:
    return SuccessionPerson(
        user_id=user_id,
        name=gente.get(user_id, ""),
        position_label=ETIQUETA[cargo] if cargo else "",
    )


def _lectura_del_plan(
    plan: sucesion.Plan, gente: dict[int, str], *, applied: bool, operation_id: str | None = None
) -> SuccessionPlanRead:
    superior = plan.superior_saliente
    cargos_antes = {m.user_id: m.position for m in plan.movimientos}
    return SuccessionPlanRead(
        operation=plan.operacion,
        applied=applied,
        operation_id=operation_id,
        outgoing=_persona(gente, plan.saliente, plan.cargo),
        superior=SuccessionPerson(user_id=superior, name=gente.get(superior, ""), position_label="")
        if superior is not None
        else None,
        successor=_persona(gente, plan.sucesor, plan.cargo) if plan.sucesor is not None else None,
        successor_before=ETIQUETA[plan.sucesor_antes[0]] if plan.sucesor_antes else None,
        moves=[
            SuccessionMove(
                user_id=m.user_id,
                name=gente.get(m.user_id, ""),
                position_label=ETIQUETA[cargos_antes[m.user_id]],
                from_user_id=m.superior_antes,
                from_name=gente.get(m.superior_antes) if m.superior_antes else None,
                to_user_id=m.superior_despues,
                to_name=gente.get(m.superior_despues) if m.superior_despues else None,
            )
            for m in plan.movimientos
        ],
        version=plan.version,
    )


async def _succession_guard(company: TenantContext, current_user: Users, user_id: int) -> None:
    await sucesion.exigir_autorizado(company_id=company.id, actor_user_id=current_user.id)
    if user_id not in await service.pertenencias(company.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this company")


@router.get("/{user_id}/succession", response_model=SuccessionInfo)
async def continuidad(
    user_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update", "users.delete"])),
    company: TenantContext = Depends(get_company_required),
) -> SuccessionInfo:
    """Qué pasaría al retirar a esta persona y a quién se puede elegir como
    sucesor. No escribe nada."""
    await _succession_guard(company, current_user, user_id)
    actuales = await service.vigentes(company.id)
    previa = actuales.get(user_id)
    if previa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This person has no position.")
    candidatos = await sucesion.candidatos_a_sucesor(company_id=company.id, saliente=user_id)
    directos = sorted(u for u, a in actuales.items() if a.superior_user_id == user_id)
    gente = await service.nombres(company.id, {user_id, *directos, *candidatos})
    vista = None
    bloqueo = None
    try:
        plan, gente_plan = await sucesion.calcular(company_id=company.id, operacion="retire", saliente=user_id)
        vista = _lectura_del_plan(plan, gente_plan, applied=False)
    except HTTPException as e:
        bloqueo = str(e.detail)
    return SuccessionInfo(
        outgoing=_persona(gente, user_id, previa.position),
        version=previa.version,
        direct_reports=[_persona(gente, u, actuales[u].position) for u in directos],
        can_replace=previa.position in sucesion.SUSTITUIBLES,
        retire_preview=vista,
        retire_blocked_reason=bloqueo,
        successor_candidates=[
            _persona(gente, u, actuales[u].position if u in actuales else None) for u in candidatos
        ],
    )


async def _operar(
    operacion: str, user_id: int, payload: SuccessionWrite, current_user: Users, company: TenantContext
) -> SuccessionPlanRead:
    await _succession_guard(company, current_user, user_id)
    if payload.dry_run:
        plan, gente = await sucesion.calcular(
            company_id=company.id,
            operacion=operacion,
            saliente=user_id,
            sucesor=payload.successor_user_id,
        )
        return _lectura_del_plan(plan, gente, applied=False)
    plan, operacion_id = await sucesion.ejecutar(
        company_id=company.id,
        actor_user_id=current_user.id,
        operacion=operacion,
        saliente=user_id,
        sucesor=payload.successor_user_id,
        expected_version=payload.version,
        reason=payload.reason,
    )
    gente = await service.nombres(
        company.id,
        {user_id, *(m.user_id for m in plan.movimientos), *(
            u for m in plan.movimientos for u in (m.superior_antes, m.superior_despues) if u
        ), *((plan.sucesor,) if plan.sucesor else ()), *((plan.superior_saliente,) if plan.superior_saliente else ())},
    )
    return _lectura_del_plan(plan, gente, applied=True, operation_id=operacion_id)


@router.post("/{user_id}/retire", response_model=SuccessionPlanRead)
async def retirar_responsable(
    user_id: int,
    payload: SuccessionWrite,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update", "users.delete"])),
    company: TenantContext = Depends(get_company_required),
) -> SuccessionPlanRead:
    """Salida definitiva sin sucesor: sus directos pasan a su superior inmediato
    y la persona deja la compañía. Con `dry_run`, sólo la vista previa."""
    return await _operar("retire", user_id, payload, current_user, company)


@router.post("/{user_id}/replace", response_model=SuccessionPlanRead)
async def sustituir_responsable(
    user_id: int,
    payload: SuccessionWrite,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["users.update", "users.delete"])),
    company: TenantContext = Depends(get_company_required),
) -> SuccessionPlanRead:
    """Sustitución: el sucesor ocupa el cargo bajo el mismo superior, recibe a
    todos los directos, y quien sale deja la compañía. Con `dry_run`, sólo la
    vista previa."""
    return await _operar("replace", user_id, payload, current_user, company)
