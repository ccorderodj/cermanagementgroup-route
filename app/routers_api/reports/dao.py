"""
Los hechos de Reports: una fila por **viaje** del periodo (RTE09).

Una sola fuente para todo
-------------------------
Los KPIs, la tarjeta *By day / By week / By month*, el *Activity Breakdown* y el
Excel salen **de estas mismas filas**. No hay una consulta para la pantalla y
otra para la exportación: dos caminos acabarían diciendo cosas distintas.

Por qué una fila por viaje
--------------------------
Es el grano donde nada se repite. Un viaje tiene **un** kilometraje y **como
mucho un** bloque de actividad (`uq_activity_execution_trip`), así que unir el
viaje con su kilometraje y su bloque no multiplica nada. Las actividades
seleccionadas —que sí pueden ser varias por bloque— se leen **aparte** y se
pegan en Python: unirlas aquí multiplicaría las millas y la duración por cada
etiqueta, que es justo lo que RTE09 prohíbe.

Los tramos del kilometraje (`trip_mileage_segment`) no se leen: son la
procedencia del total, no millas adicionales.

Mismas reglas que el resto del producto
---------------------------------------
* Millas: `metros_calculados()` de `mileage/read.py`, la misma expresión que
  Today / Live y el explorador. Pendientes y sin cifra aportan 0 **a la suma** y
  se informan aparte.
* Tiempo de actividad: `_duracion_segundos()` del explorador —sólo bloques
  terminados—.
* Día de negocio: `work_session.session_date`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.db.session import db_session
from app.routers_api.activities.models import (
    ActivityExecution,
    ActivityExecutionActivity,
)
from app.routers_api.activityexplorer.dao import _duracion_segundos
from app.routers_api.mileage.models import TripMileage
from app.routers_api.mileage.read import metros_calculados, pendientes, sin_resolver
from app.routers_api.trips.models import Trip
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import Vehicle
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus


async def hechos(
    *, company_id: int, user_ids: list[int], inicio: date, fin: date
) -> list[dict]:
    """Los viajes de esos supervisores con `session_date` en el periodo."""
    if not user_ids:
        return []

    async with db_session() as session:
        filas = (
            await session.execute(
                select(
                    Trip.id.label("trip_id"),
                    Trip.current_purpose.label("purpose"),
                    Trip.current_context_reference.label("reference"),
                    Trip.started_at.label("trip_started_at"),
                    Trip.arrived_at,
                    WorkSession.id.label("session_id"),
                    WorkSession.user_id,
                    WorkSession.session_date,
                    WorkSession.status.label("session_status"),
                    WorkSession.mpg_snapshot,
                    WorkSession.fuel_grade_snapshot,
                    WorkSession.operational_state_snapshot,
                    WorkSession.start_time_zone,
                    WorkSession.start_utc_offset_minutes,
                    Users.first_name,
                    Users.last_name,
                    Vehicle.make,
                    Vehicle.model,
                    Vehicle.year,
                    Vehicle.unit,
                    TripMileage.state.label("mileage_state"),
                    metros_calculados().label("metros"),
                    pendientes().label("pendiente"),
                    sin_resolver().label("sin_cifra"),
                    ActivityExecution.id.label("execution_id"),
                    ActivityExecution.started_at.label("activity_started_at"),
                    ActivityExecution.ended_at.label("activity_ended_at"),
                    ActivityExecution.outcome_label,
                    ActivityExecution.notes,
                    _duracion_segundos().label("segundos"),
                )
                .select_from(Trip)
                .join(
                    WorkSession,
                    (WorkSession.id == Trip.work_session_id)
                    & (WorkSession.company_id == Trip.company_id),
                )
                .join(Users, Users.id == WorkSession.user_id)
                .outerjoin(
                    Vehicle,
                    (Vehicle.id == WorkSession.vehicle_id)
                    & (Vehicle.company_id == WorkSession.company_id),
                )
                .outerjoin(
                    TripMileage,
                    (TripMileage.trip_id == Trip.id)
                    & (TripMileage.company_id == Trip.company_id),
                )
                .outerjoin(
                    ActivityExecution,
                    (ActivityExecution.trip_id == Trip.id)
                    & (ActivityExecution.company_id == Trip.company_id),
                )
                .where(
                    Trip.company_id == company_id,
                    WorkSession.user_id.in_(user_ids),
                    WorkSession.session_date >= inicio,
                    WorkSession.session_date <= fin,
                )
                .order_by(
                    WorkSession.session_date,
                    Users.first_name,
                    Users.last_name,
                    Trip.started_at,
                    Trip.id,
                )
            )
        ).all()

        ejecuciones = [f.execution_id for f in filas if f.execution_id is not None]
        etiquetas: dict[int, list[str]] = {}
        if ejecuciones:
            for e in (
                await session.execute(
                    select(
                        ActivityExecutionActivity.activity_execution_id,
                        ActivityExecutionActivity.label,
                    )
                    .where(
                        ActivityExecutionActivity.company_id == company_id,
                        ActivityExecutionActivity.activity_execution_id.in_(ejecuciones),
                    )
                    .order_by(
                        ActivityExecutionActivity.activity_execution_id,
                        ActivityExecutionActivity.label,
                        ActivityExecutionActivity.id,
                    )
                )
            ).all():
                etiquetas.setdefault(e.activity_execution_id, []).append(e.label)

    return [
        {
            "trip_id": f.trip_id,
            "purpose": f.purpose,
            "reference": f.reference,
            "trip_started_at": f.trip_started_at,
            "arrived_at": f.arrived_at,
            "session_id": f.session_id,
            "user_id": f.user_id,
            "supervisor_name": f"{f.first_name or ''} {f.last_name or ''}".strip()
            or f"User {f.user_id}",
            "session_date": f.session_date,
            "session_ended": f.session_status == WorkSessionStatus.ENDED.value,
            "mpg": f.mpg_snapshot,
            "fuel_grade": f.fuel_grade_snapshot,
            "operational_state": f.operational_state_snapshot,
            "time_zone": f.start_time_zone,
            "utc_offset_minutes": f.start_utc_offset_minutes,
            "vehicle_label": (
                f"{f.year} {f.make} {f.model} · {f.unit}" if f.make is not None else None
            ),
            "mileage_state": f.mileage_state,
            "metros": f.metros,
            "pendiente": bool(f.pendiente),
            "sin_cifra": bool(f.sin_cifra),
            "execution_id": f.execution_id,
            "activity_started_at": f.activity_started_at,
            "activity_ended_at": f.activity_ended_at,
            "outcome_label": f.outcome_label,
            "notes": f.notes,
            "segundos": int(f.segundos or 0),
            "activity_labels": etiquetas.get(f.execution_id, []),
        }
        for f in filas
    ]
