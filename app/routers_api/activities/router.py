"""
API de la ejecución tras la llegada (RTE05).

Comandos, no CRUD
-----------------
Tres verbos, y ninguno expone el bloque como un recurso editable: `start`,
`complete` y `leave` describen lo que ocurre en la calle. Dejarlo abierto a `PUT`
permitiría cambiarle el resultado o la hora después, que es justo lo que un
registro operativo no debe permitir.

Autorización
------------
`route.worksession.execute`, la misma con la que se ejecuta la jornada y el
viaje. No hace falta una capacidad nueva: esto es el trabajo operativo del propio
usuario, y el endpoint nunca acepta la identidad de otro. Los valores
configurados se leen con el contrato que ya existe —`route.standardvalues.read`—,
así que no hay ninguna API paralela de listas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.routers_api.activities.models import TerminalAction
from app.routers_api.activities.schemas import (
    ActivityExecutionRead,
    ActivityStart,
    ActivityTerminalize,
    SelectedActivityRead,
)
from app.routers_api.activities.service import ActivityService
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.trips.dao import TripsDAO
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/trips", tags=["Route · Activity execution"])


async def _viaje_propio(*, company_id: int, user_id: int, trip_id: int):
    """El viaje tiene que ser de quien llama. 404 si no, sin distinguir."""
    viaje = await TripsDAO.get_for_owner(
        trip_id=trip_id, company_id=company_id, user_id=user_id
    )
    if viaje is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
        )
    return viaje


async def _leer(company_id: int, trip_id: int) -> ActivityExecutionRead:
    bloque = await ActivityService.current_for_trip(
        company_id=company_id, trip_id=trip_id
    )
    if bloque is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No activity execution"
        )
    seleccionadas = await ActivityService.activities_of(
        company_id=company_id, execution_id=bloque.id
    )
    lectura = ActivityExecutionRead.model_validate(bloque)
    lectura.activities = [
        SelectedActivityRead.model_validate(a) for a in seleccionadas
    ]
    return lectura


@router.get("/{trip_id}/activity")
async def get_activity_execution(
    trip_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> ActivityExecutionRead:
    """El bloque de esa parada, si existe."""
    await _viaje_propio(
        company_id=company.id, user_id=current_user.id, trip_id=trip_id
    )
    return await _leer(company.id, trip_id)


@router.post("/{trip_id}/activity/start")
async def start_activity(
    trip_id: int,
    payload: ActivityStart,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> ActivityExecutionRead:
    """Empieza el trabajo de la parada. Idempotente: reintentar no duplica."""
    await _viaje_propio(
        company_id=company.id, user_id=current_user.id, trip_id=trip_id
    )
    await ActivityService.start(
        company_id=company.id,
        user_id=current_user.id,
        trip_id=trip_id,
        activity_ids=payload.activity_ids,
        device_captured_at=payload.device_captured_at,
    )
    return await _leer(company.id, trip_id)


@router.post("/{trip_id}/activity/complete")
async def complete_activity(
    trip_id: int,
    payload: ActivityTerminalize,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> ActivityExecutionRead:
    """Termina el trabajo y cierra el viaje. Exige resultado."""
    if payload.action is not TerminalAction.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This endpoint completes; use leave to leave.",
        )
    await _viaje_propio(
        company_id=company.id, user_id=current_user.id, trip_id=trip_id
    )
    await ActivityService.terminalize(
        company_id=company.id,
        user_id=current_user.id,
        trip_id=trip_id,
        action=payload.action.value,
        outcome_id=payload.outcome_id,
        notes=payload.notes,
        received_by_id=payload.received_by_id,
        device_captured_at=payload.device_captured_at,
    )
    return await _leer(company.id, trip_id)


@router.post("/{trip_id}/activity/leave")
async def leave_activity(
    trip_id: int,
    payload: ActivityTerminalize,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> ActivityExecutionRead:
    """Marcharse. Salida **controlada**: exige resultado igual que completar."""
    if payload.action is not TerminalAction.LEAVE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This endpoint leaves; use complete to complete.",
        )
    await _viaje_propio(
        company_id=company.id, user_id=current_user.id, trip_id=trip_id
    )
    await ActivityService.terminalize(
        company_id=company.id,
        user_id=current_user.id,
        trip_id=trip_id,
        action=payload.action.value,
        outcome_id=payload.outcome_id,
        notes=payload.notes,
        received_by_id=payload.received_by_id,
        device_captured_at=payload.device_captured_at,
    )
    return await _leer(company.id, trip_id)
