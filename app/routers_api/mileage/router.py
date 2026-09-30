"""Lectura del kilometraje y su provenance (RTE06-CP3, §31 y §33).

Lo que hay y lo que no
----------------------
Hay lectura del estado y del resultado de un viaje, lectura de la provenance
ordenada, reintento interno y suma de la jornada. **No** hay pantalla: §33 dice
expresamente que Today/Live no se implementa aquí, y §6 saca de alcance la UI de
Reports y el Activity Explorer. Estos endpoints existen para que RTE07 tenga un
contrato estable al que llamar.

La suma de la jornada no miente sobre lo que no sabe
----------------------------------------------------
§33: "do not present a partial sum as if the Work Session were fully resolved".
Así que la respuesta lleva la suma **y** el recuento de viajes sin resolver y en
excepción. Un cliente que sólo lea `total_miles` estaría leyendo una verdad
parcial, y por eso `fully_resolved` viene calculado al lado.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.core.db.session import db_session
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.mileage.models import (
    MileageState,
    TripMileage,
    TripMileageSegment,
)
from app.routers_api.mileage.service import MileageService, miles_from_meters
from app.routers_api.trips.models import Trip
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions
from app.routers_api.worksessions.models import WorkSession

router = APIRouter(prefix="/mileage", tags=["Route Mileage"])

EJECUTA = Depends(require_permissions(["route.worksession.execute"]))


class TripMileageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trip_id: int
    state: str
    total_meters: Decimal | None = None
    total_miles: Decimal | None = None
    calculated_at: datetime | None = None
    terminal_reason: str | None = None
    #: Cuántas veces se ha intentado. Diagnóstico, no dato de negocio.
    attempt_count: int = 0


class SegmentRead(BaseModel):
    """Un tramo, con todo lo que §23 exige poder auditar."""

    model_config = ConfigDict(from_attributes=True)

    sequence: int
    from_event_kind: str
    from_latitude: Decimal
    from_longitude: Decimal
    from_evidence_level: str
    from_accuracy_m: Decimal | None = None
    from_captured_at: datetime
    to_event_kind: str
    to_latitude: Decimal
    to_longitude: Decimal
    to_evidence_level: str
    to_accuracy_m: Decimal | None = None
    to_captured_at: datetime
    distance_meters: Decimal
    distance_miles: Decimal | None = None
    provider: str
    method: str
    provider_version: str | None = None
    computed_at: datetime


class SessionMileageRead(BaseModel):
    """La suma de la jornada, con lo que le falta declarado."""

    work_session_id: int
    calculated_trips: int
    calculated_meters: Decimal
    calculated_miles: Decimal
    pending_trips: int
    not_calculable_trips: int
    calculation_failed_trips: int
    #: `False` si queda algún viaje pendiente o en excepción. Es lo que impide
    #: leer la suma como si fuera el total definitivo del día (§33).
    fully_resolved: bool


async def _kilometraje_propio(
    *, company_id: int, trip_id: int, user_id: int
) -> TripMileage:
    """El kilometraje de un viaje del propio supervisor.

    404 cuando no existe, es de otra compañía o es de la jornada de otro: no se
    confirma que exista algo ajeno (regla 8 de backend).
    """
    async with db_session() as sesion:
        fila = (
            await sesion.execute(
                select(TripMileage)
                .join(
                    Trip,
                    (Trip.id == TripMileage.trip_id)
                    & (Trip.company_id == TripMileage.company_id),
                )
                .join(
                    WorkSession,
                    (WorkSession.id == Trip.work_session_id)
                    & (WorkSession.company_id == Trip.company_id),
                )
                .where(
                    TripMileage.company_id == company_id,
                    TripMileage.trip_id == trip_id,
                    WorkSession.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No mileage for that trip."
        )
    return fila


@router.get("/trips/{trip_id}")
async def get_trip_mileage(
    trip_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> TripMileageRead:
    """Estado y resultado oficial del kilometraje de un viaje."""
    fila = await _kilometraje_propio(
        company_id=company.id, trip_id=trip_id, user_id=current_user.id
    )
    salida = TripMileageRead.model_validate(fila)
    return salida.model_copy(
        update={"total_miles": miles_from_meters(fila.total_meters)}
    )


@router.get("/trips/{trip_id}/segments")
async def get_trip_mileage_segments(
    trip_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> list[SegmentRead]:
    """La provenance ordenada: qué se enrutó, con qué evidencia y quién lo midió.

    Sale de `trip_mileage_segment`, no de `location_fix`, y esa diferencia es el
    punto entero de §28: estos tramos siguen respondiendo cuando la evidencia
    cruda ya no exista.
    """
    km = await _kilometraje_propio(
        company_id=company.id, trip_id=trip_id, user_id=current_user.id
    )
    async with db_session() as sesion:
        tramos = (
            await sesion.execute(
                select(TripMileageSegment)
                .where(
                    TripMileageSegment.company_id == company.id,
                    TripMileageSegment.trip_mileage_id == km.id,
                )
                .order_by(TripMileageSegment.sequence)
            )
        ).scalars().all()

    return [
        SegmentRead.model_validate(t).model_copy(
            update={"distance_miles": miles_from_meters(t.distance_meters)}
        )
        for t in tramos
    ]


@router.post("/trips/{trip_id}/recalculate", status_code=status.HTTP_202_ACCEPTED)
async def retry_trip_mileage(
    trip_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> TripMileageRead:
    """Fuerza un intento de cálculo. **No** recalcula lo ya calculado.

    §31 pide poder disparar el cálculo internamente; §27 prohíbe recalcular un
    `calculated`. Las dos cosas conviven porque este endpoint no fuerza nada:
    llama al mismo cálculo, y el cálculo respeta el estado. Un `calculated`
    vuelve tal cual, y un terminal de excepción también — no es un reintento
    manual de excepciones, que pertenecería a la corrección administrativa que
    §27 deja para un alcance posterior.
    """
    km = await _kilometraje_propio(
        company_id=company.id, trip_id=trip_id, user_id=current_user.id
    )
    await MileageService.calculate(mileage_id=km.id)
    actualizado = await _kilometraje_propio(
        company_id=company.id, trip_id=trip_id, user_id=current_user.id
    )
    salida = TripMileageRead.model_validate(actualizado)
    return salida.model_copy(
        update={"total_miles": miles_from_meters(actualizado.total_meters)}
    )


@router.get("/work-sessions/{session_id}")
async def get_session_mileage(
    session_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = EJECUTA,
    company: TenantContext = Depends(get_company_required),
) -> SessionMileageRead:
    """La suma del día, con lo que no está resuelto declarado al lado (§33)."""
    async with db_session() as sesion:
        propia = await sesion.scalar(
            select(WorkSession.id).where(
                WorkSession.id == session_id,
                WorkSession.company_id == company.id,
                WorkSession.user_id == current_user.id,
            )
        )
        if propia is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No such work session."
            )

        filas = (
            await sesion.execute(
                select(
                    TripMileage.state,
                    func.count().label("cuantos"),
                    func.coalesce(func.sum(TripMileage.total_meters), 0).label("metros"),
                )
                .join(
                    Trip,
                    (Trip.id == TripMileage.trip_id)
                    & (Trip.company_id == TripMileage.company_id),
                )
                .where(
                    TripMileage.company_id == company.id,
                    Trip.work_session_id == session_id,
                )
                .group_by(TripMileage.state)
            )
        ).all()

    por_estado = {f.state: (f.cuantos, Decimal(f.metros)) for f in filas}
    calculados, metros = por_estado.get(MileageState.CALCULATED.value, (0, Decimal("0")))
    pendientes = por_estado.get(MileageState.PENDING_CALCULATION.value, (0, Decimal("0")))[0]
    no_calculables = por_estado.get(MileageState.NOT_CALCULABLE.value, (0, Decimal("0")))[0]
    fallidos = por_estado.get(MileageState.CALCULATION_FAILED.value, (0, Decimal("0")))[0]

    return SessionMileageRead(
        work_session_id=session_id,
        calculated_trips=calculados,
        calculated_meters=metros,
        calculated_miles=miles_from_meters(metros) or Decimal("0"),
        pending_trips=pendientes,
        not_calculable_trips=no_calculables,
        calculation_failed_trips=fallidos,
        fully_resolved=(pendientes == 0 and no_calculables == 0 and fallidos == 0),
    )
