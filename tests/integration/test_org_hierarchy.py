"""
Jerarquía organizacional, RBAC y alcance de datos (Control C).

El organigrama de prueba, en alpha (todo por API, como lo haría el Superadmin):

    CEO
     ├── COO
     │    ├── RM-A ── OSM-A, SUP-A
     │    └── SUP-C                (COO → Supervisor, sin RM)
     └── RM-B ── SUP-B             (CEO → RM, sin COO)

    `supervisor` (sembrado) queda **sin asignar**.

CEO, COO, RM-A y RM-B tienen el rol `route_manager`; OSM-A y los SUP, el rol
`supervisor`. Beta es el otro tenant.

Lo que se defiende: invariantes del modelo (nivel, ciclos, superior único,
tenant, concurrencia, auditoría), el alcance por rama en Today, Activity,
Reports y Excel, la historia por periodo con `started_at` (D-3), la
administración delegada por **todas** las rutas de usuarios y la igualdad
OSM = Supervisor.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.database import async_session_maker
from tests.integration.conftest import TEST_PASSWORD, SeededUser, TenantClient
from tests.integration.test_activity_explorer import _perfil_y_vehiculo
from tests.integration.test_reports import _jornada

pytestmark = pytest.mark.integration

ORG = "/api/route/organization"
DIA = date(2026, 9, 16)


# ── Ayudas ──────────────────────────────────────────────────────────────────


async def _persona(cliente, seeded, clave: str, rol: str, *, compania: str = "alpha") -> SeededUser:
    empresa = getattr(seeded, compania)
    await cliente.login(empresa.users["route_admin"].email)
    r = await cliente.post(
        "/api/route/users",
        json={
            "username": f"{compania}_{clave}",
            "email": f"{clave}@{compania}.example.com",
            "first_name": clave.upper(),
            "last_name": "Org",
            "password": TEST_PASSWORD,
            "role_id": empresa.roles[rol],
        },
    )
    assert r.status_code in (200, 201), r.text
    usuario = SeededUser(id=r.json()["id"], email=f"{clave}@{compania}.example.com",
                         username=f"{compania}_{clave}", role=rol)
    empresa.users[clave] = usuario
    return usuario


async def _cargo(cliente, seeded, clave, posicion, superior=None, *, actor="route_admin", **extra):
    await cliente.login(seeded.alpha.users[actor].email)
    return await cliente.put(
        f"{ORG}/{seeded.alpha.users[clave].id}",
        json={
            "position": posicion,
            "superior_user_id": seeded.alpha.users[superior].id if superior else None,
            **extra,
        },
    )


async def _organigrama(cliente, seeded, *, perfiles: bool = True) -> None:
    for clave in ("ceo", "coo", "rm_a", "rm_b"):
        await _persona(cliente, seeded, clave, "route_manager")
    for clave in ("osm_a", "sup_a", "sup_b", "sup_c"):
        await _persona(cliente, seeded, clave, "supervisor")
    for clave, cargo, jefe in (
        ("ceo", "ceo", None),
        ("coo", "coo", "ceo"),
        ("rm_a", "regional_manager", "coo"),
        ("rm_b", "regional_manager", "ceo"),
        ("osm_a", "osm", "rm_a"),
        ("sup_a", "supervisor", "rm_a"),
        ("sup_b", "supervisor", "rm_b"),
        ("sup_c", "supervisor", "coo"),
    ):
        r = await _cargo(cliente, seeded, clave, cargo, jefe)
        assert r.status_code == 200, (clave, r.text)
    if perfiles:
        for clave in ("osm_a", "sup_a", "sup_b", "sup_c", "supervisor"):
            await _perfil_y_vehiculo(cliente, seeded, unidad=f"V-ORG-{clave}", usuario=clave)


def _ids(seeded, *claves) -> set[int]:
    return {seeded.alpha.users[c].id for c in claves}


async def _como(cliente, seeded, clave):
    await cliente.login(seeded.alpha.users[clave].email)
    return cliente


async def _hoy(cliente, seeded, clave) -> set[int]:
    await _como(cliente, seeded, clave)
    r = await cliente.get("/api/live/today")
    assert r.status_code == 200, r.text
    return {s["user_id"] for s in r.json()["supervisors"]}


async def _explorables(cliente, seeded, clave) -> set[int]:
    await _como(cliente, seeded, clave)
    r = await cliente.get("/api/activity-explorer", params={"range": "week", "date": DIA.isoformat()})
    assert r.status_code == 200, r.text
    return {s["user_id"] for s in r.json()["supervisors"]}


async def _informe(cliente, seeded, clave, **params) -> dict:
    await _como(cliente, seeded, clave)
    params.setdefault("range", "week")
    params.setdefault("date", DIA.isoformat())
    r = await cliente.get("/api/reports", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def _filas(sql: str, **p):
    async with async_session_maker() as s:
        return (await s.execute(text(sql), p)).all()


async def _ejecutar(sql: str, **p):
    async with async_session_maker() as s:
        await s.execute(text(sql), p)
        await s.commit()


async def _retrofechar(company_id: int, desde: datetime) -> None:
    """Prepara la historia: las asignaciones abiertas valen desde `desde`."""
    await _ejecutar(
        "UPDATE org_assignment SET valid_from = :d WHERE company_id = :c AND valid_to IS NULL",
        d=desde, c=company_id,
    )


async def _iniciada(jornada_id: int, instante: datetime) -> None:
    await _ejecutar("UPDATE work_session SET started_at = :t WHERE id = :i", t=instante, i=jornada_id)


# ── Modelo e invariantes ────────────────────────────────────────────────────


async def test_niveles_opcionales_y_sin_backfill(seeded, alpha_client):
    """CEO→RM sin COO y COO→Supervisor sin RM son válidos; nadie más tiene cargo."""
    assert await _filas("SELECT 1 FROM org_assignment") == [], "sin asignaciones inferidas"
    await _organigrama(alpha_client, seeded, perfiles=False)
    filas = await _filas(
        "SELECT user_id, position, superior_user_id FROM org_assignment WHERE valid_to IS NULL"
    )
    assert len(filas) == 8
    assert seeded.alpha.users["supervisor"].id not in {f.user_id for f in filas}


@pytest.mark.parametrize(
    ("clave", "cargo", "jefe", "codigo"),
    [
        ("sup_a", "supervisor", "osm_a", 422),   # lateral Supervisor → OSM
        ("osm_a", "osm", "sup_a", 422),          # lateral OSM → Supervisor
        ("rm_b", "regional_manager", "rm_a", 422),  # par
        ("coo", "coo", "rm_a", 422),             # superior de nivel inferior
        ("sup_a", "supervisor", "sup_a", 422),   # a sí mismo
    ],
)
async def test_relaciones_invalidas_se_rechazan(seeded, alpha_client, clave, cargo, jefe, codigo):
    await _organigrama(alpha_client, seeded, perfiles=False)
    r = await _cargo(alpha_client, seeded, clave, cargo, jefe)
    assert r.status_code == codigo, r.text


async def test_superior_de_otro_tenant_y_objetivo_de_otro_tenant(seeded, alpha_client, beta_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    ajeno = await _persona(beta_client, seeded, "beta_rm", "route_manager", compania="beta")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.put(
        f"{ORG}/{seeded.alpha.users['sup_a'].id}",
        json={"position": "supervisor", "superior_user_id": ajeno.id},
    )
    assert r.status_code == 422
    r = await alpha_client.put(f"{ORG}/{ajeno.id}", json={"position": "supervisor"})
    assert r.status_code == 404


async def test_un_manager_con_subordinados_no_baja_ni_se_retira(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    assert (await _cargo(alpha_client, seeded, "rm_a", "supervisor", "coo")).status_code == 409
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    rm_a = seeded.alpha.users["rm_a"].id
    assert (await alpha_client.delete(f"{ORG}/{rm_a}")).status_code == 409
    assert (await alpha_client.delete(f"/api/route/users/{rm_a}")).status_code == 409


async def test_nadie_se_asigna_a_si_mismo(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.put(
        f"{ORG}/{seeded.alpha.users['route_admin'].id}",
        json={"position": "ceo"},
    )
    assert r.status_code == 403


async def test_reasignar_cierra_y_abre_sin_solape_y_audita(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    assert (await _cargo(alpha_client, seeded, "sup_a", "supervisor", "rm_b")).status_code == 200
    filas = await _filas(
        "SELECT superior_user_id, valid_from, valid_to, version FROM org_assignment "
        "WHERE user_id = :u ORDER BY valid_from",
        u=seeded.alpha.users["sup_a"].id,
    )
    assert len(filas) == 2
    assert filas[0].valid_to == filas[1].valid_from, "contiguas: sin hueco ni solape"
    assert filas[1].valid_to is None and filas[1].version == filas[0].version + 1
    eventos = await _filas(
        "SELECT action, actor_user_id, changes FROM audit_event WHERE entity_type = "
        "'org_assignment' AND entity_id = :u ORDER BY id",
        u=seeded.alpha.users["sup_a"].id,
    )
    assert [e.action for e in eventos] == ["assign", "reassign"]
    assert eventos[1].actor_user_id == seeded.alpha.users["route_admin"].id
    assert eventos[1].changes["superior_user_id"] == {
        "old": seeded.alpha.users["rm_a"].id, "new": seeded.alpha.users["rm_b"].id,
    }


async def test_la_base_rechaza_dos_asignaciones_abiertas(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    with pytest.raises(Exception, match="uq_org_assignment_current|ex_org_assignment_no_overlap"):
        await _ejecutar(
            "INSERT INTO org_assignment (company_id, user_id, position, valid_from) "
            "VALUES (:c, :u, 'supervisor', now())",
            c=seeded.alpha.id, u=seeded.alpha.users["sup_a"].id,
        )


async def test_dos_reasignaciones_simultaneas_una_gana(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    version = (await _filas(
        "SELECT version FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
        u=seeded.alpha.users["sup_a"].id,
    ))[0].version

    async def intento(jefe: str) -> int:
        async with TenantClient("alpha") as c:
            r = await _cargo(c, seeded, "sup_a", "supervisor", jefe, version=version)
            return r.status_code

    codigos = sorted(await asyncio.gather(intento("rm_b"), intento("coo")))
    assert codigos == [200, 409]
    abiertas = await _filas(
        "SELECT 1 FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
        u=seeded.alpha.users["sup_a"].id,
    )
    assert len(abiertas) == 1


# ── Alcance: Today, Activity, Reports, Excel ────────────────────────────────


async def test_today_por_rama_vigente(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    assert await _hoy(alpha_client, seeded, "rm_a") == _ids(seeded, "osm_a", "sup_a")
    assert await _hoy(alpha_client, seeded, "rm_b") == _ids(seeded, "sup_b")
    assert await _hoy(alpha_client, seeded, "coo") == _ids(seeded, "osm_a", "sup_a", "sup_c")
    assert await _hoy(alpha_client, seeded, "ceo") == _ids(seeded, "osm_a", "sup_a", "sup_b", "sup_c")
    # El Superadmin conserva el tenant, incluido quien no tiene cargo.
    assert await _hoy(alpha_client, seeded, "route_admin") == _ids(
        seeded, "osm_a", "sup_a", "sup_b", "sup_c", "supervisor"
    )


async def test_activity_por_rama_y_404_fuera(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    assert await _explorables(alpha_client, seeded, "rm_a") == _ids(seeded, "osm_a", "sup_a")
    await _como(alpha_client, seeded, "rm_a")
    params = {"range": "week", "date": DIA.isoformat()}
    ajeno = await alpha_client.get(
        "/api/activity-explorer",
        params={**params, "supervisor_user_id": seeded.alpha.users["sup_b"].id},
    )
    falso = await alpha_client.get(
        "/api/activity-explorer", params={**params, "supervisor_user_id": 987654321}
    )
    assert ajeno.status_code == falso.status_code == 404
    assert ajeno.json() == falso.json()


async def test_reports_y_excel_con_el_mismo_alcance(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _jornada(alpha_client, seeded, millas="10.0", usuario="sup_a")
    await _jornada(alpha_client, seeded, millas="4.0", usuario="osm_a")
    await _jornada(alpha_client, seeded, millas="7.0", usuario="sup_b")
    await _jornada(alpha_client, seeded, millas="2.0", usuario="supervisor")

    rm_a = await _informe(alpha_client, seeded, "rm_a")
    assert {s["user_id"] for s in rm_a["supervisors"]} == _ids(seeded, "osm_a", "sup_a")
    assert rm_a["summary"]["official_miles"] == "14.0"
    assert (await _informe(alpha_client, seeded, "ceo"))["summary"]["official_miles"] == "21.0"
    assert (await _informe(alpha_client, seeded, "route_admin"))["summary"]["official_miles"] == "23.0"

    await _como(alpha_client, seeded, "rm_a")
    params = {"range": "week", "date": DIA.isoformat()}
    for ruta in ("/api/reports", "/api/reports/export"):
        r = await alpha_client.get(
            ruta, params={**params, "supervisor_user_id": seeded.alpha.users["sup_b"].id}
        )
        assert r.status_code == 404, ruta
    excel = await alpha_client.get("/api/reports/export", params=params)
    assert excel.status_code == 200
    filas = list(load_workbook(BytesIO(excel.content))["Activity Detail"].iter_rows(values_only=True))[1:]
    assert sorted(f[8] for f in filas) == [4.0, 10.0], "las filas del Excel = la pantalla"


async def test_un_manager_sin_cargo_no_ve_a_nadie(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _persona(alpha_client, seeded, "huerfano", "route_manager")
    await _jornada(alpha_client, seeded, millas="10.0", usuario="sup_a")
    assert await _hoy(alpha_client, seeded, "huerfano") == set()
    assert await _explorables(alpha_client, seeded, "huerfano") == set()
    vista = await _informe(alpha_client, seeded, "huerfano")
    assert vista["supervisors"] == [] and vista["summary"]["official_miles"] == "0.0"
    await _como(alpha_client, seeded, "huerfano")
    r = await alpha_client.get("/api/users/pagination", params={"page": 1, "page_size": 50})
    assert r.json()["count"] == 0 if "count" in r.json() else r.json()["results"] == []


async def test_osm_y_supervisor_son_iguales(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    permisos = {}
    for clave in ("osm_a", "sup_a"):
        await _como(alpha_client, seeded, clave)
        permisos[clave] = sorted(
            (await _filas(
                "SELECT p.name FROM permission p JOIN role_permission rp ON rp.permission_id = p.id "
                "JOIN user_company uc ON uc.role_id = rp.role_id WHERE uc.user_id = :u",
                u=seeded.alpha.users[clave].id,
            ))
        )
        for ruta in ("/api/live/today", "/api/activity-explorer", "/api/reports",
                     "/api/users/pagination", ORG):
            assert (await alpha_client.get(ruta)).status_code == 403, (clave, ruta)
        assert (await alpha_client.get("/api/activity-explorer/me")).status_code == 200
    assert permisos["osm_a"] == permisos["sup_a"]


async def test_un_manager_en_su_activity_personal_ve_solo_lo_suyo(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _jornada(alpha_client, seeded, millas="10.0", usuario="sup_a")
    await _como(alpha_client, seeded, "rm_a")
    r = await alpha_client.get("/api/activity-explorer/me", params={"range": "week", "date": DIA.isoformat()})
    assert r.status_code == 200
    assert r.json()["supervisor_user_id"] == seeded.alpha.users["rm_a"].id
    assert r.json()["groups"] == []


# ── Historia por periodo (D-3) ──────────────────────────────────────────────


async def test_traslado_rm_a_rm_b_por_started_at(seeded, alpha_client):
    """Antes de T, de RM-A; desde T, de RM-B. La jornada que empieza antes de T y
    termina después es entera de RM-A."""
    await _organigrama(alpha_client, seeded)
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    antes = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="10.0", usuario="sup_a")
    cruza = await _jornada(alpha_client, seeded, dia=date(2026, 9, 15), millas="3.0", usuario="sup_a")
    despues = await _jornada(alpha_client, seeded, dia=date(2026, 9, 17), millas="5.0", usuario="sup_a")

    assert (await _cargo(alpha_client, seeded, "sup_a", "supervisor", "rm_b")).status_code == 200
    t = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
    await _ejecutar(
        "UPDATE org_assignment SET valid_to = :t WHERE user_id = :u AND valid_to IS NOT NULL",
        t=t, u=seeded.alpha.users["sup_a"].id,
    )
    await _ejecutar(
        "UPDATE org_assignment SET valid_from = :t WHERE user_id = :u AND valid_to IS NULL",
        t=t, u=seeded.alpha.users["sup_a"].id,
    )
    await _iniciada(antes["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    # Empieza la noche del 15 y termina la madrugada del 16, pasado T.
    await _iniciada(cruza["jornada"]["id"], datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    await _iniciada(despues["jornada"]["id"], datetime(2026, 9, 17, 13, tzinfo=timezone.utc))
    await _ejecutar(
        "UPDATE work_session SET ended_at = :t WHERE id = :i",
        t=datetime(2026, 9, 16, 6, tzinfo=timezone.utc), i=cruza["jornada"]["id"],
    )

    a = await _informe(alpha_client, seeded, "rm_a", supervisor_user_id=seeded.alpha.users["sup_a"].id)
    b = await _informe(alpha_client, seeded, "rm_b", supervisor_user_id=seeded.alpha.users["sup_a"].id)
    assert a["summary"]["official_miles"] == "13.0", "las dos que empezaron antes de T"
    assert b["summary"]["official_miles"] == "5.0", "sólo la que empezó después"
    # Hoy, sólo RM-B lo tiene.
    assert seeded.alpha.users["sup_a"].id not in await _hoy(alpha_client, seeded, "rm_a")
    assert seeded.alpha.users["sup_a"].id in await _hoy(alpha_client, seeded, "rm_b")
    # Las jornadas no se tocaron.
    sesiones = await _filas(
        "SELECT count(*) AS n FROM work_session WHERE user_id = :u", u=seeded.alpha.users["sup_a"].id
    )
    assert sesiones[0].n == 3


async def test_mover_una_rama_entera(seeded, alpha_client):
    """RM-A pasa del COO al CEO: el COO deja de ver la rama desde T; el CEO la
    sigue viendo, porque estaba por encima antes y después."""
    await _organigrama(alpha_client, seeded)
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    previa = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="10.0", usuario="sup_a")
    posterior = await _jornada(alpha_client, seeded, dia=date(2026, 9, 17), millas="5.0", usuario="sup_a")
    assert (await _cargo(alpha_client, seeded, "rm_a", "regional_manager", "ceo")).status_code == 200
    t = datetime(2026, 9, 16, tzinfo=timezone.utc)
    await _ejecutar(
        "UPDATE org_assignment SET valid_to = :t WHERE user_id = :u AND valid_to IS NOT NULL",
        t=t, u=seeded.alpha.users["rm_a"].id,
    )
    await _ejecutar(
        "UPDATE org_assignment SET valid_from = :t WHERE user_id = :u AND valid_to IS NULL",
        t=t, u=seeded.alpha.users["rm_a"].id,
    )
    await _iniciada(previa["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    await _iniciada(posterior["jornada"]["id"], datetime(2026, 9, 17, 13, tzinfo=timezone.utc))

    coo = await _informe(alpha_client, seeded, "coo")
    ceo = await _informe(alpha_client, seeded, "ceo")
    assert coo["summary"]["official_miles"] == "10.0"
    assert ceo["summary"]["official_miles"] == "15.0"


async def test_historia_anterior_a_la_relacion_no_se_expone(seeded, alpha_client):
    """El supervisor sin asignar trabajó antes; al asignarlo a RM-A hoy, RM-A no
    hereda esa historia (no se infiere quién lo supervisaba)."""
    await _organigrama(alpha_client, seeded)
    await _jornada(alpha_client, seeded, millas="9.0", usuario="supervisor")
    await _iniciada(
        (await _filas("SELECT id FROM work_session WHERE user_id = :u",
                      u=seeded.alpha.users["supervisor"].id))[0].id,
        datetime(2026, 9, 16, 13, tzinfo=timezone.utc),
    )
    assert (await _cargo(alpha_client, seeded, "supervisor", "supervisor", "rm_a")).status_code == 200
    vista = await _informe(alpha_client, seeded, "rm_a")
    assert vista["summary"]["official_miles"] == "0.0"
    assert (await _informe(alpha_client, seeded, "route_admin"))["summary"]["official_miles"] == "9.0"


async def test_el_cambio_rige_en_la_siguiente_lectura(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    assert seeded.alpha.users["sup_a"].id in await _hoy(alpha_client, seeded, "rm_a")
    await _cargo(alpha_client, seeded, "sup_a", "supervisor", "rm_b")
    assert seeded.alpha.users["sup_a"].id not in await _hoy(alpha_client, seeded, "rm_a")
    await _como(alpha_client, seeded, "rm_a")
    r = await alpha_client.put(f"/api/users/{seeded.alpha.users['sup_a'].id}", json={"first_name": "X"})
    assert r.status_code == 404


async def test_suspendido_sale_de_today_y_su_historia_queda(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    await _jornada(alpha_client, seeded, millas="6.0", usuario="sup_a")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.put(
        f"/api/users/{seeded.alpha.users['sup_a'].id}/access", json={"is_active": False}
    )
    assert r.status_code == 200
    assert seeded.alpha.users["sup_a"].id not in await _hoy(alpha_client, seeded, "route_admin")
    assert (await _informe(alpha_client, seeded, "route_admin"))["summary"]["official_miles"] == "6.0"


# ── Administración delegada: todas las rutas ────────────────────────────────


@pytest.mark.parametrize("base", ["/api/users", "/api/route/users"])
async def test_el_manager_lista_solo_su_rama(seeded, alpha_client, base):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "rm_a")
    r = await alpha_client.get(f"{base}/pagination", params={"page": 1, "page_size": 100})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert {u["id"] for u in cuerpo["results"]} == _ids(seeded, "osm_a", "sup_a")
    assert cuerpo["count"] == 2, "el total tampoco cuenta a nadie más"


@pytest.mark.parametrize("base", ["/api/users", "/api/route/users"])
@pytest.mark.parametrize("objetivo", ["sup_b", "coo", "rm_b", "rm_a", "route_admin", "owner"])
async def test_el_manager_no_toca_fuera_de_su_rama(seeded, alpha_client, base, objetivo):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "rm_a")
    uid = seeded.alpha.users[objetivo].id
    assert (await alpha_client.put(f"{base}/{uid}", json={"first_name": "X"})).status_code == 404
    assert (await alpha_client.put(f"{base}/{uid}/access", json={"is_active": False})).status_code == 404
    assert (await alpha_client.put(f"{ORG}/{uid}", json={"position": "supervisor",
            "superior_user_id": seeded.alpha.users["rm_a"].id})).status_code == 404


async def test_el_manager_no_toca_otro_tenant(seeded, alpha_client, beta_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "rm_a")
    beta = seeded.beta.users["supervisor"].id
    for base in ("/api/users", "/api/route/users"):
        assert (await alpha_client.put(f"{base}/{beta}", json={"first_name": "X"})).status_code == 404
    assert (await alpha_client.put(f"{ORG}/{beta}", json={"position": "supervisor"})).status_code == 404


async def test_el_manager_gestiona_su_rama(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "rm_a")
    sup_a = seeded.alpha.users["sup_a"].id
    assert (await alpha_client.put(f"/api/route/users/{sup_a}", json={"first_name": "Ana"})).status_code == 200
    assert (await alpha_client.put(f"/api/route/users/{sup_a}/access", json={"is_active": False})).status_code == 200
    # Suspendido sigue en su rama: su superior le devuelve el acceso.
    assert (await alpha_client.put(f"/api/route/users/{sup_a}/access", json={"is_active": True})).status_code == 200
    r = await alpha_client.put(f"{ORG}/{sup_a}", json={
        "position": "osm", "superior_user_id": seeded.alpha.users["rm_a"].id})
    assert r.status_code == 200, r.text


async def test_el_manager_no_borra_ni_readmite(seeded, alpha_client):
    """Retirar es del Superadmin (D-1c); readmitir a quien fue retirado, también:
    retirado ya no está en ninguna rama."""
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "rm_a")
    sup_a = seeded.alpha.users["sup_a"].id
    assert (await alpha_client.delete(f"/api/route/users/{sup_a}")).status_code == 403

    sup_c = seeded.alpha.users["sup_c"].id
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.delete(f"/api/route/users/{sup_c}")).status_code == 204
    await _como(alpha_client, seeded, "coo")
    r = await alpha_client.post(f"/api/route/users/{sup_c}/reenrollment",
                                json={"role_id": seeded.alpha.roles["supervisor"]})
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("actor", "cargo", "jefe", "rol", "codigo"),
    [
        ("rm_a", "supervisor", "rm_a", "supervisor", 200),
        ("rm_a", "osm", "osm_a", "supervisor", 422),            # OSM no es superior de nadie
        ("rm_a", "regional_manager", "rm_a", "route_manager", 403),  # su nivel
        ("rm_a", "supervisor", "rm_b", "supervisor", 403),       # rama ajena
        ("rm_a", "supervisor", "rm_a", "route_admin", 403),      # escalar
        ("rm_a", "supervisor", "rm_a", "route_manager", 403),    # rol que no es del cargo
        ("rm_a", None, None, "supervisor", 403),                 # sin cargo: fuera de su rama
        ("coo", "regional_manager", "coo", "route_manager", 200),
        ("coo", "coo", "coo", "route_manager", 403),
        ("ceo", "coo", "ceo", "route_manager", 200),
        ("ceo", "ceo", "ceo", "route_manager", 403),
    ],
)
async def test_alta_delegada(seeded, alpha_client, actor, cargo, jefe, rol, codigo):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, actor)
    r = await alpha_client.post(
        "/api/route/users",
        json={
            "username": f"alpha_nuevo_{actor}", "email": f"nuevo_{actor}@alpha.example.com",
            "first_name": "Nuevo", "last_name": "Org", "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles[rol],
            "position": cargo,
            "superior_user_id": seeded.alpha.users[jefe].id if jefe else None,
        },
    )
    assert r.status_code == (codigo if codigo != 200 else r.status_code), r.text
    if codigo == 200:
        assert r.status_code in (200, 201)
        fila = await _filas(
            "SELECT position, superior_user_id FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
            u=r.json()["id"],
        )
        assert (fila[0].position, fila[0].superior_user_id) == (cargo, seeded.alpha.users[jefe].id)
    else:
        assert await _filas(
            "SELECT 1 FROM \"user\" WHERE email = :e", e=f"nuevo_{actor}@alpha.example.com"
        ) == [], "nada se creó"


@pytest.mark.parametrize("rol", ["route_admin", "route_manager", "owner"])
async def test_el_manager_no_escala_un_rol(seeded, alpha_client, rol):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "rm_a")
    r = await alpha_client.put(
        f"/api/users/{seeded.alpha.users['sup_a'].id}", json={"role_id": seeded.alpha.roles[rol]}
    )
    assert r.status_code == 403


async def test_un_route_admin_en_la_rama_no_es_gestionable(seeded, alpha_client):
    """Un Superadmin colocado bajo un RM no queda a merced del RM (contraseña)."""
    await _organigrama(alpha_client, seeded, perfiles=False)
    admin2 = await _persona(alpha_client, seeded, "admin2", "route_admin")
    assert (await _cargo(alpha_client, seeded, "admin2", "supervisor", "rm_a")).status_code == 200
    await _como(alpha_client, seeded, "rm_a")
    r = await alpha_client.put(f"/api/users/{admin2.id}", json={"password": "Otra-Clave-123!"})
    assert r.status_code == 404


async def test_roles_asignables_por_nivel(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    esperado = {"rm_a": {"supervisor"}, "coo": {"route_manager", "supervisor"}}
    for actor, roles in esperado.items():
        await _como(alpha_client, seeded, actor)
        r = await alpha_client.get("/api/route/users/assignable-roles")
        assert {o["code"] for o in r.json()} == roles
        o = (await alpha_client.get(f"{ORG}/options")).json()
        nivel = {"rm_a": 2, "coo": 3}[actor]
        assert all(p["level"] < nivel for p in o["positions"])


async def test_ejecutores_no_administran(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    for clave in ("osm_a", "sup_a"):
        await _como(alpha_client, seeded, clave)
        assert (await alpha_client.get("/api/route/users/pagination")).status_code == 403
        assert (await alpha_client.put(
            f"{ORG}/{seeded.alpha.users['sup_b'].id}", json={"position": "supervisor"}
        )).status_code == 403


# ── Catálogo y provisión ────────────────────────────────────────────────────


async def test_route_manager_tiene_exactamente_lo_aprobado(seeded):
    filas = await _filas(
        "SELECT p.name FROM permission p JOIN role_permission rp ON rp.permission_id = p.id "
        "WHERE rp.role_id = :r",
        r=seeded.alpha.roles["route_manager"],
    )
    assert {f.name for f in filas} == {
        "route.worksession.execute", "route.standardvalues.read", "route.live.read",
        "route.activity.read", "route.reports.read", "route.reports.export",
        "users.read", "users.create", "users.update",
    }


async def test_la_alineacion_concede_route_manager_a_tenants_existentes(seeded):
    from app.db.scripts.align_role_capabilities import alinear

    await _ejecutar("DELETE FROM role_permission WHERE role_id = :r", r=seeded.alpha.roles["route_manager"])
    await alinear()
    filas = await _filas(
        "SELECT p.name FROM permission p JOIN role_permission rp ON rp.permission_id = p.id "
        "WHERE rp.role_id = :r",
        r=seeded.alpha.roles["route_manager"],
    )
    nombres = {f.name for f in filas}
    assert len(nombres) == 9 and "users.delete" not in nombres


async def test_el_manager_no_alcanza_candidatos_de_supervisor(seeded, alpha_client):
    """La otra API con `users.read` exige además `route.vehicles.read`."""
    await _organigrama(alpha_client, seeded, perfiles=False)
    await _como(alpha_client, seeded, "ceo")
    assert (await alpha_client.get("/api/supervisors/candidates")).status_code == 403
