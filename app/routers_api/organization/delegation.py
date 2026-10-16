"""
Administración delegada de usuarios y estructura, validada en el servidor.

A quién afecta
--------------
A los roles de mando de la jerarquía: CEO, COO, Regional Manager (V1.3) y el
`route_manager` heredado. Cualquier otro actor con `users.*` conserva el
contrato vigente de la administración de usuarios —incluidas sus guardas
propias (`role_policy`)—: esta política no amplía ni recorta a nadie más.

Qué puede un manager
--------------------
* **Sobre quién**: sólo sus descendientes **vigentes** con un rol de la
  jerarquía (`ROLES_GESTIONABLES`). Nunca a sí mismo, a pares, a superiores, a
  ramas ajenas, a un `route_admin` colocado en su rama ni a otro tenant. Fuera
  de eso, **404**, como un id que no existe.
* **Qué cargos**: estrictamente por debajo del suyo; **Sales sólo si es CEO**
  (CEO → COO, RM, OSM, Supervisor, Sales; COO → RM, OSM, Supervisor;
  RM → OSM, Supervisor).
* **Bajo qué superior**: él mismo o alguien de su rama, y además uno de los
  cargos de los que ese rol puede depender (`PADRES_PERMITIDOS`, que valida el
  servicio). Una persona nueva **nunca** queda fuera de su rama.
* **Qué rol**: el del cargo — un rol por cargo. Nunca `route_admin`, el
  `route_manager` heredado ni un rol del núcleo.
* **Sin cargo** propio, un manager no gestiona a nadie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, status

from app.routers_api.organization.models import NIVEL, ROL_DE_CARGO, OrgPosition
from app.routers_api.organization.scope import ROLES_ACOTADOS
from app.routers_api.organization.service import (
    descendientes,
    rol_en_compania,
    vigentes,
)

#: Los roles que un manager puede ver y gestionar en su rama: los de la
#: jerarquía por debajo de un CEO y el `route_manager` heredado. Nunca un
#: `route_admin` ni un rol del núcleo, aunque alguien lo colocara en su rama.
ROLES_GESTIONABLES: frozenset[str] = frozenset(
    {"COO", "Regional Manager", "OSM", "supervisor", "Sales", "route_manager"}
)


def rol_para_cargo(position: str) -> str:
    """El rol de producto de cada cargo (V1.3: uno por cargo)."""
    return ROL_DE_CARGO[position]


@dataclass
class Delegacion:
    actor_user_id: int
    #: `True`: no tiene rol de mando; rige el contrato vigente sin acotar.
    tenant: bool
    #: Nivel del cargo vigente del manager; `None` sin cargo.
    nivel: int | None = None
    #: Su cargo vigente.
    cargo: str | None = None
    #: Descendientes vigentes (sin filtrar por rol).
    rama: set[int] = field(default_factory=set)

    @property
    def cargos_asignables(self) -> list[str]:
        if self.tenant:
            return list(OrgPosition.values())
        if self.nivel is None:
            return []
        # Por debajo del suyo; Sales, sólo si es CEO (Sales depende de un CEO
        # directo y queda fuera de COO y RM).
        return [
            p for p in OrgPosition.values()
            if NIVEL[p] < self.nivel
            and (p != OrgPosition.SALES or self.cargo == OrgPosition.CEO)
        ]

    def superiores_posibles(self) -> set[int] | None:
        """Quiénes pueden ser superiores en una asignación suya; `None`: sin acotar."""
        if self.tenant:
            return None
        if self.nivel is None:
            return set()
        return self.rama | {self.actor_user_id}


async def delegacion(*, company_id: int, actor_user_id: int) -> Delegacion:
    rol = await rol_en_compania(company_id=company_id, user_id=actor_user_id)
    if rol not in ROLES_ACOTADOS:
        return Delegacion(actor_user_id=actor_user_id, tenant=True)
    actuales = await vigentes(company_id)
    propia = actuales.get(actor_user_id)
    if propia is None:
        return Delegacion(actor_user_id=actor_user_id, tenant=False)
    return Delegacion(
        actor_user_id=actor_user_id,
        tenant=False,
        nivel=NIVEL[propia.position],
        cargo=propia.position,
        rama=descendientes(actuales, actor_user_id),
    )


async def gestionables(d: Delegacion, *, company_id: int) -> set[int] | None:
    """Las personas que este manager puede ver y gestionar; `None`: sin acotar."""
    if d.tenant:
        return None
    resultado = set()
    for user_id in d.rama:
        rol = await rol_en_compania(
            company_id=company_id, user_id=user_id, incluir_suspendidos=True
        )
        if rol in ROLES_GESTIONABLES:
            resultado.add(user_id)
    return resultado


def _no_encontrado() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this company")


async def exigir_objetivo(d: Delegacion, *, company_id: int, user_id: int) -> None:
    """404 si el objetivo está fuera de lo que este actor puede gestionar."""
    if d.tenant:
        return
    if user_id not in (await gestionables(d, company_id=company_id) or set()):
        raise _no_encontrado()


def exigir_asignacion(
    d: Delegacion, *, position: str | None, superior_user_id: int | None
) -> None:
    """403 si el cargo o el superior quedan fuera de lo delegable."""
    if d.tenant:
        return
    if position is None or position not in d.cargos_asignables:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only assign positions below your own.",
        )
    posibles = d.superiores_posibles() or set()
    if superior_user_id is None or superior_user_id not in posibles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The superior must be you or someone in your branch.",
        )

