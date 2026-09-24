"""
Ciclo de vida del Admin de CER Route (addendum RTE02-A01).

Lo que este archivo demuestra, y por qué cada bloque existe
-------------------------------------------------------------
El addendum pide una cosa por encima de todas: **probar que borrar no es otro
nombre para desactivar**. Y pide probarlo de forma que un solo indicador de
estado no pueda explicar los dos resultados, porque si `is_active` bastara para
justificar ambos comportamientos, la implementación podría ser la misma con dos
etiquetas y el test no lo notaría.

Por eso la discriminación se hace siempre igual: se crean **dos** registros, se
desactiva uno y se borra el otro, y se comprueba que la vista de inactivos
—donde el desactivado *sí* aparece— contiene exactamente uno. Un `is_active`
compartido no puede producir ese resultado.

Bloques:

* **Discriminación de ciclo de vida** por entidad: desactivar retira del uso
  pero deja en la administración; reactivar restaura; borrar saca de ambas
  vistas; y la fila sigue existiendo para la historia.
* **Aprovisionamiento**: los valores exactos aprobados, y las cuatro cosas que
  re-ejecutarlo no puede hacer (duplicar, renombrar de vuelta, resucitar lo
  borrado, reactivar lo desactivado).
* **Autorización**: cada acción de borrado la exige el servidor, por tenant.
* **Integridad del núcleo**: borrar una designación de Route o una pertenencia
  no destruye la identidad de plataforma.
* **Reglas de negocio**: una asignación vigente bloquea el borrado, con motivo.
* **Historia**: el snapshot de una jornada sigue siendo legible después.
"""

import pytest
from sqlalchemy import select, text

from app.database import async_session_maker
from app.routers_api.companies.models import UserCompany
from app.routers_api.standardvalues.models import StandardValue, StandardValueList
from app.routers_api.standardvalues.provisioning import (
    INITIAL_VALUES,
    provision_standard_values,
    seed_key_for,
)
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import SupervisorProfile, Vehicle
from tests.integration.conftest import TEST_PASSWORD, TenantClient


pytestmark = pytest.mark.integration


TODAS_LAS_LISTAS = tuple(codigo.value for codigo in StandardValueList)


# ── Ayudas ──────────────────────────────────────────────────────────────────


async def _crear_valor(cliente, list_code: str, label: str) -> dict:
    respuesta = await cliente.post(
        "/api/standard-values", json={"list_code": list_code, "label": label}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _crear_vehiculo(cliente, unit: str) -> dict:
    respuesta = await cliente.post(
        "/api/vehicles",
        json={
            "make": "Toyota", "model": "RAV4", "year": 2024, "unit": unit,
            "fuel_grade": "regular", "operational_mpg": "27.00",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _etiquetas(cliente, list_code: str, *, incluir_inactivos: bool) -> list[str]:
    sufijo = "?include_inactive=true" if incluir_inactivos else ""
    respuesta = await cliente.get(f"/api/standard-values/{list_code}{sufijo}")
    assert respuesta.status_code == 200, respuesta.text
    return [fila["label"] for fila in respuesta.json()]


# ── Discriminación: valores de lista ────────────────────────────────────────


async def test_deactivate_removes_from_operational_use_but_keeps_it_in_admin(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Temporary")

    await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"is_active": False, "version": valor["version"]},
    )

    assert "Temporary" not in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=False
    ), "un valor desactivado no se ofrece en el uso operativo"
    assert "Temporary" in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=True
    ), "pero el administrador lo sigue viendo, que es lo que lo hace reversible"


async def test_reactivate_restores_the_value(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Temporary")

    desactivado = (
        await alpha_client.put(
            f"/api/standard-values/{valor['id']}",
            json={"is_active": False, "version": valor["version"]},
        )
    ).json()
    await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"is_active": True, "version": desactivado["version"]},
    )

    assert "Temporary" in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=False
    )


async def test_delete_removes_the_value_from_both_admin_views(seeded, alpha_client):
    """Borrar lo quita también de la vista de inactivos. Ahí está la diferencia."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Mistake")

    respuesta = await alpha_client.delete(
        f"/api/standard-values/{valor['id']}?version={valor['version']}"
    )
    assert respuesta.status_code == 204, respuesta.text

    assert "Mistake" not in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=False
    )
    assert "Mistake" not in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=True
    ), "un valor borrado no reaparece al pedir los inactivos"


async def test_delete_is_not_a_synonym_for_deactivate(seeded, alpha_client):
    """El test discriminante: un solo `is_active` no puede explicar los dos.

    Se desactiva uno y se borra el otro. La vista de inactivos tiene que
    contener exactamente el desactivado. Si borrar estuviera implementado como
    desactivar, contendría los dos.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    desactivado = await _crear_valor(alpha_client, "outcomes", "Will Be Deactivated")
    borrado = await _crear_valor(alpha_client, "outcomes", "Will Be Deleted")

    await alpha_client.put(
        f"/api/standard-values/{desactivado['id']}",
        json={"is_active": False, "version": desactivado["version"]},
    )
    await alpha_client.delete(
        f"/api/standard-values/{borrado['id']}?version={borrado['version']}"
    )

    inactivos = await _etiquetas(alpha_client, "outcomes", incluir_inactivos=True)
    assert "Will Be Deactivated" in inactivos
    assert "Will Be Deleted" not in inactivos


async def test_the_deleted_row_survives_for_history(seeded, alpha_client):
    """Sale de la administración, no de la base: la historia lo referencia."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Historical")
    await alpha_client.delete(
        f"/api/standard-values/{valor['id']}?version={valor['version']}"
    )

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(StandardValue).where(StandardValue.id == valor["id"])
        )

    assert fila is not None, "la fila no se destruye"
    assert fila.deleted_at is not None, "queda marcada con su lápida"
    assert fila.label == "Historical", "y sigue resolviendo a lo que decía"


async def test_deleting_frees_the_label_for_reuse(seeded, alpha_client):
    """El índice único es parcial: la etiqueta borrada deja de ocupar sitio.

    Sin esto, borrar por error un valor lo haría irrepetible para siempre, y el
    conflicto señalaría una fila que el administrador ya no puede ver.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Recyclable")
    await alpha_client.delete(
        f"/api/standard-values/{valor['id']}?version={valor['version']}"
    )

    de_nuevo = await alpha_client.post(
        "/api/standard-values", json={"list_code": "outcomes", "label": "Recyclable"}
    )
    assert de_nuevo.status_code == 200, de_nuevo.text
    assert de_nuevo.json()["id"] != valor["id"], "es una fila nueva, no la resucitada"


async def test_a_deleted_value_cannot_be_updated_or_deleted_again(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Gone")
    await alpha_client.delete(
        f"/api/standard-values/{valor['id']}?version={valor['version']}"
    )

    assert (
        await alpha_client.put(
            f"/api/standard-values/{valor['id']}", json={"label": "Back"}
        )
    ).status_code == 404
    assert (
        await alpha_client.delete(f"/api/standard-values/{valor['id']}")
    ).status_code == 404


async def test_a_deleted_value_is_rejected_by_reorder(seeded, alpha_client):
    """Reordenar exige el conjunto exacto, y el borrado ya no está en él."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vivo = await _crear_valor(alpha_client, "outcomes", "Alive")
    muerto = await _crear_valor(alpha_client, "outcomes", "Dead")
    await alpha_client.delete(
        f"/api/standard-values/{muerto['id']}?version={muerto['version']}"
    )

    respuesta = await alpha_client.post(
        "/api/standard-values/outcomes/reorder",
        json={"value_ids": [vivo["id"], muerto["id"]]},
    )
    assert respuesta.status_code == 422

    correcto = await alpha_client.post(
        "/api/standard-values/outcomes/reorder", json={"value_ids": [vivo["id"]]}
    )
    assert correcto.status_code == 200


@pytest.mark.parametrize("list_code", TODAS_LAS_LISTAS)
async def test_every_list_supports_delete(seeded, alpha_client, list_code):
    """Las ocho, no sólo la que se probó a mano."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, list_code, "Throwaway")

    respuesta = await alpha_client.delete(
        f"/api/standard-values/{valor['id']}?version={valor['version']}"
    )
    assert respuesta.status_code == 204, respuesta.text
    assert "Throwaway" not in await _etiquetas(
        alpha_client, list_code, incluir_inactivos=True
    )


# ── Autorización y aislamiento de los valores ───────────────────────────────


async def test_deleting_a_value_requires_the_capability(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Protected")

    await alpha_client.login(seeded.alpha.users["viewer"].email)
    respuesta = await alpha_client.delete(f"/api/standard-values/{valor['id']}")
    assert respuesta.status_code == 403

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert "Protected" in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=True
    ), "el 403 no debe haber borrado nada"


async def test_one_tenant_cannot_delete_another_tenants_value(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Alpha Only")

    async with TenantClient("beta") as beta:
        await beta.login(seeded.beta.users["route_admin"].email)
        respuesta = await beta.delete(f"/api/standard-values/{valor['id']}")

    assert respuesta.status_code == 404, "no se confirma que exista"
    assert "Alpha Only" in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=True
    )


# ── Aprovisionamiento de los valores iniciales ──────────────────────────────


async def _sembrar(company_id: int):
    async with async_session_maker() as session:
        resultado = await provision_standard_values(session, company_id=company_id)
        await session.commit()
    return resultado


async def test_a_fresh_tenant_receives_the_exact_approved_values(seeded):
    resultado = await _sembrar(seeded.alpha.id)

    esperados = sum(len(v) for v in INITIAL_VALUES.values())
    assert resultado.created == esperados
    assert resultado.skipped == 0

    async with async_session_maker() as session:
        filas = await session.execute(
            select(StandardValue.list_code, StandardValue.label).where(
                StandardValue.company_id == seeded.alpha.id
            )
        )
        presentes = {(codigo, etiqueta) for codigo, etiqueta in filas.all()}

    aprobados = {
        (codigo, etiqueta)
        for codigo, etiquetas in INITIAL_VALUES.items()
        for etiqueta in etiquetas
    }
    assert presentes == aprobados, (
        "ni sinónimos ni valores de más: exactamente los aprobados"
    )


@pytest.mark.parametrize("list_code", TODAS_LAS_LISTAS)
async def test_each_list_gets_its_initial_values_in_order(
    seeded, alpha_client, list_code,
):
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    etiquetas = await _etiquetas(alpha_client, list_code, incluir_inactivos=False)
    assert etiquetas == list(INITIAL_VALUES[list_code]), (
        "el orden aprobado es el que se ve en pantalla"
    )


async def test_provisioning_twice_creates_no_duplicates(seeded):
    primera = await _sembrar(seeded.alpha.id)
    segunda = await _sembrar(seeded.alpha.id)

    assert segunda.created == 0
    assert segunda.skipped == primera.created

    async with async_session_maker() as session:
        total = await session.scalar(
            select(text("count(*)")).select_from(
                select(StandardValue.id)
                .where(StandardValue.company_id == seeded.alpha.id)
                .subquery()
            )
        )
    assert total == primera.created


async def test_a_renamed_seeded_value_is_not_reset(seeded, alpha_client):
    """Renombrar es una decisión del tenant; la siembra no la revierte."""
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valores = (await alpha_client.get("/api/standard-values/outcomes")).json()
    escalated = next(v for v in valores if v["label"] == "Escalated")
    await alpha_client.put(
        f"/api/standard-values/{escalated['id']}",
        json={"label": "Escalated to Manager", "version": escalated["version"]},
    )

    await _sembrar(seeded.alpha.id)

    etiquetas = await _etiquetas(alpha_client, "outcomes", incluir_inactivos=True)
    assert "Escalated to Manager" in etiquetas
    assert "Escalated" not in etiquetas, (
        "no se recrea con el nombre original: sería un duplicado silencioso"
    )


async def test_a_deleted_seeded_value_is_not_resurrected(seeded, alpha_client):
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valores = (await alpha_client.get("/api/standard-values/outcomes")).json()
    no_contact = next(v for v in valores if v["label"] == "No Contact")
    await alpha_client.delete(
        f"/api/standard-values/{no_contact['id']}?version={no_contact['version']}"
    )

    resultado = await _sembrar(seeded.alpha.id)

    assert resultado.created == 0, "la huella de siembra sobrevive a la lápida"
    assert "No Contact" not in await _etiquetas(
        alpha_client, "outcomes", incluir_inactivos=True
    )


async def test_a_deactivated_seeded_value_is_not_silently_reactivated(
    seeded, alpha_client,
):
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valores = (await alpha_client.get("/api/standard-values/received_by")).json()
    office = next(v for v in valores if v["label"] == "Office Staff")
    await alpha_client.put(
        f"/api/standard-values/{office['id']}",
        json={"is_active": False, "version": office["version"]},
    )

    await _sembrar(seeded.alpha.id)

    assert "Office Staff" not in await _etiquetas(
        alpha_client, "received_by", incluir_inactivos=False
    ), "sigue desactivado tras volver a sembrar"


async def test_provisioning_is_tenant_safe(seeded):
    """Sembrar alpha no escribe una sola fila en beta."""
    await _sembrar(seeded.alpha.id)

    async with async_session_maker() as session:
        de_beta = await session.execute(
            select(StandardValue.id).where(
                StandardValue.company_id == seeded.beta.id
            )
        )
    assert de_beta.all() == []


async def test_seed_key_is_stable_against_renaming(seeded):
    """La clave se deriva de la etiqueta aprobada, no de la que tenga la fila."""
    assert seed_key_for("outcomes", "Follow-up Required") == (
        "outcomes:follow_up_required"
    )
    assert seed_key_for("office_purposes", "Pickup / Drop-off") == (
        "office_purposes:pickup_drop_off"
    )


async def test_admin_created_values_have_no_seed_key(seeded, alpha_client):
    """Lo que crea el tenant no lleva huella: ninguna siembra lo tocará jamás."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Tenant Made")

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(StandardValue).where(StandardValue.id == valor["id"])
        )
    assert fila.seed_key is None


# ── Discriminación: vehículos ───────────────────────────────────────────────


async def test_vehicle_delete_is_not_a_synonym_for_deactivate(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    desactivado = await _crear_vehiculo(alpha_client, "V-DEACT")
    borrado = await _crear_vehiculo(alpha_client, "V-DEL")

    await alpha_client.post(
        f"/api/vehicles/{desactivado['id']}/deactivate",
        json={"version": desactivado["version"]},
    )
    respuesta = await alpha_client.delete(
        f"/api/vehicles/{borrado['id']}?version={borrado['version']}"
    )
    assert respuesta.status_code == 204, respuesta.text

    # La lista de administración (`/pagination`) incluye activos e inactivos.
    en_admin = {
        fila["unit"]
        for fila in (
            await alpha_client.get("/api/vehicles/pagination?page_size=100")
        ).json()["results"]
    }
    assert "V-DEACT" in en_admin, "el desactivado sigue en la administración"
    assert "V-DEL" not in en_admin, "el borrado no"

    # `GET /api/vehicles` es el selector operativo de asignación: ahí no debe
    # estar ninguno de los dos, y el addendum lo exige explícitamente para el
    # borrado ("disappear from ... operational selectors").
    en_selector = {
        fila["unit"] for fila in (await alpha_client.get("/api/vehicles")).json()
    }
    assert "V-DEACT" not in en_selector
    assert "V-DEL" not in en_selector


async def test_a_deactivated_vehicle_can_be_reactivated(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client, "V-BACK")

    desactivado = (
        await alpha_client.post(
            f"/api/vehicles/{vehiculo['id']}/deactivate",
            json={"version": vehiculo["version"]},
        )
    ).json()
    reactivado = (
        await alpha_client.post(
            f"/api/vehicles/{vehiculo['id']}/activate",
            json={"version": desactivado["version"]},
        )
    ).json()

    assert reactivado["is_active"] is True


async def test_a_current_assignment_blocks_vehicle_delete(seeded, alpha_client):
    """Y el motivo se explica en lenguaje normal, porque acaba en pantalla."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = await _crear_vehiculo(alpha_client, "V-BUSY")
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    respuesta = await alpha_client.delete(f"/api/vehicles/{vehiculo['id']}")

    assert respuesta.status_code == 409
    assert "end the current vehicle assignment" in respuesta.json()["detail"].lower()


async def test_after_ending_the_assignment_the_vehicle_can_be_deleted(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = await _crear_vehiculo(alpha_client, "V-FREED")
    asignacion = (
        await alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": vehiculo["id"]},
        )
    ).json()

    await alpha_client.post(f"/api/supervisors/assignments/{asignacion['id']}/end")
    respuesta = await alpha_client.delete(f"/api/vehicles/{vehiculo['id']}")

    assert respuesta.status_code == 204, respuesta.text


async def test_assignment_history_survives_the_vehicle_delete(seeded, alpha_client):
    """Lo que el addendum llama "no corromper referencias históricas"."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = await _crear_vehiculo(alpha_client, "V-HIST")
    asignacion = (
        await alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": vehiculo["id"]},
        )
    ).json()
    await alpha_client.post(f"/api/supervisors/assignments/{asignacion['id']}/end")
    await alpha_client.delete(f"/api/vehicles/{vehiculo['id']}")

    historial = (
        await alpha_client.get(f"/api/supervisors/{perfil['id']}/assignments")
    ).json()
    assert any(fila["id"] == asignacion["id"] for fila in historial), (
        "la asignación histórica sigue ahí después de borrar el vehículo"
    )


async def test_a_work_session_snapshot_survives_the_vehicle_delete(
    seeded, alpha_client,
):
    """La jornada guardó su snapshot; borrar el vehículo no puede romperlo."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = await _crear_vehiculo(alpha_client, "V-SNAP")
    asignacion = (
        await alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": vehiculo["id"]},
        )
    ).json()

    async with TenantClient("alpha") as supervisor:
        await supervisor.login(seeded.alpha.users["supervisor"].email)
        jornada = (await supervisor.post("/api/worksessions", json={})).json()
        assert jornada["vehicle_id"] == vehiculo["id"]
        await supervisor.post(f"/api/worksessions/{jornada['id']}/end", json={})

    await alpha_client.post(f"/api/supervisors/assignments/{asignacion['id']}/end")
    assert (
        await alpha_client.delete(f"/api/vehicles/{vehiculo['id']}")
    ).status_code == 204

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(Vehicle).where(Vehicle.id == vehiculo["id"])
        )
    assert fila is not None and fila.deleted_at is not None
    assert str(fila.operational_mpg) == "27.00", (
        "el vehículo que la jornada referencia sigue resolviendo a lo que era"
    )


async def test_deleting_a_vehicle_frees_its_unit(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    primero = await _crear_vehiculo(alpha_client, "V-REUSE")
    await alpha_client.delete(f"/api/vehicles/{primero['id']}")

    segundo = await _crear_vehiculo(alpha_client, "V-REUSE")
    assert segundo["id"] != primero["id"]


async def test_deleting_a_vehicle_requires_the_capability(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client, "V-AUTH")

    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (
        await alpha_client.delete(f"/api/vehicles/{vehiculo['id']}")
    ).status_code == 403


async def test_one_tenant_cannot_delete_another_tenants_vehicle(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _crear_vehiculo(alpha_client, "V-ALPHA")

    async with TenantClient("beta") as beta:
        await beta.login(seeded.beta.users["route_admin"].email)
        respuesta = await beta.delete(f"/api/vehicles/{vehiculo['id']}")

    assert respuesta.status_code == 404


# ── Discriminación: designación de supervisor ───────────────────────────────


async def test_deleting_a_designation_does_not_delete_the_core_user(
    seeded, alpha_client,
):
    """La exigencia central del addendum para supervisores."""
    usuario_id = seeded.alpha.users["supervisor"].id
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post("/api/supervisors", json={"user_id": usuario_id})
    ).json()

    respuesta = await alpha_client.delete(f"/api/supervisors/{perfil['id']}")
    assert respuesta.status_code == 204, respuesta.text

    async with async_session_maker() as session:
        usuario = await session.scalar(select(Users).where(Users.id == usuario_id))
        pertenencia = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == usuario_id,
                UserCompany.company_id == seeded.alpha.id,
            )
        )

    assert usuario is not None, "la identidad del núcleo no se toca"
    assert usuario.is_active is True
    assert pertenencia is not None and pertenencia.deleted_at is None, (
        "ni su pertenencia al tenant"
    )


async def test_a_deleted_designation_can_be_created_again(seeded, alpha_client):
    """El índice parcial hace reversible el borrado sin resucitar la fila."""
    usuario_id = seeded.alpha.users["supervisor"].id
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    primero = (
        await alpha_client.post("/api/supervisors", json={"user_id": usuario_id})
    ).json()
    await alpha_client.delete(f"/api/supervisors/{primero['id']}")

    segundo = await alpha_client.post(
        "/api/supervisors", json={"user_id": usuario_id}
    )
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["id"] != primero["id"]


async def test_a_deleted_designation_leaves_the_person_as_a_candidate(
    seeded, alpha_client,
):
    usuario_id = seeded.alpha.users["supervisor"].id
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post("/api/supervisors", json={"user_id": usuario_id})
    ).json()
    await alpha_client.delete(f"/api/supervisors/{perfil['id']}")

    candidatos = (await alpha_client.get("/api/supervisors/candidates")).json()
    fila = next(c for c in candidatos if c["user_id"] == usuario_id)
    assert fila["supervisor_profile_id"] is None, (
        "vuelve a figurar como designable, que es lo que hace usable el borrado"
    )


async def test_a_current_assignment_blocks_designation_delete(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = await _crear_vehiculo(alpha_client, "V-LOCKED")
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    respuesta = await alpha_client.delete(f"/api/supervisors/{perfil['id']}")
    assert respuesta.status_code == 409
    assert "end the current vehicle assignment" in respuesta.json()["detail"].lower()


async def test_the_designation_row_survives_for_history(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    await alpha_client.delete(f"/api/supervisors/{perfil['id']}")

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(SupervisorProfile).where(SupervisorProfile.id == perfil["id"])
        )
    assert fila is not None and fila.deleted_at is not None


async def test_deleting_a_designation_requires_the_capability(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()

    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (
        await alpha_client.delete(f"/api/supervisors/{perfil['id']}")
    ).status_code == 403


# ── Usuarios: borrado a nivel de tenant ─────────────────────────────────────


async def _crear_usuario(cliente, seeded, username: str) -> dict:
    respuesta = await cliente.post(
        "/api/users",
        json={
            "username": username,
            "email": f"{username}@alpha.example.com",
            "first_name": "Temp",
            "last_name": "User",
            "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles["viewer"],
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_route_admin_can_remove_a_user_from_the_company(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario = await _crear_usuario(alpha_client, seeded, "removable")

    respuesta = await alpha_client.delete(f"/api/users/{usuario['id']}")
    assert respuesta.status_code == 204, respuesta.text

    pagina = (await alpha_client.get("/api/users/pagination?page_size=100")).json()
    ids = {fila["id"] for fila in pagina["results"]}
    assert usuario["id"] not in ids, "sale de la experiencia normal del tenant"


async def test_user_delete_is_not_a_synonym_for_suspend(seeded, alpha_client):
    """Suspender lo deja en la lista con el acceso cortado; borrar lo saca."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    suspendido = await _crear_usuario(alpha_client, seeded, "tosuspend")
    borrado = await _crear_usuario(alpha_client, seeded, "todelete")

    await alpha_client.put(
        f"/api/users/{suspendido['id']}/access", json={"is_active": False}
    )
    await alpha_client.delete(f"/api/users/{borrado['id']}")

    pagina = (await alpha_client.get("/api/users/pagination?page_size=100")).json()
    ids = {fila["id"] for fila in pagina["results"]}
    assert suspendido["id"] in ids, "el suspendido sigue administrándose"
    assert borrado["id"] not in ids


async def test_a_removed_user_cannot_log_in(seeded, alpha_client):
    """No es sólo presentación: la pertenencia borrada cierra la puerta."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario = await _crear_usuario(alpha_client, seeded, "cantlogin")

    async with TenantClient("alpha") as cliente:
        antes = await cliente.login(usuario["email"])
        assert antes.status_code == 200, "antes de borrarlo, entraba"

    await alpha_client.delete(f"/api/users/{usuario['id']}")

    async with TenantClient("alpha") as cliente:
        despues = await cliente.login(usuario["email"])
    assert despues.status_code == 401


async def test_a_removed_user_loses_authorization_on_an_open_session(
    seeded, alpha_client,
):
    """Una sesión ya abierta deja de autorizar en la siguiente petición.

    403 y no 401 porque el testigo sigue siendo válido: la identidad se
    reconoce, lo que ya no existe es su acceso a esta compañía. Es el mismo
    contrato que para una pertenencia suspendida (`get_current_membership`), y
    lo que demuestra que el borrado no es sólo presentación.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario = await _crear_usuario(alpha_client, seeded, "opensession")

    async with TenantClient("alpha") as victima:
        await victima.login(usuario["email"])
        assert (await victima.get("/api/companies/profile")).status_code == 200

        await alpha_client.delete(f"/api/users/{usuario['id']}")

        despues = await victima.get("/api/companies/profile")
    assert despues.status_code == 403


async def test_removing_a_user_preserves_the_platform_identity(seeded, alpha_client):
    """Se borra la pertenencia, no la persona: puede estar en otros tenants."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario = await _crear_usuario(alpha_client, seeded, "shared")
    await alpha_client.delete(f"/api/users/{usuario['id']}")

    async with async_session_maker() as session:
        fila = await session.scalar(select(Users).where(Users.id == usuario["id"]))
        pertenencia = await session.scalar(
            select(UserCompany).where(UserCompany.user_id == usuario["id"])
        )

    assert fila is not None, "la identidad de plataforma sobrevive"
    assert fila.is_active is True, "y no se desactiva globalmente"
    assert pertenencia.deleted_at is not None, "lo que se retira es la pertenencia"


async def test_removing_a_user_does_not_grant_platform_privilege(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario = await _crear_usuario(alpha_client, seeded, "noescalation")
    await alpha_client.delete(f"/api/users/{usuario['id']}")

    async with async_session_maker() as session:
        fila = await session.scalar(select(Users).where(Users.id == usuario["id"]))
    assert fila.is_superuser is False


async def test_removing_a_user_requires_the_delete_capability(seeded, alpha_client):
    """`manager` edita y suspende, pero no retira del tenant."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario = await _crear_usuario(alpha_client, seeded, "protected")

    await alpha_client.login(seeded.alpha.users["manager"].email)
    respuesta = await alpha_client.delete(f"/api/users/{usuario['id']}")
    assert respuesta.status_code == 403, (
        "users.update no debe traer el borrado de regalo"
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    pagina = (await alpha_client.get("/api/users/pagination?page_size=100")).json()
    assert usuario["id"] in {fila["id"] for fila in pagina["results"]}


async def test_nobody_can_remove_their_own_access(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    yo = seeded.alpha.users["route_admin"].id

    respuesta = await alpha_client.delete(f"/api/users/{yo}")
    assert respuesta.status_code == 409
    assert "your own access" in respuesta.json()["detail"].lower()


async def test_one_tenant_cannot_remove_another_tenants_membership(
    seeded, alpha_client,
):
    objetivo = seeded.beta.users["viewer"].id

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.delete(f"/api/users/{objetivo}")
    assert respuesta.status_code == 404

    async with async_session_maker() as session:
        pertenencia = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == objetivo,
                UserCompany.company_id == seeded.beta.id,
            )
        )
    assert pertenencia.deleted_at is None, "la pertenencia del otro tenant intacta"


async def test_removing_a_user_keeps_their_route_history_readable(
    seeded, alpha_client,
):
    """Borrar la pertenencia no puede llevarse por delante el historial."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    usuario_id = seeded.alpha.users["supervisor"].id
    perfil = (
        await alpha_client.post("/api/supervisors", json={"user_id": usuario_id})
    ).json()
    vehiculo = await _crear_vehiculo(alpha_client, "V-LEGACY")
    asignacion = (
        await alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": vehiculo["id"]},
        )
    ).json()
    await alpha_client.post(f"/api/supervisors/assignments/{asignacion['id']}/end")

    assert (await alpha_client.delete(f"/api/users/{usuario_id}")).status_code == 204

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(SupervisorProfile).where(SupervisorProfile.id == perfil["id"])
        )
    assert fila is not None, (
        "la designación no se destruyó en cascada al borrar la pertenencia"
    )


# ── Auditoría ───────────────────────────────────────────────────────────────


async def _acciones_auditadas(company_id: int, entity_type: str) -> set[str]:
    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT action FROM audit_event "
                "WHERE company_id = :c AND entity_type = :e"
            ),
            {"c": company_id, "e": entity_type},
        )
    return {accion for (accion,) in filas.all()}


async def test_every_delete_is_audited(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valor = await _crear_valor(alpha_client, "outcomes", "Audited")
    await alpha_client.delete(f"/api/standard-values/{valor['id']}")

    vehiculo = await _crear_vehiculo(alpha_client, "V-AUDIT")
    await alpha_client.delete(f"/api/vehicles/{vehiculo['id']}")

    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    await alpha_client.delete(f"/api/supervisors/{perfil['id']}")

    usuario = await _crear_usuario(alpha_client, seeded, "auditedremoval")
    await alpha_client.delete(f"/api/users/{usuario['id']}")

    assert "delete" in await _acciones_auditadas(seeded.alpha.id, "standard_value")
    assert "delete" in await _acciones_auditadas(seeded.alpha.id, "vehicle")
    assert "delete" in await _acciones_auditadas(seeded.alpha.id, "supervisor_profile")
    assert "delete" in await _acciones_auditadas(seeded.alpha.id, "user")


async def test_the_audit_records_who_acted_and_what_was_removed(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valor = await _crear_valor(alpha_client, "outcomes", "Traceable")
    await alpha_client.delete(f"/api/standard-values/{valor['id']}")

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT actor_user_id, summary FROM audit_event "
                    "WHERE company_id = :c AND entity_type = 'standard_value' "
                    "AND action = 'delete' AND entity_id = :i"
                ),
                {"c": seeded.alpha.id, "i": valor["id"]},
            )
        ).first()

    assert fila is not None
    actor, resumen = fila
    assert actor == seeded.alpha.users["route_admin"].id
    assert "Traceable" in resumen, (
        "la pantalla ya no lo muestra; la traza tiene que decir qué se quitó"
    )
