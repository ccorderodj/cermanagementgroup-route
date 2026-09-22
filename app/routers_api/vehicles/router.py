"""
API de vehículos, perfiles de supervisor y asignaciones (CER Route).

Handlers finos: petición -> schema -> servicio -> respuesta. La compañía sale
siempre de `get_company_required` —del subdominio, nunca del cuerpo— y la
autorización la exige el servidor en cada endpoint.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import TypeAdapter

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions
from app.routers_api.vehicles.dao import (
    SupervisorProfilesDAO,
    VehicleAssignmentsDAO,
    VehiclesDAO,
)
from app.routers_api.vehicles.schemas import (
    SupervisorProfileCreate,
    SupervisorProfileRead,
    VehicleAssignmentCreate,
    VehicleAssignmentEnd,
    VehicleAssignmentRead,
    VehicleCreate,
    VehicleRead,
    VehiclesPaginationParams,
    VehicleUpdate,
)
from app.routers_api.vehicles.service import (
    SupervisorProfileService,
    VehicleAssignmentService,
    VehicleService,
)


router = APIRouter(prefix="/vehicles", tags=["Route · Vehicles"])

supervisors_router = APIRouter(
    prefix="/supervisors", tags=["Route · Supervisors"]
)


# ── Vehículos ───────────────────────────────────────────────────────────────


@router.get("")
async def list_vehicles(
    _authz: None = Depends(require_permissions(["route.vehicles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[VehicleRead]:
    """Vehículos activos, para los desplegables de asignación."""
    page = await VehiclesDAO.paginate(
        page=1, page_size=500, company_id=company.id, is_active=True
    )
    return [VehicleRead.model_validate(fila) for fila in page.items]


@router.get("/pagination")
async def get_vehicles_pagination(
    request: Request,
    params: VehiclesPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["route.vehicles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[VehicleRead]:
    page = await VehiclesDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=company.id,
        search=params.search,
        is_active=params.is_active,
        fuel_grade=params.fuel_grade,
    )
    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=[VehicleRead.model_validate(fila) for fila in page.items],
        request=request,
    )
    return schema.PaginatedResponse[VehicleRead](**paginator.to_response())


@router.get("/{vehicle_id}")
async def get_vehicle(
    vehicle_id: int,
    _authz: None = Depends(require_permissions(["route.vehicles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleRead:
    vehiculo = await VehiclesDAO.get_for_company(
        vehicle_id=vehicle_id, company_id=company.id
    )
    return VehicleRead.model_validate(vehiculo)


@router.post("")
async def create_vehicle(
    payload: VehicleCreate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleRead:
    vehiculo = await VehicleService.create(
        company_id=company.id,
        actor_user_id=current_user.id,
        values=payload.model_dump(),
    )
    return VehicleRead.model_validate(vehiculo)


@router.put("/{vehicle_id}")
async def update_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleRead:
    datos = payload.model_dump(exclude_unset=True)
    version = datos.pop("version", None)
    vehiculo = await VehicleService.update(
        company_id=company.id,
        vehicle_id=vehicle_id,
        actor_user_id=current_user.id,
        values=datos,
        expected_version=version,
    )
    return VehicleRead.model_validate(vehiculo)


@router.post("/{vehicle_id}/deactivate")
async def deactivate_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate | None = None,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleRead:
    """Retira el vehículo. No hay borrado: se conserva por la historia."""
    vehiculo = await VehicleService.set_active(
        company_id=company.id,
        vehicle_id=vehicle_id,
        actor_user_id=current_user.id,
        is_active=False,
        expected_version=payload.version if payload else None,
    )
    return VehicleRead.model_validate(vehiculo)


@router.post("/{vehicle_id}/activate")
async def activate_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate | None = None,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleRead:
    vehiculo = await VehicleService.set_active(
        company_id=company.id,
        vehicle_id=vehicle_id,
        actor_user_id=current_user.id,
        is_active=True,
        expected_version=payload.version if payload else None,
    )
    return VehicleRead.model_validate(vehiculo)


# ── Supervisores y sus asignaciones ─────────────────────────────────────────


async def _leer_perfil(fila: dict, company_id: int) -> SupervisorProfileRead:
    perfil = SupervisorProfileRead.model_validate(fila)
    vehiculo = await VehicleAssignmentService.current_vehicle(
        company_id=company_id, supervisor_profile_id=perfil.id
    )
    perfil.current_vehicle = (
        VehicleRead.model_validate(vehiculo) if vehiculo else None
    )
    return perfil


@supervisors_router.get("")
async def list_supervisors(
    _authz: None = Depends(require_permissions(["route.vehicles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[SupervisorProfileRead]:
    """Supervisores de Route con su vehículo vigente.

    El vehículo se **deriva** de la asignación abierta; no hay copia en el
    perfil que pueda haberse quedado atrás.
    """
    filas = await SupervisorProfilesDAO.list_with_identity(company_id=company.id)
    return [await _leer_perfil(fila, company.id) for fila in filas]


@supervisors_router.post("")
async def create_supervisor_profile(
    payload: SupervisorProfileCreate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> SupervisorProfileRead:
    """Designa supervisor de Route a un usuario que ya pertenece a la compañía."""
    perfil = await SupervisorProfileService.create(
        company_id=company.id,
        actor_user_id=current_user.id,
        user_id=payload.user_id,
    )
    filas = await SupervisorProfilesDAO.list_with_identity(company_id=company.id)
    fila = next(f for f in filas if f["id"] == perfil.id)
    return await _leer_perfil(fila, company.id)


@supervisors_router.get("/me")
async def get_my_supervisor_profile(
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
) -> SupervisorProfileRead | None:
    """El perfil del supervisor que llama, con su vehículo vigente.

    **Sin capacidad, sólo sesión**: son sus propios datos, igual que
    `/users/profile`. Exigir `route.vehicles.read` obligaría a dar al rol
    Supervisor un permiso de administración de vehículos para que pudiera ver
    cuál conduce él, que es justo lo contrario de privilegio mínimo.

    Devuelve `null` si quien llama no es supervisor de Route en esta compañía.
    Es un estado normal —un administrador abriendo la pantalla—, no un error.
    """
    perfil = await SupervisorProfilesDAO.find_by_user(
        company_id=company.id, user_id=current_user.id
    )
    if perfil is None:
        return None

    filas = await SupervisorProfilesDAO.list_with_identity(company_id=company.id)
    fila = next(f for f in filas if f["id"] == perfil.id)
    return await _leer_perfil(fila, company.id)


@supervisors_router.get("/{supervisor_profile_id}/assignments")
async def get_assignment_history(
    supervisor_profile_id: int,
    _authz: None = Depends(require_permissions(["route.vehicles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[VehicleAssignmentRead]:
    """Historial completo. Las asignaciones cerradas no desaparecen."""
    await SupervisorProfilesDAO.get_for_company(
        supervisor_profile_id=supervisor_profile_id, company_id=company.id
    )
    filas = await VehicleAssignmentsDAO.history_for_supervisor(
        company_id=company.id, supervisor_profile_id=supervisor_profile_id
    )
    return TypeAdapter(list[VehicleAssignmentRead]).validate_python(filas)


@supervisors_router.post("/{supervisor_profile_id}/assignments")
async def assign_vehicle(
    supervisor_profile_id: int,
    payload: VehicleAssignmentCreate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleAssignmentRead:
    """Asigna vehículo, cerrando la asignación anterior si la había."""
    asignacion = await VehicleAssignmentService.assign(
        company_id=company.id,
        supervisor_profile_id=supervisor_profile_id,
        vehicle_id=payload.vehicle_id,
        actor_user_id=current_user.id,
        effective_from=payload.effective_from,
    )
    return VehicleAssignmentRead.model_validate(asignacion)


@supervisors_router.post("/assignments/{assignment_id}/end")
async def end_assignment(
    assignment_id: int,
    payload: VehicleAssignmentEnd | None = None,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.vehicles.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> VehicleAssignmentRead:
    asignacion = await VehicleAssignmentService.end(
        company_id=company.id,
        assignment_id=assignment_id,
        actor_user_id=current_user.id,
        effective_to=payload.effective_to if payload else None,
    )
    return VehicleAssignmentRead.model_validate(asignacion)
