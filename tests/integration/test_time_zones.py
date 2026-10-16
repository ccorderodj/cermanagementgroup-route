"""
T-1/T-2: la zona horaria y el día de negocio de cada supervisor.

Lo que este archivo defiende
----------------------------
**Una sola zona efectiva por jornada**: el override del perfil si existe, la
del dispositivo si no. Esa zona fecha `session_date` y formatea las horas de la
jornada, así que las dos cosas no pueden contradecirse. Y el «hoy» de cada
supervisor sale de **su** zona: nunca de la última jornada de otra persona,
nunca de un desfase extrapolado y nunca de UTC presentado como hora local.

Instantes explícitos, no el reloj
---------------------------------
Las pruebas fijan los instantes —`device_captured_at`, `ahora`— en vez de
depender de la hora a la que se ejecuten. La E2E de R-1 enseñó por qué: una
prueba que mezcla `CURRENT_DATE` con «hoy» pasa o falla según la hora del día.
Las de cambio de horario mueven el reloj del servidor con `time_machine`,
porque el servidor descarta con razón una evidencia del dispositivo que vaya
más de dos minutos por delante de su propio reloj.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.live.dao import today_rows

pytestmark = pytest.mark.integration

ESTE = "America/New_York"
CENTRO = "America/Chicago"


# ── Ayudas ──────────────────────────────────────────────────────────────────


def _instante_de_corte() -> datetime:
    """El 04:30 UTC más reciente: 00:30 en el Este y 23:30 del día anterior en
    el Centro, en horario de verano. Es el instante en que las dos fechas
    locales difieren, y está siempre dentro de la ventana de evidencia del
    servidor (siete días hacia atrás)."""
    ahora = datetime.now(timezone.utc)
    corte = ahora.replace(hour=4, minute=30, second=0, microsecond=0)
    return corte if corte <= ahora else corte - timedelta(days=1)


async def _perfil(cliente, seeded, usuario: str) -> dict:
    """Designa a un usuario sembrado como supervisor de Route, sin vehículo."""
    await cliente.login(seeded.alpha.users["route_admin"].email)
    respuesta = await cliente.post(
        "/api/supervisors", json={"user_id": seeded.alpha.users[usuario].id}
    )
    assert respuesta.status_code in (200, 201), respuesta.text
    return respuesta.json()


async def _empezar(
    cliente, seeded, usuario: str, *, instante: datetime, zona=None, desfase=None
) -> dict:
    await cliente.login(seeded.alpha.users[usuario].email)
    cuerpo = {"device_captured_at": instante.isoformat()}
    if zona is not None:
        cuerpo["time_zone"] = zona
    if desfase is not None:
        cuerpo["utc_offset_minutes"] = desfase
    respuesta = await cliente.post("/api/worksessions", json=cuerpo)
    assert respuesta.status_code in (200, 201), respuesta.text
    return respuesta.json()


async def _terminar(cliente, jornada: dict, *, instante: datetime) -> None:
    respuesta = await cliente.post(
        f"/api/worksessions/{jornada['id']}/end",
        json={"device_captured_at": instante.isoformat()},
    )
    assert respuesta.status_code == 200, respuesta.text


def _fila(filas: list[dict], user_id: int) -> dict:
    return next(f for f in filas if f["user_id"] == user_id)


# ── 1. Start Work: la zona efectiva fecha la jornada ────────────────────────


async def test_la_zona_del_dispositivo_fecha_la_jornada_y_se_guarda(
    seeded, alpha_client
):
    """Mismo instante, dos zonas, dos fechas: Este y Centro cerca de medianoche."""
    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    await _perfil(alpha_client, seeded, "route_admin")

    este = await _empezar(alpha_client, seeded, "supervisor", instante=corte, zona=ESTE)
    centro = await _empezar(
        alpha_client, seeded, "route_admin", instante=corte, zona=CENTRO
    )

    assert este["start_time_zone"] == ESTE
    assert centro["start_time_zone"] == CENTRO
    assert este["session_date"] == corte.date().isoformat()
    assert centro["session_date"] == (corte.date() - timedelta(days=1)).isoformat()


async def test_el_override_prevalece_sobre_el_dispositivo(seeded, alpha_client):
    """Override Centro, teléfono en el Este: la jornada es del Centro, entera."""
    corte = _instante_de_corte()
    perfil = await _perfil(alpha_client, seeded, "supervisor")
    fijado = await alpha_client.put(
        f"/api/supervisors/{perfil['id']}/time-zone",
        json={"operational_time_zone": CENTRO, "version": perfil["version"]},
    )
    assert fijado.status_code == 200, fijado.text

    jornada = await _empezar(
        alpha_client, seeded, "supervisor", instante=corte, zona=ESTE
    )

    # La zona que se **aplicó**, no la del dispositivo: la fecha y las horas
    # de esta jornada tienen que salir de la misma.
    assert jornada["start_time_zone"] == CENTRO
    assert jornada["session_date"] == (corte.date() - timedelta(days=1)).isoformat()


async def test_cambiar_el_override_no_reescribe_jornadas_anteriores(
    seeded, alpha_client
):
    corte = _instante_de_corte()
    perfil = await _perfil(alpha_client, seeded, "supervisor")
    jornada = await _empezar(
        alpha_client, seeded, "supervisor", instante=corte, zona=ESTE
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(
        f"/api/supervisors/{perfil['id']}/time-zone",
        json={"operational_time_zone": CENTRO},
    )

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT start_time_zone, session_date FROM work_session "
                    "WHERE id = :i"
                ),
                {"i": jornada["id"]},
            )
        ).one()
    assert fila.start_time_zone == ESTE, "la instantánea es inmutable"
    assert fila.session_date.isoformat() == jornada["session_date"]


async def test_una_zona_invalida_no_bloquea_y_se_fecha_como_antes(
    seeded, alpha_client
):
    """Zona que `zoneinfo` no reconoce: se ignora, el desfase fecha, nada se rompe."""
    corte = _instante_de_corte()
    jornada = await _empezar(
        alpha_client, seeded, "supervisor",
        instante=corte, zona="Mars/Olympus_Mons", desfase=-240,
    )

    assert jornada["start_time_zone"] is None
    assert jornada["session_date"] == (corte - timedelta(minutes=240)).date().isoformat()


async def test_sin_zona_ni_desfase_el_comportamiento_anterior_se_conserva(
    seeded, alpha_client
):
    """Un cliente anterior a T-1/T-2: se fecha en UTC, como siempre, y sin zona."""
    corte = _instante_de_corte()
    jornada = await _empezar(alpha_client, seeded, "supervisor", instante=corte)

    assert jornada["start_time_zone"] is None
    assert jornada["session_date"] == corte.date().isoformat()


# ── 2. El override administrativo ───────────────────────────────────────────


async def test_el_override_se_valida_se_audita_y_se_puede_quitar(
    seeded, alpha_client
):
    perfil = await _perfil(alpha_client, seeded, "supervisor")
    ruta = f"/api/supervisors/{perfil['id']}/time-zone"

    invalida = await alpha_client.put(
        ruta, json={"operational_time_zone": "Eastern Time"}
    )
    assert invalida.status_code == 422

    fijada = await alpha_client.put(ruta, json={"operational_time_zone": CENTRO})
    assert fijada.status_code == 200
    assert fijada.json()["operational_time_zone"] == CENTRO

    quitada = await alpha_client.put(ruta, json={"operational_time_zone": None})
    assert quitada.status_code == 200
    assert quitada.json()["operational_time_zone"] is None

    async with async_session_maker() as session:
        eventos = (
            await session.execute(
                text(
                    "SELECT actor_user_id, changes, occurred_at FROM audit_event "
                    "WHERE company_id = :c AND entity_type = 'supervisor_profile' "
                    "AND action = 'time_zone' ORDER BY id"
                ),
                {"c": seeded.alpha.id},
            )
        ).all()

    assert [e.changes["operational_time_zone"] for e in eventos] == [
        {"old": None, "new": CENTRO},
        {"old": CENTRO, "new": None},
    ], "la invalida no deja traza porque no cambió nada"
    assert all(e.actor_user_id == seeded.alpha.users["route_admin"].id for e in eventos)
    assert all(e.occurred_at is not None for e in eventos)


async def test_el_override_tiene_permiso_tenant_y_version(
    seeded, alpha_client, beta_client
):
    perfil = await _perfil(alpha_client, seeded, "supervisor")
    ruta = f"/api/supervisors/{perfil['id']}/time-zone"

    # Un supervisor no cambia la zona de nadie, tampoco la suya.
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (
        await alpha_client.put(ruta, json={"operational_time_zone": CENTRO})
    ).status_code == 403

    # Otra compañía: 404, sin confirmar que el perfil existe.
    await beta_client.login(seeded.beta.users["route_admin"].email)
    assert (
        await beta_client.put(ruta, json={"operational_time_zone": CENTRO})
    ).status_code == 404

    # Una versión vieja no pisa un cambio ajeno.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (
        await alpha_client.put(
            ruta, json={"operational_time_zone": CENTRO, "version": perfil["version"]}
        )
    ).status_code == 200
    assert (
        await alpha_client.put(
            ruta, json={"operational_time_zone": ESTE, "version": perfil["version"]}
        )
    ).status_code == 409


# ── 3. Today: el día de cada supervisor ─────────────────────────────────────


async def test_este_y_centro_ven_cada_uno_su_dia_sin_depender_del_otro(
    seeded, alpha_client
):
    """AC01 y AC02: el mismo instante, dos fechas, y ninguna prestada."""
    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    await _perfil(alpha_client, seeded, "route_admin")
    este = await _empezar(
        alpha_client, seeded, "supervisor", instante=corte - timedelta(minutes=10),
        zona=ESTE,
    )
    await _terminar(alpha_client, este, instante=corte - timedelta(minutes=5))
    centro = await _empezar(
        alpha_client, seeded, "route_admin", instante=corte - timedelta(minutes=10),
        zona=CENTRO,
    )
    await _terminar(alpha_client, centro, instante=corte - timedelta(minutes=5))

    filas = await today_rows(seeded.alpha.id, corte)
    fila_este = _fila(filas, seeded.alpha.users["supervisor"].id)
    fila_centro = _fila(filas, seeded.alpha.users["route_admin"].id)

    # 04:30 UTC: en el Este ya es el día siguiente, en el Centro todavía no.
    assert fila_este["session_date"] == corte.date()
    assert fila_centro["session_date"] == corte.date() - timedelta(days=1)
    # La jornada del Este (00:20 local) es de su hoy; la del Centro (23:20)
    # también es de su hoy. Las dos se ven, cada una en su día.
    assert fila_este["status"] == "ended"
    assert fila_centro["status"] == "ended"
    assert fila_este["time_zone"] == ESTE
    assert fila_centro["time_zone"] == CENTRO

    # Y que el Centro empiece otra jornada no mueve el día del Este.
    await _empezar(
        alpha_client, seeded, "route_admin", instante=corte, zona=CENTRO
    )
    otra_vez = _fila(
        await today_rows(seeded.alpha.id, corte), seeded.alpha.users["supervisor"].id
    )
    assert otra_vez["session_date"] == corte.date()


async def test_la_jornada_nocturna_sigue_visible_y_sus_metricas_no_se_mudan(
    seeded, alpha_client
):
    """D4: activa después de medianoche, visible; sus métricas, de su día."""
    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    # 23:30 en el Este: la jornada es de «ayer».
    jornada = await _empezar(
        alpha_client, seeded, "supervisor", instante=corte - timedelta(hours=1),
        zona=ESTE,
    )
    assert jornada["session_date"] == (corte.date() - timedelta(days=1)).isoformat()

    fila = _fila(
        await today_rows(seeded.alpha.id, corte), seeded.alpha.users["supervisor"].id
    )

    assert fila["status"] == "working", "no desaparece a medianoche"
    assert fila["session_date"] == corte.date(), "la fila habla del hoy del supervisor"
    assert fila["activities_today"] == 0
    assert str(fila["official_miles"]) == "0.0"

    # Y nadie la cerró.
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["status"] == "active"


async def test_sin_zona_determinable_no_se_inventa_un_dia(seeded, alpha_client):
    """D3: un cliente sin zona. Ni UTC como si fuera su hora, ni el día de otro."""
    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    await _perfil(alpha_client, seeded, "route_admin")
    # Otro supervisor con zona en la misma compañía: no se le presta.
    await _empezar(alpha_client, seeded, "route_admin", instante=corte, zona=ESTE)

    sin_zona = await _empezar(
        alpha_client, seeded, "supervisor", instante=corte - timedelta(minutes=10)
    )
    activa = _fila(
        await today_rows(seeded.alpha.id, corte), seeded.alpha.users["supervisor"].id
    )
    # Trabajando: se ve su estado, con la fecha de su propia jornada.
    assert activa["status"] == "working"
    assert activa["time_zone_determined"] is False
    assert activa["session_date"] == date.fromisoformat(sin_zona["session_date"])
    assert activa["time_zone"] is None

    await _terminar(alpha_client, sin_zona, instante=corte - timedelta(minutes=5))
    cerrada = _fila(
        await today_rows(seeded.alpha.id, corte), seeded.alpha.users["supervisor"].id
    )
    # Terminada y sin zona: no hay ningún día que se pueda afirmar.
    assert cerrada["time_zone_determined"] is False
    assert cerrada["session_date"] is None
    assert cerrada["status"] == "not_started"


async def test_el_contrato_de_today_es_aditivo(seeded, alpha_client):
    """Los campos nuevos están; los de siempre conservan nombre y tipo."""
    await _perfil(alpha_client, seeded, "supervisor")
    await _empezar(
        alpha_client, seeded, "supervisor",
        instante=datetime.now(timezone.utc) - timedelta(minutes=1), zona=ESTE,
    )
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = (await alpha_client.get("/api/live/today")).json()

    date.fromisoformat(cuerpo["session_date"])
    fila = next(
        s for s in cuerpo["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    for campo in ("status", "since", "official_miles", "activities_today"):
        assert campo in fila
    assert fila["time_zone"] == ESTE
    assert fila["time_zone_determined"] is True
    assert cuerpo["session_date"] == fila["session_date"]


# ── 4. Cambio de horario ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("reloj", "desfase_viejo", "esperado"),
    [
        # Otoño: 04:30 UTC del 2 de noviembre son las 23:30 EST del día 1. Con
        # el desfase de octubre (-240) serían las 00:30 del día 2.
        ("2026-11-02T04:30:00+00:00", -240, date(2026, 11, 1)),
        # Primavera: 04:30 UTC del 15 de marzo son las 00:30 EDT del día 15.
        # Con el desfase de invierno (-300) serían las 23:30 del día 14.
        ("2027-03-15T04:30:00+00:00", -300, date(2027, 3, 15)),
    ],
    ids=["otono-2026", "primavera-2027"],
)
async def test_el_cambio_de_horario_lo_resuelve_la_zona_no_el_desfase(
    seeded, reloj, desfase_viejo, esperado
):
    """El desfase que se envía es el **viejo** a propósito: si la fecha saliera
    de él, el resultado sería el día equivocado.

    Cliente propio, con sesión iniciada **dentro** del reloj movido, por lo que
    documenta `test_work_sessions.py`: las cookies emitidas con el reloj real
    parecerían caducadas en el instante congelado.
    """
    import time_machine

    from tests.integration.conftest import TenantClient

    instante = datetime.fromisoformat(reloj)
    with time_machine.travel(instante + timedelta(minutes=1), tick=False):
        async with TenantClient("alpha") as cliente:
            await _perfil(cliente, seeded, "supervisor")
            jornada = await _empezar(
                cliente, seeded, "supervisor",
                instante=instante, zona=ESTE, desfase=desfase_viejo,
            )
        filas = await today_rows(seeded.alpha.id, instante + timedelta(minutes=1))

    assert jornada["session_date"] == esperado.isoformat()
    fila = _fila(filas, seeded.alpha.users["supervisor"].id)
    assert fila["session_date"] == esperado
    assert fila["status"] == "working"


# ── 5. Offline ──────────────────────────────────────────────────────────────


async def test_un_start_work_encolado_se_fecha_por_su_ocurrencia_y_su_zona(
    seeded, alpha_client
):
    """Capturado a las 23:50 del Este, sincronizado al día siguiente."""
    corte = _instante_de_corte()
    capturado = corte - timedelta(minutes=40)  # 23:50 EDT del día anterior
    jornada = await _empezar(
        alpha_client, seeded, "supervisor", instante=capturado, zona=ESTE
    )

    assert jornada["session_date"] == (corte.date() - timedelta(days=1)).isoformat()
    assert jornada["started_at_source"] == "device"
    assert datetime.fromisoformat(jornada["started_at"]) == capturado


async def test_un_override_fijado_mientras_estaba_encolado_se_aplica_al_crearla(
    seeded, alpha_client
):
    """La política documentada: la jornada nace al sincronizar.

    Se resuelve con el override vigente al crearla y la zona del dispositivo
    del encolado, sobre el instante de ocurrencia. Después ya no cambia.
    """
    corte = _instante_de_corte()
    perfil = await _perfil(alpha_client, seeded, "supervisor")
    capturado = corte - timedelta(minutes=10)  # 00:20 en el Este, 23:20 Centro
    # Mientras la acción esperaba en el teléfono, el administrador fijó Centro.
    await alpha_client.put(
        f"/api/supervisors/{perfil['id']}/time-zone",
        json={"operational_time_zone": CENTRO},
    )

    jornada = await _empezar(
        alpha_client, seeded, "supervisor", instante=capturado, zona=ESTE
    )

    assert jornada["start_time_zone"] == CENTRO
    assert jornada["session_date"] == (corte.date() - timedelta(days=1)).isoformat()


# ── 6. User Activity ────────────────────────────────────────────────────────


async def test_las_paradas_llevan_la_zona_de_su_jornada_o_su_desfase(
    seeded, alpha_client
):
    """Con zona, la zona; histórica, sólo el desfase, sin atribuirle una zona."""
    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    jornada = await _empezar(
        alpha_client, seeded, "supervisor", instante=corte, zona=ESTE, desfase=-240,
    )
    viaje = (await alpha_client.post("/api/trips", json={"purpose": "home"})).json()
    assert (
        await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    ).status_code == 200

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vista = (
        await alpha_client.get(
            "/api/activity-explorer",
            params={
                "range": "day",
                "date": jornada["session_date"],
                "supervisor_user_id": seeded.alpha.users["supervisor"].id,
            },
        )
    ).json()
    assert vista["activities"][0]["time_zone"] == ESTE
    assert vista["activities"][0]["utc_offset_minutes"] == -240

    # Una jornada anterior a T-1/T-2: se le quita la zona como si nunca la
    # hubiera tenido.
    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE work_session SET start_time_zone = NULL WHERE id = :i"),
            {"i": jornada["id"]},
        )
        await session.commit()
    historica = (
        await alpha_client.get(
            "/api/activity-explorer",
            params={
                "range": "day",
                "date": jornada["session_date"],
                "supervisor_user_id": seeded.alpha.users["supervisor"].id,
            },
        )
    ).json()
    assert historica["activities"][0]["time_zone"] is None
    assert historica["activities"][0]["utc_offset_minutes"] == -240


async def test_user_activity_abre_en_el_dia_del_supervisor_que_se_mira(
    seeded, alpha_client
):
    """Sin fecha en la petición: el hoy de esa persona, o su última jornada."""
    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    await _perfil(alpha_client, seeded, "route_admin")
    # Uno con zona; el otro sólo con una jornada vieja sin zona.
    await _empezar(alpha_client, seeded, "supervisor", instante=corte, zona=CENTRO)
    vieja = await _empezar(
        alpha_client, seeded, "route_admin", instante=corte - timedelta(days=2)
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    con_zona = (
        await alpha_client.get(
            "/api/activity-explorer",
            params={"supervisor_user_id": seeded.alpha.users["supervisor"].id},
        )
    ).json()
    sin_zona = (
        await alpha_client.get(
            "/api/activity-explorer",
            params={"supervisor_user_id": seeded.alpha.users["route_admin"].id},
        )
    ).json()

    from app.routers_api.worksessions.time_zones import dia_local

    hoy_centro = dia_local(datetime.now(timezone.utc), CENTRO)
    assert con_zona["start"] == hoy_centro.isoformat()
    assert sin_zona["start"] == vieja["session_date"], (
        "sin zona no se inventa un hoy: se abre en su última jornada"
    )


# ── 7. La zona de sesión de PostgreSQL no cuenta ────────────────────────────


async def test_el_resultado_no_depende_de_la_zona_de_sesion_de_postgres(
    seeded, alpha_client
):
    """Edge case del §9: una base con `timezone` distinto de UTC."""
    from app.database import engine

    corte = _instante_de_corte()
    await _perfil(alpha_client, seeded, "supervisor")
    await _empezar(alpha_client, seeded, "supervisor", instante=corte, zona=ESTE)
    antes = await today_rows(seeded.alpha.id, corte)

    async with async_session_maker() as session:
        base = await session.scalar(text("SELECT current_database()"))
    try:
        async with engine.begin() as conexion:
            await conexion.execute(
                text(f'ALTER DATABASE "{base}" SET timezone TO \'Pacific/Kiritimati\'')
            )
        await engine.dispose()
        async with async_session_maker() as session:
            assert (
                await session.scalar(text("SHOW timezone"))
            ) == "Pacific/Kiritimati"
        despues = await today_rows(seeded.alpha.id, corte)
    finally:
        async with engine.begin() as conexion:
            await conexion.execute(text(f'ALTER DATABASE "{base}" RESET timezone'))
        await engine.dispose()

    assert despues == antes
