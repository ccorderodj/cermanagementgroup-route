"""
Reglas de las listas configurables.

La regla que gobierna todo este módulo: **nada se borra**. Un valor retirado
sigue existiendo porque un registro histórico guardó su identificador y tiene
que poder resolverlo años después. Lo único que cambia es si se ofrece o no en
los formularios.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import diff, record_event
from app.core.dao.concurrency import ensure_version
from app.core.db.session import transaction
from app.routers_api.standardvalues.dao import StandardValuesDAO
from app.routers_api.standardvalues.models import StandardValue, StandardValueList


#: Etiqueta legible de cada lista. El código es el contrato; esto es sólo cómo
#: se llama en pantalla, y por eso vive aquí y no en la base.
LIST_LABELS: dict[str, str] = {
    StandardValueList.CLIENT_VISIT_ACTIVITIES.value: "Client Visit Activities",
    StandardValueList.RECRUITING_ACTIVITIES.value: "Recruiting Activities",
    StandardValueList.EMPLOYEE_VISIT_REASONS.value: "Employee Visit Reasons",
    StandardValueList.DELIVERY_TYPES.value: "Delivery Types",
    StandardValueList.OFFICE_PURPOSES.value: "Office Purposes",
    StandardValueList.OTHER_ACTIVITIES.value: "Other Activities",
    StandardValueList.OUTCOMES.value: "Outcomes",
    StandardValueList.RECEIVED_BY.value: "Received By",
}

_CAMPOS_AUDITADOS = ("label", "sort_order", "is_active")


def _instantanea(valor: StandardValue) -> dict:
    return {campo: getattr(valor, campo) for campo in _CAMPOS_AUDITADOS}


class StandardValueService:
    @staticmethod
    async def create(
        *, company_id: int, actor_user_id: int, list_code: str, label: str,
        sort_order: int | None,
    ) -> StandardValue:
        orden = (
            sort_order
            if sort_order is not None
            else await StandardValuesDAO.next_sort_order(
                company_id=company_id, list_code=list_code
            )
        )

        async with transaction() as session:
            valor = StandardValue(
                company_id=company_id,
                list_code=list_code,
                label=label,
                sort_order=orden,
            )
            session.add(valor)
            try:
                await session.flush()
            except IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"'{label}' already exists in "
                        f"{LIST_LABELS.get(list_code, list_code)}."
                    ),
                ) from exc
            value_id = valor.id
            instantanea = _instantanea(valor)

        await record_event(
            company_id=company_id,
            entity_type="standard_value",
            entity_id=value_id,
            action="create",
            actor_user_id=actor_user_id,
            summary=f"Standard value '{label}' added to {list_code}",
            changes={c: {"old": None, "new": v} for c, v in instantanea.items()},
        )
        return await StandardValuesDAO.get_for_company(
            value_id=value_id, company_id=company_id
        )

    @staticmethod
    async def update(
        *,
        company_id: int,
        value_id: int,
        actor_user_id: int,
        values: dict,
        expected_version: int | None,
    ) -> StandardValue:
        cambios = {k: v for k, v in values.items() if v is not None}

        async with transaction() as session:
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

            ensure_version(current=valor.version, expected=expected_version)

            antes = _instantanea(valor)
            for campo, dato in cambios.items():
                setattr(valor, campo, dato)
            valor.version = valor.version + 1

            try:
                await session.flush()
            except IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another value in this list already uses that label.",
                ) from exc

            despues = _instantanea(valor)
            codigo, etiqueta = valor.list_code, valor.label

        delta = diff(antes, despues)
        if delta:
            await record_event(
                company_id=company_id,
                entity_type="standard_value",
                entity_id=value_id,
                action="update",
                actor_user_id=actor_user_id,
                summary=f"Standard value '{etiqueta}' updated in {codigo}",
                changes=delta,
            )

        return await StandardValuesDAO.get_for_company(
            value_id=value_id, company_id=company_id
        )

    @staticmethod
    async def reorder(
        *,
        company_id: int,
        list_code: str,
        actor_user_id: int,
        value_ids: list[int],
    ) -> list[StandardValue]:
        """Reordena la lista completa según el orden recibido.

        Se exige el conjunto **exacto** de la lista: aceptar un subconjunto
        dejaría los que faltan con un orden arbitrario respecto de los demás, y
        el resultado dependería de con qué fila se tropezara la consulta
        primero.
        """
        async with transaction() as session:
            filas = (
                (
                    await session.execute(
                        select(StandardValue).where(
                            StandardValue.company_id == company_id,
                            StandardValue.list_code == list_code,
                        )
                    )
                )
                .scalars()
                .all()
            )

            existentes = {fila.id for fila in filas}
            recibidos = set(value_ids)

            if len(value_ids) != len(recibidos):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="The order contains repeated values.",
                )
            if recibidos != existentes:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "The order must contain exactly the values of this list."
                    ),
                )

            por_id = {fila.id: fila for fila in filas}
            for posicion, value_id in enumerate(value_ids, start=1):
                fila = por_id[value_id]
                if fila.sort_order != posicion:
                    fila.sort_order = posicion
                    fila.version = fila.version + 1
            await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="standard_value_list",
            # La entidad reordenada es la lista, no un valor suelto. El id de
            # entidad no aplica, así que se usa 0 y el código va en el resumen.
            entity_id=0,
            action="reorder",
            actor_user_id=actor_user_id,
            summary=f"Standard value list {list_code} reordered",
            changes={"order": {"old": None, "new": value_ids}},
        )

        return await StandardValuesDAO.list_for_code(
            company_id=company_id, list_code=list_code, include_inactive=True
        )
