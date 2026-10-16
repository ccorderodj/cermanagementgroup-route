"""
Maker-checker de los cambios de capacidades.

Las cuatro reglas del control, cada una con su test:

    1. enviar un cambio NO lo aplica
    2. quien lo pide no puede aprobarlo
    3. solo un rol de categoría `management` puede revisar
    4. un rol tiene como mucho una solicitud pendiente

La cuarta pasó de comprobarse con un SELECT seguido de un INSERT —que dos
peticiones simultáneas esquivaban— a un índice único parcial en la base
(AUD-BE-029).
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission


pytestmark = pytest.mark.integration


async def capabilities_of(role_id: int) -> set[str]:
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


async def test_submitting_does_not_apply_the_change(seeded, alpha_client):
    """Regla 1. Antes, revocar borraba la fila al instante y solo conceder
    pasaba por revisión: el control protegía justo lo contrario de lo que debía.
    """
    role_id = seeded.alpha.roles["viewer"]
    before = await capabilities_of(role_id)
    assert before

    await alpha_client.login(seeded.alpha.users["admin"].email)
    response = await alpha_client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": []},
    )

    assert response.status_code == 200
    assert await capabilities_of(role_id) == before, (
        "Enviar la solicitud ha aplicado el cambio sin que nadie lo revisara."
    )
    assert response.json()["pending_request"] is not None


async def test_the_pending_request_shows_what_it_would_change(seeded, alpha_client):
    role_id = seeded.alpha.roles["viewer"]

    await alpha_client.login(seeded.alpha.users["admin"].email)
    response = await alpha_client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": []},
    )

    pending = response.json()["pending_request"]
    assert set(pending["to_revoke"]) == await capabilities_of(role_id)
    assert pending["to_grant"] == []


async def test_the_requester_cannot_approve_their_own_request(seeded, alpha_client):
    """Regla 2: segregación de deberes."""
    role_id = seeded.alpha.roles["viewer"]

    await alpha_client.login(seeded.alpha.users["admin"].email)
    await alpha_client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": []},
    )

    request_id = (
        await alpha_client.get("/api/rolepermissionsapprovals/pagination")
    ).json()["results"][0]["id"]

    response = await alpha_client.post(
        f"/api/rolepermissionsapprovals/{request_id}/approve"
    )
    assert response.status_code == 409


async def test_an_operative_role_cannot_review(seeded, tenant_client):
    """Regla 3. `manager` es operativo a propósito: opera, no administra seguridad."""
    role_id = seeded.alpha.roles["viewer"]

    async with tenant_client("alpha") as admin:
        await admin.login(seeded.alpha.users["admin"].email)
        await admin.put(
            f"/api/roles/{role_id}/permissions",
            json={"permission_ids": []},
        )
        request_id = (
            await admin.get("/api/rolepermissionsapprovals/pagination")
        ).json()["results"][0]["id"]

    async with tenant_client("alpha") as manager:
        await manager.login(seeded.alpha.users["manager"].email)
        response = await manager.post(
            f"/api/rolepermissionsapprovals/{request_id}/approve"
        )

    # `manager` no tiene `rolepermissions.update`, así que ni llega a la
    # comprobación de autoridad.
    assert response.status_code == 403


async def test_a_second_pending_request_for_the_same_role_is_rejected(
    seeded, alpha_client,
):
    """Regla 4, ahora impuesta por un índice único parcial."""
    role_id = seeded.alpha.roles["viewer"]
    catalog = await capabilities_of(seeded.alpha.roles["owner"])

    async with async_session_maker() as session:
        first_id = await session.scalar(
            select(Permission.id).where(Permission.name == sorted(catalog)[0])
        )

    await alpha_client.login(seeded.alpha.users["admin"].email)

    first = await alpha_client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": []},
    )
    assert first.status_code == 200

    second = await alpha_client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": [first_id]},
    )
    assert second.status_code == 409


async def test_approval_applies_exactly_the_requested_set(seeded, tenant_client):
    role_id = seeded.alpha.roles["viewer"]

    async with async_session_maker() as session:
        wanted = list(
            (
                await session.execute(
                    select(Permission.id)
                    .where(Permission.name.in_(["roles.read", "permissions.read"]))
                    .order_by(Permission.name)
                )
            ).scalars().all()
        )

    async with tenant_client("alpha") as admin:
        await admin.login(seeded.alpha.users["admin"].email)
        await admin.put(
            f"/api/roles/{role_id}/permissions",
            json={"permission_ids": wanted},
        )
        request_id = (
            await admin.get("/api/rolepermissionsapprovals/pagination")
        ).json()["results"][0]["id"]

    async with tenant_client("alpha") as owner:
        await owner.login(seeded.alpha.users["owner"].email)
        approved = await owner.post(
            f"/api/rolepermissionsapprovals/{request_id}/approve"
        )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert await capabilities_of(role_id) == {"roles.read", "permissions.read"}


async def test_rejection_leaves_everything_untouched(seeded, tenant_client):
    role_id = seeded.alpha.roles["viewer"]
    before = await capabilities_of(role_id)

    async with tenant_client("alpha") as admin:
        await admin.login(seeded.alpha.users["admin"].email)
        await admin.put(
            f"/api/roles/{role_id}/permissions",
            json={"permission_ids": []},
        )
        request_id = (
            await admin.get("/api/rolepermissionsapprovals/pagination")
        ).json()["results"][0]["id"]

    async with tenant_client("alpha") as owner:
        await owner.login(seeded.alpha.users["owner"].email)
        rejected = await owner.post(
            f"/api/rolepermissionsapprovals/{request_id}/reject",
            json={"review_note": "Not this time"},
        )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_note"] == "Not this time"
    assert await capabilities_of(role_id) == before


async def test_a_resolved_request_cannot_be_resolved_again(seeded, tenant_client):
    role_id = seeded.alpha.roles["viewer"]

    async with tenant_client("alpha") as admin:
        await admin.login(seeded.alpha.users["admin"].email)
        await admin.put(
            f"/api/roles/{role_id}/permissions",
            json={"permission_ids": []},
        )
        request_id = (
            await admin.get("/api/rolepermissionsapprovals/pagination")
        ).json()["results"][0]["id"]

    async with tenant_client("alpha") as owner:
        await owner.login(seeded.alpha.users["owner"].email)
        await owner.post(f"/api/rolepermissionsapprovals/{request_id}/approve")
        again = await owner.post(f"/api/rolepermissionsapprovals/{request_id}/approve")

    assert again.status_code == 409


async def test_submitting_the_current_set_is_not_a_change(seeded, alpha_client):
    """Pedir exactamente lo que ya hay no debe crear una solicitud vacía."""
    role_id = seeded.alpha.roles["viewer"]

    async with async_session_maker() as session:
        current = list(
            (
                await session.execute(
                    select(RolePermission.permission_id).where(
                        RolePermission.role_id == role_id,
                        RolePermission.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )

    await alpha_client.login(seeded.alpha.users["admin"].email)
    response = await alpha_client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": current},
    )

    assert response.status_code == 400
