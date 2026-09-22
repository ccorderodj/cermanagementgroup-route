"""
Contrato de paginación y atomicidad de las operaciones multi-tabla.

Paginación
----------
El frontend cuenta páginas desde 0 y el backend desde 1. La traducción vive
ahora en un solo sitio, pero lo que importa es el contrato de la respuesta:
`count`, `next`, `previous`, `results` — y **no** `page_size`, que el tipo de
TypeScript declaraba obligatorio y el backend nunca ha enviado (AUD-FE-010).

Transacciones
-------------
Cada DAO abría su propia sesión y hacía su propio commit, así que una operación
que tocaba dos tablas podía quedarse a medias: crear el usuario y fallar al
vincularlo dejaba una identidad huérfana (AUD-BE-015).
"""

import pytest
from sqlalchemy import func, select

from app.database import async_session_maker
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.models import Users
from tests.integration.conftest import TEST_PASSWORD


pytestmark = pytest.mark.integration


# ── Contrato de paginación ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/users/pagination",
        "/api/roles/pagination",
        "/api/permissions/pagination",
        "/api/rolepermissions/pagination",
        "/api/rolepermissionsapprovals/pagination",
        "/api/regions/pagination",
    ],
)
async def test_paginated_endpoints_share_the_same_envelope(seeded, alpha_client, path):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get(path)
    assert response.status_code == 200

    payload = response.json()
    assert set(payload) == {"count", "next", "previous", "results"}, (
        f"{path} devuelve un envoltorio distinto: {sorted(payload)}"
    )
    assert isinstance(payload["count"], int)
    assert isinstance(payload["results"], list)


@pytest.mark.parametrize(
    "path",
    ["/api/users/pagination", "/api/roles/pagination", "/api/permissions/pagination"],
)
async def test_the_envelope_does_not_include_page_size(seeded, alpha_client, path):
    """El frontend declaraba `page_size` obligatorio; el backend no lo envía."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    payload = (await alpha_client.get(path)).json()
    assert "page_size" not in payload


async def test_pages_are_one_based_and_do_not_overlap(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    first = (await alpha_client.get("/api/roles/pagination?page=1&page_size=2")).json()
    second = (await alpha_client.get("/api/roles/pagination?page=2&page_size=2")).json()

    assert len(first["results"]) == 2
    assert first["count"] == second["count"] == len(seeded.alpha.roles)

    first_ids = {row["id"] for row in first["results"]}
    second_ids = {row["id"] for row in second["results"]}
    assert not first_ids & second_ids, "Dos páginas consecutivas repiten filas."


async def test_page_zero_is_rejected(seeded, alpha_client):
    """El backend es base 1: `page=0` es un error del cliente, no la primera página."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/api/roles/pagination?page=0")
    assert response.status_code == 422


async def test_the_page_size_is_capped(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/api/roles/pagination?page_size=5000")
    assert response.status_code == 422


async def test_count_matches_the_filter(seeded, alpha_client):
    """El conteo y las filas salen de la misma consulta: no pueden divergir."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    payload = (
        await alpha_client.get("/api/roles/pagination?name=owner&page_size=50")
    ).json()

    assert payload["count"] == len(payload["results"]) == 1
    assert payload["results"][0]["name"] == "owner"


async def test_next_and_previous_reflect_the_position(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    first = (await alpha_client.get("/api/roles/pagination?page=1&page_size=2")).json()
    assert first["previous"] is None
    assert first["next"] is not None

    last = (await alpha_client.get("/api/roles/pagination?page=2&page_size=2")).json()
    assert last["previous"] is not None
    assert last["next"] is None


# ── Atomicidad ──────────────────────────────────────────────────────────────


async def test_creating_a_user_and_its_membership_is_atomic(seeded, alpha_client):
    """Un rol inválido no debe dejar el usuario ya creado.

    Antes eran dos operaciones con su propio commit: la primera quedaba escrita
    aunque la segunda fallara.
    """
    await alpha_client.login(seeded.alpha.users["owner"].email)

    async with async_session_maker() as session:
        before = await session.scalar(select(func.count(Users.id)))

    response = await alpha_client.post(
        "/api/users",
        json={
            "username": "orphan_candidate",
            "email": "orphan@alpha.example.com",
            "first_name": "Orphan",
            "last_name": "Candidate",
            "password": TEST_PASSWORD,
            # Rol de la otra compañía: la operación tiene que abortar entera.
            "role_id": seeded.beta.roles["viewer"],
        },
    )
    assert response.status_code == 404

    async with async_session_maker() as session:
        after = await session.scalar(select(func.count(Users.id)))
        orphan = await session.scalar(
            select(Users).where(Users.username == "orphan_candidate")
        )

    assert after == before, "Se creó un usuario pese a fallar la operación."
    assert orphan is None


async def test_updating_a_user_and_its_role_is_atomic(seeded, alpha_client):
    """Si el rol no vale, tampoco deben escribirse los datos del usuario."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    target = seeded.alpha.users["viewer"]

    response = await alpha_client.put(
        f"/api/users/{target.id}",
        json={"first_name": "ShouldNotPersist", "role_id": seeded.beta.roles["owner"]},
    )
    assert response.status_code == 404

    async with async_session_maker() as session:
        first_name = await session.scalar(
            select(Users.first_name).where(Users.id == target.id)
        )
    assert first_name != "ShouldNotPersist", (
        "Los datos se escribieron aunque la asignación de rol falló."
    )


async def test_a_successful_creation_leaves_both_rows(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.post(
        "/api/users",
        json={
            "username": "well_formed",
            "email": "well.formed@alpha.example.com",
            "first_name": "Well",
            "last_name": "Formed",
            "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles["manager"],
        },
    )
    assert response.status_code == 200

    created_id = response.json()["id"]

    async with async_session_maker() as session:
        membership = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == created_id,
                UserCompany.company_id == seeded.alpha.id,
            )
        )

    assert membership is not None
    assert membership.role_id == seeded.alpha.roles["manager"]
    assert membership.is_active is True


async def test_suspending_a_membership_does_not_disable_the_identity(
    seeded, alpha_client,
):
    """Los dos niveles son distintos y deben seguir siéndolo (D7)."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    target = seeded.alpha.users["manager"]

    response = await alpha_client.put(
        f"/api/users/{target.id}/access",
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert response.json()["is_platform_active"] is True

    async with async_session_maker() as session:
        platform_active = await session.scalar(
            select(Users.is_active).where(Users.id == target.id)
        )
        membership_active = await session.scalar(
            select(UserCompany.is_active).where(
                UserCompany.user_id == target.id,
                UserCompany.company_id == seeded.alpha.id,
            )
        )

    assert platform_active is True, (
        "Suspender en un tenant no debe desactivar la identidad de plataforma."
    )
    assert membership_active is False


async def test_a_suspended_member_cannot_log_in_again(seeded, alpha_client, tenant_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    target = seeded.alpha.users["manager"]

    await alpha_client.put(f"/api/users/{target.id}/access", json={"is_active": False})

    async with tenant_client("alpha") as suspended:
        response = await suspended.login(target.email)

    assert response.status_code == 401, (
        "Suspender el acceso tiene que impedir el siguiente inicio de sesión."
    )
