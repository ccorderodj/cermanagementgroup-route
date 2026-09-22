"""
DAO base.

El punto de extensión es `query()`: cada DAO describe **una vez** cómo se
seleccionan sus filas —con sus joins y sus filtros— y hereda gratis el conteo,
el orden y la paginación.

Antes `get_total()` y `calculate_offset()` estaban reimplementados en siete de
los ocho DAO, cada uno con su propia versión de los mismos filtros y su propio
`order_by(desc(id))` (AUD-BE-008). Duplicar dos métodos por módulo no duele con
ocho módulos; con los quince que faltan por construir, sí.

    class RolesDAO(BaseDAO):
        model = Role

        @classmethod
        def query(cls, *, company_id, name=None, **_):
            stmt = select(Role).where(Role.company_id == company_id)
            if name:
                stmt = stmt.where(Role.name.ilike(f"%{name}%"))
            return stmt

    page = await RolesDAO.paginate(page=1, page_size=20, company_id=7)
    page.items, page.total
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import Select, delete, func, insert, select, update

from app.core.db.session import db_session
from app.logger import logger


T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    """Una página de resultados junto al total que la contiene."""

    items: Sequence[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return math.ceil(self.total / self.page_size)


class BaseDAO:
    model: Any = None

    # ── Punto de extensión ──────────────────────────────────────────────────

    @classmethod
    def query(cls, **filters: Any) -> Select:
        """Consulta base del DAO. Los subclases la redefinen con sus filtros."""
        stmt = select(cls.model)
        for field_name, value in filters.items():
            if value is None:
                continue
            stmt = stmt.where(getattr(cls.model, field_name) == value)
        return stmt

    @classmethod
    def default_order(cls):
        return cls.model.id.desc()

    # ── Lecturas ────────────────────────────────────────────────────────────

    @classmethod
    async def find_by_id(cls, model_id: int):
        async with db_session() as session:
            return await session.scalar(
                select(cls.model).where(cls.model.id == model_id)
            )

    @classmethod
    async def find_one_or_none(cls, **filter_by):
        """Primera coincidencia o `None`.

        Usa `limit(1)` en vez de `scalar_one_or_none()`: varios de los campos
        por los que se filtra no son únicos, y la versión estricta convertía un
        duplicado en un 500 (AUD-BE-017).
        """
        async with db_session() as session:
            stmt = select(cls.model).filter_by(**filter_by).limit(1)
            return await session.scalar(stmt)

    @classmethod
    async def find_all(cls, **filter_by):
        async with db_session() as session:
            result = await session.execute(select(cls.model).filter_by(**filter_by))
            return result.scalars().all()

    @classmethod
    async def count(cls, **filters: Any) -> int:
        async with db_session() as session:
            subquery = cls.query(**filters).order_by(None).subquery()
            return int(
                await session.scalar(select(func.count()).select_from(subquery)) or 0
            )

    @classmethod
    async def paginate(
        cls,
        *,
        page: int,
        page_size: int,
        order_by: Any = None,
        **filters: Any,
    ) -> Page:
        """Página + total, con los mismos filtros en ambas consultas.

        Que el conteo derive de la misma `query()` que las filas es lo que
        garantiza que no puedan divergir, que es el error clásico al escribir
        `get_total` y `calculate_offset` por separado.
        """
        offset = page_size * (page - 1)
        stmt = cls.query(**filters)

        async with db_session() as session:
            count_subquery = stmt.order_by(None).subquery()
            total = int(
                await session.scalar(
                    select(func.count()).select_from(count_subquery)
                )
                or 0
            )

            rows = await session.execute(
                stmt.order_by(order_by if order_by is not None else cls.default_order())
                .limit(page_size)
                .offset(offset)
            )
            items = rows.unique().all()

        # `query()` puede seleccionar la entidad entera —una sola columna, la del
        # modelo— o un conjunto de columnas ya combinadas por joins. Se devuelve
        # la entidad en el primer caso y un dict en el segundo, que es lo que
        # esperan los schemas de lectura.
        normalized = [
            row[0] if len(row) == 1 else dict(row._mapping) for row in items
        ]

        return Page(items=normalized, total=total, page=page, page_size=page_size)

    # ── Escrituras ──────────────────────────────────────────────────────────

    @classmethod
    async def add(cls, **data):
        async with db_session() as session:
            try:
                result = await session.execute(
                    insert(cls.model).values(**data).returning(cls.model)
                )
                created = result.scalar_one()
                await session.commit()
                return created
            except Exception:
                logger.error(
                    "No se pudo insertar en %s",
                    cls.model.__tablename__,
                    exc_info=True,
                )
                await session.rollback()
                raise

    @classmethod
    async def update_by_id(cls, model_id: int, **values):
        async with db_session() as session:
            await session.execute(
                update(cls.model).where(cls.model.id == model_id).values(**values)
            )
            await session.commit()

    @classmethod
    async def delete_by_id(cls, model_id: int) -> None:
        async with db_session() as session:
            await session.execute(delete(cls.model).where(cls.model.id == model_id))
            await session.commit()
