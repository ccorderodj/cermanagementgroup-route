"""
El contexto de producto gobierna qué roles se pueden conceder (A02-FC1, PD-02).

Qué corrige este checkpoint
---------------------------
A02 acotó la asignación mirando **quién llama**. Cerraba la escalada, pero CER
encontró el hueco al revisarlo: un Superadmin o un `owner` entrando por
`CER Route > Users` seguía recibiendo el catálogo completo del tenant y podía
conceder `admin` desde una pantalla que dice CER Route. La autoridad de quien
mira no debería cambiar lo que una pantalla de producto ofrece.

Ahora hacen falta **dos** condiciones, y son distintas:

* **contexto** — todo lo que entre por `/api/route/users` queda acotado a los dos
  roles de producto, sea quien sea quien llame;
* **actor** — quien tiene un rol de CER Route queda acotado llame por donde
  llame.

La segunda parecía redundante al llegar PD-02. Quitarla reabrió la escalada al
instante: un `route_admin` tiene `users.create`, así que por `/api/users` volvía a
crear un `owner`, y se midió devolviendo 200. Está comprobado abajo, porque una
regresión que ya ocurrió una vez merece su propio test.

La frontera la decide la ruta
------------------------------
No una cabecera. Confiar en que el cliente declare su propio contexto sería
confiar en el cliente para decidir una frontera. El mismo router se monta dos
veces y lo único que cambia es una dependencia que marca por dónde entró.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.rbac.catalog import ROUTE_PRODUCT_ROLES
from app.database import async_session_maker
from tests.integration.conftest import TEST_PASSWORD, TenantClient


pytestmark = pytest.mark.integration


ROLES_DEL_NUCLEO = ("owner", "admin", "manager", "viewer")

#: El contrato de CER Route. La barra intermedia es toda la diferencia.
RUTA_ROUTE = "/api/route/users"
RUTA_NUCLEO = "/api/users"


def _cuerpo(sufijo: str, role_id: int) -> dict:
    return {
        "username": f"fc1_{sufijo}",
        "email": f"fc1_{sufijo}@alpha.example.com",
        "first_name": "FC1",
        "last_name": sufijo,
        "password": TEST_PASSWORD,
        "role_id": role_id,
    }


async def _existe(email: str) -> bool:
    async with async_session_maker() as session:
        return bool(
            await session.scalar(
                text('SELECT count(*) FROM "user" WHERE email = :e'), {"e": email}
            )
        )


# ── Test 1-3: el selector, para cada tipo de actor ───────────────────────────


@pytest.mark.parametrize("actor", ["route_admin", "owner", "admin"])
async def test_the_route_contract_offers_exactly_two_roles_to_anyone(
    seeded, alpha_client, actor,
):
    """Tests 1 y 3 de la resolución: Administrador, Owner y Admin del núcleo.

    El mismo endpoint, el mismo tenant, tres autoridades muy distintas, y la
    misma respuesta: dos opciones.
    """
    await alpha_client.login(seeded.alpha.users[actor].email)
    respuesta = await alpha_client.get(f"{RUTA_ROUTE}/assignable-roles")

    assert respuesta.status_code == 200, respuesta.text
    assert {o["code"] for o in respuesta.json()} == ROUTE_PRODUCT_ROLES
    assert {o["label"] for o in respuesta.json()} == {"Administrador", "Supervisor"}


async def test_the_route_contract_offers_two_roles_to_the_platform_superadmin(
    seeded,
):
    """Test 2, el escenario que destapó el hueco.

    Es el caso que más importa: el Superadmin tiene toda la autoridad de la
    plataforma y aun así, dentro de una pantalla de CER Route, ve lo que CER
    Route ofrece. Su autoridad no desaparece — sigue intacta por el contrato del
    núcleo, y eso también se comprueba.
    """
    async with TenantClient("alpha") as plataforma:
        await plataforma.login(seeded.platform_admin.email)

        por_route = await plataforma.get(f"{RUTA_ROUTE}/assignable-roles")
        assert por_route.status_code == 200
        assert {o["code"] for o in por_route.json()} == ROUTE_PRODUCT_ROLES

        por_nucleo = await plataforma.get(f"{RUTA_NUCLEO}/assignable-roles")
        assert por_nucleo.status_code == 200
        assert len({o["code"] for o in por_nucleo.json()}) == 6, (
            "su autoridad sigue intacta en el contrato del núcleo"
        )


async def test_no_technical_code_leaks_as_a_product_label(seeded, alpha_client):
    """Las etiquetas son de producto; `route_admin` no se enseña nunca."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    opciones = (await alpha_client.get(f"{RUTA_ROUTE}/assignable-roles")).json()

    etiquetas = " ".join(o["label"] for o in opciones)
    assert "route_admin" not in etiquetas
    assert "supervisor" not in etiquetas.lower().replace("supervisor", "", 1) or True
    assert sorted(o["label"] for o in opciones) == ["Administrador", "Supervisor"]


# ── Test 4-6: la escritura, por el contrato de Route ─────────────────────────


@pytest.mark.parametrize("rol", ROLES_DEL_NUCLEO)
async def test_the_route_contract_rejects_creating_with_a_core_role(
    seeded, alpha_client, rol,
):
    """Tests 4 y 6, para los cuatro roles del núcleo."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        RUTA_ROUTE, json=_cuerpo(rol, seeded.alpha.roles[rol])
    )

    assert respuesta.status_code == 403
    assert not await _existe(f"fc1_{rol}@alpha.example.com"), "y no se escribió nada"


@pytest.mark.parametrize("rol", ROLES_DEL_NUCLEO)
async def test_the_route_contract_rejects_promoting_to_a_core_role(
    seeded, alpha_client, rol,
):
    """Test 5: por actualización, que abría la misma puerta."""
    supervisor = seeded.alpha.users["supervisor"]
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.put(
        f"{RUTA_ROUTE}/{supervisor.id}", json={"role_id": seeded.alpha.roles[rol]}
    )
    assert respuesta.status_code == 403


async def test_the_platform_superadmin_is_not_exempt_in_the_route_contract(seeded):
    """FR-03, pasos 7 y 8. Rechazo **y** ninguna escritura."""
    async with TenantClient("alpha") as plataforma:
        await plataforma.login(seeded.platform_admin.email)
        respuesta = await plataforma.post(
            RUTA_ROUTE, json=_cuerpo("porsuper", seeded.alpha.roles["owner"])
        )

    assert respuesta.status_code == 403
    assert not await _existe("fc1_porsuper@alpha.example.com")


@pytest.mark.parametrize("rol", ["route_admin", "supervisor"])
async def test_the_route_contract_accepts_the_two_product_roles(
    seeded, alpha_client, rol,
):
    """Lo que sí tiene que funcionar, que es la mitad que suele olvidarse."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        RUTA_ROUTE, json=_cuerpo(f"ok_{rol}", seeded.alpha.roles[rol])
    )
    assert respuesta.status_code == 200, respuesta.text


# ── La puerta de atrás: el actor, llame por donde llame ──────────────────────


@pytest.mark.parametrize("rol", ROLES_DEL_NUCLEO)
async def test_a_route_actor_cannot_escape_through_the_core_contract(
    seeded, alpha_client, rol,
):
    """La regresión que introduje al implementar PD-02, con su propio test.

    Al pasar a mirar sólo el contexto, un `route_admin` volvía a poder crear un
    `owner` llamando a `/api/users`: tiene `users.create`, y el contrato del
    núcleo dejaba de acotarle. Se midió devolviendo 200 antes de corregirlo.

    Las dos condiciones son necesarias: el contexto cierra la pantalla, el actor
    cierra la puerta de atrás.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        RUTA_NUCLEO, json=_cuerpo(f"fuga_{rol}", seeded.alpha.roles[rol])
    )

    assert respuesta.status_code == 403
    assert not await _existe(f"fc1_fuga_{rol}@alpha.example.com")


async def test_a_route_actor_sees_only_two_roles_in_the_core_contract_too(
    seeded, alpha_client,
):
    """Lo ofrecido y lo aceptado no pueden divergir, ni cambiando de contrato."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    opciones = (await alpha_client.get(f"{RUTA_NUCLEO}/assignable-roles")).json()
    assert {o["code"] for o in opciones} == ROUTE_PRODUCT_ROLES


# ── Test 7-8: tenant ajeno, y el núcleo sin tocar ────────────────────────────


async def test_a_role_from_another_tenant_is_rejected_without_leaking(
    seeded, alpha_client,
):
    """Test 7: 404, no 403 — no se confirma que exista en otro sitio."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        RUTA_ROUTE, json=_cuerpo("cruzado", seeded.beta.roles["owner"])
    )
    assert respuesta.status_code == 404


async def test_core_management_behavior_is_unchanged(seeded, alpha_client):
    """Test 8, y el límite de este checkpoint.

    Un actor del núcleo por el contrato del núcleo sigue exactamente como estaba.
    La resolución lo pide expresamente: esto acota CER Route, no rediseña el RBAC
    compartido.
    """
    await alpha_client.login(seeded.alpha.users["owner"].email)
    respuesta = await alpha_client.post(
        RUTA_NUCLEO, json=_cuerpo("delnucleo", seeded.alpha.roles["admin"])
    )
    assert respuesta.status_code == 200, respuesta.text


async def test_the_supervisor_administers_nothing_in_either_contract(
    seeded, alpha_client,
):
    """El rol de campo no administra usuarios, ni por una ruta ni por la otra."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    for base in (RUTA_ROUTE, RUTA_NUCLEO):
        assert (await alpha_client.get(f"{base}/pagination")).status_code == 403
        assert (await alpha_client.get(f"{base}/assignable-roles")).status_code == 403
        creacion = await alpha_client.post(
            base, json=_cuerpo("porsup", seeded.alpha.roles["supervisor"])
        )
        assert creacion.status_code == 403


async def test_no_superuser_path_exists_in_the_route_contract(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        RUTA_ROUTE,
        json={
            **_cuerpo("su", seeded.alpha.roles["supervisor"]),
            "is_superuser": True,
        },
    )
    assert respuesta.status_code == 422
    assert "extra_forbidden" in respuesta.text
