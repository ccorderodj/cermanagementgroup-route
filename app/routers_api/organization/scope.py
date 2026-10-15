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
  - *Historia del CEO*: **todo, sin tiempo** (V1.6). Hay un solo CEO y toda
    la jerarquía es suya; incluye a quien ya salió, hasta su última asignación.
  - *Historia* de COO y RM (Activity, Reports, Excel): **la historia sigue al puesto**
    (V1.5, sustituye a D-3 en dos casos). Cada jornada se atribuye a la cadena
    vigente en su `started_at`, con dos excepciones:
      * **Carga inicial.** La primera asignación de cada persona cubre todo su
        pasado: antes de existir la jerarquía nadie era su jefe, así que esas
        jornadas son de quien la recibe primero (no hay a quién quitárselas).
      * **Sustitución.** Quien entra por «Replace manager» hereda lo que veía
        su antecesor hasta el instante del relevo: un CEO o un RM nuevo ve el
        histórico de su puesto, no sólo desde que llegó.
    Los **traslados laterales** siguen por periodo: un supervisor que pasa de
    RM-A (Texas) a RM-B (Georgia) queda para RM-A en su tramo y para RM-B desde
    el traslado; ninguno ve la zona del otro y el histórico de cada zona no se
    reescribe. COO y CEO lo siguen viendo entero, porque no salió de su rama.
* **Vacío** — un rol de mando sin cargo o sin subordinados no ve a nadie.
  Una lista vacía **no** es «sin filtro» (B2.3).

Sin caché: se calcula en cada petición desde la base, así que un cambio de
superior rige en la lectura siguiente.

`/route/*` y `/api/activity-explorer/me` no pasan por aquí: allí el sujeto es
siempre el usuario de la sesión.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from sqlalchemy import and_, false, or_

from app.routers_api.organization.models import OrgPosition
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


#: Desde cuándo cuenta la primera asignación de cada persona (carga inicial).
ORIGEN = datetime(1970, 1, 1, tzinfo=timezone.utc)


def con_carga_inicial(filas: list[Asignacion]) -> list[Asignacion]:
    """La primera asignación de cada persona, extendida hasta `ORIGEN`.

    Sólo para calcular el alcance: la fila guardada no cambia.
    """
    primera: dict[int, Asignacion] = {}
    for f in filas:
        if f.user_id not in primera or f.valid_from < primera[f.user_id].valid_from:
            primera[f.user_id] = f
    return [replace(f, valid_from=ORIGEN) if primera[f.user_id] is f else f for f in filas]


def antecesores(filas: list[Asignacion], raiz: int) -> list[tuple[int, datetime]]:
    """A quiénes sustituyó `raiz` —y a quiénes sustituyeron ellos—, con el
    instante de cada relevo."""
    resultado: list[tuple[int, datetime]] = []
    vistos = {raiz}
    pendientes = [raiz]
    while pendientes:
        u = pendientes.pop()
        for f in filas:
            if f.user_id == u and f.replaces_user_id and f.replaces_user_id not in vistos:
                vistos.add(f.replaces_user_id)
                resultado.append((f.replaces_user_id, f.valid_from))
                pendientes.append(f.replaces_user_id)
    return resultado


def _recortar(ventanas: list[Ventana], hasta: datetime) -> list[Ventana]:
    return [
        (d, h if h is not None and h < hasta else hasta)
        for d, h in ventanas
        if d < hasta
    ]


def _unir(a: list[Ventana], b: list[Ventana]) -> list[Ventana]:
    unidas: list[Ventana] = []
    for d, h in sorted(a + b, key=lambda v: v[0]):
        if unidas and (unidas[-1][1] is None or unidas[-1][1] >= d):
            previo_d, previo_h = unidas[-1]
            unidas[-1] = (previo_d, None if previo_h is None or h is None else max(previo_h, h))
        else:
            unidas.append((d, h))
    return unidas


def ventanas_del_puesto(filas: list[Asignacion], raiz: int) -> dict[int, list[Ventana]]:
    """La rama de `raiz` por periodo, con la carga inicial y lo heredado de sus
    antecesores hasta cada relevo (V1.5)."""
    # Los relevos, de las filas tal como se guardaron: la fila de un sucesor
    # nuevo es también su primera, y extendida perdería el instante del relevo.
    relevos = antecesores(filas, raiz)
    filas = con_carga_inicial(filas)
    ventanas = ramas_por_periodo(filas, raiz)
    for antecesor, relevo in relevos:
        for u, vs in ramas_por_periodo(filas, antecesor).items():
            if u == raiz:
                continue
            heredadas = _recortar(vs, relevo)
            if heredadas:
                ventanas[u] = _unir(ventanas.get(u, []), heredadas)
    return ventanas


def ventanas_del_ceo(filas: list[Asignacion], ceo: int) -> dict[int, list[Ventana]]:
    """El CEO ve **todo**, sin tiempo (V1.6): hay uno solo, y toda la
    jerarquía es su árbol.

    * Quien cuelga hoy de él: todo su historial, ventana abierta.
    * Quien ya no tiene cargo (salió de la compañía o del árbol): todo su
      historial hasta su última asignación, ventana cerrada. Así no queda
      ningún punto ciego y Today —que mira las ventanas abiertas— sigue
      mostrando sólo a quien está.
    """
    abiertas = {f.user_id for f in filas if f.valid_to is None}
    actuales = {u for u, vs in ramas_por_periodo(filas, ceo).items() if vs and vs[-1][1] is None}
    ultima: dict[int, datetime] = {}
    for f in filas:
        if f.user_id == ceo or f.user_id in abiertas or f.valid_to is None:
            continue
        if f.user_id not in ultima or f.valid_to > ultima[f.user_id]:
            ultima[f.user_id] = f.valid_to
    ventanas: dict[int, list[Ventana]] = {u: [(ORIGEN, None)] for u in actuales}
    ventanas.update({u: [(ORIGEN, hasta)] for u, hasta in ultima.items()})
    return ventanas


async def alcance_administrativo(*, company_id: int, actor_user_id: int) -> Alcance:
    """El alcance de lectura administrativa de este actor en esta compañía."""
    rol = await rol_en_compania(company_id=company_id, user_id=actor_user_id)
    if rol not in ROLES_ACOTADOS:
        return Alcance(tenant=True)
    filas = await historial(company_id)
    propia = next(
        (f for f in filas if f.user_id == actor_user_id and f.valid_to is None), None
    )
    if propia is not None and propia.position == OrgPosition.CEO:
        return Alcance(tenant=False, ventanas=ventanas_del_ceo(filas, actor_user_id))
    return Alcance(tenant=False, ventanas=ventanas_del_puesto(filas, actor_user_id))


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
