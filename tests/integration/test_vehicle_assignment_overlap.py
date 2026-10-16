"""E5 de RTE06: dos asignaciones de vehículo nunca vigentes a la vez.

Por qué hace falta un caso concreto y no uno genérico
-----------------------------------------------------
Antes de la migración 0009 había tres protecciones —un índice único parcial y
dos comprobaciones en Python— y entre las tres cubrían los solapes *evidentes*.
Un test de solapamiento escrito "en general" pasaba con ellas y no demostraba
nada. El que las atravesaba es el primero de este archivo, y no necesita
concurrencia:

    existe:  [Mar 1 → Abr 1)   cerrada
    no hay:  ninguna abierta
    assign(effective_from = Feb 1)  →  insertaba [Feb 1 → ∞)

El 15 de marzo había entonces dos asignaciones aplicables y `effective_at()`
devolvía una de las dos según el plan de ejecución: el vehículo de una jornada
dejaba de ser determinista.

Lo que también se comprueba aquí
--------------------------------
Que la reasignación normal **siga funcionando**. La restricción usa el intervalo
semiabierto `[from, to)` justamente para eso: cerrar en `effective_to = desde` y
abrir en `effective_from = desde` se tocan sin solaparse. Con `[]` habría
empezado a fallar toda reasignación del producto, y ése es el modo de fallo que
más fácil se cuela al añadir una restricción de este tipo.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import async_session_maker


pytestmark = pytest.mark.integration


AHORA = datetime.now(timezone.utc)


async def _perfil_y_vehiculos(alpha_client, seeded, cuantos: int = 2):
    """Un perfil de supervisor y `cuantos` vehículos, sin asignar ninguno."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculos = []
    for i in range(cuantos):
        respuesta = await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota",
                "model": "Hilux",
                "year": 2024,
                "unit": f"OV-{i}",
                "fuel_grade": "regular",
                "operational_mpg": "24.00",
            },
        )
        assert respuesta.status_code in (200, 201), respuesta.text
        vehiculos.append(respuesta.json())
    return perfil, vehiculos


async def _asignar(alpha_client, perfil_id: int, vehicle_id: int, desde=None):
    cuerpo: dict = {"vehicle_id": vehicle_id}
    if desde is not None:
        cuerpo["effective_from"] = desde.isoformat()
    return await alpha_client.post(
        f"/api/supervisors/{perfil_id}/assignments", json=cuerpo
    )


async def _cerrar(alpha_client, assignment_id: int, hasta):
    return await alpha_client.post(
        f"/api/supervisors/assignments/{assignment_id}/end",
        json={"effective_to": hasta.isoformat()},
    )


async def _periodos(company_id: int, supervisor_profile_id: int) -> list[tuple]:
    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT effective_from, effective_to FROM vehicle_assignment "
                "WHERE company_id = :c AND supervisor_profile_id = :s "
                "ORDER BY effective_from"
            ),
            {"c": company_id, "s": supervisor_profile_id},
        )
        return [tuple(f) for f in filas]


# ── El caso que se colaba ───────────────────────────────────────────────────


async def test_a_start_date_before_a_closed_period_is_rejected(seeded, alpha_client):
    """E5: el solape que atravesaba las tres protecciones anteriores.

    Se deja un periodo **cerrado** en el futuro y ninguna asignación abierta, y
    luego se intenta abrir una que empieza **antes** de ese periodo. La nueva
    sería `[desde, ∞)`, así que se come el periodo cerrado entero.

    Ninguna de las protecciones anteriores lo veía: el índice parcial porque
    ninguna de las dos filas tiene `effective_to IS NULL`, y la comprobación en
    Python porque buscaba un periodo que *contuviera* la fecha de inicio nueva,
    no uno que empezara después.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)

    # Un periodo cerrado: [+30d, +60d).
    alta = await _asignar(
        alpha_client, perfil["id"], vehiculos[0]["id"], AHORA + timedelta(days=30)
    )
    assert alta.status_code in (200, 201), alta.text
    cierre = await _cerrar(alpha_client, alta.json()["id"], AHORA + timedelta(days=60))
    assert cierre.status_code in (200, 201, 204), cierre.text

    # Y ahora una abierta que empieza antes: [+10d, ∞).
    solapada = await _asignar(
        alpha_client, perfil["id"], vehiculos[1]["id"], AHORA + timedelta(days=10)
    )

    assert solapada.status_code == 409, solapada.text
    assert "overlaps" in solapada.json()["detail"].lower(), solapada.json()

    # Y no se escribió nada: sigue habiendo un solo periodo.
    assert len(await _periodos(seeded.alpha.id, perfil["id"])) == 1


async def test_a_start_date_inside_a_closed_period_is_rejected(seeded, alpha_client):
    """El caso que la comprobación en Python sí cubría. Sigue cubierto.

    Está aquí porque borrar `overlaps_existing()` no puede aflojar nada: lo que
    antes rechazaba Python lo rechaza ahora la base, y con el mismo código HTTP.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)

    alta = await _asignar(
        alpha_client, perfil["id"], vehiculos[0]["id"], AHORA + timedelta(days=10)
    )
    assert alta.status_code in (200, 201), alta.text
    await _cerrar(alpha_client, alta.json()["id"], AHORA + timedelta(days=40))

    # Dentro del periodo cerrado.
    dentro = await _asignar(
        alpha_client, perfil["id"], vehiculos[1]["id"], AHORA + timedelta(days=20)
    )
    assert dentro.status_code == 409, dentro.text
    assert len(await _periodos(seeded.alpha.id, perfil["id"])) == 1


# ── Lo que no se puede romper al añadir la restricción ──────────────────────


async def test_a_normal_reassignment_still_works(seeded, alpha_client):
    """Cerrar en `desde` y abrir en `desde` se tocan, no solapan.

    Es la operación más común del módulo y la que una restricción mal escrita
    —con el intervalo cerrado `[]` en vez de `[)`— habría roto de inmediato. El
    borde exacto es lo que se mide: las dos filas comparten el instante.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)

    primera = await _asignar(alpha_client, perfil["id"], vehiculos[0]["id"])
    assert primera.status_code in (200, 201), primera.text

    # Sin `effective_from`: el servidor pone su reloj, cierra la anterior en ese
    # mismo instante y abre la nueva ahí.
    segunda = await _asignar(alpha_client, perfil["id"], vehiculos[1]["id"])
    assert segunda.status_code in (200, 201), segunda.text

    periodos = await _periodos(seeded.alpha.id, perfil["id"])
    assert len(periodos) == 2, periodos
    cerrada, abierta = periodos
    assert cerrada[1] is not None, "la primera tiene que quedar cerrada"
    assert abierta[1] is None, "la segunda tiene que quedar abierta"
    assert cerrada[1] == abierta[0], (
        "el cierre y la apertura comparten instante: es el borde que `[)` permite"
    )


async def test_consecutive_closed_periods_that_touch_are_allowed(seeded, alpha_client):
    """Dos periodos cerrados pegados tampoco solapan.

    El mismo borde que el anterior, pero sin ninguna asignación abierta, para
    que la prueba no dependa del índice parcial.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)
    corte = AHORA + timedelta(days=20)

    primera = await _asignar(
        alpha_client, perfil["id"], vehiculos[0]["id"], AHORA + timedelta(days=10)
    )
    await _cerrar(alpha_client, primera.json()["id"], corte)

    segunda = await _asignar(alpha_client, perfil["id"], vehiculos[1]["id"], corte)
    assert segunda.status_code in (200, 201), segunda.text
    cierre = await _cerrar(
        alpha_client, segunda.json()["id"], AHORA + timedelta(days=30)
    )
    assert cierre.status_code in (200, 201, 204), cierre.text

    assert len(await _periodos(seeded.alpha.id, perfil["id"])) == 2


async def test_a_future_assignment_after_an_open_one_is_still_rejected(
    seeded, alpha_client,
):
    """Una abierta `[t, ∞)` se come cualquier periodo posterior.

    Y por eso reasignar con fecha futura **cierra** la anterior en esa fecha en
    vez de dejar las dos: el caso se comprueba aquí porque es el que hace que la
    restricción y la lógica de `assign()` tengan que estar de acuerdo.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)

    abierta = await _asignar(alpha_client, perfil["id"], vehiculos[0]["id"])
    assert abierta.status_code in (200, 201), abierta.text

    futura = await _asignar(
        alpha_client, perfil["id"], vehiculos[1]["id"], AHORA + timedelta(days=15)
    )
    assert futura.status_code in (200, 201), futura.text

    periodos = await _periodos(seeded.alpha.id, perfil["id"])
    assert len(periodos) == 2, periodos
    assert periodos[0][1] == periodos[1][0], (
        "la abierta se cerró en la fecha de la nueva, en vez de solaparse"
    )


# ── La base, no el servicio ─────────────────────────────────────────────────


async def test_the_database_rejects_an_overlap_written_directly(seeded, alpha_client):
    """El invariante es de la base, así que se comprueba sin pasar por la API.

    Es la diferencia entre la protección anterior y ésta. `overlaps_existing()`
    vivía en Python: cualquier camino que no lo llamara —un script, una
    corrección manual, un módulo futuro— podía escribir el solape. Con la
    restricción, el `INSERT` directo tampoco puede (invariante 6).

    La fila que se intenta insertar va **cerrada** a propósito. Con
    `effective_to = NULL` chocaría primero contra `uq_vehicle_assignment_current`
    y el test pasaría sin haber ejercitado nunca la restricción nueva — que es
    exactamente lo que me ocurrió al escribirlo la primera vez.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)
    alta = await _asignar(alpha_client, perfil["id"], vehiculos[0]["id"])
    assert alta.status_code in (200, 201), alta.text

    async with async_session_maker() as session:
        with pytest.raises(IntegrityError) as fallo:
            await session.execute(
                text(
                    "INSERT INTO vehicle_assignment "
                    "(company_id, supervisor_profile_id, vehicle_id, "
                    " effective_from, effective_to, created_at, updated_at) "
                    "VALUES (:c, :s, :v, :f, :t, now(), now())"
                ),
                {
                    "c": seeded.alpha.id,
                    "s": perfil["id"],
                    "v": vehiculos[1]["id"],
                    "f": AHORA + timedelta(days=5),
                    "t": AHORA + timedelta(days=10),
                },
            )
            await session.commit()

    # `23P01` es exclusion_violation: la restricción nueva, no el índice parcial.
    assert fallo.value.orig.sqlstate == "23P01", str(fallo.value)
    assert "ex_vehicle_assignment_no_overlap" in str(fallo.value)


async def test_two_simultaneous_assignments_produce_one(seeded, alpha_client):
    """Concurrencia real: la restricción no tiene ventana que aprovechar.

    La comprobación que se ha borrado leía **fuera** de la transacción, así que
    dos peticiones a la vez pasaban las dos y dependían del índice parcial para
    no duplicar. Ahora es la restricción la que decide, y decide una sola vez.
    """
    perfil, vehiculos = await _perfil_y_vehiculos(alpha_client, seeded)
    desde = AHORA + timedelta(days=5)

    a, b = await asyncio.gather(
        _asignar(alpha_client, perfil["id"], vehiculos[0]["id"], desde),
        _asignar(alpha_client, perfil["id"], vehiculos[1]["id"], desde),
        return_exceptions=True,
    )
    codigos = [r.status_code for r in (a, b) if not isinstance(r, BaseException)]
    assert sum(1 for c in codigos if c in (200, 201)) == 1, codigos
    assert len(await _periodos(seeded.alpha.id, perfil["id"])) == 1


# ── Aislamiento entre compañías ─────────────────────────────────────────────


async def test_the_constraint_is_scoped_per_company(seeded, alpha_client, beta_client):
    """La restricción lleva `company_id`: un tenant no limita al otro.

    Parece obvio y es exactamente la clase de detalle que se olvida al escribir
    un `EXCLUDE`. Sin `company_id WITH =` en la restricción, la asignación de
    una compañía habría bloqueado la de otra.
    """
    perfil_a, vehiculos_a = await _perfil_y_vehiculos(alpha_client, seeded)
    alta_a = await _asignar(alpha_client, perfil_a["id"], vehiculos_a[0]["id"])
    assert alta_a.status_code in (200, 201), alta_a.text

    await beta_client.login(seeded.beta.users["route_admin"].email)
    perfil_b = (
        await beta_client.post(
            "/api/supervisors", json={"user_id": seeded.beta.users["supervisor"].id}
        )
    ).json()
    vehiculo_b = (
        await beta_client.post(
            "/api/vehicles",
            json={
                "make": "Ford", "model": "Ranger", "year": 2024, "unit": "OV-B",
                "fuel_grade": "regular", "operational_mpg": "22.00",
            },
        )
    ).json()
    alta_b = await _asignar(beta_client, perfil_b["id"], vehiculo_b["id"])

    assert alta_b.status_code in (200, 201), alta_b.text
