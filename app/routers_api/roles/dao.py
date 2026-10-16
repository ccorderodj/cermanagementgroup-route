"""
Acceso a datos de roles.

**Todos** los métodos exigen `company_id`. No es una comodidad: es la garantía
de que ninguna consulta pueda devolver o modificar el rol de otro tenant. Un
método que no lo pidiera sería una puerta trasera, así que la firma obliga.
"""

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role


class RolesDAO(BaseDAO):
    model = Role

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        name: str | None = None,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        stmt = select(Role).where(Role.company_id == company_id)
        if name:
            stmt = stmt.where(Role.name.ilike(f"%{name}%"))
        if is_active is not None:
            stmt = stmt.where(Role.is_active.is_(is_active))
        return stmt

    @classmethod
    async def find_all_ordered(cls, *, company_id: int) -> list[Role]:
        async with db_session() as session:
            result = await session.execute(
                select(Role)
                .where(Role.company_id == company_id)
                .order_by(Role.name.asc())
            )
            return list(result.scalars().all())

    @classmethod
    async def get_for_company(cls, *, role_id: int, company_id: int) -> Role:
        """El rol, solo si es de esta compañía. 404 en caso contrario.

        Devolver 404 y no 403 es deliberado: un rol de otro tenant no debe ni
        siquiera confirmarse que existe.
        """
        async with db_session() as session:
            role = await session.scalar(
                select(Role).where(Role.id == role_id, Role.company_id == company_id)
            )

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
            )
        return role

    @classmethod
    async def permission_counts(cls, role_ids: list[int]) -> dict[int, int]:
        """Cuántas capacidades activas concede cada rol."""
        if not role_ids:
            return {}

        async with db_session() as session:
            rows = await session.execute(
                select(RolePermission.role_id, func.count(RolePermission.id))
                .where(
                    RolePermission.role_id.in_(role_ids),
                    RolePermission.is_active.is_(True),
                )
                .group_by(RolePermission.role_id)
            )
            return {role_id: count for role_id, count in rows.all()}

    @classmethod
    async def permission_catalog_for_role(
        cls,
        *,
        role_id: int,
        company_id: int,
    ) -> list[dict]:
        """El catálogo completo, marcando qué concede este rol."""
        await cls.get_for_company(role_id=role_id, company_id=company_id)

        async with db_session() as session:
            granted = set(
                (
                    await session.execute(
                        select(RolePermission.permission_id).where(
                            RolePermission.role_id == role_id,
                            RolePermission.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )

            rows = (
                await session.execute(
                    select(
                        Permission.id,
                        Permission.name,
                        Permission.description,
                    )
                    .where(Permission.is_active.is_(True))
                    .order_by(Permission.name)
                )
            ).mappings().all()

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
                    "granted": row["id"] in granted,
                }
            )
        return catalog

    # ── Escrituras ──────────────────────────────────────────────────────────

    @classmethod
    async def create(cls, *, company_id: int, **data) -> Role:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Role name is required",
            )

        async with db_session() as session:
            try:
                result = await session.execute(
                    Role.__table__.insert()
                    .values(company_id=company_id, **{**data, "name": name})
                    .returning(Role.id)
                )
                role_id = result.scalar_one()
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A role with that name already exists in this company",
                ) from exc

            return await session.scalar(select(Role).where(Role.id == role_id))

    @classmethod
    async def update_for_company(
        cls,
        *,
        role_id: int,
        company_id: int,
        **data,
    ) -> Role:
        await cls.get_for_company(role_id=role_id, company_id=company_id)

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided to update",
            )

        if isinstance(data.get("name"), str):
            data["name"] = data["name"].strip()

        async with db_session() as session:
            try:
                await session.execute(
                    update(Role)
                    .where(Role.id == role_id, Role.company_id == company_id)
                    .values(**data)
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A role with that name already exists in this company",
                ) from exc

            return await session.scalar(select(Role).where(Role.id == role_id))

    @classmethod
    async def soft_delete(cls, *, role_id: int, company_id: int) -> Role:
        """Desactiva el rol. No se borra: hay pertenencias apuntando a él."""
        return await cls.update_for_company(
            role_id=role_id,
            company_id=company_id,
            is_active=False,
        )

    @classmethod
    async def replace_permissions(cls, *, role_id: int, permission_ids: list[int]) -> None:
        """Deja el rol exactamente con estas capacidades.

        Solo la llama el servicio de aprobaciones, ya dentro de una transacción.
        """
        async with db_session() as session:
            await session.execute(
                delete(RolePermission).where(RolePermission.role_id == role_id)
            )
            for permission_id in sorted(set(permission_ids)):
                await session.execute(
                    RolePermission.__table__.insert().values(
                        role_id=role_id,
                        permission_id=permission_id,
                        is_active=True,
                    )
                )
            await session.commit()
