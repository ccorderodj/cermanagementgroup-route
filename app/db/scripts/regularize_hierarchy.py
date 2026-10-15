"""Regulariza la jerarquía de CER Route por las vías del producto. Modo prueba por omisión.

Para qué existe
---------------
Antes de V1.4, la pantalla general permitía cambiar el rol de un jefe sin tocar
su cargo: quedaron personas con rol `supervisor` y cargo COO o Regional Manager.
Y con V1.4, «Replace manager» retiraba siempre a quien salía (así salió la CEO
anterior del entorno compartido). Este comando deja todo coherente **con los
mismos servicios y validaciones que usa la pantalla**; no escribe SQL a mano.

Dos acciones, cada una explícita
--------------------------------
* `--alinear` (por omisión): a quien tiene rol y cargo que no se
  corresponden le pone **el rol de su cargo**. El cargo y el superior no se
  tocan: son la estructura que se cargó desde CER Route; el rol es lo que la
  pantalla general cambió por error.
* `--readmitir CORREO --rol ROL --superior CORREO`: devuelve a la compañía a
  quien fue retirado, con ese rol y bajo ese superior, en una transacción
  (pertenencia + cargo), como «Create user → Re-add» en CER Route.

Sin `--aplicar` sólo enseña lo que haría. Con `--aplicar`, cada cambio deja su
`audit_event` sin actor (lo ejecutó un comando autorizado, no una persona desde
una pantalla) y con el motivo. Ids internos en la salida; nada de coordenadas.

    python -m app.db.scripts.regularize_hierarchy --compania 1
    python -m app.db.scripts.regularize_hierarchy --compania 1 --aplicar
    python -m app.db.scripts.regularize_hierarchy --compania 1 \\
        --readmitir lcerda@cermanagementgroup.com --rol COO --superior test@test.com --aplicar
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import func, select

from app.core.audit.service import record_event
from app.core.db.session import transaction
from app.database import async_session_maker
from app.db.model_registry import load_all_models

load_all_models()

from app.routers_api.companies.models import UserCompany  # noqa: E402
from app.routers_api.organization import service as organizacion  # noqa: E402
from app.routers_api.organization.models import CARGO_DE_ROL, ROL_DE_CARGO  # noqa: E402
from app.routers_api.roles.models import Role  # noqa: E402
from app.routers_api.usermanagement.dao import UserManagementDAO  # noqa: E402
from app.routers_api.users.models import Users  # noqa: E402

MOTIVO = "Hierarchy regularization by authorized command"


@dataclass(frozen=True)
class Desajuste:
    user_id: int
    rol: str
    cargo: str
    rol_del_cargo: str


async def desajustes(company_id: int) -> list[Desajuste]:
    """Quienes tienen un cargo vigente cuyo rol no es el del cargo."""
    actuales = await organizacion.vigentes(company_id)
    miembros = await organizacion.pertenencias(company_id)
    casos = []
    for u, a in sorted(actuales.items()):
        rol = miembros[u].rol if u in miembros else None
        if rol is None or rol == "route_manager":
            continue
        if CARGO_DE_ROL.get(rol) != a.position:
            casos.append(Desajuste(u, rol, a.position, ROL_DE_CARGO[a.position]))
    return casos


async def _rol_id(company_id: int, nombre: str) -> int:
    ids = await organizacion.roles_por_nombre(company_id)
    if nombre not in ids:
        raise SystemExit(f"El rol {nombre!r} no existe en la compañía {company_id}.")
    return ids[nombre]


async def alinear(company_id: int, *, aplicar: bool) -> list[Desajuste]:
    casos = await desajustes(company_id)
    for c in casos:
        print(f"  usuario {c.user_id}: rol {c.rol!r} → {c.rol_del_cargo!r} (cargo {c.cargo}, sin tocar)")
        if not aplicar:
            continue
        rol_id = await _rol_id(company_id, c.rol_del_cargo)
        async with transaction():
            previo = await UserManagementDAO.find_for_company(user_id=c.user_id, company_id=company_id)
            await UserManagementDAO.update_user_in_company(
                user_id=c.user_id, company_id=company_id, role_id=rol_id
            )
            await record_event(
                company_id=company_id,
                entity_type="user",
                entity_id=c.user_id,
                action="update",
                actor_user_id=None,
                summary=f"Role aligned with position {c.cargo}",
                changes={"role_id": {"old": previo.get("role_id"), "new": rol_id}},
                reason=MOTIVO,
            )
    return casos


async def _id_por_correo(correo: str) -> int:
    async with async_session_maker() as s:
        uid = await s.scalar(select(Users.id).where(func.lower(Users.email) == correo.lower()))
    if uid is None:
        raise SystemExit(f"No existe un usuario con correo {correo}.")
    return uid


async def readmitir(
    company_id: int, *, correo: str, rol: str, superior: str, aplicar: bool
) -> None:
    user_id = await _id_por_correo(correo)
    superior_id = await _id_por_correo(superior)
    if user_id in await organizacion.pertenencias(company_id):
        raise SystemExit(f"{correo} ya pertenece a la compañía {company_id}: nada que readmitir.")
    if CARGO_DE_ROL.get(rol) is None:
        raise SystemExit(f"{rol!r} no es un rol de la jerarquía.")
    rol_id = await _rol_id(company_id, rol)
    print(f"  readmitir usuario {user_id} como {rol!r} bajo el usuario {superior_id}")
    if not aplicar:
        return
    # Misma operación que «Create user → Re-add» en CER Route: pertenencia y
    # cargo juntos; si el cargo no es válido (superior, CEO único…), nada queda.
    async with transaction():
        _, membership_id, rol_previo = await UserManagementDAO.reenroll_membership(
            user_id=user_id, company_id=company_id, role_id=rol_id
        )
        await organizacion.sincronizar_con_rol(
            company_id=company_id,
            actor_user_id=None,
            user_id=user_id,
            superior_user_id=superior_id,
            superior_dado=True,
            reason=MOTIVO,
        )
        await record_event(
            company_id=company_id,
            entity_type="user_company",
            entity_id=membership_id,
            action="reenroll",
            actor_user_id=None,
            summary=f"Tenant access restored for user {user_id} by authorized command",
            changes={
                "user_id": {"old": user_id, "new": user_id},
                "membership": {"old": "removed", "new": "active"},
                "role_id": {"old": rol_previo, "new": rol_id},
            },
            reason=MOTIVO,
        )


async def _principal() -> None:
    p = argparse.ArgumentParser(description="Regulariza la jerarquía de CER Route.")
    p.add_argument("--compania", type=int, required=True)
    p.add_argument("--readmitir", metavar="CORREO")
    p.add_argument("--rol")
    p.add_argument("--superior", metavar="CORREO")
    p.add_argument("--aplicar", action="store_true", help="Escribe; sin esto sólo enseña.")
    a = p.parse_args()

    if a.readmitir:
        if not (a.rol and a.superior):
            raise SystemExit("--readmitir necesita --rol y --superior.")
        await readmitir(a.compania, correo=a.readmitir, rol=a.rol, superior=a.superior, aplicar=a.aplicar)
    else:
        casos = await alinear(a.compania, aplicar=a.aplicar)
        print(f"  {len(casos)} desajuste(s) rol/cargo.")
    print("APLICADO." if a.aplicar else "MODO PRUEBA: no se ha escrito nada. Repetir con --aplicar.")


if __name__ == "__main__":
    asyncio.run(_principal())
