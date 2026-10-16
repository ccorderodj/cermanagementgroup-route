"""
RTE08 personal: la actividad propia del supervisor (`GET /api/activity-explorer/me`).

Qué se defiende
---------------
* El sujeto es **siempre** el usuario de la sesión, en el tenant del
  subdominio. Ningún parámetro lo cambia: `supervisor_user_id`, `user_id` y
  `company_id` se ignoran, y la respuesta es la misma que sin ellos.
* La capacidad es la de ejecutar la jornada (`route.worksession.execute`), no
  la de explorar la compañía (`route.activity.read`): el supervisor entra a lo
  suyo y sigue sin entrar al explorador de administración.
* Paridad: para la misma persona y periodo, `/me` devuelve exactamente lo que
  el explorador de administración devuelve al elegirla, salvo el directorio de
  supervisores, que `/me` no tiene.
* Sólo lectura: consultar no crea ni cambia nada.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from tests.integration.test_activity_explorer import (
    RUTA as RUTA_ADMIN,
    _fechar_jornada,
    _jornada_con_parada,
    _perfil_y_vehiculo,
    _viaje_a_casa,
)
from tests.integration.test_reports import _jornada, _millas

pytestmark = pytest.mark.integration

RUTA = "/api/activity-explorer/me"
DIA = date(2026, 9, 16)
#: Los campos que dependen de quién mira, no de los datos.
DIRECTORIO = ("supervisors",)


async def _yo(cliente, **parametros) -> dict:
    r = await cliente.get(RUTA, params=parametros)
    assert r.status_code == 200, r.text
    return r.json()


async def _admin(cliente, seeded, user_id: int, **parametros) -> dict:
    await cliente.login(seeded.alpha.users["route_admin"].email)
    r = await cliente.get(RUTA_ADMIN, params={**parametros, "supervisor_user_id": user_id})
    assert r.status_code == 200, r.text
    return r.json()


def _sin_directorio(vista: dict) -> dict:
    return {k: v for k, v in vista.items() if k not in DIRECTORIO}


async def _dos_supervisores(alpha_client, seeded) -> None:
    """El supervisor: visita el 16 (10 mi) y regreso a casa sin actividad (4 mi);
    otra jornada el mismo día con una oficina (3 mi); y una visita el 15.
    El route_admin, que también hace campo: una visita el 16 (7 mi)."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-R8-A")
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-R8-B", usuario="route_admin")

    hecho = await _jornada_con_parada(alpha_client, seeded, cerrar_jornada=False)
    await _millas(hecho["viaje"]["id"], "10.0")
    await _viaje_a_casa(alpha_client, seeded, hecho["jornada"]["id"], "6437.376")
    await _fechar_jornada(hecho["jornada"]["id"], DIA)
    async with async_session_maker() as s:
        await s.execute(
            text("UPDATE work_session SET status = 'ended', ended_at = now() WHERE id = :i"),
            {"i": hecho["jornada"]["id"]},
        )
        await s.commit()

    await _jornada(alpha_client, seeded, dia=DIA, millas="3.0", proposito="office")
    await _jornada(alpha_client, seeded, dia=date(2026, 9, 15), millas="5.0")
    await _jornada(alpha_client, seeded, dia=DIA, millas="7.0", usuario="route_admin")


# ── Sujeto y aislamiento ────────────────────────────────────────────────────


async def test_el_supervisor_ve_solo_lo_suyo(seeded, alpha_client):
    await _dos_supervisores(alpha_client, seeded)
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    vista = await _yo(alpha_client, range="day", date=DIA.isoformat())

    assert vista["supervisor_user_id"] == seeded.alpha.users["supervisor"].id
    assert vista["supervisors"] == [], "sin directorio de otros supervisores"
    assert vista["summary"]["official_miles"] == "17.0"  # 10 + 4 + 3; no los 7 del otro
    referencias = {a["purpose"] for a in vista["activities"]}
    assert referencias == {"client_visit", "home", "office"}


@pytest.mark.parametrize(
    "manipulado",
    ["supervisor_user_id", "user_id", "company_id", "tenant_id"],
)
async def test_un_parametro_de_otra_persona_se_ignora(seeded, alpha_client, manipulado):
    await _dos_supervisores(alpha_client, seeded)
    ajeno = {
        "supervisor_user_id": seeded.alpha.users["route_admin"].id,
        "user_id": seeded.alpha.users["route_admin"].id,
        "company_id": seeded.beta.id,
        "tenant_id": seeded.beta.id,
    }[manipulado]

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    limpio = await _yo(alpha_client, range="day", date=DIA.isoformat())
    sucio = await _yo(alpha_client, range="day", date=DIA.isoformat(), **{manipulado: ajeno})
    assert sucio == limpio
    assert sucio["supervisor_user_id"] == seeded.alpha.users["supervisor"].id


async def test_el_administrador_en_su_ruta_personal_ve_solo_lo_suyo(seeded, alpha_client):
    """Ni siquiera quien puede explorar la compañía la explora desde `/me`."""
    await _dos_supervisores(alpha_client, seeded)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    propio = await _yo(
        alpha_client, range="day", date=DIA.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert propio["supervisor_user_id"] == seeded.alpha.users["route_admin"].id
    assert propio["summary"]["official_miles"] == "7.0"
    assert propio["supervisors"] == []

    # Su ruta de administración sigue con su alcance administrativo.
    otro = await _admin(alpha_client, seeded, seeded.alpha.users["supervisor"].id,
                        range="day", date=DIA.isoformat())
    assert otro["summary"]["official_miles"] == "17.0"
    assert len(otro["supervisors"]) == 2


async def test_otro_tenant_no_ve_nada_de_este(seeded, alpha_client, beta_client):
    await _dos_supervisores(alpha_client, seeded)
    await beta_client.login(seeded.beta.users["supervisor"].email)
    vista = await _yo(beta_client, range="year", date=DIA.isoformat())
    assert vista["supervisor_user_id"] == seeded.beta.users["supervisor"].id
    assert vista["groups"] == []
    # Y una cuenta de alpha, en un cliente limpio de beta, no entra: sin sesión
    # en beta no hay `/me` que leer.
    from tests.integration.conftest import TenantClient

    async with TenantClient("beta") as limpio:
        acceso = await limpio.login(seeded.alpha.users["supervisor"].email)
        assert acceso.status_code != 200, acceso.text
        r = await limpio.get(RUTA, params={"range": "day"})
        assert r.status_code in (401, 403)
        assert str(seeded.alpha.users["supervisor"].id) not in r.text


# ── Capacidades ─────────────────────────────────────────────────────────────


async def test_el_supervisor_entra_a_lo_suyo_y_no_al_explorador(seeded, alpha_client):
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-R8-C")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (await alpha_client.get(RUTA, params={"range": "day"})).status_code == 200
    assert (await alpha_client.get(RUTA_ADMIN, params={"range": "day"})).status_code == 403


async def test_sin_sesion_y_sin_capacidad_de_ejecucion(seeded, alpha_anonymous, alpha_client):
    assert (await alpha_anonymous.get(RUTA, params={"range": "day"})).status_code == 401
    # `viewer` no ejecuta jornadas: no tiene actividad propia que consultar aquí.
    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (await alpha_client.get(RUTA, params={"range": "day"})).status_code == 403


async def test_las_capacidades_no_cambiaron(seeded):
    """RTE08 personal no concede `route.activity.read` al supervisor."""
    from app.core.rbac.catalog import DEFAULT_ROLES

    supervisor = next(r for r in DEFAULT_ROLES if r.name == "supervisor")
    assert "route.activity.read" not in supervisor.capabilities
    assert "route.worksession.execute" in supervisor.capabilities


# ── Paridad con el explorador de administración ────────────────────────────


@pytest.mark.parametrize("rango", ["day", "week", "month", "year"])
async def test_paridad_con_el_explorador_para_la_misma_persona(seeded, alpha_client, rango):
    """Varios días, dos jornadas el mismo día y un viaje sin actividad."""
    await _dos_supervisores(alpha_client, seeded)
    supervisor = seeded.alpha.users["supervisor"].id
    admin = await _admin(alpha_client, seeded, supervisor, range=rango, date=DIA.isoformat())
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    propio = await _yo(alpha_client, range=rango, date=DIA.isoformat())
    assert _sin_directorio(propio) == _sin_directorio(admin)


async def test_r1_el_viaje_sin_actividad_aparece_y_no_cuenta(seeded, alpha_client):
    await _dos_supervisores(alpha_client, seeded)
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    vista = await _yo(alpha_client, range="day", date=DIA.isoformat())
    casa = [a for a in vista["activities"] if a["purpose"] == "home"]
    assert len(casa) == 1 and casa[0]["has_activity"] is False
    assert vista["summary"]["activities"] == 2, "visita + oficina; no el regreso"


async def test_estados_reales_en_curso_y_millas_sin_resolver(seeded, alpha_client):
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-R8-E")
    abierta = await _jornada_con_parada(
        alpha_client, seeded, terminar=False, cerrar_jornada=False
    )
    await _fechar_jornada(abierta["jornada"]["id"], DIA)

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    vista = await _yo(alpha_client, range="day", date=DIA.isoformat())
    assert vista["summary"]["has_open_activity"] is True
    assert vista["summary"]["mileage_pending"] is True
    assert vista["summary"]["official_miles"] == "0.0", "lo pendiente no es una cifra"
    parada = vista["activities"][0]
    assert parada["ended_at"] is None and parada.get("outcome") in (None, "")


async def test_sin_jornadas_es_un_estado_vacio(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    for rango in ("day", "week", "month", "year"):
        vista = await _yo(alpha_client, range=rango, date=DIA.isoformat())
        assert vista["groups"] == [] and vista["activities"] == []


# ── Sólo lectura ────────────────────────────────────────────────────────────


async def test_consultar_no_cambia_nada(seeded, alpha_client):
    await _dos_supervisores(alpha_client, seeded)
    consulta = text(
        "SELECT (SELECT count(*) FROM work_session), (SELECT count(*) FROM trip), "
        "(SELECT count(*) FROM activity_execution), (SELECT count(*) FROM audit_event), "
        "(SELECT max(updated_at) FROM work_session)"
    )
    async with async_session_maker() as s:
        antes = (await s.execute(consulta)).one()
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    for rango in ("day", "week", "month", "year"):
        await _yo(alpha_client, range=rango, date=DIA.isoformat())
    async with async_session_maker() as s:
        despues = (await s.execute(consulta)).one()
    assert despues == antes
