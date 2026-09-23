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
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus


def _session_date_from(started_at_utc: datetime, utc_offset_minutes: int | None) -> date:
    """La fecha del calendario local en el que ocurrió `started_at` (D-10).

    Se confía en el desfase que reporta el dispositivo —qué zona horaria
    tiene configurada—, no en su reloj —qué hora dice que es—. Son preguntas
    distintas: el reloj de un teléfono puede estar mal ajustado por minutos u
    horas (deriva), pero su zona horaria casi nunca lo está, porque sale de
    la configuración del sistema operativo y no del deriva del reloj. Por eso
    el ancla temporal sigue siendo `started_at`, autoritativo del servidor; el
    desfase solo decide qué día del calendario sintió quien apretó el botón.

    Sin desfase —evidencia ausente, cliente antiguo, acción encolada sin
    conectividad para reportarlo— la fecha cae a UTC. Es un límite honesto, no
    un fallo silencioso: un `Start Work` nunca se bloquea por falta de esta
    evidencia (D-10, "el manejo del tiempo nunca bloquea Start Work o End
    Work").
    """
    if utc_offset_minutes is None:
        return started_at_utc.date()
    return (started_at_utc + timedelta(minutes=utc_offset_minutes)).date()


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

        ahora = datetime.now(timezone.utc)
        session_date = _session_date_from(ahora, utc_offset_minutes)

        try:
            async with transaction() as session:
                jornada = WorkSession(
                    company_id=company_id,
                    user_id=user_id,
                    status=WorkSessionStatus.ACTIVE.value,
                    session_date=session_date,
                    started_at=ahora,
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
    ) -> WorkSession:
        """Cierra la jornada del supervisor que llama. Nunca otra.

        404 si la fila no existe **o** no es de quien llama: da igual cuál de
        las dos sea, la respuesta no distingue — es el mismo principio que
        "un recurso de otro tenant no se confirma que existe", aplicado aquí a
        la propiedad de la jornada dentro del mismo tenant.
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

        ahora = datetime.now(timezone.utc)

        async with transaction() as session:
            jornada = await session.scalar(
                select(WorkSession).where(WorkSession.id == session_id)
            )
            if jornada.status == WorkSessionStatus.ENDED.value:
                return jornada

            jornada.status = WorkSessionStatus.ENDED.value
            jornada.ended_at = ahora
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
                "ended_at": {"old": None, "new": ahora.isoformat()},
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
