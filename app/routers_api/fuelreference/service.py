"""
La estimación de combustible de cada jornada (RTE09).

La fórmula aprobada
-------------------
    galones = millas oficiales / MPG operativo
    coste   = galones × precio de la referencia aplicable

Con **las entradas congeladas de la jornada**: su MPG, su grado, su estado
operativo. Nunca los valores actuales del vehículo o del supervisor, nunca el
delta de odómetro, nunca una distancia calculada en el navegador.

Se calcula por **jornada** —cada una tiene su MPG, su grado, su estado y su
fecha— y sólo después se suma. Nunca `millas del periodo / un MPG × un precio`.

Tres estados, que el API distingue sin ambigüedad
--------------------------------------------------
* `calculated` — hay referencia y se aplicó. El coste es real, aunque sea 0
  (una jornada válida sin millas).
* `waiting_reference` — las entradas están, falta el precio en la base. El
  coste **visible** es 0 por decisión de producto (autorización §8), pero no es
  un resultado: no se congela y se resuelve en cuanto la referencia exista.
* `missing_input` — falta una entrada de la jornada (estado, grado o MPG). Se
  dice cuál. Coste visible 0, con el mismo criterio que la espera.

Cuándo se congela
-----------------
Sólo cuando la estimación ya no puede cambiar: jornada **terminada**, ningún
viaje con kilometraje pendiente y una referencia **real** aplicada. Entonces se
escribe una fila en `work_session_fuel_estimate` con toda la procedencia, y a
partir de ahí manda esa fila: una referencia cargada después no la reescribe.

Escribirla durante una lectura es la única mutación que hace Reports, y está
acotada: una inserción idempotente (`ON CONFLICT DO NOTHING`) de un resultado
derivado. Ningún hecho operativo cambia (autorización §19).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.core.db.session import db_session, transaction
from app.routers_api.fuelreference.models import FuelReference, WorkSessionFuelEstimate
from app.routers_api.mileage.read import millas_oficiales

CALCULATED = "calculated"
WAITING_REFERENCE = "waiting_reference"
MISSING_INPUT = "missing_input"

#: Precisión interna: la de la referencia. Se redondea a céntimos al presentar.
CUATRO_DECIMALES = Decimal("0.0001")


@dataclass(frozen=True)
class EntradasJornada:
    """Lo que una jornada aporta al cálculo, ya congelado en ella."""

    session_id: int
    session_date: date
    terminada: bool
    mpg: Decimal | None
    grado: str | None
    estado: str | None
    #: Metros de los viajes con kilometraje **calculado**. Los pendientes y los
    #: que terminaron sin cifra no aportan: no se les inventa distancia.
    metros: Decimal
    #: Viajes cuyo kilometraje todavía puede llegar.
    pendientes: int


@dataclass(frozen=True)
class Combustible:
    """La estimación de una jornada y de dónde sale."""

    status: str
    #: Qué entradas faltan, si `status == missing_input`.
    faltan: tuple[str, ...] = ()
    #: Congelada: ya no cambia.
    final: bool = False
    mpg: Decimal | None = None
    grado: str | None = None
    estado: str | None = None
    precio: Decimal | None = None
    referencia_id: int | None = None
    fecha_efectiva: date | None = None
    fuente: str | None = None
    #: Lo congelado, si lo hay: es lo que se informa de una jornada final.
    galones_congelados: Decimal | None = None
    coste_congelado: Decimal | None = None
    extra: dict = field(default_factory=dict)


def millas_precisas(metros: Decimal) -> Decimal:
    """Las millas oficiales con cuatro decimales, con la **misma** conversión.

    Reutiliza `millas_oficiales` —el único sitio con la constante metros→millas—
    cambiando sólo la precisión del redondeo. Redondear a la décima antes de
    dividir por el MPG perdería céntimos en cada viaje.
    """
    return millas_oficiales(metros, precision=CUATRO_DECIMALES)


def galones(metros: Decimal | None, mpg: Decimal | None) -> Decimal | None:
    """Galones de unos metros calculados con un MPG. `None` si falta algo."""
    if metros is None or mpg is None or mpg <= 0:
        return None
    return millas_precisas(metros) / mpg


def coste(metros: Decimal | None, combustible: Combustible) -> Decimal:
    """El coste de unos metros con la estimación de su jornada.

    `0` cuando la jornada no está calculada: es el valor visible aprobado, y el
    estado de la jornada dice por qué. Nunca se multiplica por un precio falso.
    """
    if combustible.status != CALCULATED:
        return Decimal("0")
    g = galones(metros, combustible.mpg)
    if g is None:
        return Decimal("0")
    return g * combustible.precio


async def resolver(
    *, company_id: int, jornadas: list[EntradasJornada]
) -> dict[int, Combustible]:
    """La estimación de cada jornada, congelando las que ya son finales."""
    if not jornadas:
        return {}

    ids = [j.session_id for j in jornadas]
    async with db_session() as session:
        congeladas = {
            e.work_session_id: e
            for e in (
                await session.scalars(
                    select(WorkSessionFuelEstimate).where(
                        WorkSessionFuelEstimate.company_id == company_id,
                        WorkSessionFuelEstimate.work_session_id.in_(ids),
                    )
                )
            ).all()
        }

    resultado: dict[int, Combustible] = {}
    por_resolver: list[EntradasJornada] = []
    for j in jornadas:
        e = congeladas.get(j.session_id)
        if e is not None:
            resultado[j.session_id] = Combustible(
                status=CALCULATED,
                final=True,
                mpg=e.operational_mpg,
                grado=e.fuel_grade,
                estado=e.state_code,
                precio=e.price_per_gallon,
                referencia_id=e.fuel_reference_id,
                fecha_efectiva=e.effective_date,
                fuente=e.source,
                galones_congelados=e.estimated_gallons,
                coste_congelado=e.estimated_cost,
            )
            continue
        faltan = tuple(
            nombre
            for nombre, valor in (
                ("operational_state", j.estado),
                ("fuel_grade", j.grado),
                ("operational_mpg", j.mpg),
            )
            if valor is None
        )
        if faltan:
            resultado[j.session_id] = Combustible(
                status=MISSING_INPUT,
                faltan=faltan,
                mpg=j.mpg,
                grado=j.grado,
                estado=j.estado,
            )
            continue
        por_resolver.append(j)

    if not por_resolver:
        return resultado

    referencias = await _candidatas(company_id=company_id, jornadas=por_resolver)
    a_congelar: list[dict] = []
    for j in por_resolver:
        ref = _aplicable(referencias, estado=j.estado, grado=j.grado, dia=j.session_date)
        if ref is None:
            resultado[j.session_id] = Combustible(
                status=WAITING_REFERENCE, mpg=j.mpg, grado=j.grado, estado=j.estado
            )
            continue

        final = j.terminada and j.pendientes == 0
        combustible = Combustible(
            status=CALCULATED,
            final=final,
            mpg=j.mpg,
            grado=j.grado,
            estado=j.estado,
            precio=ref.price_per_gallon,
            referencia_id=ref.id,
            fecha_efectiva=ref.effective_date,
            fuente=ref.source,
        )
        resultado[j.session_id] = combustible
        if final:
            g = galones(j.metros, j.mpg) or Decimal("0")
            a_congelar.append(
                {
                    "company_id": company_id,
                    "work_session_id": j.session_id,
                    "fuel_reference_id": ref.id,
                    "state_code": j.estado,
                    "fuel_grade": j.grado,
                    "operational_mpg": j.mpg,
                    "official_miles": millas_precisas(j.metros),
                    "price_per_gallon": ref.price_per_gallon,
                    "effective_date": ref.effective_date,
                    "source": ref.source,
                    "estimated_gallons": g.quantize(CUATRO_DECIMALES),
                    "estimated_cost": (g * ref.price_per_gallon).quantize(CUATRO_DECIMALES),
                }
            )

    if a_congelar:
        # Idempotente: dos lecturas a la vez congelan una sola vez, y si otra
        # ganó la carrera su fila es la que vale.
        async with transaction() as session:
            await session.execute(
                insert(WorkSessionFuelEstimate)
                .values(a_congelar)
                .on_conflict_do_nothing(index_elements=["work_session_id"])
            )
    return resultado


async def _candidatas(
    *, company_id: int, jornadas: list[EntradasJornada]
) -> list[FuelReference]:
    """Las referencias que pueden aplicar, en el orden en que se eligen."""
    pares = sorted({(j.estado, j.grado) for j in jornadas})
    hasta = max(j.session_date for j in jornadas)
    async with db_session() as session:
        return list(
            (
                await session.scalars(
                    select(FuelReference)
                    .where(
                        FuelReference.company_id == company_id,
                        tuple_(FuelReference.state_code, FuelReference.fuel_grade).in_(pares),
                        FuelReference.effective_date <= hasta,
                    )
                    # La vigente es la de fecha efectiva más reciente; entre dos
                    # del mismo día, la cargada después (una corrección).
                    .order_by(
                        FuelReference.effective_date.desc(),
                        FuelReference.loaded_at.desc(),
                        FuelReference.id.desc(),
                    )
                )
            ).all()
        )


def _aplicable(
    referencias: list[FuelReference], *, estado: str, grado: str, dia: date
) -> FuelReference | None:
    """Mismo estado, mismo grado, vigente en `dia`. Sin región ni nación."""
    for ref in referencias:
        if ref.state_code == estado and ref.fuel_grade == grado and ref.effective_date <= dia:
            return ref
    return None
