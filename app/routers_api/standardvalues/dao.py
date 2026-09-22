"""Acceso a datos de las listas configurables. Siempre acotado por compañía."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.standardvalues.models import StandardValue


class StandardValuesDAO(BaseDAO):
    model = StandardValue

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        list_code: str | None = None,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        stmt = select(StandardValue).where(StandardValue.company_id == company_id)
        if list_code:
            stmt = stmt.where(StandardValue.list_code == list_code)
        if is_active is not None:
            stmt = stmt.where(StandardValue.is_active.is_(is_active))
        return stmt

    @classmethod
    def default_order(cls):
        return StandardValue.sort_order.asc()

    @classmethod
    async def list_for_code(
        cls,
        *,
        company_id: int,
        list_code: str,
        include_inactive: bool = False,
    ) -> list[StandardValue]:
        """Valores de una lista, en su orden.

        `include_inactive` existe porque un administrador necesita ver lo que
        retiró —para reactivarlo, o para entender un informe antiguo—, mientras
        que un formulario operativo sólo debe ofrecer lo vigente. El que llama
        decide cuál de las dos preguntas está haciendo.
        """
        async with db_session() as session:
            stmt = select(StandardValue).where(
                StandardValue.company_id == company_id,
                StandardValue.list_code == list_code,
            )
            if not include_inactive:
                stmt = stmt.where(StandardValue.is_active.is_(True))

            filas = await session.execute(
                stmt.order_by(
                    StandardValue.sort_order.asc(), StandardValue.label.asc()
                )
            )
            return list(filas.scalars().all())

    @classmethod
    async def get_for_company(
        cls, *, value_id: int, company_id: int
    ) -> StandardValue:
        async with db_session() as session:
            valor = await session.scalar(
                select(StandardValue).where(
                    StandardValue.id == value_id,
                    StandardValue.company_id == company_id,
                )
            )

        if valor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Standard value not found",
            )
        return valor

    @classmethod
    async def next_sort_order(cls, *, company_id: int, list_code: str) -> int:
        """El siguiente hueco al final de la lista."""
        async with db_session() as session:
            maximo = await session.scalar(
                select(func.max(StandardValue.sort_order)).where(
                    StandardValue.company_id == company_id,
                    StandardValue.list_code == list_code,
                )
            )
        return int(maximo or 0) + 1

    @classmethod
    async def counts_by_list(cls, *, company_id: int) -> dict[str, int]:
        """Cuántos valores activos tiene cada lista, para el resumen de la UI."""
        async with db_session() as session:
            filas = await session.execute(
                select(StandardValue.list_code, func.count(StandardValue.id))
                .where(
                    StandardValue.company_id == company_id,
                    StandardValue.is_active.is_(True),
                )
                .group_by(StandardValue.list_code)
            )
            return {codigo: total for codigo, total in filas.all()}
