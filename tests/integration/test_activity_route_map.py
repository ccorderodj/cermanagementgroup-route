"""Visor de ruta de Activity Admin: los puntos del cálculo de millas, por viaje.

Organigrama de `test_org_hierarchy` (CEO, COO, RM-A/B, OSM-A, SUP-A/B/C,
Sales-A). Lo que se comprueba:

* el permiso `route.activity.map.read` no lo trae **ninguna** plantilla, ni
  owner ni admin, y sin él el endpoint responde 403;
* con él, el viaje tiene que estar en el alcance: COO no ve a Sales (ni por
  id), el CEO sí; otro tenant, 404; historia por periodo;
* los puntos salen en orden, sin repetir el punto entre tramos;
* revocar el permiso corta el acceso en la petición siguiente;
* el listado de Activity sólo dice si hay puntos, nunca coordenadas;
* la CSP abre `img-src` sólo al origen de las teselas configurado.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for
from tests.integration.test_org_hierarchy import (
    _como,
    _ejecutar,
    _filas,
    _iniciada,
    _organigrama,
    _retrofechar,
    _superior,
    _trasladar_en,
)
from tests.integration.test_reports import _jornada

pytestmark = pytest.mark.integration

MAPA = "/api/activity-explorer/trips/{}/map"
CAPACIDAD = "route.activity.map.read"

#: Salida, cambio de plan y llegada (coordenadas sintéticas).
PUNTOS = [
    ("start_trip", 35.10, -79.10),
    ("change_plan", 35.20, -79.00),
    ("arrived", 35.30, -78.90),
]


async def _tramos(trip_id: int, puntos=PUNTOS) -> None:
    """Los tramos que escribe el motor al calcular: uno por par consecutivo."""
    fila = (await _filas(
        "SELECT id, company_id FROM trip_mileage WHERE trip_id = :t", t=trip_id
    ))[0]
    for i, (a, b) in enumerate(zip(puntos, puntos[1:]), start=1):
        await _ejecutar(
            "INSERT INTO trip_mileage_segment (company_id, trip_mileage_id, sequence, "
            "from_event_kind, from_latitude, from_longitude, from_evidence_level, from_captured_at, "
            "to_event_kind, to_latitude, to_longitude, to_evidence_level, to_captured_at, "
            "distance_meters, provider, method, provider_version, computed_at, created_at, updated_at) "
            "VALUES (:c, :m, :s, :fk, :fla, :flo, 'fresh', now(), :tk, :tla, :tlo, 'fresh', now(), "
            "1000, 'tomtom', 'car/fastest/no-traffic', 'test', now(), now(), now())",
            c=fila.company_id, m=fila.id, s=i,
            fk=a[0], fla=a[1], flo=a[2], tk=b[0], tla=b[1], tlo=b[2],
        )


async def _conceder(seeded, rol: str, empresa: str = "alpha") -> None:
    compania = getattr(seeded, empresa)
    await _ejecutar(
        "INSERT INTO role_permission (role_id, permission_id, is_active, created_at, updated_at) "
        "SELECT :r, id, true, now(), now() FROM permission WHERE name = :n",
        r=compania.roles[rol], n=CAPACIDAD,
    )


async def _revocar(seeded, rol: str) -> None:
    await _ejecutar(
        "DELETE FROM role_permission WHERE role_id = :r AND permission_id = "
        "(SELECT id FROM permission WHERE name = :n)",
        r=seeded.alpha.roles[rol], n=CAPACIDAD,
    )


async def _viaje(cliente, seeded, usuario: str, *, tramos: bool = True) -> int:
    hecho = await _jornada(cliente, seeded, usuario=usuario, millas="5.0")
    trip_id = hecho["viaje"]["id"]
    if tramos:
        await _tramos(trip_id)
    return trip_id


async def _pedir(cliente, seeded, actor: str, trip_id: int, empresa: str = "alpha"):
    await cliente.login(getattr(seeded, empresa).users[actor].email)
    return await cliente.get(MAPA.format(trip_id))


# ── El permiso, a demanda ───────────────────────────────────────────────────


def test_ninguna_plantilla_concede_el_mapa():
    for plantilla in DEFAULT_ROLES:
        assert CAPACIDAD not in capabilities_for(plantilla), plantilla.name


async def test_sin_el_permiso_no_hay_coordenadas(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    trip_id = await _viaje(alpha_client, seeded, "sup_c")
    for actor in ("route_admin", "owner", "admin", "ceo"):
        r = await _pedir(alpha_client, seeded, actor, trip_id)
        assert r.status_code == 403, (actor, r.text)
    # El listado de Activity dice que hay puntos, pero no los da.
    await _como(alpha_client, seeded, "route_admin")
    vista = (await alpha_client.get(
        "/api/activity-explorer", params={"range": "day", "date": "2026-09-16",
                                          "supervisor_user_id": seeded.alpha.users["sup_c"].id},
    )).json()
    texto = str(vista)
    assert "latitude" not in texto and "longitude" not in texto


# ── Con el permiso: los puntos, en orden ────────────────────────────────────


async def test_con_el_permiso_salen_los_puntos_en_orden(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "route_admin")
    trip_id = await _viaje(alpha_client, seeded, "sup_c")
    r = await _pedir(alpha_client, seeded, "route_admin", trip_id)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["available"] is True
    assert [(p["sequence"], p["kind"]) for p in cuerpo["points"]] == [
        (1, "start_trip"), (2, "change_plan"), (3, "arrived"),
    ], "tres puntos, sin repetir el de enlace entre tramos"
    assert cuerpo["provider"] == "tomtom"
    assert cuerpo["tiles"]["url"].startswith("https://")
    assert "OpenStreetMap" in cuerpo["tiles"]["attribution"]


async def test_un_viaje_sin_millaje_calculado_no_tiene_puntos(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "route_admin")
    trip_id = await _viaje(alpha_client, seeded, "sup_c", tramos=False)
    await _ejecutar(
        "UPDATE trip_mileage SET state = 'not_calculable', total_meters = NULL, calculated_at = NULL, "
        "terminal_reason = 'arrival_waypoint_missing' WHERE trip_id = :t",
        t=trip_id,
    )
    r = await _pedir(alpha_client, seeded, "route_admin", trip_id)
    assert r.status_code == 200
    assert r.json()["available"] is False and r.json()["points"] == []


# ── Alcance: jerarquía, Sales, tenant, historia ─────────────────────────────


async def test_el_coo_no_ve_a_sales_ni_por_id_y_el_ceo_si(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    for rol in ("COO", "CEO"):
        await _conceder(seeded, rol)
    de_sales = await _viaje(alpha_client, seeded, "sales_a")
    de_su_rama = await _viaje(alpha_client, seeded, "sup_c")
    assert (await _pedir(alpha_client, seeded, "coo", de_su_rama)).status_code == 200
    r = await _pedir(alpha_client, seeded, "coo", de_sales)
    assert r.status_code == 404, r.text
    falso = await _pedir(alpha_client, seeded, "coo", 999_999)
    assert falso.status_code == 404 and falso.json() == r.json(), "igual que un id inventado"
    assert (await _pedir(alpha_client, seeded, "ceo", de_sales)).status_code == 200


async def test_otro_tenant_no_alcanza_el_viaje(seeded, alpha_client, beta_client):
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "route_admin", "beta")
    trip_id = await _viaje(alpha_client, seeded, "sup_c")
    r = await _pedir(beta_client, seeded, "route_admin", trip_id, empresa="beta")
    assert r.status_code == 404


async def test_la_historia_va_por_periodo(seeded, alpha_client):
    """RM-B recibe a SUP-A por traslado: no ve el mapa de un viaje de antes."""
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "Regional Manager")
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    hecho = await _jornada(alpha_client, seeded, usuario="sup_a", millas="5.0")
    await _tramos(hecho["viaje"]["id"])
    assert (await _superior(alpha_client, seeded, "sup_a", "rm_b")).status_code == 200
    await _trasladar_en(seeded.alpha.users["sup_a"].id, datetime(2026, 9, 16, 3, tzinfo=timezone.utc))
    await _iniciada(hecho["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    assert (await _pedir(alpha_client, seeded, "rm_b", hecho["viaje"]["id"])).status_code == 404
    assert (await _pedir(alpha_client, seeded, "rm_a", hecho["viaje"]["id"])).status_code == 200


async def test_revocar_el_permiso_corta_en_la_siguiente_peticion(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "route_admin")
    trip_id = await _viaje(alpha_client, seeded, "sup_c")
    assert (await _pedir(alpha_client, seeded, "route_admin", trip_id)).status_code == 200
    await _revocar(seeded, "route_admin")
    assert (await alpha_client.get(MAPA.format(trip_id))).status_code == 403


async def test_un_supervisor_no_tiene_acceso_aunque_le_den_el_mapa(seeded, alpha_client):
    """Sin `route.activity.read` no hay vista administrativa, y el mapa la exige."""
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "supervisor")
    trip_id = await _viaje(alpha_client, seeded, "sup_c")
    assert (await _pedir(alpha_client, seeded, "sup_c", trip_id)).status_code == 403


# ── La CSP ──────────────────────────────────────────────────────────────────


async def test_la_csp_abre_solo_el_origen_de_las_teselas(seeded, alpha_client):
    r = await alpha_client.get("/login")
    csp = r.headers["content-security-policy"]
    img = next(d for d in csp.split("; ") if d.startswith("img-src"))
    assert "https://tile.openstreetmap.org" in img
    assert "tile.openstreetmap.org" not in csp.replace(img, ""), "sólo en img-src"
