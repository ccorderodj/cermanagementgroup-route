"""Correlación exacta de la evidencia capturada sin red (RTE06 cierre final).

Qué hueco fija esto
-------------------
La correlación de §14 es un id **que crea el servidor**, así que una acción
encolada sin red no tenía a qué atar su punto. El cierre anterior lo resolvía
difiriendo el sujeto y **negándose a atar cuando había dos acciones del mismo
tipo pendientes** — veraz, pero convertía puntos válidos en Missing por
ambigüedad. CER lo marcó `NOT IMPLEMENTED / GAP`.

La cadena ahora es completa:

    clave de acción del cliente
      → cabecera `Idempotency-Key`
      → `client_action_key` en la fila que la acción crea
      → `location_fix.subject_id`

Estos tests recorren la cadena por el lado del servidor: mandan la clave que un
cliente offline habría guardado y comprueban que el punto acaba en la fila
correcta, incluso con dos acciones del mismo tipo.

Por qué aquí y no sólo en navegador
------------------------------------
El navegador prueba que el cliente **guarda y reenvía**; eso está en
`test_rte06_offline_durability_browser.py`. Lo que se prueba aquí es lo que el
navegador no puede aislar: que dos claves distintas resuelvan a dos filas
distintas, que una clave ajena no resuelva nada, y que un reenvío no duplique.
Son propiedades del servidor y se comprueban contra la base.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import async_session_maker

pytestmark = pytest.mark.integration


AHORA = datetime.now(timezone.utc)

#: Puntos próximos: la plausibilidad geométrica rechaza distancias imposibles y
#: estos tests no quieren pelearse con ella.
P0 = ("40.712800", "-74.0060000")
P1 = ("40.722800", "-74.0100000")
P2 = ("40.732800", "-74.0140000")


def _clave(prefijo: str) -> str:
    """Una clave de acción como la que genera el cliente."""
    return f"{prefijo}-0000-0000-0000-000000000000"[:64]


async def _filas(consulta: str, params: dict) -> list[dict]:
    async with async_session_maker() as sesion:
        filas = await sesion.execute(text(consulta), params)
        return [dict(f._mapping) for f in filas]


async def _punto_por_clave(
    cliente, *, event_kind: str, clave: str, coord, hace: int = 60, nivel="fresh"
):
    lat, lon = coord
    cuerpo = {
        "event_kind": event_kind,
        "client_action_key": clave,
        "evidence_level": nivel,
        "latitude": lat,
        "longitude": lon,
        "accuracy_m": "10.00",
        "device_captured_at": (AHORA - timedelta(minutes=hace)).isoformat(),
    }
    if nivel == "degraded_cached":
        cuerpo["source_age_seconds"] = 120
    return await cliente.post("/api/location/evidence", json=cuerpo)


# ── O1: Start Work sin red ──────────────────────────────────────────────────


async def test_o1_start_work_offline_binds_to_that_work_session(
    seeded, alpha_client
):
    """O1: la jornada se crea con la clave y el punto se ata a **ella**.

    Es el caso que antes no podía funcionar: cuando el punto se mide, la jornada
    no tiene `id`. Ahora la clave viaja en la cabecera, el servidor la guarda en
    la fila, y el punto la nombra.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    clave = _clave("sw")

    jornada = await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )
    assert jornada.status_code in (200, 201), jornada.text
    jornada_id = jornada.json()["id"]

    # La clave quedó en la fila. Es el eslabón que faltaba.
    guardada = await _filas(
        "SELECT client_action_key FROM work_session WHERE id = :i", {"i": jornada_id}
    )
    assert guardada[0]["client_action_key"] == clave

    respuesta = await _punto_por_clave(
        alpha_client, event_kind="start_work", clave=clave, coord=P0, hace=5
    )
    assert respuesta.status_code == 201, respuesta.text

    puntos = await _filas(
        "SELECT event_kind, subject_kind, subject_id FROM location_fix "
        "WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(puntos) == 1
    assert puntos[0]["subject_kind"] == "work_session"
    assert puntos[0]["subject_id"] == jornada_id, (
        "el punto se ató a la jornada que creó esa acción, no a la que hubiera"
    )


# ── O2: Start Trip sin red ──────────────────────────────────────────────────


async def test_o2_start_trip_offline_binds_to_that_trip(seeded, alpha_client):
    """O2: **un Start Trip real**, no un Start Work como sustituto.

    La clave que identifica el viaje es la de la acción que lo **crea** —el
    plan—, no la de arrancarlo: es la fila del viaje la que lleva la columna, y
    el waypoint de salida pertenece al viaje.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    clave = _clave("st")
    viaje = await alpha_client.post(
        "/api/trips",
        json={"purpose": "other", "context_reference": "Sin red"},
        headers={"Idempotency-Key": clave},
    )
    assert viaje.status_code in (200, 201), viaje.text
    viaje_id = viaje.json()["id"]
    await alpha_client.post(f"/api/trips/{viaje_id}/start", json={})

    respuesta = await _punto_por_clave(
        alpha_client, event_kind="start_trip", clave=clave, coord=P0, hace=120
    )
    assert respuesta.status_code == 201, respuesta.text

    puntos = await _filas(
        "SELECT event_kind, subject_kind, subject_id FROM location_fix "
        "WHERE company_id = :c AND event_kind = 'start_trip'",
        {"c": seeded.alpha.id},
    )
    assert len(puntos) == 1
    assert puntos[0]["subject_kind"] == "trip"
    assert puntos[0]["subject_id"] == viaje_id


# ── O3: varias acciones offline que crean viajes ───────────────────────────


async def test_o3_two_offline_trips_keep_their_points_apart(seeded, alpha_client):
    """O3: **el caso que antes no se podía resolver.**

    Dos viajes creados con dos claves, dos puntos. Antes, dos `start_trip`
    pendientes hacían el mapeo indemostrable y ninguno se ataba: los dos podían
    acabar en Missing. Ahora cada punto nombra su acción y no hay nada que
    deducir.

    El ciclo de vida no permite dos viajes vivos a la vez, así que el escenario
    válido más fuerte que el producto admite es secuencial: crear, salir,
    llegar, cerrar la parada, y crear el siguiente. Los dos viajes existen, los
    dos tienen su clave, y sus puntos llegan **después** y desordenados — que es
    lo que produce una cola vaciándose tras un corte largo.
    """
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    async with async_session_maker() as sesion:
        await provision_standard_values(sesion, company_id=seeded.alpha.id)
        await sesion.commit()

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    async def _valor(list_code: str, etiqueta: str) -> int:
        valores = (await alpha_client.get(f"/api/standard-values/{list_code}")).json()
        for v in valores:
            if v["label"] == etiqueta:
                return v["id"]
        raise AssertionError(etiqueta)

    actividad = await _valor("other_activities", "Housing Visit")
    resultado = await _valor("outcomes", "Completed")

    viajes: list[tuple[str, int]] = []
    for indice in range(2):
        clave = _clave(f"t{indice}")
        creado = await alpha_client.post(
            "/api/trips",
            json={"purpose": "other", "context_reference": f"Viaje {indice}"},
            headers={"Idempotency-Key": clave},
        )
        assert creado.status_code in (200, 201), creado.text
        viaje_id = creado.json()["id"]
        viajes.append((clave, viaje_id))

        await alpha_client.post(f"/api/trips/{viaje_id}/start", json={})
        await alpha_client.post(f"/api/trips/{viaje_id}/arrive", json={})
        # Cerrar la parada: nada se cierra solo, y sin cerrarla el siguiente
        # `POST /api/trips` devolvería este mismo viaje.
        await alpha_client.post(
            f"/api/trips/{viaje_id}/activity/start",
            json={"activity_ids": [actividad]},
        )
        await alpha_client.post(
            f"/api/trips/{viaje_id}/activity/complete",
            json={"action": "complete", "outcome_id": resultado},
        )

    assert viajes[0][1] != viajes[1][1]

    # Los puntos llegan ahora, y **al revés**: el segundo viaje primero.
    for (clave, _), coord in zip(reversed(viajes), (P1, P0)):
        respuesta = await _punto_por_clave(
            alpha_client, event_kind="start_trip", clave=clave, coord=coord, hace=300
        )
        assert respuesta.status_code == 201, respuesta.text

    puntos = await _filas(
        "SELECT subject_id FROM location_fix "
        "WHERE company_id = :c AND event_kind = 'start_trip' ORDER BY subject_id",
        {"c": seeded.alpha.id},
    )
    assert [p["subject_id"] for p in puntos] == sorted(v[1] for v in viajes), (
        "punto A -> evento A, punto B -> evento B, sin adivinar"
    )
    # Y ninguno acabó en Missing por ambigüedad.
    assert await _filas(
        "SELECT id FROM missing_location_event WHERE company_id = :c "
        "AND event_kind = 'start_trip'",
        {"c": seeded.alpha.id},
    ) == []


# ── O4 y O5: Change Plan ────────────────────────────────────────────────────


async def test_o4_change_plan_offline_binds_to_that_purpose_change(
    seeded, alpha_client
):
    """O4: el punto se ata a **esa** fila de cambio de plan.

    Change Plan pasa por la cola desde este cierre, así que ya tiene clave. Sin
    ella había que leer el historial para saber a qué atar el punto, y sin red
    ese historial no existía todavía.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "other", "context_reference": "Base"}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    clave = _clave("cp")
    cambio = await alpha_client.post(
        f"/api/trips/{viaje['id']}/change-plan",
        json={"purpose": "other", "context_reference": "Desvío"},
        headers={"Idempotency-Key": clave},
    )
    assert cambio.status_code in (200, 201), cambio.text

    filas = await _filas(
        "SELECT id, client_action_key FROM trip_purpose_change "
        "WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 1
    assert filas[0]["client_action_key"] == clave
    cambio_id = filas[0]["id"]

    respuesta = await _punto_por_clave(
        alpha_client, event_kind="change_plan", clave=clave, coord=P1, hace=90
    )
    assert respuesta.status_code == 201, respuesta.text

    puntos = await _filas(
        "SELECT subject_kind, subject_id FROM location_fix "
        "WHERE company_id = :c AND event_kind = 'change_plan'",
        {"c": seeded.alpha.id},
    )
    assert puntos == [{"subject_kind": "trip_purpose_change", "subject_id": cambio_id}]


async def test_o5_two_change_plans_keep_their_points_and_their_order(
    seeded, alpha_client
):
    """O5: dos cambios, dos puntos, y el orden es el de **ocurrencia**.

    Los puntos se envían al revés a propósito. El orden que importa sale de
    `changed_at`, no del orden de subida, y eso es lo que la última aserción
    comprueba.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "other", "context_reference": "Base"}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    claves = [_clave("cpa"), _clave("cpb")]
    for indice, clave in enumerate(claves):
        respuesta = await alpha_client.post(
            f"/api/trips/{viaje['id']}/change-plan",
            json={"purpose": "other", "context_reference": f"Cambio {indice}"},
            headers={"Idempotency-Key": clave},
        )
        assert respuesta.status_code in (200, 201), respuesta.text

    filas = await _filas(
        "SELECT id, client_action_key, changed_at FROM trip_purpose_change "
        "WHERE company_id = :c ORDER BY changed_at, id",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 2
    por_clave = {f["client_action_key"]: f["id"] for f in filas}
    assert set(por_clave) == set(claves)

    # Al revés, y con horas de captura que **no** siguen el orden de subida.
    for clave, coord, hace in zip(reversed(claves), (P2, P1), (120, 180)):
        respuesta = await _punto_por_clave(
            alpha_client, event_kind="change_plan", clave=clave, coord=coord, hace=hace
        )
        assert respuesta.status_code == 201, respuesta.text

    puntos = await _filas(
        "SELECT f.subject_id FROM location_fix f "
        "JOIN trip_purpose_change c ON c.id = f.subject_id "
        "WHERE f.company_id = :c AND f.event_kind = 'change_plan' "
        "ORDER BY c.changed_at, c.id",
        {"c": seeded.alpha.id},
    )
    assert [p["subject_id"] for p in puntos] == [f["id"] for f in filas], (
        "el orden es el de ocurrencia del dominio, no el de subida"
    )


# ── O8: reenvío ─────────────────────────────────────────────────────────────


async def test_o8_replay_creates_one_event_and_one_point(seeded, alpha_client):
    """O8: la misma acción y el mismo punto reenviados → uno de cada.

    Dos garantías distintas y las dos hacen falta: la idempotencia de la acción
    la da `Idempotency-Key`, y la del punto el índice único de la correlación.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    clave = _clave("rp")

    primera = await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )
    segunda = await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )
    assert primera.status_code in (200, 201), primera.text
    assert segunda.status_code in (200, 201), segunda.text
    assert len(
        await _filas(
            "SELECT id FROM work_session WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    ) == 1

    for _ in range(2):
        respuesta = await _punto_por_clave(
            alpha_client, event_kind="start_work", clave=clave, coord=P0, hace=5
        )
        assert respuesta.status_code == 201, respuesta.text

    assert len(
        await _filas(
            "SELECT id FROM location_fix WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    ) == 1


async def test_a_replay_cannot_replace_an_accepted_point(seeded, alpha_client):
    """§5.10: un punto aceptado no lo sustituye un reenvío posterior.

    Se manda el mismo evento con **otras** coordenadas. El primero manda: es el
    que se midió más cerca del evento.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    clave = _clave("nr")
    await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )

    await _punto_por_clave(
        alpha_client, event_kind="start_work", clave=clave, coord=P0, hace=5
    )
    segundo = await _punto_por_clave(
        alpha_client, event_kind="start_work", clave=clave, coord=P2, hace=1
    )
    assert segundo.status_code == 201
    assert segundo.json()["replayed"] is True

    filas = await _filas(
        "SELECT latitude FROM location_fix WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 1
    assert str(filas[0]["latitude"]) == P0[0], "el primero manda"


# ── O9: nivel y hora se conservan ───────────────────────────────────────────


async def test_o9_delayed_cached_evidence_keeps_level_and_timestamp(
    seeded, alpha_client
):
    """O9: subirse tarde no cambia el nivel ni la hora de captura.

    Se manda un punto `degraded_cached` medido hace una hora. El servidor
    conserva las dos cosas y pone **su** reloj sólo en `server_received_at`.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    clave = _clave("dc")
    await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )
    medido = AHORA - timedelta(minutes=60)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json={
            "event_kind": "start_work",
            "client_action_key": clave,
            "evidence_level": "degraded_cached",
            "latitude": P0[0],
            "longitude": P0[1],
            "accuracy_m": "80.00",
            "source_age_seconds": 120,
            "device_captured_at": medido.isoformat(),
        },
    )
    assert respuesta.status_code == 201, respuesta.text

    fila = (
        await _filas(
            "SELECT evidence_level, source_age_seconds, device_captured_at, "
            "server_received_at FROM location_fix WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert fila["evidence_level"] == "degraded_cached"
    assert fila["source_age_seconds"] == 120
    assert abs((fila["device_captured_at"] - medido).total_seconds()) < 2
    assert fila["server_received_at"] > fila["device_captured_at"]


# ── O10: Missing sigue siendo veraz ────────────────────────────────────────


async def test_o10_missing_still_requires_a_real_acquisition_failure(
    seeded, alpha_client
):
    """O10: un punto válido no se convierte en Missing, y un Missing sigue siendo
    posible cuando la adquisición falló de verdad.

    Las dos mitades. La primera es lo que este cierre arregla: ya no hay
    ambigüedad que pueda perder un punto. La segunda es que el camino de Missing
    sigue existiendo para su caso real.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    clave = _clave("ms")
    await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )

    # El punto llega y se acepta: nada lo convierte en Missing.
    assert (
        await _punto_por_clave(
            alpha_client, event_kind="start_work", clave=clave, coord=P0, hace=5
        )
    ).status_code == 201
    assert await _filas(
        "SELECT id FROM missing_location_event WHERE company_id = :c",
        {"c": seeded.alpha.id},
    ) == []

    # Y para otro evento cuya adquisición sí falló, el Missing se crea.
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "other", "context_reference": "X"}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    perdido = await alpha_client.post(
        "/api/location/missing",
        json={
            "event_kind": "arrived",
            "subject_id": viaje["id"],
            "reason_code": "permission_denied",
        },
    )
    assert perdido.status_code == 201, perdido.text


# ── §12: la clave es identificador, no autoridad ───────────────────────────


async def test_an_action_key_from_another_tenant_resolves_to_nothing(
    seeded, alpha_client, beta_client
):
    """La clave de otro tenant no encuentra fila. **404, no 403.**

    Es la garantía de §12: resolver por clave no concede nada. La consulta
    filtra por `company_id`, así que una clave ajena es indistinguible de una
    inexistente — y eso es lo correcto: no se confirma que exista.
    """
    await beta_client.login(seeded.beta.users["supervisor"].email)
    clave_beta = _clave("bt")
    creada = await beta_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave_beta}
    )
    assert creada.status_code in (200, 201), creada.text

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    respuesta = await _punto_por_clave(
        alpha_client, event_kind="start_work", clave=clave_beta, coord=P0, hace=5
    )
    assert respuesta.status_code == 404, respuesta.text
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


async def test_an_unknown_action_key_is_not_found(seeded, alpha_client):
    """Una clave inventada no ata nada."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    respuesta = await _punto_por_clave(
        alpha_client, event_kind="start_work", clave=_clave("xx"), coord=P0, hace=5
    )
    assert respuesta.status_code == 404, respuesta.text


@pytest.mark.parametrize(
    "extra,caso",
    [
        ({}, "ninguna"),
        ({"subject_id": 1, "client_action_key": _clave("zz")}, "las dos"),
    ],
    ids=["ninguna", "las-dos"],
)
async def test_the_subject_must_be_identified_exactly_once(
    seeded, alpha_client, extra, caso
):
    """Ni ninguna forma de identificar el sujeto, ni dos a la vez.

    Dos a la vez permitiría mandar el id de una fila y la clave de otra, y el
    servidor tendría que decidir cuál cree. Esa decisión no debe existir.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json={
            "event_kind": "start_work",
            "evidence_level": "fresh",
            "latitude": P0[0],
            "longitude": P0[1],
            "device_captured_at": AHORA.isoformat(),
            **extra,
        },
    )
    assert respuesta.status_code == 422, f"{caso}: {respuesta.text}"


async def test_two_simultaneous_points_for_one_key_produce_one_row(
    seeded, alpha_client
):
    """Concurrencia sobre la misma clave: una fila.

    La cola puede vaciar en paralelo con una captura en vivo. Lo decide el
    índice único, no el orden de llegada.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    clave = _clave("cc")
    await alpha_client.post(
        "/api/worksessions", json={}, headers={"Idempotency-Key": clave}
    )

    a, b = await asyncio.gather(
        _punto_por_clave(
            alpha_client, event_kind="start_work", clave=clave, coord=P0, hace=5
        ),
        _punto_por_clave(
            alpha_client, event_kind="start_work", clave=clave, coord=P0, hace=5
        ),
        return_exceptions=True,
    )
    codigos = [r.status_code for r in (a, b) if not isinstance(r, BaseException)]
    assert all(c == 201 for c in codigos), codigos
    assert len(
        await _filas(
            "SELECT id FROM location_fix WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    ) == 1
