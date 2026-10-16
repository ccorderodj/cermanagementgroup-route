"""Jerarquía V1.6: el CEO lo ve todo, un mando no se vacía a mano y quien sale
puede quedarse con un rango inferior.

Organigrama de partida (`test_org_hierarchy.ORGANIGRAMA`):

    CEO ─┬─ COO ─┬─ RM-A ─┬─ OSM-A
         │       │        └─ SUP-A
         │       └─ SUP-C
         ├─ RM-B ── SUP-B
         └─ Sales-A
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from tests.integration.test_hierarchy_integrity_v14 import _foto, _id, _rol, _sustituir
from tests.integration.test_org_hierarchy import (
    ORG,
    _ejecutar,
    _filas,
    _hoy,
    _iniciada,
    _informe,
    _organigrama,
    _retrofechar,
    _trasladar_en,
    _vigente,
)
from tests.integration.test_reports import _jornada

pytestmark = pytest.mark.integration


# ── El CEO ve todo, sin tiempo ──────────────────────────────────────────────


async def test_el_ceo_ve_todo_aunque_el_relevo_no_tenga_enlace(seeded, alpha_client):
    """El caso de Rodrigo: un relevo de CEO sin `replaces_user_id` (se hizo
    antes de V1.5). Con V1.6 no importa: el CEO ve todo el historial."""
    await _organigrama(alpha_client, seeded)
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    antes = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="10.0", usuario="sup_c")
    r = await _sustituir(alpha_client, seeded, "ceo", _id(seeded, "rm_b"))
    assert r.status_code == 200, r.text
    await _ejecutar("UPDATE org_assignment SET replaces_user_id = NULL")
    for clave in ("rm_b", "coo", "sales_a"):
        await _trasladar_en(_id(seeded, clave), datetime(2026, 9, 16, 3, tzinfo=timezone.utc))
    await _iniciada(antes["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))

    informe = await _informe(alpha_client, seeded, "rm_b", supervisor_user_id=_id(seeded, "sup_c"))
    assert informe["summary"]["official_miles"] == "10.0", "anterior al relevo y sin enlace"


async def test_el_ceo_ve_el_historial_de_quien_ya_salio_y_today_no_lo_muestra(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    jornada = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="7.0", usuario="sup_c")
    await _iniciada(jornada["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.delete(f"/api/route/users/{_id(seeded, 'sup_c')}")).status_code == 204

    informe = await _informe(alpha_client, seeded, "ceo", supervisor_user_id=_id(seeded, "sup_c"))
    assert informe["summary"]["official_miles"] == "7.0"
    assert _id(seeded, "sup_c") not in await _hoy(alpha_client, seeded, "ceo"), "Today: sólo quien está"


async def test_los_rm_siguen_por_periodo(seeded, alpha_client):
    """El tiempo sigue rigiendo de RM hacia abajo: el traslado lateral no
    lleva la zona anterior al nuevo RM."""
    await _organigrama(alpha_client, seeded)
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    antes = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="10.0", usuario="sup_a")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.put(f"/api/route/users/{_id(seeded, 'sup_a')}", json={"superior_user_id": _id(seeded, "rm_b")})
    assert r.status_code == 200, r.text
    await _trasladar_en(_id(seeded, "sup_a"), datetime(2026, 9, 16, 3, tzinfo=timezone.utc))
    await _iniciada(antes["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    u = _id(seeded, "sup_a")
    assert (await _informe(alpha_client, seeded, "rm_b", supervisor_user_id=u))["summary"]["official_miles"] == "0.0"
    assert (await _informe(alpha_client, seeded, "ceo", supervisor_user_id=u))["summary"]["official_miles"] == "10.0"


# ── Un mando no se vacía a mano ─────────────────────────────────────────────


async def test_mover_al_ultimo_del_equipo_de_un_mando_se_rechaza(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    # Parte del equipo de RM-A: permitido.
    r = await alpha_client.put(f"/api/route/users/{_id(seeded, 'sup_a')}", json={"superior_user_id": _id(seeded, "rm_b")})
    assert r.status_code == 200, r.text
    antes = await _foto(seeded)
    intentos = [
        # El último de RM-A, a otro jefe.
        alpha_client.put(f"/api/route/users/{_id(seeded, 'osm_a')}", json={"superior_user_id": _id(seeded, "coo")}),
        # El último de RM-A, fuera del árbol por un cambio de rol.
        alpha_client.put(f"/api/route/users/{_id(seeded, 'osm_a')}", json={"role_id": seeded.alpha.roles["route_admin"]}),
        # Por la API de organización.
        alpha_client.put(f"{ORG}/{_id(seeded, 'osm_a')}", json={"position": "osm", "superior_user_id": _id(seeded, "coo")}),
        alpha_client.delete(f"{ORG}/{_id(seeded, 'osm_a')}"),
    ]
    for intento in intentos:
        r = await intento
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "manager_left_without_team"
    assert await _foto(seeded) == antes


async def test_salir_de_la_compania_o_suspender_no_esta_bloqueado(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    sup_b = _id(seeded, "sup_b")
    assert (await alpha_client.put(f"/api/route/users/{sup_b}/access", json={"is_active": False})).status_code == 200
    assert (await alpha_client.delete(f"/api/route/users/{sup_b}")).status_code == 204


# ── Sustituir y bajar de rango a quien sale ─────────────────────────────────


async def test_sustituir_al_coo_y_dejarlo_como_rm_bajo_el_sucesor(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    cuerpo = {
        "outgoing_role_id": seeded.alpha.roles["Regional Manager"],
        "outgoing_superior_user_id": _id(seeded, "rm_b"),
    }
    vista = await _sustituir(alpha_client, seeded, "coo", _id(seeded, "rm_b"), dry_run=True, **cuerpo)
    assert vista.status_code == 200, vista.text
    assert vista.json()["outgoing_after"] == "Regional Manager"
    r = await _sustituir(alpha_client, seeded, "coo", _id(seeded, "rm_b"), **cuerpo)
    assert r.status_code == 200, r.text
    assert (await _vigente(seeded, "coo")) == ("regional_manager", _id(seeded, "rm_b"), 2)
    assert await _rol(seeded, "coo") == "Regional Manager", "sigue en la compañía, con el rol de su cargo"
    assert (await _vigente(seeded, "rm_b")).position == "coo"
    assert (await _vigente(seeded, "rm_a")).superior_user_id == _id(seeded, "rm_b")
    eventos = await _filas(
        "SELECT action FROM audit_event WHERE changes -> 'operation_id' ->> 'new' = :o",
        o=r.json()["operation_id"],
    )
    assert "delete" not in {e.action for e in eventos}, "no se retiró a nadie"


async def test_sustituir_al_ceo_y_dejarlo_como_coo(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    r = await _sustituir(
        alpha_client, seeded, "ceo", _id(seeded, "coo"),
        outgoing_role_id=seeded.alpha.roles["COO"], outgoing_superior_user_id=_id(seeded, "coo"),
    )
    assert r.status_code == 200, r.text
    assert (await _vigente(seeded, "coo")).position == "ceo"
    assert (await _vigente(seeded, "ceo"))[:2] == ("coo", _id(seeded, "coo"))
    assert (await _vigente(seeded, "sales_a")).superior_user_id == _id(seeded, "coo"), "Sales, al nuevo CEO"
    n = await _filas(
        "SELECT count(*) AS n FROM org_assignment WHERE company_id = :c AND position = 'ceo' AND valid_to IS NULL",
        c=seeded.alpha.id,
    )
    assert n[0].n == 1


@pytest.mark.parametrize(
    ("rol", "superior", "codigo"),
    [
        ("COO", "rm_b", 409),            # mismo nivel: no es bajar de rango
        ("CEO", None, 409),               # más alto
        ("Regional Manager", "coo", 409), # bajo sí mismo: ciclo
        ("Sales", "rm_b", 409),           # Sales sólo bajo un CEO
        ("route_admin", None, 422),       # fuera de la jerarquía
    ],
)
async def test_bajadas_de_rango_invalidas_no_cambian_nada(seeded, alpha_client, rol, superior, codigo):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    r = await _sustituir(
        alpha_client, seeded, "coo", _id(seeded, "rm_b"),
        outgoing_role_id=seeded.alpha.roles[rol],
        outgoing_superior_user_id=_id(seeded, superior) if superior else None,
    )
    assert r.status_code == codigo, r.text
    assert await _foto(seeded) == antes


async def test_la_vista_de_continuidad_ofrece_roles_inferiores(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    info = (await alpha_client.get(f"{ORG}/{_id(seeded, 'coo')}/succession")).json()
    assert {r["position"] for r in info["demotion_roles"]} == {
        "regional_manager", "osm", "supervisor", "sales",
    }
