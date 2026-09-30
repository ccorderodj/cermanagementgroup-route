"""Acceso a datos de la evidencia de ubicación (RTE06-CP2).

La resolución del sujeto está aquí y no en el servicio porque es una pregunta
de datos: "¿esta fila existe, es de esta compañía y cuelga de esta jornada?".
El servicio decide qué hacer con la respuesta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.activities.models import ActivityExecution, TerminalAction
from app.routers_api.location.models import (
    LocationEventKind,
    LocationFix,
    LocationSubjectKind,
    MissingLocationEvent,
    subject_kind_for,
)
from app.routers_api.trips.models import Trip, TripPurposeChange


@dataclass(frozen=True)
class SujetoResuelto:
    """El sujeto de un evento, ya comprobado contra la jornada y el tenant.

    `occurred_at` es la hora de ocurrencia **del evento operativo**, tomada de
    la fila de dominio. No se acepta del cliente: §31 dice que la hora de
    ocurrencia no llega en el cuerpo, y esa fila ya la resolvió cuando se
    escribió, con la semántica de RTE03.
    """

    subject_kind: LocationSubjectKind
    subject_id: int
    work_session_id: int
    trip_id: int | None
    occurred_at: datetime


class LocationFixesDAO(BaseDAO):
    model = LocationFix

    @classmethod
    async def find_for_event(
        cls,
        *,
        company_id: int,
        event_kind: LocationEventKind,
        subject_id: int,
    ) -> LocationFix | None:
        """El punto ya registrado para este evento, si lo hay.

        Es lo que hace visible el reenvío de la cola offline: el índice único
        lo impediría de todos modos, pero responder "ya estaba" es mejor que
        devolver un conflicto por algo que el cliente hizo bien (§32).
        """
        async with db_session() as session:
            return await session.scalar(
                select(LocationFix).where(
                    LocationFix.company_id == company_id,
                    LocationFix.event_kind == event_kind.value,
                    LocationFix.subject_kind == subject_kind_for(event_kind).value,
                    LocationFix.subject_id == subject_id,
                )
            )

    @classmethod
    async def for_trip_waypoints(
        cls, *, company_id: int, trip_id: int
    ) -> list[LocationFix]:
        """Los puntos que pueden ser waypoints de este viaje, **ya ordenados**.

        El orden es el de ocurrencia y sale de las filas de dominio, no de las
        horas de captura: `trip.started_at`, luego cada
        `trip_purpose_change.changed_at`, luego `trip.arrived_at`. Ordenar por
        `device_captured_at` sería correlacionar por proximidad de tiempo, que
        es justo lo que §14 prohíbe — un punto recuperado tres minutos después
        del evento se colocaría fuera de su sitio.

        Se hace en SQL de una vez porque son tres orígenes distintos con una
        sola ordenación; hacerlo en Python obligaría a tres consultas y a
        reconstruir el orden a mano.
        """
        consulta = text(
            """
            SELECT f.*, o.orden, o.momento
            FROM location_fix f
            JOIN (
                SELECT 'start_trip' AS event_kind, :trip_id AS subject_id,
                       0 AS orden, t.started_at AS momento
                FROM trip t
                WHERE t.id = :trip_id AND t.company_id = :company_id

                UNION ALL

                SELECT 'change_plan', c.id, 1, c.changed_at
                FROM trip_purpose_change c
                WHERE c.trip_id = :trip_id AND c.company_id = :company_id

                UNION ALL

                SELECT 'arrived', :trip_id, 2, t.arrived_at
                FROM trip t
                WHERE t.id = :trip_id AND t.company_id = :company_id
            ) o
              ON o.event_kind = f.event_kind AND o.subject_id = f.subject_id
            WHERE f.company_id = :company_id
            ORDER BY o.orden, o.momento, f.subject_id
            """
        )
        async with db_session() as session:
            filas = await session.execute(
                consulta, {"trip_id": trip_id, "company_id": company_id}
            )
            return [LocationFix(**_columnas_del_modelo(f._mapping)) for f in filas]


def _columnas_del_modelo(mapping) -> dict:
    """Sólo las columnas de `location_fix`, sin las auxiliares del `JOIN`."""
    nombres = {c.name for c in LocationFix.__table__.columns}
    return {k: v for k, v in mapping.items() if k in nombres}


class MissingLocationEventsDAO(BaseDAO):
    model = MissingLocationEvent

    @classmethod
    async def find_for_event(
        cls,
        *,
        company_id: int,
        event_kind: LocationEventKind,
        subject_id: int,
    ) -> MissingLocationEvent | None:
        async with db_session() as session:
            return await session.scalar(
                select(MissingLocationEvent).where(
                    MissingLocationEvent.company_id == company_id,
                    MissingLocationEvent.event_kind == event_kind.value,
                    MissingLocationEvent.subject_kind
                    == subject_kind_for(event_kind).value,
                    MissingLocationEvent.subject_id == subject_id,
                )
            )

    @classmethod
    async def subject_ids_for_trip(
        cls, *, company_id: int, trip_id: int
    ) -> set[tuple[str, int]]:
        """Qué eventos de este viaje están marcados como Missing.

        El motor de kilometraje lo necesita para distinguir dos cosas que no son
        lo mismo: un waypoint que **falta por ahora** —todavía en ventana de
        recuperación, así que el viaje sigue pendiente— y uno que ya se dio por
        perdido, que es terminal (§17, §24).
        """
        async with db_session() as session:
            filas = await session.execute(
                select(
                    MissingLocationEvent.event_kind, MissingLocationEvent.subject_id
                ).where(
                    MissingLocationEvent.company_id == company_id,
                    MissingLocationEvent.trip_id == trip_id,
                )
            )
            return {(f.event_kind, f.subject_id) for f in filas}


class SubjectsDAO:
    """Resuelve y comprueba el sujeto de un evento de ubicación.

    Una consulta por tipo de sujeto, cada una filtrando por `company_id` **y**
    por la jornada. Es donde se cierra §13: la evidencia que no se puede atar a
    una jornada autoritativa de esta compañía no entra.
    """

    @classmethod
    async def resolve(
        cls,
        *,
        company_id: int,
        event_kind: LocationEventKind,
        subject_id: int,
        work_session_id: int,
    ) -> SujetoResuelto | None:
        """El sujeto, o `None` si no existe o no es de esta jornada.

        `None` se traduce a **404** arriba, nunca a 403: confirmar que la fila
        existe pero es de otro sería confirmar su existencia (regla 8 de
        backend).
        """
        clase = subject_kind_for(event_kind)

        if clase is LocationSubjectKind.WORK_SESSION:
            # El sujeto **es** la jornada; sólo hay que comprobar que es la
            # misma que el servicio ya resolvió como autoritativa.
            if subject_id != work_session_id:
                return None
            momento = await cls._momento_de_jornada(
                company_id=company_id,
                work_session_id=work_session_id,
                event_kind=event_kind,
            )
            if momento is None:
                return None
            return SujetoResuelto(
                subject_kind=clase,
                subject_id=subject_id,
                work_session_id=work_session_id,
                trip_id=None,
                occurred_at=momento,
            )

        if clase is LocationSubjectKind.TRIP:
            async with db_session() as session:
                viaje = await session.scalar(
                    select(Trip).where(
                        Trip.id == subject_id,
                        Trip.company_id == company_id,
                        Trip.work_session_id == work_session_id,
                    )
                )
            if viaje is None:
                return None
            momento = (
                viaje.started_at
                if event_kind is LocationEventKind.START_TRIP
                else viaje.arrived_at
            )
            if momento is None:
                # El evento no ha ocurrido. No se acepta evidencia de algo que
                # no pasó, y menos un Missing: §19 lo dice de `Arrived` en un
                # viaje interrumpido.
                return None
            return SujetoResuelto(
                subject_kind=clase,
                subject_id=subject_id,
                work_session_id=work_session_id,
                trip_id=viaje.id,
                occurred_at=momento,
            )

        if clase is LocationSubjectKind.TRIP_PURPOSE_CHANGE:
            async with db_session() as session:
                fila = (
                    await session.execute(
                        select(TripPurposeChange, Trip.work_session_id)
                        .join(
                            Trip,
                            (Trip.id == TripPurposeChange.trip_id)
                            & (Trip.company_id == TripPurposeChange.company_id),
                        )
                        .where(
                            TripPurposeChange.id == subject_id,
                            TripPurposeChange.company_id == company_id,
                            Trip.work_session_id == work_session_id,
                        )
                    )
                ).first()
            if fila is None:
                return None
            cambio, sesion_del_viaje = fila
            return SujetoResuelto(
                subject_kind=clase,
                subject_id=cambio.id,
                work_session_id=sesion_del_viaje,
                trip_id=cambio.trip_id,
                occurred_at=cambio.changed_at,
            )

        # ActivityExecution
        async with db_session() as session:
            bloque = await session.scalar(
                select(ActivityExecution).where(
                    ActivityExecution.id == subject_id,
                    ActivityExecution.company_id == company_id,
                    ActivityExecution.work_session_id == work_session_id,
                )
            )
        if bloque is None:
            return None
        if bloque.ended_at is None:
            # Completar o dejar la actividad es lo que causa la captura; sin
            # hora de fin, ese evento no ha ocurrido.
            return None

        # El evento tiene que ser **el que de verdad pasó**. Sin esto, un
        # cliente podria reportar un `activity_leave` de un bloque que se
        # completó, y la correlación de §14 quedaría satisfecha en la forma
        # mientras describe otra cosa.
        esperado = (
            LocationEventKind.ACTIVITY_COMPLETE
            if bloque.terminal_action == TerminalAction.COMPLETE.value
            else LocationEventKind.ACTIVITY_LEAVE
        )
        if event_kind is not esperado:
            return None

        return SujetoResuelto(
            subject_kind=clase,
            subject_id=bloque.id,
            work_session_id=bloque.work_session_id,
            trip_id=bloque.trip_id,
            occurred_at=bloque.ended_at,
        )

    @staticmethod
    async def _momento_de_jornada(
        *, company_id: int, work_session_id: int, event_kind: LocationEventKind
    ) -> datetime | None:
        from app.routers_api.worksessions.models import WorkSession

        async with db_session() as session:
            jornada = await session.scalar(
                select(WorkSession).where(
                    WorkSession.id == work_session_id,
                    WorkSession.company_id == company_id,
                )
            )
        if jornada is None:
            return None
        return (
            jornada.started_at
            if event_kind is LocationEventKind.START_WORK
            else jornada.ended_at
        )
