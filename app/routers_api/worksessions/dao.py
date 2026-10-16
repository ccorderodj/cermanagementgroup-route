"""Acceso a datos de la Jornada. Todo acotado por compañía y por supervisor."""

from __future__ import annotations

from sqlalchemy import Select, select

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.worksessions.models import WorkSession, WorkSessionStatus


class WorkSessionsDAO(BaseDAO):
    model = WorkSession

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        user_id: int | None = None,
        status: str | None = None,
        **_: object,
    ) -> Select:
        stmt = select(WorkSession).where(WorkSession.company_id == company_id)
        if user_id is not None:
            stmt = stmt.where(WorkSession.user_id == user_id)
        if status:
            stmt = stmt.where(WorkSession.status == status)
        return stmt

    @classmethod
    def default_order(cls):
        return WorkSession.started_at.desc()

    @classmethod
    async def find_active_for_user(
        cls, *, company_id: int, user_id: int
    ) -> WorkSession | None:
        """La jornada vigente del supervisor, si la hay.

        Es **la** fuente de "¿está trabajando ahora?" — no hay una copia de
        ese booleano en ninguna otra tabla que pueda decir otra cosa.
        """
        async with db_session() as session:
            return await session.scalar(
                select(WorkSession).where(
                    WorkSession.company_id == company_id,
                    WorkSession.user_id == user_id,
                    WorkSession.status == WorkSessionStatus.ACTIVE.value,
                )
            )

    @classmethod
    async def get_for_company_and_owner(
        cls, *, session_id: int, company_id: int, user_id: int
    ) -> WorkSession | None:
        """La jornada, solo si es de esta compañía **y** de este supervisor.

        Sin excepción: quien llama decide 404 vs devolver la fila. Una jornada
        de otro supervisor del mismo tenant no debe ni confirmarse que existe
        (mismo principio que el aislamiento entre tenants, aplicado aquí a la
        propiedad dentro de un tenant).
        """
        async with db_session() as session:
            return await session.scalar(
                select(WorkSession).where(
                    WorkSession.id == session_id,
                    WorkSession.company_id == company_id,
                    WorkSession.user_id == user_id,
                )
            )
