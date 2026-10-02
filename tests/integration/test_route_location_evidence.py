"""Evidencia de ubicación: niveles, correlación, frontera y Missing (RTE06-CP2).

Qué se prueba aquí y qué no
---------------------------
Aquí está el servidor: que la evidencia se ate a la acción exacta, que no se
pueda inyectar la de otro, que la base rechace lo que no debe existir y que el
Missing se cree una sola vez. El motor de kilometraje tiene su propio archivo.

Los casos vienen de §37 de la instrucción: G1–G5 para ubicación, más las reglas
de §13 (frontera de privacidad) y §31 (contrato de servidor).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values

pytestmark = pytest.mark.integration


AHORA = datetime.now(timezone.utc)


# ── Montaje ─────────────────────────────────────────────────────────────────


async def _jornada_con_viaje(
    cliente, seeded, *, llegar: bool = True, tenant="alpha", purpose: str = "other"
):
    """Una jornada abierta y un viaje que ya salió, opcionalmente ya llegado.

    Sin vehículo asignado a propósito: así el odómetro no bloquea `Start Trip`
    y estos tests miden lo que quieren medir. Que el odómetro sí bloquea con
    vehículo aplicable lo prueba la suite de RTE04, y no se repite aquí.
    """
    compania = getattr(seeded, tenant)
    await cliente.login(compania.users["supervisor"].email)
    jornada = (await cliente.post("/api/worksessions", json={})).json()
    assert "id" in jornada, jornada
    viaje = (
        await cliente.post(
            "/api/trips",
            json={"purpose": purpose, "context_reference": "Field task"},
        )
    ).json()
    assert "id" in viaje, viaje
    inicio = await cliente.post(f"/api/trips/{viaje['id']}/start", json={})
    assert inicio.status_code in (200, 201), inicio.text
    if llegar:
        llegada = await cliente.post(f"/api/trips/{viaje['id']}/arrive", json={})
        assert llegada.status_code in (200, 201), llegada.text
    return jornada, viaje


def _punto(
    *,
    event_kind: str,
    subject_id: int,
    nivel: str = "fresh",
    lat: str = "40.712800",
    lon: str = "-74.0060000",
    edad: int | None = None,
    precision: str | None = "12.00",
    capturado=None,
) -> dict:
    cuerpo = {
        "event_kind": event_kind,
        "subject_id": subject_id,
        "evidence_level": nivel,
        "latitude": lat,
        "longitude": lon,
        "device_captured_at": (capturado or AHORA).isoformat(),
    }
    if precision is not None:
        cuerpo["accuracy_m"] = precision
    if edad is not None:
        cuerpo["source_age_seconds"] = edad
    return cuerpo


async def _filas(consulta: str, params: dict) -> list[dict]:
    async with async_session_maker() as sesion:
        filas = await sesion.execute(text(consulta), params)
        return [dict(f._mapping) for f in filas]


# ── G1: captura fresca atada a la acción exacta ─────────────────────────────


async def test_fresh_evidence_binds_to_the_exact_action(seeded, alpha_client):
    """G1: el punto queda atado a ese `Start Trip`, no a "lo de esa hora".

    La correlación es la tupla `(company, event_kind, subject_kind, subject_id)`,
    así que se comprueba leyendo la fila: `subject_kind` tiene que ser `trip` y
    `subject_id` el del viaje. §14 prohíbe correlacionar por proximidad de
    tiempo, y esto es lo que demuestra que no se hace.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="start_trip", subject_id=viaje["id"]),
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["evidence_level"] == "fresh"
    assert cuerpo["replayed"] is False
    # La respuesta no devuelve coordenadas: el cliente ya sabe dónde estaba.
    assert "latitude" not in cuerpo

    filas = await _filas(
        "SELECT event_kind, subject_kind, subject_id, evidence_level, "
        "work_session_id, source_age_seconds FROM location_fix "
        "WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 1
    assert filas[0]["subject_kind"] == "trip"
    assert filas[0]["subject_id"] == viaje["id"]
    assert filas[0]["source_age_seconds"] is None, "fresh no lleva edad"


async def test_occurrence_and_receipt_are_separate(seeded, alpha_client):
    """§31: la hora de captura y la de recepción son dos hechos distintos.

    Se manda un punto medido hace diez minutos —lo que pasa cuando la acción
    esperó en la cola— y se comprueba que el servidor conserva **las dos**: la
    del dispositivo tal cual, y la suya propia. Un punto cacheado no pasa a
    fresco porque la subida ocurriera después (§32).
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    medido = AHORA - timedelta(minutes=10)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip", subject_id=viaje["id"], capturado=medido
        ),
    )
    assert respuesta.status_code == 201, respuesta.text

    fila = (
        await _filas(
            "SELECT device_captured_at, server_received_at, evidence_level "
            "FROM location_fix WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert abs((fila["device_captured_at"] - medido).total_seconds()) < 2
    assert fila["server_received_at"] > fila["device_captured_at"]
    assert fila["evidence_level"] == "fresh", (
        "el nivel lo declara el dispositivo; llegar tarde no lo degrada"
    )


# ── G3: el punto cacheado, y sus criterios ──────────────────────────────────


async def test_cached_evidence_keeps_its_age(seeded, alpha_client):
    """G3: se guarda como `degraded_cached` y **con** su edad.

    La edad no es decorativa: §28 obliga a poder auditar de cuándo era la
    coordenada que se usó, años después. Sin ella, un tramo calculado con un
    punto de cinco minutos sería indistinguible de uno recién medido.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip",
            subject_id=viaje["id"],
            nivel="degraded_cached",
            edad=120,
            precision="80.00",
        ),
    )
    assert respuesta.status_code == 201, respuesta.text

    fila = (
        await _filas(
            "SELECT evidence_level, source_age_seconds FROM location_fix "
            "WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert fila["evidence_level"] == "degraded_cached"
    assert fila["source_age_seconds"] == 120


@pytest.mark.parametrize(
    "edad,precision,motivo",
    [
        (7200, "10.00", "demasiado viejo"),
        (60, "5000.00", "demasiado impreciso"),
    ],
    ids=["viejo", "impreciso"],
)
async def test_a_cached_point_outside_the_policy_is_rejected(
    seeded, alpha_client, edad, precision, motivo
):
    """§11: el punto cacheado sólo vale si cumple los criterios configurados.

    Los comprueba también el servidor, y no por desconfianza: el umbral es
    configuración suya —`route_location`— y el cliente puede llevar una versión
    vieja con otro número.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip",
            subject_id=viaje["id"],
            nivel="degraded_cached",
            edad=edad,
            precision=precision,
        ),
    )
    assert respuesta.status_code == 422, f"{motivo}: {respuesta.text}"
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


async def test_an_incoherent_level_is_rejected_by_the_schema(seeded, alpha_client):
    """Un `fresh` con edad declarada es una contradicción, y no entra.

    Lo rechazan a la vez el schema y el `CHECK` de la tabla. Las dos cosas a
    propósito: el schema da un 422 legible, la restricción protege el camino que
    no pase por el schema.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip", subject_id=viaje["id"], nivel="fresh", edad=30
        ),
    )
    assert respuesta.status_code == 422, respuesta.text


# ── C6: reenvío duplicado ───────────────────────────────────────────────────


async def test_a_replayed_point_does_not_duplicate(seeded, alpha_client):
    """C6: el mismo punto dos veces da una fila y lo dice.

    Y **no sobrescribe**: el primer punto es el que se midió más cerca del
    evento. Reemplazarlo por el del reenvío cambiaría la evidencia por una
    posterior, que es lo contrario de lo que §32 pide conservar.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    cuerpo = _punto(event_kind="start_trip", subject_id=viaje["id"])

    primero = await alpha_client.post("/api/location/evidence", json=cuerpo)
    assert primero.status_code == 201, primero.text
    assert primero.json()["replayed"] is False

    segundo = await alpha_client.post(
        "/api/location/evidence",
        json={**cuerpo, "latitude": "41.000000", "longitude": "-75.0000000"},
    )
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["replayed"] is True
    assert segundo.json()["id"] == primero.json()["id"]

    filas = await _filas(
        "SELECT latitude FROM location_fix WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 1
    assert str(filas[0]["latitude"]) == "40.712800", "el primero manda"


async def test_two_simultaneous_points_produce_one(seeded, alpha_client):
    """Concurrencia: el índice único decide, y el segundo lee el que ganó.

    Importa porque la cola offline vacía en paralelo con una captura en vivo.
    Un 409 aquí sería castigar al cliente por algo que hizo bien.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    cuerpo = _punto(event_kind="start_trip", subject_id=viaje["id"])

    a, b = await asyncio.gather(
        alpha_client.post("/api/location/evidence", json=cuerpo),
        alpha_client.post("/api/location/evidence", json=cuerpo),
        return_exceptions=True,
    )
    codigos = [r.status_code for r in (a, b) if not isinstance(r, BaseException)]
    assert all(c == 201 for c in codigos), codigos
    filas = await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    )
    assert len(filas) == 1


# ── §13: la frontera de privacidad ──────────────────────────────────────────


async def test_evidence_for_another_users_trip_is_not_found(
    seeded, alpha_client, beta_client
):
    """§31: inyectar evidencia en el viaje de otro da **404**, no 403.

    El 404 es la respuesta correcta: un 403 confirmaría que ese viaje existe.
    Aquí el otro es de otro tenant, que es el caso más grave, y la respuesta es
    la misma que si el id no existiera.
    """
    _, viaje_beta = await _jornada_con_viaje(beta_client, seeded, tenant="beta")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="start_trip", subject_id=viaje_beta["id"]),
    )
    assert respuesta.status_code == 404, respuesta.text
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


async def test_capture_requires_an_active_session(seeded, alpha_client):
    """§13: la captura normal sólo se permite con la jornada ACTIVE.

    Se cierra la jornada y se intenta mandar un punto de `Start Trip`, que no
    es el evento de la excepción. Se rechaza.
    """
    jornada, viaje = await _jornada_con_viaje(alpha_client, seeded, purpose="home")
    fin = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert fin.status_code in (200, 201), fin.text

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="start_trip", subject_id=viaje["id"]),
    )
    assert respuesta.status_code == 409, respuesta.text


async def test_end_work_recovery_is_allowed_after_the_session_ends(
    seeded, alpha_client
):
    """L5: la jornada termina ya, y la recuperación de ese End Work la alcanza.

    Es la única grieta de §13, y la estrecha: sólo el evento `end_work`, sólo
    dentro de la ventana y sólo del propio supervisor. Aquí se comprueba que la
    grieta existe; el siguiente test comprueba que no da para más.
    """
    jornada, _ = await _jornada_con_viaje(alpha_client, seeded, purpose="home")
    fin = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert fin.status_code in (200, 201), fin.text

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="end_work", subject_id=jornada["id"], nivel="recovered"
        ),
    )
    assert respuesta.status_code == 201, respuesta.text
    fila = (
        await _filas(
            "SELECT event_kind, evidence_level, subject_kind FROM location_fix "
            "WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert fila["event_kind"] == "end_work"
    assert fila["subject_kind"] == "work_session"
    assert fila["evidence_level"] == "recovered"


async def test_the_end_work_exception_does_not_extend_to_other_events(
    seeded, alpha_client
):
    """La grieta de End Work no abre captura nueva.

    Con la jornada cerrada, un `arrived` del viaje de esa jornada se rechaza.
    Si no, la excepción de §13 se convertiría en una vía para escribir ubicación
    en jornadas ya cerradas.
    """
    jornada, viaje = await _jornada_con_viaje(alpha_client, seeded, purpose="home")
    fin = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert fin.status_code in (200, 201), fin.text

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="arrived", subject_id=viaje["id"]),
    )
    assert respuesta.status_code == 409, respuesta.text


# ── G5: Missing, exactamente uno ────────────────────────────────────────────


async def test_missing_is_created_once_and_fabricates_nothing(seeded, alpha_client):
    """G5: un evento Missing, sin coordenada inventada, y sólo uno.

    El segundo intento devuelve el mismo: §29 pide que cada evento subyacente
    quede preservado, y dos filas para el mismo hecho harían que "cuántas
    ubicaciones faltaron hoy" tuviera dos respuestas.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    cuerpo = {
        "event_kind": "arrived",
        "subject_id": viaje["id"],
        "reason_code": "recovery_window_exhausted",
        "permission_state": "granted",
        "attempts": [
            {
                "stage": "current",
                "started_at": AHORA.isoformat(),
                "duration_ms": 10_000,
                "error_code": 3,
                "error_message": "Timeout expired",
            }
        ],
        "rejected_age_seconds": 7200,
        "rejected_accuracy_m": "3000.00",
    }

    primero = await alpha_client.post("/api/location/missing", json=cuerpo)
    assert primero.status_code == 201, primero.text
    assert primero.json()["replayed"] is False

    segundo = await alpha_client.post("/api/location/missing", json=cuerpo)
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["replayed"] is True
    assert segundo.json()["id"] == primero.json()["id"]

    # `notification_status` ya **no** es una columna de esta tabla.
    #
    # Expectativa anterior: el hecho llevaba `notification_status` y se leía de
    #   aquí.
    # Delta aprobado por CER: D-RTE06-MISSING-01 — el hecho es estrictamente
    #   inmutable, así que el estado de entrega, que por definición avanza, se
    #   muda a `missing_location_notification`.
    # Expectativa nueva: el hecho no tiene la columna; el estado de entrega se
    #   lee de su propia tabla, y la respuesta de la API lo sigue devolviendo
    #   por comodidad del cliente.
    filas = await _filas(
        "SELECT reason_code, attempts, rejected_candidate, "
        "trip_id, occurred_at FROM missing_location_event WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 1
    fila = filas[0]
    assert fila["reason_code"] == "recovery_window_exhausted"
    assert primero.json()["notification_status"] == "pending"
    entrega = await _filas(
        "SELECT channel, status FROM missing_location_notification "
        "WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert entrega == [{"channel": "in_platform", "status": "pending"}]
    assert fila["trip_id"] == viaje["id"]
    assert fila["attempts"][0]["stage"] == "current"
    # Del candidato rechazado se guarda edad y precisión, **nunca** dónde estaba.
    assert set(fila["rejected_candidate"]) == {"age_seconds", "accuracy_m"}
    assert "latitude" not in fila["rejected_candidate"]
    # Y no hay ningún punto: no se fabricó coordenada.
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


async def test_missing_is_refused_when_a_point_already_exists(seeded, alpha_client):
    """El punto manda sobre el Missing.

    Un cliente que reintenta podría llamar a las dos cosas. Un `missing` junto a
    un punto válido obligaría al motor de kilometraje a decidir cuál cree, y esa
    decisión no debería existir.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="arrived", subject_id=viaje["id"]),
    )

    respuesta = await alpha_client.post(
        "/api/location/missing",
        json={
            "event_kind": "arrived",
            "subject_id": viaje["id"],
            "reason_code": "acquisition_timeout",
        },
    )
    assert respuesta.status_code == 409, respuesta.text


async def test_an_event_that_never_happened_takes_no_evidence(seeded, alpha_client):
    """§19: no se crea Missing para un `Arrived` que no ocurrió.

    El viaje está en tránsito, así que `arrived_at` es nulo. Ni punto ni
    Missing: el evento no ha pasado, y marcarlo como "ubicación perdida" diría
    que sí.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded, llegar=False)

    punto = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="arrived", subject_id=viaje["id"]),
    )
    assert punto.status_code == 404, punto.text

    perdido = await alpha_client.post(
        "/api/location/missing",
        json={
            "event_kind": "arrived",
            "subject_id": viaje["id"],
            "reason_code": "acquisition_timeout",
        },
    )
    assert perdido.status_code == 404, perdido.text


# ── La base, no el servicio ─────────────────────────────────────────────────


async def test_the_database_rejects_missing_as_an_evidence_level(seeded):
    """§11: `missing` **no** es un nivel, y lo garantiza el `CHECK`.

    Si lo fuera, cualquier consulta que pidiera waypoints tendría que acordarse
    de excluirlo, y la que se olvidara calcularía kilometraje con una coordenada
    que no existe.
    """
    async with async_session_maker() as sesion:
        with pytest.raises((IntegrityError, ProgrammingError)) as fallo:
            await sesion.execute(
                text(
                    "INSERT INTO location_fix (company_id, work_session_id, "
                    "event_kind, subject_kind, subject_id, evidence_level, "
                    "latitude, longitude, device_captured_at, server_received_at, "
                    "created_at, updated_at) VALUES "
                    "(:c, 1, 'start_trip', 'trip', 1, 'missing', 0, 0, now(), "
                    "now(), now(), now())"
                ),
                {"c": seeded.alpha.id},
            )
            await sesion.commit()
    assert "ck_location_fix_evidence_level" in str(fallo.value), str(fallo.value)


@pytest.mark.parametrize(
    "lat,lon,caso",
    [("91", "0", "latitud"), ("0", "181", "longitud")],
    ids=["latitud", "longitud"],
)
async def test_the_database_rejects_impossible_coordinates(seeded, lat, lon, caso):
    """§31 pide validar el rango, y se valida también en la tabla.

    El schema protege la API; la restricción protege la tabla de cualquier
    camino que no pase por la API — un script, una importación (invariante 6).
    """
    async with async_session_maker() as sesion:
        with pytest.raises((IntegrityError, ProgrammingError)) as fallo:
            await sesion.execute(
                text(
                    "INSERT INTO location_fix (company_id, work_session_id, "
                    "event_kind, subject_kind, subject_id, evidence_level, "
                    "latitude, longitude, device_captured_at, server_received_at, "
                    "created_at, updated_at) VALUES "
                    f"(:c, 1, 'start_trip', 'trip', 1, 'fresh', {lat}, {lon}, "
                    "now(), now(), now(), now())"
                ),
                {"c": seeded.alpha.id},
            )
            await sesion.commit()
    assert "ck_location_fix_coordinates" in str(fallo.value), caso


async def test_the_database_rejects_an_impossible_event_subject_pairing(seeded):
    """Un `change_plan` no puede colgar de una jornada.

    La pareja evento→sujeto se deriva de un diccionario y se comprueba en la
    base. Sin esto, una correlación imposible de reconstruir después quedaría
    escrita sin que nada protestara.
    """
    async with async_session_maker() as sesion:
        with pytest.raises((IntegrityError, ProgrammingError)) as fallo:
            await sesion.execute(
                text(
                    "INSERT INTO location_fix (company_id, work_session_id, "
                    "event_kind, subject_kind, subject_id, evidence_level, "
                    "latitude, longitude, device_captured_at, server_received_at, "
                    "created_at, updated_at) VALUES "
                    "(:c, 1, 'change_plan', 'work_session', 1, 'fresh', 0, 0, "
                    "now(), now(), now(), now())"
                ),
                {"c": seeded.alpha.id},
            )
            await sesion.commit()
    assert "ck_location_fix_event_subject" in str(fallo.value), str(fallo.value)


async def test_location_evidence_is_append_only(seeded, alpha_client):
    """Una coordenada capturada es un hecho: ni se edita ni se borra (§35)."""
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="start_trip", subject_id=viaje["id"]),
    )

    for sentencia in (
        "UPDATE location_fix SET latitude = 0 WHERE company_id = :c",
        "DELETE FROM location_fix WHERE company_id = :c",
    ):
        async with async_session_maker() as sesion:
            with pytest.raises(Exception) as fallo:
                await sesion.execute(text(sentencia), {"c": seeded.alpha.id})
                await sesion.commit()
        assert "append-only" in str(fallo.value), sentencia


async def test_the_missing_fact_admits_no_update_at_all(seeded, alpha_client):
    """El hecho es inmutable **sin excepciones de columna**.

    Expectativa anterior: el disparador permitía `UPDATE` de
      `notification_status`, `notified_at`, `notes` y `updated_at`, porque el
      estado de entrega vivía en esta fila.
    Delta aprobado por CER: D-RTE06-MISSING-01 — un hecho "inmutable salvo
      cuatro columnas" es un hecho mutable con pasos de más. El estado de
      entrega se separa y el disparador pasa a ser el genérico del proyecto.
    Expectativa nueva: ningún `UPDATE` y ningún `DELETE`, y la prueba de que el
      aviso sí avanza está en `test_route_missing_immutability.py`, donde
      corresponde ahora.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await alpha_client.post(
        "/api/location/missing",
        json={
            "event_kind": "arrived",
            "subject_id": viaje["id"],
            "reason_code": "acquisition_timeout",
        },
    )

    for sentencia in (
        "UPDATE missing_location_event SET reason_code = 'permission_denied' "
        "WHERE company_id = :c",
        "UPDATE missing_location_event SET updated_at = now() WHERE company_id = :c",
        "DELETE FROM missing_location_event WHERE company_id = :c",
    ):
        async with async_session_maker() as sesion:
            with pytest.raises(Exception) as fallo:
                await sesion.execute(text(sentencia), {"c": seeded.alpha.id})
                await sesion.commit()
        assert "append-only" in str(fallo.value), sentencia


# ── L3 y L4: actividad ──────────────────────────────────────────────────────


async def _valor(cliente, list_code: str, etiqueta: str) -> int:
    """El id de un valor configurado, buscado por etiqueta.

    Igual que en la suite de RTE05: los ids se siembran y no se pueden suponer.
    """
    respuesta = await cliente.get(f"/api/standard-values/{list_code}")
    assert respuesta.status_code == 200, respuesta.text
    for v in respuesta.json():
        if v["label"] == etiqueta:
            return v["id"]
    raise AssertionError(f"no está '{etiqueta}' en {list_code}")


async def test_activity_evidence_must_match_what_actually_happened(
    seeded, alpha_client
):
    """L3/L4: el evento reportado tiene que ser la acción terminal real.

    Se completa una actividad y se intenta registrar la ubicación como si se
    hubiera **dejado**. Se rechaza: la correlación de §14 quedaría satisfecha en
    la forma mientras describe algo que no pasó.
    """
    # El catálogo se siembra por test, igual que en la suite de RTE05: los ids
    # no se pueden suponer y las etiquetas sólo existen si se provisionan.
    async with async_session_maker() as sesion:
        await provision_standard_values(sesion, company_id=seeded.alpha.id)
        await sesion.commit()

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    assert "id" in jornada, jornada
    actividad = await _valor(alpha_client, "client_visit_activities", "Service Review")
    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": "Acme Corporation"},
        )
    ).json()
    assert "id" in viaje, viaje
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()
    assert "id" in bloque, bloque

    resultado = await _valor(alpha_client, "outcomes", "Follow-up Required")
    fin = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )
    assert fin.status_code in (200, 201), fin.text

    equivocado = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="activity_leave", subject_id=bloque["id"]),
    )
    assert equivocado.status_code == 404, equivocado.text

    correcto = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="activity_complete", subject_id=bloque["id"]),
    )
    assert correcto.status_code == 201, correcto.text


# ── G3, G4 y G12: la calidad se exige en los tres niveles ───────────────────
#
# Qué cubre este bloque y por qué está en el servidor
# ---------------------------------------------------
# El cliente ya comprueba la precisión antes de enviar, pero el bundle y la
# cookie son del navegador: lo que el cliente comprueba es experiencia de uso,
# no un control (AGENTS.md, invariante 8). La puerta tiene que estar aquí.
#
# Y tiene que estar **aquí** y no más adelante porque `for_trip_waypoints()` no
# vuelve a filtrar por nivel ni por precisión: si la fila se escribe, ya es un
# waypoint oficial de kilometraje. La única defensa es que no se escriba.
#
# Antes de este delta, `_validar_calidad` volvía en la primera línea para
# cualquier nivel que no fuera `degraded_cached`, así que `fresh` y `recovered`
# no tenían ninguna comprobación de precisión en el servidor y
# `fresh_max_accuracy_m` estaba declarado en la política sin usarse.


@pytest.mark.parametrize("nivel", ["fresh", "recovered"])
async def test_g4_a_grossly_inaccurate_point_is_not_authoritative(
    seeded, alpha_client, nivel
):
    """G4: dos kilómetros de error no son evidencia, en ningún nivel.

    El umbral de `recovered` es el mismo que el de `fresh` a propósito: un punto
    recuperado no puede valer menos que uno recién capturado sólo por haber
    tardado más.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip",
            subject_id=viaje["id"],
            nivel=nivel,
            precision="2000.00",
        ),
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


@pytest.mark.parametrize(
    "precision, esperado",
    [("100.00", 201), ("100.01", 422), ("99.99", 201)],
    ids=["en-el-umbral", "justo-por-encima", "justo-por-debajo"],
)
async def test_g3_the_threshold_is_the_threshold(
    seeded, alpha_client, precision, esperado
):
    """G3: el límite se comprueba donde está, no "más o menos" ahí.

    Los tres casos juntos porque lo que se prueba es el borde: que 100 entre,
    que 100,01 no, y que el que está justo por debajo siga entrando. Comprobar
    sólo uno dejaría pasar un `<` escrito donde debía ir un `<=`.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip",
            subject_id=viaje["id"],
            nivel="fresh",
            precision=precision,
        ),
    )

    assert respuesta.status_code == esperado, respuesta.text


@pytest.mark.parametrize("nivel", ["fresh", "degraded_cached", "recovered"])
async def test_g12_unknown_accuracy_is_not_acceptable_accuracy(
    seeded, alpha_client, nivel
):
    """G12: una precisión que no se puede evaluar no es una precisión buena.

    Es el hallazgo de CER sobre la regla implementada en el delta anterior:
    aceptaba `precision <= umbral` **o** `precision desconocida`, tratando las
    dos como equivalentes. No lo son. Un punto de 12 m se midió y cumple; un
    punto sin precisión no se pudo comprobar, y aceptarlo es afirmar que su
    calidad es buena sin haberla mirado.

    Se comprueban los tres niveles porque el agujero no estaba sólo en
    `recovered`: `fresh` aceptaba lo mismo, y al aceptarlo en la etapa 1 el
    punto de precisión desconocida nunca llegaba a la etapa de recuperación.
    Arreglar sólo `recovered` habría dejado el camino real abierto.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip",
            subject_id=viaje["id"],
            nivel=nivel,
            precision=None,
            edad=60 if nivel == "degraded_cached" else None,
        ),
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


async def test_g12_a_rejected_point_never_becomes_a_trip_waypoint(
    seeded, alpha_client
):
    """FR-02: lo que se rechazó no aparece después como entrada de kilometraje.

    No basta con que el POST devuelva 422. Lo que importa es lo que ve el motor
    de kilometraje, y lo que ve es `for_trip_waypoints()`, que selecciona de
    `location_fix` sin filtrar por nivel ni por precisión. Así que esto
    comprueba el final del camino, no la puerta: después del rechazo, ese viaje
    no tiene ningún waypoint.
    """
    from app.routers_api.location.dao import LocationFixesDAO

    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    for precision in (None, "2000.00"):
        respuesta = await alpha_client.post(
            "/api/location/evidence",
            json=_punto(
                event_kind="start_trip",
                subject_id=viaje["id"],
                nivel="recovered",
                precision=precision,
            ),
        )
        assert respuesta.status_code == 422, respuesta.text

    waypoints = await LocationFixesDAO.for_trip_waypoints(
        company_id=seeded.alpha.id, trip_id=viaje["id"]
    )
    assert waypoints == [], (
        "un punto rechazado por calidad acabó siendo waypoint oficial: "
        f"{waypoints}"
    )


async def test_g12_the_good_point_still_enters(seeded, alpha_client):
    """La otra mitad: endurecer la regla no puede cerrar el camino bueno.

    Sin esto, los tests de arriba pasarían igual si el servidor rechazara
    **todo**, que es el modo de fallo más fácil de introducir al añadir una
    comprobación.
    """
    from app.routers_api.location.dao import LocationFixesDAO

    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(
            event_kind="start_trip",
            subject_id=viaje["id"],
            nivel="fresh",
            precision="12.00",
        ),
    )
    assert respuesta.status_code == 201, respuesta.text

    waypoints = await LocationFixesDAO.for_trip_waypoints(
        company_id=seeded.alpha.id, trip_id=viaje["id"]
    )
    assert len(waypoints) == 1, waypoints


# ── La política de captura llega al cliente ─────────────────────────────────


async def test_the_client_can_read_the_capture_policy(seeded, alpha_client):
    """Los umbrales que el cliente debe aplicar se pueden pedir.

    Por qué este test existe
    ------------------------
    No existía el endpoint. El cliente llevaba los cinco números escritos en el
    bundle y `setLocationPolicy` estaba exportada sin que nadie la llamara, así
    que `route_location` —política de plataforma, editable desde el panel— no
    llegaba al dispositivo: la pantalla guardaba el cambio y el teléfono seguía
    capturando con los valores por defecto.

    Se descubrió al ejecutar por primera vez los tests de navegador G3/G4/G6/G7,
    que acortan la ventana de recuperación con una fila de política y fallaban
    porque el cliente no la leía nunca.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    respuesta = await alpha_client.get("/api/location/policy")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == {
        "fresh_timeout_seconds",
        "fresh_max_accuracy_m",
        "cached_max_age_seconds",
        "cached_max_accuracy_m",
        "recovery_window_seconds",
        "sweeper_grace_seconds",
    }, cuerpo
    # Los valores por defecto de `RouteLocationPolicy`, que son los aprobados.
    assert cuerpo["fresh_max_accuracy_m"] == 100
    assert cuerpo["recovery_window_seconds"] == 180


async def test_the_capture_policy_needs_a_session(seeded, alpha_anonymous):
    """Sin sesión no se sirve: es configuración operativa, no superficie pública."""
    respuesta = await alpha_anonymous.get("/api/location/policy")
    assert respuesta.status_code == 401, respuesta.text


# ── §8.3: nada se queda en el limbo ─────────────────────────────────────────


async def test_an_event_the_client_never_reported_is_closed_by_the_sweep(
    seeded, alpha_client
):
    """El tercer camino: si el cliente no vuelve, el servidor cierra el hecho.

    Por qué esto es la pieza que cierra FR-03
    -----------------------------------------
    El cliente acota sus reintentos —pasada la ventana más el margen deja de
    insistir y retira la entrada—, así que la pregunta siguiente es qué pasa
    con el evento. La respuesta no puede ser "nada": un evento sin punto y sin
    Missing es exactamente el estado que §11 no contempla y que el hallazgo de
    campo produjo.

    Lo cierra el barrido, con el motivo que describe el hecho observable
    —`no_client_report`— y no una suposición sobre qué le pasó al teléfono.

    Se envejece el viaje con SQL porque el corte del barrido se mide contra
    `occurred_at` y esperar cinco minutos de reloj en un test no demuestra nada
    que esto no demuestre. `trip` no es append-only, así que se puede.
    """
    from app.routers_api.location.service import sweep_unreported_windows

    _, viaje = await _jornada_con_viaje(alpha_client, seeded)

    # Antes del barrido: el evento existe y no tiene ni punto ni Missing.
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []
    assert await _filas(
        "SELECT id FROM missing_location_event WHERE company_id = :c",
        {"c": seeded.alpha.id},
    ) == []

    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE trip SET started_at = now() - interval '2 hours' "
                "WHERE id = :t AND company_id = :c"
            ),
            {"t": viaje["id"], "c": seeded.alpha.id},
        )
        await sesion.commit()

    cerrados = await sweep_unreported_windows()
    assert cerrados >= 1, "el barrido no cerró el evento que nadie reportó"

    hechos = await _filas(
        "SELECT event_kind, reason_code FROM missing_location_event "
        "WHERE company_id = :c AND subject_id = :s",
        {"c": seeded.alpha.id, "s": viaje["id"]},
    )
    motivos = {(f["event_kind"], f["reason_code"]) for f in hechos}
    assert ("start_trip", "no_client_report") in motivos, hechos

    # Y no fabrica coordenadas para rellenar el hueco.
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


async def test_the_sweep_leaves_alone_what_already_has_an_answer(
    seeded, alpha_client
):
    """El barrido no duplica ni pisa lo que ya está resuelto.

    La otra mitad del test de arriba: sin esto, un barrido que escribiera un
    `no_client_report` encima de un punto válido pasaría igual los dos
    primeros, y estaría borrando la respuesta verdadera con una genérica.
    """
    from app.routers_api.location.service import sweep_unreported_windows

    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json=_punto(event_kind="start_trip", subject_id=viaje["id"]),
    )
    assert respuesta.status_code == 201, respuesta.text

    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE trip SET started_at = now() - interval '2 hours' "
                "WHERE id = :t AND company_id = :c"
            ),
            {"t": viaje["id"], "c": seeded.alpha.id},
        )
        await sesion.commit()

    await sweep_unreported_windows()

    assert await _filas(
        "SELECT id FROM missing_location_event WHERE company_id = :c "
        "AND subject_id = :s",
        {"c": seeded.alpha.id, "s": viaje["id"]},
    ) == [], "el barrido escribió un Missing sobre un evento que ya tenía punto"


async def test_a_configured_window_reaches_the_client(seeded, alpha_client):
    """Lo que la compañía configura es lo que el cliente recibe.

    Es la otra mitad de F-C: no basta con que el endpoint exista, tiene que
    servir el valor **guardado**, no el de fábrica. Si esto falla, acortar la
    ventana desde el panel no acorta nada en el teléfono.
    """
    import json as _json

    from app.core.platform.config_service import platform_config

    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "INSERT INTO platform_policy(key, value, version, updated_at) "
                "VALUES ('route_location', CAST(:v AS jsonb), 1, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = CAST(:v AS jsonb), "
                "  version = platform_policy.version + 1, updated_at = now()"
            ),
            {"v": _json.dumps({"recovery_window_seconds": 7})},
        )
        await sesion.commit()
    await platform_config.refresh()

    cuerpo = (await alpha_client.get("/api/location/policy")).json()

    assert cuerpo["recovery_window_seconds"] == 7, cuerpo
    # Y lo que no se guardó sigue viniendo de los valores por defecto.
    assert cuerpo["fresh_max_accuracy_m"] == 100, cuerpo


# ── El barrido cubre los siete eventos, no tres ─────────────────────────────


async def test_the_sweep_closes_work_session_events_too(seeded, alpha_client):
    """`start_work` y `end_work` también se cierran si nadie los reporta.

    Por qué este test existe
    ------------------------
    El barrido sólo miraba `start_trip`, `arrived` y `change_plan`. Los cuatro
    eventos restantes —los dos de jornada y los dos de actividad— no tenían
    tercer camino: si el cliente no volvía a hablar de ellos, el evento se
    quedaba sin punto y sin Missing **para siempre**, que es el limbo que esta
    función existe para evitar.

    No se notaba porque la entrada se quedaba en la cola del dispositivo
    reintentando, lo que daba la impresión de que alguien seguía ocupándose. Al
    acotar esos reintentos —FR-03 del cierre anterior— el hueco pasó a ser
    observable: una entrada caducada de `start_work` se retiraba y nadie
    cerraba el hecho.
    """
    from app.routers_api.location.service import sweep_unreported_windows

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    assert "id" in jornada, jornada
    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code in (200, 201), cierre.text

    # Se envejece la jornada entera: el corte del barrido se mide contra la
    # hora de ocurrencia, y esperar cinco minutos de reloj no demostraría nada
    # que esto no demuestre.
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE work_session SET started_at = now() - interval '2 hours', "
                "ended_at = now() - interval '2 hours' "
                "WHERE id = :j AND company_id = :c"
            ),
            {"j": jornada["id"], "c": seeded.alpha.id},
        )
        await sesion.commit()

    await sweep_unreported_windows()

    hechos = await _filas(
        "SELECT event_kind, reason_code, trip_id, subject_kind "
        "FROM missing_location_event WHERE company_id = :c AND subject_id = :s",
        {"c": seeded.alpha.id, "s": jornada["id"]},
    )
    por_evento = {f["event_kind"]: f for f in hechos}
    assert "start_work" in por_evento, hechos
    assert "end_work" in por_evento, hechos
    for evento in ("start_work", "end_work"):
        fila = por_evento[evento]
        assert fila["reason_code"] == "no_client_report", fila
        assert fila["subject_kind"] == "work_session", fila
        # La jornada no tiene viaje, y el hecho no se lo inventa.
        assert fila["trip_id"] is None, fila

    # Y no se fabrican coordenadas para rellenar el hueco.
    assert await _filas(
        "SELECT id FROM location_fix WHERE company_id = :c", {"c": seeded.alpha.id}
    ) == []


def test_the_sweep_cannot_leave_an_event_kind_behind():
    """Ningún evento del catálogo puede quedarse fuera del barrido.

    Es un guardián estructural, y conviene ser exacto sobre lo que demuestra:
    lee el SQL del barrido y comprueba que cada valor de `LocationEventKind`
    aparece en él. **No** demuestra que cada rama funcione —eso lo hacen los
    tests de comportamiento—, sino que añadir un evento nuevo sin darle tercer
    camino hace fallar la suite en vez de pasar inadvertido.

    Existe porque el hueco anterior duró así: cuatro de los siete eventos sin
    barrido, sin que nada lo dijera.
    """
    import inspect

    from app.routers_api.location import service
    from app.routers_api.location.models import LocationEventKind

    fuente = inspect.getsource(service.sweep_unreported_windows)
    sin_cubrir = [
        evento.value
        for evento in LocationEventKind
        if f"'{evento.value}'" not in fuente
    ]
    assert not sin_cubrir, (
        "estos eventos no aparecen en el barrido, así que un evento sin punto "
        f"y sin Missing se quedaría así para siempre: {sin_cubrir}"
    )
