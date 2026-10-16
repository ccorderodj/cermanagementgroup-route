"""
Los puntos con los que se calculó el millaje de un viaje, para el visor de ruta.

Qué se enseña, y qué no
-----------------------
El cálculo de millas pide a TomTom **sólo la distancia** (`summaryOnly`): no
existe el trazado por carretera. Lo que sí existe son los puntos que se le
dieron —salida, cada cambio de plan, llegada—, guardados en los tramos del
millaje cuando se calculó. Son ubicaciones capturadas por el teléfono, no
contenido de TomTom.

Se devuelven esos puntos, en orden, para pintarlos como **marcadores
numerados sin línea**: unirlos con una recta la presentaría como la ruta, y no
lo es (V1.0 del visor, FR-04).

Seguridad: primero quién y sobre qué, después las coordenadas
-------------------------------------------------------------
El viaje se busca **con el alcance ya aplicado** (tenant y rama por periodo,
`WorkSession.started_at`): fuera de alcance, otro tenant o un id inventado dan
el mismo 404. Ninguna coordenada se lee antes de esa comprobación, y ninguna
se registra en logs.
"""

from __future__ import annotations

from sqlalchemy import and_, select

from app.core.db.session import db_session
from app.routers_api.mileage.models import MileageState, TripMileage, TripMileageSegment
from app.routers_api.organization.scope import Alcance, condicion_de_jornadas
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession


async def viaje_en_alcance(*, company_id: int, trip_id: int, alcance: Alcance) -> bool:
    """Si el viaje existe en esta compañía y su jornada está en el alcance."""
    condicion = condicion_de_jornadas(alcance, WorkSession.user_id, WorkSession.started_at)
    consulta = (
        select(Trip.id)
        .join(
            WorkSession,
            and_(
                WorkSession.id == Trip.work_session_id,
                WorkSession.company_id == Trip.company_id,
            ),
        )
        .where(Trip.id == trip_id, Trip.company_id == company_id)
    )
    if condicion is not None:
        consulta = consulta.where(condicion)
    async with db_session() as session:
        return await session.scalar(consulta) is not None


def _valido(lat, lon) -> bool:
    return lat is not None and lon is not None and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180


async def puntos_del_calculo(*, company_id: int, trip_id: int) -> tuple[list[dict], str | None]:
    """Los puntos del millaje **calculado**, en orden y sin repetir el punto en
    que un tramo acaba y el siguiente empieza."""
    async with db_session() as session:
        tramos = (
            await session.execute(
                select(TripMileageSegment)
                .join(
                    TripMileage,
                    and_(
                        TripMileage.id == TripMileageSegment.trip_mileage_id,
                        TripMileage.company_id == TripMileageSegment.company_id,
                    ),
                )
                .where(
                    TripMileage.company_id == company_id,
                    TripMileage.trip_id == trip_id,
                    TripMileage.state == MileageState.CALCULATED.value,
                )
                .order_by(TripMileageSegment.sequence)
            )
        ).scalars().all()
    if not tramos:
        return [], None
    crudos = [(tramos[0].from_event_kind, tramos[0].from_latitude, tramos[0].from_longitude)]
    crudos += [(t.to_event_kind, t.to_latitude, t.to_longitude) for t in tramos]
    puntos = [
        {"sequence": i + 1, "kind": kind, "latitude": float(lat), "longitude": float(lon)}
        for i, (kind, lat, lon) in enumerate(crudos)
        if _valido(lat, lon)
    ]
    return puntos, tramos[0].provider
