"""
Reglas del viaje. El servidor es la autoridad sobre qué transición es legal.

Las cinco reglas de producto que sostienen este módulo, y que no se relajan
porque la interfaz ya las respete:

1. **Un viaje vive dentro de una jornada `ACTIVE`.** Sin jornada abierta no hay
   desplazamiento que registrar.
2. **Un solo viaje vivo por jornada.** Lo garantiza el índice único parcial; el
   servicio lo comprueba antes para dar un mensaje legible, pero la garantía es
   de la base.
3. **`Change Plan` sólo en tránsito**, y **apila**: el plan original no se pisa
   nunca. Después de llegar ya no hay plan que cambiar — el siguiente
   desplazamiento es otro viaje.
4. **Llegar no es terminar.** Un viaje operativo se queda en `ARRIVED`
   esperando a RTE05. Sólo `HOME` cierra al llegar, porque volver a casa no es
   una parada donde se ejecute nada.
5. **`End Work Anyway` interrumpe, no fabrica una llegada.** El viaje queda
   `INTERRUPTED`, que es lo que de verdad ocurrió.

Idempotencia
------------
Igual que en la jornada: repetir una transición que ya se aplicó devuelve el
mismo estado en vez de fallar. Una cola offline reenvía, y el resultado tiene
que ser el mismo la primera vez y la enésima.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import record_event
from app.core.db.session import transaction
from app.routers_api.trips.dao import TripsDAO
from app.routers_api.trips.models import (
    PRETRIP_STANDARD_LIST,
    Trip,
    TripPurpose,
    TripPurposeChange,
    TripStatus,
)
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus
from app.routers_api.worksessions.service import _resolve_occurrence


async def _validar_valor_de_contexto(
    *, company_id: int, purpose: str, standard_value_id: int | None
) -> None:
    """El valor de lista tiene que pertenecer a la lista de **ese** contexto.

    Dos reglas, las dos del servidor:

    * Un contexto sin valor de pre-viaje —Client Visit, Recruiting, Other,
      HOME— no acepta ninguno. Lo que se elige en esos casos describe lo que se
      ejecutó al llegar, y eso es RTE05.
    * Un contexto que sí lo lleva sólo acepta valores de **su** lista. Ofrecer
      un Delivery Type en una visita a oficina sería cruzar contextos, que el
      baseline prohíbe de forma explícita.

    El valor es opcional: un supervisor puede no rellenarlo. Lo que no puede es
    rellenarlo con algo de otra lista.
    """
    if standard_value_id is None:
        return

    lista = PRETRIP_STANDARD_LIST.get(purpose)
    if lista is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This trip context does not take a standardized value.",
        )

    from app.routers_api.standardvalues.dao import StandardValuesDAO

    valor = await StandardValuesDAO.get_including_deleted(
        value_id=standard_value_id, company_id=company_id
    )
    if valor is None or valor.list_code != lista:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That value does not belong to this trip context.",
        )


async def _jornada_activa(*, company_id: int, user_id: int) -> WorkSession:
    """La jornada abierta de quien llama, o 409 explicando que no la hay."""
    from app.routers_api.worksessions.dao import WorkSessionsDAO

    jornada = await WorkSessionsDAO.find_active_for_user(
        company_id=company_id, user_id=user_id
    )
    if jornada is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Start your workday before recording a trip.",
        )
    return jornada


class TripService:
    @staticmethod
    async def create(
        *,
        company_id: int,
        user_id: int,
        purpose: str,
        context_reference: str | None,
        standard_value_id: int | None,
        device_captured_at: datetime | None,
        utc_offset_minutes: int | None,
    ) -> tuple[Trip, bool]:
        """Crea el viaje en planificación, o devuelve el que ya estaba vivo.

        Devolver el existente —en vez de fallar— es lo que hace la acción
        segura frente a un reenvío de la cola offline y frente a un segundo
        dispositivo: ninguno de los dos debe acabar con dos viajes.
        """
        jornada = await _jornada_activa(company_id=company_id, user_id=user_id)
        await _validar_valor_de_contexto(
            company_id=company_id,
            purpose=purpose,
            standard_value_id=standard_value_id,
        )

        vivo = await TripsDAO.find_non_terminal(
            company_id=company_id, work_session_id=jornada.id
        )
        if vivo is not None:
            return vivo, False

        secuencia = await TripsDAO.next_sequence(
            company_id=company_id, work_session_id=jornada.id
        )

        try:
            async with transaction() as session:
                viaje = Trip(
                    company_id=company_id,
                    work_session_id=jornada.id,
                    sequence=secuencia,
                    status=TripStatus.PLANNING.value,
                    original_purpose=purpose,
                    original_context_reference=context_reference,
                    original_standard_value_id=standard_value_id,
                    current_purpose=purpose,
                    current_context_reference=context_reference,
                    current_standard_value_id=standard_value_id,
                )
                session.add(viaje)
                await session.flush()
                trip_id = viaje.id
        except IntegrityError:
            # El índice parcial atrapó una carrera real: otra petición creó el
            # viaje entre la lectura de arriba y este insert. Es el mismo viaje
            # que esa otra petición acaba de crear, no un error del supervisor.
            ganador = await TripsDAO.find_non_terminal(
                company_id=company_id, work_session_id=jornada.id
            )
            if ganador is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not start a trip. Try again.",
                )
            return ganador, False

        await record_event(
            company_id=company_id,
            entity_type="trip",
            entity_id=trip_id,
            action="create",
            actor_user_id=user_id,
            summary=f"Trip planned ({purpose})",
            changes={
                "status": {"old": None, "new": TripStatus.PLANNING.value},
                "purpose": {"old": None, "new": purpose},
                "work_session_id": {"old": None, "new": jornada.id},
            },
        )

        creado = await TripsDAO.get_for_owner(
            trip_id=trip_id, company_id=company_id, user_id=user_id
        )
        return creado, True

    @staticmethod
    async def start(
        *,
        company_id: int,
        user_id: int,
        trip_id: int,
        device_captured_at: datetime | None,
        utc_offset_minutes: int | None,
    ) -> Trip:
        """`PLANNING → IN_TRANSIT`.

        Exige que la jornada siga abierta: arrancar un viaje en una jornada ya
        cerrada dejaría un desplazamiento sin dueño.
        """
        viaje = await TripService._propio(
            company_id=company_id, user_id=user_id, trip_id=trip_id
        )

        if viaje.status == TripStatus.IN_TRANSIT.value:
            return viaje  # replay: ya arrancó
        if viaje.status != TripStatus.PLANNING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This trip has already started.",
            )

        await _jornada_activa(company_id=company_id, user_id=user_id)

        recibido, ocurrido = _momentos(device_captured_at)

        async with transaction() as session:
            fila = await session.scalar(select(Trip).where(Trip.id == trip_id))
            if fila.status == TripStatus.IN_TRANSIT.value:
                return fila
            fila.status = TripStatus.IN_TRANSIT.value
            fila.started_at = ocurrido
            fila.started_received_at = recibido
            fila.version = fila.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="trip",
            entity_id=trip_id,
            action="start",
            actor_user_id=user_id,
            summary="Trip started",
            changes={
                "status": {
                    "old": TripStatus.PLANNING.value,
                    "new": TripStatus.IN_TRANSIT.value,
                },
                "started_at": {"old": None, "new": ocurrido.isoformat()},
            },
        )

        return await TripsDAO.get_for_owner(
            trip_id=trip_id, company_id=company_id, user_id=user_id
        )

    @staticmethod
    async def change_plan(
        *,
        company_id: int,
        user_id: int,
        trip_id: int,
        purpose: str,
        context_reference: str | None,
        standard_value_id: int | None,
        device_captured_at: datetime | None,
    ) -> Trip:
        """Cambia el plan **sin borrar el anterior**.

        Sólo en tránsito: antes de salir el supervisor todavía está editando su
        planificación, y después de llegar el viaje ya alcanzó su destino — lo
        que venga después es otro viaje.
        """
        viaje = await TripService._propio(
            company_id=company_id, user_id=user_id, trip_id=trip_id
        )

        if viaje.status != TripStatus.IN_TRANSIT.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You can only change the plan while you are on route.",
            )

        await _validar_valor_de_contexto(
            company_id=company_id,
            purpose=purpose,
            standard_value_id=standard_value_id,
        )

        recibido, ocurrido = _momentos(device_captured_at)
        anterior_purpose = viaje.current_purpose
        anterior_ref = viaje.current_context_reference
        anterior_valor = viaje.current_standard_value_id

        async with transaction() as session:
            fila = await session.scalar(select(Trip).where(Trip.id == trip_id))
            session.add(
                TripPurposeChange(
                    company_id=company_id,
                    trip_id=trip_id,
                    from_purpose=anterior_purpose,
                    from_context_reference=anterior_ref,
                    from_standard_value_id=anterior_valor,
                    to_purpose=purpose,
                    to_context_reference=context_reference,
                    to_standard_value_id=standard_value_id,
                    changed_at=ocurrido,
                    changed_received_at=recibido,
                    changed_by=user_id,
                )
            )
            # Sólo se mueve lo **actual**. `original_*` no se toca nunca.
            fila.current_purpose = purpose
            fila.current_context_reference = context_reference
            fila.current_standard_value_id = standard_value_id
            fila.version = fila.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="trip",
            entity_id=trip_id,
            action="change_plan",
            actor_user_id=user_id,
            summary=f"Trip plan changed to {purpose}",
            changes={"purpose": {"old": anterior_purpose, "new": purpose}},
        )

        return await TripsDAO.get_for_owner(
            trip_id=trip_id, company_id=company_id, user_id=user_id
        )

    @staticmethod
    async def arrive(
        *,
        company_id: int,
        user_id: int,
        trip_id: int,
        device_captured_at: datetime | None,
    ) -> Trip:
        """`IN_TRANSIT → ARRIVED`, y sólo `HOME` sigue hasta `CLOSED`.

        Un viaje operativo se queda en `ARRIVED`: no se crea ningún bloque de
        actividad ni se cierra solo. Eso es RTE05, y fabricarlo aquí sería
        simular una funcionalidad que no existe.

        Llegar a casa **no** termina la jornada. La jornada la cierra el
        supervisor, explícitamente, con `End Work`.
        """
        viaje = await TripService._propio(
            company_id=company_id, user_id=user_id, trip_id=trip_id
        )

        es_home = viaje.current_purpose == TripPurpose.HOME.value
        destino = TripStatus.CLOSED.value if es_home else TripStatus.ARRIVED.value

        if viaje.status == destino:
            return viaje  # replay
        if viaje.status != TripStatus.IN_TRANSIT.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You can only arrive while you are on route.",
            )

        recibido, ocurrido = _momentos(device_captured_at)

        async with transaction() as session:
            fila = await session.scalar(select(Trip).where(Trip.id == trip_id))
            if fila.status == destino:
                return fila
            fila.status = destino
            fila.arrived_at = ocurrido
            fila.arrived_received_at = recibido
            if es_home:
                fila.ended_at = ocurrido
                fila.ended_received_at = recibido
            fila.version = fila.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="trip",
            entity_id=trip_id,
            action="arrive_home" if es_home else "arrive",
            actor_user_id=user_id,
            summary="Arrived home, trip closed" if es_home else "Arrived",
            changes={
                "status": {"old": TripStatus.IN_TRANSIT.value, "new": destino},
                "arrived_at": {"old": None, "new": ocurrido.isoformat()},
            },
        )

        return await TripsDAO.get_for_owner(
            trip_id=trip_id, company_id=company_id, user_id=user_id
        )

    @staticmethod
    async def interrupt(
        *,
        company_id: int,
        user_id: int,
        trip_id: int,
        device_captured_at: datetime | None,
    ) -> Trip:
        """`IN_TRANSIT → INTERRUPTED`, por un `End Work Anyway` explícito.

        No se inventa una llegada. El viaje se cortó a medias, y así queda
        escrito.
        """
        viaje = await TripService._propio(
            company_id=company_id, user_id=user_id, trip_id=trip_id
        )

        if viaje.status == TripStatus.INTERRUPTED.value:
            return viaje  # replay
        if viaje.status != TripStatus.IN_TRANSIT.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a trip on route can be interrupted.",
            )

        recibido, ocurrido = _momentos(device_captured_at)

        async with transaction() as session:
            fila = await session.scalar(select(Trip).where(Trip.id == trip_id))
            if fila.status == TripStatus.INTERRUPTED.value:
                return fila
            fila.status = TripStatus.INTERRUPTED.value
            fila.ended_at = ocurrido
            fila.ended_received_at = recibido
            fila.version = fila.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="trip",
            entity_id=trip_id,
            action="interrupt",
            actor_user_id=user_id,
            summary="Trip interrupted by End Work Anyway",
            changes={
                "status": {
                    "old": TripStatus.IN_TRANSIT.value,
                    "new": TripStatus.INTERRUPTED.value,
                }
            },
        )

        return await TripsDAO.get_for_owner(
            trip_id=trip_id, company_id=company_id, user_id=user_id
        )

    @staticmethod
    async def current(*, company_id: int, work_session_id: int) -> Trip | None:
        return await TripsDAO.find_non_terminal(
            company_id=company_id, work_session_id=work_session_id
        )

    @staticmethod
    async def _propio(*, company_id: int, user_id: int, trip_id: int) -> Trip:
        viaje = await TripsDAO.get_for_owner(
            trip_id=trip_id, company_id=company_id, user_id=user_id
        )
        if viaje is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
            )
        return viaje


def _momentos(device_captured_at: datetime | None) -> tuple[datetime, datetime]:
    """`(recibido, ocurrido)` con la semántica de RTE03.

    Se reutiliza `_resolve_occurrence` de la jornada en vez de reimplementarla:
    la regla de qué evidencia de tiempo se acepta es una sola en el producto, y
    tenerla dos veces la haría divergir.
    """
    from datetime import timezone

    recibido = datetime.now(timezone.utc)
    ocurrido, _origen = _resolve_occurrence(
        received_at=recibido, device_captured_at=device_captured_at
    )
    return recibido, ocurrido
