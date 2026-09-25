"""
API de la Jornada del supervisor.

Tres endpoints, cada uno con una sola responsabilidad:

* `GET current`   el estado autoritativo — de aquí arranca toda reconexión.
* `POST` (start)  empezar, o confirmar que ya se empezó.
* `POST .../end`  terminar la propia jornada, y solo la propia.

`Idempotency-Key` es opcional y reutiliza el mecanismo existente
(`app/core/integration/idempotency.py`) para la cola de acciones offline: el
dispositivo genera una clave por acción encolada, y reenviarla tras reconectar
devuelve la misma respuesta sin repetir la escritura. Sin la cabecera, el
endpoint sigue siendo seguro frente a duplicados por la propia regla de
negocio (§14 de las instrucciones RTE03 — el mecanismo del encabezado y la
idempotencia del dominio son dos capas, no una alternativa a la otra).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.core.integration import idempotency
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions
from app.routers_api.worksessions.schemas import (
    CurrentWorkSessionResponse,
    WorkSessionEnd,
    WorkSessionRead,
    WorkSessionStart,
)
from app.routers_api.trips.schemas import TripRead
from app.routers_api.trips.service import TripService
from app.routers_api.worksessions.service import WorkSessionService


router = APIRouter(prefix="/worksessions", tags=["Route · Work Sessions"])

_IDEMPOTENCY_SCOPE_START = "route.worksession.start"
_IDEMPOTENCY_SCOPE_END = "route.worksession.end"


@router.get("/current")
async def get_current_work_session(
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
) -> CurrentWorkSessionResponse:
    """El estado del que arranca cualquier reapertura, reconexión o segundo
    dispositivo.

    Devuelve la jornada abierta y, si lo hay, su viaje **vivo**. Un segundo
    dispositivo resuelve exactamente el mismo viaje en vez de crear otro, y una
    recarga o una reautenticación recuperan el mismo estado: esta respuesta es
    la única autoridad, y el cliente nunca se fía de lo que tenga guardado.

    Sin viaje vivo, `current_trip` es `null`. No se inventa un marcador de
    posición, y no se devuelve una Activity: ese dominio es de RTE05 y no
    existe todavía.
    """
    jornada = await WorkSessionService.current(
        company_id=company.id, user_id=current_user.id
    )
    if jornada is None:
        return CurrentWorkSessionResponse()

    viaje = await TripService.current(
        company_id=company.id, work_session_id=jornada.id
    )
    return CurrentWorkSessionResponse(
        work_session=WorkSessionRead.model_validate(jornada),
        current_trip=TripRead.model_validate(viaje) if viaje else None,
    )


@router.post("")
async def start_work(
    request: Request,
    payload: WorkSessionStart | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> WorkSessionRead:
    cuerpo_crudo = await request.body()

    if idempotency_key:
        previa = await idempotency.claim(
            scope=_IDEMPOTENCY_SCOPE_START,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo_crudo,
        )
        if previa.replay:
            return JSONResponse(status_code=previa.status, content=previa.body)

    jornada, _creada = await WorkSessionService.start(
        company_id=company.id,
        user_id=current_user.id,
        device_captured_at=payload.device_captured_at if payload else None,
        utc_offset_minutes=payload.utc_offset_minutes if payload else None,
    )
    resultado = WorkSessionRead.model_validate(jornada)

    if idempotency_key:
        await idempotency.remember(
            scope=_IDEMPOTENCY_SCOPE_START,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo_crudo,
            status_code=status.HTTP_200_OK,
            body=resultado.model_dump(mode="json"),
        )

    return resultado


@router.post("/{session_id}/end")
async def end_work(
    session_id: int,
    request: Request,
    payload: WorkSessionEnd | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    company: TenantContext = Depends(get_company_required),
) -> WorkSessionRead:
    """Termina la jornada del supervisor autenticado. Nunca la de otro:
    `WorkSessionService.end` filtra por `user_id` del token, no por lo que
    diga el cliente."""
    cuerpo_crudo = await request.body()

    if idempotency_key:
        previa = await idempotency.claim(
            scope=_IDEMPOTENCY_SCOPE_END,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo_crudo,
        )
        if previa.replay:
            return JSONResponse(status_code=previa.status, content=previa.body)

    jornada = await WorkSessionService.end(
        company_id=company.id,
        user_id=current_user.id,
        session_id=session_id,
        device_captured_at=payload.device_captured_at if payload else None,
        utc_offset_minutes=payload.utc_offset_minutes if payload else None,
        end_anyway=payload.end_anyway if payload else False,
    )
    resultado = WorkSessionRead.model_validate(jornada)

    if idempotency_key:
        await idempotency.remember(
            scope=_IDEMPOTENCY_SCOPE_END,
            company_id=company.id,
            key=idempotency_key,
            request_body=cuerpo_crudo,
            status_code=status.HTTP_200_OK,
            body=resultado.model_dump(mode="json"),
        )

    return resultado
