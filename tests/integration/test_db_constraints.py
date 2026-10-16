"""
Restricciones de integridad, comprobadas contra PostgreSQL.

No se comprueba que el código valide: se comprueba que **la base rechace**.
La diferencia importa. Una comprobación en Python protege mientras nadie se
olvide de llamarla; una restricción de la base protege siempre, incluida la
migración que alguien escriba dentro de dos años y el script que se ejecute a
mano un viernes.

Cada test corresponde a un hallazgo concreto de la auditoría.
"""

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError

from app.database import async_session_maker
from app.routers_api.companies.models import CompanyState, UserCompany
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.rolepermissionsapprovals.models import RolePermissionChangeRequest
from app.routers_api.roles.models import Role
from app.routers_api.users.models import Users


pytestmark = pytest.mark.integration


async def test_a_user_cannot_have_two_memberships_in_the_same_company(seeded):
    """AUD-DB-002.

    Sin esta restricción, la consulta de login devolvía múltiples filas y
    respondía 500. La comprobación estaba solo en un mensaje de error amistoso
    que esperaba una constraint que no existía.
    """
    user_id = seeded.alpha.users["viewer"].id

    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(UserCompany).values(
                    user_id=user_id,
                    company_id=seeded.alpha.id,
                    role_id=seeded.alpha.roles["owner"],
                    is_active=True,
                )
            )
            await session.commit()


async def test_a_membership_cannot_use_a_role_of_another_company(seeded):
    """La clave foránea compuesta `(role_id, company_id) -> role(id, company_id)`.

    Es la invariante central del RBAC multi-tenant: sin ella, asignar el rol de
    otra compañía era un `UPDATE` cualquiera.
    """
    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                update(UserCompany)
                .where(
                    UserCompany.user_id == seeded.alpha.users["viewer"].id,
                    UserCompany.company_id == seeded.alpha.id,
                )
                .values(role_id=seeded.beta.roles["owner"])
            )
            await session.commit()


async def test_role_names_are_unique_per_company(seeded):
    """AUD-DB-004, ahora acotado al tenant."""
    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(Role).values(
                    company_id=seeded.alpha.id,
                    name="owner",
                    description="duplicate",
                    category="operative",
                )
            )
            await session.commit()


async def test_role_category_only_accepts_the_two_valid_values(seeded):
    """AUD-DB-007.

    Era `String(20)` sin restricción: una categoría inválida dejaba al rol sin
    autoridad de revisión sin que nada lo indicara.
    """
    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(Role).values(
                    company_id=seeded.alpha.id,
                    name="broken",
                    category="whatever",
                )
            )
            await session.commit()


async def test_a_company_cannot_repeat_a_state(seeded):
    """AUD-DB-008, primera mitad."""
    async with async_session_maker() as session:
        await session.execute(
            insert(CompanyState).values(
                company_id=seeded.alpha.id,
                state_id=seeded.regions["GA"],
                is_active=True,
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(CompanyState).values(
                    company_id=seeded.alpha.id,
                    state_id=seeded.regions["GA"],
                    is_active=True,
                )
            )
            await session.commit()


async def test_a_company_cannot_have_two_active_main_states(seeded):
    """AUD-DB-008, segunda mitad: índice único parcial.

    Antes, dos peticiones concurrentes a `set_main_state` podían dejar dos sedes
    principales, y nada en la base lo impedía.
    """
    async with async_session_maker() as session:
        await session.execute(
            insert(CompanyState).values(
                company_id=seeded.alpha.id,
                state_id=seeded.regions["GA"],
                is_active=True,
                is_main=True,
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(CompanyState).values(
                    company_id=seeded.alpha.id,
                    state_id=seeded.regions["TX"],
                    is_active=True,
                    is_main=True,
                )
            )
            await session.commit()


async def test_two_companies_can_each_have_their_own_main_state(seeded):
    """El índice es parcial POR compañía: no debe estorbar entre tenants."""
    async with async_session_maker() as session:
        await session.execute(
            insert(CompanyState).values(
                company_id=seeded.alpha.id,
                state_id=seeded.regions["GA"],
                is_active=True,
                is_main=True,
            )
        )
        await session.execute(
            insert(CompanyState).values(
                company_id=seeded.beta.id,
                state_id=seeded.regions["TX"],
                is_active=True,
                is_main=True,
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        count = await session.scalar(
            select(text("count(*)")).select_from(CompanyState.__table__)
        )
    assert count == 2


async def test_a_role_cannot_have_two_pending_requests(seeded):
    """AUD-BE-029: la carrera que el SELECT-luego-INSERT no cerraba."""
    async with async_session_maker() as session:
        await session.execute(
            insert(RolePermissionChangeRequest).values(
                role_id=seeded.alpha.roles["viewer"],
                company_id=seeded.alpha.id,
                requested_by_user_id=seeded.alpha.users["admin"].id,
                requested_permission_ids=[],
                status="pending",
                is_active=True,
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(RolePermissionChangeRequest).values(
                    role_id=seeded.alpha.roles["viewer"],
                    company_id=seeded.alpha.id,
                    requested_by_user_id=seeded.alpha.users["owner"].id,
                    requested_permission_ids=[],
                    status="pending",
                    is_active=True,
                )
            )
            await session.commit()


async def test_resolved_requests_do_not_block_a_new_one(seeded):
    """El índice es parcial `WHERE status = 'pending'`: lo resuelto no estorba."""
    async with async_session_maker() as session:
        await session.execute(
            insert(RolePermissionChangeRequest).values(
                role_id=seeded.alpha.roles["viewer"],
                company_id=seeded.alpha.id,
                requested_by_user_id=seeded.alpha.users["admin"].id,
                requested_permission_ids=[],
                status="approved",
                is_active=False,
            )
        )
        await session.execute(
            insert(RolePermissionChangeRequest).values(
                role_id=seeded.alpha.roles["viewer"],
                company_id=seeded.alpha.id,
                requested_by_user_id=seeded.alpha.users["admin"].id,
                requested_permission_ids=[],
                status="pending",
                is_active=True,
            )
        )
        await session.commit()


async def test_change_request_status_is_constrained(seeded):
    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(RolePermissionChangeRequest).values(
                    role_id=seeded.alpha.roles["viewer"],
                    company_id=seeded.alpha.id,
                    requested_by_user_id=seeded.alpha.users["admin"].id,
                    requested_permission_ids=[],
                    status="maybe",
                    is_active=True,
                )
            )
            await session.commit()


async def test_a_change_request_cannot_point_to_a_role_of_another_company(seeded):
    """`company_id` y `role_id` no pueden contradecirse: FK compuesta."""
    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(RolePermissionChangeRequest).values(
                    role_id=seeded.beta.roles["viewer"],
                    company_id=seeded.alpha.id,
                    requested_by_user_id=seeded.alpha.users["admin"].id,
                    requested_permission_ids=[],
                    status="pending",
                    is_active=True,
                )
            )
            await session.commit()


async def test_a_role_cannot_grant_the_same_capability_twice(seeded):
    async with async_session_maker() as session:
        existing = await session.scalar(
            select(RolePermission).where(
                RolePermission.role_id == seeded.alpha.roles["viewer"]
            )
        )

        with pytest.raises(IntegrityError):
            await session.execute(
                insert(RolePermission).values(
                    role_id=existing.role_id,
                    permission_id=existing.permission_id,
                    is_active=True,
                )
            )
            await session.commit()


async def test_usernames_are_unique_across_the_platform(seeded):
    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(Users).values(
                    username=seeded.alpha.users["owner"].username,
                    email="another@example.com",
                    password="x",
                    first_name="A",
                    last_name="B",
                )
            )
            await session.commit()


async def test_timestamps_are_timezone_aware(seeded):
    """D10. Antes convivían `timestamp` naive y `timestamptz` en la misma fila."""
    async with async_session_maker() as session:
        created_at = await session.scalar(
            select(Users.created_at).where(Users.id == seeded.alpha.users["owner"].id)
        )

    assert created_at.tzinfo is not None, (
        "created_at debe llevar zona horaria: comparar naive con aware lanza "
        "TypeError en Python."
    )


async def test_the_company_subdomain_is_mandatory(seeded):
    """Es la clave con la que se resuelve el tenant (AUD-DB-015)."""
    from app.routers_api.companies.models import Company

    async with async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(Company).values(name="No Subdomain Inc", subdomain=None)
            )
            await session.commit()


async def test_the_audit_trail_cannot_be_rewritten(seeded):
    """`audit_event` es append-only y lo garantiza un disparador.

    Sin él, "append-only" sería una convención que se rompe la primera vez que
    alguien abre una consola de SQL.
    """
    from sqlalchemy.exc import DBAPIError

    from app.core.audit.models import AuditEvent

    async with async_session_maker() as session:
        event_id = (
            await session.execute(
                insert(AuditEvent)
                .values(
                    company_id=seeded.alpha.id,
                    entity_type="company",
                    entity_id=1,
                    action="create",
                )
                .returning(AuditEvent.id)
            )
        ).scalar_one()
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(AuditEvent)
                .where(AuditEvent.id == event_id)
                .values(action="tampered")
            )
            await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("DELETE FROM audit_event WHERE id = :id"), {"id": event_id}
            )
            await session.commit()
