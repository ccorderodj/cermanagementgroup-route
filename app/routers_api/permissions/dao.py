"""
Lectura del catálogo de capacidades.

Sin escrituras: el catálogo lo define `app/core/rbac/catalog.py` y lo siembra el
bootstrap. Un administrador de tenant no crea capacidades porque una capacidad
sin endpoint detrás no hace nada, y el CRUD que había aquí permitía justo eso.
"""

from sqlalchemy import Select, select

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role


class PermissionsDAO(BaseDAO):
    model = Permission

    @classmethod
    def query(
        cls,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        stmt = select(Permission)
        if name:
            stmt = stmt.where(Permission.name.ilike(f"%{name}%"))
        if is_active is not None:
            stmt = stmt.where(Permission.is_active.is_(is_active))
        return stmt

    @classmethod
    def default_order(cls):
        return Permission.name.asc()

    @classmethod
    async def find_all_ordered(cls) -> list[Permission]:
        async with db_session() as session:
            result = await session.execute(
                select(Permission)
                .where(Permission.is_active.is_(True))
                .order_by(Permission.name)
            )
            return list(result.scalars().all())

    @classmethod
    async def feature_map(cls, *, company_id: int) -> list[dict]:
        """El catálogo visto como mapa de capacidades del sistema.

        Agrupa por módulo y acción, y dice qué roles **de esta compañía** tienen
        cada capacidad. El filtro por `company_id` es lo que impide que la
        pantalla muestre los roles de otro tenant.
        """
        async with db_session() as session:
            rows = (
                await session.execute(
                    select(
                        Permission.id,
                        Permission.name,
                        Permission.description,
                        Permission.is_active,
                    ).order_by(Permission.name)
                )
            ).mappings().all()

            grants = (
                await session.execute(
                    select(RolePermission.permission_id, Role.name, Role.category)
                    .join(Role, Role.id == RolePermission.role_id)
                    .where(
                        Role.company_id == company_id,
                        RolePermission.is_active.is_(True),
                        Role.is_active.is_(True),
                    )
                )
            ).all()

        by_permission: dict[int, list[dict]] = {}
        for permission_id, role_name, role_category in grants:
            by_permission.setdefault(permission_id, []).append(
                {"name": role_name, "category": role_category}
            )

        catalog = []
        for row in rows:
            module, _, action = (row["name"] or "").partition(".")
            catalog.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "module": module or row["name"],
                    "action": action or "",
                    "is_active": row["is_active"],
                    "roles": sorted(
                        by_permission.get(row["id"], []),
                        key=lambda entry: entry["name"],
                    ),
                }
            )
        return catalog
