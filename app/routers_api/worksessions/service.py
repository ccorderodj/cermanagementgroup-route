"""
Reglas de negocio de la Jornada.

Dos decisiones sostienen todo este módulo:

1. **`Start Work` es idempotente por diseño, no por excepción.** Pulsarlo dos
   veces, o que la cola offline lo reenvíe tras reconectar, no es un error:
   el supervisor sigue trabajando, y la respuesta es la misma jornada vigente
   con 200, no un 409. La única vez que se ve el choque del índice único
   parcial es dentro de una carrera real entre dos peticiones simultáneas, y
   ahí se resuelve igual: se relee la jornada vigente y se devuelve.

2. **`End Work` sobre una jornada ya `ENDED` no es un error.** Es la misma
   propiedad: replay-safe, porque una acción offline reenviada tiene que
   producir el mismo resultado la primera vez y la enésima (§14 de las
   instrucciones).

3. **Cuándo ocurrió y cuándo se recibió son dos hechos, no uno.** Si la cola
   offline retuvo la acción, el reloj del servidor solo sabe cuándo se enteró.
   Guardar únicamente eso convierte el retraso de sincronización en la jornada
   —un `Start Work` del viernes por la noche sincronizado el sábado quedaría
   fechado en sábado—, así que la ocurrencia y la recepción se guardan por
   separado y `_resolve_occurrence` decide, con criterios que el servidor puede
   verificar por sí mismo, cuál de los dos relojes describe la ocurrencia.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import record_event
from app.core.db.session import transaction
from app.routers_api.vehicles.dao import (
    SupervisorProfilesDAO,
    VehicleAssignmentsDAO,
    VehiclesDAO,
)
from app.routers_api.worksessions.dao import WorkSessionsDAO
from app.routers_api.worksessions.models import (
    WorkSession,
    WorkSessionStatus,
    WorkSessionTimeSource,
)


#: Margen por el que se tolera que la evidencia del dispositivo vaya *por
#: delante* del reloj del servidor: la red tarda, y unos segundos de deriva
#: benigna no son una contradicción. Más allá de esto sí lo son: una acción no
#: puede haber ocurrido después del instante en que se recibió.
_FUTURE_EVIDENCE_TOLERANCE = timedelta(minutes=2)

#: Antigüedad máxima admisible para la evidencia de una acción encolada.
#: Generoso a propósito —cubre un fin de semana largo sin cobertura—, pero
#: acotado: una hora de ocurrencia de hace semanas no describe la jornada que
#: se está sincronizando, describe un reloj roto o una cola corrupta.
_MAX_EVIDENCE_AGE = timedelta(days=7)


def _as_utc(momento: datetime) -> datetime:
    """Un `datetime` sin zona se interpreta como UTC, no se rechaza.

    El contrato pide ISO-8601 con desfase y el cliente lo cumple, pero recibir
    uno sin zona no puede tumbar un `Start Work`: D-10 exige que el manejo del
    tiempo nunca bloquee la acción.
    """
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _resolve_occurrence(
    *,
    received_at: datetime,
    device_captured_at: datetime | None,
    not_before: datetime | None = None,
) -> tuple[datetime, WorkSessionTimeSource]:
    """Cuándo ocurrió la acción, y de qué reloj lo sabemos.

    El reloj del dispositivo es la **única** fuente que puede saber cuándo se
    pulsó el botón: si la acción esperó en la cola, el servidor solo conoce el
    momento en que se enteró. Ignorarla obligaría a representar el retraso de
    sincronización como la jornada, que es exactamente el defecto que corrige
    este cierre.

    Pero no se acepta a ciegas. Hay dos hechos que el servidor sí conoce con
    certeza y que permiten descartar evidencia imposible sin confiar en nada
    del cliente:

    * **Causalidad.** Una acción no puede ocurrir después de recibirse. Una
      evidencia por delante del reloj del servidor (más allá de la tolerancia
      de red) es contradictoria.
    * **Orden del ciclo de vida.** Un `End Work` no puede ocurrir antes del
      `Start Work` de su propia jornada — eso es lo que aporta `not_before`.

    Cuando la evidencia se descarta no se inventa precisión: se usa la hora de
    recepción como aproximación y se devuelve `SERVER_RECEIPT`, que queda
    almacenado. La evidencia cruda se guarda igual, aunque se haya rechazado
    (ver `start_device_captured_at` en el modelo). Rechazar nunca bloquea la
    acción: el supervisor termina su jornada igual, y la incertidumbre queda
    escrita en vez de disimulada.
    """
    if device_captured_at is None:
        return received_at, WorkSessionTimeSource.SERVER_RECEIPT

    ocurrencia = _as_utc(device_captured_at)

    if ocurrencia > received_at + _FUTURE_EVIDENCE_TOLERANCE:
        return received_at, WorkSessionTimeSource.SERVER_RECEIPT
    if ocurrencia < received_at - _MAX_EVIDENCE_AGE:
        return received_at, WorkSessionTimeSource.SERVER_RECEIPT
    if not_before is not None and ocurrencia < _as_utc(not_before):
        return received_at, WorkSessionTimeSource.SERVER_RECEIPT

    return ocurrencia, WorkSessionTimeSource.DEVICE


def _session_date_from(occurred_at_utc: datetime, utc_offset_minutes: int | None) -> date:
    """La fecha del calendario local en la que **ocurrió** el `Start Work`.

    Dos evidencias distintas del dispositivo, con confianzas distintas:

    * el **desfase** respecto a UTC dice en qué zona horaria está trabajando.
      Sale de la configuración del sistema operativo, no de la deriva del
      reloj, así que es fiable incluso en un teléfono mal ajustado.
    * el **instante** de la ocurrencia dice cuándo pulsó el botón. Es la única
      fuente posible para una acción encolada, y `_resolve_occurrence` ya la
      validó contra lo que el servidor sabe con certeza antes de llegar aquí.

    Sin desfase la fecha cae a UTC. Es un límite honesto y documentado, no un
    fallo silencioso: un `Start Work` nunca se bloquea por falta de evidencia
    (D-10, "el manejo del tiempo nunca bloquea Start Work o End Work").
    """
    if utc_offset_minutes is None:
        return occurred_at_utc.date()
    return (occurred_at_utc + timedelta(minutes=utc_offset_minutes)).date()


class WorkSessionService:
    @staticmethod
    async def start(
        *,
        company_id: int,
        user_id: int,
        device_captured_at: datetime | None,
        utc_offset_minutes: int | None,
    ) -> tuple[WorkSession, bool]:
        """Empieza la jornada, o devuelve la que ya está vigente.

        Devuelve `(jornada, created)`: `created=False` es la respuesta correcta
        a un `Start Work` repetido, no una excepción que el llamador deba
        capturar.
        """
        existente = await WorkSessionsDAO.find_active_for_user(
            company_id=company_id, user_id=user_id
        )
        if existente is not None:
            return existente, False

        # El snapshot de vehículo es opcional: un supervisor sin perfil de
        # Route, o sin asignación vigente, tiene una jornada igualmente válida
        # (§6.1). No se fabrica ninguno de los dos.
        vehicle_id: int | None = None
        mpg_snapshot = None
        perfil = await SupervisorProfilesDAO.find_by_user(
            company_id=company_id, user_id=user_id
        )
        if perfil is not None and perfil.is_active:
            asignacion = await VehicleAssignmentsDAO.current_for_supervisor(
                company_id=company_id, supervisor_profile_id=perfil.id
            )
            if asignacion is not None:
                vehiculo = await VehiclesDAO.get_for_company(
                    vehicle_id=asignacion.vehicle_id, company_id=company_id
                )
                vehicle_id = vehiculo.id
                mpg_snapshot = vehiculo.operational_mpg

        recibido_en = datetime.now(timezone.utc)
        ocurrido_en, origen = _resolve_occurrence(
            received_at=recibido_en, device_captured_at=device_captured_at
        )
        session_date = _session_date_from(ocurrido_en, utc_offset_minutes)

        try:
            async with transaction() as session:
                jornada = WorkSession(
                    company_id=company_id,
                    user_id=user_id,
                    status=WorkSessionStatus.ACTIVE.value,
                    session_date=session_date,
                    started_at=ocurrido_en,
                    started_received_at=recibido_en,
                    started_at_source=origen.value,
                    start_device_captured_at=device_captured_at,
                    start_utc_offset_minutes=utc_offset_minutes,
                    vehicle_id=vehicle_id,
                    mpg_snapshot=mpg_snapshot,
                )
                session.add(jornada)
                await session.flush()
                session_id = jornada.id
        except IntegrityError:
            # El índice único parcial atrapó una carrera real: otra petición
            # ganó entre la lectura de arriba y este insert. No es un error
            # del supervisor — es la misma jornada que esa otra petición acaba
            # de crear. La excepción sale de `transaction()` ya deshecha (su
            # propio `except` hace el rollback); aquí solo se relee.
            ganadora = await WorkSessionsDAO.find_active_for_user(
                company_id=company_id, user_id=user_id
            )
            if ganadora is None:
                # No debería ocurrir —el índice garantiza que alguien la
                # tiene—, pero no se inventa una jornada si de verdad no está.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not start a Work Session. Try again.",
                )
            return ganadora, False

        await record_event(
            company_id=company_id,
            entity_type="work_session",
            entity_id=session_id,
            action="start",
            actor_user_id=user_id,
            summary="Work Session started",
            changes={
                "status": {"old": None, "new": WorkSessionStatus.ACTIVE.value},
                "session_date": {"old": None, "new": session_date.isoformat()},
                "vehicle_id": {"old": None, "new": vehicle_id},
                # La auditoría registra las dos horas y de cuál se fio, no solo
                # el resultado: si una jornada quedó fechada por recepción, el
                # rastro tiene que decirlo.
                "started_at": {"old": None, "new": ocurrido_en.isoformat()},
                "started_received_at": {"old": None, "new": recibido_en.isoformat()},
                "started_at_source": {"old": None, "new": origen.value},
            },
        )

        creada = await WorkSessionsDAO.get_for_company_and_owner(
            session_id=session_id, company_id=company_id, user_id=user_id
        )
        return creada, True

    @staticmethod
    async def end(
        *,
        company_id: int,
        user_id: int,
        session_id: int,
        device_captured_at: datetime | None,
        utc_offset_minutes: int | None,
        end_anyway: bool = False,
    ) -> WorkSession:
        """Cierra la jornada del supervisor que llama. Nunca otra.

        404 si la fila no existe **o** no es de quien llama: da igual cuál de
        las dos sea, la respuesta no distingue — es el mismo principio que
        "un recurso de otro tenant no se confirma que existe", aplicado aquí a
        la propiedad de la jornada dentro del mismo tenant.

        Revisión con viaje en curso (D-07)
        -----------------------------------
        Si queda un viaje **en tránsito**, cerrar no es una acción destructiva
        automática: es una revisión. Sin `end_anyway` el servidor responde 409
        y la pantalla ofrece seguir trabajando o terminar de todos modos. Con
        `end_anyway`, el viaje queda **interrumpido** — no se fabrica una
        llegada que no ocurrió — y después se cierra la jornada.

        Un viaje operativo en `ARRIVED` **no** bloquea el cierre y **no se
        cierra**: completarlo es de RTE05, y ni inventar su cierre ni inventar
        un bloqueo serían comportamientos que el baseline defina.
        """
        existente = await WorkSessionsDAO.get_for_company_and_owner(
            session_id=session_id, company_id=company_id, user_id=user_id
        )
        if existente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work Session not found",
            )

        if existente.status == WorkSessionStatus.ENDED.value:
            # Replay seguro: la acción ya se aplicó, y reenviarla no debe
            # fallar ni volver a aplicarse.
            return existente

        # Importación diferida: `trips` depende de este módulo para la
        # semántica de tiempo, así que importarlo arriba cerraría el ciclo.
        from app.routers_api.trips.models import TripStatus
        from app.routers_api.trips.service import TripService

        en_ruta = await TripService.current(
            company_id=company_id, work_session_id=session_id
        )
        if en_ruta is not None and en_ruta.status == TripStatus.IN_TRANSIT.value:
            if not end_anyway:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You are still on route. Continue working, or end anyway.",
                )
            await TripService.interrupt(
                company_id=company_id,
                user_id=user_id,
                trip_id=en_ruta.id,
                device_captured_at=device_captured_at,
            )

        # Los bloqueos del viaje **primero**, la evidencia de cierre después: es
        # el orden que pide C4. Un viaje en tránsito hay que resolverlo antes de
        # pedir una lectura final, porque el kilometraje todavía puede cambiar.
        #
        # Esta guarda es más blanda que la de `Start Trip` a propósito: deja
        # cerrar el día con la excepción pedida aunque nadie la haya aprobado
        # todavía (Opción B). Quien termina ya no va a conducir, y retenerle la
        # jornada abierta escribiría un `ended_at` que no ocurrió.
        from app.routers_api.odometer.service import OdometerService

        await OdometerService.ensure_end_work_not_blocked(
            company_id=company_id, work_session_id=session_id
        )

        recibido_en = datetime.now(timezone.utc)
        # `not_before` es el `started_at` de esta misma jornada: un `End Work`
        # anterior a su propio `Start Work` es evidencia imposible, no un dato
        # que haya que creer porque venga del dispositivo.
        ocurrido_en, origen = _resolve_occurrence(
            received_at=recibido_en,
            device_captured_at=device_captured_at,
            not_before=existente.started_at,
        )

        async with transaction() as session:
            jornada = await session.scalar(
                select(WorkSession).where(WorkSession.id == session_id)
            )
            if jornada.status == WorkSessionStatus.ENDED.value:
                return jornada

            jornada.status = WorkSessionStatus.ENDED.value
            jornada.ended_at = ocurrido_en
            jornada.ended_received_at = recibido_en
            jornada.ended_at_source = origen.value
            jornada.end_device_captured_at = device_captured_at
            jornada.end_utc_offset_minutes = utc_offset_minutes
            jornada.version = jornada.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="work_session",
            entity_id=session_id,
            action="end",
            actor_user_id=user_id,
            summary="Work Session ended",
            changes={
                "status": {
                    "old": WorkSessionStatus.ACTIVE.value,
                    "new": WorkSessionStatus.ENDED.value,
                },
                "ended_at": {"old": None, "new": ocurrido_en.isoformat()},
                "ended_received_at": {"old": None, "new": recibido_en.isoformat()},
                "ended_at_source": {"old": None, "new": origen.value},
            },
        )

        return await WorkSessionsDAO.get_for_company_and_owner(
            session_id=session_id, company_id=company_id, user_id=user_id
        )

    @staticmethod
    async def current(*, company_id: int, user_id: int) -> WorkSession | None:
        return await WorkSessionsDAO.find_active_for_user(
            company_id=company_id, user_id=user_id
        )
