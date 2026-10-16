"""La reposición de kilometrajes que fallaron por culpa del motor.

Lo que está en juego
--------------------
`sweep_pending_mileage` sólo recoge `pending_calculation`, así que un
`calculation_failed` no se reintenta nunca. Desplegar un motor de routing no
recupera lo que falló mientras no lo había, y por eso existe el comando.

Reabrir hechos terminalizados es peligroso de dos maneras opuestas, y los tests
cubren las dos: reponer **de menos** deja viajes sin kilometraje para siempre;
reponer **de más** gasta intentos en viajes a los que les falta un waypoint y
que ningún motor puede resolver.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.database import async_session_maker
from app.db.scripts.reprocess_failed_mileage import REPONIBLES, reprocesar
from app.routers_api.mileage.models import MileageState, TripMileage

pytestmark = pytest.mark.integration


async def _sembrar(company_id: int, user_id: int, casos):
    """Una jornada con un viaje por caso. Devuelve {razon_o_estado: mileage_id}."""
    creados: dict[str, int] = {}
    async with async_session_maker() as s:
        ws = await s.scalar(text(
            "INSERT INTO work_session(company_id,user_id,status,session_date,"
            "started_at,started_received_at,started_at_source,created_at,"
            "updated_at,version) VALUES (:c,:u,'ended',DATE '2026-09-15',"
            " now()-interval '9 hours', now()-interval '9 hours','device',"
            " now(),now(),1) RETURNING id"), {"c": company_id, "u": user_id})
        for n, (estado, razon) in enumerate(casos, start=1):
            trip = await s.scalar(text(
                "INSERT INTO trip(company_id,work_session_id,sequence,status,"
                "original_purpose,current_purpose,started_at,started_received_at,"
                "arrived_at,arrived_received_at,created_at,updated_at,version) "
                "VALUES (:c,:w,:s,'closed','client_visit','client_visit',"
                " now()-interval '8 hours', now()-interval '8 hours',"
                " now()-interval '7 hours', now()-interval '7 hours',"
                " now(),now(),1) RETURNING id"),
                {"c": company_id, "w": ws, "s": n})
            km = await s.scalar(text(
                "INSERT INTO trip_mileage(company_id,trip_id,state,"
                "terminal_reason,last_error,attempt_count,created_at,updated_at) "
                "VALUES (:c,:t,:e,:r,'engine said no',5,now(),now()) RETURNING id"),
                {"c": company_id, "t": trip, "e": estado, "r": razon})
            creados[razon or estado] = km
        await s.commit()
    return ws, creados


async def _estado(mileage_id: int) -> TripMileage:
    async with async_session_maker() as s:
        return await s.scalar(
            select(TripMileage).where(TripMileage.id == mileage_id)
        )


@pytest.mark.asyncio
async def test_repone_solo_lo_que_el_motor_puede_resolver(seeded) -> None:
    """Las razones de motor sí; las de evidencia que falta, no."""
    empresa = seeded.alpha
    usuario = next(iter(empresa.users.values()))
    _ws, ids = await _sembrar(empresa.id, usuario.id, [
        ("calculation_failed", "routing_exhausted"),
        ("calculation_failed", "implausible_segment"),
        # Le falta un waypoint: ningún motor nuevo lo arregla.
        ("calculation_failed", "start_waypoint_missing"),
        ("not_calculable", "arrival_waypoint_missing"),
    ])

    resumen = await reprocesar(
        company_id=empresa.id, desde=None, hasta=None, aplicar=True
    )

    assert resumen["candidatos"] == 2
    assert resumen["repuestos"] == 2

    for razon in REPONIBLES:
        km = await _estado(ids[razon])
        assert km.state == MileageState.PENDING_CALCULATION.value
        # `ck_trip_mileage_terminal_needs_reason` exige que un estado no
        # terminal no lleve razon: si esto no se limpiara, el UPDATE fallaria.
        assert km.terminal_reason is None
        assert km.attempt_count == 0
        assert km.next_attempt_at is not None
        # El error anterior se conserva: dice por que se cayo la vez pasada.
        assert km.last_error == "engine said no"

    # Los otros dos siguen intactos.
    sigue_fallido = await _estado(ids["start_waypoint_missing"])
    assert sigue_fallido.state == MileageState.CALCULATION_FAILED.value
    assert sigue_fallido.terminal_reason == "start_waypoint_missing"

    sigue_no_calculable = await _estado(ids["arrival_waypoint_missing"])
    assert sigue_no_calculable.state == MileageState.NOT_CALCULABLE.value


@pytest.mark.asyncio
async def test_sin_aplicar_no_escribe_nada(seeded) -> None:
    """El modo por defecto informa y no toca la base."""
    empresa = seeded.alpha
    usuario = next(iter(empresa.users.values()))
    _ws, ids = await _sembrar(empresa.id, usuario.id, [
        ("calculation_failed", "routing_exhausted"),
    ])

    resumen = await reprocesar(
        company_id=empresa.id, desde=None, hasta=None, aplicar=False
    )

    assert resumen["candidatos"] == 1
    assert "repuestos" not in resumen

    km = await _estado(ids["routing_exhausted"])
    assert km.state == MileageState.CALCULATION_FAILED.value
    assert km.terminal_reason == "routing_exhausted"


@pytest.mark.asyncio
async def test_el_rango_de_fechas_acota(seeded) -> None:
    """La jornada sembrada es del 15; un rango que no la cubre no la toca."""
    empresa = seeded.alpha
    usuario = next(iter(empresa.users.values()))
    _ws, ids = await _sembrar(empresa.id, usuario.id, [
        ("calculation_failed", "routing_exhausted"),
    ])

    from datetime import date

    fuera = await reprocesar(
        company_id=empresa.id, desde=date(2026, 10, 1), hasta=date(2026, 10, 31),
        aplicar=True,
    )
    assert fuera["candidatos"] == 0
    assert (await _estado(ids["routing_exhausted"])).state == (
        MileageState.CALCULATION_FAILED.value
    )

    dentro = await reprocesar(
        company_id=empresa.id, desde=date(2026, 9, 1), hasta=date(2026, 9, 30),
        aplicar=True,
    )
    assert dentro["repuestos"] == 1


@pytest.mark.asyncio
async def test_no_cruza_de_empresa(seeded) -> None:
    """Un reproceso de alpha no puede tocar las filas de beta."""
    usuario_beta = next(iter(seeded.beta.users.values()))
    _ws, ids = await _sembrar(seeded.beta.id, usuario_beta.id, [
        ("calculation_failed", "routing_exhausted"),
    ])

    resumen = await reprocesar(
        company_id=seeded.alpha.id, desde=None, hasta=None, aplicar=True
    )

    assert resumen["candidatos"] == 0
    assert (await _estado(ids["routing_exhausted"])).state == (
        MileageState.CALCULATION_FAILED.value
    )


@pytest.mark.asyncio
async def test_deja_traza_de_auditoria(seeded) -> None:
    """Un cambio de estado a mano sin auditar es indistinguible de uno que no ocurrió."""
    empresa = seeded.alpha
    usuario = next(iter(empresa.users.values()))
    _ws, ids = await _sembrar(empresa.id, usuario.id, [
        ("calculation_failed", "routing_exhausted"),
    ])

    await reprocesar(company_id=empresa.id, desde=None, hasta=None, aplicar=True)

    async with async_session_maker() as s:
        filas = (await s.execute(text(
            "SELECT action, summary, changes FROM audit_event "
            "WHERE company_id = :c AND entity_type = 'trip_mileage' "
            "  AND entity_id = :i"),
            {"c": empresa.id, "i": ids["routing_exhausted"]})).all()

    assert len(filas) == 1
    accion, resumen_texto, cambios = filas[0]
    assert accion == "requeued"
    assert "routing_exhausted" in resumen_texto
    assert cambios["state"]["old"] == "calculation_failed"
    assert cambios["state"]["new"] == "pending_calculation"
