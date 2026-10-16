"""
El odómetro de cierre y su relación con `End Work` (RTE04-C4).

La regla que este archivo defiende: **sin lectura, el día no cierra**
---------------------------------------------------------------------
Las dos guardas de odómetro exigen ahora lo mismo —una lectura confirmada, por
foto o manual—, y lo que las diferencia es sólo cuánto se espera para poder
teclearla:

* en el **inicio**, teclear sin foto necesita la aprobación de un
  administrador: ahí el control protege que nadie salga a conducir sin saber de
  dónde partió;
* en el **cierre**, la excepción se aprueba **al enviarse**. El supervisor ya no
  va a conducir, y la lectura final es obligatoria para terminar, así que
  hacerle esperar una decisión ajena le dejaría sin poder teclear ni cerrar.

Qué había antes, y por qué se cambió
-------------------------------------
Antes regía la **Opción B**: bastaba con *haber pedido* la excepción para
cerrar el día, de modo que la jornada nunca quedaba retenida esperando a un
administrador. La intención era buena —un `ended_at` retenido es un dato
laboral falseado— y el efecto en campo fue el contrario del buscado: enviar la
solicitud cerraba la jornada **saltándose la lectura**, `Ending Odometer`
quedaba `Missing` para siempre y la distancia del día no se podía afirmar.
Pedir la excepción se convirtió en la forma de no dar la lectura.

La corrección mantiene las dos propiedades que la Opción B protegía —la jornada
se cierra a su hora real y no se reabre— y añade la que faltaba: la evidencia
no puede quedarse vacía. Lo que desapareció es la espera, no la flexibilidad.

Las consecuencias que se comprueban aquí
-----------------------------------------
1. pedir la excepción de cierre **no** cierra el día;
2. el campo manual está disponible en el acto, y confirmarlo sí cierra;
3. una lectura de cierre menor que la de inicio se rechaza;
4. cerrado el día, no se puede añadir una fotografía después;
5. las excepciones de **cierre** ya no pasan por la cola del administrador
   —nacen aprobadas—, mientras que las de **inicio** siguen pasando.
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


async def _evidencia_de_cierre(cliente, session_id: int) -> dict:
    estado = (await cliente.get(f"/api/odometer/sessions/{session_id}")).json()
    return estado["end"]


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


# ── «I can't take a photo» lleva al campo manual, no al cierre ──────────────


async def test_requesting_the_end_exception_does_not_end_the_day(
    seeded, alpha_client,
):
    """El defecto que se corrige, reproducido como test (AC1, AC4, AC5).

    Antes: enviar la solicitud cerraba la jornada y la evidencia de cierre
    quedaba `Missing` para siempre. Ahora la jornada **sigue activa** y lo que
    cambia es que el supervisor ya puede teclear: la excepción nace aprobada.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    assert solicitud["status"] == "approved", (
        "el cierre no espera a nadie: la solicitud se aprueba al enviarse"
    )

    # Pedirla no cierra nada por sí misma.
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active", (
        "pedir la excepción cerró la jornada: es el defecto que se corrige"
    )

    # Y el servidor sigue negando el cierre, porque todavía no hay lectura.
    rechazo = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert rechazo.status_code == 409
    assert "odometer" in rechazo.json()["detail"].lower()

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["end"]["status"] == "exception_approved"
    assert estado["end"]["confirmed_reading"] is None


async def test_the_manual_end_reading_then_closes_the_day(seeded, alpha_client):
    """El flujo completo que pide la instrucción (AC2, AC3).

    `I can't take a photo` → `Submit Request` → lectura manual → `Confirm` →
    `End Work`. Y la evidencia queda marcada como manual para siempre, que es
    lo que impide que una lectura sin foto pase por evidencia fotográfica.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/confirm",
            json={"reading": "50088.0"},
        )
    ).json()

    assert confirmada["status"] == "manual_exception_confirmed"
    assert confirmada["evidence_method"] == "manual_no_photo"

    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 200
    assert cierre.json()["status"] == "ended"
    assert cierre.json()["ended_at"] is not None

    # Y con las dos lecturas ya hay distancia que afirmar.
    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert Decimal(estado["odometer_distance"]) == Decimal("88.0")


async def test_a_manual_end_reading_below_the_start_is_rejected(
    seeded, alpha_client,
):
    """AC6, por la vía manual: la que no estaba cubierta.

    El camino de foto ya lo comprobaba otro archivo. Lo que aquí importa es que
    la excepción no sea también una excepción a la coherencia: la lectura entra
    sin foto, pero no sin sentido.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    rechazo = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "49999.0"},
    )

    assert rechazo.status_code == 422
    assert "lower" in rechazo.json()["detail"].lower()

    # Y el día sigue abierto: una lectura rechazada no resuelve nada.
    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 409

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active"


async def test_the_day_stays_open_until_the_reading_is_confirmed(
    seeded, alpha_client,
):
    """AC4 en su forma más dura: ningún intento de cierre pasa sin lectura.

    Se intenta tres veces, incluido con `end_anyway` —que es el atajo que
    existe para el viaje en ruta—, porque un bloqueo que se salta con una
    bandera no es un bloqueo.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    for cuerpo in ({}, {"end_anyway": True}, {}):
        respuesta = await alpha_client.post(
            f"/api/worksessions/{jornada['id']}/end", json=cuerpo
        )
        assert respuesta.status_code == 409, f"cerró con {cuerpo}"

    async with async_session_maker() as session:
        situacion = await session.scalar(
            text("SELECT status FROM work_session WHERE id = :i"),
            {"i": jornada["id"]},
        )
    assert situacion == "active"
    assert (
        await _evidencia_de_cierre(alpha_client, jornada["id"])
    )["status"] == "exception_approved", "la evidencia no se resolvió sola"


async def test_an_unreviewed_request_from_before_the_fix_can_still_be_typed(
    seeded, alpha_client,
):
    """Las jornadas que quedaron a medias con la regla anterior.

    En producción hay solicitudes de cierre en `requested` que nunca se
    revisaron, porque con la Opción B el día ya se había cerrado. Con la regla
    nueva, un estado así sin salida dejaría al supervisor atrapado: no podría
    teclear —si se exigiera la aprobación— ni cerrar el día. En el cierre basta
    con que la solicitud exista.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    # Se retrocede el estado a mano para reproducir el dato heredado: es la
    # única forma de tenerlo, porque el código ya no lo produce.
    async with async_session_maker() as session:
        await session.execute(
            text(
                "UPDATE odometer_exception_request SET status = 'requested', "
                "decided_at = NULL WHERE id = :i"
            ),
            {"i": solicitud["id"]},
        )
        await session.execute(
            text(
                "UPDATE odometer_evidence SET status = 'exception_requested' "
                "WHERE work_session_id = :i AND evidence_type = 'end'"
            ),
            {"i": jornada["id"]},
        )
        await session.commit()

    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/end/confirm",
            json={"reading": "50044.0"},
        )
    ).json()
    assert confirmada["status"] == "manual_exception_confirmed"

    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 200


async def test_the_start_exception_still_waits_for_an_administrator(
    seeded, alpha_client,
):
    """El control que **no** se tocó, y que la corrección podría haber roto.

    En el inicio la aprobación protege algo que el cierre no: que nadie salga a
    conducir sin saber de dónde partió. Así que la excepción de inicio sigue
    naciendo `requested`, sigue entrando en la cola del administrador y sigue
    sin permitir teclear hasta que alguien decida.
    """
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
                "make": "Ford", "model": "Transit", "year": 2023, "unit": "V-STRT",
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
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "camera_unavailable"},
        )
    ).json()

    assert solicitud["status"] == "requested", (
        "el inicio no se autoaprueba: ahí la espera protege la conducción"
    )

    sin_aprobar = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )
    assert sin_aprobar.status_code == 409


async def test_the_end_exception_no_longer_reaches_the_admin_queue(
    seeded, alpha_client,
):
    """Una consecuencia declarada del cambio, comprobada en vez de supuesta.

    Si la excepción de cierre nace aprobada, deja de haber nada que decidir y
    por tanto deja de aparecer en la cola. La de inicio sí aparece, y esa
    asimetría es exactamente la regla — conviene que un cambio futuro que la
    rompa haga fallar algo.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    solicitud = await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cola = (await alpha_client.get("/api/odometer/exceptions/pending")).json()

    assert solicitud["id"] not in [p["id"] for p in cola]

    # Y no se puede decidir sobre ella: ya está decidida.
    tardia = await alpha_client.post(
        f"/api/odometer/exceptions/{solicitud['id']}/approve"
    )
    assert tardia.status_code == 409


async def test_confirming_the_manual_end_reading_creates_no_trip(
    seeded, alpha_client,
):
    """Cerrar la evidencia es un hecho de la jornada, no un viaje nuevo."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    async with async_session_maker() as session:
        antes = await session.scalar(
            text("SELECT count(*) FROM trip WHERE work_session_id = :i"),
            {"i": jornada["id"]},
        )

    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    async with async_session_maker() as session:
        despues = await session.scalar(
            text("SELECT count(*) FROM trip WHERE work_session_id = :i"),
            {"i": jornada["id"]},
        )

    assert despues == antes


async def test_a_photo_cannot_be_added_once_the_day_is_closed(
    seeded, alpha_client,
):
    """El atajo que convertiría la evidencia manual en fotográfica.

    Sin esta regla: teclear la lectura sin foto, cerrar el día, subir después
    cualquier fotografía y que la evidencia pasara por fotográfica. El estado
    `manual_no_photo` quedaría desmentido por una foto posterior que nadie
    comparó con nada.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )

    assert respuesta.status_code == 409
    assert "closed" in respuesta.json()["detail"].lower()

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["end"]["evidence_method"] == "manual_no_photo", (
        "la foto tardía no puede reescribir cómo se obtuvo la lectura"
    )


async def test_the_manual_end_exception_is_single_use_too(seeded, alpha_client):
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
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


async def test_the_manual_end_reading_is_fully_audited(seeded, alpha_client):
    """Qué se pidió, por qué, cómo se aprobó y quién tecleó.

    Lo que cambia respecto de antes: ya no hay una aprobación humana que
    auditar en el cierre, así que el evento es `auto_approve` y **nombra su
    motivo**. Eso importa más de lo que parece: quien lea la auditoría dentro
    de un año tiene que poder distinguir una aprobación que tomó una persona de
    una que concedió una regla, y cuál de las dos reglas fue.
    """
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50010.0"},
    )
    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT entity_type, action, actor_user_id, occurred_at, summary "
                "FROM audit_event WHERE company_id = :c "
                "AND entity_type LIKE 'odometer%' ORDER BY id"
            ),
            {"c": seeded.alpha.id},
        )
        eventos = filas.all()

    acciones = {(e.entity_type, e.action) for e in eventos}
    assert ("odometer_exception_request", "request") in acciones
    assert ("odometer_exception_request", "auto_approve") in acciones
    assert ("odometer_evidence", "reading_confirmed") in acciones
    assert ("odometer_exception_request", "approve") not in acciones, (
        "nadie aprobó esto a mano: decirlo así sería inventar un decisor"
    )

    # El motivo de la aprobación automática consta, y es el del cierre.
    automatica = next(e for e in eventos if e.action == "auto_approve")
    assert "required to end the day" in automatica.summary

    assert all(e.occurred_at is not None for e in eventos)

    # Y el supervisor sigue sin ver la cola de administración.
    detalle = (
        await alpha_client.get("/api/odometer/exceptions/pending")
    ).status_code
    assert detalle == 403, "el supervisor no ve la cola de administración"


# ── «Keep working» retira el cierre pedido ──────────────────────────────────
#
# El reporte de campo: un supervisor pulsó `End Work` sin querer mientras
# conducía y `Keep working` no hacía nada. `End Work` deja la lectura de cierre
# `PENDING` antes de rechazar el cierre, la pantalla decide la fase por esa
# fila, y no había forma de retirarla: la única salida era cerrar el día.


async def _end_work_rechazado(cliente, seeded) -> dict:
    """Jornada conduciendo y un `End Work` que el servidor rechazó por la lectura."""
    jornada = await _jornada_conduciendo(cliente, seeded)
    rechazo = await cliente.post(f"/api/worksessions/{jornada['id']}/end", json={})
    assert rechazo.status_code == 409
    assert (await _evidencia_de_cierre(cliente, jornada["id"]))["status"] == "pending"
    return jornada


def _retirar(jornada: dict) -> str:
    return f"/api/odometer/sessions/{jornada['id']}/end/withdraw"


async def test_keep_working_withdraws_the_end_reading_and_work_goes_on(
    seeded, alpha_client,
):
    """El caso reportado, de punta a punta: se retira, se sigue y se puede cerrar."""
    jornada = await _end_work_rechazado(alpha_client, seeded)

    respuesta = await alpha_client.post(_retirar(jornada))

    assert respuesta.status_code == 200
    assert respuesta.json()["end"] is None, "la captura de cierre tiene que desaparecer"
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active"

    # Sigue trabajando: puede salir a otro destino.
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "home"})
    ).json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text

    # Y cuando de verdad termina, la lectura de cierre se vuelve a pedir.
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    otra_vez = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert otra_vez.status_code == 409
    assert (await _evidencia_de_cierre(alpha_client, jornada["id"]))["status"] == "pending"


async def test_keep_working_without_a_pending_end_changes_nothing(
    seeded, alpha_client,
):
    """Sin `End Work` previo no hay nada que retirar, y no es un error."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)

    respuesta = await alpha_client.post(_retirar(jornada))

    assert respuesta.status_code == 200
    assert respuesta.json()["end"] is None
    assert respuesta.json()["start"]["status"] == "photo_confirmed"


async def test_keep_working_does_not_discard_an_end_photo(seeded, alpha_client):
    """Con la foto ya subida hay evidencia, y descartarla no está decidido."""
    jornada = await _end_work_rechazado(alpha_client, seeded)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    antes = await _evidencia_de_cierre(alpha_client, jornada["id"])

    respuesta = await alpha_client.post(_retirar(jornada))

    assert respuesta.status_code == 409
    assert "ending odometer" in respuesta.json()["detail"].lower()
    despues = await _evidencia_de_cierre(alpha_client, jornada["id"])
    assert despues == antes, "la foto y su fila tienen que quedar intactas"


async def test_keep_working_does_not_discard_an_end_exception(seeded, alpha_client):
    """Con la excepción pedida, igual: es evidencia y no se toca."""
    jornada = await _end_work_rechazado(alpha_client, seeded)
    await _excepcion_de_cierre(alpha_client, seeded, jornada["id"])

    respuesta = await alpha_client.post(_retirar(jornada))

    assert respuesta.status_code == 409
    estado = await _evidencia_de_cierre(alpha_client, jornada["id"])
    assert estado["status"] in ("exception_requested", "exception_approved")


async def test_keep_working_cannot_reopen_an_ended_day(seeded, alpha_client):
    """Cerrado el día no hay nada que seguir: no se reabre por esta vía."""
    jornada = await _jornada_conduciendo(alpha_client, seeded)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "50100.0"},
    )
    cierre = await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})
    assert cierre.status_code == 200

    respuesta = await alpha_client.post(_retirar(jornada))

    assert respuesta.status_code == 409
    estado = await _evidencia_de_cierre(alpha_client, jornada["id"])
    assert estado["status"] == "photo_confirmed", "la lectura del cierre se conserva"


async def test_keep_working_only_on_your_own_day(seeded, alpha_client, beta_client):
    """Otra persona de la compañía, u otra compañía: 404, sin distinguir."""
    jornada = await _end_work_rechazado(alpha_client, seeded)

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    ajena = await alpha_client.post(_retirar(jornada))
    assert ajena.status_code == 404

    await beta_client.login(seeded.beta.users["supervisor"].email)
    otro_tenant = await beta_client.post(_retirar(jornada))
    assert otro_tenant.status_code == 404

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (await _evidencia_de_cierre(alpha_client, jornada["id"]))["status"] == "pending"


async def test_keep_working_is_audited(seeded, alpha_client):
    """Retirar el cierre deja traza: quién, cuándo y que siguió trabajando."""
    jornada = await _end_work_rechazado(alpha_client, seeded)
    await alpha_client.post(_retirar(jornada))

    async with async_session_maker() as session:
        evento = (
            await session.execute(
                text(
                    "SELECT actor_user_id, occurred_at, summary FROM audit_event "
                    "WHERE company_id = :c AND entity_type = 'odometer_evidence' "
                    "AND action = 'end_withdrawn'"
                ),
                {"c": seeded.alpha.id},
            )
        ).one()

    assert evento.actor_user_id == seeded.alpha.users["supervisor"].id
    assert evento.occurred_at is not None
    assert "kept working" in evento.summary
