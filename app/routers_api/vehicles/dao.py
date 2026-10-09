"""
Acceso a datos de vehículos, perfiles de supervisor y asignaciones.

Todos los métodos exigen `company_id` en la firma. No es comodidad: es lo que
hace imposible escribir por descuido una consulta que alcance el vehículo de
otro tenant. Un método que no lo pidiera sería una puerta trasera.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, or_, select

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
        stmt = select(Vehicle).where(
            Vehicle.company_id == company_id, Vehicle.deleted_at.is_(None)
        )
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
        """El vehículo, sólo si es de esta compañía y sigue en la administración.

        404 y no 403: confirmar que existe un recurso de otro tenant ya es
        filtrar información (regla 8 de `AGENTS.md`). Un vehículo borrado recibe
        el mismo trato, por el mismo motivo: el administrador ya no puede verlo.
        """
        async with db_session() as session:
            vehiculo = await session.scalar(
                select(Vehicle).where(
                    Vehicle.id == vehicle_id,
                    Vehicle.company_id == company_id,
                    Vehicle.deleted_at.is_(None),
                )
            )

        if vehiculo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
            )
        return vehiculo

    @classmethod
    async def find_by_unit(cls, *, company_id: int, unit: str) -> Vehicle | None:
        """Ignora los borrados: su unidad queda libre para reutilizarse.

        Es la contraparte en código del índice único parcial. Si mirara también
        las lápidas, el alta rechazaría "V-014" por un conflicto con una fila
        que el administrador ya no ve, y no habría forma de entender el error.
        """
        async with db_session() as session:
            return await session.scalar(
                select(Vehicle).where(
                    Vehicle.company_id == company_id,
                    Vehicle.unit == unit,
                    Vehicle.deleted_at.is_(None),
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
            SupervisorProfile.company_id == company_id,
            SupervisorProfile.deleted_at.is_(None),
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
                    SupervisorProfile.deleted_at.is_(None),
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
        """La designación vigente de esa persona, o `None` si ya no la tiene.

        Ignora las borradas a propósito: es la consulta que usa `Start Work`
        para resolver el vehículo del supervisor, y una designación retirada no
        debe seguir aportando contexto operativo.
        """
        async with db_session() as session:
            return await session.scalar(
                select(SupervisorProfile).where(
                    SupervisorProfile.company_id == company_id,
                    SupervisorProfile.user_id == user_id,
                    SupervisorProfile.deleted_at.is_(None),
                )
            )

    @classmethod
    async def list_candidates(cls, *, company_id: int) -> list[dict]:
        """Usuarios del tenant con su condición de supervisor de Route.

        Es la consulta que hace visible la cadena
        `usuario -> designación -> vehículo` en una sola pantalla. **No duplica
        identidad**: lee `user` y `user_company` por join y sólo añade si existe
        el perfil de Route. Un usuario sin perfil aparece con
        `supervisor_profile_id = NULL`, que es exactamente lo que el
        administrador necesita ver para poder designarlo.
        """
        from app.routers_api.companies.models import UserCompany
        from app.routers_api.roles.models import Role

        async with db_session() as session:
            filas = await session.execute(
                select(
                    Users.id.label("user_id"),
                    Users.first_name.label("first_name"),
                    Users.last_name.label("last_name"),
                    Users.email.label("email"),
                    Users.username.label("username"),
                    UserCompany.is_active.label("membership_active"),
                    Role.name.label("role_name"),
                    SupervisorProfile.id.label("supervisor_profile_id"),
                    SupervisorProfile.is_active.label("supervisor_active"),
                    SupervisorProfile.version.label("supervisor_version"),
                    SupervisorProfile.operational_time_zone.label(
                        "supervisor_time_zone"
                    ),
                )
                .join(UserCompany, UserCompany.user_id == Users.id)
                .outerjoin(Role, Role.id == UserCompany.role_id)
                .outerjoin(
                    SupervisorProfile,
                    and_(
                        SupervisorProfile.user_id == Users.id,
                        SupervisorProfile.company_id == company_id,
                        # Una designación borrada no cuenta: la persona vuelve a
                        # aparecer como candidata, que es lo que hace el borrado
                        # reversible sin resucitar la fila anterior.
                        SupervisorProfile.deleted_at.is_(None),
                    ),
                )
                .where(UserCompany.company_id == company_id)
                .order_by(Users.first_name.asc(), Users.last_name.asc())
            )
            return [dict(fila) for fila in filas.mappings().all()]

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
                    SupervisorProfile.operational_time_zone.label(
                        "operational_time_zone"
                    ),
                    SupervisorProfile.created_at.label("created_at"),
                    SupervisorProfile.updated_at.label("updated_at"),
                    Users.first_name.label("first_name"),
                    Users.last_name.label("last_name"),
                    Users.email.label("email"),
                )
                .join(Users, Users.id == SupervisorProfile.user_id)
                .where(
                    SupervisorProfile.company_id == company_id,
                    SupervisorProfile.deleted_at.is_(None),
                )
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
    async def effective_at(
        cls, *, company_id: int, supervisor_profile_id: int, moment: datetime
    ) -> VehicleAssignment | None:
        """La asignación que **aplica** en ese instante.

        Aplica cuando empezó (`effective_from <= moment`) y todavía no acabó
        (`effective_to` nulo o posterior). Las dos mitades importan:

        * sin la primera, una asignación fechada para el mes que viene se
          aplicaría hoy — un vehículo que el supervisor no tiene todavía, con
          una lectura de odómetro exigida por él;
        * sin la segunda, una asignación cerrada seguiría aplicando.

        El instante se recibe, no se toma de `now()`, y eso es deliberado: una
        jornada encolada sin cobertura ocurrió antes de que el servidor la
        supiera (D-10). Resolverla con el reloj de la recepción le atribuiría el
        vehículo que tenía al reconectar, no el que tenía al empezar.
        """
        async with db_session() as session:
            return await session.scalar(
                select(VehicleAssignment).where(
                    VehicleAssignment.company_id == company_id,
                    VehicleAssignment.supervisor_profile_id == supervisor_profile_id,
                    VehicleAssignment.effective_from <= moment,
                    or_(
                        VehicleAssignment.effective_to.is_(None),
                        VehicleAssignment.effective_to > moment,
                    ),
                )
            )

    @classmethod
    async def open_for_supervisor(
        cls, *, company_id: int, supervisor_profile_id: int
    ) -> VehicleAssignment | None:
        """La asignación **abierta**: la que no tiene fecha de fin.

        Responde "¿hay un vehículo en manos de este supervisor en el registro?",
        que es la pregunta correcta para impedir desactivarlo o borrarlo —
        también si su asignación empieza mañana.

        **No** es la que decide el vehículo de una jornada: para eso está
        `effective_at`, porque una asignación futura existe en el registro y aun
        así no aplica todavía.

        Se llamaba `current_for_supervisor`, y el nombre invitaba justo a la
        confusión que §8.3 de RTE06 pide no dejar en pie: "current" sugería
        vigente, y esto es otra cosa. El nombre dice ahora lo que hace.
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

