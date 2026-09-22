"""
Consulta de vinculos rol-capacidad.

Solo lectura, y siempre acotado a la compania: el join con `role` no es
decorativo, es lo que impide listar las concesiones de otro tenant.

Todo lo que escribia aqui —`add`, `update`, `soft_delete`,
`replace_role_permissions`, `activate_inactive_role_permissions_by_role`—
se retiro: esquivaba el maker-checker, y ademas ningun endpoint lo llamaba.
Un control que se puede rodear por otra puerta no es un control.
"""

from sqlalchemy import Select, select

from app.core.dao.base import BaseDAO
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role


class RolePermissionsDAO(BaseDAO):
    model = RolePermission

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        role_id: int | None = None,
        permission_id: int | None = None,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        stmt = (
            select(RolePermission)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.company_id == company_id)
        )

        if role_id is not None:
            stmt = stmt.where(RolePermission.role_id == role_id)
        if permission_id is not None:
            stmt = stmt.where(RolePermission.permission_id == permission_id)
        if is_active is not None:
            stmt = stmt.where(RolePermission.is_active.is_(is_active))

        return stmt

    @classmethod
    async def find_all_ordered(
        cls,
        *,
        company_id: int,
        role_id: int | None = None,
    ) -> list[RolePermission]:
        from app.core.db.session import db_session

        async with db_session() as session:
            stmt = cls.query(company_id=company_id, role_id=role_id).order_by(
                RolePermission.id.desc()
            )
            result = await session.execute(stmt)
            return list(result.scalars().unique().all())
