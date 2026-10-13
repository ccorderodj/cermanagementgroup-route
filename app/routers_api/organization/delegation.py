"""
Administración delegada de usuarios y estructura (D-2), validada en el servidor.

A quién afecta
--------------
Sólo a `route_manager` (CEO, COO, RM). Cualquier otro actor con `users.*`
conserva el contrato vigente de la administración de usuarios —incluidas sus
guardas propias (`role_policy`)—: esta política no amplía ni recorta a nadie
más.

Qué puede un `route_manager`
----------------------------
* **Sobre quién**: sólo sus descendientes **vigentes**, y de ellos sólo los que
  tienen rol `supervisor` o `route_manager`. Nunca a sí mismo, a pares, a
  superiores, a ramas ajenas, a un `route_admin` colocado en su rama ni a
  otro tenant. Fuera de eso, **404**, como un id que no existe.
* **Qué cargos**: estrictamente por debajo del suyo (CEO → COO, RM, OSM,
  Supervisor; COO → RM, OSM, Supervisor; RM → OSM, Supervisor).
* **Bajo qué superior**: él mismo o un descendiente suyo de nivel mayor que el
  cargo asignado. Una persona nueva **nunca** queda fuera de su rama.
* **Qué rol**: el que corresponde al cargo — `route_manager` para COO y RM,
  `supervisor` para OSM y Supervisor. Nunca `route_admin` ni un rol del núcleo.
* **Sin cargo** propio, un manager no gestiona a nadie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, status

from app.routers_api.organization.models import NIVEL, OrgPosition
from app.routers_api.organization.scope import ROL_ACOTADO
from app.routers_api.organization.service import (
    descendientes,
    rol_en_compania,
    vigentes,
)

#: Los roles que un manager puede ver y gestionar en su rama.
ROLES_GESTIONABLES: frozenset[str] = frozenset({"route_manager", "supervisor"})


def rol_para_cargo(position: str) -> str:
    """El rol de producto que lleva cada cargo cuando lo asigna un manager."""
    return "route_manager" if NIVEL[position] >= NIVEL[OrgPosition.REGIONAL_MANAGER] else "supervisor"


@dataclass
class Delegacion:
    actor_user_id: int
    #: `True`: no es `route_manager`; rige el contrato vigente sin acotar.
    tenant: bool
    #: Nivel del cargo vigente del manager; `None` sin cargo.
    nivel: int | None = None
    #: Descendientes vigentes (sin filtrar por rol).
    rama: set[int] = field(default_factory=set)

    @property
    def cargos_asignables(self) -> list[str]:
        if self.tenant:
            return list(OrgPosition.values())
        if self.nivel is None:
            return []
        return [p for p in OrgPosition.values() if NIVEL[p] < self.nivel]

    def superiores_posibles(self) -> set[int] | None:
        """Quiénes pueden ser superiores en una asignación suya; `None`: sin acotar."""
        if self.tenant:
            return None
        if self.nivel is None:
            return set()
        return self.rama | {self.actor_user_id}


async def delegacion(*, company_id: int, actor_user_id: int) -> Delegacion:
    rol = await rol_en_compania(company_id=company_id, user_id=actor_user_id)
    if rol != ROL_ACOTADO:
        return Delegacion(actor_user_id=actor_user_id, tenant=True)
    actuales = await vigentes(company_id)
    propia = actuales.get(actor_user_id)
    if propia is None:
        return Delegacion(actor_user_id=actor_user_id, tenant=False)
    return Delegacion(
        actor_user_id=actor_user_id,
        tenant=False,
        nivel=NIVEL[propia.position],
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


def exigir_rol(d: Delegacion, *, role_name: str | None, position: str | None) -> None:
    """403 si el rol no es el que corresponde al cargo (sólo managers)."""
    if d.tenant or role_name is None:
        return
    if position is None or role_name != rol_para_cargo(position):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="That role does not match the position you can assign.",
        )
