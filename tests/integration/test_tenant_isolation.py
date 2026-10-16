"""
Aislamiento entre compañías.

Es el test que la plataforma no tenía y que hacía invisibles cuatro hallazgos de
severidad alta: con **una sola compañía**, un endpoint que devuelve "todos los
roles" y uno que devuelve "los roles de mi compañía" producen exactamente el
mismo resultado. Solo con dos tenants se distinguen.

Lo que se comprueba:

* los roles no cruzan tenants (AUD-SEC-006);
* las pertenencias no cruzan tenants;
* las solicitudes de cambio de capacidades no cruzan tenants (AUD-SEC-007);
* los endpoints de compañía no exponen otro tenant (AUD-SEC-005);
* un cambio de permisos en A no altera nada de B.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.routers_api.roles.models import Role
from tests.integration.conftest import TEST_PASSWORD


pytestmark = pytest.mark.integration


async def test_roles_listing_only_returns_roles_of_the_current_company(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/api/roles")
    assert response.status_code == 200

    returned_ids = {row["id"] for row in response.json()}
    assert returned_ids == set(seeded.alpha.roles.values())
    assert not returned_ids & set(seeded.beta.roles.values()), (
        "El listado de roles de alpha incluye roles de beta."
    )


async def test_a_role_of_another_company_is_not_found(seeded, alpha_client):
    """404 y no 403: no se confirma siquiera que el rol exista."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    beta_role = seeded.beta.roles["viewer"]
    response = await alpha_client.get(f"/api/roles/{beta_role}/permissions")

    assert response.status_code == 404


async def test_cannot_edit_a_role_of_another_company(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    beta_role = seeded.beta.roles["viewer"]
    response = await alpha_client.put(
        f"/api/roles/{beta_role}",
        json={"description": "touched from alpha"},
    )

    assert response.status_code == 404

    async with async_session_maker() as session:
        description = await session.scalar(
            select(Role.description).where(Role.id == beta_role)
        )
    assert description != "touched from alpha"


async def test_cannot_delete_a_role_of_another_company(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    beta_role = seeded.beta.roles["manager"]
    response = await alpha_client.delete(f"/api/roles/{beta_role}")

    assert response.status_code == 404

    async with async_session_maker() as session:
        is_active = await session.scalar(
            select(Role.is_active).where(Role.id == beta_role)
        )
    assert is_active is True


async def test_role_names_can_repeat_across_companies(seeded):
    """`owner` existe en las dos compañías: la unicidad es (company_id, name)."""
    async with async_session_maker() as session:
        rows = (
            await session.execute(select(Role).where(Role.name == "owner"))
        ).scalars().all()

    companies = {role.company_id for role in rows}
    assert companies == {seeded.alpha.id, seeded.beta.id}


async def test_user_listing_only_returns_members_of_the_current_company(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/api/users/pagination?page_size=100")
    assert response.status_code == 200

    emails = {row["email"] for row in response.json()["results"]}
    beta_emails = {user.email for user in seeded.beta.users.values()}

    assert not emails & beta_emails, "El listado de alpha incluye usuarios de beta."


async def test_cannot_edit_a_user_of_another_company(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.put(
        f"/api/users/{seeded.beta.users['viewer'].id}",
        json={"first_name": "Touched"},
    )
    assert response.status_code == 404


async def test_cannot_assign_a_role_from_another_company(seeded, alpha_client):
    """La FK compuesta lo impide en la base; la API debe contestar 404, no 500."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.put(
        f"/api/users/{seeded.alpha.users['viewer'].id}",
        json={"role_id": seeded.beta.roles["owner"]},
    )
    assert response.status_code == 404


async def test_change_requests_do_not_cross_companies(seeded, tenant_client):
    """Un revisor de A no ve ni resuelve las solicitudes de B (AUD-SEC-007)."""
    # En beta, el `admin` pide un cambio de capacidades.
    async with tenant_client("beta") as beta:
        await beta.login(seeded.beta.users["admin"].email)
        submitted = await beta.put(
            f"/api/roles/{seeded.beta.roles['viewer']}/permissions",
            json={"permission_ids": []},
        )
        assert submitted.status_code == 200

        listing = await beta.get("/api/rolepermissionsapprovals/pagination")
        beta_requests = listing.json()["results"]
        assert len(beta_requests) == 1
        beta_request_id = beta_requests[0]["id"]

    # Desde alpha no debe verse ni poder resolverse.
    async with tenant_client("alpha") as alpha:
        await alpha.login(seeded.alpha.users["owner"].email)

        listing = await alpha.get("/api/rolepermissionsapprovals/pagination")
        assert listing.status_code == 200
        assert listing.json()["results"] == [], (
            "El listado de alpha muestra solicitudes de beta."
        )

        approve = await alpha.post(
            f"/api/rolepermissionsapprovals/{beta_request_id}/approve"
        )
        assert approve.status_code == 404, (
            "Un revisor de alpha ha podido resolver por id una solicitud de beta."
        )


async def test_approving_in_one_company_does_not_touch_the_other(
    seeded, tenant_client,
):
    """El rol `viewer` de beta se queda sin capacidades; el de alpha no cambia."""
    from app.core.rbac.catalog import CAPABILITY_NAMES

    async def capabilities_of(role_id: int) -> set[str]:
        from app.routers_api.permissions.models import Permission
        from app.routers_api.rolepermissions.models import RolePermission

        async with async_session_maker() as session:
            rows = await session.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(
                    RolePermission.role_id == role_id,
                    RolePermission.is_active.is_(True),
                )
            )
            return set(rows.scalars().all())

    alpha_before = await capabilities_of(seeded.alpha.roles["viewer"])
    assert alpha_before  # tiene algo que perder

    async with tenant_client("beta") as beta:
        await beta.login(seeded.beta.users["admin"].email)
        await beta.put(
            f"/api/roles/{seeded.beta.roles['viewer']}/permissions",
            json={"permission_ids": []},
        )
        request_id = (
            await beta.get("/api/rolepermissionsapprovals/pagination")
        ).json()["results"][0]["id"]

        # `owner` de beta aprueba: es otro usuario y su rol es de gestión.
        await beta.login(seeded.beta.users["owner"].email)
        approved = await beta.post(f"/api/rolepermissionsapprovals/{request_id}/approve")
        assert approved.status_code == 200

    assert await capabilities_of(seeded.beta.roles["viewer"]) == set()
    assert await capabilities_of(seeded.alpha.roles["viewer"]) == alpha_before, (
        "Aprobar un cambio en beta ha alterado las capacidades de alpha."
    )
    assert alpha_before <= CAPABILITY_NAMES


async def test_operating_states_do_not_leak_between_companies(
    seeded, tenant_client,
):
    async with tenant_client("alpha") as alpha:
        await alpha.login(seeded.alpha.users["owner"].email)
        await alpha.put(
            "/api/regions/operating",
            json={"state_ids": [seeded.regions["GA"]]},
        )

    async with tenant_client("beta") as beta:
        await beta.login(seeded.beta.users["owner"].email)
        response = await beta.get("/api/regions/operating")

    assert response.status_code == 200
    assert response.json() == [], (
        "Beta ve los estados de operación que configuró alpha."
    )


async def test_an_unknown_subdomain_is_not_served(seeded, tenant_client):
    async with tenant_client("does-not-exist") as client:
        response = await client.get("/api/public/auth/login")

    assert response.status_code == 404
