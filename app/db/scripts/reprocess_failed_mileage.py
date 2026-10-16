"""Devuelve a la cola los kilometrajes que fallaron por culpa del motor.

Por qué hace falta un comando y no lo arregla el barrido
-------------------------------------------------------
`sweep_pending_mileage` sólo recoge `pending_calculation`. Un
`calculation_failed` es **terminal**: nadie lo vuelve a mirar. Es la decisión
correcta —un estado terminal que se reabriera solo no sería terminal— pero
significa que desplegar un motor de routing **no recupera** los viajes que
fallaron mientras no lo había.

Reabrir un hecho ya terminalizado es una decisión de negocio, no una corrección
técnica, y por eso vive en un comando explícito con rango de fechas en vez de
dentro de un trabajo de fondo.

Qué repone, y qué no
--------------------
Sólo las razones terminales que describen **al motor**:

* `routing_exhausted` — se agotaron los intentos sin respuesta utilizable.
* `implausible_segment` — el motor respondió algo que no superó la
  comprobación de plausibilidad.

**No** toca `start_waypoint_missing`, `arrival_waypoint_missing`,
`change_plan_waypoint_missing` ni `interrupted_without_arrival`: esas describen
la evidencia, no el proveedor, y ningún motor nuevo las arregla. Reponerlas
gastaría intentos para volver al mismo sitio.

Tampoco toca `not_calculable`, por la misma razón: ahí falta un waypoint.

Lo que escribe
--------------
Devuelve la fila a `pending_calculation` con el contador a cero y la cita para
ahora, y **limpia** `terminal_reason` —`ck_trip_mileage_terminal_needs_reason`
exige que un estado no terminal no la lleve—. `last_error` se conserva: dice
por qué se cayó la vez anterior y deja de ser cierto sólo cuando haya un
intento nuevo.

Cada fila repuesta deja su `audit_event`. Un cambio de estado hecho a mano que
no se audita es indistinguible de uno que no ocurrió.

Uso
---
    # Qué pasaría, sin escribir nada. Es el modo por defecto.
    uv run python -m app.db.scripts.reprocess_failed_mileage --company 1

    # Acotado por fecha de jornada, que es como se decide en la práctica.
    uv run python -m app.db.scripts.reprocess_failed_mileage \\
        --company 1 --desde 2026-09-01 --hasta 2026-09-30 --aplicar
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import select, update

from app.core.audit.service import record_event
from app.core.db.session import db_session, transaction
from app.routers_api.mileage.models import (
    MileageState,
    MileageTerminalReason,
    TripMileage,
)
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession

#: Las razones que un motor nuevo **sí** puede resolver.
REPONIBLES: tuple[str, ...] = (
    MileageTerminalReason.ROUTING_EXHAUSTED.value,
    MileageTerminalReason.IMPLAUSIBLE_SEGMENT.value,
)


def _consulta(company_id: int, desde: date | None, hasta: date | None):
    """Los kilometrajes candidatos, acotados por fecha de la jornada."""
    q = (
        select(TripMileage.id, TripMileage.trip_id, TripMileage.terminal_reason,
               TripMileage.attempt_count, WorkSession.session_date)
        .join(Trip, (Trip.id == TripMileage.trip_id)
              & (Trip.company_id == TripMileage.company_id))
        .join(WorkSession, (WorkSession.id == Trip.work_session_id)
              & (WorkSession.company_id == Trip.company_id))
        .where(
            TripMileage.company_id == company_id,
            TripMileage.state == MileageState.CALCULATION_FAILED.value,
            TripMileage.terminal_reason.in_(REPONIBLES),
        )
        .order_by(WorkSession.session_date, TripMileage.id)
    )
    if desde is not None:
        q = q.where(WorkSession.session_date >= desde)
    if hasta is not None:
        q = q.where(WorkSession.session_date <= hasta)
    return q


async def reprocesar(
    *,
    company_id: int,
    desde: date | None,
    hasta: date | None,
    aplicar: bool,
    actor_user_id: int | None = None,
) -> dict[str, int]:
    """Repone y devuelve el recuento. Sin `aplicar`, no escribe nada."""
    async with db_session() as sesion:
        candidatos = (
            await sesion.execute(_consulta(company_id, desde, hasta))
        ).all()

    resumen: dict[str, int] = {"candidatos": len(candidatos)}
    for fila in candidatos:
        resumen[fila.terminal_reason] = resumen.get(fila.terminal_reason, 0) + 1

    if not aplicar or not candidatos:
        return resumen

    ahora = datetime.now(timezone.utc)
    repuestos = 0
    for fila in candidatos:
        async with transaction() as sesion:
            # La condición de estado va en el WHERE, no en un `if` previo: si
            # otro proceso cambió la fila entre la lectura y ahora, esto no la
            # pisa y `rowcount` lo dice.
            resultado = await sesion.execute(
                update(TripMileage)
                .where(
                    TripMileage.id == fila.id,
                    TripMileage.company_id == company_id,
                    TripMileage.state == MileageState.CALCULATION_FAILED.value,
                )
                .values(
                    state=MileageState.PENDING_CALCULATION.value,
                    terminal_reason=None,
                    attempt_count=0,
                    next_attempt_at=ahora,
                    updated_at=ahora,
                )
            )
            if resultado.rowcount == 0:
                continue
        # La auditoria va **despues** de confirmar, como en el motor: su propia
        # transaccion. Si fallara, la fila ya esta repuesta y el barrido la
        # recoge igual; perder la traza seria peor que no reponerla, asi que se
        # deja que el error suba en vez de tragarlo.
        await record_event(
            company_id=company_id,
            entity_type="trip_mileage",
            entity_id=fila.id,
            action="requeued",
            actor_user_id=actor_user_id,
            summary=(
                f"Requeued after {fila.terminal_reason} "
                f"({fila.attempt_count} attempts)"
            ),
            changes={
                "state": {
                    "old": MileageState.CALCULATION_FAILED.value,
                    "new": MileageState.PENDING_CALCULATION.value,
                },
                "terminal_reason": {"old": fila.terminal_reason, "new": None},
            },
        )
        repuestos += 1

    resumen["repuestos"] = repuestos
    resumen["no_repuestos"] = len(candidatos) - repuestos
    return resumen


def _fecha(valor: str) -> date:
    return date.fromisoformat(valor)


async def _principal() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", type=int, required=True)
    parser.add_argument("--desde", type=_fecha, default=None,
                        help="Fecha de jornada mínima, inclusive (AAAA-MM-DD).")
    parser.add_argument("--hasta", type=_fecha, default=None,
                        help="Fecha de jornada máxima, inclusive (AAAA-MM-DD).")
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe. Sin esto sólo informa.")
    args = parser.parse_args()

    resumen = await reprocesar(
        company_id=args.company,
        desde=args.desde,
        hasta=args.hasta,
        aplicar=args.aplicar,
    )

    modo = "APLICADO" if args.aplicar else "SIMULACION (nada escrito)"
    print(f"\n{modo}  empresa={args.company} "
          f"desde={args.desde or '-'} hasta={args.hasta or '-'}")
    print(f"  candidatos: {resumen['candidatos']}")
    for razon in REPONIBLES:
        if razon in resumen:
            print(f"    {razon}: {resumen[razon]}")
    if args.aplicar:
        print(f"  repuestos: {resumen.get('repuestos', 0)}")
        if resumen.get("no_repuestos"):
            print(f"  no repuestos (cambiaron entre tanto): "
                  f"{resumen['no_repuestos']}")
        print("\nEl barrido los recogera en su proxima vuelta. "
              "Comprueba que el motor responde antes de esperar resultados.")
    elif resumen["candidatos"]:
        print("\nVuelve a ejecutarlo con --aplicar para reponerlos.")


if __name__ == "__main__":
    asyncio.run(_principal())
