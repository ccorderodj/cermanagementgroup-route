"""La puerta de permiso de ubicación, del lado del servidor (RTE10-A02).

Las dos mitades, y tiran en direcciones opuestas
------------------------------------------------
* **abrir trabajo nuevo** sin permiso concedido se rechaza. Si no, la puerta del
  navegador sería decorativa: bastaría una petición a mano para saltársela;
* **cerrar lo que ya está abierto** se permite siempre. Sin esa excepción,
  revocar el permiso a mitad de un viaje dejaría ese viaje y esa jornada
  abiertos para siempre — el supervisor atrapado y el registro mintiendo.

La mayoría de estos tests defienden la segunda, porque es la que un refuerzo
hecho con prisa se lleva por delante.

Lo que estos tests **no** pueden probar
----------------------------------------
Que el permiso declarado sea cierto. El servidor no ve el sistema operativo de
nadie, y fingir lo contrario sería peor que no comprobarlo. Lo que se prueba es
lo que sí se puede: que la afirmación se exige, que se audita, y que cerrar
nunca queda bloqueado.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.audit.models import AuditEvent
from app.database import async_session_maker
from app.routers_api.location.permission_gate import CABECERA

pytestmark = pytest.mark.integration

#: Un navegador cuyo permiso NO está concedido.
SIN_PERMISO = {CABECERA: "denied"}
EN_ESPERA = {CABECERA: "prompt"}

FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def _supervisor_listo(alpha_client, seeded, *, unidad="V-GATE"):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": unidad,
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    await alpha_client.login(seeded.alpha.users["supervisor"].email)


async def _jornada(alpha_client) -> dict:
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "100000.0"},
    )
    return jornada


async def _viaje_en_ruta(alpha_client) -> dict:
    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": "ABC Manufacturing"},
        )
    ).json()
    respuesta = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert respuesta.status_code == 200, respuesta.text
    return viaje


# ── Abrir trabajo nuevo exige permiso ───────────────────────────────────────


async def test_start_work_sin_permiso_se_rechaza(seeded, alpha_client):
    """La primera puerta: sin permiso no empieza la jornada."""
    await _supervisor_listo(alpha_client, seeded)

    respuesta = await alpha_client.post(
        "/api/worksessions", json={}, headers=SIN_PERMISO
    )

    assert respuesta.status_code == 403, respuesta.text
    assert "Location access is required" in respuesta.json()["detail"]


async def test_prompt_tampoco_abre_trabajo(seeded, alpha_client):
    """`prompt` no es `granted`.

    Es el estado de quien todavía no ha decidido, y §2.1 lo pone del lado
    bloqueado. Tratarlo como permiso sería operar sin que nadie haya dicho que
    sí.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-PROMPT")

    respuesta = await alpha_client.post("/api/worksessions", json={}, headers=EN_ESPERA)

    assert respuesta.status_code == 403, respuesta.text


async def test_sin_la_cabecera_tampoco(seeded, alpha_client):
    """Un cliente que no pasó por la puerta no entra por descuido.

    Ausencia no es permiso. Si la falta de cabecera dejara pasar, cualquier
    cliente viejo —o una petición a mano— se saltaría el checkpoint entero.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-NOHDR")

    respuesta = await alpha_client.post(
        "/api/worksessions", json={}, headers={CABECERA: ""}
    )

    assert respuesta.status_code == 403, respuesta.text


async def test_las_cuatro_transiciones_que_abren_estan_cerradas(seeded, alpha_client):
    """Las cinco de §14, no sólo la primera.

    Con la jornada ya abierta —y el permiso concedido para abrirla—, cada
    transición que abre trabajo nuevo se vuelve a comprobar por su cuenta. Que
    una esté protegida no protege a las demás.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-TODAS")
    await _jornada(alpha_client)

    planificado = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": "ABC Manufacturing"},
        )
    ).json()

    casos = [
        ("trip.plan", "/api/trips",
         {"purpose": "office", "context_reference": None}),
        ("trip.start", f"/api/trips/{planificado['id']}/start", {}),
        ("trip.change_plan", f"/api/trips/{planificado['id']}/change-plan",
         {"purpose": "office", "context_reference": None}),
        ("activity.start", f"/api/trips/{planificado['id']}/activity/start",
         {"activity_ids": []}),
    ]
    for nombre, ruta, cuerpo in casos:
        respuesta = await alpha_client.post(ruta, json=cuerpo, headers=SIN_PERMISO)
        assert respuesta.status_code == 403, (
            f"'{nombre}' abre trabajo nuevo y no está protegida: "
            f"{respuesta.status_code} {respuesta.text[:120]}"
        )


# ── Cerrar lo abierto nunca se bloquea ──────────────────────────────────────


async def test_un_viaje_en_ruta_se_puede_cerrar_sin_permiso(seeded, alpha_client):
    """§8: llegar sigue siendo posible aunque el permiso se revoque a mitad.

    Sin esto, revocar el permiso conduciendo dejaría el viaje en ruta para
    siempre: ni llega, ni se interrumpe, ni se cierra la jornada.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-LLEGA")
    await _jornada(alpha_client)
    viaje = await _viaje_en_ruta(alpha_client)

    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/arrive", json={}, headers=SIN_PERMISO
    )

    assert respuesta.status_code == 200, (
        f"llegar quedó bloqueado y el viaje se queda atrapado: {respuesta.text[:160]}"
    )


async def test_una_parada_abierta_se_puede_completar_sin_permiso(seeded, alpha_client):
    """§8: la parada que ya empezó se cierra, con su resultado."""
    from app.database import async_session_maker as _sm
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    await _supervisor_listo(alpha_client, seeded, unidad="V-PARADA")
    async with _sm() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    await _jornada(alpha_client)
    viaje = await _viaje_en_ruta(alpha_client)
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    valores = (
        await alpha_client.get("/api/standard-values/client_visit_activities")
    ).json()
    inicio = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [valores[0]["id"]]},
    )
    assert inicio.status_code in (200, 201), inicio.text

    resultados = (await alpha_client.get("/api/standard-values/outcomes")).json()
    respuesta = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultados[0]["id"]},
        headers=SIN_PERMISO,
    )

    assert respuesta.status_code == 200, (
        f"completar la parada quedó bloqueado: {respuesta.text[:160]}"
    )


async def test_la_jornada_se_puede_terminar_sin_permiso(seeded, alpha_client):
    """§8: End Work siempre. Es la salida del día y no puede depender del GPS."""
    await _supervisor_listo(alpha_client, seeded, unidad="V-FIN")
    jornada = await _jornada(alpha_client)

    respuesta = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end",
        json={"end_anyway": True},
        headers=SIN_PERMISO,
    )

    assert respuesta.status_code in (200, 409), respuesta.text
    if respuesta.status_code == 409:
        # Si pide la lectura de cierre, el rechazo es del odómetro —no del
        # permiso—, que es exactamente lo que este test quiere distinguir.
        assert "Location access" not in respuesta.text


async def test_tras_cerrar_lo_abierto_no_se_puede_abrir_nada_nuevo(
    seeded, alpha_client
):
    """§8 completo: la excepción cierra, y no abre.

    Es la mitad que convierte la excepción en excepción. Sin este test, un
    refuerzo que dejara pasar todo tras la primera llegada pasaría los
    anteriores.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-DESPUES")
    await _jornada(alpha_client)
    viaje = await _viaje_en_ruta(alpha_client)

    cerrar = await alpha_client.post(
        f"/api/trips/{viaje['id']}/arrive", json={}, headers=SIN_PERMISO
    )
    assert cerrar.status_code == 200

    abrir = await alpha_client.post(
        "/api/trips",
        json={"purpose": "office", "context_reference": None},
        headers=SIN_PERMISO,
    )
    assert abrir.status_code == 403, (
        "tras cerrar se pudo abrir trabajo nuevo sin permiso"
    )


# ── Con permiso, nada cambia ────────────────────────────────────────────────


async def test_con_permiso_concedido_todo_sigue_igual(seeded, alpha_client):
    """El control del conjunto: la puerta no estorba a quien sí tiene permiso.

    Sin este test, una puerta que rechazara siempre pasaría todos los de
    arriba.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-OK")
    jornada = await _jornada(alpha_client)
    assert jornada["id"]

    viaje = await _viaje_en_ruta(alpha_client)
    assert viaje["id"]

    llegada = await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    assert llegada.status_code == 200


# ── Auditoría ───────────────────────────────────────────────────────────────


async def test_el_intento_bloqueado_queda_auditado(seeded, alpha_client):
    """§12: hay que poder distinguir un intento bloqueado después.

    Sin rastro, un supervisor que dice «no me dejaba trabajar» y un sistema que
    dice «nadie lo intentó» son indistinguibles.
    """
    await _supervisor_listo(alpha_client, seeded, unidad="V-AUDIT")

    async with async_session_maker() as session:
        antes = len(
            (
                await session.scalars(
                    select(AuditEvent.id).where(
                        AuditEvent.entity_type == "location_permission"
                    )
                )
            ).all()
        )

    await alpha_client.post("/api/worksessions", json={}, headers=SIN_PERMISO)

    async with async_session_maker() as session:
        filas = (
            await session.execute(
                select(AuditEvent.action, AuditEvent.actor_user_id, AuditEvent.changes)
                .where(AuditEvent.entity_type == "location_permission")
                .order_by(AuditEvent.id.desc())
            )
        ).all()

    assert len(filas) == antes + 1, "el intento bloqueado no dejó rastro"
    accion, actor, cambios = filas[0]
    assert accion == "blocked"
    assert actor == seeded.alpha.users["supervisor"].id
    assert cambios == {"declared": "denied"}
