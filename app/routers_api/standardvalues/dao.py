"""Acceso a datos de las listas configurables. Siempre acotado por compañía.

**Todo este módulo ignora los valores borrados.** `deleted_at IS NULL` no es un
filtro opcional que el llamador elija: un valor con lápida está fuera de la
experiencia normal por definición, así que no aparece ni entre los activos ni
entre los inactivos ni en los recuentos. La única forma de alcanzarlo es
`get_including_deleted`, que existe para resolver una referencia histórica y
para que el aprovisionamiento sepa que ya sembró ahí.
"""

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
        stmt = select(StandardValue).where(
            StandardValue.company_id == company_id,
            StandardValue.deleted_at.is_(None),
        )
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
                StandardValue.deleted_at.is_(None),
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
        """Un valor de la experiencia normal. Uno borrado responde 404.

        Es el mismo criterio que con otro tenant: no se confirma que exista algo
        que el administrador ya no puede ver.
        """
        async with db_session() as session:
            valor = await session.scalar(
                select(StandardValue).where(
                    StandardValue.id == value_id,
                    StandardValue.company_id == company_id,
                    StandardValue.deleted_at.is_(None),
                )
            )

        if valor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Standard value not found",
            )
        return valor

    @classmethod
    async def find_selectable(
        cls, *, value_id: int, company_id: int, list_code: str
    ) -> StandardValue | None:
        """El valor **elegible ahora** para esa lista, o `None`.

        Devuelve `None` por todas las razones a la vez —no existe, es de otro
        tenant, está borrado, está desactivado, o pertenece a otra lista— porque
        quien pregunta sólo necesita saber si puede ofrecerlo, y distinguir los
        casos daría información sobre filas que el llamante no puede ver.

        Lo desactivado tampoco cuenta
        ------------------------------
        Al escribirse en RTE04 sólo filtraba lápidas, porque la resolución de
        entonces hablaba de valores borrados. Pero desactivar **es** retirar del
        uso operativo —lo fijó así RTE02-A01— y un valor retirado que seguía
        pudiéndose elegir contradecía esa semántica: la pantalla dejaba de
        ofrecerlo y la API lo seguía aceptando. RTE05 lo pide explícitamente
        (FR-02) y lo corrige también para los datos de pre-viaje.

        No sirve para resolver una referencia histórica: un viaje que eligió un
        valor antes de que lo retiraran lo conserva, y eso se lee con
        `get_including_deleted`.
        """
        async with db_session() as session:
            return await session.scalar(
                select(StandardValue).where(
                    StandardValue.id == value_id,
                    StandardValue.company_id == company_id,
                    StandardValue.list_code == list_code,
                    StandardValue.deleted_at.is_(None),
                    StandardValue.is_active.is_(True),
                )
            )

    @classmethod
    async def get_including_deleted(
        cls, *, value_id: int, company_id: int
    ) -> StandardValue | None:
        """La fila aunque tenga lápida, para resolver una referencia histórica.

        No la usa ninguna pantalla de administración: si lo hiciera, el borrado
        se estaría filtrando de vuelta a la experiencia normal, que es
        exactamente lo que el addendum prohíbe.
        """
        async with db_session() as session:
            return await session.scalar(
                select(StandardValue).where(
                    StandardValue.id == value_id,
                    StandardValue.company_id == company_id,
                )
            )

    @classmethod
    async def seed_keys_present(cls, *, company_id: int) -> set[str]:
        """Las huellas de siembra que ya existen, **incluidas las borradas**.

        Deliberadamente ignora `deleted_at` e `is_active`: el aprovisionamiento
        pregunta "¿ya sembré esto alguna vez?", no "¿sigue vivo?". Si mirara
        sólo lo vivo, resucitaría en la siguiente ejecución todo lo que el
        administrador hubiera borrado.
        """
        async with db_session() as session:
            filas = await session.execute(
                select(StandardValue.seed_key).where(
                    StandardValue.company_id == company_id,
                    StandardValue.seed_key.is_not(None),
                )
            )
            return {clave for (clave,) in filas.all()}

    @classmethod
    async def next_sort_order(cls, *, company_id: int, list_code: str) -> int:
        """El siguiente hueco al final de la lista.

        Cuenta también los borrados: reutilizar el orden de una fila con lápida
        no rompe nada, pero dejar huecos es más barato que arriesgar un empate
        con una fila que sigue en la tabla.
        """
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
                    StandardValue.deleted_at.is_(None),
                )
                .group_by(StandardValue.list_code)
            )
            return {codigo: total for codigo, total in filas.all()}
