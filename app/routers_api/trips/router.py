"""
API del viaje del supervisor.

Todo endpoint exige `route.worksession.execute`: ejecutar trabajo de campo es
una sola autorización, y el viaje es parte de ese trabajo. No se inventa una
capacidad nueva por tener un dominio nuevo — eso concedería autoridad sobre
algo que ya estaba cubierto.

Ningún endpoint acepta de quién es el viaje: la propiedad se resuelve contra la
jornada del usuario autenticado. Un identificador de otro supervisor o de otro
tenant responde 404, no 403: no se confirma que exista.

`Idempotency-Key` reutiliza el mecanismo de `app/core/integration/idempotency.py`,
el mismo que la jornada, para que la cola offline de RTE03 pueda reenviar una
acción de viaje sin repetir la escritura.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.core.integration import idempotency
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.trips.dao import TripPurposeChangesDAO
from app.routers_api.trips.schemas import (
    TripPlan,
    TripPurposeChangeRead,
    TripRead,
    TripTransition,
)
from app.routers_api.trips.service import TripService
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/trips", tags=["Route · Trips"])

_SCOPE_CREATE = "route.trip.create"
_SCOPE_START = "route.trip.start"
_SCOPE_ARRIVE = "route.trip.arrive"


@router.post("")
async def plan_trip(
    request: Request,
    payload: TripPlan,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> TripRead:
    """Crea el viaje en planificación, dentro de la jornada abierta.

    Si ya hay un viaje vivo devuelve **ese**, sin crear otro: es lo que hace la
    acción segura frente a un reenvío de la cola y frente a un segundo
    dispositivo.
    """
    cuerpo = await request.body()

    if idempotency_key:
        previa = await idempotency.claim(
            scope=_SCOPE_CREATE,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
        )
        if previa.replay:
            return JSONResponse(status_code=previa.status, content=previa.body)

    viaje, _creado = await TripService.create(
        company_id=company.id,
        user_id=current_user.id,
        purpose=payload.purpose.value,
        context_reference=payload.context_reference,
        standard_value_id=payload.standard_value_id,
        device_captured_at=payload.device_captured_at,
        utc_offset_minutes=payload.utc_offset_minutes,
        client_action_key=idempotency_key,
    )
    resultado = TripRead.model_validate(viaje)

    if idempotency_key:
        await idempotency.remember(
            scope=_SCOPE_CREATE,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
            status_code=status.HTTP_200_OK,
            body=resultado.model_dump(mode="json"),
        )

    return resultado


@router.post("/{trip_id}/start")
async def start_trip(
    trip_id: int,
    request: Request,
    payload: TripTransition | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> TripRead:
    """`PLANNING → IN_TRANSIT`.

    Rechaza el arranque si la jornada usa vehículo y la lectura inicial del
    odómetro sigue sin resolverse. La comprobación es del servidor: que la
    pantalla oculte el botón es experiencia de usuario, no un control.
    """
    cuerpo = await request.body()

    if idempotency_key:
        previa = await idempotency.claim(
            scope=_SCOPE_START,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
        )
        if previa.replay:
            return JSONResponse(status_code=previa.status, content=previa.body)

    viaje = await TripService.start(
        company_id=company.id,
        user_id=current_user.id,
        trip_id=trip_id,
        device_captured_at=payload.device_captured_at if payload else None,
        utc_offset_minutes=payload.utc_offset_minutes if payload else None,
    )
    resultado = TripRead.model_validate(viaje)

    if idempotency_key:
        await idempotency.remember(
            scope=_SCOPE_START,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
            status_code=status.HTTP_200_OK,
            body=resultado.model_dump(mode="json"),
        )

    return resultado


_SCOPE_CHANGE_PLAN = "route.trip.change_plan"


@router.post("/{trip_id}/change-plan")
async def change_plan(
    trip_id: int,
    request: Request,
    payload: TripPlan,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> TripRead:
    """Cambia el plan **sin borrar el anterior**. Sólo en tránsito.

    Cada llamada apila una fila de historial. El plan original no se toca
    nunca, y por eso después se puede reconstruir la secuencia completa.

    `Idempotency-Key` desde el cierre final de RTE06
    -------------------------------------------------
    Antes era la única acción del ciclo de vida que se llamaba directamente, sin
    cola y sin clave. Eso impedía dos cosas que el cierre exige: que un cambio
    de plan sobreviva a un corte de red, y que su punto de ubicación se ate a
    **ese** cambio y no a otro del mismo viaje.

    La clave se guarda en `trip_purpose_change.client_action_key`, que es lo que
    mantiene varios cambios individualmente distinguibles al sincronizarse
    juntos. El reenvío no apila una segunda fila: lo impide el índice único
    parcial, no una comprobación previa.
    """
    cuerpo = await request.body()

    if idempotency_key:
        previa = await idempotency.claim(
            scope=_SCOPE_CHANGE_PLAN,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
        )
        if previa.replay:
            return JSONResponse(status_code=previa.status, content=previa.body)

    viaje = await TripService.change_plan(
        company_id=company.id,
        user_id=current_user.id,
        trip_id=trip_id,
        purpose=payload.purpose.value,
        context_reference=payload.context_reference,
        standard_value_id=payload.standard_value_id,
        device_captured_at=payload.device_captured_at,
        client_action_key=idempotency_key,
    )
    resultado = TripRead.model_validate(viaje)

    if idempotency_key:
        await idempotency.remember(
            scope=_SCOPE_CHANGE_PLAN,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
            status_code=200,
            body=resultado.model_dump(mode="json"),
        )

    return resultado


@router.get("/{trip_id}/plan-changes")
async def get_plan_changes(
    trip_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> list[TripPurposeChangeRead]:
    """El historial de cambios de plan de un viaje propio."""
    await TripService._propio(
        company_id=company.id, user_id=current_user.id, trip_id=trip_id
    )
    filas = await TripPurposeChangesDAO.history_for_trip(
        company_id=company.id, trip_id=trip_id
    )
    return [TripPurposeChangeRead.model_validate(fila) for fila in filas]


@router.post("/{trip_id}/arrive")
async def arrive(
    trip_id: int,
    request: Request,
    payload: TripTransition | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> TripRead:
    """Llegar. Un viaje `HOME` cierra aquí; uno operativo se queda en `ARRIVED`.

    No se crea ningún bloque de actividad ni se cierra un viaje operativo: eso
    es RTE05, y fabricarlo sería simular lo que no está construido. Llegar a
    casa **no** termina la jornada.
    """
    cuerpo = await request.body()

    if idempotency_key:
        previa = await idempotency.claim(
            scope=_SCOPE_ARRIVE,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
        )
        if previa.replay:
            return JSONResponse(status_code=previa.status, content=previa.body)

    viaje = await TripService.arrive(
        company_id=company.id,
        user_id=current_user.id,
        trip_id=trip_id,
        device_captured_at=payload.device_captured_at if payload else None,
    )
    resultado = TripRead.model_validate(viaje)

    if idempotency_key:
        await idempotency.remember(
            scope=_SCOPE_ARRIVE,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo,
            status_code=status.HTTP_200_OK,
            body=resultado.model_dump(mode="json"),
        )

    return resultado
