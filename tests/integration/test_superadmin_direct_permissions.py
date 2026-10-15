"""El superadministrador de plataforma cambia capacidades sin pasar por aprobación.

Decisión de CER (15-10-2026): `Users.is_superuser` está por encima de
cualquier rol y permiso, también del flujo maker-checker. Su cambio se aplica
al momento y deja la misma traza que una aprobación (solicitud `approved` con
él como solicitante y revisor) más un `audit_event`. Una solicitud pendiente
de otra persona sobre ese rol se cierra como sustituida. Para todos los demás
—`owner` incluido— el flujo de dos personas sigue igual.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import async_session_maker

pytestmark = pytest.mark.integration


async def _filas(sql: str, **p):
    async with async_session_maker() as s:
        return (await s.execute(text(sql), p)).all()


async def _id_permiso(nombre: str) -> int:
    return (await _filas("SELECT id FROM permission WHERE name = :n", n=nombre))[0].id


async def _concedidas(role_id: int) -> set[str]:
    return {
        f.name
        for f in await _filas(
            "SELECT p.name FROM role_permission rp JOIN permission p ON p.id = rp.permission_id "
            "WHERE rp.role_id = :r AND rp.is_active",
            r=role_id,
        )
    }


async def _poner(cliente, role_id: int, nombres: set[str]):
    ids = [await _id_permiso(n) for n in sorted(nombres)]
    return await cliente.put(f"/api/roles/{role_id}/permissions", json={"permission_ids": ids})


async def test_el_superadmin_aplica_al_momento_y_queda_trazado(seeded, alpha_client):
    rol = seeded.alpha.roles["viewer"]
    antes = await _concedidas(rol)
    deseadas = antes | {"route.activity.map.read"}

    await alpha_client.login(seeded.platform_admin.email)
    r = await _poner(alpha_client, rol, deseadas)
    assert r.status_code == 200, r.text
    assert r.json().get("pending_request") is None, "no queda nada pendiente"
    assert await _concedidas(rol) == deseadas, "aplicado ya"

    solicitud = (await _filas(
        "SELECT status, requested_by_user_id, reviewed_by_user_id, review_note "
        "FROM role_permission_change_request WHERE role_id = :r ORDER BY id DESC LIMIT 1",
        r=rol,
    ))[0]
    assert solicitud.status == "approved"
    assert solicitud.requested_by_user_id == solicitud.reviewed_by_user_id == seeded.platform_admin.id
    evento = await _filas(
        "SELECT actor_user_id, changes FROM audit_event "
        "WHERE entity_type = 'role_permission' AND action = 'apply_direct' AND entity_id = :r",
        r=rol,
    )
    assert evento and evento[0].actor_user_id == seeded.platform_admin.id
    assert evento[0].changes["granted"]["new"] == ["route.activity.map.read"]


async def test_el_superadmin_sustituye_una_solicitud_pendiente(seeded, alpha_client):
    rol = seeded.alpha.roles["viewer"]
    antes = await _concedidas(rol)
    await alpha_client.login(seeded.alpha.users["owner"].email)
    r = await _poner(alpha_client, rol, antes | {"route.live.read"})
    assert r.status_code == 200 and r.json()["pending_request"] is not None

    await alpha_client.login(seeded.platform_admin.email)
    r = await _poner(alpha_client, rol, antes | {"route.activity.map.read"})
    assert r.status_code == 200, r.text
    assert await _concedidas(rol) == antes | {"route.activity.map.read"}
    sustituida = await _filas(
        "SELECT status, review_note FROM role_permission_change_request "
        "WHERE role_id = :r AND requested_by_user_id = :u",
        r=rol, u=seeded.alpha.users["owner"].id,
    )
    assert sustituida[0].status == "rejected"
    assert "Superseded" in sustituida[0].review_note


async def test_el_owner_sigue_pasando_por_aprobacion(seeded, alpha_client):
    rol = seeded.alpha.roles["viewer"]
    antes = await _concedidas(rol)
    await alpha_client.login(seeded.alpha.users["owner"].email)
    r = await _poner(alpha_client, rol, antes | {"route.activity.map.read"})
    assert r.status_code == 200
    assert r.json()["pending_request"] is not None
    assert await _concedidas(rol) == antes, "sin aprobar no se aplica"


async def test_sin_cambios_no_hay_nada_que_aplicar(seeded, alpha_client):
    rol = seeded.alpha.roles["viewer"]
    await alpha_client.login(seeded.platform_admin.email)
    r = await _poner(alpha_client, rol, await _concedidas(rol))
    assert r.status_code == 400
