"""Traza el kilometraje de un viaje real, de punta a punta y sin escribir nada.

Para qué existe
---------------
El cierre de campo de Route Mileage exige una traza concreta por viaje:

    tenant -> supervisor -> jornada -> viaje -> evidencia de waypoints
           -> TripMileage -> estado -> intentos -> proveedor -> metros

Esa traza sólo se puede sacar del entorno donde ocurrió el síntoma, y quien
tiene acceso a ese entorno no es quien escribió el código. Sin un comando, la
alternativa es SQL escrito a mano en una consola de producción: cada ejecución
distinta, nada reproducible, y un `UPDATE` a un carácter de distancia de un
`SELECT`.

Este comando **sólo lee**. No hay `commit`, no hay `UPDATE` y no hay
`--aplicar`. Lo que resuelve un kilometraje es el barrido o
`reprocess_failed_mileage`; esto únicamente cuenta lo que hay.

Las coordenadas no salen por omisión
------------------------------------
Un waypoint es la ubicación de una persona en un momento concreto. La traza
necesita saber **si existe** y con qué nivel de evidencia, no dónde estaba, así
que por omisión se imprime la presencia y se oculta el valor. `--coordenadas`
las muestra para quien depura un caso delante de la base, y esa salida ya no
debería pegarse en un documento.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.database import async_session_maker
from app.db.model_registry import load_all_models
from app.routers_api.companies.models import Company
from app.routers_api.location.models import LocationFix, MissingLocationEvent
from app.routers_api.mileage.models import TripMileage, TripMileageSegment
from app.routers_api.mileage.read import millas_oficiales
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession

# SQLAlchemy resuelve las relaciones por nombre contra lo que esté registrado:
# `Company` apunta a `CompanyState`, que apunta a `Region`. Un script no importa
# los routers, así que hay que registrarlos igual que hace la aplicación.
load_all_models()

def _millas(metros) -> str:
    """La misma conversion que publican las pantallas. Nunca otra."""
    if metros is None:
        return "-"
    return str(millas_oficiales(metros))


def _punto(fix, *, coordenadas: bool) -> str:
    donde = f"{fix.latitude},{fix.longitude}" if coordenadas else "presente"
    return (
        f"{donde} nivel={fix.evidence_level} "
        f"+-{fix.accuracy_m}m @{fix.device_captured_at}"
    )


async def _companias(subdominio: str | None) -> list[Company]:
    async with async_session_maker() as session:
        consulta = select(Company).order_by(Company.id)
        if subdominio:
            consulta = consulta.where(Company.subdomain == subdominio)
        return list((await session.scalars(consulta)).all())


async def recientes(company_id: int, cuantos: int) -> None:
    """Los últimos viajes de una compañía con su estado de kilometraje."""
    async with async_session_maker() as session:
        filas = (
            await session.execute(
                select(
                    Trip.id,
                    Trip.status,
                    WorkSession.id,
                    WorkSession.session_date,
                    WorkSession.user_id,
                    TripMileage.state,
                    TripMileage.total_meters,
                    TripMileage.attempt_count,
                    TripMileage.terminal_reason,
                )
                .join(WorkSession, WorkSession.id == Trip.work_session_id)
                .outerjoin(TripMileage, TripMileage.trip_id == Trip.id)
                .where(Trip.company_id == company_id)
                .order_by(Trip.id.desc())
                .limit(cuantos)
            )
        ).all()

    if not filas:
        print("    (esta compania no tiene ningun viaje)")
        return

    print(
        f"    {'viaje':>7} {'jornada':>8} {'dia':>11} {'sup':>5} "
        f"{'estado viaje':>14} {'kilometraje':>19} {'millas':>8} {'int':>4} razon"
    )
    for (
        trip_id,
        estado,
        session_id,
        dia,
        user_id,
        km_estado,
        metros,
        intentos,
        razon,
    ) in filas:
        print(
            f"    {trip_id:>7} {session_id:>8} {str(dia):>11} {user_id:>5} "
            f"{estado:>14} {str(km_estado or 'SIN REGISTRO'):>19} "
            f"{_millas(metros):>8} {str(intentos if intentos is not None else '-'):>4} "
            f"{razon or ''}"
        )


async def pendientes(company_id: int) -> None:
    """Clasifica el atraso: qué espera reintento y qué espera evidencia."""
    ahora = datetime.now(timezone.utc)

    async with async_session_maker() as session:
        por_estado = (
            await session.execute(
                select(TripMileage.state, func.count())
                .where(TripMileage.company_id == company_id)
                .group_by(TripMileage.state)
                .order_by(TripMileage.state)
            )
        ).all()
        pendientes_ahora = (
            await session.execute(
                select(
                    TripMileage.trip_id,
                    TripMileage.attempt_count,
                    TripMileage.next_attempt_at,
                    TripMileage.last_error,
                )
                .where(
                    TripMileage.company_id == company_id,
                    TripMileage.state == "pending_calculation",
                )
                .order_by(TripMileage.trip_id)
            )
        ).all()

    print(f"    por estado: {dict(por_estado) or '(ninguno)'}")

    if not pendientes_ahora:
        print("    sin kilometrajes pendientes.")
        return

    print(f"    {len(pendientes_ahora)} pendientes:")
    for trip_id, intentos, proximo, error in pendientes_ahora:
        vencido = proximo is None or proximo <= ahora
        cuando = (
            "VENCIDO (el barrido debe recogerlo)"
            if vencido
            else f"espera hasta {proximo}"
        )
        print(f"      viaje {trip_id}: intentos={intentos} {cuando}")
        if error:
            print(f"        ultimo error: {error[:160]}")


async def traza(trip_id: int, *, coordenadas: bool) -> None:
    """La cadena completa que pide el cierre de campo, para un viaje concreto."""
    async with async_session_maker() as session:
        fila = (
            await session.execute(
                select(Trip, WorkSession, Company)
                .join(WorkSession, WorkSession.id == Trip.work_session_id)
                .join(Company, Company.id == Trip.company_id)
                .where(Trip.id == trip_id)
            )
        ).first()

    if fila is None:
        print(f"  No existe ningun viaje con id {trip_id}.")
        return

    viaje, jornada, compania = fila
    print(f"  tenant          : {compania.subdomain} (company_id={compania.id})")
    print(f"  supervisor      : user_id={jornada.user_id}")
    print(
        f"  jornada         : id={jornada.id} "
        f"session_date={jornada.session_date} estado={jornada.status}"
    )
    print(
        f"  viaje           : id={viaje.id} estado={viaje.status} "
        f"proposito={viaje.current_purpose}"
    )
    print(
        f"  marcas          : started={viaje.started_at} "
        f"arrived={viaje.arrived_at} ended={viaje.ended_at}"
    )

    async with async_session_maker() as session:
        fixes = (
            (
                await session.scalars(
                    select(LocationFix)
                    .where(
                        LocationFix.work_session_id == jornada.id,
                        LocationFix.subject_kind == "trip",
                        LocationFix.subject_id == viaje.id,
                    )
                    .order_by(LocationFix.device_captured_at)
                )
            )
            .all()
        )
        ausentes = (
            (
                await session.scalars(
                    select(MissingLocationEvent)
                    .where(MissingLocationEvent.trip_id == viaje.id)
                    .order_by(MissingLocationEvent.id)
                )
            )
            .all()
        )

    print(
        f"  evidencia       : {len(fixes)} fix(es), "
        f"{len(ausentes)} evento(s) sin ubicacion"
    )
    for fix in fixes:
        print(f"    - {fix.event_kind:<14} {_punto(fix, coordenadas=coordenadas)}")
    for evento in ausentes:
        print(
            f"    - {evento.event_kind:<14} SIN UBICACION "
            f"razon={evento.reason_code} intentos={evento.attempts}"
        )

    async with async_session_maker() as session:
        kilometraje = (
            await session.scalars(
                select(TripMileage).where(TripMileage.trip_id == viaje.id)
            )
        ).first()

    if kilometraje is None:
        print(
            "  kilometraje     : SIN REGISTRO (si el viaje llego a Arrived, "
            "esto es un defecto de disparador o persistencia)"
        )
        return

    print(f"  kilometraje     : id={kilometraje.id} estado={kilometraje.state}")
    print(
        f"    total_meters  : {kilometraje.total_meters} -> "
        f"{_millas(kilometraje.total_meters)} millas"
    )
    print(f"    calculated_at : {kilometraje.calculated_at}")
    print(f"    terminal      : {kilometraje.terminal_reason or '-'}")
    print(
        f"    intentos      : {kilometraje.attempt_count} "
        f"proximo={kilometraje.next_attempt_at}"
    )
    print(f"    ultimo error  : {kilometraje.last_error or '-'}")

    async with async_session_maker() as session:
        tramos = (
            await session.scalars(
                select(TripMileageSegment)
                .where(TripMileageSegment.trip_mileage_id == kilometraje.id)
                .order_by(TripMileageSegment.sequence)
            )
        ).all()

    print(f"    tramos        : {len(tramos)}")
    for tramo in tramos:
        print(
            f"      {tramo.sequence}. {tramo.from_event_kind} -> "
            f"{tramo.to_event_kind}  {tramo.distance_meters} m  "
            f"proveedor={tramo.provider}/{tramo.method}"
            f"/{tramo.provider_version or '-'}  "
            f"recta={tramo.haversine_meters} m"
        )


async def _principal() -> None:
    analizador = argparse.ArgumentParser(
        description="Traza el kilometraje de viajes reales. SOLO LECTURA.",
    )
    analizador.add_argument(
        "--company", help="subdominio del tenant; por omision, todos"
    )
    analizador.add_argument("--trip", type=int, help="traza completa de un viaje")
    analizador.add_argument(
        "--recent",
        type=int,
        default=0,
        help="lista los N viajes mas recientes de cada tenant",
    )
    analizador.add_argument(
        "--pending",
        action="store_true",
        help="clasifica el atraso de kilometrajes pendientes",
    )
    analizador.add_argument(
        "--coordenadas",
        action="store_true",
        help="imprime las coordenadas de los waypoints; esa salida ya no debe "
        "pegarse en un documento",
    )
    args = analizador.parse_args()

    print("Traza de kilometraje - SOLO LECTURA (no escribe nada)\n")

    if args.trip is not None:
        await traza(args.trip, coordenadas=args.coordenadas)
        return

    companias = await _companias(args.company)
    if not companias:
        print(f"  No hay ninguna compania con subdominio '{args.company}'.")
        return

    if not args.recent and not args.pending:
        args.recent = 20

    for compania in companias:
        print(f"  -- {compania.subdomain} (company_id={compania.id})")
        if args.recent:
            await recientes(compania.id, args.recent)
        if args.pending:
            await pendientes(compania.id)
        print()


if __name__ == "__main__":
    asyncio.run(_principal())
