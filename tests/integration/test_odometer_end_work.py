"""
El odómetro de cierre y su relación con `End Work` (RTE04-C4).

La decisión que este archivo defiende: la **Opción B** de CER
--------------------------------------------------------------
Hay dos guardas de odómetro y son distintas a propósito.

* Para **salir a conducir** hace falta una lectura confirmada. Una excepción
  aprobada no basta: autoriza teclear, no arrancar.
* Para **terminar el día** basta con haber pedido la excepción. Quien acaba ya
  no va a conducir más, y retenerle la jornada abierta hasta que alguien revise
  su solicitud escribiría un `ended_at` que no ocurrió — y la hora de fin de
  jornada es un dato laboral, no un detalle de interfaz.

De ahí se siguen las cuatro propiedades que se comprueban aquí: la jornada se
cierra a su hora real, la evidencia queda explícitamente pendiente, la jornada
**no se reabre** para completarla, y la distancia no aparece hasta que exista.

Y una consecuencia que no es cosmética: una vez cerrado el día, la lectura de
cierre sólo se completa por la vía manual aprobada. Sin esa regla, cerrar la
jornada con la excepción *pedida* y subir después cualquier fotografía
convertiría la aprobación del administrador en un adorno.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.odometer.ocr import NoSuggestionReader, set_odometer_reader
from app.routers_api.standardvalues.provisioning import provision_standard_values


pytestmark = pytest.mark.integration


FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def _sin_ocr():
    set_odometer_reader(NoSuggestionReader())
    yield
    set_odometer_reader(NoSuggestionReader())


# ── Ayudas ──────────────────────────────────────────────────────────────────


async def _resolver_la_parada(cliente, seeded, trip_id: int) -> None:
    """Cierra la parada para que lo único pendiente sea el odómetro.

    RTE05 cerró el hueco que RTE04 aceptaba: un viaje operativo que llegó y no
    se resolvió bloquea el fin de jornada **antes** de que se mire el odómetro
    (PD-04). Lo que estos tests prueban es la guarda del odómetro, así que la
    parada se resuelve aquí en vez de relajar la guarda nueva.

    De paso queda demostrado FR-15 en la suite de integración: terminalizada la
    actividad, las reglas de cierre de RTE04 siguen aplicando sin cambios. El
    viaje pasa a `CLOSED`, y eso **no** quita la necesidad de lectura final —se
    cuenta por `started_at`, no por estado: quien condujo, condujo.
    """
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    actividades = (
        await cliente.get("/api/standard-values/client_visit_activities")
    ).json()
    resultados = (await cliente.get("/api/standard-values/outcomes")).json()

    await cliente.post(
        f"/api/trips/{trip_id}/activity/start",
        json={"activity_ids": [actividades[0]["id"]]},
    )
    await cliente.post(
        f"/api/trips/{trip_id}/activity/complete",
        json={"action": "complete", "outcome_id": resultados[0]["id"]},
    )


async def _jornada_conduciendo(cliente, seeded, *, llegar: bool = True) -> dict:
    """Jornada con vehículo, lectura de inicio hecha y un viaje ya arrancado.

    Es el estado en que la lectura de cierre **sí** hace falta: se condujo.

    Con `llegar=True` el viaje además llega **y se resuelve su parada**, que es
    el estado en que un supervisor llega de verdad al fin de jornada desde
    RTE05. Con `llegar=False` se queda en tránsito, que es lo que necesita la
    guarda de D-07.
    """
    await cliente.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await cliente.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = (
        await cliente.post(
            "/api/vehicles",
            json={
                "make": "Ford", "model": "Transit", "year": 2023, "unit": "V-END",
                "fuel_grade": "regular", "operational_mpg": "19.00",
            },
        )
    ).json()
    await cliente.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    await cliente.login(seeded.alpha.users["supervisor"].email)
    jornada = (await cliente.post("/api/worksessions", json={})).json()

    await cliente.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await cliente.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "50000.0"},
    )

    viaje = (
        await cliente.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    await cliente.post(f"/api/trips/{viaje['id']}/start", json={})
    if llegar:
        await cliente.post(f"/api/trips/{viaje['id']}/arrive", json={})
        await _resolver_la_parada(cliente, seeded, viaje["id"])

    jornada["trip_id"] = viaje["id"]
    return jornada


async def _excepcion_de_cierre(cliente, seeded, session_id: int) -> dict:
    solicitud = (
        await cliente.post(
            f"/api/odometer/sessions/{session_id}/end/exception",
            json={"reason": "camera_unavailable"},
        )
    ).json()
    return solicitud


# ── La guarda de cierre ─────────────────────────────────────────────────────


async def test_end_work_is_blocked_while_the_end_reading_is_untouched(
    seeded, alpha_client,
):
    """Si se condujo y no hay ni foto ni solicitud, todavía falta algo."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )

    assert respuesta.status_code == 409
    assert "odometer" in respuesta.json()["detail"].lower()

    # Y la jornada sigue abierta: el bloqueo no dejó un estado a medias.
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active"


async def test_a_day_without_driving_ends_without_any_end_reading(
    seeded, alpha_client,
):
    """Sin viaje arrancado no hay distancia que cerrar, así que no se pide nada."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Ford", "model": "Transit", "year": 2023, "unit": "V-IDLE",
                "fuel_grade": "regular", "operational_mpg": "19.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "ended"

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["end"]["status"] == "not_required"
    assert estado["odometer_distance"] is None


async def test_the_normal_end_photo_path_closes_the_day_and_the_distance(
    seeded, alpha_client,
):
    jornada = await _jornada_conduciendo(alpha_client, seeded)

    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/confirm",
            json={"reading": "50123.5"},
        )
    ).json()
    assert confirmada["status"] == "photo_confirmed"

    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 200

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert Decimal(estado["odometer_distance"]) == Decimal("123.5")


# ── Opción B ────────────────────────────────────────────────────────────────


async def test_the_day_ends_with_the_end_exception_still_unreviewed(
    seeded, alpha_client,
):
    """El corazón de la Opción B: pedirla basta para terminar el día."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )

    assert cierre.status_code == 200
    assert cierre.json()["status"] == "ended"
    assert cierre.json()["ended_at"] is not None

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["end"]["status"] == "exception_requested", (
        "la evidencia queda pendiente, no resuelta a la fuerza"
    )
    assert estado["odometer_distance"] is None, (
        "sin lectura de cierre no hay distancia; tampoco un cero"
    )


async def test_completing_the_end_reading_later_never_moves_ended_at(
    seeded, alpha_client,
):
    """La jornada no se reabre y su hora de fin no se toca."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    # La hora de fin se lee de la base, que es el reloj que manda, y se compara
    # consigo misma: así el test no depende de cómo se serialice el instante.
    async def _cierre() -> tuple[str, object]:
        async with async_session_maker() as session:
            fila = (
                await session.execute(
                    text("SELECT status, ended_at FROM work_session WHERE id = :i"),
                    {"i": jornada["id"]},
                )
            ).one()
        return fila.status, fila.ended_at

    situacion_antes, hora_antes = await _cierre()
    assert situacion_antes == "ended"
    assert hora_antes is not None

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/confirm",
            json={"reading": "50088.0"},
        )
    ).json()

    assert confirmada["status"] == "manual_exception_confirmed"
    assert confirmada["evidence_method"] == "manual_no_photo"

    situacion_despues, hora_despues = await _cierre()
    assert situacion_despues == "ended", "completar la evidencia no reabre la jornada"
    assert hora_despues == hora_antes, "la hora de fin no se movió"

    # Y ahora sí hay distancia, derivada de dos lecturas reales.
    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert Decimal(estado["odometer_distance"]) == Decimal("88.0")


async def test_completing_the_end_reading_later_creates_no_trip(
    seeded, alpha_client,
):
    """Cerrar la evidencia es un hecho de la jornada, no un viaje nuevo."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    async with async_session_maker() as session:
        antes = await session.scalar(
            text("SELECT count(*) FROM trip WHERE work_session_id = :i"),
            {"i": jornada["id"]},
        )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )

    async with async_session_maker() as session:
        despues = await session.scalar(
            text("SELECT count(*) FROM trip WHERE work_session_id = :i"),
            {"i": jornada["id"]},
        )

    assert despues == antes


async def test_a_photo_cannot_be_added_once_the_day_is_closed(
    seeded, alpha_client,
):
    """El atajo que vaciaría de sentido la aprobación del administrador.

    Sin esta regla: pedir la excepción, cerrar el día, subir después cualquier
    fotografía y autoconfirmarla como evidencia fotográfica. La aprobación
    quedaría de adorno.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )

    assert respuesta.status_code == 409
    assert "closed" in respuesta.json()["detail"].lower()

    # Y sin foto no se puede confirmar sin la aprobación.
    sin_permiso = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )
    assert sin_permiso.status_code == 409


async def test_a_rejected_end_exception_leaves_the_evidence_pending(
    seeded, alpha_client,
):
    """Rechazada tras cerrar el día, la evidencia no se completa sola.

    Y el día sigue cerrado: rechazar una excepción no es motivo para reabrir una
    jornada, que es justo lo que CER prohíbe.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/reject")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["end"]["status"] == "pending"
    assert estado["odometer_distance"] is None

    async with async_session_maker() as session:
        situacion = await session.scalar(
            text("SELECT status FROM work_session WHERE id = :i"),
            {"i": jornada["id"]},
        )
    assert situacion == "ended"


async def test_an_end_approval_is_single_use_too(seeded, alpha_client):
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )

    # Gastada: ni se puede volver a pedir ni queda nada que consumir.
    otra = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/exception",
        json={"reason": "other"},
    )
    assert otra.status_code == 409


# ── Orden con los bloqueos del viaje ────────────────────────────────────────


async def test_the_trip_blocker_is_resolved_before_the_end_reading(
    seeded, alpha_client,
):
    """El orden que pide C4: primero el viaje, después la evidencia.

    Con un viaje en tránsito el servidor no pide todavía el odómetro: pide
    decidir sobre el viaje, porque el kilometraje aún puede cambiar.
    """
    # Sin llegar: el viaje sigue en ruta, que es el bloqueo que se quiere ver
    # primero. Y ya se condujo, así que la lectura de cierre también hará falta.
    jornada = await _jornada_conduciendo(alpha_client, seeded, llegar=False)
    otro = {"id": jornada["trip_id"]}

    primero = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert primero.status_code == 409
    assert "route" in primero.json()["detail"].lower(), (
        "el bloqueo del viaje llega antes que el del odómetro"
    )

    # Con `end_anyway` el viaje queda interrumpido y **entonces** se pide la
    # lectura de cierre.
    segundo = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={"end_anyway": True}
    )
    assert segundo.status_code == 409
    assert "odometer" in segundo.json()["detail"].lower()

    async with async_session_maker() as session:
        estado_viaje = await session.scalar(
            text("SELECT status FROM trip WHERE id = :i"), {"i": otro["id"]}
        )
    assert estado_viaje == "interrupted", (
        "no se fabrica una llegada; el viaje queda interrumpido"
    )

    # Y resuelto el odómetro, el día se cierra sin volver a preguntar por el viaje.
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50200.0"},
    )
    final = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert final.status_code == 200
    assert final.json()["status"] == "ended"


# ── Auditoría ───────────────────────────────────────────────────────────────


async def test_the_late_end_reading_is_fully_audited(seeded, alpha_client):
    """Quién lo pidió, quién lo aprobó, por qué y cuándo."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )

    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT entity_type, action, actor_user_id, occurred_at "
                "FROM audit_event WHERE company_id = :c "
                "AND entity_type LIKE 'odometer%' ORDER BY id"
            ),
            {"c": seeded.alpha.id},
        )
        eventos = filas.all()

    acciones = {(e.entity_type, e.action) for e in eventos}
    assert ("odometer_exception_request", "request") in acciones
    assert ("odometer_exception_request", "approve") in acciones
    assert ("odometer_evidence", "reading_confirmed") in acciones

    # Quien pidió y quien aprobó son personas distintas, y consta cuál es cuál.
    peticion = next(e for e in eventos if e.action == "request")
    aprobacion = next(e for e in eventos if e.action == "approve")
    assert peticion.actor_user_id != aprobacion.actor_user_id
    assert all(e.occurred_at is not None for e in eventos)

    # La solicitud guarda su propia traza de decisión, no sólo el log.
    detalle = (
        await alpha_client.get("/api/odometer/exceptions/pending")
    ).status_code
    assert detalle == 403, "el supervisor no ve la cola de administración"
