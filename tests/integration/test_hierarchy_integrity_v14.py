"""Jerarquía V1.4: integridad, retiro ascendente y sustitución de responsables.

Organigrama de partida (`test_org_hierarchy.ORGANIGRAMA`):

    CEO ─┬─ COO ─┬─ RM-A ─┬─ OSM-A
         │       │        └─ SUP-A
         │       └─ SUP-C
         ├─ RM-B ── SUP-B
         └─ Sales-A

Lo que se comprueba:

* **H-1**: el contrato general (`/api/users`) no puede desincronizar rol y
  cargo, por ninguna vía (alta, edición, superior, readmisión); 409 sin
  cambios, y lo que no toca la jerarquía sigue funcionando.
* **H-3**: un superior suspendido no se ofrece.
* **H-4**: un único CEO vigente por compañía, también en concurrencia y en la
  base.
* **Retirar responsable**: los directos suben al superior inmediato; los
  indirectos no se mueven; quien sale deja la compañía.
* **Sustituir responsable**: CEO (con Sales), COO y RM; un sucesor de la
  propia rama; todos los rechazos; auditoría correlacionada.
* Todo o nada (fallo inyectado), dos operaciones a la vez, D-3 por
  `started_at`, suspensión sin efectos y nombres fijos de los roles de Route.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from tests.integration.conftest import TEST_PASSWORD
from tests.integration.test_org_hierarchy import (
    ORG,
    _como,
    _ejecutar,
    _filas,
    _hoy,
    _iniciada,
    _informe,
    _organigrama,
    _persona,
    _retrofechar,
    _trasladar_en,
    _vigente,
)
from tests.integration.test_reports import _jornada

pytestmark = pytest.mark.integration


# ── Ayudas ──────────────────────────────────────────────────────────────────


def _id(seeded, clave: str) -> int:
    return seeded.alpha.users[clave].id


async def _foto(seeded) -> list[tuple]:
    """Estado completo de la jerarquía y de los roles del tenant alfa."""
    asignaciones = await _filas(
        "SELECT user_id, position, superior_user_id, valid_from, valid_to, version "
        "FROM org_assignment WHERE company_id = :c ORDER BY id", c=seeded.alpha.id,
    )
    roles = await _filas(
        "SELECT user_id, role_id, is_active, deleted_at FROM user_company "
        "WHERE company_id = :c ORDER BY user_id", c=seeded.alpha.id,
    )
    return [tuple(f) for f in asignaciones] + [tuple(f) for f in roles]


async def _rol(seeded, clave: str) -> str | None:
    f = await _filas(
        "SELECT r.name FROM user_company uc JOIN role r ON r.id = uc.role_id "
        "WHERE uc.user_id = :u AND uc.company_id = :c AND uc.deleted_at IS NULL",
        u=_id(seeded, clave), c=seeded.alpha.id,
    )
    return f[0].name if f else None


async def _retirar(cliente, seeded, clave, *, actor="route_admin", **cuerpo):
    await cliente.login(seeded.alpha.users[actor].email)
    return await cliente.post(f"{ORG}/{_id(seeded, clave)}/retire", json=cuerpo)


async def _sustituir(cliente, seeded, clave, sucesor_id, *, actor="route_admin", **cuerpo):
    await cliente.login(seeded.alpha.users[actor].email)
    return await cliente.post(
        f"{ORG}/{_id(seeded, clave)}/replace", json={"successor_user_id": sucesor_id, **cuerpo}
    )


# ── H-1: el contrato general no toca la jerarquía ───────────────────────────


@pytest.mark.parametrize("actor", ["owner", "admin", "route_admin"])
async def test_el_contrato_general_no_cambia_el_rol_de_un_jefe(seeded, alpha_client, actor):
    """Lo que pasó el 14-10: un COO con equipo pasado a Supervisor por la
    pantalla general. Ahora 409, sin tocar ni la pertenencia ni el cargo."""
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    await alpha_client.login(seeded.alpha.users[actor].email)
    r = await alpha_client.put(f"/api/users/{_id(seeded, 'coo')}", json={"role_id": seeded.alpha.roles["supervisor"]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "managed_in_cer_route"
    assert "CER Route → Users" in r.json()["detail"]["message"]
    assert await _foto(seeded) == antes


async def test_el_contrato_general_sigue_editando_lo_que_no_es_jerarquia(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["owner"].email)
    # Datos personales de un jefe, con su mismo rol (la pantalla lo reenvía).
    r = await alpha_client.put(
        f"/api/users/{_id(seeded, 'coo')}",
        json={"first_name": "Renamed", "role_id": seeded.alpha.roles["COO"]},
    )
    assert r.status_code == 200, r.text
    assert (await _vigente(seeded, "coo")).position == "coo"
    # Un rol del núcleo a quien está fuera del árbol.
    r = await alpha_client.put(f"/api/users/{_id(seeded, 'viewer')}", json={"role_id": seeded.alpha.roles["manager"]})
    assert r.status_code == 200, r.text
    # Suspender y restaurar no cambian la jerarquía.
    for activo in (False, True):
        r = await alpha_client.put(f"/api/users/{_id(seeded, 'rm_a')}/access", json={"is_active": activo})
        assert r.status_code == 200, r.text
    assert (await _vigente(seeded, "rm_a")).superior_user_id == _id(seeded, "coo")


async def test_el_contrato_general_no_mete_a_nadie_en_la_jerarquia(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["owner"].email)
    # Un rol de la jerarquía a quien no la tiene: quedaría con rol sin cargo.
    r = await alpha_client.put(f"/api/users/{_id(seeded, 'viewer')}", json={"role_id": seeded.alpha.roles["supervisor"]})
    assert r.status_code == 409
    assert await _rol(seeded, "viewer") == "viewer"
    # Superior por el contrato general.
    r = await alpha_client.put(f"/api/users/{_id(seeded, 'sup_c')}", json={"superior_user_id": _id(seeded, "rm_a")})
    assert r.status_code == 409
    assert (await _vigente(seeded, "sup_c")).superior_user_id == _id(seeded, "coo")
    # Alta con un rol de la jerarquía, con o sin superior: no se crea nada.
    for extra in ({}, {"superior_user_id": _id(seeded, "ceo")}):
        r = await alpha_client.post("/api/users", json={
            "username": "alpha_gen", "email": "gen@alpha.example.com", "first_name": "G",
            "last_name": "N", "password": TEST_PASSWORD, "role_id": seeded.alpha.roles["COO"], **extra,
        })
        assert r.status_code == 409, r.text
    assert await _filas('SELECT 1 FROM "user" WHERE username = :u', u="alpha_gen") == []


async def test_readmitir_con_rol_de_jerarquia_exige_cer_route_y_superior(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    sup_b = _id(seeded, "sup_b")
    assert (await alpha_client.delete(f"/api/route/users/{sup_b}")).status_code == 204
    # Por el contrato general: 409.
    await alpha_client.login(seeded.alpha.users["owner"].email)
    r = await alpha_client.post(f"/api/users/{sup_b}/reenrollment", json={"role_id": seeded.alpha.roles["supervisor"]})
    assert r.status_code == 409
    # Por CER Route sin superior: 422 y sigue fuera.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.post(f"/api/route/users/{sup_b}/reenrollment", json={"role_id": seeded.alpha.roles["supervisor"]})
    assert r.status_code == 422, r.text
    assert await _rol(seeded, "sup_b") is None
    # Con superior: vuelve con su cargo.
    r = await alpha_client.post(
        f"/api/route/users/{sup_b}/reenrollment",
        json={"role_id": seeded.alpha.roles["supervisor"], "superior_user_id": _id(seeded, "rm_b")},
    )
    assert r.status_code == 200, r.text
    vigente = await _vigente(seeded, "sup_b")
    assert (vigente.position, vigente.superior_user_id) == ("supervisor", _id(seeded, "rm_b"))


# ── H-3: candidatos realmente elegibles ─────────────────────────────────────


async def test_un_superior_suspendido_no_se_ofrece(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(f"/api/route/users/{_id(seeded, 'coo')}/access", json={"is_active": False})
    o = (await alpha_client.get(f"{ORG}/options")).json()
    ofrecidos = {s["user_id"] for s in o["superiors"]}
    assert _id(seeded, "coo") not in ofrecidos
    assert _id(seeded, "ceo") in ofrecidos
    # La estructura del suspendido sigue intacta.
    assert (await _vigente(seeded, "rm_a")).superior_user_id == _id(seeded, "coo")


# ── H-4: un único CEO ───────────────────────────────────────────────────────


async def test_un_segundo_ceo_se_rechaza_por_api_y_en_la_base(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.post("/api/route/users", json={
        "username": "alpha_ceo2", "email": "ceo2@alpha.example.com", "first_name": "C",
        "last_name": "Dos", "password": TEST_PASSWORD, "role_id": seeded.alpha.roles["CEO"],
    })
    assert r.status_code == 409, r.text
    assert await _filas('SELECT 1 FROM "user" WHERE username = :u', u="alpha_ceo2") == []
    # Y aunque alguien escribiera directamente en la base.
    with pytest.raises(IntegrityError):
        await _ejecutar(
            "INSERT INTO org_assignment (company_id, user_id, position, valid_from, version) "
            "VALUES (:c, :u, 'ceo', now(), 1)",
            c=seeded.alpha.id, u=_id(seeded, "viewer"),
        )


async def test_dos_altas_de_ceo_simultaneas_una_gana(seeded, beta_client):
    """Compañía sin CEO (aprovisionamiento): dos altas a la vez, queda una."""
    await _ejecutar("DELETE FROM org_assignment WHERE company_id = :c", c=seeded.beta.id)
    await beta_client.login(seeded.beta.users["route_admin"].email)

    def _alta(n):
        return beta_client.post("/api/route/users", json={
            "username": f"beta_ceo_{n}", "email": f"ceo{n}@beta.example.com", "first_name": "C",
            "last_name": str(n), "password": TEST_PASSWORD, "role_id": seeded.beta.roles["CEO"],
        })

    a, b = await asyncio.gather(_alta(1), _alta(2), return_exceptions=True)
    codigos = sorted(r.status_code for r in (a, b) if not isinstance(r, BaseException))
    assert codigos.count(200) == 1, codigos
    n = await _filas(
        "SELECT count(*) AS n FROM org_assignment WHERE company_id = :c AND position = 'ceo' AND valid_to IS NULL",
        c=seeded.beta.id,
    )
    assert n[0].n == 1


# ── Retirar responsable ─────────────────────────────────────────────────────


async def test_retirar_coo_sube_sus_directos_al_ceo_y_conserva_los_indirectos(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    vista = await _retirar(alpha_client, seeded, "coo", dry_run=True)
    assert vista.status_code == 200, vista.text
    assert vista.json()["applied"] is False
    assert await _foto(seeded) == antes, "la vista previa no escribe"
    previstos = {(m["user_id"], m["to_user_id"]) for m in vista.json()["moves"]}

    r = await _retirar(alpha_client, seeded, "coo", reason="left the company")
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["applied"] is True and hecho["operation_id"]
    assert {(m["user_id"], m["to_user_id"]) for m in hecho["moves"]} == previstos
    ceo = _id(seeded, "ceo")
    assert previstos == {(_id(seeded, "rm_a"), ceo), (_id(seeded, "sup_c"), ceo)}
    # Directos, al CEO; indirectos, donde estaban.
    assert (await _vigente(seeded, "rm_a")).superior_user_id == ceo
    assert (await _vigente(seeded, "sup_c")).superior_user_id == ceo
    assert (await _vigente(seeded, "osm_a")).superior_user_id == _id(seeded, "rm_a")
    assert (await _vigente(seeded, "sup_a")).superior_user_id == _id(seeded, "rm_a")
    # Quien sale: sin cargo y fuera de la compañía, sin rol inventado.
    assert await _vigente(seeded, "coo") is None
    assert await _rol(seeded, "coo") is None
    # Periodos contiguos en un mismo instante T.
    t = await _filas(
        "SELECT DISTINCT valid_to FROM org_assignment WHERE user_id IN (:a, :b, :c) AND valid_to IS NOT NULL",
        a=_id(seeded, "coo"), b=_id(seeded, "rm_a"), c=_id(seeded, "sup_c"),
    )
    assert len(t) == 1
    # Auditoría correlacionada.
    eventos = await _filas(
        "SELECT entity_type, action FROM audit_event WHERE changes -> 'operation_id' ->> 'new' = :o",
        o=hecho["operation_id"],
    )
    tipos = {(e.entity_type, e.action) for e in eventos}
    assert ("org_succession", "retire") in tipos
    assert ("org_assignment", "unassign") in tipos
    assert ("user", "delete") in tipos
    assert sum(1 for e in eventos if e.action == "reassign") == 2


@pytest.mark.parametrize(
    ("clave", "esperados"),
    [("rm_a", {"osm_a": "coo", "sup_a": "coo"}), ("rm_b", {"sup_b": "ceo"})],
)
async def test_retirar_rm_sube_su_equipo_al_superior_inmediato(seeded, alpha_client, clave, esperados):
    await _organigrama(alpha_client, seeded, perfiles=False)
    r = await _retirar(alpha_client, seeded, clave)
    assert r.status_code == 200, r.text
    for persona, jefe in esperados.items():
        assert (await _vigente(seeded, persona)).superior_user_id == _id(seeded, jefe)
    assert (await _vigente(seeded, "sales_a")).superior_user_id == _id(seeded, "ceo"), "Sales no se mueve"


async def test_un_ceo_con_equipo_no_se_retira_sin_sucesor(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    r = await _retirar(alpha_client, seeded, "ceo")
    assert r.status_code == 409
    assert "Replace manager" in r.json()["detail"]
    assert await _foto(seeded) == antes


async def test_retirar_bajo_un_superior_suspendido_no_cambia_nada(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(f"/api/route/users/{_id(seeded, 'coo')}/access", json={"is_active": False})
    antes = await _foto(seeded)
    r = await _retirar(alpha_client, seeded, "rm_a")
    assert r.status_code == 409
    assert "suspended" in r.json()["detail"]
    assert await _foto(seeded) == antes


# ── Sustituir responsable ───────────────────────────────────────────────────


async def test_sustituir_ceo_mueve_todo_incluido_sales_y_queda_un_solo_ceo(seeded, alpha_client):
    await _organigrama(alpha_client, seeded)
    nuevo = await _persona(alpha_client, seeded, "ceo_nuevo", "supervisor", "rm_b")
    r = await _sustituir(alpha_client, seeded, "ceo", nuevo.id, reason="succession")
    assert r.status_code == 200, r.text
    assert (await _vigente(seeded, "ceo_nuevo")).position == "ceo"
    assert (await _vigente(seeded, "ceo_nuevo")).superior_user_id is None
    assert await _rol(seeded, "ceo_nuevo") == "CEO"
    for directo in ("coo", "rm_b", "sales_a"):
        assert (await _vigente(seeded, directo)).superior_user_id == nuevo.id
    assert (await _vigente(seeded, "rm_a")).superior_user_id == _id(seeded, "coo"), "indirecto intacto"
    assert await _rol(seeded, "ceo") is None
    n = await _filas(
        "SELECT count(*) AS n FROM org_assignment WHERE company_id = :c AND position = 'ceo' AND valid_to IS NULL",
        c=seeded.alpha.id,
    )
    assert n[0].n == 1
    # El nuevo CEO ve a Sales; el COO, no (tampoco por id).
    assert _id(seeded, "sales_a") in await _hoy(alpha_client, seeded, "ceo_nuevo")
    assert _id(seeded, "sales_a") not in await _hoy(alpha_client, seeded, "coo")
    await _como(alpha_client, seeded, "coo")
    r = await alpha_client.get("/api/activity-explorer", params={"range": "week", "supervisor_user_id": _id(seeded, "sales_a")})
    assert r.status_code == 404


async def test_sustituir_coo_por_un_rm_de_otra_rama(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    r = await _sustituir(alpha_client, seeded, "coo", _id(seeded, "rm_b"))
    assert r.status_code == 200, r.text
    rm_b = _id(seeded, "rm_b")
    vigente = await _vigente(seeded, "rm_b")
    assert (vigente.position, vigente.superior_user_id) == ("coo", _id(seeded, "ceo"))
    assert await _rol(seeded, "rm_b") == "COO"
    assert (await _vigente(seeded, "rm_a")).superior_user_id == rm_b
    assert (await _vigente(seeded, "sup_c")).superior_user_id == rm_b
    assert (await _vigente(seeded, "sup_b")).superior_user_id == rm_b, "su propia rama sigue con él"
    assert _id(seeded, "sales_a") not in await _hoy(alpha_client, seeded, "rm_b")


async def test_sustituir_rm_por_alguien_de_su_propio_equipo(seeded, alpha_client):
    """Promoción desde la rama del saliente: SUP-A pasa a RM y recibe a OSM-A."""
    await _organigrama(alpha_client, seeded, perfiles=False)
    r = await _sustituir(alpha_client, seeded, "rm_a", _id(seeded, "sup_a"))
    assert r.status_code == 200, r.text
    vigente = await _vigente(seeded, "sup_a")
    assert (vigente.position, vigente.superior_user_id) == ("regional_manager", _id(seeded, "coo"))
    assert await _rol(seeded, "sup_a") == "Regional Manager"
    assert (await _vigente(seeded, "osm_a")).superior_user_id == _id(seeded, "sup_a")


@pytest.mark.parametrize(
    ("saliente", "sucesor", "codigo"),
    [
        ("coo", "ceo", 409),          # el sucesor está por encima
        ("coo", "coo", 409),          # a sí mismo
        ("sup_a", "sup_b", 409),      # un Supervisor no se sustituye
        ("coo", "route_admin", 409),  # fuera del árbol
        ("coo", "viewer", 409),       # rol del núcleo
    ],
)
async def test_sustituciones_invalidas_no_cambian_nada(seeded, alpha_client, saliente, sucesor, codigo):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    r = await _sustituir(alpha_client, seeded, saliente, _id(seeded, sucesor))
    assert r.status_code == codigo, r.text
    assert await _foto(seeded) == antes


async def test_sucesor_suspendido_o_de_otro_tenant(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(f"/api/route/users/{_id(seeded, 'rm_b')}/access", json={"is_active": False})
    antes = await _foto(seeded)
    assert (await _sustituir(alpha_client, seeded, "coo", _id(seeded, "rm_b"))).status_code == 409
    assert (await _sustituir(alpha_client, seeded, "coo", seeded.beta.users["supervisor"].id)).status_code == 404
    assert await _foto(seeded) == antes


@pytest.mark.parametrize("actor", ["owner", "admin", "ceo", "coo", "supervisor"])
async def test_solo_el_administrador_de_route_retira_o_sustituye(seeded, alpha_client, actor):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    r1 = await _retirar(alpha_client, seeded, "rm_b", actor=actor)
    r2 = await _sustituir(alpha_client, seeded, "rm_b", _id(seeded, "sup_b"), actor=actor)
    assert r1.status_code == 403 and r2.status_code == 403
    await alpha_client.login(seeded.alpha.users[actor].email)
    assert (await alpha_client.get(f"{ORG}/{_id(seeded, 'rm_b')}/succession")).status_code == 403
    assert await _foto(seeded) == antes


async def test_otro_tenant_responde_404(seeded, alpha_client, beta_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await beta_client.login(seeded.beta.users["route_admin"].email)
    r = await beta_client.post(f"{ORG}/{_id(seeded, 'coo')}/retire", json={})
    assert r.status_code == 404
    r = await beta_client.get(f"{ORG}/{_id(seeded, 'coo')}/succession")
    assert r.status_code == 404


async def test_la_vista_de_continuidad_ofrece_solo_sucesores_validos(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.get(f"{ORG}/{_id(seeded, 'coo')}/succession")
    assert r.status_code == 200, r.text
    info = r.json()
    ofrecidos = {c["user_id"] for c in info["successor_candidates"]}
    assert _id(seeded, "ceo") not in ofrecidos and _id(seeded, "coo") not in ofrecidos
    assert _id(seeded, "rm_b") in ofrecidos and _id(seeded, "rm_a") in ofrecidos
    assert _id(seeded, "route_admin") not in ofrecidos
    assert {d["user_id"] for d in info["direct_reports"]} == {_id(seeded, "rm_a"), _id(seeded, "sup_c")}
    assert info["retire_preview"]["moves"]
    # Del CEO: sustituible, no retirable.
    info = (await alpha_client.get(f"{ORG}/{_id(seeded, 'ceo')}/succession")).json()
    assert info["can_replace"] is True and info["retire_preview"] is None
    assert "Replace manager" in info["retire_blocked_reason"]


# ── Todo o nada y concurrencia ──────────────────────────────────────────────


async def test_un_fallo_a_mitad_no_deja_nada_a_medias(seeded, alpha_client, monkeypatch):
    """Se fuerza un fallo después de mover a los subordinados y de cambiar el
    rol del sucesor: la transacción entera se deshace."""
    from app.routers_api.usermanagement.dao import UserManagementDAO

    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)

    async def _falla(*args, **kwargs):
        raise RuntimeError("fallo inyectado")

    monkeypatch.setattr(UserManagementDAO, "delete_membership", _falla)
    try:
        r = await _sustituir(alpha_client, seeded, "coo", _id(seeded, "rm_b"))
        assert r.status_code == 500
    except RuntimeError:
        pass  # según el transporte, la excepción llega tal cual
    assert await _foto(seeded) == antes
    eventos = await _filas("SELECT 1 FROM audit_event WHERE entity_type = 'org_succession'")
    assert eventos == []


async def test_dos_sustituciones_simultaneas_una_gana(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    coo = _id(seeded, "coo")
    a, b = await asyncio.gather(
        alpha_client.post(f"{ORG}/{coo}/replace", json={"successor_user_id": _id(seeded, "rm_b")}),
        alpha_client.post(f"{ORG}/{coo}/replace", json={"successor_user_id": _id(seeded, "sup_c")}),
        return_exceptions=True,
    )
    codigos = sorted(r.status_code for r in (a, b) if not isinstance(r, BaseException))
    assert codigos.count(200) == 1, codigos
    coos = await _filas(
        "SELECT count(*) AS n FROM org_assignment WHERE company_id = :c AND position = 'coo' AND valid_to IS NULL",
        c=seeded.alpha.id,
    )
    assert coos[0].n == 1


async def test_version_obsoleta_responde_409(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    r = await _retirar(alpha_client, seeded, "rm_b", version=99)
    assert r.status_code == 409
    assert await _foto(seeded) == antes


# ── V1.5: la historia sigue al puesto ───────────────────────────────────────


async def test_el_sucesor_hereda_el_historial_de_su_puesto(seeded, alpha_client):
    """«Replace manager»: el COO nuevo ve lo que veía su antecesor, también lo
    anterior al relevo. Las jornadas no se mueven ni se recrean."""
    await _organigrama(alpha_client, seeded)
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    antes = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="10.0", usuario="sup_c")
    despues = await _jornada(alpha_client, seeded, dia=date(2026, 9, 17), millas="5.0", usuario="sup_c")

    r = await _sustituir(alpha_client, seeded, "coo", _id(seeded, "rm_b"))
    assert r.status_code == 200, r.text
    t = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
    for clave in ("sup_c", "rm_b", "rm_a"):
        await _trasladar_en(_id(seeded, clave), t)
    await _iniciada(antes["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    await _iniciada(despues["jornada"]["id"], datetime(2026, 9, 17, 13, tzinfo=timezone.utc))

    informe = await _informe(alpha_client, seeded, "rm_b", supervisor_user_id=_id(seeded, "sup_c"))
    assert informe["summary"]["official_miles"] == "15.0", "lo de antes y lo de después del relevo"
    relevo = await _filas(
        "SELECT replaces_user_id FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
        u=_id(seeded, "rm_b"),
    )
    assert relevo[0].replaces_user_id == _id(seeded, "coo")
    sesiones = await _filas("SELECT count(*) AS n FROM work_session WHERE user_id = :u", u=_id(seeded, "sup_c"))
    assert sesiones[0].n == 2, "las jornadas no se recrean ni se mueven"


async def test_carga_inicial_el_primer_jefe_ve_el_pasado(seeded, alpha_client):
    """Quien entra por primera vez en la jerarquía trae su historia: antes no
    era de nadie. Sin retrofechar ninguna asignación."""
    await _organigrama(alpha_client, seeded)
    previa = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="8.0", usuario="sup_b")
    await _iniciada(previa["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    informe = await _informe(alpha_client, seeded, "rm_b", supervisor_user_id=_id(seeded, "sup_b"))
    assert informe["summary"]["official_miles"] == "8.0"


async def test_el_traslado_lateral_sigue_por_periodo(seeded, alpha_client):
    """Un supervisor de RM-A (Texas) a RM-B (Georgia): cada RM ve su tramo y
    RM-B no ve la zona de RM-A. El CEO, encima de los dos, lo ve entero."""
    await _organigrama(alpha_client, seeded)
    await _retrofechar(seeded.alpha.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
    antes = await _jornada(alpha_client, seeded, dia=date(2026, 9, 14), millas="10.0", usuario="sup_a")
    despues = await _jornada(alpha_client, seeded, dia=date(2026, 9, 17), millas="5.0", usuario="sup_a")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.put(
        f"/api/route/users/{_id(seeded, 'sup_a')}", json={"superior_user_id": _id(seeded, "rm_b")}
    )
    assert r.status_code == 200, r.text
    await _trasladar_en(_id(seeded, "sup_a"), datetime(2026, 9, 16, 3, tzinfo=timezone.utc))
    await _iniciada(antes["jornada"]["id"], datetime(2026, 9, 14, 13, tzinfo=timezone.utc))
    await _iniciada(despues["jornada"]["id"], datetime(2026, 9, 17, 13, tzinfo=timezone.utc))
    u = _id(seeded, "sup_a")
    assert (await _informe(alpha_client, seeded, "rm_a", supervisor_user_id=u))["summary"]["official_miles"] == "10.0"
    assert (await _informe(alpha_client, seeded, "rm_b", supervisor_user_id=u))["summary"]["official_miles"] == "5.0"
    assert (await _informe(alpha_client, seeded, "ceo", supervisor_user_id=u))["summary"]["official_miles"] == "15.0"


# ── V1.5: CEO y COO sólo por «Replace manager» ──────────────────────────────


async def test_ceo_y_coo_no_se_editan_con_la_lista_de_roles(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    antes = await _foto(seeded)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    casos = [
        # El COO baja a RM, o cambia de superior.
        (_id(seeded, "coo"), {"role_id": seeded.alpha.roles["Regional Manager"],
                              "superior_user_id": _id(seeded, "ceo")}),
        (_id(seeded, "coo"), {"superior_user_id": _id(seeded, "rm_b")}),
        # El CEO baja a COO.
        (_id(seeded, "ceo"), {"role_id": seeded.alpha.roles["COO"]}),
        # Un RM sube a COO por la lista.
        (_id(seeded, "rm_b"), {"role_id": seeded.alpha.roles["COO"],
                               "superior_user_id": _id(seeded, "ceo")}),
    ]
    for user_id, cuerpo in casos:
        r = await alpha_client.put(f"/api/route/users/{user_id}", json=cuerpo)
        assert r.status_code == 409, (cuerpo, r.text)
        assert r.json()["detail"]["code"] == "use_replace_manager"
    # Por la API de organización, igual.
    r = await alpha_client.put(f"{ORG}/{_id(seeded, 'coo')}", json={
        "position": "regional_manager", "superior_user_id": _id(seeded, "ceo")})
    assert r.status_code == 409
    assert (await alpha_client.delete(f"{ORG}/{_id(seeded, 'coo')}")).status_code == 409
    assert await _foto(seeded) == antes


async def test_lo_demas_de_un_coo_se_sigue_editando_y_se_crean_coo_nuevos(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    # Mismo rol y mismo superior, con otro nombre: no es un cambio de puesto.
    r = await alpha_client.put(f"/api/route/users/{_id(seeded, 'coo')}", json={
        "first_name": "Renamed", "role_id": seeded.alpha.roles["COO"],
        "superior_user_id": _id(seeded, "ceo")})
    assert r.status_code == 200, r.text
    # Un COO nuevo (otro puesto, no un relevo) se crea en el alta.
    await _persona(alpha_client, seeded, "coo_2", "COO", "ceo")
    assert (await _vigente(seeded, "coo_2")).position == "coo"
    # RM, Supervisor, OSM y Sales siguen con la lista, como antes.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    r = await alpha_client.put(f"/api/route/users/{_id(seeded, 'sup_c')}", json={
        "role_id": seeded.alpha.roles["OSM"], "superior_user_id": _id(seeded, "coo")})
    assert r.status_code == 200, r.text


# ── Suspensión: ausencia temporal, sin efectos en la estructura ─────────────


async def test_suspender_y_reactivar_al_ceo_no_toca_la_jerarquia(seeded, alpha_client):
    await _organigrama(alpha_client, seeded, perfiles=False)
    asignaciones = await _filas("SELECT * FROM org_assignment WHERE company_id = :c ORDER BY id", c=seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    ceo = _id(seeded, "ceo")
    assert (await alpha_client.put(f"/api/route/users/{ceo}/access", json={"is_active": False})).status_code == 200
    # Nadie hereda: el COO sigue viendo sólo su rama, sin Sales.
    assert _id(seeded, "sales_a") not in await _hoy(alpha_client, seeded, "coo")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.put(f"/api/route/users/{ceo}/access", json={"is_active": True})).status_code == 200
    assert await _filas("SELECT * FROM org_assignment WHERE company_id = :c ORDER BY id", c=seeded.alpha.id) == asignaciones


# ── Los roles de Route conservan su nombre ──────────────────────────────────


@pytest.mark.parametrize("rol", ["COO", "CEO", "Sales", "supervisor", "route_admin"])
async def test_los_roles_de_route_no_se_renombran_ni_se_borran(seeded, alpha_client, rol):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    role_id = seeded.alpha.roles[rol]
    r = await alpha_client.put(f"/api/roles/{role_id}", json={"name": f"{rol} renamed"})
    assert r.status_code == 409, r.text
    assert (await alpha_client.delete(f"/api/roles/{role_id}")).status_code == 409
    nombre = await _filas("SELECT name, is_active FROM role WHERE id = :r", r=role_id)
    assert (nombre[0].name, nombre[0].is_active) == (rol, True)
    # La descripción sí.
    r = await alpha_client.put(f"/api/roles/{role_id}", json={"description": "edited"})
    assert r.status_code == 200, r.text


async def test_un_rol_del_nucleo_se_sigue_renombrando(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    r = await alpha_client.put(f"/api/roles/{seeded.alpha.roles['viewer']}", json={"name": "reader"})
    assert r.status_code == 200, r.text
