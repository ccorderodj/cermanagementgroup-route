"""
Acceso a datos de vehículos, perfiles de supervisor y asignaciones.

Todos los métodos exigen `company_id` en la firma. No es comodidad: es lo que
hace imposible escribir por descuido una consulta que alcance el vehículo de
otro tenant. Un método que no lo pidiera sería una puerta trasera.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, select

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import (
    SupervisorProfile,
    Vehicle,
    VehicleAssignment,
)


class VehiclesDAO(BaseDAO):
    model = Vehicle

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        search: str | None = None,
        is_active: bool | None = None,
        fuel_grade: str | None = None,
        **_: object,
    ) -> Select:
        stmt = select(Vehicle).where(Vehicle.company_id == company_id)
        if search:
            patron = f"%{search}%"
            stmt = stmt.where(
                Vehicle.unit.ilike(patron)
                | Vehicle.make.ilike(patron)
                | Vehicle.model.ilike(patron)
            )
        if is_active is not None:
            stmt = stmt.where(Vehicle.is_active.is_(is_active))
        if fuel_grade:
            stmt = stmt.where(Vehicle.fuel_grade == fuel_grade)
        return stmt

    @classmethod
    def default_order(cls):
        return Vehicle.unit.asc()

    @classmethod
    async def get_for_company(cls, *, vehicle_id: int, company_id: int) -> Vehicle:
        """El vehículo, sólo si es de esta compañía.

        404 y no 403: confirmar que existe un recurso de otro tenant ya es
        filtrar información (regla 8 de `AGENTS.md`).
        """
        async with db_session() as session:
            vehiculo = await session.scalar(
                select(Vehicle).where(
                    Vehicle.id == vehicle_id, Vehicle.company_id == company_id
                )
            )

        if vehiculo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
            )
        return vehiculo

    @classmethod
    async def find_by_unit(cls, *, company_id: int, unit: str) -> Vehicle | None:
        async with db_session() as session:
            return await session.scalar(
                select(Vehicle).where(
                    Vehicle.company_id == company_id, Vehicle.unit == unit
                )
            )


class SupervisorProfilesDAO(BaseDAO):
    model = SupervisorProfile

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        stmt = select(SupervisorProfile).where(
            SupervisorProfile.company_id == company_id
        )
        if is_active is not None:
            stmt = stmt.where(SupervisorProfile.is_active.is_(is_active))
        return stmt

    @classmethod
    async def get_for_company(
        cls, *, supervisor_profile_id: int, company_id: int
    ) -> SupervisorProfile:
        async with db_session() as session:
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
        return perfil

    @classmethod
    async def find_by_user(
        cls, *, company_id: int, user_id: int
    ) -> SupervisorProfile | None:
        async with db_session() as session:
            return await session.scalar(
                select(SupervisorProfile).where(
                    SupervisorProfile.company_id == company_id,
                    SupervisorProfile.user_id == user_id,
                )
            )

    @classmethod
    async def list_with_identity(cls, *, company_id: int) -> list[dict]:
        """Perfiles con el nombre que ya vive en `user`, resuelto por join.

        El nombre **no** se copia a `supervisor_profile`: se lee de su dueño.
        Esta consulta existe para que la pantalla de asignaciones no tenga que
        cruzar dos llamadas para pintar una fila.
        """
        async with db_session() as session:
            filas = await session.execute(
                select(
                    SupervisorProfile.id.label("id"),
                    SupervisorProfile.user_id.label("user_id"),
                    SupervisorProfile.is_active.label("is_active"),
                    SupervisorProfile.version.label("version"),
                    SupervisorProfile.created_at.label("created_at"),
                    SupervisorProfile.updated_at.label("updated_at"),
                    Users.first_name.label("first_name"),
                    Users.last_name.label("last_name"),
                    Users.email.label("email"),
                )
                .join(Users, Users.id == SupervisorProfile.user_id)
                .where(SupervisorProfile.company_id == company_id)
                .order_by(Users.first_name.asc(), Users.last_name.asc())
            )
            return [dict(fila) for fila in filas.mappings().all()]


class VehicleAssignmentsDAO(BaseDAO):
    model = VehicleAssignment

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        supervisor_profile_id: int | None = None,
        vehicle_id: int | None = None,
        current_only: bool = False,
        **_: object,
    ) -> Select:
        stmt = select(VehicleAssignment).where(
            VehicleAssignment.company_id == company_id
        )
        if supervisor_profile_id is not None:
            stmt = stmt.where(
                VehicleAssignment.supervisor_profile_id == supervisor_profile_id
            )
        if vehicle_id is not None:
            stmt = stmt.where(VehicleAssignment.vehicle_id == vehicle_id)
        if current_only:
            stmt = stmt.where(VehicleAssignment.effective_to.is_(None))
        return stmt

    @classmethod
    def default_order(cls):
        return VehicleAssignment.effective_from.desc()

    @classmethod
    async def current_for_supervisor(
        cls, *, company_id: int, supervisor_profile_id: int
    ) -> VehicleAssignment | None:
        """La asignación vigente, que es la que no tiene fecha de fin.

        Es **la** fuente del vehículo actual de un supervisor. No hay copia en
        el perfil que pueda decir otra cosa.
        """
        async with db_session() as session:
            return await session.scalar(
                select(VehicleAssignment).where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.supervisor_profile_id == supervisor_profile_id,
                    VehicleAssignment.effective_to.is_(None),
                )
            )

    @classmethod
    async def history_for_supervisor(
        cls, *, company_id: int, supervisor_profile_id: int
    ) -> list[dict]:
        """Historial completo, con los datos del vehículo resueltos por join."""
        async with db_session() as session:
            filas = await session.execute(
                select(
                    VehicleAssignment.id.label("id"),
                    VehicleAssignment.supervisor_profile_id.label(
                        "supervisor_profile_id"
                    ),
                    VehicleAssignment.vehicle_id.label("vehicle_id"),
                    VehicleAssignment.effective_from.label("effective_from"),
                    VehicleAssignment.effective_to.label("effective_to"),
                    VehicleAssignment.created_at.label("created_at"),
                    VehicleAssignment.updated_at.label("updated_at"),
                    Vehicle.unit.label("vehicle_unit"),
                    Vehicle.make.label("vehicle_make"),
                    Vehicle.model.label("vehicle_model"),
                    Vehicle.year.label("vehicle_year"),
                )
                .join(
                    Vehicle,
                    and_(
                        Vehicle.id == VehicleAssignment.vehicle_id,
                        Vehicle.company_id == VehicleAssignment.company_id,
                    ),
                )
                .where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.supervisor_profile_id == supervisor_profile_id,
                )
                .order_by(VehicleAssignment.effective_from.desc())
            )
            return [dict(fila) for fila in filas.mappings().all()]

    @classmethod
    async def get_for_company(
        cls, *, assignment_id: int, company_id: int
    ) -> VehicleAssignment:
        async with db_session() as session:
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
        return asignacion

    @classmethod
    async def has_any_for_vehicle(cls, *, company_id: int, vehicle_id: int) -> bool:
        """Si el vehículo tiene historial. Decide si puede retirarse sin más."""
        async with db_session() as session:
            encontrada = await session.scalar(
                select(VehicleAssignment.id)
                .where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.vehicle_id == vehicle_id,
                )
                .limit(1)
            )
        return encontrada is not None

    @classmethod
    async def current_holders(
        cls, *, company_id: int, vehicle_id: int
    ) -> list[int]:
        """Supervisores que conducen ahora mismo este vehículo.

        Puede ser más de uno: CER no aprobó que un vehículo sea exclusivo de un
        supervisor, así que el modelo no lo impide y esta consulta tampoco lo
        asume.
        """
        async with db_session() as session:
            filas = await session.execute(
                select(VehicleAssignment.supervisor_profile_id).where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.vehicle_id == vehicle_id,
                    VehicleAssignment.effective_to.is_(None),
                )
            )
            return list(filas.scalars().all())

    @classmethod
    async def overlaps_existing(
        cls,
        *,
        company_id: int,
        supervisor_profile_id: int,
        effective_from: datetime,
    ) -> bool:
        """Si ya hay una asignación cerrada que cubre `effective_from`.

        El índice único parcial impide dos **vigentes**; esto cubre el otro
        caso: retroceder la fecha de inicio dentro de un periodo ya cerrado,
        que produciría dos vehículos válidos a la vez en ese instante.
        """
        async with db_session() as session:
            encontrada = await session.scalar(
                select(VehicleAssignment.id)
                .where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.supervisor_profile_id == supervisor_profile_id,
                    VehicleAssignment.effective_from <= effective_from,
                    VehicleAssignment.effective_to.is_not(None),
                    VehicleAssignment.effective_to > effective_from,
                )
                .limit(1)
            )
        return encontrada is not None
