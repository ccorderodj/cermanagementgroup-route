"""
Escribir y leer la estructura organizacional, con sus invariantes.

Todas las escrituras van dentro de `transaction()` y toman antes un **candado
por compañía** (`pg_advisory_xact_lock`). Las reglas que dependen de otras filas
—nivel estrictamente superior, sin ciclos, sin dejar subordinados colgando— se
validan sobre una lectura que nadie puede cambiar mientras tanto: dos
reasignaciones simultáneas que juntas formarían un ciclo se ejecutan una detrás
de otra, y la segunda lo ve.

Las fechas salen del reloj de la base (`now()`, el instante de la transacción),
nunca del cliente.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, text, update

from app.core.audit.service import record_event
from app.core.dao.concurrency import ensure_version
from app.core.db.session import db_session, transaction
from app.routers_api.companies.models import UserCompany
from app.routers_api.organization.models import NIVEL, OrgAssignment, OrgPosition
from app.routers_api.roles.models import Role
from app.routers_api.users.models import Users

#: Espacio de claves del candado consultivo de la jerarquía. Con el id de la
#: compañía forma la clave: sólo se serializan las escrituras del mismo tenant.
_CANDADO = 7301


@dataclass(frozen=True)
class Asignacion:
    user_id: int
    position: str
    superior_user_id: int | None
    valid_from: datetime
    valid_to: datetime | None
    version: int


def _fila(a: OrgAssignment) -> Asignacion:
    return Asignacion(
        user_id=a.user_id,
        position=a.position,
        superior_user_id=a.superior_user_id,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        version=a.version,
    )


# ── Lecturas ────────────────────────────────────────────────────────────────


async def vigentes(company_id: int) -> dict[int, Asignacion]:
    """Las asignaciones abiertas de la compañía, por persona."""
    async with db_session() as session:
        filas = (
            await session.execute(
                select(OrgAssignment).where(
                    OrgAssignment.company_id == company_id,
                    OrgAssignment.valid_to.is_(None),
                )
            )
        ).scalars().all()
    return {f.user_id: _fila(f) for f in filas}


async def historial(company_id: int) -> list[Asignacion]:
    """Todas las asignaciones de la compañía, abiertas y cerradas."""
    async with db_session() as session:
        filas = (
            await session.execute(
                select(OrgAssignment)
                .where(OrgAssignment.company_id == company_id)
                .order_by(OrgAssignment.valid_from, OrgAssignment.id)
            )
        ).scalars().all()
    return [_fila(f) for f in filas]


def descendientes(asignaciones: dict[int, Asignacion], raiz: int) -> set[int]:
    """Quienes cuelgan de `raiz`, a cualquier profundidad, sin incluirla."""
    hijos: dict[int, list[int]] = defaultdict(list)
    for a in asignaciones.values():
        if a.superior_user_id is not None:
            hijos[a.superior_user_id].append(a.user_id)
    vistos: set[int] = set()
    pendientes = list(hijos.get(raiz, []))
    while pendientes:
        u = pendientes.pop()
        if u in vistos or u == raiz:
            continue
        vistos.add(u)
        pendientes.extend(hijos.get(u, []))
    return vistos


async def rol_en_compania(
    *, company_id: int, user_id: int, incluir_suspendidos: bool = False
) -> str | None:
    """El rol de la persona en esta compañía.

    Por defecto sólo con la pertenencia **activa** (el actor). Con
    `incluir_suspendidos`, también suspendida: alguien suspendido sigue en su
    rama —su superior tiene que poder devolverle el acceso—; alguien retirado
    (`deleted_at`) ya no.
    """
    condiciones = [
        UserCompany.user_id == user_id,
        UserCompany.company_id == company_id,
        UserCompany.deleted_at.is_(None),
    ]
    if not incluir_suspendidos:
        condiciones.append(UserCompany.is_active.is_(True))
    async with db_session() as session:
        return await session.scalar(
            select(Role.name)
            .join(UserCompany, UserCompany.role_id == Role.id)
            .where(*condiciones)
        )


async def nombres(company_id: int, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    async with db_session() as session:
        filas = (
            await session.execute(
                select(Users.id, Users.first_name, Users.last_name)
                .join(UserCompany, UserCompany.user_id == Users.id)
                .where(UserCompany.company_id == company_id, Users.id.in_(user_ids))
            )
        ).all()
    return {f.id: f"{f.first_name} {f.last_name}".strip() for f in filas}


# ── Escrituras ──────────────────────────────────────────────────────────────


def _error(codigo: int, detalle: str) -> HTTPException:
    return HTTPException(status_code=codigo, detail=detalle)


async def _miembro(session, *, company_id: int, user_id: int, activo: bool) -> bool:
    """Pertenece a la compañía y no fue retirado; con `activo`, además activa."""
    condiciones = [
        UserCompany.company_id == company_id,
        UserCompany.user_id == user_id,
        UserCompany.deleted_at.is_(None),
    ]
    if activo:
        condiciones.append(UserCompany.is_active.is_(True))
    return bool(
        await session.scalar(
            select(func.count()).select_from(UserCompany).where(*condiciones)
        )
    )


async def asignar(
    *,
    company_id: int,
    actor_user_id: int | None,
    user_id: int,
    position: str,
    superior_user_id: int | None,
    expected_version: int | None = None,
    reason: str | None = None,
) -> Asignacion:
    """Fija el cargo y el superior **vigentes** de una persona.

    Cierra la asignación abierta —si la hay— en el instante de la transacción y
    abre la nueva desde ese mismo instante: periodos contiguos, sin solape y sin
    hueco. Si no cambia nada, no escribe nada.

    Quién puede pedirlo y sobre quién lo decide la delegación
    (`organization.delegation`) **antes** de llamar aquí; esto valida la
    estructura, sea quien sea el actor.
    """
    if position not in OrgPosition.values():
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown position.")
    if actor_user_id is not None and actor_user_id == user_id:
        raise _error(status.HTTP_403_FORBIDDEN, "You cannot change your own position.")
    if superior_user_id is not None and superior_user_id == user_id:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "A person cannot report to themselves.")

    async with transaction() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k, :c)"), {"k": _CANDADO, "c": company_id}
        )
        # La persona puede estar suspendida (sigue en su rama); retirada, no.
        if not await _miembro(session, company_id=company_id, user_id=user_id, activo=False):
            raise _error(status.HTTP_404_NOT_FOUND, "User not found for this company")

        actuales = {
            f.user_id: _fila(f)
            for f in (
                await session.execute(
                    select(OrgAssignment).where(
                        OrgAssignment.company_id == company_id,
                        OrgAssignment.valid_to.is_(None),
                    )
                )
            ).scalars().all()
        }
        previa = actuales.get(user_id)
        if expected_version is not None:
            ensure_version(current=previa.version if previa else 0, expected=expected_version)

        nivel = NIVEL[position]
        if superior_user_id is not None:
            jefe = actuales.get(superior_user_id)
            if jefe is None or not await _miembro(
                session, company_id=company_id, user_id=superior_user_id, activo=True
            ):
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "The superior must be an active member with a position in this company.",
                )
            if NIVEL[jefe.position] <= nivel:
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "The superior must hold a strictly higher position.",
                )
            if superior_user_id in descendientes(actuales, user_id):
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "That superior reports to this person: it would create a cycle.",
                )

        # Quien tiene subordinados no puede bajar a su nivel o por debajo:
        # dejaría una relación con el superior igual o inferior.
        directos = [a for a in actuales.values() if a.superior_user_id == user_id]
        if directos and nivel <= max(NIVEL[a.position] for a in directos):
            raise _error(
                status.HTTP_409_CONFLICT,
                "This person has direct reports at that level or above. Reassign them first.",
            )

        if (
            previa is not None
            and previa.position == position
            and previa.superior_user_id == superior_user_id
        ):
            return previa

        ahora = await session.scalar(select(func.now()))
        if previa is not None:
            await session.execute(
                update(OrgAssignment)
                .where(
                    OrgAssignment.company_id == company_id,
                    OrgAssignment.user_id == user_id,
                    OrgAssignment.valid_to.is_(None),
                )
                .values(valid_to=ahora)
            )
        nueva = OrgAssignment(
            company_id=company_id,
            user_id=user_id,
            position=position,
            superior_user_id=superior_user_id,
            valid_from=ahora,
            created_by=actor_user_id,
            reason=reason,
            version=(previa.version + 1) if previa else 1,
        )
        session.add(nueva)
        await session.flush()

        await record_event(
            company_id=company_id,
            entity_type="org_assignment",
            entity_id=user_id,
            action="reassign" if previa else "assign",
            actor_user_id=actor_user_id,
            summary=f"Position {position} assigned to user {user_id}",
            changes={
                "position": {"old": previa.position if previa else None, "new": position},
                "superior_user_id": {
                    "old": previa.superior_user_id if previa else None,
                    "new": superior_user_id,
                },
            },
            reason=reason,
        )
        return _fila(nueva)


async def retirar(
    *,
    company_id: int,
    actor_user_id: int | None,
    user_id: int,
    expected_version: int | None = None,
    reason: str | None = None,
    sin_error_si_no_hay: bool = False,
) -> None:
    """Cierra la asignación vigente. Con subordinados directos, 409."""
    if actor_user_id is not None and actor_user_id == user_id and not sin_error_si_no_hay:
        raise _error(status.HTTP_403_FORBIDDEN, "You cannot change your own position.")

    async with transaction() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k, :c)"), {"k": _CANDADO, "c": company_id}
        )
        previa = (
            await session.execute(
                select(OrgAssignment).where(
                    OrgAssignment.company_id == company_id,
                    OrgAssignment.user_id == user_id,
                    OrgAssignment.valid_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if previa is None:
            if sin_error_si_no_hay:
                return
            raise _error(status.HTTP_404_NOT_FOUND, "This person has no position.")
        if expected_version is not None:
            ensure_version(current=previa.version, expected=expected_version)

        directos = await session.scalar(
            select(func.count())
            .select_from(OrgAssignment)
            .where(
                OrgAssignment.company_id == company_id,
                OrgAssignment.superior_user_id == user_id,
                OrgAssignment.valid_to.is_(None),
            )
        )
        if directos:
            raise _error(
                status.HTTP_409_CONFLICT,
                "This person has direct reports. Reassign them first.",
            )

        previa.valid_to = await session.scalar(select(func.now()))
        await session.flush()
        await record_event(
            company_id=company_id,
            entity_type="org_assignment",
            entity_id=user_id,
            action="unassign",
            actor_user_id=actor_user_id,
            summary=f"Position removed from user {user_id}",
            changes={
                "position": {"old": previa.position, "new": None},
                "superior_user_id": {"old": previa.superior_user_id, "new": None},
            },
            reason=reason,
        )
