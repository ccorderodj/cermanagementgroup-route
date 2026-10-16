"""
Continuidad de la jerarquía ante cambios de personal (V1.4, FR-03 y FR-04).

Dos operaciones sobre un responsable, distintas a propósito
-----------------------------------------------------------
* **Retirar** (salida definitiva **sin** sucesor): sus subordinados **directos**
  pasan a su superior inmediato; los indirectos no se tocan, siguen bajo quien
  ya estaban. Un CEO con equipo **no** se retira así: no hay a quién subir a
  nadie, y un COO no hereda la raíz (decisión del PO).
* **Sustituir** (sucesor identificado): el sucesor ocupa el cargo del saliente
  bajo su mismo superior y recibe a todos sus directos. En un CEO, también a
  Sales: Sales sólo depende de un CEO.

Quien sale deja la compañía con la baja que ya existe (retirar la
pertenencia), salvo en una sustitución en la que se elija **bajarlo de rango**
(V1.6): entonces se queda con el cargo inferior y el superior que se indiquen,
validados como cualquier asignación, y su equipo pasa entero al sucesor. No se
le inventa nada que no se haya elegido. **Suspender** es otra cosa —ausencia
temporal— y no pasa por aquí: conserva la estructura intacta.

Cómo se garantiza que no queda nada a medias
--------------------------------------------
Las dos se resuelven igual. Se calcula en memoria la **estructura final** y se
valida **entera**:

* cada relación nueva, contra `PADRES_PERMITIDOS`;
* superiores activos;
* sin ciclos;
* un único CEO.

Sólo entonces se escribe, dentro de una transacción, con el candado de la
jerarquía y con **un único instante T** para todo: se cierran las filas
afectadas en T y se abren las nuevas desde T. Si algo falla, no se escribe
nada.

La vista previa es **el mismo cálculo** sin escribir. Lo que se enseña antes de
confirmar es exactamente lo que se ejecuta.

Quién puede
-----------
Sólo el Administrador de CER Route (`route_admin`) del tenant: mínimo
privilegio. Ni `owner`/`admin` del núcleo por serlo, ni los mandos de la
jerarquía, hasta que CER lo decida (V1.4, §2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import func, insert, select, text, update

from app.core.audit.service import record_event
from app.core.dao.concurrency import ensure_version
from app.core.db.session import transaction
from app.routers_api.companies.models import UserCompany
from app.routers_api.organization import service
from app.routers_api.organization.models import (
    CARGO_DE_ROL,
    ETIQUETA,
    NIVEL,
    PADRES_PERMITIDOS,
    ROL_DE_CARGO,
    OrgAssignment,
    OrgPosition,
)
from app.routers_api.roles.models import Role

#: Cargos que se pueden sustituir.
SUSTITUIBLES = frozenset({OrgPosition.CEO, OrgPosition.COO, OrgPosition.REGIONAL_MANAGER})

#: Roles desde los que se puede ser sucesor: los de la jerarquía y el heredado.
#: Nunca `route_admin` ni un rol del núcleo, que están fuera del árbol.
ROLES_SUCESORES = frozenset(CARGO_DE_ROL) | {"route_manager"}

#: El único rol que administra la continuidad (V1.4, §2).
ROL_AUTORIZADO = "route_admin"


@dataclass(frozen=True)
class Movimiento:
    user_id: int
    position: str
    superior_antes: int | None
    superior_despues: int | None


@dataclass
class Plan:
    operacion: str
    saliente: int
    cargo: str
    superior_saliente: int | None
    version: int
    directos: list[int]
    sucesor: int | None = None
    sucesor_antes: tuple[str, int | None] | None = None
    movimientos: list[Movimiento] = field(default_factory=list)
    #: Estado final de cada persona tocada: `(cargo, superior)` o `None` si su
    #: cargo se cierra.
    final: dict[int, tuple[str, int | None] | None] = field(default_factory=dict)
    #: V1.6: si quien sale se queda en la compañía con un cargo inferior,
    #: `(cargo, superior)`. `None`: deja la compañía.
    degradado: tuple[str, int | None] | None = None


def _conflicto(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)


def _directos(actuales: dict[int, service.Asignacion], jefe: int) -> list[int]:
    return sorted(u for u, a in actuales.items() if a.superior_user_id == jefe)


def _validar_final(
    actuales: dict[int, service.Asignacion],
    final: dict[int, tuple[str, int | None] | None],
    miembros: dict[int, service.Pertenencia],
    nombres: dict[int, str],
) -> None:
    """La estructura resultante, entera. Cualquier fallo: nada se escribe."""
    estructura: dict[int, tuple[str, int | None]] = {
        u: (a.position, a.superior_user_id) for u, a in actuales.items()
    }
    for u, valor in final.items():
        if valor is None:
            estructura.pop(u, None)
        else:
            estructura[u] = valor

    for u, valor in final.items():
        if valor is None:
            continue
        cargo, jefe = valor
        permitidos = PADRES_PERMITIDOS[cargo]
        if jefe is None:
            if permitidos:
                raise _conflicto(f"{nombres.get(u, u)} would be left without a superior.")
            continue
        if jefe not in estructura:
            raise _conflicto(f"The new superior of {nombres.get(u, u)} has no position.")
        if not (miembros.get(jefe) and miembros[jefe].activa):
            raise _conflicto(
                f"{nombres.get(jefe, jefe)} is suspended and cannot receive "
                "reports. Restore their access first."
            )
        if estructura[jefe][0] not in permitidos:
            raise _conflicto(
                f"{nombres.get(u, u)} ({ETIQUETA[cargo]}) cannot report to a "
                f"{ETIQUETA[estructura[jefe][0]]}."
            )

    # Quien cambia de cargo no puede quedarse con directos que no caben debajo.
    for u, valor in final.items():
        if valor is None:
            continue
        for hijo, (cargo_hijo, jefe_hijo) in estructura.items():
            if jefe_hijo == u and valor[0] not in PADRES_PERMITIDOS[cargo_hijo]:
                raise _conflicto(
                    f"{nombres.get(hijo, hijo)} ({ETIQUETA[cargo_hijo]}) cannot report "
                    f"to a {ETIQUETA[valor[0]]}. Reassign them first."
                )

    if sum(1 for cargo, _ in estructura.values() if cargo == OrgPosition.CEO) > 1:
        raise _conflicto("The company would have two CEOs.")

    for inicio in final:
        visto: set[int] = set()
        actual: int | None = inicio
        while actual is not None and actual in estructura:
            if actual in visto:
                raise _conflicto("This change would create a cycle in the hierarchy.")
            visto.add(actual)
            actual = estructura[actual][1]


def planificar_retiro(
    *,
    actuales: dict[int, service.Asignacion],
    miembros: dict[int, service.Pertenencia],
    nombres: dict[int, str],
    saliente: int,
) -> Plan:
    previa = actuales.get(saliente)
    if previa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This person has no position.")
    directos = _directos(actuales, saliente)
    if previa.position == OrgPosition.CEO and directos:
        raise _conflicto(
            "A CEO with a team cannot leave without a successor. Use “Replace manager”."
        )
    destino = previa.superior_user_id
    plan = Plan(
        operacion="retire",
        saliente=saliente,
        cargo=previa.position,
        superior_saliente=destino,
        version=previa.version,
        directos=directos,
    )
    plan.final[saliente] = None
    for d in directos:
        a = actuales[d]
        plan.final[d] = (a.position, destino)
        plan.movimientos.append(Movimiento(d, a.position, saliente, destino))
    _validar_final(actuales, plan.final, miembros, nombres)
    return plan


def planificar_sustitucion(
    *,
    actuales: dict[int, service.Asignacion],
    miembros: dict[int, service.Pertenencia],
    nombres: dict[int, str],
    saliente: int,
    sucesor: int,
    degradar: tuple[str, int | None] | None = None,
) -> Plan:
    previa = actuales.get(saliente)
    if previa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This person has no position.")
    if previa.position not in SUSTITUIBLES:
        raise _conflicto("Only a CEO, a COO or a Regional Manager can be replaced.")
    if sucesor == saliente:
        raise _conflicto("Choose someone else as the successor.")
    pertenencia = miembros.get(sucesor)
    if pertenencia is None:
        # Otro tenant, retirado o inexistente: lo mismo, sin confirmar nada.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this company")
    if not pertenencia.activa:
        raise _conflicto("The successor's access is suspended.")
    if pertenencia.rol not in ROLES_SUCESORES:
        raise _conflicto(
            "The successor must be a CER Route user (CEO, COO, Regional Manager, "
            "OSM, Supervisor or Sales)."
        )
    if saliente in service.descendientes(actuales, sucesor):
        raise _conflicto("The successor is above this person in the hierarchy.")

    directos = _directos(actuales, saliente)
    antes = actuales.get(sucesor)
    plan = Plan(
        operacion="replace",
        saliente=saliente,
        cargo=previa.position,
        superior_saliente=previa.superior_user_id,
        version=previa.version,
        directos=directos,
        sucesor=sucesor,
        sucesor_antes=(antes.position, antes.superior_user_id) if antes else None,
    )
    plan.final[saliente] = None
    if degradar is not None:
        # Baja de rango (V1.6): quien sale se queda, siempre por debajo de lo
        # que era; su equipo pasa entero al sucesor.
        if NIVEL[degradar[0]] >= NIVEL[previa.position]:
            raise _conflicto("The outgoing person can only stay with a lower position.")
        plan.final[saliente] = degradar
        plan.degradado = degradar
    plan.final[sucesor] = (previa.position, previa.superior_user_id)
    for d in directos:
        if d == sucesor:
            continue
        a = actuales[d]
        plan.final[d] = (a.position, sucesor)
        plan.movimientos.append(Movimiento(d, a.position, saliente, sucesor))
    _validar_final(actuales, plan.final, miembros, nombres)
    return plan


async def _estado(company_id: int) -> tuple[dict, dict, dict]:
    actuales = await service.vigentes(company_id)
    miembros = await service.pertenencias(company_id)
    gente = await service.nombres(company_id, set(actuales) | set(miembros))
    return actuales, miembros, gente


async def calcular(
    *,
    company_id: int,
    operacion: str,
    saliente: int,
    sucesor: int | None = None,
    degradar: tuple[str, int | None] | None = None,
) -> tuple[Plan, dict[int, str]]:
    """La vista previa: el plan, sin escribir nada."""
    actuales, miembros, gente = await _estado(company_id)
    if operacion == "retire":
        plan = planificar_retiro(actuales=actuales, miembros=miembros, nombres=gente, saliente=saliente)
    else:
        if sucesor is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose the successor."
            )
        plan = planificar_sustitucion(
            actuales=actuales,
            miembros=miembros,
            nombres=gente,
            saliente=saliente,
            sucesor=sucesor,
            degradar=degradar,
        )
    return plan, gente


async def candidatos_a_sucesor(*, company_id: int, saliente: int) -> list[int]:
    """Quienes podrían sustituir a esta persona **sin** que nada falle."""
    actuales, miembros, gente = await _estado(company_id)
    validos = []
    for u in sorted(miembros):
        try:
            planificar_sustitucion(
                actuales=actuales, miembros=miembros, nombres=gente, saliente=saliente, sucesor=u
            )
        except HTTPException:
            continue
        validos.append(u)
    return validos


async def exigir_autorizado(*, company_id: int, actor_user_id: int) -> None:
    rol = await service.rol_en_compania(company_id=company_id, user_id=actor_user_id)
    if rol != ROL_AUTORIZADO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the CER Route administrator can retire or replace managers.",
        )


async def ejecutar(
    *,
    company_id: int,
    actor_user_id: int,
    operacion: str,
    saliente: int,
    sucesor: int | None,
    expected_version: int | None,
    reason: str | None,
    degradar: tuple[str, int | None] | None = None,
) -> tuple[Plan, str]:
    """Aplica el plan en una sola transacción. Devuelve el plan y su id de operación."""
    from app.routers_api.usermanagement.dao import UserManagementDAO

    if saliente == actor_user_id:
        raise _conflicto("You cannot retire or replace yourself.")
    operacion_id = str(uuid.uuid4())
    async with transaction() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k, :c)"), {"k": service._CANDADO, "c": company_id}
        )
        # Con el candado tomado, se recalcula sobre lo que hay **ahora**: nada
        # de la vista previa se da por bueno.
        plan, gente = await calcular(
            company_id=company_id,
            operacion=operacion,
            saliente=saliente,
            sucesor=sucesor,
            degradar=degradar,
        )
        if expected_version is not None:
            ensure_version(current=plan.version, expected=expected_version)
        actuales = await service.vigentes(company_id)

        ahora = await session.scalar(select(func.now()))
        await session.execute(
            update(OrgAssignment)
            .where(
                OrgAssignment.company_id == company_id,
                OrgAssignment.user_id.in_(list(plan.final)),
                OrgAssignment.valid_to.is_(None),
            )
            .values(valid_to=ahora)
        )
        for u, valor in plan.final.items():
            if valor is None:
                continue
            previa = actuales.get(u)
            await session.execute(
                insert(OrgAssignment).values(
                    company_id=company_id,
                    user_id=u,
                    position=valor[0],
                    superior_user_id=valor[1],
                    valid_from=ahora,
                    created_by=actor_user_id,
                    reason=reason,
                    version=(previa.version + 1) if previa else 1,
                    # La fila del sucesor recuerda a quién sustituye: con eso
                    # hereda lo que veía su antecesor (V1.5).
                    replaces_user_id=saliente if u == plan.sucesor else None,
                )
            )

        async def _rol_del_cargo(user_id: int, cargo: str) -> None:
            """Un rol por cargo: el rol de `user_id` pasa a ser el de `cargo`."""
            nuevo_rol = ROL_DE_CARGO[cargo]
            rol_previo = await session.scalar(
                select(Role.id)
                .join(UserCompany, UserCompany.role_id == Role.id)
                .where(UserCompany.user_id == user_id, UserCompany.company_id == company_id)
            )
            rol_id = await session.scalar(
                select(Role.id).where(Role.company_id == company_id, Role.name == nuevo_rol)
            )
            if rol_id is None:
                raise _conflicto(f"The role {nuevo_rol} does not exist in this company.")
            if rol_id == rol_previo:
                return
            await session.execute(
                update(UserCompany)
                .where(
                    UserCompany.user_id == user_id,
                    UserCompany.company_id == company_id,
                    UserCompany.deleted_at.is_(None),
                )
                .values(role_id=rol_id)
            )
            await record_event(
                company_id=company_id,
                entity_type="user",
                entity_id=user_id,
                action="update",
                actor_user_id=actor_user_id,
                summary=f"Role changed by replacement {operacion_id}",
                changes={"role_id": {"old": rol_previo, "new": rol_id},
                         "operation_id": {"old": None, "new": operacion_id}},
                reason=reason,
            )

        if plan.sucesor is not None:
            await _rol_del_cargo(plan.sucesor, plan.cargo)

        retirado = None
        if plan.degradado is not None:
            # Se queda, con el rol de su cargo nuevo.
            await _rol_del_cargo(saliente, plan.degradado[0])
        else:
            # Quien sale deja la compañía con la baja que ya existe.
            retirado = await UserManagementDAO.delete_membership(user_id=saliente, company_id=company_id)

        for u, valor in plan.final.items():
            previa = actuales.get(u)
            await record_event(
                company_id=company_id,
                entity_type="org_assignment",
                entity_id=u,
                action="unassign" if valor is None else ("reassign" if previa else "assign"),
                actor_user_id=actor_user_id,
                summary=f"{'Retirement' if operacion == 'retire' else 'Replacement'} {operacion_id}",
                changes={
                    "position": {"old": previa.position if previa else None,
                                 "new": valor[0] if valor else None},
                    "superior_user_id": {"old": previa.superior_user_id if previa else None,
                                         "new": valor[1] if valor else None},
                    "operation_id": {"old": None, "new": operacion_id},
                },
                reason=reason,
            )
        if retirado is not None:
            await record_event(
                company_id=company_id,
                entity_type="user",
                entity_id=saliente,
                action="delete",
                actor_user_id=actor_user_id,
                summary=f"Removed from this company by {operacion} {operacion_id}",
                changes={
                    "membership": {"old": "active", "new": None},
                    "role_id": {"old": retirado.get("role_id"), "new": None},
                    "operation_id": {"old": None, "new": operacion_id},
                },
                reason=reason,
            )
        await record_event(
            company_id=company_id,
            entity_type="org_succession",
            entity_id=saliente,
            action=operacion,
            actor_user_id=actor_user_id,
            summary=(
                f"{ETIQUETA[plan.cargo]} {gente.get(saliente, saliente)} "
                + ("retired" if operacion == "retire"
                   else f"replaced by {gente.get(plan.sucesor, plan.sucesor)}")
            ),
            changes={
                "operation_id": {"old": None, "new": operacion_id},
                "outgoing_user_id": {"old": saliente, "new": None},
                "position": {"old": plan.cargo, "new": None},
                "successor_user_id": {"old": None, "new": plan.sucesor},
                "successor_before": {"old": list(plan.sucesor_antes) if plan.sucesor_antes else None,
                                     "new": [plan.cargo, plan.superior_saliente] if plan.sucesor else None},
                "outgoing_after": {"old": [plan.cargo, plan.superior_saliente],
                                   "new": list(plan.degradado) if plan.degradado else None},
                "moved": {"old": None, "new": [
                    {"user_id": m.user_id, "from": m.superior_antes, "to": m.superior_despues}
                    for m in plan.movimientos
                ]},
            },
            reason=reason,
        )
    return plan, operacion_id
