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
from datetime import date, datetime, timedelta, timezone
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
from app.routers_api.mileage.read import (
    metros_calculados,
    millas_oficiales,
    pendientes,
)
from app.routers_api.standardvalues.models import StandardValue
from app.routers_api.trips.models import Trip
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import SupervisorProfile
from app.routers_api.worksessions.models import WorkSession

#: El nivel por el que agrupa cada rango, según `groupRows()` de la línea base.
AGRUPA_POR: dict[str, str] = {"year": "month", "month": "week", "week": "day"}


async def dia_actual_de(company_id: int, user_id: int | None) -> date:
    """El «hoy» del supervisor que se está mirando, para cuando no llega fecha.

    El día de **esa persona**, en su zona de referencia (T-1/T-2): no el de la
    compañía, no el del navegador del administrador y no el de otro supervisor.
    Una fecha explícita en la petición conserva su significado y no pasa por
    aquí.

    Sin zona determinable no se inventa un «hoy»: se abre en la fecha de su
    jornada más reciente, que es un hecho registrado. Sin ninguna jornada no
    hay nada que mostrar en ningún día, y la fecha UTC sólo ancla una vista
    vacía.
    """
    from app.routers_api.worksessions.time_zones import (
        dia_local,
        zonas_de_referencia,
    )

    ahora = datetime.now(timezone.utc)
    if user_id is None:
        return ahora.date()

    zona, _origen = (
        await zonas_de_referencia(company_id=company_id, user_ids=[user_id])
    )[user_id]
    if zona is not None:
        return dia_local(ahora, zona)

    async with db_session() as session:
        ultima = await session.scalar(
            select(func.max(WorkSession.session_date)).where(
                WorkSession.company_id == company_id,
                WorkSession.user_id == user_id,
            )
        )
    return ultima or ahora.date()


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
                    func.coalesce(func.sum(metros_calculados()), 0).label("metros"),
                    func.coalesce(func.sum(pendientes()), 0).label("pendientes"),
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
                "official_miles": millas_oficiales(metros),
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
                    # Del **viaje**: `ActivityExecution.trip_id` es nulo cuando
                    # no hubo parada, y es precisamente la fila que ahora tiene
                    # que existir. Además es la clave estable del detalle.
                    Trip.id.label("trip_id"),
                    ActivityExecution.started_at,
                    ActivityExecution.ended_at,
                    ActivityExecution.terminal_action,
                    ActivityExecution.outcome_label,
                    ActivityExecution.notes,
                    # De la **jornada**, no de la actividad: un viaje sin parada
                    # no tiene `ActivityExecution.user_id`, y la jornada siempre
                    # sabe de quién es. Son el mismo supervisor por
                    # construcción —la actividad se ejecuta dentro de su propia
                    # jornada— así que no cambia ningún valor existente.
                    WorkSession.user_id,
                    # La zona con que se registraron estos instantes (T-1/T-2):
                    # sus horas se formatean en la de la jornada, no en la del
                    # navegador de quien consulta.
                    WorkSession.start_time_zone,
                    WorkSession.start_utc_offset_minutes,
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
                # Se parte del **viaje**, no de la actividad (R-1).
                #
                # Partir de `ActivityExecution` dejaba fuera todo viaje que no
                # abre parada —el regreso a casa, que cierra al llegar; uno
                # interrumpido por `End Work Anyway`; uno que llegó y cuya
                # parada no se inició— y esos viajes **sí** aportan sus millas
                # al consolidado. El resultado era un total que la propia lista
                # no podía explicar, y medido en el caso que lo destapó era la
                # mitad del kilometraje del día.
                #
                # `outerjoin` a la actividad, no `join`: es la relación opcional
                # que convierte «no hay parada» en un hecho representable en vez
                # de en una fila ausente.
                .select_from(Trip)
                .join(
                    WorkSession,
                    (WorkSession.id == Trip.work_session_id)
                    & (WorkSession.company_id == Trip.company_id),
                )
                .join(Users, Users.id == WorkSession.user_id)
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
                    Trip.company_id == company_id,
                    WorkSession.user_id == user_id,
                    WorkSession.session_date == dia,
                )
                # Por la hora de salida del viaje, que **todas** las filas
                # tienen —incluidas las que no abrieron parada—, y a igualdad
                # por el identificador del viaje. Ordenar por el inicio de la
                # actividad dejaría los viajes sin parada agrupados al final o
                # al principio según cómo trate los nulos el motor, que es
                # justo el orden no determinista que §12 prohíbe.
                .order_by(Trip.started_at, Trip.id)
            )
        ).all()

        if not filas:
            return []

        etiquetas: dict[int, list[str]] = {}
        # `f.id` es nulo en los viajes sin parada, y pedirle al motor que
        # busque un `IN (NULL)` no devolvería nada pero sí ensuciaría la
        # consulta. Se filtran antes.
        con_actividad = [f.id for f in filas if f.id is not None]
        seleccionadas = (
            await session.execute(
                select(
                    ActivityExecutionActivity.activity_execution_id,
                    ActivityExecutionActivity.label,
                )
                .where(
                    ActivityExecutionActivity.company_id == company_id,
                    ActivityExecutionActivity.activity_execution_id.in_(
                        con_actividad
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
        # Un viaje sin parada **no es una actividad**, y la diferencia no es
        # cosmética: `outcome_label` vacío lo pintaría como `In progress`, que
        # afirmaría que hay una parada abierta esperando resultado. Lo que hay
        # es un trayecto que nunca abrió ninguna.
        tiene_actividad = f.id is not None
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
                "official_miles": millas_oficiales(metros),
                "mileage_pending": f.millaje_estado
                == MileageState.PENDING_CALCULATION.value,
                "terminal_action": f.terminal_action,
                "outcome_label": f.outcome_label,
                "notes": f.notes,
                "supervisor_user_id": f.user_id,
                "supervisor_name": f"{f.first_name or ''} {f.last_name or ''}".strip()
                or f"User {f.user_id}",
                #: Si esta fila describe una parada o sólo el trayecto. La
                #: pantalla lo necesita para no llamar «actividad» a un viaje
                #: que no la tuvo, y el contador para seguir contando paradas.
                "has_activity": tiene_actividad,
                "time_zone": f.start_time_zone,
                "utc_offset_minutes": f.start_utc_offset_minutes,
            }
        )

    return paradas
