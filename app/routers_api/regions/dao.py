from fastapi import HTTPException, status
from sqlalchemy import Select, and_, false, func, select, update

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session, transaction
from app.routers_api.companies.models import CompanyState
from app.routers_api.regions.models import Region


class RegionsDAO(BaseDAO):
    model = Region

    @classmethod
    def query(cls, *, company_id: int, name: str | None = None, **_: object) -> Select:
        """Estados en los que opera esta compañía.

        El join con `company_state` no es un detalle de implementación: es lo
        que hace que este catálogo global se vea acotado al tenant.
        """
        stmt = (
            select(Region)
            .join(CompanyState, CompanyState.state_id == Region.id)
            .where(
                CompanyState.company_id == company_id,
                CompanyState.is_active.is_(True),
                Region.is_active.is_(True),
            )
            .distinct()
        )
        if name:
            stmt = stmt.where(Region.name.ilike(f"%{name}%"))
        return stmt

    @classmethod
    def default_order(cls):
        return Region.name.asc()

    @classmethod
    async def find_all_by_company(cls, *, company_id: int) -> list[Region]:
        async with db_session() as session:
            result = await session.execute(
                cls.query(company_id=company_id).order_by(Region.name.asc())
            )
            return list(result.scalars().unique().all())

    @classmethod
    async def find_operating_states(cls, *, company_id: int) -> list[dict]:
        """Estados donde opera la compañía, con la sede principal primero.

        Devuelve el estado ya combinado con su marca de sede principal: la
        pantalla no tiene que cruzar `region` con `company_state`.
        """
        async with db_session() as session:
            result = await session.execute(
                select(
                    Region.id.label("id"),
                    Region.code.label("code"),
                    Region.name.label("name"),
                    CompanyState.is_main.label("is_main"),
                    CompanyState.is_active.label("is_active"),
                    CompanyState.created_at.label("created_at"),
                    CompanyState.updated_at.label("updated_at"),
                )
                .join(CompanyState, CompanyState.state_id == Region.id)
                .where(
                    CompanyState.company_id == company_id,
                    CompanyState.is_active.is_(True),
                    Region.is_active.is_(True),
                )
                .order_by(CompanyState.is_main.desc(), Region.name)
            )
            return [dict(row) for row in result.mappings().all()]

    @classmethod
    async def find_catalog_by_company(cls, *, company_id: int) -> list[dict]:
        """Catálogo completo de estados, marcando cuáles opera la compañía."""
        async with db_session() as session:
            result = await session.execute(
                select(
                    Region.id.label("id"),
                    Region.code.label("code"),
                    Region.name.label("name"),
                    func.coalesce(CompanyState.is_active, false()).label("enabled"),
                )
                .select_from(Region)
                .outerjoin(
                    CompanyState,
                    and_(
                        CompanyState.state_id == Region.id,
                        CompanyState.company_id == company_id,
                    ),
                )
                .where(Region.is_active.is_(True))
                .order_by(Region.name.asc())
            )
            return [dict(row) for row in result.mappings().all()]

    @classmethod
    async def sync_operating_states(cls, *, company_id: int, state_ids: list[int]) -> None:
        """Reemplaza el conjunto de estados donde opera la compañía.

        Todo en una transacción: dejar la mitad aplicada describiría una
        operación geográfica que nadie pidió.
        """
        selected_ids = list(dict.fromkeys(state_ids or []))

        async with transaction() as session:
            if selected_ids:
                valid = set(
                    (
                        await session.execute(
                            select(Region.id).where(
                                Region.id.in_(selected_ids),
                                Region.is_active.is_(True),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                invalid = [sid for sid in selected_ids if sid not in valid]
                if invalid:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid state ids: {invalid}",
                    )

            existing = list(
                (
                    await session.execute(
                        select(CompanyState).where(CompanyState.company_id == company_id)
                    )
                )
                .scalars()
                .all()
            )
            by_state_id = {row.state_id: row for row in existing}
            selected = set(selected_ids)

            # Primero se desactiva lo que sale. Hacerlo antes de activar lo que
            # entra evita chocar con el índice único parcial de la sede
            # principal si la sede cambia de estado en la misma operación.
            for row in existing:
                if row.state_id not in selected:
                    row.is_active = False
                    row.is_main = False
                    session.add(row)
            await session.flush()

            for state_id in selected:
                current = by_state_id.get(state_id)
                if current:
                    current.is_active = True
                    session.add(current)
                else:
                    session.add(
                        CompanyState(
                            company_id=company_id,
                            state_id=state_id,
                            is_active=True,
                        )
                    )

    @classmethod
    async def set_main_state(cls, *, company_id: int, state_id: int) -> None:
        """Marca `state_id` como sede principal; el resto deja de serlo.

        Se limpia primero y se marca después, en la misma transacción: el índice
        único parcial `uq_company_state_single_main` rechaza dos sedes
        principales activas, así que el orden importa.
        """
        async with transaction() as session:
            target = await session.scalar(
                select(CompanyState).where(
                    CompanyState.company_id == company_id,
                    CompanyState.state_id == state_id,
                    CompanyState.is_active.is_(True),
                )
            )
            if target is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The state must be an active operating state",
                )

            await session.execute(
                update(CompanyState)
                .where(
                    CompanyState.company_id == company_id,
                    CompanyState.is_main.is_(True),
                )
                .values(is_main=False)
            )
            await session.flush()

            await session.execute(
                update(CompanyState)
                .where(CompanyState.id == target.id)
                .values(is_main=True)
            )
