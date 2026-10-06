"""
El modelo de lectura de Today / Live.

Una sola pasada, no una por supervisor
---------------------------------------
Cada dato se resuelve con **una** consulta para toda la lista: el conjunto de
supervisores, su jornada de hoy, su viaje vigente, su actividad en curso, cuántas
actividades llevan y sus millas oficiales. Seis consultas en total, y las seis
independientes del número de supervisores.

Importa porque la pantalla se refresca sola cada treinta segundos: un patrón
N+1 aquí no sería una ineficiencia de arranque, sería carga permanente que crece
con la plantilla.

Qué día es "hoy"
----------------
El de negocio, no el de UTC. `session_date` se calcula al abrir la jornada
aplicando al instante el **desfase horario que reporta el dispositivo**, y aquí
se usa esa misma evidencia: el desfase más reciente que la compañía haya
reportado. Resolverlo con `CURRENT_DATE` adelantaría el cambio de día cuatro o
cinco horas para una flota americana —a las ocho de la tarde ya sería mañana—,
que es exactamente lo que FR-01 prohíbe.

Sin ninguna jornada previa no hay desfase conocido y se cae a UTC. Es el mismo
límite documentado que el dominio ya acepta al abrir la primera jornada de una
compañía, y se comporta igual: no bloquea nada.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Integer, case, func, select

from app.core.db.session import db_session
from app.routers_api.activities.models import (
    ActivityExecution,
    ActivityExecutionStatus,
)
from app.routers_api.mileage.models import MileageState, TripMileage
from app.routers_api.trips.models import Trip, TripStatus
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import SupervisorProfile, Vehicle
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus

#: Un metro en millas. El millaje oficial se persiste en metros; la pantalla
#: aprobada enseña millas.
MILLAS_POR_METRO = Decimal("0.000621371")


def _iniciales(nombre: str, apellido: str) -> str:
    return f"{(nombre or '?')[:1]}{(apellido or '')[:1]}".upper() or "?"


async def business_day(company_id: int) -> date:
    """El día de negocio vigente para esta compañía."""
    async with db_session() as session:
        desfase = await session.scalar(
            select(WorkSession.start_utc_offset_minutes)
            .where(
                WorkSession.company_id == company_id,
                WorkSession.start_utc_offset_minutes.is_not(None),
            )
            .order_by(WorkSession.started_at.desc())
            .limit(1)
        )

    ahora = datetime.now(timezone.utc)
    if desfase is None:
        return ahora.date()
    return (ahora + timedelta(minutes=int(desfase))).date()


async def today_rows(company_id: int, dia: date) -> list[dict]:
    """Una fila por supervisor autorizado, con todo lo que la pantalla enseña.

    El conjunto de supervisores lo decide **el servidor**. Hoy son todos los
    perfiles activos de la compañía; cuando exista jerarquía organizativa será
    este `where` el que se estreche, sin que la pantalla cambie una línea. Por
    eso el frontend nunca filtra por rol: no sabría hacerlo y no debe.
    """
    async with db_session() as session:
        # ── 1. Supervisores y su jornada de hoy, si la hay ──────────────────
        #
        # `LEFT JOIN`: quien no ha empezado sigue en la lista. FR-09 lo exige y
        # es lo que hace la pantalla útil a primera hora, cuando lo relevante es
        # justo quién **no** ha salido todavía.
        filas = (
            await session.execute(
                select(
                    SupervisorProfile.id.label("perfil_id"),
                    SupervisorProfile.user_id,
                    Users.first_name,
                    Users.last_name,
                    WorkSession.id.label("sesion_id"),
                    WorkSession.status.label("sesion_estado"),
                    WorkSession.started_at,
                    WorkSession.ended_at,
                    WorkSession.vehicle_id,
                    Vehicle.make,
                    Vehicle.model,
                    Vehicle.year,
                    Vehicle.unit,
                    Vehicle.operational_mpg,
                    Vehicle.fuel_grade,
                )
                .join(Users, Users.id == SupervisorProfile.user_id)
                .outerjoin(
                    WorkSession,
                    (WorkSession.user_id == SupervisorProfile.user_id)
                    & (WorkSession.company_id == SupervisorProfile.company_id)
                    & (WorkSession.session_date == dia),
                )
                .outerjoin(
                    Vehicle,
                    (Vehicle.id == WorkSession.vehicle_id)
                    & (Vehicle.company_id == WorkSession.company_id),
                )
                .where(
                    SupervisorProfile.company_id == company_id,
                    SupervisorProfile.is_active.is_(True),
                    SupervisorProfile.deleted_at.is_(None),
                )
                .order_by(Users.first_name, Users.last_name)
            )
        ).all()

        sesiones = [f.sesion_id for f in filas if f.sesion_id is not None]
        if not sesiones:
            return [_fila(f, None, None, 0, Decimal("0"), False) for f in filas]

        # ── 2. El viaje vigente de cada jornada ─────────────────────────────
        #
        # El de mayor `sequence` que no esté terminado. `DISTINCT ON` resuelve
        # las N jornadas de una vez, que es lo que evita el N+1.
        viajes = {
            v.work_session_id: v
            for v in (
                await session.execute(
                    select(
                        Trip.work_session_id,
                        Trip.status,
                        Trip.current_purpose,
                        Trip.current_context_reference,
                        Trip.started_at,
                        Trip.arrived_at,
                    )
                    .where(
                        Trip.company_id == company_id,
                        Trip.work_session_id.in_(sesiones),
                        Trip.status.in_(
                            (TripStatus.IN_TRANSIT.value, TripStatus.ARRIVED.value)
                        ),
                    )
                    .distinct(Trip.work_session_id)
                    .order_by(Trip.work_session_id, Trip.sequence.desc())
                )
            ).all()
        }

        # ── 3. La actividad en curso ────────────────────────────────────────
        actividades = {
            a.work_session_id: a
            for a in (
                await session.execute(
                    select(
                        ActivityExecution.work_session_id,
                        ActivityExecution.started_at,
                    )
                    .where(
                        ActivityExecution.company_id == company_id,
                        ActivityExecution.work_session_id.in_(sesiones),
                        ActivityExecution.status
                        == ActivityExecutionStatus.IN_PROGRESS.value,
                    )
                    .distinct(ActivityExecution.work_session_id)
                    .order_by(
                        ActivityExecution.work_session_id,
                        ActivityExecution.started_at.desc(),
                    )
                )
            ).all()
        }

        # ── 4. Cuántas actividades lleva hoy ────────────────────────────────
        cuentas = dict(
            (
                await session.execute(
                    select(
                        ActivityExecution.work_session_id,
                        func.count(ActivityExecution.id),
                    )
                    .where(
                        ActivityExecution.company_id == company_id,
                        ActivityExecution.work_session_id.in_(sesiones),
                    )
                    .group_by(ActivityExecution.work_session_id)
                )
            ).all()
        )

        # ── 5. Millas oficiales, y si queda algo por calcular ───────────────
        #
        # Sólo `CALCULATED` suma. Un viaje pendiente **no** aporta cero: aporta
        # un aviso de que el total todavía no es final, que es distinto y es lo
        # que FR-05 pide no disimular.
        millaje = {
            m.work_session_id: m
            for m in (
                await session.execute(
                    select(
                        Trip.work_session_id,
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        TripMileage.state
                                        == MileageState.CALCULATED.value,
                                        TripMileage.total_meters,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ).label("metros"),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        TripMileage.state
                                        == MileageState.PENDING_CALCULATION.value,
                                        1,
                                    ),
                                    else_=0,
                                ).cast(Integer)
                            ),
                            0,
                        ).label("pendientes"),
                    )
                    .join(
                        TripMileage,
                        (TripMileage.trip_id == Trip.id)
                        & (TripMileage.company_id == Trip.company_id),
                    )
                    .where(
                        Trip.company_id == company_id,
                        Trip.work_session_id.in_(sesiones),
                    )
                    .group_by(Trip.work_session_id)
                )
            ).all()
        }

    return [
        _fila(
            f,
            viajes.get(f.sesion_id),
            actividades.get(f.sesion_id),
            int(cuentas.get(f.sesion_id, 0)),
            Decimal(str(millaje[f.sesion_id].metros)) * MILLAS_POR_METRO
            if f.sesion_id in millaje
            else Decimal("0"),
            bool(f.sesion_id in millaje and millaje[f.sesion_id].pendientes),
        )
        for f in filas
    ]


def _fila(f, viaje, actividad, actividades: int, millas: Decimal, pendiente: bool) -> dict:
    """Traduce los hechos de dominio al estado visible que V0.7 aprobó.

    El orden de las ramas **es** la regla, y no es arbitrario: estar en una
    actividad es más específico que estar en un viaje, porque una actividad
    ocurre dentro del viaje que ya llegó. Preguntar primero por el viaje
    enseñaría "On Route" a quien está trabajando en el destino.
    """
    if f.sesion_id is None:
        estado, desde = "not_started", None
    elif f.sesion_estado == WorkSessionStatus.ENDED.value:
        estado, desde = "ended", f.ended_at
    elif actividad is not None:
        estado, desde = "activity", actividad.started_at
    elif viaje is not None and viaje.status == TripStatus.IN_TRANSIT.value:
        estado, desde = "route", viaje.started_at
    else:
        # Jornada abierta sin viaje en tránsito ni actividad en curso: llegó y
        # todavía no empezó, o cerró una y aún no ha salido. V0.7 lo llama
        # "Working" y no distingue más.
        estado = "working"
        desde = (viaje.arrived_at if viaje is not None else None) or f.started_at

    vehiculo = (
        f"{f.year} {f.make} {f.model} · {f.unit}"
        if f.sesion_id is not None and f.make is not None
        else None
    )

    return {
        "supervisor_profile_id": f.perfil_id,
        "user_id": f.user_id,
        "name": f"{f.first_name} {f.last_name}".strip(),
        "initials": _iniciales(f.first_name, f.last_name),
        "status": estado,
        "since": desde,
        "vehicle_label": vehiculo,
        "activity_label": viaje.current_purpose if viaje is not None else None,
        "activity_reference": (
            viaje.current_context_reference if viaje is not None else None
        ),
        "official_miles": millas.quantize(Decimal("0.1")),
        "mileage_pending": pendiente,
        "activities_today": actividades,
        "operational_mpg": f.operational_mpg,
        "fuel_grade": f.fuel_grade,
    }
