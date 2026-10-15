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
from app.routers_api.organization.models import (
    CARGO_DE_ROL,
    PADRES_PERMITIDOS,
    OrgAssignment,
    OrgPosition,
)
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
    #: V1.5: a quién sustituyó con esta fila («Replace manager»).
    replaces_user_id: int | None = None


def _fila(a: OrgAssignment) -> Asignacion:
    return Asignacion(
        user_id=a.user_id,
        position=a.position,
        superior_user_id=a.superior_user_id,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        version=a.version,
        replaces_user_id=a.replaces_user_id,
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


@dataclass(frozen=True)
class Pertenencia:
    rol: str
    activa: bool


async def pertenencias(company_id: int) -> dict[int, Pertenencia]:
    """Rol y estado de cada pertenencia **no retirada** de la compañía."""
    async with db_session() as session:
        filas = (
            await session.execute(
                select(UserCompany.user_id, Role.name, UserCompany.is_active)
                .join(Role, Role.id == UserCompany.role_id)
                .where(
                    UserCompany.company_id == company_id,
                    UserCompany.deleted_at.is_(None),
                )
            )
        ).all()
    return {f.user_id: Pertenencia(rol=f.name, activa=bool(f.is_active)) for f in filas}


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

        # El cargo **sale del rol** (V1.3): no puede contradecirlo. Sólo el
        # `route_manager` heredado conserva un cargo de mando a elegir; fuera de
        # eso —Superadmin, roles del núcleo— no hay cargo: están fuera del árbol.
        rol = await _rol(session, company_id=company_id, user_id=user_id)
        esperado = CARGO_DE_ROL.get(rol)
        if esperado is not None and esperado != position:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "The position must match the person's CER Route role.",
            )
        if esperado is None and not (
            rol == "route_manager"
            and position in (OrgPosition.CEO, OrgPosition.COO, OrgPosition.REGIONAL_MANAGER)
        ):
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "This role has no place in the CER Route hierarchy.",
            )

        permitidos = PADRES_PERMITIDOS[position]
        if superior_user_id is None and permitidos:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "This role needs a superior: choose the person they report to.",
            )
        if superior_user_id is not None:
            jefe = actuales.get(superior_user_id)
            if jefe is None or not await _miembro(
                session, company_id=company_id, user_id=superior_user_id, activo=True
            ):
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "The superior must be an active member with a position in this company.",
                )
            if jefe.position not in permitidos:
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "That person cannot be the superior for this role.",
                )
            if superior_user_id in descendientes(actuales, user_id):
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "That superior reports to this person: it would create a cycle.",
                )

        # Un único CEO vigente por compañía (V1.4). El índice de la 0019 lo
        # garantiza igualmente; esto da un 409 con algo que hacer en vez de un
        # error de integridad.
        if position == OrgPosition.CEO and any(
            a.position == OrgPosition.CEO and u != user_id for u, a in actuales.items()
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "This company already has a CEO. To change it, use "
                "“Replace manager” in CER Route → Users.",
            )

        # Quien tiene subordinados no puede pasar a un cargo del que ellos no
        # puedan depender (p. ej. un CEO con Sales directo que pasa a COO).
        directos = [a for a in actuales.values() if a.superior_user_id == user_id]
        if any(position not in PADRES_PERMITIDOS[a.position] for a in directos):
            raise _error(
                status.HTTP_409_CONFLICT,
                "This person has direct reports who cannot report to that role. "
                "Reassign them first.",
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


async def _rol(session, *, company_id: int, user_id: int) -> str | None:
    """El rol de la persona dentro de la transacción en curso (suspendida
    incluida; retirada, no)."""
    return await session.scalar(
        select(Role.name)
        .join(UserCompany, UserCompany.role_id == Role.id)
        .where(
            UserCompany.user_id == user_id,
            UserCompany.company_id == company_id,
            UserCompany.deleted_at.is_(None),
        )
    )


async def sincronizar_con_rol(
    *,
    company_id: int,
    actor_user_id: int | None,
    user_id: int,
    superior_user_id: int | None,
    superior_dado: bool,
    reason: str | None = None,
) -> None:
    """Deja el cargo de la persona coherente con su rol **actual**.

    Se llama dentro de la misma transacción que cambia el rol o el superior:
    si el conjunto —rol nuevo, superior nuevo, rama resultante— no es válido,
    se deshace todo, también el cambio de rol (V1.3, FR-03).

    * Rol con cargo (CEO … Sales): asigna ese cargo con el superior dado o, si
      no se dio, con el que tenía. Si el cargo exige superior y no lo hay, 422.
    * Rol sin cargo (Superadmin, núcleo): cierra el cargo que tuviera.
    * `route_manager` heredado: no se toca; su cargo se cambia expresamente.
    """
    async with transaction() as session:
        rol = await _rol(session, company_id=company_id, user_id=user_id)
    cargo = CARGO_DE_ROL.get(rol)
    if cargo is not None:
        previa = (await vigentes(company_id)).get(user_id)
        jefe = superior_user_id if superior_dado else (previa.superior_user_id if previa else None)
        if not PADRES_PERMITIDOS[cargo]:
            # El CEO es raíz: pasar a CEO deja a la persona sin superior.
            jefe = None
        await asignar(
            company_id=company_id,
            actor_user_id=actor_user_id,
            user_id=user_id,
            position=cargo,
            superior_user_id=jefe,
            reason=reason,
        )
    elif rol != "route_manager":
        await retirar(
            company_id=company_id,
            actor_user_id=None,
            user_id=user_id,
            sin_error_si_no_hay=True,
            reason=reason or "role without a CER Route position",
        )


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
