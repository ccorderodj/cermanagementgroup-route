"""
La política única de alcance de datos de las vistas de administración de Route.

Una sola función —`alcance_administrativo`— decide sobre qué personas y qué
jornadas puede leer un actor en Today, Activity, Reports y su Excel. Las
superficies no deciden nada: piden el alcance y filtran con él **antes** de
agregar, contar u ordenar.

Las tres respuestas posibles
----------------------------
* **Tenant** — todo actor sin rol de mando de Route. Es el contrato vigente
  y no se toca: quien tiene hoy `route.live.read` (el Superadmin `route_admin`,
  `owner`, `admin` o un rol propio) sigue viendo la compañía. No se crea ninguna
  equivalencia nueva entre roles: simplemente sólo el rol nuevo se acota.
* **Rama** — un rol de mando (CEO, COO, Regional Manager, y el `route_manager`
  heredado): sus descendientes.
  - *Hoy* (Today): los descendientes **vigentes**.
  - *Historia* (Activity, Reports, Excel): cada jornada se atribuye entera a la
    cadena vigente en su `started_at` (D-3). Un supervisor que pasó de RM-A a
    RM-B queda visible para RM-A en el periodo en que dependía de él y para
    RM-B desde que depende de él; nadie hereda el pasado de otro.
* **Vacío** — un rol de mando sin cargo o sin subordinados no ve a nadie.
  Una lista vacía **no** es «sin filtro» (B2.3).

Sin caché: se calcula en cada petición desde la base, así que un cambio de
superior rige en la lectura siguiente.

`/route/*` y `/api/activity-explorer/me` no pasan por aquí: allí el sujeto es
siempre el usuario de la sesión.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import and_, false, or_

from app.routers_api.organization.service import (
    Asignacion,
    historial,
    rol_en_compania,
)

#: Los roles cuyo alcance se acota a su rama: los de mando de la jerarquía
#: (V1.3) y el `route_manager` heredado. Nunca el tenant por ser CEO.
ROLES_ACOTADOS: frozenset[str] = frozenset({"CEO", "COO", "Regional Manager", "route_manager"})

Ventana = tuple[datetime, datetime | None]


@dataclass
class Alcance:
    """`tenant=True`: sin acotar. Si no, `ventanas` por persona."""

    tenant: bool
    #: Periodos `[desde, hasta)` en que cada persona estuvo en la rama.
    ventanas: dict[int, list[Ventana]] = field(default_factory=dict)

    @property
    def actuales(self) -> set[int]:
        """Quienes están en la rama **ahora**: su último periodo está abierto."""
        return {u for u, vs in self.ventanas.items() if vs and vs[-1][1] is None}

    @property
    def historicos(self) -> set[int]:
        """Quienes estuvieron en la rama en algún momento."""
        return set(self.ventanas)

    def ve(self, user_id: int) -> bool:
        return self.tenant or user_id in self.ventanas


def ramas_por_periodo(filas: list[Asignacion], raiz: int) -> dict[int, list[Ventana]]:
    """Los periodos en que cada persona colgó de `raiz`, reconstruidos instante a
    instante con las vigencias `[valid_from, valid_to)`.

    Entre dos cambios consecutivos —cualquier apertura o cierre de la compañía—
    el árbol es constante; se recorre una vez por tramo y se unen los tramos
    contiguos de cada persona.
    """
    instantes = sorted(
        {f.valid_from for f in filas} | {f.valid_to for f in filas if f.valid_to is not None}
    )
    ventanas: dict[int, list[Ventana]] = {}
    for i, desde in enumerate(instantes):
        hasta = instantes[i + 1] if i + 1 < len(instantes) else None
        hijos: dict[int, list[int]] = {}
        for f in filas:
            if f.valid_from <= desde and (f.valid_to is None or f.valid_to > desde):
                if f.superior_user_id is not None:
                    hijos.setdefault(f.superior_user_id, []).append(f.user_id)
        vistos: set[int] = set()
        pendientes = list(hijos.get(raiz, []))
        while pendientes:
            u = pendientes.pop()
            if u in vistos or u == raiz:
                continue
            vistos.add(u)
            pendientes.extend(hijos.get(u, []))
        for u in vistos:
            lista = ventanas.setdefault(u, [])
            if lista and lista[-1][1] == desde:
                lista[-1] = (lista[-1][0], hasta)
            else:
                lista.append((desde, hasta))
    return ventanas


async def alcance_administrativo(*, company_id: int, actor_user_id: int) -> Alcance:
    """El alcance de lectura administrativa de este actor en esta compañía."""
    rol = await rol_en_compania(company_id=company_id, user_id=actor_user_id)
    if rol not in ROLES_ACOTADOS:
        return Alcance(tenant=True)
    filas = await historial(company_id)
    return Alcance(tenant=False, ventanas=ramas_por_periodo(filas, actor_user_id))


def condicion_de_jornadas(alcance: Alcance, columna_usuario, columna_inicio, user_ids=None):
    """La condición SQL que deja sólo las jornadas en alcance.

    `None` si el alcance es de tenant (no se añade nada). Con rama: la jornada
    de cada persona cuenta si **empezó** dentro de uno de sus periodos. Sin
    periodos, `false()`: nada.
    """
    if alcance.tenant:
        return None
    partes = []
    for user_id, ventanas in alcance.ventanas.items():
        if user_ids is not None and user_id not in user_ids:
            continue
        for desde, hasta in ventanas:
            tramo = [columna_usuario == user_id, columna_inicio >= desde]
            if hasta is not None:
                tramo.append(columna_inicio < hasta)
            partes.append(and_(*tramo))
    return or_(*partes) if partes else false()
