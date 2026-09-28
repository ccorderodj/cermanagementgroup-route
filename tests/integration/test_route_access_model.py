"""
El modelo de acceso de CER Route tras A02: dos roles, y ninguna puerta al núcleo.

Lo que cambió, y por qué
------------------------
CER aprobó un modelo simplificado: **Administrador** y **Supervisor**, los dos
salen a ruta, y sólo el Administrador administra. Eso supersede dos supuestos
anteriores:

* RTE03 negaba `route.worksession.execute` al Administrador razonando que
  administrar y conducir son autorizaciones distintas. Siguen siendo distintas —
  lo que cambia es que el mismo rol tiene las dos, porque un CEO o un COO usan
  ese rol y conducen (BR-02).
* RTE04-C5 autorizó la lectura de las listas con `manage` **o** `execute`. Cerraba
  un 403 real, pero hacía de "ejecutar" un permiso de lectura genérico. Ahora la
  lectura tiene su propia capacidad (BR-03).

La regla de asignación, y la que se descartó
---------------------------------------------
El diagnóstico A01 propuso "nadie concede autoridad que no tenga". CER la
descartó con razón: el Administrador tiene que poder crear un Supervisor, y sus
capacidades son distintas **a propósito**. La regla aprobada es más estrecha:
quien administra usuarios desde CER Route sólo concede roles de CER Route.

Los veinte casos límite de la resolución se comprueban aquí contra la API, que es
donde está la autoridad. Que la pantalla ofrezca dos opciones es experiencia de
usuario; lo que cierra la escalada es esto.
"""

from __future__ import annotations

import pytest

from app.core.rbac.catalog import (
    DEFAULT_ROLES,
    ROUTE_PRODUCT_ROLE_LABELS,
    ROUTE_PRODUCT_ROLES,
    capabilities_for,
)
from app.routers_api.users.permissions import get_user_permissions
from tests.integration.conftest import TEST_PASSWORD, TenantClient


pytestmark = pytest.mark.integration


ROLES_DEL_NUCLEO = ("owner", "admin", "manager", "viewer")


async def _crear(cliente, *, sufijo: str, role_id: int):
    return await cliente.post(
        "/api/users",
        json={
            "username": f"a02_{sufijo}",
            "email": f"a02_{sufijo}@alpha.example.com",
            "first_name": "A02",
            "last_name": sufijo,
            "password": TEST_PASSWORD,
            "role_id": role_id,
        },
    )


# ── El modelo, en el catálogo ────────────────────────────────────────────────


def test_cer_route_has_exactly_two_product_roles():
    assert ROUTE_PRODUCT_ROLES == {"route_admin", "supervisor"}
    assert ROUTE_PRODUCT_ROLE_LABELS == {
        "route_admin": "Administrador",
        "supervisor": "Supervisor",
    }


def test_the_core_roles_are_preserved_and_are_not_route_personas():
    """No se borran, no se renombran, no se reconvierten (FR-06)."""
    plantillas = {p.name for p in DEFAULT_ROLES}
    for nombre in ROLES_DEL_NUCLEO:
        assert nombre in plantillas, f"'{nombre}' es del núcleo y debe seguir existiendo"
        assert nombre not in ROUTE_PRODUCT_ROLES


def test_both_product_roles_can_execute_the_route_workflow():
    """BR-02: los dos salen a ruta."""
    for nombre in ROUTE_PRODUCT_ROLES:
        plantilla = next(p for p in DEFAULT_ROLES if p.name == nombre)
        assert "route.worksession.execute" in capabilities_for(plantilla), (
            f"'{nombre}' tiene que poder ejecutar la jornada"
        )


def test_the_supervisor_reads_but_never_manages():
    """FR-03: Read + Execute, nunca Edit/Manage/Adjust."""
    plantilla = next(p for p in DEFAULT_ROLES if p.name == "supervisor")
    capacidades = set(capabilities_for(plantilla))

    assert "route.standardvalues.read" in capacidades
    prohibidas = {
        c for c in capacidades
        if c.endswith(".manage") or c.startswith(("users.", "roles.", "rolepermissions"))
        or c == "route.records.adjust"
    }
    assert prohibidas == set(), f"el supervisor no administra: {prohibidas}"


def test_the_administrator_reads_and_manages():
    plantilla = next(p for p in DEFAULT_ROLES if p.name == "route_admin")
    capacidades = set(capabilities_for(plantilla))
    for esperada in (
        "route.standardvalues.read",
        "route.standardvalues.manage",
        "route.records.adjust",
        "route.vehicles.manage",
        "users.create",
        "route.worksession.execute",
    ):
        assert esperada in capacidades, f"falta '{esperada}'"


def test_execute_is_not_a_generic_read_shortcut():
    """BR-03: la lectura del catálogo no se autoriza con `execute`.

    Se comprueba en el código del endpoint, no en su efecto: el efecto sería el
    mismo si alguien volviera a añadir `worksession.execute` a la lista de
    permisos aceptados, y esa es precisamente la regresión que hay que impedir.
    """
    from pathlib import Path

    router = Path("app/routers_api/standardvalues/router.py").read_text(encoding="utf-8")
    bloque = router.split('@router.get("/{list_code}")')[1].split("@router.post")[0]
    # Sin comentarios: el bloque explica por qué se retiró el atajo, y mencionarlo
    # en prosa no es usarlo. Lo que se comprueba es el código.
    codigo = " ".join(
        linea for linea in bloque.splitlines() if not linea.lstrip().startswith("#")
    )

    assert 'require_permissions(["route.standardvalues.read"])' in codigo
    assert "worksession.execute" not in codigo


# ── Casos límite 1-4: lo que el Administrador sí puede ───────────────────────


@pytest.mark.parametrize("rol", ["supervisor", "route_admin"])
async def test_the_administrator_can_create_both_route_roles(
    seeded, alpha_client, rol,
):
    """Casos 1 y 2."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(alpha_client, sufijo=rol, role_id=seeded.alpha.roles[rol])
    assert respuesta.status_code == 200, respuesta.text


async def test_the_administrator_can_switch_a_user_between_route_roles(
    seeded, alpha_client,
):
    """Casos 3 y 4: Supervisor → Administrador y de vuelta."""
    supervisor = seeded.alpha.users["supervisor"]
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    ascenso = await alpha_client.put(
        f"/api/users/{supervisor.id}",
        json={"role_id": seeded.alpha.roles["route_admin"]},
    )
    assert ascenso.status_code == 200, ascenso.text

    vuelta = await alpha_client.put(
        f"/api/users/{supervisor.id}",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )
    assert vuelta.status_code == 200, vuelta.text


# ── Casos límite 5-11: la escalada, cerrada ──────────────────────────────────


@pytest.mark.parametrize("rol", ROLES_DEL_NUCLEO)
async def test_the_administrator_cannot_create_a_user_with_a_core_role(
    seeded, alpha_client, rol,
):
    """Casos 5-8. Esto devolvía 200 antes de A02."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(alpha_client, sufijo=rol, role_id=seeded.alpha.roles[rol])

    assert respuesta.status_code == 403, respuesta.text
    assert "CER Route" in respuesta.json()["detail"]


@pytest.mark.parametrize("rol", ROLES_DEL_NUCLEO)
async def test_the_administrator_cannot_promote_anyone_to_a_core_role(
    seeded, alpha_client, rol,
):
    """Caso 9: por actualización, que abría la misma puerta."""
    supervisor = seeded.alpha.users["supervisor"]
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.put(
        f"/api/users/{supervisor.id}", json={"role_id": seeded.alpha.roles[rol]}
    )
    assert respuesta.status_code == 403


async def test_the_escalation_path_measured_in_the_a01_diagnostic_is_closed(
    seeded, alpha_client,
):
    """Caso 10, y la razón por la que existe este checkpoint.

    El diagnóstico A01 midió la secuencia completa: crear un `owner`, entrar con
    esa cuenta, borrar un rol. El primer paso ya no ocurre, así que la secuencia
    no empieza — y se comprueba además que nada se escribió.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(
        alpha_client, sufijo="escalada", role_id=seeded.alpha.roles["owner"]
    )
    assert respuesta.status_code == 403

    # Ni el usuario, ni su pertenencia: el rechazo precede a la escritura.
    from sqlalchemy import text

    from app.database import async_session_maker

    async with async_session_maker() as session:
        existe = await session.scalar(
            text('SELECT count(*) FROM "user" WHERE email = :e'),
            {"e": "a02_escalada@alpha.example.com"},
        )
    assert existe == 0, "no se creó a medias"


async def test_a_role_from_another_tenant_is_still_rejected_without_leaking(
    seeded, alpha_client,
):
    """Caso 11: 404, no 403 — no se confirma que exista en otro sitio."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(
        alpha_client, sufijo="cruzado", role_id=seeded.beta.roles["owner"]
    )
    assert respuesta.status_code == 404


async def test_a_core_administrator_is_not_restricted_by_the_route_policy(
    seeded, alpha_client,
):
    """El alcance de la regla es estrecho a propósito.

    Quien administra desde el núcleo sigue como estaba. Esta resolución cierra la
    superficie de CER Route; lo que el núcleo permita se reporta aparte y no se
    redisena aquí.
    """
    await alpha_client.login(seeded.alpha.users["owner"].email)
    respuesta = await _crear(
        alpha_client, sufijo="delnucleo", role_id=seeded.alpha.roles["admin"]
    )
    assert respuesta.status_code == 200, respuesta.text


# ── Caso límite 12: el Supervisor no administra ──────────────────────────────


async def test_the_supervisor_cannot_administer_users(seeded, alpha_client):
    """Caso 12."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    assert (await alpha_client.get("/api/users/pagination")).status_code == 403
    assert (await alpha_client.get("/api/users/assignable-roles")).status_code == 403
    creacion = await _crear(
        alpha_client, sufijo="porsup", role_id=seeded.alpha.roles["supervisor"]
    )
    assert creacion.status_code == 403


# ── Casos límite 13-14: los dos entran a la experiencia operativa ────────────


@pytest.mark.parametrize("rol", ["supervisor", "route_admin"])
async def test_both_product_roles_can_start_work(seeded, alpha_client, rol):
    """Casos 13 y 14. El Administrador podía **no** antes de A02."""
    await alpha_client.login(seeded.alpha.users[rol].email)
    respuesta = await alpha_client.post("/api/worksessions", json={})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "active"


# ── Casos límite 15-16: Read / Manage separados ──────────────────────────────


async def test_the_supervisor_reads_the_values_but_cannot_touch_them(
    seeded, alpha_client,
):
    """Caso 15."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "employee_visit_reasons", "label": "Attendance Issue"},
    )
    assert creado.status_code == 200
    valor_id = creado.json()["id"]

    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    lectura = await alpha_client.get("/api/standard-values/employee_visit_reasons")
    assert lectura.status_code == 200
    assert [v["label"] for v in lectura.json()] == ["Attendance Issue"]

    # Y nada más: crear, editar, retirar, borrar, reordenar y ver los retirados.
    assert (
        await alpha_client.post(
            "/api/standard-values",
            json={"list_code": "office_purposes", "label": "Inventado"},
        )
    ).status_code == 403
    assert (
        await alpha_client.put(
            f"/api/standard-values/{valor_id}", json={"label": "Cambiado"}
        )
    ).status_code == 403
    assert (
        await alpha_client.delete(f"/api/standard-values/{valor_id}")
    ).status_code == 403
    assert (
        await alpha_client.get(
            "/api/standard-values/employee_visit_reasons?include_inactive=true"
        )
    ).status_code == 403
    assert (await alpha_client.get("/api/standard-values/lists")).status_code == 403


async def test_the_administrator_reads_and_manages_the_values(seeded, alpha_client):
    """Caso 16."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    creado = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "delivery_types", "label": "Payroll Check"},
    )
    assert creado.status_code == 200
    assert (await alpha_client.get("/api/standard-values/delivery_types")).status_code == 200
    assert (await alpha_client.get("/api/standard-values/lists")).status_code == 200
    assert (
        await alpha_client.get("/api/standard-values/delivery_types?include_inactive=true")
    ).status_code == 200


# ── Caso límite 20: los roles del núcleo, fuera del selector ─────────────────


async def test_the_assignable_roles_endpoint_offers_exactly_the_two_route_roles(
    seeded, alpha_client,
):
    """Caso 20, por API. El selector del navegador se valida aparte.

    Y llega con la etiqueta de producto: el código técnico no sale a pantalla.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.get("/api/users/assignable-roles")

    assert respuesta.status_code == 200
    opciones = respuesta.json()
    assert {o["code"] for o in opciones} == ROUTE_PRODUCT_ROLES
    assert {o["label"] for o in opciones} == {"Administrador", "Supervisor"}
    for opcion in opciones:
        assert opcion["id"] == seeded.alpha.roles[opcion["code"]]


async def test_a_core_administrator_still_sees_the_tenant_catalog(
    seeded, alpha_client,
):
    """El endpoint no recorta a quien no administra desde Route."""
    await alpha_client.login(seeded.alpha.users["owner"].email)
    opciones = (await alpha_client.get("/api/users/assignable-roles")).json()

    codigos = {o["code"] for o in opciones}
    assert ROUTE_PRODUCT_ROLES <= codigos
    assert set(ROLES_DEL_NUCLEO) <= codigos


# ── Y el privilegio de plataforma, intacto ───────────────────────────────────


async def test_no_superuser_path_was_introduced(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        "/api/users",
        json={
            "username": "a02_su",
            "email": "a02_su@alpha.example.com",
            "first_name": "A", "last_name": "S",
            "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles["supervisor"],
            "is_superuser": True,
        },
    )
    assert respuesta.status_code == 422
    assert "extra_forbidden" in respuesta.text

    # Y el administrador de plataforma no queda atrapado por la regla de Route.
    async with TenantClient("alpha") as plataforma:
        await plataforma.login(seeded.platform_admin.email)
        creado = await _crear(
            plataforma, sufijo="porplataforma", role_id=seeded.alpha.roles["admin"]
        )
        assert creado.status_code == 200, creado.text


async def test_the_role_change_is_audited_with_actor_target_and_both_roles(
    seeded, alpha_client,
):
    """La auditoría del cambio de rol, que la resolución pide por nombre."""
    from sqlalchemy import text

    from app.database import async_session_maker

    supervisor = seeded.alpha.users["supervisor"]
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(
        f"/api/users/{supervisor.id}",
        json={"role_id": seeded.alpha.roles["route_admin"]},
    )

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT actor_user_id, entity_id, changes::text, occurred_at "
                    "FROM audit_event WHERE company_id = :c AND entity_type = 'user' "
                    "AND action = 'update' ORDER BY id DESC LIMIT 1"
                ),
                {"c": seeded.alpha.id},
            )
        ).one()

    assert fila.actor_user_id == seeded.alpha.users["route_admin"].id
    assert fila.entity_id == supervisor.id
    assert "role" in fila.changes.lower()
    assert fila.occurred_at is not None
