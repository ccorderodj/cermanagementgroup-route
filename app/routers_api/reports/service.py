"""
El modelo de lectura de Reports (RTE09): un solo resultado para la pantalla y
para el Excel.

Cómo se compone
---------------
1. El periodo **en curso** y sus subgrupos salen del explorador (`periodo`,
   `componer_grupos`): semana lunes–domingo, el mes en semanas recortadas, el
   año en meses. El V0.7 lo dice en la propia tarjeta: *«Time grouping follows
   Activity exploration»*.
2. Los hechos son una fila por viaje (`dao.hechos`).
3. El combustible se resuelve **por jornada** (`fuelreference.service`), con sus
   entradas congeladas, y se reparte a sus viajes de forma lineal.
4. Todo lo demás —resumen, grupos, desglose— son sumas de esas mismas filas.

Por eso `Σ grupos = resumen` y `Σ desglose + Σ excluidos = resumen` se cumplen
por construcción, salvo el redondeo a la décima de milla, que se aplica una vez
sobre los metros de cada corte, como en el resto del producto.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.routers_api.activityexplorer.dao import (
    _subperiodos,
    componer_grupos,
    periodo,
    supervisores,
)
from app.routers_api.fuelreference.service import (
    CALCULATED,
    MISSING_INPUT,
    WAITING_REFERENCE,
    Combustible,
    EntradasJornada,
    coste,
    galones,
    resolver,
)
from app.routers_api.mileage.models import MileageState
from app.routers_api.mileage.read import millas_oficiales
from app.routers_api.reports import dao
from app.routers_api.worksessions.time_zones import dia_local, zonas_de_referencia

#: Las filas del *Activity Breakdown* del V0.7, en su orden. `home` no es una
#: visita y no tiene fila: sus millas van a `breakdown_excluded`.
PROPOSITOS_V07: tuple[str, ...] = (
    "client_visit",
    "employee_visit",
    "recruiting",
    "check_delivery",
    "office",
    "other",
)

#: Por qué nivel agrupa cada rango. Lo mismo que el explorador.
AGRUPA_POR: dict[str, str] = {"week": "day", "month": "week", "year": "month"}

CENTIMOS = Decimal("0.01")

#: Cuántas opciones ofrece, como mucho, el selector de periodo: un año de
#: semanas, tres de meses, diez de años. Acotado a propósito: una lista sin
#: límite crecería con la historia del tenant. Un periodo más antiguo sigue
#: siendo consultable por el API (`date`), y se añade a las opciones si es el
#: que se está mostrando (una recarga con un periodo guardado).
OPCIONES_MAXIMAS: dict[str, int] = {"week": 52, "month": 36, "year": 10}


class GrupoFueraDelPeriodo(ValueError):
    """El subgrupo pedido no es uno de los del periodo principal."""


async def hoy_del_informe(company_id: int, user_ids: list[int]) -> date:
    """El día que ancla el periodo en curso, decidido en el servidor.

    Con un supervisor, su día (T-1/T-2). Con *All Supervisors*, el día local más
    frecuente entre los que tienen zona: una semana o un mes casi nunca cambian
    por un día de diferencia, y cuando lo hacen gana la mayoría. Nunca la fecha
    del navegador.
    """
    ahora = datetime.now(timezone.utc)
    if not user_ids:
        return ahora.date()
    zonas = await zonas_de_referencia(company_id=company_id, user_ids=user_ids)
    dias = Counter(dia_local(ahora, z) for z, _ in zonas.values() if z is not None)
    if dias:
        return dias.most_common(1)[0][0]
    from app.routers_api.activityexplorer.dao import dia_actual_de

    return await dia_actual_de(company_id, user_ids[0] if len(user_ids) == 1 else None)


async def construir(
    *,
    company_id: int,
    rango: str,
    ancla: date | None,
    supervisor_user_id: int | None,
    grupo: date | None = None,
) -> tuple[dict, list[dict]]:
    """La vista y las filas enriquecidas que la producen (las del Excel).

    `supervisor_user_id` ya viene validado por el router contra el conjunto
    autorizado; `None` es *All Supervisors*.

    `grupo` es el inicio de un subgrupo del periodo —un día de la semana, una
    semana del mes, un mes del año— y **sólo acota el desglose**: KPIs, grupos
    y filas del Excel siguen siendo del periodo principal. Un `grupo` que no es
    uno de esos subgrupos lanza `GrupoFueraDelPeriodo`.
    """
    autorizados = await supervisores(company_id)
    user_ids = (
        [supervisor_user_id]
        if supervisor_user_id is not None
        else [s["user_id"] for s in autorizados]
    )

    hoy = await hoy_del_informe(company_id, user_ids)
    inicio, fin = periodo(rango, ancla or hoy)

    elegido = None
    if grupo is not None:
        elegido = next(
            ((a, b) for a, b in _subperiodos(rango, inicio, fin) if a == grupo), None
        )
        if elegido is None:
            raise GrupoFueraDelPeriodo(grupo)
    filas = await dao.hechos(
        company_id=company_id, user_ids=user_ids, inicio=inicio, fin=fin
    )

    combustible = await _combustible_por_jornada(company_id, filas)
    for f in filas:
        _enriquecer(f, combustible[f["session_id"]])

    grupos = []
    for g in componer_grupos(rango, inicio, fin, _por_dia(filas)):
        dentro = [f for f in filas if g["start"] <= f["session_date"] <= g["end"]]
        grupos.append({"start": g["start"], "end": g["end"], **_metricas(dentro, combustible)})

    # El desglose, del periodo entero o del subgrupo: las mismas filas,
    # acotadas por `session_date` con los mismos límites que el grupo.
    base = (
        [f for f in filas if elegido[0] <= f["session_date"] <= elegido[1]]
        if elegido
        else filas
    )
    desglose = [
        {"purpose": p, **_metricas(dentro, combustible)}
        for p in PROPOSITOS_V07
        if (dentro := [f for f in base if f["purpose"] == p])
    ]
    excluidos = [
        {"purpose": p, **_metricas(dentro, combustible)}
        for p in sorted({f["purpose"] for f in base} - set(PROPOSITOS_V07))
        if (dentro := [f for f in base if f["purpose"] == p])
    ]

    tipos = Counter(
        etiqueta
        for f in base
        if f["execution_id"] is not None
        for etiqueta in f["activity_labels"]
    )

    opciones = await _opciones(company_id, user_ids, rango, hoy, (inicio, fin))

    vista = {
        "range": rango,
        "start": inicio,
        "end": fin,
        "grouped_by": AGRUPA_POR[rango],
        "supervisors": autorizados,
        "supervisor_user_id": supervisor_user_id,
        "periods": [{"start": a, "end": b} for a, b in opciones],
        "summary": _metricas(filas, combustible),
        "groups": grupos,
        "selected_group": (
            {"start": elegido[0], "end": elegido[1]} if elegido else None
        ),
        "breakdown": desglose,
        "breakdown_excluded": excluidos,
        "activity_types": [
            {"label": etiqueta, "count": n}
            for etiqueta, n in sorted(tipos.items(), key=lambda t: (-t[1], t[0]))
        ],
        "fuel": _resumen_combustible(filas, combustible),
    }
    return vista, filas


async def _opciones(
    company_id: int,
    user_ids: list[int],
    rango: str,
    hoy: date,
    mostrado: tuple[date, date],
) -> list[tuple[date, date]]:
    """Las opciones del selector, de la más reciente a la más antigua.

    Empiezan en el periodo **en curso del servidor** —nunca en la fecha del
    navegador— y retroceden hasta el primer dato del alcance autorizado, con
    el tope de `OPCIONES_MAXIMAS`. Sin datos, sólo el en curso.
    """
    primero = await dao.primer_dia(company_id=company_id, user_ids=user_ids)
    opciones: list[tuple[date, date]] = []
    cursor = periodo(rango, hoy)
    while len(opciones) < OPCIONES_MAXIMAS[rango]:
        opciones.append(cursor)
        if primero is None or cursor[0] <= primero:
            break
        cursor = periodo(rango, cursor[0] - timedelta(days=1))
    if mostrado not in opciones:
        opciones.append(mostrado)
        opciones.sort(reverse=True)
    return opciones


async def _combustible_por_jornada(
    company_id: int, filas: list[dict]
) -> dict[int, Combustible]:
    """Las entradas de cada jornada, tomadas de sus viajes, y su estimación."""
    jornadas: dict[int, dict] = {}
    for f in filas:
        j = jornadas.setdefault(
            f["session_id"],
            {
                "session_date": f["session_date"],
                "terminada": f["session_ended"],
                "mpg": f["mpg"],
                "grado": f["fuel_grade"],
                "estado": f["operational_state"],
                "metros": Decimal("0"),
                "pendientes": 0,
            },
        )
        j["metros"] += Decimal(f["metros"] or 0)
        j["pendientes"] += int(f["pendiente"])

    return await resolver(
        company_id=company_id,
        jornadas=[EntradasJornada(session_id=sid, **datos) for sid, datos in jornadas.items()],
    )


def _enriquecer(fila: dict, comb: Combustible) -> None:
    """Las millas, galones y coste **de este viaje**, con la estimación de su
    jornada. Lineal: la suma de los viajes es la de la jornada."""
    calculado = fila["mileage_state"] == MileageState.CALCULATED.value
    metros = Decimal(fila["metros"] or 0) if calculado else None
    fila["official_miles"] = millas_oficiales(metros) if calculado else None
    fila["estimated_gallons"] = galones(metros, comb.mpg)
    fila["estimated_fuel_cost"] = coste(metros, comb)
    fila["fuel_cost_status"] = comb.status
    fila["fuel_final"] = comb.final
    fila["reference_price"] = comb.precio if comb.status == CALCULATED else None
    fila["reference_effective_date"] = comb.fecha_efectiva
    fila["reference_source"] = comb.fuente


def _por_dia(filas: list[dict]) -> dict[date, dict]:
    """La forma que `componer_grupos` del explorador espera, por día."""
    dias: dict[date, dict] = {}
    for f in filas:
        d = dias.setdefault(
            f["session_date"],
            {"metros": Decimal("0"), "pendientes": 0, "paradas": 0, "segundos": 0, "abiertos": 0},
        )
        d["metros"] += Decimal(f["metros"] or 0)
        d["pendientes"] += int(f["pendiente"])
        if f["execution_id"] is not None:
            d["paradas"] += 1
            d["segundos"] += f["segundos"]
            d["abiertos"] += int(f["activity_ended_at"] is None)
    return dias


def _metricas(filas: list[dict], combustible: dict[int, Combustible]) -> dict:
    """Las métricas de un corte: un resumen, un grupo o una fila del desglose."""
    metros = sum((Decimal(f["metros"] or 0) for f in filas), Decimal("0"))
    ejecuciones = [f for f in filas if f["execution_id"] is not None]
    con_galones = [f["estimated_gallons"] for f in filas if f["estimated_gallons"] is not None]
    jornadas = {f["session_id"] for f in filas}
    return {
        "official_miles": millas_oficiales(metros),
        "mileage_pending": any(f["pendiente"] for f in filas),
        "mileage_unresolved": sum(int(f["sin_cifra"]) for f in filas),
        "activity_seconds": sum(f["segundos"] for f in ejecuciones),
        "has_open_activity": any(f["activity_ended_at"] is None for f in ejecuciones),
        "activities": len(ejecuciones),
        "estimated_gallons": (
            sum(con_galones, Decimal("0")).quantize(Decimal("0.001")) if con_galones else None
        ),
        "estimated_fuel_cost": sum(
            (f["estimated_fuel_cost"] for f in filas), Decimal("0")
        ).quantize(CENTIMOS, rounding=ROUND_HALF_UP),
        "fuel_cost_status": _estado(combustible[s].status for s in jornadas),
    }


def _estado(estados) -> str:
    """El estado del coste de un corte, a partir del de sus jornadas."""
    vistos = list(estados)
    if not vistos:
        return "none"
    calculadas = sum(1 for e in vistos if e == CALCULATED)
    if calculadas == len(vistos):
        return CALCULATED
    if calculadas:
        return "partial"
    if any(e == MISSING_INPUT for e in vistos):
        return MISSING_INPUT
    return WAITING_REFERENCE


def _resumen_combustible(filas: list[dict], combustible: dict[int, Combustible]) -> dict:
    jornadas = [combustible[s] for s in {f["session_id"] for f in filas}]
    faltan = Counter(nombre for c in jornadas for nombre in c.faltan)
    return {
        "sessions": len(jornadas),
        "calculated": sum(1 for c in jornadas if c.status == CALCULATED),
        "final": sum(1 for c in jornadas if c.final),
        "waiting_reference": sum(1 for c in jornadas if c.status == WAITING_REFERENCE),
        "missing_input": sum(1 for c in jornadas if c.status == MISSING_INPUT),
        "missing": dict(sorted(faltan.items())),
    }
