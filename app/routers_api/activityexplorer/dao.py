"""
Las lecturas del Activity Explorer. Un nivel por consulta.

Por qué un nivel por consulta y no un árbol de una vez
-------------------------------------------------------
§15 pide que abrir la página no traiga la historia completa del tenant y que
bajar por una rama no traiga las demás. La forma natural de conseguirlo aquí no
es paginar: es **preguntar sólo por el periodo que se está mirando**, que es
exactamente lo que la línea base hace —sus pestañas son un rango, y sus filas
bajan un nivel—. El coste de abrir el explorador es una agregación sobre un año
de una persona, no sobre la historia de la compañía.

El día de negocio es la autoridad del agrupamiento
---------------------------------------------------
Todo se agrupa por `WorkSession.session_date`, que se calculó una vez al abrir
la jornada y nunca se recalcula. Es lo que hace que una parada de la 1:00 AM
siga perteneciendo al día en que se empezó a trabajar (PR-02). Agrupar por la
fecha UTC del evento movería esa parada al día siguiente y el histórico dejaría
de cuadrar con lo que ocurrió.

La semana empieza el lunes, y no es una elección mía
-----------------------------------------------------
Sale de los datos de la propia línea base: sus grupos de mes rompen en `Sep 1–6`,
`Sep 7–13`, `Sep 14–20` y `Sep 21–27`, y el 7, el 14 y el 21 de septiembre de
2026 son lunes. La vista de semana se titula `Sep 14–20` y su primera fila es
`Mon Sep 14`. Las semanas se **recortan al mes** cuando se listan dentro de él,
que es lo que explica ese primer grupo de seis días.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Integer, case, func, select

from app.core.db.session import db_session
from app.routers_api.activities.models import (
    POSTARRIVAL_ACTIVITY_LIST,
    ActivityExecution,
    ActivityExecutionActivity,
    ActivityExecutionStatus,
)
from app.routers_api.mileage.models import MileageState, TripMileage
from app.routers_api.standardvalues.models import StandardValue
from app.routers_api.trips.models import Trip
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import SupervisorProfile
from app.routers_api.worksessions.models import WorkSession

#: Un metro en millas. El millaje oficial se persiste en metros; la pantalla
#: aprobada enseña millas. Es la misma constante que usa Today / Live, y por el
#: mismo motivo: la conversión es de presentación, no un dato que se guarde.
MILLAS_POR_METRO = Decimal("0.000621371")

#: El nivel por el que agrupa cada rango, según `groupRows()` de la línea base.
AGRUPA_POR: dict[str, str] = {"year": "month", "month": "week", "week": "day"}


async def business_day_actual(company_id: int) -> date:
    """El día de negocio vigente, para cuando la petición no trae fecha.

    Se **reutiliza** el de Today / Live en vez de reimplementarlo. Es la misma
    regla —hoy según el desfase local de la compañía— y tener dos versiones de
    ella acabaría con dos respuestas distintas a la misma pregunta, que es
    exactamente lo que el invariante 9 prohíbe. Esto no toca RTE07: sólo lee su
    función.
    """
    from app.routers_api.live.dao import business_day

    return await business_day(company_id)


def periodo(rango: str, ancla: date) -> tuple[date, date]:
    """El primer y el último día del periodo que contiene a `ancla`.

    La semana es lunes–domingo. El año y el mes son naturales. El día es él
    mismo: el explorador no parte un día de negocio en trozos.
    """
    if rango == "year":
        return date(ancla.year, 1, 1), date(ancla.year, 12, 31)
    if rango == "month":
        ultimo = calendar.monthrange(ancla.year, ancla.month)[1]
        return date(ancla.year, ancla.month, 1), date(ancla.year, ancla.month, ultimo)
    if rango == "week":
        lunes = ancla - timedelta(days=ancla.weekday())
        return lunes, lunes + timedelta(days=6)
    return ancla, ancla


def _subperiodos(rango: str, inicio: date, fin: date) -> list[tuple[date, date]]:
    """Los grupos que ese periodo puede contener, en orden cronológico.

    Se recortan al periodo padre a propósito: una semana que empieza en el mes
    anterior se presenta desde el día 1, que es lo que produce el `Sep 1–6` de
    la línea base. Lo que no se hace es moverla de mes.
    """
    if rango == "year":
        return [periodo("month", date(inicio.year, m, 1)) for m in range(1, 13)]

    if rango == "month":
        semanas: list[tuple[date, date]] = []
        cursor = inicio
        while cursor <= fin:
            _, domingo = periodo("week", cursor)
            semanas.append((cursor, min(domingo, fin)))
            cursor = domingo + timedelta(days=1)
        return semanas

    # Semana → días.
    return [
        (inicio + timedelta(days=i), inicio + timedelta(days=i))
        for i in range((fin - inicio).days + 1)
    ]


async def supervisores(company_id: int) -> list[dict]:
    """Las opciones del selector, autorizadas aquí y no en la pantalla.

    Son los perfiles de supervisor **de esta compañía**. El explorador es de
    administración y la lista no se filtra en el navegador: lo que el servidor
    no devuelve, no existe para la pantalla.
    """
    async with db_session() as session:
        filas = (
            await session.execute(
                select(
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
                .order_by(Users.first_name, Users.last_name, SupervisorProfile.user_id)
            )
        ).all()

    return [
        {
            "user_id": f.user_id,
            "name": f"{f.first_name or ''} {f.last_name or ''}".strip()
            or f"User {f.user_id}",
        }
        for f in filas
    ]


def _metros_calculados():
    """Los metros que ya están calculados. Lo pendiente no suma como cero."""
    return case(
        (
            TripMileage.state == MileageState.CALCULATED.value,
            TripMileage.total_meters,
        ),
        else_=0,
    )


def _pendiente():
    return case(
        (TripMileage.state == MileageState.PENDING_CALCULATION.value, 1),
        else_=0,
    )


def _duracion_segundos():
    """Segundos de un bloque **terminado**. Uno en curso no tiene duración.

    Presentar un bloque abierto como de duración cero sería afirmar que no duró
    nada. La vista lo cuenta por separado y la pantalla dice `In progress`,
    igual que la línea base.
    """
    return case(
        (
            ActivityExecution.ended_at.is_not(None),
            func.extract(
                "epoch", ActivityExecution.ended_at - ActivityExecution.started_at
            ),
        ),
        else_=0,
    )


async def agregados_por_dia(
    *, company_id: int, user_id: int, inicio: date, fin: date
) -> dict[date, dict]:
    """Millas, paradas y tiempo de actividad por día de negocio del periodo.

    Una sola consulta agrupada por `session_date` para todo el periodo, se
    pidan meses, semanas o días. Los grupos de un nivel superior se componen
    sumando estos días en Python, que es aritmética sobre un conjunto que ya
    está acotado por el periodo: un año de una persona son 365 filas como
    máximo, y en la práctica las que tuvieron jornada.

    El millaje se cuenta **por viaje** y no por parada: un viaje tiene un
    bloque de actividad como máximo, así que no hay doble conteo, y el
    `outerjoin` deja pasar los viajes sin bloque sin inventarles una.
    """
    async with db_session() as session:
        filas = (
            await session.execute(
                select(
                    WorkSession.session_date.label("dia"),
                    func.coalesce(func.sum(_metros_calculados()), 0).label("metros"),
                    func.coalesce(func.sum(_pendiente()), 0).label("pendientes"),
                    func.coalesce(
                        func.sum(
                            case((ActivityExecution.id.is_not(None), 1), else_=0)
                        ),
                        0,
                    ).label("paradas"),
                    func.coalesce(
                        func.sum(_duracion_segundos()), 0
                    ).label("segundos"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ActivityExecution.status
                                    == ActivityExecutionStatus.IN_PROGRESS.value,
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("abiertos"),
                )
                .select_from(WorkSession)
                .join(
                    Trip,
                    (Trip.work_session_id == WorkSession.id)
                    & (Trip.company_id == WorkSession.company_id),
                )
                .outerjoin(
                    ActivityExecution,
                    (ActivityExecution.trip_id == Trip.id)
                    & (ActivityExecution.company_id == Trip.company_id),
                )
                .outerjoin(
                    TripMileage,
                    (TripMileage.trip_id == Trip.id)
                    & (TripMileage.company_id == Trip.company_id),
                )
                .where(
                    WorkSession.company_id == company_id,
                    WorkSession.user_id == user_id,
                    WorkSession.session_date >= inicio,
                    WorkSession.session_date <= fin,
                )
                .group_by(WorkSession.session_date)
                .order_by(WorkSession.session_date)
            )
        ).all()

    return {
        f.dia: {
            "metros": Decimal(str(f.metros or 0)),
            "pendientes": int(f.pendientes or 0),
            "paradas": int(f.paradas or 0),
            "segundos": int(f.segundos or 0),
            "abiertos": int(f.abiertos or 0),
        }
        for f in filas
    }


def componer_grupos(
    rango: str, inicio: date, fin: date, por_dia: dict[date, dict]
) -> list[dict]:
    """Los grupos visibles del periodo, sin los que no tienen registros.

    La línea base sólo dibuja lo que existe: su semana va de lunes a viernes
    porque el fin de semana no tuvo jornada. Un mes sin actividad no aparece
    como una fila de ceros (FR-02).
    """
    grupos: list[dict] = []

    for sub_inicio, sub_fin in _subperiodos(rango, inicio, fin):
        dias = [
            datos
            for dia, datos in por_dia.items()
            if sub_inicio <= dia <= sub_fin
        ]
        if not dias:
            continue

        metros = sum((d["metros"] for d in dias), Decimal("0"))
        grupos.append(
            {
                "start": sub_inicio,
                "end": sub_fin,
                "drill_date": sub_inicio,
                "official_miles": (metros * MILLAS_POR_METRO).quantize(
                    Decimal("0.1")
                ),
                "mileage_pending": any(d["pendientes"] for d in dias),
                "activities": sum(d["paradas"] for d in dias),
                "activity_seconds": sum(d["segundos"] for d in dias),
                "has_open_activity": any(d["abiertos"] for d in dias),
            }
        )

    return grupos


async def paradas_del_dia(
    *, company_id: int, user_id: int, dia: date
) -> list[dict]:
    """Las paradas de un día de negocio, con el contexto que V0.7 enseña.

    Dos consultas y no una por parada: primero los bloques con su viaje y su
    millaje, después **todas** las actividades seleccionadas de esos bloques de
    una vez. Es el patrón que evita el N+1 cuando un día tiene veinte paradas.

    El orden es por la hora de ocurrencia del bloque y, a igualdad, por su
    identificador: así dos lecturas seguidas devuelven lo mismo, que es lo que
    pide §12 cuando habla de orden determinista.
    """
    async with db_session() as session:
        filas = (
            await session.execute(
                select(
                    ActivityExecution.id,
                    ActivityExecution.trip_id,
                    ActivityExecution.started_at,
                    ActivityExecution.ended_at,
                    ActivityExecution.terminal_action,
                    ActivityExecution.outcome_label,
                    ActivityExecution.notes,
                    ActivityExecution.user_id,
                    Trip.current_purpose,
                    Trip.current_context_reference,
                    Trip.current_standard_value_id,
                    Trip.started_at.label("viaje_salida"),
                    Trip.arrived_at,
                    TripMileage.state.label("millaje_estado"),
                    TripMileage.total_meters,
                    StandardValue.label.label("detalle_proposito"),
                    Users.first_name,
                    Users.last_name,
                )
                .select_from(ActivityExecution)
                .join(
                    WorkSession,
                    (WorkSession.id == ActivityExecution.work_session_id)
                    & (WorkSession.company_id == ActivityExecution.company_id),
                )
                .join(
                    Trip,
                    (Trip.id == ActivityExecution.trip_id)
                    & (Trip.company_id == ActivityExecution.company_id),
                )
                .join(Users, Users.id == ActivityExecution.user_id)
                .outerjoin(
                    TripMileage,
                    (TripMileage.trip_id == Trip.id)
                    & (TripMileage.company_id == Trip.company_id),
                )
                # La etiqueta del valor de propósito se lee del catálogo porque
                # el viaje guarda su identificador y no una copia congelada.
                # Un valor retirado sigue ahí —la clave foránea es `RESTRICT`,
                # no desaparece de debajo de un histórico— así que la parada
                # sigue siendo legible (PR-05).
                .outerjoin(
                    StandardValue,
                    (StandardValue.id == Trip.current_standard_value_id)
                    & (StandardValue.company_id == Trip.company_id),
                )
                .where(
                    ActivityExecution.company_id == company_id,
                    WorkSession.user_id == user_id,
                    WorkSession.session_date == dia,
                )
                .order_by(ActivityExecution.started_at, ActivityExecution.id)
            )
        ).all()

        if not filas:
            return []

        etiquetas: dict[int, list[str]] = {}
        seleccionadas = (
            await session.execute(
                select(
                    ActivityExecutionActivity.activity_execution_id,
                    ActivityExecutionActivity.label,
                )
                .where(
                    ActivityExecutionActivity.company_id == company_id,
                    ActivityExecutionActivity.activity_execution_id.in_(
                        [f.id for f in filas]
                    ),
                )
                .order_by(
                    ActivityExecutionActivity.activity_execution_id,
                    ActivityExecutionActivity.label,
                    ActivityExecutionActivity.id,
                )
            )
        ).all()
        for s in seleccionadas:
            etiquetas.setdefault(s.activity_execution_id, []).append(s.label)

    paradas: list[dict] = []
    for f in filas:
        metros = (
            Decimal(str(f.total_meters))
            if f.millaje_estado == MileageState.CALCULATED.value and f.total_meters
            else Decimal("0")
        )
        # El detalle de propósito sólo acompaña a los contextos que **no**
        # llevan lista post-llegada. Donde sí la llevan, lo que cualifica la
        # parada son las actividades seleccionadas, y enseñar además el valor
        # del plan mezclaría las dos cosas que PR-04 manda separar.
        lleva_lista = f.current_purpose in POSTARRIVAL_ACTIVITY_LIST
        paradas.append(
            {
                "activity_execution_id": f.id,
                "trip_id": f.trip_id,
                "purpose": f.current_purpose,
                "context_reference": f.current_context_reference,
                "activity_labels": etiquetas.get(f.id, []),
                "purpose_detail": None if lleva_lista else f.detalle_proposito,
                "trip_started_at": f.viaje_salida,
                "arrived_at": f.arrived_at,
                "started_at": f.started_at,
                "ended_at": f.ended_at,
                "official_miles": (metros * MILLAS_POR_METRO).quantize(
                    Decimal("0.1")
                ),
                "mileage_pending": f.millaje_estado
                == MileageState.PENDING_CALCULATION.value,
                "terminal_action": f.terminal_action,
                "outcome_label": f.outcome_label,
                "notes": f.notes,
                "supervisor_user_id": f.user_id,
                "supervisor_name": f"{f.first_name or ''} {f.last_name or ''}".strip()
                or f"User {f.user_id}",
            }
        )

    return paradas
