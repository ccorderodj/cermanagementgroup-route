"""
Fundación de CER Route: vehículos, perfiles de supervisor, asignaciones y
listas configurables (RTE02).

Qué se comprueba aquí, y por qué cada cosa
------------------------------------------
* **Aislamiento entre tenants.** Con una sola compañía, "los vehículos" y "los
  vehículos de mi compañía" devuelven lo mismo; el fallo sólo se ve con dos.
* **Autorización en el servidor.** Que el menú esconda una pantalla es
  experiencia de usuario; lo que impide el acceso es el 403 del backend. Por eso
  se prueba con el rol que *no* debería poder, no sólo con el que sí.
* **Reglas que garantiza la base.** El índice único parcial y las claves
  foráneas compuestas se prueban contra PostgreSQL real, porque una comprobación
  en Python protege mientras nadie se olvide y la de la base protege siempre.
* **Historia.** Reasignar cierra la asignación anterior en vez de reescribirla,
  y retirar un valor no lo borra: una actividad de marzo tiene que seguir
  resolviendo lo que eligió.
"""

import asyncio

import pytest
from sqlalchemy import select, text

from app.database import async_session_maker
from app.routers_api.vehicles.models import SupervisorProfile, VehicleAssignment


pytestmark = pytest.mark.integration


VEHICULO = {
    "make": "Toyota",
    "model": "RAV4",
    "year": 2024,
    "unit": "V-014",
    "fuel_grade": "regular",
    "operational_mpg": "27.00",
}


async def _crear_vehiculo(client, **overrides):
    payload = {**VEHICULO, **overrides}
    response = await client.post("/api/vehicles", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def _crear_supervisor(client, user_id: int):
    response = await client.post("/api/supervisors", json={"user_id": user_id})
    assert response.status_code == 200, response.text
    return response.json()


# ── Aislamiento entre compañías ─────────────────────────────────────────────


async def test_a_vehicle_of_another_company_is_not_found(
    seeded, alpha_client, beta_client,
):
    """404 y no 403: confirmar que existe ya sería filtrar información."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)

    await beta_client.login(seeded.beta.users["route_admin"].email)

    assert (await beta_client.get(f"/api/vehicles/{vehiculo['id']}")).status_code == 404
    assert (
        await beta_client.put(
            f"/api/vehicles/{vehiculo['id']}", json={"make": "Hijacked"}
        )
    ).status_code == 404


async def test_vehicle_listing_does_not_cross_tenants(
    seeded, alpha_client, beta_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await _crear_vehiculo(alpha_client, unit="ALPHA-1")

    await beta_client.login(seeded.beta.users["route_admin"].email)
    await _crear_vehiculo(beta_client, unit="BETA-1")

    unidades_beta = {v["unit"] for v in (await beta_client.get("/api/vehicles")).json()}
    assert unidades_beta == {"BETA-1"}


async def test_standard_values_do_not_cross_tenants(
    seeded, alpha_client, beta_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Alpha only"},
    )

    await beta_client.login(seeded.beta.users["route_admin"].email)
    etiquetas = {
        v["label"]
        for v in (await beta_client.get("/api/standard-values/outcomes")).json()
    }
    assert "Alpha only" not in etiquetas


async def test_a_vehicle_cannot_be_assigned_across_tenants(
    seeded, alpha_client, beta_client,
):
    """La FK compuesta `(vehicle_id, company_id)` lo impide en la base."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo_alpha = await _crear_vehiculo(alpha_client, unit="ALPHA-X")

    await beta_client.login(seeded.beta.users["route_admin"].email)
    perfil_beta = await _crear_supervisor(
        beta_client, seeded.beta.users["supervisor"].id
    )

    respuesta = await beta_client.post(
        f"/api/supervisors/{perfil_beta['id']}/assignments",
        json={"vehicle_id": vehiculo_alpha["id"]},
    )
    assert respuesta.status_code == 404


async def test_a_user_of_another_company_cannot_become_a_supervisor(
    seeded, alpha_client,
):
    """`fk_supervisor_profile_membership` exige pertenencia a la compañía."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.post(
        "/api/supervisors", json={"user_id": seeded.beta.users["supervisor"].id}
    )
    assert respuesta.status_code == 404


# ── Autorización ────────────────────────────────────────────────────────────


async def test_route_admin_can_manage_vehicles(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    assert vehiculo["unit"] == "V-014"
    assert vehiculo["is_active"] is True


async def test_a_supervisor_cannot_administer_vehicles(seeded, alpha_client):
    """El rol de campo no administra configuración. Lo corta el servidor."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    assert (await alpha_client.get("/api/vehicles")).status_code == 403
    assert (
        await alpha_client.post("/api/vehicles", json=VEHICULO)
    ).status_code == 403


async def test_a_supervisor_cannot_administer_standard_values(seeded, alpha_client):
    """Lee los valores operativos, y nada más (A02/BR-03).

    Antes de A02 la lectura también se le negaba, y eso hacía imposible arrancar
    los tres contextos de viaje que exigen un valor de lista antes de salir: el
    formulario pedía el dato y recibía 403 al buscar las opciones. La lectura
    pasó a ser una capacidad propia, `route.standardvalues.read`, precisamente
    para poder concederla sin conceder administración.

    Leer para elegir no es administrar, y este test lo dice en las dos
    direcciones.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    assert (
        await alpha_client.get("/api/standard-values/outcomes")
    ).status_code == 200, "el supervisor lee los valores que su viaje exige"

    # Y no puede tocarlos de ninguna forma.
    assert (
        await alpha_client.post(
            "/api/standard-values",
            json={"list_code": "outcomes", "label": "Nope"},
        )
    ).status_code == 403
    assert (
        await alpha_client.get("/api/standard-values/lists")
    ).status_code == 403
    assert (
        await alpha_client.get("/api/standard-values/outcomes?include_inactive=true")
    ).status_code == 403


async def test_a_viewer_without_the_capability_is_denied(seeded, alpha_client):
    """Sin la capacidad no se entra, aunque se conozca la ruta exacta."""
    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (await alpha_client.get("/api/vehicles")).status_code == 403


async def test_a_supervisor_can_read_their_own_profile(seeded, alpha_client):
    """Sus propios datos no exigen capacidad, igual que `/users/profile`.

    Es el privilegio mínimo llevado al caso concreto: para ver qué vehículo
    conduce, un supervisor no necesita permiso para administrar vehículos.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )
    vehiculo = await _crear_vehiculo(alpha_client)
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.get("/api/supervisors/me")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["current_vehicle"]["unit"] == "V-014"


# ── Vehículos ───────────────────────────────────────────────────────────────


async def test_vehicle_create_read_update(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)

    respuesta = await alpha_client.put(
        f"/api/vehicles/{vehiculo['id']}",
        json={"operational_mpg": "24.50", "version": vehiculo["version"]},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["operational_mpg"] == "24.50"
    assert respuesta.json()["version"] == vehiculo["version"] + 1


async def test_a_stale_version_is_rejected_with_409(seeded, alpha_client):
    """Dos administradores editando la misma ficha: el segundo no pisa al primero."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)

    primera = await alpha_client.put(
        f"/api/vehicles/{vehiculo['id']}",
        json={"make": "Honda", "version": vehiculo["version"]},
    )
    assert primera.status_code == 200

    # La segunda llega con la versión que leyó antes, que ya no es la actual.
    segunda = await alpha_client.put(
        f"/api/vehicles/{vehiculo['id']}",
        json={"make": "Ford", "version": vehiculo["version"]},
    )
    assert segunda.status_code == 409
    assert (await alpha_client.get(f"/api/vehicles/{vehiculo['id']}")).json()[
        "make"
    ] == "Honda"


async def test_an_invalid_fuel_grade_is_rejected(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        "/api/vehicles", json={**VEHICULO, "fuel_grade": "kerosene"}
    )
    assert respuesta.status_code == 422


async def test_the_database_rejects_a_fuel_grade_outside_the_enum(seeded):
    """El `CHECK` protege aunque la escritura no pase por la API."""
    async with async_session_maker() as session:
        with pytest.raises(Exception):
            await session.execute(
                text(
                    "INSERT INTO vehicle (company_id, make, model, year, unit, "
                    "fuel_grade, operational_mpg, is_active, version) VALUES "
                    f"({seeded.alpha.id}, 'X', 'Y', 2024, 'BAD-1', 'kerosene', "
                    "20.0, true, 1)"
                )
            )
            await session.commit()
        await session.rollback()


async def test_a_duplicate_unit_in_the_same_company_is_rejected(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await _crear_vehiculo(alpha_client)

    respuesta = await alpha_client.post("/api/vehicles", json=VEHICULO)
    assert respuesta.status_code == 409


async def test_the_same_unit_may_exist_in_two_companies(
    seeded, alpha_client, beta_client,
):
    """La unicidad es por tenant: dos compañías pueden llamar igual a su unidad."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await _crear_vehiculo(alpha_client)

    await beta_client.login(seeded.beta.users["route_admin"].email)
    respuesta = await beta_client.post("/api/vehicles", json=VEHICULO)
    assert respuesta.status_code == 200


async def test_deactivating_a_vehicle_preserves_its_history(seeded, alpha_client):
    """Retirar no borra: el historial sigue apuntando al mismo vehículo."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    asignacion = await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    await alpha_client.post(
        f"/api/supervisors/assignments/{asignacion.json()['id']}/end", json={}
    )

    retirado = await alpha_client.post(
        f"/api/vehicles/{vehiculo['id']}/deactivate", json={}
    )
    assert retirado.status_code == 200
    assert retirado.json()["is_active"] is False

    historial = await alpha_client.get(f"/api/supervisors/{perfil['id']}/assignments")
    assert len(historial.json()) == 1
    assert historial.json()[0]["vehicle_unit"] == "V-014"


async def test_a_vehicle_in_use_cannot_be_retired(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    respuesta = await alpha_client.post(
        f"/api/vehicles/{vehiculo['id']}/deactivate", json={}
    )
    assert respuesta.status_code == 409


# ── Asignaciones ────────────────────────────────────────────────────────────


async def test_the_current_assignment_resolves_the_current_vehicle(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    supervisores = (await alpha_client.get("/api/supervisors")).json()
    actual = next(s for s in supervisores if s["id"] == perfil["id"])
    assert actual["current_vehicle"]["unit"] == "V-014"


async def test_a_supervisor_without_an_assignment_has_no_vehicle(
    seeded, alpha_client,
):
    """Estado normal, no error: alguien recién designado no conduce nada."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    supervisores = (await alpha_client.get("/api/supervisors")).json()
    actual = next(s for s in supervisores if s["id"] == perfil["id"])
    assert actual["current_vehicle"] is None


async def test_reassignment_closes_the_previous_one_instead_of_overwriting(
    seeded, alpha_client,
):
    """La fila anterior sigue ahí, con su fecha de fin. La historia no se pisa."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    primero = await _crear_vehiculo(alpha_client, unit="V-001")
    segundo = await _crear_vehiculo(alpha_client, unit="V-002")
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": primero["id"]},
    )
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": segundo["id"]},
    )

    historial = (
        await alpha_client.get(f"/api/supervisors/{perfil['id']}/assignments")
    ).json()

    assert len(historial) == 2, "la asignación anterior debe seguir existiendo"
    vigentes = [fila for fila in historial if fila["effective_to"] is None]
    assert len(vigentes) == 1
    assert vigentes[0]["vehicle_unit"] == "V-002"

    cerradas = [fila for fila in historial if fila["effective_to"] is not None]
    assert cerradas[0]["vehicle_unit"] == "V-001"


async def test_the_database_prevents_two_current_assignments(seeded):
    """El índice único parcial, probado saltándose la API.

    Es la garantía que sobrevive a un servicio que se olvide de comprobarlo y a
    dos peticiones simultáneas: PostgreSQL rechaza la segunda fila vigente.
    """
    from datetime import datetime, timezone

    from sqlalchemy import insert

    from app.routers_api.vehicles.models import Vehicle

    async with async_session_maker() as session:
        vehicle_id = (
            await session.execute(
                insert(Vehicle)
                .values(
                    company_id=seeded.alpha.id,
                    make="T", model="M", year=2024, unit="DB-1",
                    fuel_grade="regular", operational_mpg=20,
                    is_active=True, version=1,
                )
                .returning(Vehicle.id)
            )
        ).scalar_one()

        profile_id = (
            await session.execute(
                insert(SupervisorProfile)
                .values(
                    company_id=seeded.alpha.id,
                    user_id=seeded.alpha.users["supervisor"].id,
                    is_active=True, version=1,
                )
                .returning(SupervisorProfile.id)
            )
        ).scalar_one()

        await session.execute(
            insert(VehicleAssignment).values(
                company_id=seeded.alpha.id,
                supervisor_profile_id=profile_id,
                vehicle_id=vehicle_id,
                effective_from=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(Exception):
            await session.execute(
                insert(VehicleAssignment).values(
                    company_id=seeded.alpha.id,
                    supervisor_profile_id=profile_id,
                    vehicle_id=vehicle_id,
                    effective_from=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        await session.rollback()


async def test_concurrent_assignment_requests_produce_one_current_row(
    seeded, alpha_client,
):
    """Dos peticiones a la vez: una gana, la otra recibe un error, nunca dos."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    primero = await _crear_vehiculo(alpha_client, unit="C-1")
    segundo = await _crear_vehiculo(alpha_client, unit="C-2")
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    respuestas = await asyncio.gather(
        alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": primero["id"]},
        ),
        alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": segundo["id"]},
        ),
        return_exceptions=True,
    )

    codigos = [
        r.status_code for r in respuestas if not isinstance(r, BaseException)
    ]
    assert 200 in codigos, f"ninguna asignación prosperó: {codigos}"

    async with async_session_maker() as session:
        vigentes = (
            await session.execute(
                select(VehicleAssignment).where(
                    VehicleAssignment.company_id == seeded.alpha.id,
                    VehicleAssignment.supervisor_profile_id == perfil["id"],
                    VehicleAssignment.effective_to.is_(None),
                )
            )
        ).scalars().all()

    assert len(vigentes) == 1, (
        f"quedaron {len(vigentes)} asignaciones vigentes; el índice parcial "
        "debe permitir exactamente una"
    )


async def test_ending_an_assignment_leaves_the_supervisor_without_a_vehicle(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    asignacion = await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    cerrada = await alpha_client.post(
        f"/api/supervisors/assignments/{asignacion.json()['id']}/end", json={}
    )

    assert cerrada.status_code == 200
    assert cerrada.json()["effective_to"] is not None

    supervisores = (await alpha_client.get("/api/supervisors")).json()
    actual = next(s for s in supervisores if s["id"] == perfil["id"])
    assert actual["current_vehicle"] is None


# ── Listas configurables ────────────────────────────────────────────────────


async def test_all_eight_approved_lists_are_available(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    listas = (await alpha_client.get("/api/standard-values/lists")).json()

    codigos = {fila["code"] for fila in listas}
    assert codigos == {
        "client_visit_activities",
        "recruiting_activities",
        "employee_visit_reasons",
        "delivery_types",
        "office_purposes",
        "other_activities",
        "outcomes",
        "received_by",
    }


async def test_an_invalid_list_code_is_rejected(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    assert (
        await alpha_client.get("/api/standard-values/client_destinations")
    ).status_code == 422
    assert (
        await alpha_client.post(
            "/api/standard-values",
            json={"list_code": "client_destinations", "label": "Nope"},
        )
    ).status_code == 422


async def test_outcomes_are_tenant_data_and_not_seeded_by_the_product(
    seeded, alpha_client,
):
    """Outcome es configurable: una compañía nueva no trae valores impuestos.

    Si el producto sembrara "Completed" y compañía, sería un enum disfrazado de
    dato, que es justo lo que la decisión A-3 del cierre de RTE01 prohíbe.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valores = (await alpha_client.get("/api/standard-values/outcomes")).json()
    assert valores == []

    creado = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Follow-up Required"},
    )
    assert creado.status_code == 200
    assert creado.json()["label"] == "Follow-up Required"


async def test_a_retired_value_remains_resolvable_for_history(seeded, alpha_client):
    """Retirar quita la opción del formulario, no el dato del pasado."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = (
        await alpha_client.post(
            "/api/standard-values",
            json={"list_code": "outcomes", "label": "Escalated"},
        )
    ).json()

    retirado = await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"is_active": False, "version": valor["version"]},
    )
    assert retirado.status_code == 200
    assert retirado.json()["is_active"] is False

    # Fuera del formulario operativo...
    activos = (await alpha_client.get("/api/standard-values/outcomes")).json()
    assert [v["id"] for v in activos] == []

    # ...pero sigue existiendo y se puede resolver.
    todos = (
        await alpha_client.get("/api/standard-values/outcomes?include_inactive=true")
    ).json()
    assert [v["id"] for v in todos] == [valor["id"]]


async def test_a_retired_value_can_be_restored(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = (
        await alpha_client.post(
            "/api/standard-values",
            json={"list_code": "outcomes", "label": "No Contact"},
        )
    ).json()

    retirado = (
        await alpha_client.put(
            f"/api/standard-values/{valor['id']}",
            json={"is_active": False, "version": valor["version"]},
        )
    ).json()
    restaurado = await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"is_active": True, "version": retirado["version"]},
    )

    assert restaurado.status_code == 200
    assert restaurado.json()["is_active"] is True


async def test_the_same_label_may_exist_in_two_different_lists(
    seeded, alpha_client,
):
    """Son listas distintas: "Completed" puede ser Outcome y Delivery Type."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    primera = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Completed"},
    )
    segunda = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "delivery_types", "label": "Completed"},
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200


async def test_a_duplicate_label_in_the_same_list_is_rejected(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Completed"},
    )

    repetida = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Completed"},
    )
    assert repetida.status_code == 409


async def test_the_same_label_may_exist_in_two_companies(
    seeded, alpha_client, beta_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Completed"},
    )

    await beta_client.login(seeded.beta.users["route_admin"].email)
    respuesta = await beta_client.post(
        "/api/standard-values",
        json={"list_code": "outcomes", "label": "Completed"},
    )
    assert respuesta.status_code == 200


async def test_values_can_be_reordered(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    primero = (
        await alpha_client.post(
            "/api/standard-values", json={"list_code": "outcomes", "label": "A"}
        )
    ).json()
    segundo = (
        await alpha_client.post(
            "/api/standard-values", json={"list_code": "outcomes", "label": "B"}
        )
    ).json()

    reordenado = await alpha_client.post(
        "/api/standard-values/outcomes/reorder",
        json={"value_ids": [segundo["id"], primero["id"]]},
    )
    assert reordenado.status_code == 200
    assert [v["label"] for v in reordenado.json()] == ["B", "A"]


async def test_a_partial_reorder_is_rejected(seeded, alpha_client):
    """Aceptar un subconjunto dejaría el resto en un orden indeterminado."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    primero = (
        await alpha_client.post(
            "/api/standard-values", json={"list_code": "outcomes", "label": "A"}
        )
    ).json()
    await alpha_client.post(
        "/api/standard-values", json={"list_code": "outcomes", "label": "B"}
    )

    respuesta = await alpha_client.post(
        "/api/standard-values/outcomes/reorder",
        json={"value_ids": [primero["id"]]},
    )
    assert respuesta.status_code == 422


# ── Auditoría ───────────────────────────────────────────────────────────────


async def test_vehicle_changes_are_audited(seeded, alpha_client):
    """La traza dice quién, qué, cuándo y qué cambió."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    await alpha_client.put(
        f"/api/vehicles/{vehiculo['id']}",
        json={"make": "Honda", "version": vehiculo["version"]},
    )

    async with async_session_maker() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT action, actor_user_id, changes FROM audit_event "
                    "WHERE entity_type = 'vehicle' AND entity_id = :id "
                    "ORDER BY id"
                ),
                {"id": vehiculo["id"]},
            )
        ).mappings().all()

    acciones = [fila["action"] for fila in filas]
    assert acciones == ["create", "update"]
    assert all(
        fila["actor_user_id"] == seeded.alpha.users["route_admin"].id
        for fila in filas
    )
    assert filas[1]["changes"]["make"] == {"old": "Toyota", "new": "Honda"}


async def test_assignment_changes_are_audited(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client)
    perfil = await _crear_supervisor(
        alpha_client, seeded.alpha.users["supervisor"].id
    )
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    async with async_session_maker() as session:
        total = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_event "
                    "WHERE entity_type = 'vehicle_assignment'"
                )
            )
        ).scalar_one()

    assert total >= 1


async def test_standard_value_changes_are_audited(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = (
        await alpha_client.post(
            "/api/standard-values",
            json={"list_code": "outcomes", "label": "Completed"},
        )
    ).json()
    await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"label": "Completed on site", "version": valor["version"]},
    )

    async with async_session_maker() as session:
        acciones = (
            await session.execute(
                text(
                    "SELECT action FROM audit_event WHERE entity_type = "
                    "'standard_value' AND entity_id = :id ORDER BY id"
                ),
                {"id": valor["id"]},
            )
        ).scalars().all()

    assert list(acciones) == ["create", "update"]
