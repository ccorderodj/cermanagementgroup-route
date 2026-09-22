"""
Reglas de negocio de vehículos y asignaciones.

Aquí viven las decisiones que no son ni acceso a datos ni transporte HTTP:
cuándo una asignación sustituye a otra, qué se puede retirar y qué no, y qué
queda escrito en la traza de auditoría. Los handlers quedan finos y el DAO se
queda en persistencia, que es la regla de capas de
`ARCHITECTURE_BEST_PRACTICES.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import diff, record_event
from app.core.dao.concurrency import ensure_version
from app.core.db.session import transaction
from app.routers_api.users.models import Users
from app.routers_api.vehicles.dao import (
    SupervisorProfilesDAO,
    VehicleAssignmentsDAO,
    VehiclesDAO,
)
from app.routers_api.vehicles.models import (
    SupervisorProfile,
    Vehicle,
    VehicleAssignment,
)


#: Campos del vehículo que se comparan para la traza de auditoría.
_CAMPOS_AUDITADOS = (
    "make",
    "model",
    "year",
    "unit",
    "fuel_grade",
    "operational_mpg",
    "is_active",
)


def _instantanea(vehiculo: Vehicle) -> dict:
    return {
        campo: (
            str(getattr(vehiculo, campo))
            if campo == "operational_mpg"
            else getattr(vehiculo, campo)
        )
        for campo in _CAMPOS_AUDITADOS
    }


class VehicleService:
    """Alta, edición y retirada de vehículos."""

    @staticmethod
    async def create(
        *, company_id: int, actor_user_id: int, values: dict
    ) -> Vehicle:
        datos = dict(values)
        datos["fuel_grade"] = str(datos["fuel_grade"].value)

        async with transaction() as session:
            vehiculo = Vehicle(company_id=company_id, **datos)
            session.add(vehiculo)
            try:
                await session.flush()
            except IntegrityError as exc:
                # La unidad duplicada es la única colisión esperable aquí, y es
                # un error de quien la escribe, no un fallo del servidor.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A vehicle with unit '{datos['unit']}' already exists.",
                ) from exc

            vehicle_id = vehiculo.id
            instantanea = _instantanea(vehiculo)

        await record_event(
            company_id=company_id,
            entity_type="vehicle",
            entity_id=vehicle_id,
            action="create",
            actor_user_id=actor_user_id,
            summary=f"Vehicle {datos['unit']} created",
            changes={campo: {"old": None, "new": valor} for campo, valor in instantanea.items()},
        )
        return await VehiclesDAO.get_for_company(
            vehicle_id=vehicle_id, company_id=company_id
        )

    @staticmethod
    async def update(
        *,
        company_id: int,
        vehicle_id: int,
        actor_user_id: int,
        values: dict,
        expected_version: int | None,
    ) -> Vehicle:
        cambios = {k: v for k, v in values.items() if v is not None}
        if "fuel_grade" in cambios:
            cambios["fuel_grade"] = str(cambios["fuel_grade"].value)

        async with transaction() as session:
            vehiculo = await session.scalar(
                select(Vehicle).where(
                    Vehicle.id == vehicle_id, Vehicle.company_id == company_id
                )
            )
            if vehiculo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
                )

            ensure_version(current=vehiculo.version, expected=expected_version)

            antes = _instantanea(vehiculo)
            for campo, valor in cambios.items():
                setattr(vehiculo, campo, valor)
            # La versión sube en cada escritura: es lo que hará fallar a quien
            # esté editando la misma ficha con el número anterior.
            vehiculo.version = vehiculo.version + 1

            try:
                await session.flush()
            except IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A vehicle with that unit already exists.",
                ) from exc

            despues = _instantanea(vehiculo)
            unidad = vehiculo.unit

        delta = diff(antes, despues)
        if delta:
            await record_event(
                company_id=company_id,
                entity_type="vehicle",
                entity_id=vehicle_id,
                action="update",
                actor_user_id=actor_user_id,
                summary=f"Vehicle {unidad} updated",
                changes=delta,
            )

        return await VehiclesDAO.get_for_company(
            vehicle_id=vehicle_id, company_id=company_id
        )

    @staticmethod
    async def set_active(
        *,
        company_id: int,
        vehicle_id: int,
        actor_user_id: int,
        is_active: bool,
        expected_version: int | None,
    ) -> Vehicle:
        """Retira o reactiva un vehículo. **Nunca lo borra.**

        Un vehículo con asignaciones detrás sostiene la trazabilidad de esas
        jornadas; borrarlo dejaría el historial hablando de algo que ya no
        existe. Retirar uno que alguien está conduciendo ahora mismo se rechaza:
        primero se cierra la asignación.
        """
        if not is_active:
            conductores = await VehicleAssignmentsDAO.current_holders(
                company_id=company_id, vehicle_id=vehicle_id
            )
            if conductores:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This vehicle is currently assigned. End the assignment "
                        "before deactivating it."
                    ),
                )

        return await VehicleService.update(
            company_id=company_id,
            vehicle_id=vehicle_id,
            actor_user_id=actor_user_id,
            values={"is_active": is_active},
            expected_version=expected_version,
        )


class SupervisorProfileService:
    """Designación de supervisores de Route."""

    @staticmethod
    async def create(
        *, company_id: int, actor_user_id: int, user_id: int
    ) -> SupervisorProfile:
        existente = await SupervisorProfilesDAO.find_by_user(
            company_id=company_id, user_id=user_id
        )
        if existente is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This user already has a Route supervisor profile.",
            )

        async with transaction() as session:
            perfil = SupervisorProfile(company_id=company_id, user_id=user_id)
            session.add(perfil)
            try:
                await session.flush()
            except IntegrityError as exc:
                # La FK compuesta contra `user_company` es la que rechaza a un
                # usuario que no pertenece a esta compañía. Que lo pare la base
                # y no un `if` es el punto: no depende de que nadie se acuerde.
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found in this company",
                ) from exc
            perfil_id = perfil.id

        await record_event(
            company_id=company_id,
            entity_type="supervisor_profile",
            entity_id=perfil_id,
            action="create",
            actor_user_id=actor_user_id,
            summary="Route supervisor profile created",
            changes={"user_id": {"old": None, "new": user_id}},
        )
        return await SupervisorProfilesDAO.get_for_company(
            supervisor_profile_id=perfil_id, company_id=company_id
        )


    @staticmethod
    async def set_active(
        *,
        company_id: int,
        supervisor_profile_id: int,
        actor_user_id: int,
        is_active: bool,
        expected_version: int | None,
    ) -> SupervisorProfile:
        """Retira o restaura la designación de supervisor. **Nunca la borra.**

        Retirar a quien tiene un vehículo asignado se rechaza: primero se cierra
        la asignación. Si no, quedaría un vehículo vigente en manos de alguien
        que ya no es supervisor, que es un estado que nadie sabría interpretar.
        """
        if not is_active:
            vigente = await VehicleAssignmentsDAO.current_for_supervisor(
                company_id=company_id,
                supervisor_profile_id=supervisor_profile_id,
            )
            if vigente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This supervisor still has a vehicle assigned. End the "
                        "assignment before removing the designation."
                    ),
                )

        async with transaction() as session:
            perfil = await session.scalar(
                select(SupervisorProfile).where(
                    SupervisorProfile.id == supervisor_profile_id,
                    SupervisorProfile.company_id == company_id,
                )
            )
            if perfil is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Supervisor profile not found",
                )

            ensure_version(current=perfil.version, expected=expected_version)

            antes = perfil.is_active
            perfil.is_active = is_active
            perfil.version = perfil.version + 1
            await session.flush()

        if antes != is_active:
            await record_event(
                company_id=company_id,
                entity_type="supervisor_profile",
                entity_id=supervisor_profile_id,
                action="activate" if is_active else "deactivate",
                actor_user_id=actor_user_id,
                summary=(
                    "Route supervisor designation restored"
                    if is_active
                    else "Route supervisor designation removed"
                ),
                changes={"is_active": {"old": antes, "new": is_active}},
            )

        return await SupervisorProfilesDAO.get_for_company(
            supervisor_profile_id=supervisor_profile_id, company_id=company_id
        )


class VehicleAssignmentService:
    """Asignación efectiva de vehículo a supervisor, con su historia."""

    @staticmethod
    async def assign(
        *,
        company_id: int,
        supervisor_profile_id: int,
        vehicle_id: int,
        actor_user_id: int,
        effective_from: datetime | None = None,
    ) -> VehicleAssignment:
        """Asigna un vehículo cerrando antes la asignación vigente, si la hay.

        Cerrar y abrir ocurren en **la misma transacción**: dejar la mitad
        aplicada describiría o un supervisor sin vehículo o uno con dos, y
        ninguno de los dos estados pasó nunca de verdad.
        """
        desde = effective_from or datetime.now(timezone.utc)

        # Ambos existen y son de esta compañía. La FK compuesta lo garantizaría
        # igualmente, pero comprobarlo antes da un 404 legible en vez de un
        # error de integridad.
        await SupervisorProfilesDAO.get_for_company(
            supervisor_profile_id=supervisor_profile_id, company_id=company_id
        )
        vehiculo = await VehiclesDAO.get_for_company(
            vehicle_id=vehicle_id, company_id=company_id
        )
        if not vehiculo.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A retired vehicle cannot be assigned.",
            )

        if await VehicleAssignmentsDAO.overlaps_existing(
            company_id=company_id,
            supervisor_profile_id=supervisor_profile_id,
            effective_from=desde,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That start date falls inside a previous assignment period "
                    "for this supervisor."
                ),
            )

        async with transaction() as session:
            anterior = await session.scalar(
                select(VehicleAssignment).where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.supervisor_profile_id == supervisor_profile_id,
                    VehicleAssignment.effective_to.is_(None),
                )
            )

            anterior_id = None
            if anterior is not None:
                if anterior.vehicle_id == vehicle_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="That vehicle is already assigned to this supervisor.",
                    )
                if desde < anterior.effective_from:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "The new assignment cannot start before the current "
                            "one did."
                        ),
                    )
                # Se cierra, no se reescribe: la fila sigue ahí diciendo qué se
                # condujo y hasta cuándo.
                anterior.effective_to = desde
                anterior_id = anterior.id
                await session.flush()

            asignacion = VehicleAssignment(
                company_id=company_id,
                supervisor_profile_id=supervisor_profile_id,
                vehicle_id=vehicle_id,
                effective_from=desde,
            )
            session.add(asignacion)
            try:
                await session.flush()
            except IntegrityError as exc:
                # El índice único parcial. Dos peticiones simultáneas llegan
                # hasta aquí y sólo una sobrevive: la otra recibe 409 en vez de
                # crear un segundo vehículo vigente.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This supervisor already has a current vehicle "
                        "assignment. Reload and try again."
                    ),
                ) from exc

            asignacion_id = asignacion.id

        if anterior_id is not None:
            await record_event(
                company_id=company_id,
                entity_type="vehicle_assignment",
                entity_id=anterior_id,
                action="end",
                actor_user_id=actor_user_id,
                summary="Vehicle assignment ended by reassignment",
                changes={"effective_to": {"old": None, "new": desde.isoformat()}},
            )

        await record_event(
            company_id=company_id,
            entity_type="vehicle_assignment",
            entity_id=asignacion_id,
            action="create",
            actor_user_id=actor_user_id,
            summary=f"Vehicle {vehiculo.unit} assigned",
            changes={
                "supervisor_profile_id": {"old": None, "new": supervisor_profile_id},
                "vehicle_id": {"old": None, "new": vehicle_id},
                "effective_from": {"old": None, "new": desde.isoformat()},
            },
        )

        return await VehicleAssignmentsDAO.get_for_company(
            assignment_id=asignacion_id, company_id=company_id
        )

    @staticmethod
    async def end(
        *,
        company_id: int,
        assignment_id: int,
        actor_user_id: int,
        effective_to: datetime | None = None,
    ) -> VehicleAssignment:
        """Cierra una asignación vigente sin poner otra en su lugar.

        El supervisor se queda sin vehículo, que es un estado legítimo: alguien
        deja de conducir antes de que se le asigne el siguiente.
        """
        hasta = effective_to or datetime.now(timezone.utc)

        async with transaction() as session:
            asignacion = await session.scalar(
                select(VehicleAssignment).where(
                    VehicleAssignment.id == assignment_id,
                    VehicleAssignment.company_id == company_id,
                )
            )
            if asignacion is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vehicle assignment not found",
                )
            if asignacion.effective_to is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="That assignment is already closed.",
                )
            if hasta < asignacion.effective_from:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="The end date cannot be earlier than the start date.",
                )

            asignacion.effective_to = hasta
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="vehicle_assignment",
            entity_id=assignment_id,
            action="end",
            actor_user_id=actor_user_id,
            summary="Vehicle assignment ended",
            changes={"effective_to": {"old": None, "new": hasta.isoformat()}},
        )

        return await VehicleAssignmentsDAO.get_for_company(
            assignment_id=assignment_id, company_id=company_id
        )

    @staticmethod
    async def current_vehicle(
        *, company_id: int, supervisor_profile_id: int
    ) -> Vehicle | None:
        """El vehículo actual del supervisor, derivado de la asignación vigente."""
        asignacion = await VehicleAssignmentsDAO.current_for_supervisor(
            company_id=company_id, supervisor_profile_id=supervisor_profile_id
        )
        if asignacion is None:
            return None
        return await VehiclesDAO.get_for_company(
            vehicle_id=asignacion.vehicle_id, company_id=company_id
        )
