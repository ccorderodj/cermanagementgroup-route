"""
La ejecución tras la llegada (RTE05).

Lo que este archivo defiende
-----------------------------
* **Un bloque por parada.** Tres actividades en una visita son tres etiquetas de
  la misma parada, no tres paradas. Un inicio, un fin, una duración, un
  resultado, una nota (PD-01).
* **Nada se cierra solo.** El viaje llega a `CLOSED` porque alguien terminó o se
  marchó **y dijo cómo fue**. Terminar sin resultado no es un caso de borde: es
  imposible, y lo impide la base.
* **El contexto manda.** Sólo tres contextos seleccionan actividad. Employee
  Visit y Office ya traen su dato de antes de salir; ofrecerles otro selector
  sería preguntar dos veces lo mismo. HOME no ejecuta nada.
* **El histórico se lee como era.** Renombrar, desactivar o retirar un valor
  después no puede cambiar lo que dice un registro de marzo.
* **Terminar la jornada no resuelve la parada.** `End Work` con trabajo de
  llegada pendiente se rechaza y devuelve al supervisor a donde está el trabajo.

Los veintiocho casos límite de la resolución se comprueban contra la API, que es
donde está la autoridad.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from tests.integration.conftest import TenantClient


pytestmark = pytest.mark.integration


FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


# ── Ayudas ──────────────────────────────────────────────────────────────────


async def _sembrar_valores(company_id: int) -> None:
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()


async def _valores(cliente, list_code: str) -> list[dict]:
    respuesta = await cliente.get(f"/api/standard-values/{list_code}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _id_de(cliente, list_code: str, etiqueta: str) -> int:
    for v in await _valores(cliente, list_code):
        if v["label"] == etiqueta:
            return v["id"]
    raise AssertionError(f"no está '{etiqueta}' en {list_code}")


async def _llegar(cliente, seeded, *, purpose: str, unidad: str = None, **extra):
    """Deja al supervisor con un viaje de ese contexto en `ARRIVED`."""
    if unidad is not None:
        await cliente.login(seeded.alpha.users["route_admin"].email)
        perfil = (
            await cliente.post(
                "/api/supervisors",
                json={"user_id": seeded.alpha.users["supervisor"].id},
            )
        ).json()
        veh = (
            await cliente.post(
                "/api/vehicles",
                json={
                    "make": "T", "model": "H", "year": 2024, "unit": unidad,
                    "fuel_grade": "regular", "operational_mpg": "24.00",
                },
            )
        ).json()
        await cliente.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": veh["id"]},
        )

    await cliente.login(seeded.alpha.users["supervisor"].email)
    jornada = (await cliente.post("/api/worksessions", json={})).json()

    if unidad is not None:
        await cliente.post(
            f"/api/odometer/sessions/{jornada['id']}/start/photo",
            files={"photo": ("o.png", FOTO, "image/png")},
        )
        await cliente.post(
            f"/api/odometer/sessions/{jornada['id']}/start/confirm",
            json={"reading": "1000.0"},
        )

    viaje = (
        await cliente.post("/api/trips", json={"purpose": purpose, **extra})
    ).json()
    assert "id" in viaje, viaje
    await cliente.post(f"/api/trips/{viaje['id']}/start", json={})
    await cliente.post(f"/api/trips/{viaje['id']}/arrive", json={})
    return jornada, viaje


async def _estado_del_viaje(company_id: int, trip_id: int) -> str:
    async with async_session_maker() as session:
        return await session.scalar(
            text("SELECT status FROM trip WHERE id = :i AND company_id = :c"),
            {"i": trip_id, "c": company_id},
        )


async def _estado_de_la_jornada(company_id: int, session_id: int) -> str:
    async with async_session_maker() as session:
        return await session.scalar(
            text(
                "SELECT status FROM work_session "
                "WHERE id = :i AND company_id = :c"
            ),
            {"i": session_id, "c": company_id},
        )


# ── Casos 1-4: seleccionar, ejecutar, terminar ──────────────────────────────


async def test_one_activity_completes_the_stop_and_closes_the_trip(
    seeded, alpha_client,
):
    """Caso 1: llegar, una actividad, completar."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")

    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    arranque = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    assert arranque.status_code == 200, arranque.text
    assert arranque.json()["status"] == "in_progress"
    assert [a["label"] for a in arranque.json()["activities"]] == ["Service Review"]

    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    fin = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )

    assert fin.status_code == 200, fin.text
    cuerpo = fin.json()
    assert cuerpo["status"] == "completed"
    assert cuerpo["terminal_action"] == "complete"
    assert cuerpo["outcome_label"] == "Completed"
    assert cuerpo["ended_at"] is not None

    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"

    # La jornada sigue abierta: cerrar la parada no cierra el día.
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active"
    assert actual["current_trip"] is None, "el viaje cerrado ya no es el actual"
    assert actual["post_arrival_pending"] is False


async def test_several_activities_are_one_block_with_one_of_everything(
    seeded, alpha_client,
):
    """Caso 2, y el corazón de PD-01.

    Tres cosas en la misma visita son tres etiquetas de **una** parada. Si el
    modelo las tratara como unidades de ejecución habría que inventar tres horas
    de inicio que nadie midió.
    """
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")

    elegidas = [
        await _id_de(alpha_client, "client_visit_activities", etiqueta)
        for etiqueta in ("Staffing Follow-up", "Service Review", "Safety Follow-up")
    ]
    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": elegidas},
        )
    ).json()
    assert len(bloque["activities"]) == 3

    resultado = await _id_de(alpha_client, "outcomes", "Follow-up Required")
    fin = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/complete",
            json={"action": "complete", "outcome_id": resultado, "notes": "Tres cosas"},
        )
    ).json()

    # Uno de cada, para las tres actividades juntas.
    assert fin["outcome_label"] == "Follow-up Required"
    assert fin["notes"] == "Tres cosas"
    assert fin["started_at"] is not None and fin["ended_at"] is not None

    async with async_session_maker() as session:
        bloques = await session.scalar(
            text(
                "SELECT count(*) FROM activity_execution WHERE trip_id = :t"
            ),
            {"t": viaje["id"]},
        )
        etiquetas = await session.scalar(
            text(
                "SELECT count(*) FROM activity_execution_activity "
                "WHERE activity_execution_id = :e"
            ),
            {"e": fin["id"]},
        )
    assert bloques == 1, "un bloque, no tres"
    assert etiquetas == 3, "tres etiquetas de ese bloque"


async def test_leaving_is_a_controlled_exit_that_also_closes_the_trip(
    seeded, alpha_client,
):
    """Caso 3: marcharse no es abandonar — exige resultado igual que completar."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="recruiting")

    elegidas = [
        await _id_de(alpha_client, "recruiting_activities", e)
        for e in ("Candidate Sourcing", "Hiring Event")
    ]
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": elegidas}
    )

    resultado = await _id_de(alpha_client, "outcomes", "No Contact")
    fin = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/leave",
            json={"action": "leave", "outcome_id": resultado},
        )
    ).json()

    assert fin["status"] == "left"
    assert fin["terminal_action"] == "leave", (
        "marcharse y terminar quedan distinguibles para siempre"
    )
    assert fin["outcome_label"] == "No Contact"
    assert fin["ended_at"] is not None, "la duración se conserva igual"
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"


async def test_other_context_completes_with_several_activities(
    seeded, alpha_client,
):
    """Caso 4."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="other")

    elegidas = [
        await _id_de(alpha_client, "other_activities", e)
        for e in ("Housing Visit", "Supply Pickup")
    ]
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": elegidas}
    )
    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    fin = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )
    assert fin.status_code == 200
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"


# ── Casos 5-8: los contextos sin selector, y HOME ───────────────────────────


@pytest.mark.parametrize(
    "purpose,lista_previa",
    [("employee_visit", "employee_visit_reasons"), ("office", "office_purposes")],
)
async def test_contexts_that_already_asked_do_not_ask_again(
    seeded, alpha_client, purpose, lista_previa,
):
    """Casos 5 y 6: sin selector redundante, pero con bloque de ejecución.

    Employee Visit y Office traen su dato desde la planificación. Lo que RTE05
    les añade no es otra lista: es la duración, el resultado y la nota, que sólo
    se conocen al terminar.
    """
    await _sembrar_valores(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor_previo = (await _valores(alpha_client, lista_previa))[0]["id"]

    _, viaje = await _llegar(
        alpha_client, seeded, purpose=purpose, standard_value_id=valor_previo
    )

    # Sin actividades: es lo correcto aquí.
    arranque = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )
    assert arranque.status_code == 200, arranque.text
    assert arranque.json()["activities"] == []

    # Y enviarlas es un error, no un extra que se ignora. Hay que cerrar la
    # parada actual antes de abrir otra: un solo viaje vivo por jornada.
    otro = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )

    segundo = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": purpose, "standard_value_id": valor_previo},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{segundo['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{segundo['id']}/arrive", json={})

    rechazo = await alpha_client.post(
        f"/api/trips/{segundo['id']}/activity/start", json={"activity_ids": [otro]}
    )
    assert rechazo.status_code == 422
    assert "does not take" in rechazo.json()["detail"]


async def test_check_delivery_records_who_received_it(seeded, alpha_client):
    """Caso 7, y AC-01: al **completar**, `Received By` es obligatorio.

    Completar una entrega afirma que alguien la recibió, y esa afirmación sin
    nombre no es verificable. La obligatoriedad al completar es decisión
    explícita de CER (cierre 002, Delta 1); el camino de marcharse la relaja y
    lo cubre `test_leaving_a_check_delivery_needs_no_receiver`.
    """
    await _sembrar_valores(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    tipo = await _id_de(alpha_client, "delivery_types", "Payroll Check")

    jornada, viaje = await _llegar(
        alpha_client, seeded, purpose="check_delivery", standard_value_id=tipo
    )
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )

    resultado = await _id_de(alpha_client, "outcomes", "Completed")

    # Sin `received_by` no se cierra.
    sin_firma = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )
    assert sin_firma.status_code == 422
    assert "received" in sin_firma.json()["detail"].lower()

    quien = await _id_de(alpha_client, "received_by", "Authorized Person")
    fin = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/complete",
            json={
                "action": "complete",
                "outcome_id": resultado,
                "received_by_id": quien,
            },
        )
    ).json()

    assert fin["received_by_label"] == "Authorized Person"
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"
    assert await _estado_de_la_jornada(seeded.alpha.id, jornada["id"]) == "active"


@pytest.mark.parametrize("con_receptor", [False, True], ids=["sin", "con"])
async def test_leaving_a_check_delivery_needs_no_receiver(
    seeded, alpha_client, con_receptor,
):
    """AC-02: marcharse de una entrega **no** exige receptor, y lo acepta.

    Es el caso real que el cierre 002 corrige: el supervisor llega, no hay nadie
    a quien entregar, y se marcha. Exigirle un receptor le obligaría a
    inventarse uno para poder cerrar la parada — un dato fabricado para
    satisfacer una validación es peor que la ausencia del dato.

    Y si sí hubo alguien pero la entrega no se completó, se registra igual: que
    sea opcional no lo hace menos verificable, así que se valida contra la lista
    y el tenant como cualquier otro valor.
    """
    await _sembrar_valores(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    tipo = await _id_de(alpha_client, "delivery_types", "Payroll Check")

    jornada, viaje = await _llegar(
        alpha_client, seeded, purpose="check_delivery", standard_value_id=tipo
    )
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )

    cuerpo = {
        "action": "leave",
        "outcome_id": await _id_de(alpha_client, "outcomes", "No Contact"),
    }
    if con_receptor:
        cuerpo["received_by_id"] = await _id_de(
            alpha_client, "received_by", "Office Staff"
        )

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/leave", json=cuerpo
    )
    assert respuesta.status_code == 200, respuesta.text
    fin = respuesta.json()

    assert fin["status"] == "left"
    assert fin["terminal_action"] == "leave"
    assert fin["outcome_label"] == "No Contact"
    if con_receptor:
        assert fin["received_by_label"] == "Office Staff", "si se eligió, se conserva"
    else:
        assert fin["received_by_standard_value_id"] is None
        assert fin["received_by_label"] is None, "no se fabrica un receptor"

    # AC-02: el viaje cierra y la jornada sigue abierta, igual que al completar.
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"
    assert await _estado_de_la_jornada(seeded.alpha.id, jornada["id"]) == "active"


async def test_leaving_a_check_delivery_still_requires_an_outcome(
    seeded, alpha_client,
):
    """AC-03: relajar el receptor no relaja el resultado.

    Son dos datos distintos y sólo uno cambió. Marcharse sigue siendo una salida
    controlada: exige decir cómo fue.
    """
    await _sembrar_valores(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    tipo = await _id_de(alpha_client, "delivery_types", "Payroll Check")

    _, viaje = await _llegar(
        alpha_client, seeded, purpose="check_delivery", standard_value_id=tipo
    )
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/leave", json={"action": "leave"}
    )
    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.parametrize("accion", ["complete", "leave"])
async def test_only_a_check_delivery_records_who_received_it(
    seeded, alpha_client, accion,
):
    """Los demás contextos siguen rechazando el receptor, en las dos salidas.

    La regla de Delta 1 relaja **cuándo** hace falta en Check Delivery; no
    convierte el campo en un cajón de sastre para el resto. Una visita a un
    cliente no tiene a quién entregar nada.
    """
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/{accion}",
        json={
            "action": accion,
            "outcome_id": await _id_de(alpha_client, "outcomes", "Completed"),
            "received_by_id": await _id_de(
                alpha_client, "received_by", "Employee"
            ),
        },
    )
    assert respuesta.status_code == 422, respuesta.text
    assert "check delivery" in respuesta.json()["detail"].lower()
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "arrived", (
        "un cierre rechazado no cierra el viaje"
    )


async def test_going_home_records_no_activity(seeded, alpha_client):
    """Caso 8: HOME no ejecuta nada, y su viaje ya se cerró al llegar."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="home")

    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"

    rechazo = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )
    assert rechazo.status_code == 409

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["post_arrival_pending"] is False, "volver a casa no deja trabajo"


# ── Casos 9-14: lo que el servidor rechaza ──────────────────────────────────


async def test_a_multi_select_context_requires_at_least_one_activity(
    seeded, alpha_client,
):
    """Caso 9."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )
    assert respuesta.status_code == 422
    assert "at least one" in respuesta.json()["detail"]


async def test_an_activity_from_the_wrong_list_is_rejected(seeded, alpha_client):
    """Caso 10: cruzar contextos por API directa."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")

    ajena = await _id_de(alpha_client, "recruiting_activities", "Hiring Event")
    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": [ajena]}
    )
    assert respuesta.status_code == 422


async def test_an_inactive_or_deleted_activity_is_rejected(seeded, alpha_client):
    """Caso 11: lo retirado no vuelve a elegirse."""
    await _sembrar_valores(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valor = await _id_de(alpha_client, "client_visit_activities", "Safety Follow-up")
    await alpha_client.put(
        f"/api/standard-values/{valor}", json={"is_active": False}
    )

    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": [valor]}
    )
    assert respuesta.status_code == 422


@pytest.mark.parametrize("accion", ["complete", "leave"])
async def test_terminalizing_without_an_outcome_is_rejected(
    seeded, alpha_client, accion,
):
    """Casos 12 y 13: sin resultado no se termina, por ninguno de los dos caminos."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/{accion}", json={"action": accion}
    )
    assert respuesta.status_code == 422, "el resultado no es opcional"
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "arrived"


async def test_notes_are_optional(seeded, alpha_client):
    """Caso 14."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    resultado = await _id_de(alpha_client, "outcomes", "Completed")

    fin = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )
    assert fin.status_code == 200
    assert fin.json()["notes"] is None


# ── Casos 15-18: reintento y concurrencia ───────────────────────────────────


async def test_repeating_start_produces_one_execution(seeded, alpha_client):
    """Caso 15: la cola reintenta, y reintentar no puede duplicar la parada."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")

    primero = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()
    segundo = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()

    assert segundo["id"] == primero["id"]
    assert segundo["started_at"] == primero["started_at"], (
        "reintentar no mueve la hora de inicio"
    )


async def test_two_devices_starting_at_once_produce_one_execution(
    seeded, alpha_client,
):
    """Caso 16: lo decide el índice único, no el orden de llegada."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    correo = seeded.alpha.users["supervisor"].email

    async with TenantClient("alpha") as uno, TenantClient("alpha") as otro:
        await uno.login(correo)
        await otro.login(correo)
        await asyncio.gather(
            uno.post(
                f"/api/trips/{viaje['id']}/activity/start",
                json={"activity_ids": [actividad]},
            ),
            otro.post(
                f"/api/trips/{viaje['id']}/activity/start",
                json={"activity_ids": [actividad]},
            ),
            return_exceptions=True,
        )

    async with async_session_maker() as session:
        cuantos = await session.scalar(
            text("SELECT count(*) FROM activity_execution WHERE trip_id = :t"),
            {"t": viaje["id"]},
        )
    assert cuantos == 1


async def test_replaying_complete_does_not_corrupt_the_terminal_facts(
    seeded, alpha_client,
):
    """Caso 17."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    resultado = await _id_de(alpha_client, "outcomes", "Completed")

    primero = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/complete",
            json={"action": "complete", "outcome_id": resultado},
        )
    ).json()
    replay = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/complete",
            json={"action": "complete", "outcome_id": resultado},
        )
    ).json()

    assert replay["ended_at"] == primero["ended_at"], "la hora de fin no se mueve"
    assert replay["version"] == primero["version"]


async def test_complete_and_leave_at_once_leave_one_terminal_result(
    seeded, alpha_client,
):
    """Caso 18: dos caminos terminales a la vez, un solo hecho."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    correo = seeded.alpha.users["supervisor"].email

    async with TenantClient("alpha") as uno, TenantClient("alpha") as otro:
        await uno.login(correo)
        await otro.login(correo)
        await asyncio.gather(
            uno.post(
                f"/api/trips/{viaje['id']}/activity/complete",
                json={"action": "complete", "outcome_id": resultado},
            ),
            otro.post(
                f"/api/trips/{viaje['id']}/activity/leave",
                json={"action": "leave", "outcome_id": resultado},
            ),
            return_exceptions=True,
        )

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT status, terminal_action FROM activity_execution "
                    "WHERE trip_id = :t"
                ),
                {"t": viaje["id"]},
            )
        ).one()
    assert fila.status in ("completed", "left")
    assert fila.terminal_action in ("complete", "leave")
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "closed"


# ── Casos 19-21: recuperar el estado ────────────────────────────────────────


async def test_the_current_state_returns_the_running_execution(
    seeded, alpha_client,
):
    """Casos 19 y 20: recargar y reautenticarse devuelven a la misma parada."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["current_activity"]["id"] == bloque["id"]
    assert actual["current_activity"]["status"] == "in_progress"
    assert [a["label"] for a in actual["current_activity"]["activities"]] == [
        "Service Review"
    ]
    assert actual["post_arrival_pending"] is True

    # Perder la sesión y volver devuelve exactamente lo mismo.
    await alpha_client.post("/api/public/auth/logout")
    await alpha_client.reload_login_page()
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    tras_reautenticar = (await alpha_client.get("/api/worksessions/current")).json()
    assert tras_reautenticar["current_activity"]["id"] == bloque["id"]


async def test_a_second_device_resolves_the_same_execution(seeded, alpha_client):
    """Caso 21: el mismo bloque, no otro."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()

    async with TenantClient("alpha") as segundo:
        await segundo.login(seeded.alpha.users["supervisor"].email)
        actual = (await segundo.get("/api/worksessions/current")).json()

    assert actual["current_activity"]["id"] == bloque["id"]


# ── Casos 22-25: End Work ───────────────────────────────────────────────────


async def test_end_work_is_blocked_while_the_arrival_is_unresolved(
    seeded, alpha_client,
):
    """Caso 22: llegar y no hacer nada no permite terminar el día."""
    await _sembrar_valores(seeded.alpha.id)
    jornada, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )

    assert respuesta.status_code == 409
    assert "stop" in respuesta.json()["detail"].lower()
    assert await _estado_del_viaje(seeded.alpha.id, viaje["id"]) == "arrived", (
        "no se cierra el viaje por haber pedido terminar"
    )

    async with async_session_maker() as session:
        bloques = await session.scalar(
            text("SELECT count(*) FROM activity_execution WHERE trip_id = :t"),
            {"t": viaje["id"]},
        )
    assert bloques == 0, "ni se fabrica una ejecución"


async def test_end_work_is_blocked_while_the_execution_is_running(
    seeded, alpha_client,
):
    """Caso 23: con el trabajo en marcha tampoco."""
    await _sembrar_valores(seeded.alpha.id)
    jornada, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert respuesta.status_code == 409

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["current_activity"]["status"] == "in_progress", (
        "el estado devuelve al supervisor a donde está el trabajo"
    )


async def test_after_terminalizing_the_session_stays_active_and_a_new_trip_can_start(
    seeded, alpha_client,
):
    """Casos 24 y 25."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )

    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active"

    siguiente = await alpha_client.post("/api/trips", json={"purpose": "office"})
    assert siguiente.status_code == 200, "con el anterior cerrado, ya se puede salir"


# ── Casos 26-28: histórico, mando obsoleto y tenant ─────────────────────────


async def test_history_survives_renaming_and_retiring_the_catalog_value(
    seeded, alpha_client,
):
    """Caso 26: marzo se lee como marzo.

    Las **tres** operaciones del ciclo de vida del catálogo, sobre un histórico
    que ya existe: renombrar, desactivar y retirar como lápida. El identificador
    sigue resolviendo porque la fila sobrevive en los tres casos, pero el
    **nombre** puede cambiar — y por eso se guarda la etiqueta de entonces. Leer
    marzo con el nombre de hoy contaría otra historia.
    """
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    renombrada = await _id_de(
        alpha_client, "client_visit_activities", "Service Review"
    )
    desactivada = await _id_de(
        alpha_client, "client_visit_activities", "Safety Follow-up"
    )
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [renombrada, desactivada]},
    )
    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )

    # El administrador renombra una, desactiva otra y retira el resultado.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (
        await alpha_client.put(
            f"/api/standard-values/{renombrada}",
            json={"label": "Revisión de servicio"},
        )
    ).status_code == 200
    assert (
        await alpha_client.put(
            f"/api/standard-values/{desactivada}", json={"is_active": False}
        )
    ).status_code == 200
    # Retirar es una lápida, no un `DELETE`: si borrara la fila, la clave
    # foránea `RESTRICT` lo impediría y el histórico se quedaría sin su valor.
    assert (
        await alpha_client.delete(f"/api/standard-values/{resultado}")
    ).status_code == 204

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    historico = (await alpha_client.get(f"/api/trips/{viaje['id']}/activity")).json()

    assert [a["label"] for a in historico["activities"]] == [
        "Service Review",
        "Safety Follow-up",
    ], "las etiquetas de entonces, no las de ahora"
    assert historico["outcome_label"] == "Completed", (
        "el resultado sigue legible aunque el valor se haya retirado"
    )

    # Y las referencias siguen resolviendo: ninguna fila desapareció.
    async with async_session_maker() as session:
        vivas = await session.scalar(
            text(
                "SELECT count(*) FROM standard_value WHERE id = ANY(:ids)"
            ),
            {"ids": [renombrada, desactivada, resultado]},
        )
    assert vivas == 3


async def test_a_stale_command_cannot_terminalize_a_later_execution(
    seeded, alpha_client,
):
    """Caso 27: una orden vieja no puede cerrar la parada siguiente.

    El comando apunta a un viaje concreto, así que reenviarlo después sólo puede
    afectar a aquel viaje — y aquel ya terminó, de modo que no cambia nada.
    """
    await _sembrar_valores(seeded.alpha.id)
    _, primero = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{primero['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    completado = await _id_de(alpha_client, "outcomes", "Completed")
    original = (
        await alpha_client.post(
            f"/api/trips/{primero['id']}/activity/complete",
            json={"action": "complete", "outcome_id": completado},
        )
    ).json()

    # Segunda parada, ya en marcha.
    segundo = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    await alpha_client.post(f"/api/trips/{segundo['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{segundo['id']}/arrive", json={})
    await alpha_client.post(
        f"/api/trips/{segundo['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )

    # Llega tarde la orden de la primera, con otro resultado.
    escalado = await _id_de(alpha_client, "outcomes", "Escalated")
    tardia = await alpha_client.post(
        f"/api/trips/{primero['id']}/activity/complete",
        json={"action": "complete", "outcome_id": escalado},
    )

    assert tardia.json()["outcome_label"] == original["outcome_label"], (
        "no reescribe el resultado de la parada que ya terminó"
    )
    segunda = (await alpha_client.get(f"/api/trips/{segundo['id']}/activity")).json()
    assert segunda["status"] == "in_progress", "y no toca la parada en curso"


async def test_a_value_from_another_tenant_is_rejected(seeded, alpha_client):
    """Caso 28."""
    await _sembrar_valores(seeded.alpha.id)
    await _sembrar_valores(seeded.beta.id)

    async with TenantClient("beta") as beta:
        await beta.login(seeded.beta.users["route_admin"].email)
        ajeno = (await _valores(beta, "client_visit_activities"))[0]["id"]

    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": [ajeno]}
    )
    assert respuesta.status_code == 422


# ── Tiempo de ocurrencia, autorización y auditoría ──────────────────────────


async def test_a_queued_command_keeps_the_time_it_was_pressed(seeded, alpha_client):
    """La semántica D-10, también aquí: la duración es la real, no la de sincronizar."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")

    # El arranque se fecha **después** de llegar: pulsarlo antes sería evidencia
    # imposible y el servidor usaría su propio reloj, con razón. Lo que se
    # comprueba es que una acción encolada conserve su hora, no que se acepte
    # cualquier hora.
    async with async_session_maker() as session:
        llegada = await session.scalar(
            text("SELECT arrived_at FROM trip WHERE id = :i"), {"i": viaje["id"]}
        )
    # A mitad de camino entre la llegada y ahora: posterior a llegar —antes
    # sería imposible— y anterior a la recepción, que es lo que ocurre cuando la
    # acción espera en la cola.
    ahora = datetime.now(timezone.utc)
    pulsado = llegada + (ahora - llegada) / 2

    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={
                "activity_ids": [actividad],
                "device_captured_at": pulsado.isoformat(),
            },
        )
    ).json()

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT started_at, started_received_at, started_at_source "
                    "FROM activity_execution WHERE id = :i"
                ),
                {"i": bloque["id"]},
            )
        ).one()

    assert fila.started_at < fila.started_received_at
    assert fila.started_at_source == "device"
    assert abs((fila.started_at - pulsado).total_seconds()) < 2


async def test_a_queued_terminal_command_keeps_the_time_it_was_pressed(
    seeded, alpha_client,
):
    """Y la hora de cierre también, que es la que fija la duración.

    Sin esto, una parada de cuarenta minutos cerrada al recuperar cobertura dos
    horas después mediría dos horas cuarenta. La duración es un dato operativo
    —se factura y se audita con él—, así que el extremo de cierre tiene la misma
    semántica D-10 que el de apertura: `ended_at` es cuando se pulsó,
    `ended_received_at` cuando el servidor lo supo.
    """
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()

    async with async_session_maker() as session:
        inicio = await session.scalar(
            text("SELECT started_at FROM activity_execution WHERE id = :i"),
            {"i": bloque["id"]},
        )

    # Entre el inicio y ahora: posterior a empezar —antes sería imposible— y
    # anterior a la recepción, que es lo que ocurre al esperar en la cola.
    ahora = datetime.now(timezone.utc)
    pulsado = inicio + (ahora - inicio) / 2

    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={
            "action": "complete",
            "outcome_id": resultado,
            "device_captured_at": pulsado.isoformat(),
        },
    )
    assert respuesta.status_code == 200, respuesta.text

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT started_at, ended_at, ended_received_at, "
                    "ended_at_source FROM activity_execution WHERE id = :i"
                ),
                {"i": bloque["id"]},
            )
        ).one()

    assert fila.ended_at_source == "device"
    assert fila.ended_at < fila.ended_received_at
    assert abs((fila.ended_at - pulsado).total_seconds()) < 2
    assert fila.ended_at > fila.started_at, (
        "la restricción de la base lo exige, y la duración sale de esta resta"
    )


async def test_the_supervisor_executes_but_never_manages(seeded, alpha_client):
    """Read + Execute. RTE05 no introduce ninguna capacidad nueva."""
    from app.routers_api.users.permissions import get_user_permissions

    concedidas = await get_user_permissions(
        user_id=seeded.alpha.users["supervisor"].id, company_id=seeded.alpha.id
    )
    assert concedidas == {"route.worksession.execute", "route.standardvalues.read"}


async def test_another_supervisors_execution_is_not_reachable(seeded, alpha_client):
    """Aislamiento dentro del propio tenant."""
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.get(f"/api/trips/{viaje['id']}/activity")
    assert respuesta.status_code == 404, "ni se confirma que exista"


@pytest.mark.parametrize("accion", ["complete", "leave"])
async def test_the_lifecycle_is_audited(seeded, alpha_client, accion):
    """Las **dos** salidas se auditan, no sólo completar.

    Marcharse es una decisión con resultado, así que deja el mismo rastro que
    terminar. Se comprueban además los datos que hacen trazable el hecho: quién,
    en qué compañía, sobre qué viaje y cuándo.
    """
    await _sembrar_valores(seeded.alpha.id)
    _, viaje = await _llegar(alpha_client, seeded, purpose="client_visit")
    actividad = await _id_de(alpha_client, "client_visit_activities", "Service Review")
    bloque = (
        await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [actividad]},
        )
    ).json()
    resultado = await _id_de(alpha_client, "outcomes", "Completed")
    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/{accion}",
        json={"action": accion, "outcome_id": resultado},
    )
    assert respuesta.status_code == 200, respuesta.text

    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT action, actor_user_id, company_id, entity_id, "
                "occurred_at, changes::text AS changes FROM audit_event "
                "WHERE company_id = :c AND entity_type = 'activity_execution' "
                "ORDER BY id"
            ),
            {"c": seeded.alpha.id},
        )
        eventos = filas.all()

    assert {e.action for e in eventos} == {"start", accion}
    assert all(e.actor_user_id == seeded.alpha.users["supervisor"].id for e in eventos)
    assert all(e.company_id == seeded.alpha.id for e in eventos)
    assert all(e.entity_id == bloque["id"] for e in eventos)
    assert all(e.occurred_at is not None for e in eventos)

    # El viaje es trazable desde el rastro: sin eso, el evento no se puede
    # situar en la jornada que lo produjo.
    arranque = json.loads(
        next(e for e in eventos if e.action == "start").changes
    )
    cierre = json.loads(next(e for e in eventos if e.action == accion).changes)
    assert arranque["trip_id"]["new"] == viaje["id"]
    assert cierre["trip_status"]["new"] == "closed"
    assert cierre["terminal_action"]["new"] == accion
    assert cierre["outcome"]["new"] == "Completed"
