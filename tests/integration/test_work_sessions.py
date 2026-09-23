"""
Jornada del supervisor (RTE03).

Lo que este archivo demuestra, y por qué cada bloque existe
-------------------------------------------------------------
* **Persistencia.** Una jornada vigente por supervisor, garantizada por la
  base — no por una lectura previa en Python (§4, §10.1 de las instrucciones).
* **Snapshot de vehículo.** Se congela al empezar y no se vuelve a tocar,
  aunque el vehículo o la asignación cambien después (§6).
* **Tiempo.** La jornada pertenece a la fecha local en la que **ocurrió** el
  `Start Work`, no a la fecha en la que el servidor lo recibió — y las dos
  pueden separarse horas si la acción esperó en la cola offline (D-10, §7, y
  el cierre 002).
* **Autorización.** Solo quien tiene `route.worksession.execute` puede actuar,
  y solo sobre su propia jornada (§9).
* **Concurrencia.** Dos peticiones simultáneas de `Start Work` no producen dos
  jornadas vigentes (§4, edge case 2).
* **Estado actual y multi-dispositivo.** `GET current` es la única fuente de
  verdad, y un segundo dispositivo la recupera en vez de duplicarla (§12, A-6).
* **Continuidad de autenticación.** Revocar el acceso corta las acciones
  nuevas sin destruir la jornada histórica (§8, edge cases 20-21).
* **Idempotencia.** Reenviar la misma `Idempotency-Key` no repite la
  transición de estado (§14).
"""

import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text

from app.database import async_session_maker
from app.routers_api.worksessions.models import WorkSession
from tests.integration.conftest import TenantClient


pytestmark = pytest.mark.integration


# ── Persistencia y regla A-1 (cero Trips) ───────────────────────────────────


async def test_start_work_creates_one_active_session(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    respuesta = await alpha_client.post("/api/worksessions", json={})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "active"
    assert cuerpo["ended_at"] is None


async def test_start_then_end_produces_a_valid_zero_trip_session(
    seeded, alpha_client,
):
    """A-1: una jornada sin ningún Trip es un resultado válido, no incompleto.

    RTE03 no crea la tabla `trip` para demostrarlo — no existe todavía, y esa
    ausencia es exactamente el punto.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    creada = (await alpha_client.post("/api/worksessions", json={})).json()
    terminada = await alpha_client.post(
        f"/api/worksessions/{creada['id']}/end", json={}
    )

    assert terminada.status_code == 200
    assert terminada.json()["status"] == "ended"
    assert terminada.json()["ended_at"] is not None

    async with async_session_maker() as session:
        # No existe ninguna tabla `trip` que consultar: la ausencia de
        # importación ya lo demuestra, pero se deja explícito que la jornada
        # sigue existiendo, cerrada, sin nada más.
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )
    assert fila is not None
    assert fila.status == "ended"


async def test_ended_session_remains_in_history(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(f"/api/worksessions/{creada['id']}/end", json={})

    async with async_session_maker() as session:
        total = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )
    assert total is not None, "la jornada terminada debe seguir en la base"


async def test_start_work_stores_the_correct_tenant_and_supervisor(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )
    assert fila.company_id == seeded.alpha.id
    assert fila.user_id == seeded.alpha.users["supervisor"].id


# ── Repetir Start Work no duplica ───────────────────────────────────────────


async def test_repeated_start_work_returns_the_same_session(seeded, alpha_client):
    """Pulsar el botón dos veces no es un error: sigue siendo la misma jornada."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    primera = (await alpha_client.post("/api/worksessions", json={})).json()
    segunda = (await alpha_client.post("/api/worksessions", json={})).json()

    assert primera["id"] == segunda["id"]

    async with async_session_maker() as session:
        vigentes = (
            await session.execute(
                select(WorkSession).where(
                    WorkSession.company_id == seeded.alpha.id,
                    WorkSession.user_id == seeded.alpha.users["supervisor"].id,
                    WorkSession.status == "active",
                )
            )
        ).scalars().all()
    assert len(vigentes) == 1


async def test_concurrent_start_work_creates_only_one_active_session(
    seeded, alpha_client,
):
    """La carrera real: dos peticiones a la vez, una sola jornada vigente.

    Es el índice único parcial el que decide, no una lectura previa en Python
    —eso es precisamente lo que el edge case 2 pide demostrar.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    respuestas = await asyncio.gather(
        alpha_client.post("/api/worksessions", json={}),
        alpha_client.post("/api/worksessions", json={}),
        return_exceptions=True,
    )
    codigos = [r.status_code for r in respuestas if not isinstance(r, BaseException)]
    assert all(c == 200 for c in codigos), f"alguna petición falló: {codigos}"

    async with async_session_maker() as session:
        vigentes = (
            await session.execute(
                select(WorkSession).where(
                    WorkSession.company_id == seeded.alpha.id,
                    WorkSession.user_id == seeded.alpha.users["supervisor"].id,
                    WorkSession.status == "active",
                )
            )
        ).scalars().all()
    assert len(vigentes) == 1, (
        f"quedaron {len(vigentes)} jornadas vigentes; el índice parcial debe "
        "permitir exactamente una"
    )


async def test_the_database_rejects_a_second_active_session_directly(seeded):
    """El índice, probado saltándose el servicio por completo."""
    from sqlalchemy import insert

    async with async_session_maker() as session:
        await session.execute(
            insert(WorkSession).values(
                company_id=seeded.alpha.id,
                user_id=seeded.alpha.users["supervisor"].id,
                status="active",
                session_date=date.today(),
                started_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(Exception):
            await session.execute(
                insert(WorkSession).values(
                    company_id=seeded.alpha.id,
                    user_id=seeded.alpha.users["supervisor"].id,
                    status="active",
                    session_date=date.today(),
                    started_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        await session.rollback()


# ── Snapshot de vehículo ─────────────────────────────────────────────────────


async def _asignar_vehiculo(route_admin_client, user_id: int) -> dict:
    perfil = (
        await route_admin_client.post("/api/supervisors", json={"user_id": user_id})
    ).json()
    vehiculo = (
        await route_admin_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "RAV4", "year": 2024, "unit": "V-501",
                "fuel_grade": "regular", "operational_mpg": "27.00",
            },
        )
    ).json()
    await route_admin_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    return vehiculo


async def test_start_work_snapshots_the_current_vehicle(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _asignar_vehiculo(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    assert jornada["vehicle_id"] == vehiculo["id"]
    assert jornada["mpg_snapshot"] == "27.00"


async def test_no_vehicle_produces_null_snapshot_without_blocking_start(
    seeded, alpha_client,
):
    """§6.1: sin vehículo asignado, la jornada sigue siendo válida."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    assert jornada["status"] == "active"
    assert jornada["vehicle_id"] is None
    assert jornada["mpg_snapshot"] is None


async def test_a_supervisor_role_without_a_profile_still_gets_a_valid_session(
    seeded, alpha_client,
):
    """La capacidad de ejecutar la jornada y el perfil de campo son cosas
    distintas: tener la primera no exige el segundo (§6.1)."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.post("/api/worksessions", json={})
    assert respuesta.status_code == 200
    assert respuesta.json()["vehicle_id"] is None


async def test_later_mpg_change_does_not_alter_the_session_snapshot(
    seeded, alpha_client,
):
    """RTE01 D-02.8, aplicado a la jornada: lo que se congeló no se recalcula."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    vehiculo = await _asignar_vehiculo(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    assert jornada["mpg_snapshot"] == "27.00"

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(
        f"/api/vehicles/{vehiculo['id']}",
        json={"operational_mpg": "19.00", "version": vehiculo["version"]},
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["mpg_snapshot"] == "27.00", (
        "el cambio de MPG del vehículo maestro no debe alterar el snapshot "
        "ya congelado"
    )


async def test_later_reassignment_does_not_alter_an_already_started_session(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    primero = await _asignar_vehiculo(
        alpha_client, seeded.alpha.users["supervisor"].id
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    assert jornada["vehicle_id"] == primero["id"]

    # El administrador reasigna a un vehículo distinto DESPUÉS de Start Work.
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    segundo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Honda", "model": "CR-V", "year": 2023, "unit": "V-502",
                "fuel_grade": "regular", "operational_mpg": "29.00",
            },
        )
    ).json()
    perfiles = (await alpha_client.get("/api/supervisors/candidates")).json()
    perfil = next(
        f for f in perfiles
        if f["user_id"] == seeded.alpha.users["supervisor"].id
    )
    await alpha_client.post(
        f"/api/supervisors/{perfil['supervisor_profile_id']}/assignments",
        json={"vehicle_id": segundo["id"]},
    )

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    assert actual["work_session"]["vehicle_id"] == primero["id"], (
        "la reasignación posterior no debe tocar la jornada ya activa"
    )


# ── Tiempo (D-10) ────────────────────────────────────────────────────────────


async def test_friday_evening_to_saturday_early_morning_stays_friday(seeded):
    """Viernes 20:00 -> sábado 00:41 sigue siendo la Jornada del viernes.

    El ejemplo exacto del baseline certificado: el reloj del servidor —
    autoritativo, en UTC— marca ya la madrugada del sábado (00:41 UTC), pero
    el desfase local del dispositivo (-240 min, EDT) coloca la hora en el
    sitio donde está parado el supervisor a las 20:41 del viernes anterior.
    """
    import time_machine

    with time_machine.travel("2026-09-26 00:41:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            respuesta = await cliente.post(
                "/api/worksessions",
                json={"utc_offset_minutes": -240},
            )

    assert respuesta.status_code == 200
    assert respuesta.json()["session_date"] == "2026-09-25"


#: `time_machine` congela `datetime.now()` en **todo el intérprete** — incluida
#: la comprobación de expiración de cookies que hace `httpx`/`http.cookiejar`
#: dentro del propio cliente de pruebas, que corre en el mismo proceso que el
#: servidor (transporte ASGI en memoria, sin red real). Si se inicia sesión
#: con el reloj real y **después** se salta el reloj varios días adelante, la
#: cookie de acceso —minteada con el reloj real, Max-Age de 24 h— parece
#: expirada para el cliente en el instante congelado, y ni siquiera se envía:
#: la petición nunca llega a autorizarse, y falla en CSRF con un 403 que nada
#: tiene que ver con lo que el test pretende comprobar.
#:
#: Por eso cada test de esta sección abre su **propio** cliente y entra en
#: sesión **dentro** del bloque congelado: las cookies nacen en el mismo
#: instante que se va a comprobar, y siguen siendo válidas mientras el salto
#: entre dos bloques (cuando hace falta un segundo instante) se mantenga por
#: debajo de las 24 h de `ACCESS_TOKEN_EXPIRE_MINUTES`.


async def test_session_date_uses_local_offset_not_utc(seeded):
    """La fecha depende del desfase reportado, no de la fecha UTC del servidor.

    Con el reloj del servidor fijo a las 00:15 UTC de un sábado, un desfase de
    -240 minutos (EDT) coloca la hora local en las 20:15 del viernes anterior:
    `session_date` debe ser viernes, no sábado.
    """
    import time_machine

    with time_machine.travel("2026-09-26 00:15:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            respuesta = await cliente.post(
                "/api/worksessions",
                json={"utc_offset_minutes": -240},
            )

    assert respuesta.status_code == 200
    assert respuesta.json()["session_date"] == "2026-09-25"


async def test_without_offset_evidence_session_date_falls_back_to_utc(seeded):
    """Límite honesto de D-10: sin desfase, la fecha es la UTC del servidor.

    No es un fallo silencioso — es el comportamiento documentado cuando la
    evidencia de zona horaria no llegó (cliente antiguo, acción encolada sin
    conectividad para reportarla). `Start Work` nunca se bloquea por su
    ausencia.
    """
    import time_machine

    with time_machine.travel("2026-09-26 00:15:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            respuesta = await cliente.post("/api/worksessions", json={})

    assert respuesta.status_code == 200
    assert respuesta.json()["session_date"] == "2026-09-26"


async def test_session_date_is_immutable_after_end_work(seeded):
    import time_machine

    with time_machine.travel("2026-09-26 00:15:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            creada = (
                await cliente.post(
                    "/api/worksessions", json={"utc_offset_minutes": -240}
                )
            ).json()
            assert creada["session_date"] == "2026-09-25"

            # Mismo cliente, reloj adelantado casi 4 h — muy por debajo de las
            # 24 h de vida de la cookie, así que la sesión sigue siendo válida.
            with time_machine.travel("2026-09-26 04:00:00+00:00", tick=False):
                terminada = await cliente.post(
                    f"/api/worksessions/{creada['id']}/end",
                    json={"utc_offset_minutes": -240},
                )

    assert terminada.json()["session_date"] == "2026-09-25", (
        "session_date no se recalcula en End Work"
    )


async def test_a_dst_boundary_does_not_split_a_session_into_two_days(seeded):
    """El desfase es el que rige en ESE instante, así que un cambio de horario
    de verano entre Start y End no crea un segundo día ni una segunda jornada:
    `session_date` ya quedó fijado al empezar."""
    import time_machine

    with time_machine.travel("2026-11-01 06:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            # Antes del cambio de horario en EE.UU. (EDT, UTC-4).
            creada = (
                await cliente.post(
                    "/api/worksessions", json={"utc_offset_minutes": -240}
                )
            ).json()

            # 21 h después: cruza el cambio de horario y sigue bajo las 24 h
            # de vida de la cookie.
            with time_machine.travel("2026-11-02 03:00:00+00:00", tick=False):
                # Después del cambio (EST, UTC-5). Misma jornada, otro desfase.
                terminada = await cliente.post(
                    f"/api/worksessions/{creada['id']}/end",
                    json={"utc_offset_minutes": -300},
                )

    assert terminada.json()["id"] == creada["id"]
    assert terminada.json()["session_date"] == creada["session_date"]


async def test_skewed_device_clock_does_not_affect_authoritative_ordering(seeded):
    """Evidencia imposible: una acción no puede ocurrir después de recibirse.

    El dispositivo declara estar tres días en el futuro. El servidor no necesita
    confiar en ningún reloj ajeno para saber que eso es contradictorio —lo
    contradice su propia recepción—, así que descarta la evidencia, fecha la
    ocurrencia por recepción y **lo deja escrito** en `started_at_source`. Sin
    esa columna, esta jornada sería indistinguible de una cuya hora sí se
    conoce.
    """
    import time_machine

    with time_machine.travel("2026-09-25 12:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            creada = (
                await cliente.post(
                    "/api/worksessions",
                    json={
                        # El dispositivo cree que son tres días después.
                        "device_captured_at": "2026-09-28T12:00:00+00:00",
                        "utc_offset_minutes": 0,
                    },
                )
            ).json()

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )
    assert fila.started_at.date() == date(2026, 9, 25), (
        "la evidencia del futuro se descarta: la ocurrencia cae a la hora de "
        "recepción del servidor"
    )
    assert fila.started_at_source == "server_receipt", (
        "y el rechazo queda registrado, en vez de disimularse como una hora "
        "conocida"
    )
    assert fila.start_device_captured_at.date() == date(2026, 9, 28), (
        "lo que el dispositivo reportó se conserva verbatim aunque se haya "
        "descartado: es la evidencia de qué se rechazó"
    )


async def test_stale_device_evidence_beyond_the_window_is_rejected(seeded):
    """Una ocurrencia de hace semanas no describe la jornada que se sincroniza.

    Está dentro del pasado, así que la causalidad no la descarta; lo que la
    descarta es la ventana máxima de antigüedad admisible para una acción
    encolada. El límite es generoso a propósito (siete días), y rebasarlo no
    bloquea el `Start Work`: solo degrada la procedencia.
    """
    import time_machine

    with time_machine.travel("2026-09-25 12:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            respuesta = await cliente.post(
                "/api/worksessions",
                json={
                    "device_captured_at": "2026-09-01T12:00:00+00:00",
                    "utc_offset_minutes": 0,
                },
            )

    assert respuesta.status_code == 200, "el tiempo nunca bloquea Start Work"
    cuerpo = respuesta.json()
    assert cuerpo["started_at_source"] == "server_receipt"
    assert cuerpo["session_date"] == "2026-09-25", (
        "la fecha sale de la recepción, no de una evidencia descartada"
    )

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == cuerpo["id"])
        )
    assert fila.start_device_captured_at.date() == date(2026, 9, 1)


# ── Ocurrencia frente a recepción: acciones encoladas (cierre 002) ───────────
#
# Estos tests fallan con el comportamiento anterior, en el que `started_at` era
# la hora de recepción del servidor: ahí el retraso de sincronización se leía
# como la jornada. Son la red que impide volver a ese estado.


async def test_offline_start_queued_before_midnight_keeps_the_previous_day(seeded):
    """El caso que motivó el cierre 002.

    El supervisor pulsa `Start Work` el viernes a las 23:50 locales, sin
    cobertura. La acción espera en la cola y sincroniza el sábado a las 08:00
    locales. La jornada es del **viernes**: es el día que trabajó.

    Con el comportamiento anterior `session_date` habría salido de la hora de
    recepción (sábado) y la jornada habría quedado fechada en el día
    equivocado.
    """
    import time_machine

    # Viernes 23:50 EDT (UTC-4) = sábado 03:50 UTC. La acción se queda en la
    # cola; el servidor no se enterará hasta ocho horas después.
    ocurrencia = "2026-09-26T03:50:00+00:00"

    # Sábado 12:00 UTC = 08:00 EDT: el supervisor recupera cobertura y la cola
    # vacía lo pendiente.
    with time_machine.travel("2026-09-26 12:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            respuesta = await cliente.post(
                "/api/worksessions",
                json={
                    "device_captured_at": ocurrencia,
                    "utc_offset_minutes": -240,
                },
            )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["session_date"] == "2026-09-25", (
        "la jornada pertenece al día en que se empezó a trabajar, no al día en "
        "que la acción consiguió sincronizar"
    )
    assert cuerpo["started_at_source"] == "device"

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == cuerpo["id"])
        )

    assert fila.started_at.astimezone(timezone.utc) == datetime(
        2026, 9, 26, 3, 50, tzinfo=timezone.utc
    ), "started_at es la ocurrencia"
    assert fila.started_received_at.astimezone(timezone.utc) == datetime(
        2026, 9, 26, 12, 0, tzinfo=timezone.utc
    ), "started_received_at es la recepción, y sigue estando disponible"
    assert fila.started_at < fila.started_received_at, (
        "los dos hechos son distinguibles: ocho horas de cola entre ellos"
    )


async def test_offline_end_keeps_its_occurrence_not_the_sync_time(seeded):
    """Un `End Work` de las 17:00 que sincroniza de madrugada terminó a las
    17:00. La hora de sincronización queda, aparte, como trazabilidad."""
    import time_machine

    with time_machine.travel("2026-09-25 14:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            creada = (
                await cliente.post(
                    "/api/worksessions",
                    json={
                        "device_captured_at": "2026-09-25T14:00:00+00:00",
                        "utc_offset_minutes": -240,
                    },
                )
            ).json()

            # Doce horas después: la cola vacía el `End Work` que el supervisor
            # pulsó a las 17:00 locales (21:00 UTC), siete horas antes.
            with time_machine.travel("2026-09-26 02:00:00+00:00", tick=False):
                terminada = await cliente.post(
                    f"/api/worksessions/{creada['id']}/end",
                    json={
                        "device_captured_at": "2026-09-25T21:00:00+00:00",
                        "utc_offset_minutes": -240,
                    },
                )

    assert terminada.status_code == 200, terminada.text
    assert terminada.json()["ended_at_source"] == "device"

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )

    assert fila.ended_at.astimezone(timezone.utc) == datetime(
        2026, 9, 25, 21, 0, tzinfo=timezone.utc
    ), "la jornada terminó cuando el supervisor la cerró"
    assert fila.ended_received_at.astimezone(timezone.utc) == datetime(
        2026, 9, 26, 2, 0, tzinfo=timezone.utc
    ), "y el servidor lo supo cinco horas más tarde, que es trazable"


async def test_cross_midnight_session_with_device_evidence_stays_on_start_date(
    seeded,
):
    """Empezar viernes 20:00 y terminar sábado 01:00 es una sola jornada del
    viernes, con la evidencia de ocurrencia gobernando las dos puntas."""
    import time_machine

    with time_machine.travel("2026-09-26 00:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            creada = (
                await cliente.post(
                    "/api/worksessions",
                    json={
                        # Viernes 20:00 EDT.
                        "device_captured_at": "2026-09-26T00:00:00+00:00",
                        "utc_offset_minutes": -240,
                    },
                )
            ).json()
            assert creada["session_date"] == "2026-09-25"

            with time_machine.travel("2026-09-26 05:00:00+00:00", tick=False):
                terminada = (
                    await cliente.post(
                        f"/api/worksessions/{creada['id']}/end",
                        json={
                            # Sábado 01:00 EDT.
                            "device_captured_at": "2026-09-26T05:00:00+00:00",
                            "utc_offset_minutes": -240,
                        },
                    )
                ).json()

    assert terminada["id"] == creada["id"], "no se crea una segunda jornada"
    assert terminada["session_date"] == "2026-09-25", (
        "cruzar medianoche no reasigna la jornada al día siguiente"
    )
    assert terminada["ended_at"] is not None


async def test_replaying_a_queued_action_does_not_move_the_occurrence(seeded):
    """Rule 5 del cierre: un replay no reescribe la hora ya establecida.

    Se reenvía la misma acción con la misma `Idempotency-Key` seis horas más
    tarde. Ni la ocurrencia ni la recepción originales se mueven.
    """
    import time_machine

    cabeceras = {"Idempotency-Key": "closure-002-replay-start"}
    cuerpo = {
        "device_captured_at": "2026-09-25T11:50:00+00:00",
        "utc_offset_minutes": -240,
    }

    with time_machine.travel("2026-09-25 12:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            primera = (
                await cliente.post(
                    "/api/worksessions", json=cuerpo, headers=cabeceras
                )
            ).json()

            with time_machine.travel("2026-09-25 18:00:00+00:00", tick=False):
                replay = (
                    await cliente.post(
                        "/api/worksessions", json=cuerpo, headers=cabeceras
                    )
                ).json()

    assert replay["id"] == primera["id"]
    assert replay["started_at"] == primera["started_at"]
    assert replay["started_received_at"] == primera["started_received_at"], (
        "el replay no reescribe la hora de recepción original"
    )

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == primera["id"])
        )
    assert fila.started_at.astimezone(timezone.utc) == datetime(
        2026, 9, 25, 11, 50, tzinfo=timezone.utc
    )
    assert fila.started_received_at.astimezone(timezone.utc) == datetime(
        2026, 9, 25, 12, 0, tzinfo=timezone.utc
    )


async def test_online_start_and_end_behave_as_before(seeded):
    """Caso de control: online, ocurrencia y recepción coinciden.

    La corrección no cambia el camino normal — es lo que exige la decisión 4
    del cierre. Con cobertura, la evidencia del dispositivo llega al instante y
    se acepta, así que las dos horas son la misma.
    """
    import time_machine

    with time_machine.travel("2026-09-25 15:30:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            creada = (
                await cliente.post(
                    "/api/worksessions",
                    json={
                        "device_captured_at": "2026-09-25T15:30:00+00:00",
                        "utc_offset_minutes": -240,
                    },
                )
            ).json()
            terminada = (
                await cliente.post(
                    f"/api/worksessions/{creada['id']}/end",
                    json={
                        "device_captured_at": "2026-09-25T15:30:00+00:00",
                        "utc_offset_minutes": -240,
                    },
                )
            ).json()

    assert creada["started_at"] == creada["started_received_at"]
    assert creada["started_at_source"] == "device"
    assert creada["session_date"] == "2026-09-25"
    assert terminada["ended_at"] == terminada["ended_received_at"]
    assert terminada["status"] == "ended"


async def test_without_device_evidence_the_receipt_time_is_labelled_as_such(seeded):
    """Rule 9: la ausencia de evidencia no se disfraza de hora conocida.

    Sin `device_captured_at` la recepción sigue siendo la mejor aproximación
    disponible —y `Start Work` no se bloquea—, pero la fila dice
    `server_receipt` para que nadie lea después esa hora como el instante en el
    que el supervisor pulsó el botón.
    """
    async with TenantClient("alpha") as cliente:
        await cliente.login(seeded.alpha.users["supervisor"].email)
        cuerpo = (await cliente.post("/api/worksessions", json={})).json()

    assert cuerpo["started_at_source"] == "server_receipt"
    assert cuerpo["started_at"] == cuerpo["started_received_at"]


async def test_end_evidence_before_start_is_rejected_as_impossible(seeded):
    """Un `End Work` anterior a su propio `Start Work` es imposible.

    No se cree por venir del dispositivo: se descarta, se fecha por recepción y
    se registra la procedencia. La evidencia cruda se conserva.
    """
    import time_machine

    with time_machine.travel("2026-09-25 12:00:00+00:00", tick=False):
        async with TenantClient("alpha") as cliente:
            await cliente.login(seeded.alpha.users["supervisor"].email)
            creada = (await cliente.post("/api/worksessions", json={})).json()

            with time_machine.travel("2026-09-25 13:00:00+00:00", tick=False):
                terminada = (
                    await cliente.post(
                        f"/api/worksessions/{creada['id']}/end",
                        json={
                            # Dos horas ANTES de haber empezado.
                            "device_captured_at": "2026-09-25T10:00:00+00:00",
                            "utc_offset_minutes": 0,
                        },
                    )
                ).json()

    assert terminada["ended_at_source"] == "server_receipt"

    async with async_session_maker() as session:
        fila = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )

    assert fila.ended_at.astimezone(timezone.utc) == datetime(
        2026, 9, 25, 13, 0, tzinfo=timezone.utc
    )
    assert fila.ended_at >= fila.started_at, "nunca una duración negativa"
    assert fila.end_device_captured_at.astimezone(timezone.utc) == datetime(
        2026, 9, 25, 10, 0, tzinfo=timezone.utc
    ), "lo descartado se conserva como evidencia de qué se rechazó"


async def test_the_database_rejects_an_end_before_its_start(seeded):
    """`ck_work_session_end_after_start`, probado saltándose el servicio.

    La hora de fin llega en parte de un reloj ajeno, así que la garantía no
    puede depender de que el servicio se acuerde de comprobarlo.
    """
    from sqlalchemy import insert, update

    async with async_session_maker() as session:
        resultado = await session.execute(
            insert(WorkSession)
            .values(
                company_id=seeded.alpha.id,
                user_id=seeded.alpha.users["supervisor"].id,
                status="active",
                session_date=date(2026, 9, 25),
                started_at=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
            )
            .returning(WorkSession.id)
        )
        jornada_id = resultado.scalar_one()
        await session.commit()

    async with async_session_maker() as session:
        with pytest.raises(Exception):
            await session.execute(
                update(WorkSession)
                .where(WorkSession.id == jornada_id)
                .values(
                    status="ended",
                    ended_at=datetime(2026, 9, 25, 11, 0, tzinfo=timezone.utc),
                )
            )
            await session.commit()
        await session.rollback()


# ── Autorización ─────────────────────────────────────────────────────────────


async def test_supervisor_with_capability_can_execute_own_session(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    assert (await alpha_client.post("/api/worksessions", json={})).status_code == 200


async def test_a_route_admin_without_the_capability_cannot_start_work(
    seeded, alpha_client,
):
    """`route_admin` no recibe `worksession.execute` por administrar la
    compañía: son autorizaciones distintas (§9)."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.post("/api/worksessions", json={})).status_code == 403


async def test_a_viewer_cannot_execute_work_session_actions(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (await alpha_client.post("/api/worksessions", json={})).status_code == 403


async def test_a_supervisor_cannot_end_another_supervisors_session(seeded, alpha_client):
    """Ni siquiera del mismo tenant: la jornada no es de quien la pide."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    ajena = (await alpha_client.post("/api/worksessions", json={})).json()

    # Un segundo supervisor (el usuario "disabled" reactivado no aplica; se
    # promueve a un usuario nuevo con el mismo rol para tener una identidad
    # distinta con la misma capacidad).
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    otro = (
        await alpha_client.post(
            "/api/users",
            json={
                "username": "segundo_supervisor",
                "email": "segundo.supervisor@alpha.example.com",
                "first_name": "Segundo",
                "last_name": "Supervisor",
                "gender": False,
                "password": "UnaClaveSegura123!",
                "role_id": seeded.alpha.roles["supervisor"],
            },
        )
    ).json()

    async with TenantClient("alpha") as cliente_otro:
        await cliente_otro.login(otro["email"], password="UnaClaveSegura123!")
        respuesta = await cliente_otro.post(
            f"/api/worksessions/{ajena['id']}/end", json={}
        )
        assert respuesta.status_code == 404


async def test_cross_tenant_session_id_returns_not_found(
    seeded, alpha_client, beta_client,
):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    de_alpha = (await alpha_client.post("/api/worksessions", json={})).json()

    await beta_client.login(seeded.beta.users["supervisor"].email)
    respuesta = await beta_client.post(
        f"/api/worksessions/{de_alpha['id']}/end", json={}
    )
    assert respuesta.status_code == 404


# ── Estado actual y multi-dispositivo ───────────────────────────────────────


async def test_current_with_no_active_session_returns_null(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.get("/api/worksessions/current")
    assert respuesta.status_code == 200
    assert respuesta.json()["work_session"] is None


async def test_current_returns_the_active_session_after_reopen(
    seeded, alpha_client,
):
    """Simula reabrir la app: una llamada nueva a `current` recupera el
    mismo estado sin que el cliente haya guardado nada localmente."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()

    actual = await alpha_client.get("/api/worksessions/current")
    assert actual.json()["work_session"]["id"] == creada["id"]


async def test_a_second_device_resolves_the_same_session(seeded, alpha_client):
    """A-6: un segundo dispositivo recupera la misma jornada; nunca crea otra."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()

    async with TenantClient("alpha") as segundo_dispositivo:
        await segundo_dispositivo.login(seeded.alpha.users["supervisor"].email)
        desde_b = await segundo_dispositivo.get("/api/worksessions/current")

        assert desde_b.json()["work_session"]["id"] == creada["id"]

        # Y si el segundo dispositivo intenta "empezar" de nuevo, recibe la
        # misma jornada — nunca una segunda.
        repetida = await segundo_dispositivo.post("/api/worksessions", json={})
        assert repetida.json()["id"] == creada["id"]

    async with async_session_maker() as session:
        vigentes = (
            await session.execute(
                select(WorkSession).where(
                    WorkSession.company_id == seeded.alpha.id,
                    WorkSession.user_id == seeded.alpha.users["supervisor"].id,
                    WorkSession.status == "active",
                )
            )
        ).scalars().all()
    assert len(vigentes) == 1


# ── Continuidad de autenticación (D-09) ─────────────────────────────────────


async def test_revoked_membership_blocks_new_actions_but_keeps_history(
    seeded, alpha_client,
):
    """Edge cases 20-21: revocar corta lo nuevo; la jornada histórica queda.

    Se prioriza la seguridad, tal como piden las instrucciones: la fila
    `ACTIVE` puede seguir en la base, pero ninguna acción nueva se autoriza.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.put(
        f"/api/users/{seeded.alpha.users['supervisor'].id}/access",
        json={"is_active": False},
    )

    async with TenantClient("alpha") as cliente_revocado:
        # Inicia sesión con las credenciales todavía válidas del núcleo...
        intento = await cliente_revocado.login(
            seeded.alpha.users["supervisor"].email
        )
        # ... pero `find_login_candidate` exige membresía activa (D7): con la
        # pertenencia suspendida, el login la trata como credencial inválida
        # —la misma respuesta que "no existe", a propósito (AUD-BE-006)—, así
        # que no hay sesión nueva y no hay acción nueva posible.
        assert intento.status_code == 401

    async with async_session_maker() as session:
        sigue = await session.scalar(
            select(WorkSession).where(WorkSession.id == creada["id"])
        )
    assert sigue is not None
    assert sigue.status == "active", (
        "la jornada histórica no se toca al revocar: solo se corta el acceso "
        "nuevo"
    )

    # Se restaura para no afectar a otros tests que compartan el fixture.
    await alpha_client.put(
        f"/api/users/{seeded.alpha.users['supervisor'].id}/access",
        json={"is_active": True},
    )


async def test_an_already_open_device_is_rejected_after_membership_suspension(
    seeded, alpha_client,
):
    """El caso más afilado de los edge cases 20-21: no es un login nuevo el
    que se corta — es una cookie **ya válida** la que deja de servir, porque
    `get_current_membership` vuelve a comprobar la base en cada petición, sin
    caché. Una credencial local nunca basta por sí sola.
    """
    async with TenantClient("alpha") as dispositivo:
        await dispositivo.login(seeded.alpha.users["supervisor"].email)
        creada = (await dispositivo.post("/api/worksessions", json={})).json()

        await alpha_client.login(seeded.alpha.users["route_admin"].email)
        await alpha_client.put(
            f"/api/users/{seeded.alpha.users['supervisor'].id}/access",
            json={"is_active": False},
        )

        # La cookie de `dispositivo` sigue siendo un JWT válido y sin expirar:
        # lo único que cambió es la fila en `user_company`.
        rechazado = await dispositivo.post(
            f"/api/worksessions/{creada['id']}/end", json={}
        )
        assert rechazado.status_code == 403

        await alpha_client.put(
            f"/api/users/{seeded.alpha.users['supervisor'].id}/access",
            json={"is_active": True},
        )


async def test_valid_reauthentication_resumes_the_same_session(
    seeded, alpha_client,
):
    """Reautenticarse —sin ningún cambio de servidor— recupera la misma
    jornada: no depende de ningún token ni cookie de "propiedad de sesión",
    solo de `(company_id, user_id)`."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()

    # Nueva "sesión de navegador": cliente distinto, mismas credenciales.
    async with TenantClient("alpha") as reautenticado:
        await reautenticado.login(seeded.alpha.users["supervisor"].email)
        actual = await reautenticado.get("/api/worksessions/current")

    assert actual.json()["work_session"]["id"] == creada["id"]


# ── Idempotencia ─────────────────────────────────────────────────────────────


async def test_replaying_the_same_idempotency_key_changes_state_once(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    clave = "start-2026-09-25-abc123"
    primera = await alpha_client.post(
        "/api/worksessions",
        json={},
        headers={"Idempotency-Key": clave},
    )
    segunda = await alpha_client.post(
        "/api/worksessions",
        json={},
        headers={"Idempotency-Key": clave},
    )

    assert primera.json()["id"] == segunda.json()["id"]

    async with async_session_maker() as session:
        vigentes = (
            await session.execute(
                select(WorkSession).where(
                    WorkSession.company_id == seeded.alpha.id,
                    WorkSession.user_id == seeded.alpha.users["supervisor"].id,
                    WorkSession.status == "active",
                )
            )
        ).scalars().all()
    assert len(vigentes) == 1


async def test_end_work_replayed_twice_is_safe(seeded, alpha_client):
    """Edge case 13: terminar dos veces no es un error ni una doble escritura."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()

    primera = await alpha_client.post(f"/api/worksessions/{creada['id']}/end", json={})
    segunda = await alpha_client.post(f"/api/worksessions/{creada['id']}/end", json={})

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert primera.json()["ended_at"] == segunda.json()["ended_at"], (
        "la segunda llamada no debe recalcular ended_at"
    )


async def test_out_of_order_end_before_start_does_not_corrupt_state(
    seeded, alpha_client,
):
    """Edge case 19: un `End Work` sin jornada vigente no crea nada raro."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    respuesta = await alpha_client.post("/api/worksessions/999999/end", json={})
    assert respuesta.status_code == 404

    todavia_nada = await alpha_client.get("/api/worksessions/current")
    assert todavia_nada.json()["work_session"] is None


# ── Auditoría ────────────────────────────────────────────────────────────────


async def test_start_and_end_are_audited(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    creada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(f"/api/worksessions/{creada['id']}/end", json={})

    async with async_session_maker() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT action, actor_user_id FROM audit_event WHERE "
                    "entity_type = 'work_session' AND entity_id = :id ORDER BY id"
                ),
                {"id": creada["id"]},
            )
        ).mappings().all()

    assert [f["action"] for f in filas] == ["start", "end"]
    assert all(
        f["actor_user_id"] == seeded.alpha.users["supervisor"].id for f in filas
    )
