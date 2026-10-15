"""Regularización de la jerarquía: rol alineado con el cargo y readmisión.

Reproduce los datos que dejó la pantalla general antes de V1.4 (rol
`supervisor` con cargo COO o RM) y una CEO retirada por «Replace manager» en
V1.4, y comprueba que el comando los deja coherentes por los servicios del
producto, sin tocar cargos ni superiores, y que la pantalla de CER Route
también puede regularizar sin abrir un ascenso por la lista.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.db.scripts.regularize_hierarchy import alinear, desajustes, readmitir
from tests.integration.test_hierarchy_integrity_v14 import _foto, _id, _rol, _sustituir
from tests.integration.test_org_hierarchy import _ejecutar, _filas, _organigrama, _vigente

pytestmark = pytest.mark.integration


async def _desajustar(seeded, *claves: str) -> None:
    """Lo que hizo la pantalla general antes de V1.4: rol Supervisor, cargo intacto."""
    for clave in claves:
        await _ejecutar(
            "UPDATE user_company SET role_id = :r WHERE user_id = :u AND company_id = :c",
            r=seeded.alpha.roles["supervisor"], u=_id(seeded, clave), c=seeded.alpha.id,
        )


async def test_alinear_pone_el_rol_del_cargo_sin_tocar_la_estructura(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _desajustar(seeded, "coo", "rm_a")
    cargos = await _filas("SELECT * FROM org_assignment WHERE company_id = :c ORDER BY id", c=seeded.alpha.id)

    casos = await desajustes(seeded.alpha.id)
    assert {(c.user_id, c.rol_del_cargo) for c in casos} == {
        (_id(seeded, "coo"), "COO"), (_id(seeded, "rm_a"), "Regional Manager"),
    }
    antes = await _foto(seeded)
    await alinear(seeded.alpha.id, aplicar=False)
    assert await _foto(seeded) == antes, "el modo prueba no escribe"

    await alinear(seeded.alpha.id, aplicar=True)
    assert await _rol(seeded, "coo") == "COO"
    assert await _rol(seeded, "rm_a") == "Regional Manager"
    assert await _filas(
        "SELECT * FROM org_assignment WHERE company_id = :c ORDER BY id", c=seeded.alpha.id
    ) == cargos, "cargos y superiores intactos"
    eventos = await _filas(
        "SELECT entity_id FROM audit_event WHERE entity_type = 'user' AND action = 'update' "
        "AND reason = 'Hierarchy regularization by authorized command'"
    )
    assert {e.entity_id for e in eventos} == {_id(seeded, "coo"), _id(seeded, "rm_a")}
    assert await desajustes(seeded.alpha.id) == [], "idempotente"


async def test_la_pantalla_regulariza_pero_no_asciende(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _desajustar(seeded, "coo")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    # Rol COO a quien ya tiene cargo COO, mismo superior: regularizar.
    r = await alpha_client.put(f"/api/route/users/{_id(seeded, 'coo')}", json={
        "role_id": seeded.alpha.roles["COO"], "superior_user_id": _id(seeded, "ceo")})
    assert r.status_code == 200, r.text
    assert await _rol(seeded, "coo") == "COO"
    # Rol COO a un RM: sigue siendo un ascenso por la lista.
    r = await alpha_client.put(f"/api/route/users/{_id(seeded, 'rm_b')}", json={
        "role_id": seeded.alpha.roles["COO"], "superior_user_id": _id(seeded, "ceo")})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "use_replace_manager"


async def test_readmitir_a_la_ex_ceo_como_coo(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    ex_ceo = seeded.alpha.users["ceo"]
    r = await _sustituir(alpha_client, seeded, "ceo", _id(seeded, "rm_b"))
    assert r.status_code == 200, r.text
    nuevo_ceo = seeded.alpha.users["rm_b"].email

    antes = await _foto(seeded)
    await readmitir(seeded.alpha.id, correo=ex_ceo.email, rol="COO", superior=nuevo_ceo, aplicar=False)
    assert await _foto(seeded) == antes, "el modo prueba no escribe"

    await readmitir(seeded.alpha.id, correo=ex_ceo.email, rol="COO", superior=nuevo_ceo, aplicar=True)
    assert await _rol(seeded, "ceo") == "COO"
    assert (await _vigente(seeded, "ceo"))[:2] == ("coo", _id(seeded, "rm_b"))
    with pytest.raises(SystemExit):
        await readmitir(seeded.alpha.id, correo=ex_ceo.email, rol="COO", superior=nuevo_ceo, aplicar=True)


async def test_readmitir_como_segundo_ceo_no_deja_nada(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    ex_ceo = seeded.alpha.users["ceo"]
    assert (await _sustituir(alpha_client, seeded, "ceo", _id(seeded, "rm_b"))).status_code == 200
    antes = await _foto(seeded)
    with pytest.raises(HTTPException):
        await readmitir(
            seeded.alpha.id, correo=ex_ceo.email, rol="CEO",
            superior=seeded.alpha.users["rm_b"].email, aplicar=True,
        )
    assert await _foto(seeded) == antes, "pertenencia y cargo, todo o nada"
