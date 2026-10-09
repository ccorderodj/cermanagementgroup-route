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

Qué día es "hoy" — el de **cada** supervisor (T-1/T-2)
------------------------------------------------------
Antes había un solo día para toda la compañía, y lo decidía el desfase de la
última jornada iniciada por **cualquiera**: un supervisor en otra zona cambiaba
la fecha de todos, y sin desfases se caía a UTC —a las ocho de la tarde en el
Este ya era mañana—.

Ahora cada fila tiene su propio día, calculado con la zona de referencia de esa
persona (`worksessions.time_zones.zonas_de_referencia`): su override, o la zona
efectiva de su última jornada que la registró. Si no hay ninguna, su día es
**indeterminado** y se dice así; no se le presta la zona de otro ni se le
presenta UTC como si fuera su hora (D3).

Una jornada **activa** se enseña aunque su `session_date` sea anterior —una
jornada nocturna no desaparece a medianoche (D4)—, pero sus métricas siguen
siendo de su día: Today suma sólo las jornadas cuya `session_date` es el día
local de esa persona, y no traslada millas ni actividades al día siguiente.

Una fila por supervisor, no por jornada (H-2)
----------------------------------------------
El modelo permite varias jornadas por persona y día —el índice único es parcial
sobre `status = 'active'`, así que las cerradas se repiten cuantas veces haga
falta— y esta pantalla asumía una. La consulta devolvía una fila por jornada con
identificadores idénticos, de modo que la persona salía dos veces, sus millas se
partían y el panel mostraba la primera.

`_consolidar` agrupa por `user_id` antes de devolver: **suma** lo que pertenece
al día (millas, actividades, viajes sin cifra) y **elige** lo que describe un
instante (estado, `since`, vehículo, contexto del viaje), tomando la jornada
activa o, si no la hay, la última iniciada.

"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Integer, func, or_, select, tuple_

from app.core.db.session import db_session
from app.routers_api.activities.models import (
    ActivityExecution,
    ActivityExecutionStatus,
)
from app.routers_api.mileage.models import TripMileage
from app.routers_api.mileage.read import (
    metros_calculados,
    millas_oficiales,
    pendientes,
    sin_resolver,
)
from app.routers_api.trips.models import Trip, TripStatus
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import SupervisorProfile, Vehicle
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus
from app.routers_api.worksessions.time_zones import (
    ORIGEN_INDETERMINADA,
    dia_local,
    zonas_de_referencia,
)

def _iniciales(nombre: str, apellido: str) -> str:
    return f"{(nombre or '?')[:1]}{(apellido or '')[:1]}".upper() or "?"


async def today_rows(company_id: int, ahora: datetime) -> list[dict]:
    """Una fila por supervisor autorizado, con todo lo que la pantalla enseña.

    El conjunto de supervisores lo decide **el servidor**. Hoy son todos los
    perfiles activos de la compañía; cuando exista jerarquía organizativa será
    este `where` el que se estreche, sin que la pantalla cambie una línea. Por
    eso el frontend nunca filtra por rol: no sabría hacerlo y no debe.

    `ahora` es un instante, no una fecha: cada supervisor lo convierte a **su**
    día con su propia zona (T-1/T-2).
    """
    async with db_session() as session:
        # ── 1. Supervisores ─────────────────────────────────────────────────
        perfiles = (
            await session.execute(
                select(
                    SupervisorProfile.id.label("perfil_id"),
                    SupervisorProfile.user_id,
                    Users.first_name,
                    Users.last_name,
                )
                .join(Users, Users.id == SupervisorProfile.user_id)
                .where(
                    SupervisorProfile.company_id == company_id,
                    SupervisorProfile.is_active.is_(True),
                    SupervisorProfile.deleted_at.is_(None),
                )
                .order_by(Users.first_name, Users.last_name)
            )
        ).all()
        usuarios = [p.user_id for p in perfiles]

        # La jornada activa de cada uno, si la hay: se enseña aunque sea de
        # ayer (D4), y para quien no tiene zona determinable su fecha es la
        # única fecha operativa que existe como hecho registrado.
        activas = dict(
            (
                await session.execute(
                    select(WorkSession.user_id, WorkSession.session_date).where(
                        WorkSession.company_id == company_id,
                        WorkSession.user_id.in_(usuarios),
                        WorkSession.status == WorkSessionStatus.ACTIVE.value,
                    )
                )
            ).all()
        ) if usuarios else {}

    zonas = await zonas_de_referencia(company_id=company_id, user_ids=usuarios)
    dias: dict[int, date | None] = {}
    for user_id in usuarios:
        zona, _origen = zonas[user_id]
        if zona is not None:
            dias[user_id] = dia_local(ahora, zona)
        else:
            # Zona indeterminada: no se inventa un «hoy». Si está trabajando,
            # sus métricas son las de la fecha de su jornada en curso; si no,
            # no hay ningún día que se pueda afirmar.
            dias[user_id] = activas.get(user_id)
    pares = [(u, d) for u, d in dias.items() if d is not None]

    async with db_session() as session:
        # ── 2. Su jornada de su día, y la activa aunque sea de otro ─────────
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
                    WorkSession.session_date,
                    WorkSession.started_at,
                    WorkSession.ended_at,
                    WorkSession.start_time_zone,
                    WorkSession.start_utc_offset_minutes,
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
                    & or_(
                        tuple_(WorkSession.user_id, WorkSession.session_date).in_(
                            pares
                        ),
                        WorkSession.status == WorkSessionStatus.ACTIVE.value,
                    ),
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
            return _consolidar(filas, {}, {}, {}, {}, dias, zonas)

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
                            func.sum(metros_calculados()), 0
                        ).label("metros"),
                        func.coalesce(
                            func.sum(pendientes().cast(Integer)), 0
                        ).label("pendientes"),
                        func.coalesce(
                            func.sum(sin_resolver().cast(Integer)), 0
                        ).label("sin_resolver"),
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

    return _consolidar(filas, viajes, actividades, cuentas, millaje, dias, zonas)


def _representante(grupo: list):
    """La jornada que describe el estado operativo del supervisor ahora mismo.

    La **activa** si la hay; si no, la **última** por hora de inicio. No es una
    preferencia estética: con dos jornadas el mismo día, una cerrada por la
    mañana y otra en curso, lo que describe a esa persona es la que está
    abierta. Enseñar la cerrada —que es lo que hacía la pantalla, por quedarse
    con la primera fila— decía «Work Ended» de alguien que estaba conduciendo.

    `started_at` nunca es nulo en una jornada creada (`server_default=now()`),
    pero el orden se defiende igualmente contra el nulo: sin eso, un `None` en
    la comparación tumbaría la pantalla entera en vez de degradar una fila.
    """
    activas = [f for f in grupo if f.sesion_estado == WorkSessionStatus.ACTIVE.value]
    candidatas = activas or grupo
    return max(
        candidatas,
        key=lambda f: (f.started_at is not None, f.started_at or datetime.min),
    )


def _consolidar(
    filas, viajes, actividades, cuentas, millaje, dias, zonas
) -> list[dict]:
    """Una fila por **supervisor**, no por jornada (H-2).

    Por qué hacía falta
    -------------------
    El `LEFT JOIN` de arriba no limita a una jornada, y el modelo permite varias
    por día a propósito —`uq_work_session_one_active` es parcial sobre
    `status = 'active'`, así que las cerradas se repiten—. Una persona con dos
    jornadas salía dos veces, con identificadores idénticos, y la pantalla no
    podía distinguirlas: seleccionaba por `user_id` y se quedaba con la primera.

    Lo que se suma y lo que se elige
    --------------------------------
    * **Se suma** lo que es del día: millas oficiales, actividades y viajes sin
      cifra. Un supervisor que condujo en dos jornadas recorrió la suma, y
      enseñar sólo una parte bajo el rótulo «miles today» es afirmar un dato
      falso.
    * **Se elige** lo que describe un instante: estado, `since`, vehículo y el
      contexto del viaje. Sumarlos no significaría nada.

    `mileage_pending` es un **O lógico**: si cualquier jornada del día tiene un
    viaje sin calcular, el total todavía no es final.

    Qué jornadas suman (T-1/T-2, D4)
    --------------------------------
    Sólo las de **su** día (`dias[user_id]`). La activa de ayer —una jornada
    nocturna que cruzó medianoche— describe el estado de la persona y por eso
    puede ser la representante, pero sus millas y actividades son de su
    `session_date` y no se trasladan a hoy.
    """
    por_usuario: dict[int, list] = {}
    for f in filas:
        por_usuario.setdefault(f.user_id, []).append(f)

    consolidadas: list[dict] = []
    for user_id, grupo in por_usuario.items():
        elegida = _representante(grupo)
        dia = dias.get(user_id)
        # Sólo las jornadas reales **de su día** suman. El `LEFT JOIN` deja una
        # fila con `sesion_id` nulo a quien no ha empezado hoy, y esa no es una
        # jornada de cero: es la ausencia de jornada.
        sesiones_del_dia = [
            f.sesion_id
            for f in grupo
            if f.sesion_id is not None and f.session_date == dia
        ]
        zona_referencia, origen = zonas.get(user_id, (None, ORIGEN_INDETERMINADA))

        metros = sum(
            (millaje[s].metros for s in sesiones_del_dia if s in millaje),
            0,
        )
        consolidadas.append(
            _fila(
                elegida,
                viajes.get(elegida.sesion_id),
                actividades.get(elegida.sesion_id),
                sum(int(cuentas.get(s, 0)) for s in sesiones_del_dia),
                millas_oficiales(metros if sesiones_del_dia else None),
                any(
                    bool(millaje[s].pendientes)
                    for s in sesiones_del_dia
                    if s in millaje
                ),
                sum(
                    int(millaje[s].sin_resolver)
                    for s in sesiones_del_dia
                    if s in millaje
                ),
            )
            | {
                # La fecha operativa de esta fila, y la zona con que se
                # formatean sus horas: la de **la jornada** que describe el
                # estado, que es la que registró esos instantes; sin jornada,
                # la de referencia de la persona.
                "session_date": dia,
                "time_zone": (
                    elegida.start_time_zone
                    if elegida.sesion_id is not None
                    else zona_referencia
                ),
                "utc_offset_minutes": (
                    elegida.start_utc_offset_minutes
                    if elegida.sesion_id is not None
                    else None
                ),
                "time_zone_determined": origen != ORIGEN_INDETERMINADA,
            }
        )

    # El orden lo fija la consulta (nombre, apellido). Agrupar por un
    # diccionario lo conserva —Python 3.7+ mantiene el orden de inserción— y
    # aquí se deja escrito para que nadie lo reordene por descuido.
    return consolidadas


def _fila(
    f,
    viaje,
    actividad,
    actividades: int,
    millas: Decimal,
    pendiente: bool,
    sin_cifra: int = 0,
) -> dict:
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
        #: Viajes del dia que terminaron **sin** kilometraje: falto
        #: evidencia, o el routing agoto su reintento. Cero no es lo mismo
        #: que no haber conducido, y hasta ahora se dibujaban igual.
        "mileage_unresolved": sin_cifra,
        "activities_today": actividades,
        "operational_mpg": f.operational_mpg,
        "fuel_grade": f.fuel_grade,
    }
