"""
El viaje del supervisor (RTE04-C1).

Lo que este archivo demuestra, y por qué cada bloque existe
-------------------------------------------------------------
* **La jornada manda.** Un viaje sólo existe dentro de una jornada abierta, y
  `Start Work` sigue sin crear ninguno: una jornada con cero viajes es un
  resultado válido, no incompleto (A-1, heredado de RTE03).
* **Un solo viaje vivo.** Garantizado por la base, no por una lectura previa en
  Python. `ARRIVED` cuenta como vivo a propósito: un viaje operativo que llegó
  espera a RTE05, y confundir llegar con terminar es lo que la instrucción
  prohíbe.
* **El plan original no se pisa.** Cada `Change Plan` apila; el original sigue
  legible tras varios cambios consecutivos.
* **Llegar no es terminar.** Sólo `HOME` cierra al llegar, y llegar a casa no
  termina la jornada.
* **Interrumpir no es llegar.** `End Work Anyway` deja `INTERRUPTED`, sin
  fabricar una llegada que no ocurrió.
* **El valor de pre-viaje pertenece a su contexto.** CER fijó tres contextos
  que lo llevan; ofrecer uno de otra lista se rechaza.
* **Aislamiento.** Un viaje de otro supervisor o de otro tenant responde 404.
"""

import asyncio

import pytest
from sqlalchemy import select, text

from app.database import async_session_maker
from app.routers_api.trips.models import Trip
from tests.integration.conftest import TEST_PASSWORD, TenantClient


pytestmark = pytest.mark.integration


# ── Ayudas ──────────────────────────────────────────────────────────────────


async def _abrir_jornada(cliente, seeded) -> dict:
    await cliente.login(seeded.alpha.users["supervisor"].email)
    respuesta = await cliente.post("/api/worksessions", json={})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _planificar(cliente, *, purpose="client_visit", **extra) -> dict:
    cuerpo = {"purpose": purpose, **extra}
    respuesta = await cliente.post("/api/trips", json=cuerpo)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _valor_de_lista(cliente, list_code: str) -> int:
    """Crea un valor en esa lista y devuelve su id."""
    respuesta = await cliente.post(
        "/api/standard-values", json={"list_code": list_code, "label": f"V {list_code}"}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["id"]


# ── La jornada manda ────────────────────────────────────────────────────────


async def test_start_work_still_creates_no_trip(seeded, alpha_client):
    """A-1 sigue intacto: RTE04 no regresa RTE03."""
    jornada = await _abrir_jornada(alpha_client, seeded)

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Trip).where(Trip.work_session_id == jornada["id"])
        )
    assert filas.scalars().all() == [], "abrir la jornada no fabrica un viaje"


async def test_a_trip_requires_an_active_work_session(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    respuesta = await alpha_client.post("/api/trips", json={"purpose": "office"})

    assert respuesta.status_code == 409
    assert "start your workday" in respuesta.json()["detail"].lower()


async def test_a_zero_trip_work_session_still_ends_normally(seeded, alpha_client):
    """Una jornada sin desplazamientos sigue siendo un resultado válido."""
    jornada = await _abrir_jornada(alpha_client, seeded)

    terminada = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert terminada.status_code == 200
    assert terminada.json()["status"] == "ended"


# ── Un solo viaje vivo ──────────────────────────────────────────────────────


async def test_planning_twice_returns_the_same_trip(seeded, alpha_client):
    """Reenviar la creación no duplica: devuelve el viaje que ya estaba vivo."""
    await _abrir_jornada(alpha_client, seeded)
    primero = await _planificar(alpha_client)
    segundo = await _planificar(alpha_client, purpose="office")

    assert segundo["id"] == primero["id"]
    assert segundo["original_purpose"] == "client_visit", (
        "el segundo intento no reescribe el plan del viaje vivo"
    )


async def test_concurrent_planning_creates_only_one_trip(seeded, alpha_client):
    """Carrera real: dos peticiones simultáneas, un solo viaje."""
    await _abrir_jornada(alpha_client, seeded)

    respuestas = await asyncio.gather(
        alpha_client.post("/api/trips", json={"purpose": "office"}),
        alpha_client.post("/api/trips", json={"purpose": "other"}),
    )

    assert all(r.status_code == 200 for r in respuestas), [r.text for r in respuestas]
    ids = {r.json()["id"] for r in respuestas}
    assert len(ids) == 1, "el índice parcial impide un segundo viaje vivo"


async def test_an_arrived_operational_trip_still_blocks_a_new_one(
    seeded, alpha_client,
):
    """`ARRIVED` cuenta como vivo: el viaje espera a RTE05, no ha terminado."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    otro = await _planificar(alpha_client, purpose="office")
    assert otro["id"] == viaje["id"], (
        "no se puede abrir otro viaje mientras el operativo sigue en ARRIVED"
    )


async def test_the_database_rejects_a_second_live_trip_directly(seeded, alpha_client):
    """El índice parcial, probado saltándose el servicio por completo."""
    from sqlalchemy import insert

    jornada = await _abrir_jornada(alpha_client, seeded)
    await _planificar(alpha_client)

    async with async_session_maker() as session:
        with pytest.raises(Exception):
            await session.execute(
                insert(Trip).values(
                    company_id=seeded.alpha.id,
                    work_session_id=jornada["id"],
                    sequence=99,
                    status="planning",
                    original_purpose="office",
                    current_purpose="office",
                )
            )
            await session.commit()
        await session.rollback()


# ── Transiciones ────────────────────────────────────────────────────────────


async def test_the_trip_progresses_planning_in_transit_arrived(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    assert viaje["status"] == "planning"

    en_ruta = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    ).json()
    assert en_ruta["status"] == "in_transit"
    assert en_ruta["started_at"] is not None

    llegado = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    ).json()
    assert llegado["status"] == "arrived"
    assert llegado["arrived_at"] is not None


async def test_an_operational_arrival_does_not_close_the_trip(seeded, alpha_client):
    """Ni cierra ni crea actividad: eso es RTE05 y no se simula."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    llegado = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    ).json()

    assert llegado["status"] == "arrived"
    assert llegado["ended_at"] is None, "un viaje operativo que llegó no ha terminado"


async def test_repeated_start_changes_state_once(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)

    primero = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    ).json()
    segundo = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    ).json()

    assert segundo["status"] == "in_transit"
    assert segundo["started_at"] == primero["started_at"], (
        "el replay no mueve la hora de arranque"
    )


async def test_repeated_arrival_changes_state_once(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    primero = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    ).json()
    segundo = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    ).json()

    assert segundo["arrived_at"] == primero["arrived_at"]


async def test_starting_a_trip_that_never_planned_is_rejected(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    respuesta = await alpha_client.post("/api/trips/999999/start", json={})
    assert respuesta.status_code == 404


async def test_arriving_before_starting_is_rejected(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)

    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    assert respuesta.status_code == 409


# ── HOME ────────────────────────────────────────────────────────────────────


async def test_arriving_home_closes_the_trip(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="home")
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    llegado = (
        await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    ).json()

    assert llegado["status"] == "closed", "HOME cierra al llegar"
    assert llegado["ended_at"] is not None


async def test_arriving_home_does_not_end_the_work_session(seeded, alpha_client):
    """Volver a casa termina el desplazamiento, no el día de trabajo."""
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="home")
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"] is not None
    assert actual["work_session"]["id"] == jornada["id"]
    assert actual["work_session"]["status"] == "active"


async def test_after_arriving_home_a_new_trip_can_start(seeded, alpha_client):
    """El viaje HOME terminó, así que deja sitio al siguiente."""
    await _abrir_jornada(alpha_client, seeded)
    casa = await _planificar(alpha_client, purpose="home")
    await alpha_client.post(f"/api/trips/{casa['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{casa['id']}/arrive", json={})

    siguiente = await _planificar(alpha_client, purpose="office")
    assert siguiente["id"] != casa["id"]
    assert siguiente["sequence"] == casa["sequence"] + 1


# ── Change Plan ─────────────────────────────────────────────────────────────


async def test_change_plan_preserves_the_original_across_two_changes(
    seeded, alpha_client,
):
    """El requisito central: el plan original sobrevive a varios cambios."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(
        alpha_client, purpose="client_visit", context_reference="Acme HQ"
    )
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    await alpha_client.post(
        f"/api/trips/{viaje['id']}/change-plan",
        json={"purpose": "other", "context_reference": "Detour"},
    )
    final = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/change-plan",
            json={"purpose": "office", "context_reference": "Main office"},
        )
    ).json()

    assert final["original_purpose"] == "client_visit", "el original no se pisa"
    assert final["original_context_reference"] == "Acme HQ"
    assert final["current_purpose"] == "office"
    assert final["current_context_reference"] == "Main office"

    historial = (
        await alpha_client.get(f"/api/trips/{viaje['id']}/plan-changes")
    ).json()
    assert len(historial) == 2, "cada cambio apila una fila"
    assert historial[0]["from_purpose"] == "client_visit"
    assert historial[0]["to_purpose"] == "other"
    assert historial[1]["from_purpose"] == "other"
    assert historial[1]["to_purpose"] == "office"


async def test_change_plan_before_starting_is_rejected(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/change-plan", json={"purpose": "office"}
    )
    assert respuesta.status_code == 409


async def test_change_plan_after_arriving_is_rejected(seeded, alpha_client):
    """A-4: llegado el destino, lo que venga después es otro viaje."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/change-plan", json={"purpose": "office"}
    )
    assert respuesta.status_code == 409


# ── Valor estandarizado de pre-viaje (resolución CER 002) ───────────────────


@pytest.mark.parametrize(
    "purpose,list_code",
    [
        ("employee_visit", "employee_visit_reasons"),
        ("check_delivery", "delivery_types"),
        ("office", "office_purposes"),
    ],
)
async def test_the_three_pretrip_contexts_accept_their_own_list(
    seeded, alpha_client, purpose, list_code,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor_id = await _valor_de_lista(alpha_client, list_code)

    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(
        alpha_client, purpose=purpose, standard_value_id=valor_id
    )

    assert viaje["original_standard_value_id"] == valor_id
    assert viaje["current_standard_value_id"] == valor_id


async def test_a_value_from_another_list_is_rejected(seeded, alpha_client):
    """Cruzar contextos está prohibido: un Delivery Type no vale en Office."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    entrega_id = await _valor_de_lista(alpha_client, "delivery_types")

    await _abrir_jornada(alpha_client, seeded)
    respuesta = await alpha_client.post(
        "/api/trips", json={"purpose": "office", "standard_value_id": entrega_id}
    )

    assert respuesta.status_code == 422
    assert "does not belong" in respuesta.json()["detail"].lower()


@pytest.mark.parametrize("purpose", ["client_visit", "recruiting", "other", "home"])
async def test_post_arrival_contexts_take_no_pretrip_value(
    seeded, alpha_client, purpose,
):
    """Lo que se elige al llegar es de RTE05: aquí no se acepta."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor_id = await _valor_de_lista(alpha_client, "office_purposes")

    await _abrir_jornada(alpha_client, seeded)
    respuesta = await alpha_client.post(
        "/api/trips", json={"purpose": purpose, "standard_value_id": valor_id}
    )

    assert respuesta.status_code == 422
    assert "does not take" in respuesta.json()["detail"].lower()


async def test_the_pretrip_value_is_optional(seeded, alpha_client):
    """Un contexto que lo admite no lo exige."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="office")
    assert viaje["current_standard_value_id"] is None


# ── Aislamiento y autorización ──────────────────────────────────────────────


async def test_a_trip_of_another_supervisor_returns_not_found(seeded, alpha_client):
    """Mismo trato que otro tenant: no se confirma que exista."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    otro = (
        await alpha_client.post(
            "/api/users",
            json={
                "username": "otrosup",
                "email": "otrosup@alpha.example.com",
                "first_name": "Otro",
                "last_name": "Sup",
                "password": TEST_PASSWORD,
                "role_id": seeded.alpha.roles["supervisor"],
            },
        )
    ).json()

    async with TenantClient("alpha") as cliente:
        await cliente.login(otro["email"])
        await cliente.post("/api/worksessions", json={})
        ajeno = (await cliente.post("/api/trips", json={"purpose": "office"})).json()

    await _abrir_jornada(alpha_client, seeded)
    respuesta = await alpha_client.post(f"/api/trips/{ajeno['id']}/start", json={})
    assert respuesta.status_code == 404


async def test_a_trip_of_another_tenant_returns_not_found(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)

    async with TenantClient("beta") as beta:
        await beta.login(seeded.beta.users["supervisor"].email)
        await beta.post("/api/worksessions", json={})
        respuesta = await beta.post(f"/api/trips/{viaje['id']}/start", json={})

    assert respuesta.status_code == 404


async def test_planning_a_trip_requires_the_capability(seeded, alpha_client):
    """`route_admin` administra la compañía; no ejecuta trabajo de campo."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post("/api/trips", json={"purpose": "office"})
    assert respuesta.status_code == 403


# ── Idempotencia de la cola offline ─────────────────────────────────────────


async def test_replaying_the_same_idempotency_key_plans_one_trip(
    seeded, alpha_client,
):
    await _abrir_jornada(alpha_client, seeded)
    cabeceras = {"Idempotency-Key": "rte04-plan-1"}
    cuerpo = {"purpose": "office"}

    primera = (
        await alpha_client.post("/api/trips", json=cuerpo, headers=cabeceras)
    ).json()
    replay = (
        await alpha_client.post("/api/trips", json=cuerpo, headers=cabeceras)
    ).json()

    assert replay["id"] == primera["id"]

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Trip).where(Trip.work_session_id == primera["work_session_id"])
        )
    assert len(filas.scalars().all()) == 1


async def test_a_second_device_resolves_the_same_trip(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    async with TenantClient("alpha") as segundo:
        await segundo.login(seeded.alpha.users["supervisor"].email)
        desde_otro = (await segundo.post("/api/trips", json={"purpose": "other"})).json()

    assert desde_otro["id"] == viaje["id"], "el segundo dispositivo no crea otro viaje"
    assert desde_otro["status"] == "in_transit"


# ── Auditoría ───────────────────────────────────────────────────────────────


async def test_trip_transitions_are_audited(seeded, alpha_client):
    from sqlalchemy import text

    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="home")
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT action FROM audit_event "
                "WHERE company_id = :c AND entity_type = 'trip' AND entity_id = :i"
            ),
            {"c": seeded.alpha.id, "i": viaje["id"]},
        )
    acciones = {a for (a,) in filas.all()}

    assert {"create", "start", "arrive_home"} <= acciones


# ── Cierre de C1 (resolución CER 003) ───────────────────────────────────────
#
# Dos huecos que CER pidió cerrar: el estado actual tenía que devolver el viaje
# vivo, y los tres datos de planificación tenían que dejar de ser opcionales.
# Un viaje puede quedarse en PLANNING mientras el supervisor rellena el
# formulario; lo que no puede es SALIR sin el dato.


@pytest.mark.parametrize(
    "purpose,texto_error",
    [
        ("employee_visit", "reason"),
        ("check_delivery", "delivery type"),
        ("office", "purpose"),
    ],
)
async def test_the_three_pretrip_contexts_cannot_start_without_their_value(
    seeded, alpha_client, purpose, texto_error,
):
    """Sin el dato obligatorio no se sale, y el mensaje dice qué falta."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose=purpose)

    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    assert respuesta.status_code == 422, respuesta.text
    assert texto_error in respuesta.json()["detail"].lower()

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["current_trip"]["status"] == "planning", (
        "el rechazo deja el viaje donde estaba, no lo rompe"
    )


@pytest.mark.parametrize(
    "purpose,list_code",
    [
        ("employee_visit", "employee_visit_reasons"),
        ("check_delivery", "delivery_types"),
        ("office", "office_purposes"),
    ],
)
async def test_the_three_pretrip_contexts_start_once_the_value_is_present(
    seeded, alpha_client, purpose, list_code,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor_id = await _valor_de_lista(alpha_client, list_code)

    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(
        alpha_client, purpose=purpose, standard_value_id=valor_id
    )

    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "in_transit"


@pytest.mark.parametrize("purpose", ["client_visit", "recruiting", "other", "home"])
async def test_post_arrival_contexts_start_without_any_pretrip_value(
    seeded, alpha_client, purpose,
):
    """Lo que se elige al llegar no puede exigirse antes de salir."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose=purpose)

    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert respuesta.status_code == 200, respuesta.text


async def test_a_deleted_value_cannot_be_newly_selected(seeded, alpha_client):
    """Un valor retirado de la administración no vuelve a ofrecerse."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor_id = await _valor_de_lista(alpha_client, "office_purposes")
    await alpha_client.delete(f"/api/standard-values/{valor_id}")

    await _abrir_jornada(alpha_client, seeded)
    respuesta = await alpha_client.post(
        "/api/trips", json={"purpose": "office", "standard_value_id": valor_id}
    )

    assert respuesta.status_code == 422


async def test_changing_plan_into_a_pretrip_context_does_not_invent_its_value(
    seeded, alpha_client,
):
    """Cambiar de plan no rellena solo el dato del contexto nuevo."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="client_visit")
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    cambiado = await alpha_client.post(
        f"/api/trips/{viaje['id']}/change-plan", json={"purpose": "office"}
    )

    assert cambiado.status_code == 200, cambiado.text
    assert cambiado.json()["current_purpose"] == "office"
    assert cambiado.json()["current_standard_value_id"] is None, (
        "no se inventa un valor para el contexto nuevo"
    )


# ── Estado actual con el viaje vivo ─────────────────────────────────────────


async def test_current_returns_null_trip_when_there_is_none(seeded, alpha_client):
    """Sin viaje vivo la clave es `null`, no un marcador inventado."""
    await _abrir_jornada(alpha_client, seeded)

    actual = (await alpha_client.get("/api/worksessions/current")).json()

    assert actual["work_session"] is not None
    assert actual["current_trip"] is None


async def test_current_returns_nothing_without_a_work_session(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    actual = (await alpha_client.get("/api/worksessions/current")).json()

    assert actual["work_session"] is None
    assert actual["current_trip"] is None


@pytest.mark.parametrize("estado", ["planning", "in_transit", "arrived"])
async def test_current_returns_the_live_trip_in_every_non_terminal_state(
    seeded, alpha_client, estado,
):
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)

    if estado in ("in_transit", "arrived"):
        await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    if estado == "arrived":
        await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    actual = (await alpha_client.get("/api/worksessions/current")).json()

    assert actual["current_trip"] is not None
    assert actual["current_trip"]["id"] == viaje["id"]
    assert actual["current_trip"]["status"] == estado


async def test_current_stops_returning_a_closed_trip(seeded, alpha_client):
    """Un viaje HOME cerrado deja de ser el actual; la jornada sigue abierta."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="home")
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    actual = (await alpha_client.get("/api/worksessions/current")).json()

    assert actual["current_trip"] is None
    assert actual["work_session"]["status"] == "active"


async def test_a_second_device_reads_the_same_current_trip(seeded, alpha_client):
    """Recuperar el estado no crea un viaje nuevo, lo resuelve."""
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    async with TenantClient("alpha") as segundo:
        await segundo.login(seeded.alpha.users["supervisor"].email)
        actual = (await segundo.get("/api/worksessions/current")).json()

    assert actual["current_trip"]["id"] == viaje["id"]
    assert actual["current_trip"]["status"] == "in_transit"

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Trip).where(Trip.work_session_id == viaje["work_session_id"])
        )
    assert len(filas.scalars().all()) == 1, "leer el estado no duplica el viaje"


async def test_current_does_not_leak_another_tenants_trip(seeded, alpha_client):
    await _abrir_jornada(alpha_client, seeded)
    await _planificar(alpha_client)

    async with TenantClient("beta") as beta:
        await beta.login(seeded.beta.users["supervisor"].email)
        await beta.post("/api/worksessions", json={})
        actual = (await beta.get("/api/worksessions/current")).json()

    assert actual["current_trip"] is None, (
        "cada tenant ve su propio estado, nunca el del otro"
    )


# ── Revisión de End Work con viaje en curso (D-07, §7 de la resolución 003) ──


async def test_ending_work_in_transit_is_a_review_not_a_silent_close(
    seeded, alpha_client,
):
    """Con un viaje en ruta, cerrar no cierra: pide confirmación."""
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )

    assert respuesta.status_code == 409
    assert "still on route" in respuesta.json()["detail"].lower()

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active", "la jornada sigue abierta"
    assert actual["current_trip"]["status"] == "in_transit", "y el viaje también"


async def test_continue_working_restores_the_same_trip(seeded, alpha_client):
    """"Continue Working" es no confirmar: nada cambia, ni se crea otro viaje."""
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    await alpha_client.post(f"/api/worksessions/{jornada['id']}/end", json={})

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["current_trip"]["id"] == viaje["id"]
    assert actual["current_trip"]["status"] == "in_transit"

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Trip).where(Trip.work_session_id == jornada["id"])
        )
    assert len(filas.scalars().all()) == 1, "la revisión no crea un segundo viaje"


async def test_end_work_anyway_interrupts_without_faking_an_arrival(
    seeded, alpha_client,
):
    """El viaje se corta a medias y así queda escrito: nunca como llegada."""
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={"end_anyway": True}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "ended"

    async with async_session_maker() as session:
        fila = await session.scalar(select(Trip).where(Trip.id == viaje["id"]))

    assert fila.status == "interrupted"
    assert fila.arrived_at is None, "no se fabrica una llegada que no ocurrió"
    assert fila.ended_at is not None


async def test_an_arrived_operational_trip_does_not_block_end_work(
    seeded, alpha_client,
):
    """Llegar no bloquea cerrar, y cerrar no cierra el viaje.

    Completar un viaje operativo es de RTE05. Ni se inventa su cierre ni se
    inventa un bloqueo: ninguna de las dos cosas está definida en el baseline.
    """
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert respuesta.status_code == 200, respuesta.text

    async with async_session_maker() as session:
        fila = await session.scalar(select(Trip).where(Trip.id == viaje["id"]))
    assert fila.status == "arrived", "el viaje operativo sigue esperando a RTE05"


async def test_ending_work_without_any_trip_still_works(seeded, alpha_client):
    """A-1 intacto: una jornada sin viajes cierra sin ceremonia."""
    jornada = await _abrir_jornada(alpha_client, seeded)

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "ended"


async def test_a_closed_home_trip_does_not_trigger_the_review(seeded, alpha_client):
    """Un viaje ya terminado no está en ruta, así que no hay nada que revisar."""
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client, purpose="home")
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert respuesta.status_code == 200


# ── La hora de ocurrencia sobrevive a la cola (§4 de las instrucciones 003) ───


async def test_a_queued_trip_action_keeps_the_time_the_supervisor_pressed_it(
    seeded, alpha_client,
):
    """Una acción que esperó en la cola se fecha cuando se pulsó, no al llegar.

    Es la misma semántica certificada en RTE03 y aquí importa igual: un viaje
    que arrancó a las 8:05 y se sincronizó a las 10:00 tiene que constar a las
    8:05. `started_received_at` guarda la otra mitad del hecho, así que no se
    pierde cuándo lo supo el servidor.

    El cliente lo envía en las tres acciones encoladas (`queuePlanTrip`,
    `queueStartTrip`, `queueArrive`); esto comprueba que el servidor lo honra.
    """
    from datetime import datetime, timedelta, timezone

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()

    pulsado = datetime.now(timezone.utc) - timedelta(minutes=90)
    arrancado = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/start",
            json={
                "device_captured_at": pulsado.isoformat(),
                "utc_offset_minutes": -300,
            },
        )
    ).json()

    assert arrancado["status"] == "in_transit"

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT started_at, started_received_at FROM trip WHERE id = :i"
                ),
                {"i": viaje["id"]},
            )
        ).one()

    assert fila.started_at < fila.started_received_at, (
        "la ocurrencia tiene que quedar antes que la recepción"
    )
    assert abs((fila.started_at - pulsado).total_seconds()) < 2, (
        "se guarda la hora del dispositivo, no la del servidor"
    )


async def test_a_device_time_in_the_future_is_not_believed(seeded, alpha_client):
    """Evidencia imposible: el servidor usa su reloj en vez de creerla.

    Un teléfono con la hora mal puesta no puede fechar un viaje mañana.
    """
    from datetime import datetime, timedelta, timezone

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()

    futuro = datetime.now(timezone.utc) + timedelta(hours=6)
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/start",
        json={"device_captured_at": futuro.isoformat()},
    )

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT started_at, started_received_at FROM trip WHERE id = :i"
                ),
                {"i": viaje["id"]},
            )
        ).one()

    assert fila.started_at <= fila.started_received_at, (
        "no se acepta un viaje que arrancó en el futuro"
    )


# ── Recuperación tras reautenticarse (§2.1 y §3 de las instrucciones 003) ─────


async def test_reauthenticating_resolves_the_same_current_trip(
    seeded, alpha_client,
):
    """Perder la sesión y volver a entrar devuelve **el mismo** viaje.

    Es el caso que de verdad ocurre en campo: la cookie caduca mientras el
    supervisor conduce, o cierra la aplicación y vuelve. Recargar y un segundo
    dispositivo ya estaban cubiertos; esto cubre la tercera forma que nombra la
    resolución, y es la que más se parece a un incidente real.

    Lo que se comprueba no es sólo que devuelva algo: que devuelva el mismo
    identificador y que **no haya creado otro viaje** por el camino.
    """
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    # Se pierde la sesión, igual que una cookie que expira.
    await alpha_client.post("/api/public/auth/logout")
    sin_sesion = await alpha_client.get("/api/worksessions/current")
    assert sin_sesion.status_code == 401, "sin sesión no se sirve estado"

    # Cerrar sesión borra también el testigo CSRF; un navegador vuelve a cargar
    # `/login` y recibe uno nuevo.
    await alpha_client.reload_login_page()
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["current_trip"] is not None
    assert actual["current_trip"]["id"] == viaje["id"]
    assert actual["current_trip"]["status"] == "in_transit"

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Trip).where(Trip.work_session_id == viaje["work_session_id"])
        )
    assert len(filas.scalars().all()) == 1, (
        "reautenticarse no puede fabricar un segundo viaje"
    )


async def test_current_does_not_leak_another_supervisors_trip(
    seeded, alpha_client,
):
    """El aislamiento no es sólo entre tenants: también dentro de uno.

    Dos supervisores de la misma compañía trabajan a la vez. El estado se
    resuelve por la sesión autenticada, nunca por algo que llegue en la
    petición, así que el viaje de uno no puede aparecer en la pantalla del otro.
    """
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _planificar(alpha_client)

    # Un segundo supervisor del **mismo** tenant, con su propia jornada.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    otro = (
        await alpha_client.post(
            "/api/users",
            json={
                "username": "supdos",
                "email": "supdos@alpha.example.com",
                "first_name": "Sup", "last_name": "Dos",
                "password": TEST_PASSWORD,
                "role_id": seeded.alpha.roles["supervisor"],
            },
        )
    ).json()

    async with TenantClient("alpha") as segundo:
        await segundo.login(otro["email"])
        await segundo.post("/api/worksessions", json={})
        actual = (await segundo.get("/api/worksessions/current")).json()

    assert actual["work_session"] is not None, "tiene su propia jornada"
    assert actual["current_trip"] is None, (
        "el viaje del otro supervisor no aparece aquí"
    )

    # Y el dueño sigue viendo el suyo, intacto.
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    propio = (await alpha_client.get("/api/worksessions/current")).json()
    assert propio["current_trip"]["id"] == viaje["id"]


# ── Una lista obligatoria vacía (hallazgo de la validación de catálogos) ──────


async def test_an_empty_required_list_blocks_the_trip_and_says_why(
    seeded, alpha_client,
):
    """Nada se inventa cuando el catálogo se queda sin valores.

    Un administrador puede retirar **todos** los valores de una lista: no hay
    restricción que lo impida, y RTE04 no cambia el comportamiento de
    configuración que CER ya certificó. Lo que sí importa es qué pasa entonces.

    El viaje sigue bloqueado —la guarda no se debilita— y el mensaje distingue
    los dos casos: "elige uno" cuando hay de dónde elegir, y "no hay ninguno
    configurado, pídeselo a un administrador" cuando no. Decir lo primero con la
    lista vacía manda al supervisor a un callejón sin salida.
    """
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valores = (
        await alpha_client.get("/api/standard-values/employee_visit_reasons")
    ).json()
    assert len(valores) == 4, "los cuatro motivos aprobados"

    for valor in valores:
        borrado = await alpha_client.delete(f"/api/standard-values/{valor['id']}")
        assert borrado.status_code == 204

    vacia = (
        await alpha_client.get("/api/standard-values/employee_visit_reasons")
    ).json()
    assert vacia == [], "la lista se puede quedar sin valores seleccionables"

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = await _planificar(alpha_client, purpose="employee_visit")
    arranque = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    assert arranque.status_code == 422, "la guarda no se debilita"
    detalle = arranque.json()["detail"]
    assert "no values configured" in detalle, (
        f"el mensaje tiene que decir que no hay nada que elegir: {detalle}"
    )
    assert "administrator" in detalle, "y a quién pedírselo"

    # Y el viaje se queda donde estaba: ni arrancado ni inventado.
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["current_trip"]["status"] == "planning"


async def test_with_values_available_the_message_asks_to_choose(
    seeded, alpha_client,
):
    """El otro lado de la moneda: si hay de dónde elegir, se pide elegir."""
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})
    viaje = await _planificar(alpha_client, purpose="employee_visit")
    arranque = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    assert arranque.status_code == 422
    assert "Choose" in arranque.json()["detail"]
