"""
Acceso a datos del viaje. Siempre acotado por compañía **y** por jornada.

El supervisor no se guarda en `trip`: se deriva de la jornada dueña. Por eso
cada consulta que necesita saber "¿es suyo?" pasa por `work_session`, en vez de
confiar en un `user_id` copiado que podría acabar diciendo otra cosa
(invariante 9 de `AGENTS.md`).
"""

from __future__ import annotations

from sqlalchemy import Select, func, select

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.trips.models import TERMINAL_STATUSES, Trip, TripPurposeChange
from app.routers_api.worksessions.models import WorkSession


class TripsDAO(BaseDAO):
    model = Trip

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        work_session_id: int | None = None,
        **_: object,
    ) -> Select:
        stmt = select(Trip).where(Trip.company_id == company_id)
        if work_session_id is not None:
            stmt = stmt.where(Trip.work_session_id == work_session_id)
        return stmt

    @classmethod
    def default_order(cls):
        return Trip.sequence.asc()

    @classmethod
    async def find_non_terminal(
        cls, *, company_id: int, work_session_id: int
    ) -> Trip | None:
        """El viaje vivo de esa jornada, si lo hay.

        "Vivo" incluye `ARRIVED`: un viaje operativo que llegó **no** ha
        terminado, está esperando a que RTE05 ejecute su actividad. Confundir
        llegar con terminar es justo lo que la instrucción prohíbe.
        """
        async with db_session() as session:
            return await session.scalar(
                select(Trip).where(
                    Trip.company_id == company_id,
                    Trip.work_session_id == work_session_id,
                    Trip.status.not_in(TERMINAL_STATUSES),
                )
            )

    @classmethod
    async def get_for_owner(
        cls, *, trip_id: int, company_id: int, user_id: int
    ) -> Trip | None:
        """El viaje, sólo si pertenece a una jornada de quien llama.

        Devuelve `None` tanto si no existe como si es de otro supervisor o de
        otro tenant: los tres casos responden igual, para no confirmar la
        existencia de algo que el llamante no puede ver.
        """
        async with db_session() as session:
            return await session.scalar(
                select(Trip)
                .join(
                    WorkSession,
                    (WorkSession.id == Trip.work_session_id)
                    & (WorkSession.company_id == Trip.company_id),
                )
                .where(
                    Trip.id == trip_id,
                    Trip.company_id == company_id,
                    WorkSession.user_id == user_id,
                )
            )

    @classmethod
    async def next_sequence(cls, *, company_id: int, work_session_id: int) -> int:
        """El orden del siguiente viaje dentro de la jornada, empezando en 1."""
        async with db_session() as session:
            maximo = await session.scalar(
                select(func.max(Trip.sequence)).where(
                    Trip.company_id == company_id,
                    Trip.work_session_id == work_session_id,
                )
            )
        return int(maximo or 0) + 1

    @classmethod
    async def count_vehicle_trips(
        cls, *, company_id: int, work_session_id: int
    ) -> int:
        """Cuántos viajes de la jornada llegaron a moverse de verdad.

        Lo usa la evidencia de odómetro final: si nadie condujo, pedir una
        lectura de cierre sería inventar una necesidad. Cuenta los que pasaron
        de `PLANNING`, porque un viaje que nunca arrancó no consumió vehículo.
        """
        async with db_session() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(Trip)
                    .where(
                        Trip.company_id == company_id,
                        Trip.work_session_id == work_session_id,
                        Trip.started_at.is_not(None),
                    )
                )
                or 0
            )


class TripPurposeChangesDAO(BaseDAO):
    model = TripPurposeChange

    @classmethod
    def query(cls, *, company_id: int, trip_id: int | None = None, **_: object) -> Select:
        stmt = select(TripPurposeChange).where(
            TripPurposeChange.company_id == company_id
        )
        if trip_id is not None:
            stmt = stmt.where(TripPurposeChange.trip_id == trip_id)
        return stmt

    @classmethod
    def default_order(cls):
        return TripPurposeChange.changed_at.asc()

    @classmethod
    async def history_for_trip(
        cls, *, company_id: int, trip_id: int
    ) -> list[TripPurposeChange]:
        """Los cambios de plan en orden, para reconstruir la intención."""
        async with db_session() as session:
            filas = await session.execute(
                select(TripPurposeChange)
                .where(
                    TripPurposeChange.company_id == company_id,
                    TripPurposeChange.trip_id == trip_id,
                )
                .order_by(TripPurposeChange.changed_at.asc(), TripPurposeChange.id.asc())
            )
            return list(filas.scalars().all())
