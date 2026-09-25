"""
Evidencia de odómetro (RTE04-C3/C4).

Lo que este archivo demuestra, y por qué cada bloque existe
-------------------------------------------------------------
* **`Start Work` ≠ `Start Driving`.** Abrir la jornada deja la lectura
  `PENDING` si hay vehículo, pero no bloquea trabajar en lo que no implique
  conducir.
* **La guarda es del servidor.** `Start Trip` no sale con la lectura sin
  resolver, y da igual lo que muestre la pantalla.
* **El OCR es asistivo.** Sugiere; la persona confirma. Sin sugerencia el
  supervisor teclea lo que ve y **sigue siendo evidencia fotográfica**, sin
  aprobación de nadie — eso es lo que separa "manual normal" de "excepción".
* **La excepción es de un solo uso y acotada.** La de inicio no autoriza el
  cierre, la de un día no sirve para otro, y consumida no vuelve a valer.
* **Nada se inventa.** Sin vehículo, `NOT_REQUIRED`. Sin lectura de cierre, no
  hay distancia — no una distancia cero. Y una lectura de cierre menor que la
  de inicio se rechaza en vez de producir una distancia negativa.
* **La foto es privada.** Se sirve sólo a quien es dueño de esa jornada.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.database import async_session_maker
from app.routers_api.odometer.models import OdometerEvidence
from app.routers_api.odometer.ocr import set_odometer_reader
from tests.integration.conftest import TEST_PASSWORD, TenantClient


pytestmark = pytest.mark.integration


#: Un PNG de 1x1 válido. Lo que se prueba es el contrato de la evidencia, no la
#: calidad de una fotografía.
FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


class _LectorFijo:
    """Un OCR que siempre sugiere lo mismo, para probar la rama de sugerencia."""

    def __init__(self, valor):
        self.valor = valor

    def suggest(self, *, image, content_type):  # noqa: ARG002 - firma del puerto
        return self.valor


@pytest.fixture(autouse=True)
def _sin_ocr_por_defecto():
    """Cada test arranca sin OCR, que es el despliegue por defecto."""
    from app.routers_api.odometer.ocr import NoSuggestionReader

    set_odometer_reader(NoSuggestionReader())
    yield
    set_odometer_reader(NoSuggestionReader())


# ── Ayudas ──────────────────────────────────────────────────────────────────


async def _vehiculo_asignado(cliente, seeded) -> dict:
    """Deja al supervisor con un vehículo, que es lo que hace falta lectura."""
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
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": "V-ODO",
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await cliente.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    return vehiculo


async def _jornada_con_vehiculo(cliente, seeded) -> dict:
    await _vehiculo_asignado(cliente, seeded)
    await cliente.login(seeded.alpha.users["supervisor"].email)
    return (await cliente.post("/api/worksessions", json={})).json()


async def _subir_foto(cliente, session_id: int, tipo: str = "start"):
    return await cliente.post(
        f"/api/odometer/sessions/{session_id}/{tipo}/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )


# ── Estado inicial ──────────────────────────────────────────────────────────


async def test_start_work_leaves_the_reading_pending_without_blocking_work(
    seeded, alpha_client,
):
    """Abrir la jornada no pide odómetro: arrancar a trabajar no es conducir."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()

    assert estado["start"]["status"] == "pending"
    assert estado["start"]["confirmed_reading"] is None
    assert estado["odometer_distance"] is None

    # Y se puede seguir trabajando: planificar no requiere lectura.
    viaje = await alpha_client.post("/api/trips", json={"purpose": "office"})
    assert viaje.status_code == 200


async def test_without_a_session_vehicle_the_reading_is_not_required(
    seeded, alpha_client,
):
    """Sin vehículo no se fabrica una lectura: se dice que no aplica."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    assert jornada["vehicle_id"] is None

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "not_required"
    assert estado["start"]["confirmed_reading"] is None


# ── La guarda de Start Trip ─────────────────────────────────────────────────


async def test_start_trip_is_blocked_while_the_reading_is_unresolved(
    seeded, alpha_client,
):
    """La guarda dura, comprobada contra el servidor."""
    await _jornada_con_vehiculo(alpha_client, seeded)
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()

    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    assert respuesta.status_code == 409
    assert "odometer" in respuesta.json()["detail"].lower()


async def test_start_trip_proceeds_once_the_reading_is_confirmed(
    seeded, alpha_client,
):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "128437.0"},
    )

    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "in_transit"


async def test_a_session_without_vehicle_is_never_blocked(seeded, alpha_client):
    """`NOT_REQUIRED` resuelve la guarda sin lectura inventada."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()

    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert respuesta.status_code == 200


# ── Foto, OCR y confirmación ────────────────────────────────────────────────


async def test_photo_plus_manual_confirmation_works_without_any_ocr(
    seeded, alpha_client,
):
    """Sin sugerencia el supervisor teclea, y sigue siendo evidencia de foto.

    Es la distinción central: manual **con** foto no necesita a nadie.
    """
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    subida = (await _subir_foto(alpha_client, jornada["id"])).json()
    assert subida["ocr_suggestion"] is None, "sin OCR no hay sugerencia, y es normal"

    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/confirm",
            json={"reading": "128437.0"},
        )
    ).json()

    assert confirmada["status"] == "photo_confirmed"
    assert confirmada["evidence_method"] == "photo"
    assert Decimal(confirmada["confirmed_reading"]) == Decimal("128437.0")


async def test_the_ocr_suggestion_and_the_confirmed_value_stay_distinguishable(
    seeded, alpha_client,
):
    """Se puede saber qué vio la máquina y qué confirmó la persona."""
    set_odometer_reader(_LectorFijo(Decimal("128437.0")))

    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    subida = (await _subir_foto(alpha_client, jornada["id"])).json()
    assert Decimal(subida["ocr_suggestion"]) == Decimal("128437.0")

    # El supervisor corrige: la máquina leyó mal un dígito.
    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/confirm",
            json={"reading": "128437.5"},
        )
    ).json()

    assert Decimal(confirmada["ocr_detected_reading"]) == Decimal("128437.0")
    assert Decimal(confirmada["confirmed_reading"]) == Decimal("128437.5")
    assert confirmada["status"] == "photo_confirmed", (
        "corregir al OCR no convierte la evidencia en una excepción"
    )


async def test_a_non_image_upload_is_rejected(seeded, alpha_client):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("nota.txt", b"no soy una foto", "text/plain")},
    )
    assert respuesta.status_code == 422


# ── Excepción sin foto ──────────────────────────────────────────────────────


async def test_manual_entry_is_impossible_without_an_approved_exception(
    seeded, alpha_client,
):
    """No hay atajo: sin foto y sin permiso, no se teclea."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "100.0"},
    )

    assert respuesta.status_code == 409
    assert "photo" in respuesta.json()["detail"].lower()


async def test_a_requested_exception_does_not_unlock_start_trip(seeded, alpha_client):
    """Pedirlo no es tenerlo: el viaje sigue bloqueado mientras se decide."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/exception",
        json={"reason": "camera_unavailable"},
    )

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "exception_requested"

    # Un propósito sin lista obligatoria, para que el único bloqueo posible sea
    # el odómetro y no el dato de planificación.
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    bloqueado = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert bloqueado.status_code == 409


async def test_the_full_exception_flow_unlocks_exactly_one_manual_entry(
    seeded, alpha_client,
):
    """Pedir, aprobar, teclear. Y la autorización queda consumida."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "no_usable_photo", "reason_note": "Glare on the dash"},
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    aprobada = (
        await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")
    ).json()
    assert aprobada["status"] == "approved"

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    confirmada = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/confirm",
            json={"reading": "90210.0"},
        )
    ).json()

    assert confirmada["status"] == "manual_exception_confirmed"
    assert confirmada["evidence_method"] == "manual_no_photo", (
        "una lectura sin foto no puede parecer evidencia fotográfica"
    )

    # Y el viaje ya puede salir.
    viaje = (await alpha_client.post("/api/trips", json={"purpose": "office"})).json()
    # Office exige su valor de lista; el odómetro ya no es el bloqueo.
    arranque = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert arranque.status_code == 422
    assert "purpose" in arranque.json()["detail"].lower()


async def test_a_consumed_approval_cannot_be_reused(seeded, alpha_client):
    """Un solo uso. Gastada, hay que volver a pedirla."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )

    # La evidencia ya está resuelta, así que ni siquiera se puede pedir otra.
    otra = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/exception",
        json={"reason": "other"},
    )
    assert otra.status_code == 409


async def test_a_start_approval_does_not_authorize_the_end_reading(
    seeded, alpha_client,
):
    """El alcance está en las columnas: inicio no autoriza cierre."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "camera_unavailable"},
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "5000.0"},
    )

    assert respuesta.status_code == 409, (
        "la aprobación de inicio no puede desbloquear el cierre"
    )


async def test_an_approval_from_one_session_does_not_authorize_another(
    seeded, alpha_client,
):
    """Ni de un día para otro."""
    primera = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{primera['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")

    # Se cierra la jornada y se abre otra.
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(f"/api/worksessions/{primera['id']}/end", json={})
    segunda = (await alpha_client.post("/api/worksessions", json={})).json()

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{segunda['id']}/start/confirm",
        json={"reading": "1.0"},
    )
    assert respuesta.status_code == 409


async def test_a_rejected_exception_leaves_the_trip_blocked(seeded, alpha_client):
    """Rechazar devuelve a pendiente: hace falta evidencia válida."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    rechazada = (
        await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/reject")
    ).json()
    assert rechazada["status"] == "rejected"

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "pending"

    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    bloqueado = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert bloqueado.status_code == 409


async def test_requesting_twice_does_not_open_two_doors(seeded, alpha_client):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    primera = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()
    segunda = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()

    assert segunda["id"] == primera["id"]


# ── Autorización ────────────────────────────────────────────────────────────


async def test_a_supervisor_cannot_approve_their_own_exception(seeded, alpha_client):
    """Aprobar es autoridad de administración, no de campo."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()

    respuesta = await alpha_client.post(
        f"/api/odometer/exceptions/{solicitud['id']}/approve"
    )
    assert respuesta.status_code == 403


async def test_the_pending_queue_requires_the_admin_capability(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (
        await alpha_client.get("/api/odometer/exceptions/pending")
    ).status_code == 403

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (
        await alpha_client.get("/api/odometer/exceptions/pending")
    ).status_code == 200


async def test_another_tenant_cannot_decide_a_request(seeded, alpha_client):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "other"},
        )
    ).json()

    async with TenantClient("beta") as beta:
        await beta.login(seeded.beta.users["route_admin"].email)
        respuesta = await beta.post(
            f"/api/odometer/exceptions/{solicitud['id']}/approve"
        )

    assert respuesta.status_code == 404


async def test_another_supervisor_cannot_read_the_photo(seeded, alpha_client):
    """La foto puede mostrar matrícula y kilometraje: sólo su dueño la ve."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])

    async with async_session_maker() as session:
        evidencia = await session.scalar(
            select(OdometerEvidence).where(
                OdometerEvidence.work_session_id == jornada["id"]
            )
        )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    otro = (
        await alpha_client.post(
            "/api/users",
            json={
                "username": "otrosupodo",
                "email": "otrosupodo@alpha.example.com",
                "first_name": "Otro", "last_name": "Sup",
                "password": TEST_PASSWORD,
                "role_id": seeded.alpha.roles["supervisor"],
            },
        )
    ).json()

    async with TenantClient("alpha") as ajeno:
        await ajeno.login(otro["email"])
        respuesta = await ajeno.get(f"/api/odometer/evidence/{evidencia.id}/photo")

    assert respuesta.status_code == 404, "ni se confirma que exista"


async def test_the_owner_can_read_their_own_photo(seeded, alpha_client):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])

    async with async_session_maker() as session:
        evidencia = await session.scalar(
            select(OdometerEvidence).where(
                OdometerEvidence.work_session_id == jornada["id"]
            )
        )

    respuesta = await alpha_client.get(
        f"/api/odometer/evidence/{evidencia.id}/photo"
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("image/")
    assert "no-store" in respuesta.headers.get("cache-control", "")


# ── Lectura de cierre y distancia ───────────────────────────────────────────


async def test_the_end_reading_is_not_required_without_any_vehicle_trip(
    seeded, alpha_client,
):
    """Sin conducir no hay distancia que cerrar: no se piden fotos vacías."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )

    from app.routers_api.odometer.service import OdometerService

    fin = await OdometerService.end_requirement(
        company_id=seeded.alpha.id, work_session_id=jornada["id"]
    )
    assert fin.status == "not_required"

    _, _, distancia = await OdometerService.session_state(
        company_id=seeded.alpha.id, work_session_id=jornada["id"]
    )
    assert distancia is None, "no se fabrica una distancia cero"


async def test_the_end_reading_is_required_after_a_vehicle_trip(seeded, alpha_client):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    from app.routers_api.odometer.service import OdometerService

    fin = await OdometerService.end_requirement(
        company_id=seeded.alpha.id, work_session_id=jornada["id"]
    )
    assert fin.status == "pending", "si se condujo, hay que cerrar la lectura"


async def test_an_end_reading_below_the_start_is_rejected(seeded, alpha_client):
    """Nunca una distancia negativa, y nunca una corrección silenciosa."""
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "5000.0"},
    )
    await _subir_foto(alpha_client, jornada["id"], "end")

    respuesta = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "4000.0"},
    )

    assert respuesta.status_code == 422
    assert "lower" in respuesta.json()["detail"].lower()


async def test_the_distance_derives_only_from_two_valid_readings(
    seeded, alpha_client,
):
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["odometer_distance"] is None, "con una sola lectura no hay distancia"

    await _subir_foto(alpha_client, jornada["id"], "end")
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "1042.5"},
    )

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert Decimal(estado["odometer_distance"]) == Decimal("42.5")


async def test_the_odometer_never_produces_routing_mileage(seeded, alpha_client):
    """No existe ningún campo de millaje de ruta que el odómetro pueda tocar.

    La separación de autoridades se sostiene porque el otro dominio **no está
    construido**: no hay nada que sobrescribir, y este checkpoint no lo crea.
    """
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "1000.0"},
    )

    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    assert "miles" not in viaje
    assert "routing_mileage" not in viaje
    assert "distance" not in viaje


# ── Auditoría ───────────────────────────────────────────────────────────────


async def test_the_whole_exception_lifecycle_is_audited(seeded, alpha_client):
    from sqlalchemy import text

    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "camera_unavailable"},
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(f"/api/odometer/exceptions/{solicitud['id']}/approve")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "777.0"},
    )

    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT entity_type, action FROM audit_event "
                "WHERE company_id = :c AND entity_type LIKE 'odometer%'"
            ),
            {"c": seeded.alpha.id},
        )
    eventos = {(t, a) for t, a in filas.all()}

    assert ("odometer_exception_request", "request") in eventos
    assert ("odometer_exception_request", "approve") in eventos
    assert ("odometer_evidence", "reading_confirmed") in eventos


async def test_the_audit_never_stores_photo_bytes(seeded, alpha_client):
    """Una foto de odómetro no acaba en un log."""
    from sqlalchemy import text

    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])

    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT changes::text FROM audit_event "
                "WHERE company_id = :c AND entity_type = 'odometer_evidence'"
            ),
            {"c": seeded.alpha.id},
        )
    for (cambios,) in filas.all():
        assert "PNG" not in cambios
        assert "storage_key" not in cambios


# ── Concurrencia e idempotencia (§10 de las instrucciones 003) ────────────────


async def test_two_admins_deciding_at_once_produce_one_decision(
    seeded, alpha_client,
):
    """Aprobar y rechazar a la vez no puede dejar la solicitud en los dos sitios.

    Dos administradores mirando la misma cola es lo normal, no un caso raro. El
    guardián es el estado: sólo una solicitud `requested` se puede decidir, así
    que la segunda llamada recibe 409 y la autorización de un solo uso sigue
    siendo de un solo uso.
    """
    import asyncio

    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    solicitud = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/exception",
            json={"reason": "camera_unavailable"},
        )
    ).json()

    async with TenantClient("alpha") as uno, TenantClient("alpha") as otro:
        await uno.login(seeded.alpha.users["route_admin"].email)
        await otro.login(seeded.alpha.users["route_admin"].email)

        primera, segunda = await asyncio.gather(
            uno.post(f"/api/odometer/exceptions/{solicitud['id']}/approve"),
            otro.post(f"/api/odometer/exceptions/{solicitud['id']}/reject"),
            return_exceptions=True,
        )

    codigos = sorted(
        r.status_code for r in (primera, segunda) if not isinstance(r, Exception)
    )
    assert codigos == [200, 409], f"una decide y la otra se rechaza: {codigos}"

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    async with async_session_maker() as session:
        estados = (
            await session.execute(
                text(
                    "SELECT status FROM odometer_exception_request "
                    "WHERE company_id = :c"
                ),
                {"c": seeded.alpha.id},
            )
        ).scalars().all()
    assert len(estados) == 1
    assert estados[0] in ("approved", "rejected")


async def test_requesting_the_exception_concurrently_opens_one_door(
    seeded, alpha_client,
):
    """El índice parcial es el que aguanta, no el orden de las peticiones."""
    import asyncio

    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    async with TenantClient("alpha") as uno, TenantClient("alpha") as otro:
        await uno.login(seeded.alpha.users["supervisor"].email)
        await otro.login(seeded.alpha.users["supervisor"].email)

        await asyncio.gather(
            uno.post(
                f"/api/odometer/sessions/{jornada['id']}/start/exception",
                json={"reason": "other"},
            ),
            otro.post(
                f"/api/odometer/sessions/{jornada['id']}/start/exception",
                json={"reason": "other"},
            ),
            return_exceptions=True,
        )

    async with async_session_maker() as session:
        cuantas = await session.scalar(
            text(
                "SELECT count(*) FROM odometer_exception_request "
                "WHERE company_id = :c AND status IN ('requested','approved')"
            ),
            {"c": seeded.alpha.id},
        )
    assert cuantas == 1, "dos peticiones simultáneas no abren dos puertas"


async def test_replaying_the_same_confirmation_writes_one_reading(
    seeded, alpha_client,
):
    """Reenviar con la misma clave de idempotencia no duplica ni contradice.

    La cola durable reintenta, así que una confirmación puede llegar dos veces.
    """
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)
    await _subir_foto(alpha_client, jornada["id"])

    clave = "odo-confirm-replay-1"
    primera = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "4321.0"},
        headers={"Idempotency-Key": clave},
    )
    segunda = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "4321.0"},
        headers={"Idempotency-Key": clave},
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert Decimal(segunda.json()["confirmed_reading"]) == Decimal("4321.0")

    async with async_session_maker() as session:
        filas = await session.scalar(
            text(
                "SELECT count(*) FROM odometer_evidence "
                "WHERE company_id = :c AND evidence_type = 'start'"
            ),
            {"c": seeded.alpha.id},
        )
    assert filas == 1, "una sola fila de evidencia por extremo"


async def test_concurrent_state_reads_do_not_create_two_evidence_rows(
    seeded, alpha_client,
):
    """`ensure_row` compite consigo mismo y la base decide.

    La pantalla del supervisor consulta el estado en cada reconciliación, y dos
    pestañas o dos dispositivos pueden hacerlo a la vez. El índice único por
    (jornada, extremo) es lo que impide dos filas; el servicio sólo tiene que no
    romperse cuando lo pierde.
    """
    import asyncio

    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    async with TenantClient("alpha") as uno, TenantClient("alpha") as otro:
        await uno.login(seeded.alpha.users["supervisor"].email)
        await otro.login(seeded.alpha.users["supervisor"].email)

        respuestas = await asyncio.gather(
            uno.get(f"/api/odometer/sessions/{jornada['id']}"),
            otro.get(f"/api/odometer/sessions/{jornada['id']}"),
            return_exceptions=True,
        )

    for r in respuestas:
        if not isinstance(r, Exception):
            assert r.status_code == 200

    async with async_session_maker() as session:
        filas = await session.scalar(
            text(
                "SELECT count(*) FROM odometer_evidence WHERE company_id = :c"
            ),
            {"c": seeded.alpha.id},
        )
    assert filas == 1
