"""
Las reglas de la ejecución tras la llegada (RTE05).

Las cinco que sostienen el módulo
----------------------------------
1. **Un bloque por parada.** Las actividades seleccionadas son etiquetas de ese
   bloque, no unidades de ejecución: un inicio, un fin, una duración, un
   resultado, una nota (PD-01).
2. **Nada se cierra solo.** Un viaje operativo alcanza `CLOSED` porque alguien
   terminó o se marchó **y dijo cómo fue**, nunca porque se pidiera terminar la
   jornada. Terminar sin resultado no es un caso de borde: es imposible, y lo
   impide una restricción de la base.
3. **El contexto manda.** Sólo tres contextos seleccionan actividad. Employee
   Visit y Office ya traen su dato desde la planificación, y añadirles un
   selector al llegar sería duplicar lo que ya se preguntó.
4. **El histórico se lee como era.** Se guarda la referencia al valor y su
   etiqueta de entonces, porque un administrador puede renombrar, desactivar o
   retirar la lista y marzo tiene que seguir leyéndose como marzo.
5. **El servidor es la autoridad.** Quién ejecuta sale de la sesión, cuándo
   ocurrió se valida contra la causalidad, y qué valores se aceptan se comprueba
   contra la lista del contexto y el tenant.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import record_event
from app.core.db.session import db_session, transaction
from app.routers_api.activities.models import (
    NO_EXECUTION_PURPOSES,
    OUTCOME_LIST,
    POSTARRIVAL_ACTIVITY_LIST,
    RECEIVED_BY_LIST,
    TERMINAL_EXECUTION_STATUSES,
    ActivityExecution,
    ActivityExecutionActivity,
    ActivityExecutionStatus,
    TerminalAction,
)
from app.routers_api.trips.models import Trip, TripPurpose, TripStatus
from app.routers_api.worksessions.service import _resolve_occurrence


def _momentos(device_captured_at: datetime | None, *, not_before: datetime | None):
    """Cuándo ocurrió y cuándo se supo, con la semántica certificada en D-10."""
    recibido = datetime.now(timezone.utc)
    ocurrido, origen = _resolve_occurrence(
        received_at=recibido,
        device_captured_at=device_captured_at,
        not_before=not_before,
    )
    return recibido, ocurrido, origen


class ActivityService:
    # ── Lectura ─────────────────────────────────────────────────────────────

    @staticmethod
    async def current_for_trip(
        *, company_id: int, trip_id: int
    ) -> ActivityExecution | None:
        async with db_session() as session:
            return await session.scalar(
                select(ActivityExecution).where(
                    ActivityExecution.company_id == company_id,
                    ActivityExecution.trip_id == trip_id,
                )
            )

    @staticmethod
    async def activities_of(
        *, company_id: int, execution_id: int
    ) -> list[ActivityExecutionActivity]:
        async with db_session() as session:
            filas = await session.execute(
                select(ActivityExecutionActivity)
                .where(
                    ActivityExecutionActivity.company_id == company_id,
                    ActivityExecutionActivity.activity_execution_id == execution_id,
                )
                .order_by(ActivityExecutionActivity.sort_order.asc())
            )
            return list(filas.scalars().all())

    @staticmethod
    async def has_unresolved_work(*, company_id: int, work_session_id: int) -> bool:
        """Si queda trabajo de llegada sin resolver en esta jornada.

        Es lo que consulta `End Work`: un viaje operativo que llegó y todavía no
        tiene bloque terminal, o un bloque en marcha. HOME no cuenta — su viaje
        ya se cerró al llegar y no ejecuta nada.
        """
        async with db_session() as session:
            viaje = await session.scalar(
                select(Trip).where(
                    Trip.company_id == company_id,
                    Trip.work_session_id == work_session_id,
                    Trip.status == TripStatus.ARRIVED.value,
                )
            )
        if viaje is None:
            return False
        if viaje.current_purpose in NO_EXECUTION_PURPOSES:
            return False

        ejecucion = await ActivityService.current_for_trip(
            company_id=company_id, trip_id=viaje.id
        )
        if ejecucion is None:
            return True
        return ejecucion.status not in TERMINAL_EXECUTION_STATUSES

    # ── Validación de los valores configurados ──────────────────────────────

    @staticmethod
    async def _valor_elegible(*, company_id: int, value_id: int, list_code: str):
        """El valor debe ser de esta compañía, de esta lista, y elegible hoy.

        Una sola comprobación para las cuatro formas de equivocarse: no existe,
        es de otro tenant, es de otra lista, o está retirado. Se responde igual a
        todas porque distinguirlas daría información sobre filas que quien llama
        no puede ver.
        """
        from app.routers_api.standardvalues.dao import StandardValuesDAO

        valor = await StandardValuesDAO.find_selectable(
            value_id=value_id, company_id=company_id, list_code=list_code
        )
        if valor is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That value cannot be selected here.",
            )
        return valor

    @staticmethod
    async def _validar_actividades(
        *, company_id: int, purpose: str, activity_ids: list[int]
    ) -> list:
        """Las actividades que ese contexto exige, ni más ni menos.

        Los contextos con lista exigen **al menos una**; los que no la tienen no
        aceptan ninguna. Enviar actividades a una visita a oficina no es un extra
        que se ignore: es cruzar contextos, y se rechaza.
        """
        lista = POSTARRIVAL_ACTIVITY_LIST.get(purpose)

        if lista is None:
            if activity_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="This trip context does not take post-arrival activities.",
                )
            return []

        if not activity_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose at least one activity before starting.",
            )
        if len(set(activity_ids)) != len(activity_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That activity is selected twice.",
            )

        return [
            await ActivityService._valor_elegible(
                company_id=company_id, value_id=vid, list_code=lista
            )
            for vid in activity_ids
        ]

    # ── Arranque ────────────────────────────────────────────────────────────

    @staticmethod
    async def start(
        *,
        company_id: int,
        user_id: int,
        trip_id: int,
        activity_ids: list[int],
        device_captured_at: datetime | None,
    ) -> ActivityExecution:
        """Empieza el bloque de la parada. **Uno por viaje.**

        Reintentar es seguro: si ya existe, se devuelve el mismo. Lo garantiza el
        índice único, no una comprobación previa — dos dispositivos pulsando a la
        vez pasan la comprobación los dos y sólo uno gana en la base.
        """
        async with db_session() as session:
            viaje = await session.scalar(
                select(Trip).where(
                    Trip.id == trip_id, Trip.company_id == company_id
                )
            )
        if viaje is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
            )
        if viaje.status != TripStatus.ARRIVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Activities start once you have arrived.",
            )
        if viaje.current_purpose in NO_EXECUTION_PURPOSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Going home does not record an activity.",
            )

        existente = await ActivityService.current_for_trip(
            company_id=company_id, trip_id=trip_id
        )
        if existente is not None:
            # Replay seguro: ya se arrancó. No se vuelve a arrancar ni se
            # cambian las actividades — eso sería mutación silenciosa.
            return existente

        valores = await ActivityService._validar_actividades(
            company_id=company_id,
            purpose=viaje.current_purpose,
            activity_ids=activity_ids,
        )

        recibido, ocurrido, origen = _momentos(
            device_captured_at, not_before=viaje.arrived_at
        )

        try:
            async with transaction() as session:
                bloque = ActivityExecution(
                    company_id=company_id,
                    work_session_id=viaje.work_session_id,
                    trip_id=trip_id,
                    user_id=user_id,
                    status=ActivityExecutionStatus.IN_PROGRESS.value,
                    started_at=ocurrido,
                    started_received_at=recibido,
                    started_at_source=origen.value,
                )
                session.add(bloque)
                await session.flush()

                for orden, valor in enumerate(valores, start=1):
                    session.add(
                        ActivityExecutionActivity(
                            company_id=company_id,
                            activity_execution_id=bloque.id,
                            standard_value_id=valor.id,
                            # La etiqueta de **ahora**: es lo que hará legible
                            # este registro cuando la lista cambie.
                            label=valor.label,
                            sort_order=orden,
                        )
                    )
                await session.flush()
                bloque_id = bloque.id
        except IntegrityError:
            # Otro dispositivo llegó primero. El índice único hizo su trabajo.
            return await ActivityService.current_for_trip(
                company_id=company_id, trip_id=trip_id
            )

        await record_event(
            company_id=company_id,
            entity_type="activity_execution",
            entity_id=bloque_id,
            action="start",
            actor_user_id=user_id,
            summary=f"Activity execution started for trip {trip_id}",
            changes={
                "trip_id": {"old": None, "new": trip_id},
                "activities": {
                    "old": None,
                    "new": ", ".join(v.label for v in valores) or None,
                },
                "started_at": {"old": None, "new": ocurrido.isoformat()},
            },
        )

        return await ActivityService.current_for_trip(
            company_id=company_id, trip_id=trip_id
        )

    # ── Cierre: completar o marcharse ───────────────────────────────────────

    @staticmethod
    async def terminalize(
        *,
        company_id: int,
        user_id: int,
        trip_id: int,
        action: str,
        outcome_id: int,
        notes: str | None,
        received_by_id: int | None,
        device_captured_at: datetime | None,
    ) -> ActivityExecution:
        """Termina el bloque y **cierra el viaje**, en la misma transacción.

        Las dos cosas van juntas a propósito: un bloque terminal con un viaje sin
        cerrar, o un viaje cerrado sin los hechos que lo justifican, serían
        estados que el dominio no puede producir por sí mismo y que nadie sabría
        interpretar después.

        `Complete` y `Leave` recorren el mismo camino porque exigen lo mismo —un
        resultado— y difieren sólo en lo que queda escrito. Marcharse es una
        salida controlada, no un abandono ni un fallo.
        """
        bloque = await ActivityService.current_for_trip(
            company_id=company_id, trip_id=trip_id
        )
        if bloque is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Start the activity before finishing it.",
            )
        if bloque.status in TERMINAL_EXECUTION_STATUSES:
            # Replay seguro: ya terminó, y no se vuelve a terminar con otro
            # resultado. El primero que llegó es el que ocurrió.
            return bloque

        async with db_session() as session:
            viaje = await session.scalar(
                select(Trip).where(
                    Trip.id == trip_id, Trip.company_id == company_id
                )
            )

        resultado = await ActivityService._valor_elegible(
            company_id=company_id, value_id=outcome_id, list_code=OUTCOME_LIST
        )

        # Quién recibió: obligatorio al **completar**, opcional al marcharse.
        #
        # Completar una entrega afirma que alguien la recibió, y esa afirmación
        # sin nombre no es verificable. Marcharse afirma lo contrario —que no se
        # pudo entregar—, y exigir un receptor ahí obligaría a inventarse uno
        # para poder cerrar la parada: un dato fabricado para satisfacer una
        # validación es peor que la ausencia del dato.
        #
        # La regla sale de la **acción**, nunca del resultado elegido. El
        # catálogo de resultados es dato configurado por el tenant: ramificar
        # sobre sus etiquetas ataría esta validación a un texto que un
        # administrador puede renombrar esta tarde.
        recibido_por = None
        if viaje.current_purpose == TripPurpose.CHECK_DELIVERY.value:
            if received_by_id is None:
                if action == TerminalAction.COMPLETE.value:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Record who received the delivery before completing."
                        ),
                    )
            else:
                # Si se registra al marcharse, se conserva y se valida igual:
                # que sea opcional no lo hace menos verificable.
                recibido_por = await ActivityService._valor_elegible(
                    company_id=company_id,
                    value_id=received_by_id,
                    list_code=RECEIVED_BY_LIST,
                )
        elif received_by_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only a check delivery records who received it.",
            )

        nuevo_estado = (
            ActivityExecutionStatus.COMPLETED.value
            if action == TerminalAction.COMPLETE.value
            else ActivityExecutionStatus.LEFT.value
        )
        recibido, ocurrido, origen = _momentos(
            device_captured_at, not_before=bloque.started_at
        )

        async with transaction() as session:
            # Condicional sobre el estado: si otro dispositivo terminó mientras
            # tanto, esta actualización no toca nada y se devuelve lo que quedó.
            aplicado = await session.execute(
                update(ActivityExecution)
                .where(
                    ActivityExecution.id == bloque.id,
                    ActivityExecution.status
                    == ActivityExecutionStatus.IN_PROGRESS.value,
                )
                .values(
                    status=nuevo_estado,
                    terminal_action=action,
                    ended_at=ocurrido,
                    ended_received_at=recibido,
                    ended_at_source=origen.value,
                    outcome_standard_value_id=resultado.id,
                    outcome_label=resultado.label,
                    received_by_standard_value_id=(
                        recibido_por.id if recibido_por else None
                    ),
                    received_by_label=(
                        recibido_por.label if recibido_por else None
                    ),
                    notes=(notes.strip() or None) if notes else None,
                    version=ActivityExecution.version + 1,
                )
            )
            if aplicado.rowcount == 0:
                return await ActivityService.current_for_trip(
                    company_id=company_id, trip_id=trip_id
                )

            # Y el viaje se cierra aquí mismo, no en otra petición.
            await session.execute(
                update(Trip)
                .where(Trip.id == trip_id, Trip.company_id == company_id)
                .values(
                    status=TripStatus.CLOSED.value,
                    ended_at=ocurrido,
                    version=Trip.version + 1,
                )
            )

        await record_event(
            company_id=company_id,
            entity_type="activity_execution",
            entity_id=bloque.id,
            action=action,
            actor_user_id=user_id,
            summary=(
                f"Activity execution {nuevo_estado} for trip {trip_id}; trip closed"
            ),
            changes={
                "status": {"old": bloque.status, "new": nuevo_estado},
                "terminal_action": {"old": None, "new": action},
                "outcome": {"old": None, "new": resultado.label},
                "received_by": {
                    "old": None,
                    "new": recibido_por.label if recibido_por else None,
                },
                "ended_at": {"old": None, "new": ocurrido.isoformat()},
                "trip_status": {
                    "old": TripStatus.ARRIVED.value,
                    "new": TripStatus.CLOSED.value,
                },
            },
        )

        return await ActivityService.current_for_trip(
            company_id=company_id, trip_id=trip_id
        )
