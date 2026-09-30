"""El hecho Missing es inmutable; el aviso es aparte (D-RTE06-MISSING-01).

Qué decisión fija esto
---------------------
La primera versión guardaba el estado de entrega del aviso en la misma fila que
el hecho, y por eso su disparador permitía `UPDATE` de cuatro columnas. Eso es
un hecho "inmutable con excepciones", y CER resolvió la ambigüedad hacia el lado
estricto: un hecho histórico no se reinterpreta después.

Estos tests fijan las dos mitades de esa decisión, porque una sin la otra no
dice nada: que el hecho no se pueda tocar **y** que el aviso sí pueda avanzar.
Si sólo se comprobara lo primero, alguien podría cerrarlo congelando también la
notificación y rompiendo §30 sin que nada protestase.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import async_session_maker

pytestmark = pytest.mark.integration


AHORA = datetime.now(timezone.utc)


async def _jornada_con_viaje(cliente, seeded, *, tenant: str = "alpha"):
    compania = getattr(seeded, tenant)
    await cliente.login(compania.users["supervisor"].email)
    jornada = (await cliente.post("/api/worksessions", json={})).json()
    assert "id" in jornada, jornada
    viaje = (
        await cliente.post(
            "/api/trips", json={"purpose": "other", "context_reference": "Tarea"}
        )
    ).json()
    assert "id" in viaje, viaje
    await cliente.post(f"/api/trips/{viaje['id']}/start", json={})
    await cliente.post(f"/api/trips/{viaje['id']}/arrive", json={})
    return jornada, viaje


async def _crear_missing(cliente, viaje_id: int):
    respuesta = await cliente.post(
        "/api/location/missing",
        json={
            "event_kind": "arrived",
            "subject_id": viaje_id,
            "reason_code": "recovery_window_exhausted",
            "permission_state": "granted",
            "rejected_age_seconds": 7200,
            "rejected_accuracy_m": "3000.00",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _filas(consulta: str, params: dict) -> list[dict]:
    async with async_session_maker() as sesion:
        filas = await sesion.execute(text(consulta), params)
        return [dict(f._mapping) for f in filas]


async def _falla(sentencia: str, params: dict) -> str:
    """Ejecuta algo que debe fallar y devuelve el mensaje."""
    async with async_session_maker() as sesion:
        with pytest.raises(Exception) as fallo:
            await sesion.execute(text(sentencia), params)
            await sesion.commit()
    return str(fallo.value)


# ── El hecho: sin excepciones ───────────────────────────────────────────────


async def test_the_missing_fact_has_no_notification_columns(seeded, alpha_client):
    """Las columnas de entrega ya no están en el hecho.

    Se comprueba contra el catálogo y no contra el modelo: lo que importa es lo
    que hay en la base, que es lo que sobrevive a un despliegue.
    """
    columnas = {
        f["column_name"]
        for f in await _filas(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'missing_location_event'",
            {},
        )
    }
    assert "notification_status" not in columnas
    assert "notified_at" not in columnas
    assert "notes" not in columnas, (
        "un texto libre editable sobre un hecho histórico es la reinterpretación "
        "que D-RTE06-MISSING-01 prohíbe"
    )
    # Y lo que §3 exige conservar sigue estando.
    for exigida in (
        "company_id",
        "work_session_id",
        "trip_id",
        "event_kind",
        "subject_kind",
        "subject_id",
        "occurred_at",
        "reason_code",
        "permission_state",
        "attempts",
        "rejected_candidate",
        "created_at",
    ):
        assert exigida in columnas, exigida


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE missing_location_event SET reason_code = 'permission_denied' "
        "WHERE company_id = :c",
        "UPDATE missing_location_event SET occurred_at = now() WHERE company_id = :c",
        "UPDATE missing_location_event SET attempts = '[]'::jsonb "
        "WHERE company_id = :c",
        "UPDATE missing_location_event SET updated_at = now() WHERE company_id = :c",
        "DELETE FROM missing_location_event WHERE company_id = :c",
    ],
    ids=["razon", "ocurrencia", "intentos", "updated_at", "borrado"],
)
async def test_nothing_about_the_missing_fact_can_change(
    seeded, alpha_client, sentencia
):
    """Ninguna columna, ni siquiera `updated_at`. Ni borrado.

    `updated_at` está en la lista a propósito: era una de las cuatro que el
    disparador anterior exentaba, y dejarla abierta permitiría "tocar" la fila
    sin cambiar nada visible — que es el primer paso para volver a exentar otra.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])

    mensaje = await _falla(sentencia, {"c": seeded.alpha.id})
    assert "append-only" in mensaje, mensaje

    # Y sigue habiendo exactamente un hecho, intacto.
    filas = await _filas(
        "SELECT reason_code FROM missing_location_event WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(filas) == 1
    assert filas[0]["reason_code"] == "recovery_window_exhausted"


async def test_the_rejected_candidate_keeps_no_coordinates(seeded, alpha_client):
    """Del punto descartado se guarda edad y precisión, nunca dónde estaba.

    §3 lo dice expresamente. Saber que había un punto de dos horas con 3 km de
    error explica el fallo; guardar su posición sería conservar una ubicación
    que el sistema decidió no usar.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])

    fila = (
        await _filas(
            "SELECT rejected_candidate FROM missing_location_event "
            "WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert set(fila["rejected_candidate"]) == {"age_seconds", "accuracy_m"}
    for prohibido in ("latitude", "longitude", "lat", "lon"):
        assert prohibido not in fila["rejected_candidate"]


# ── El aviso: separado y sí mutable ────────────────────────────────────────


async def test_a_notification_row_is_created_with_the_fact(seeded, alpha_client):
    """El hecho y su registro de entrega nacen juntos, en la misma transacción.

    Un hecho sin fila de aviso quedaría invisible para quien entregue los
    avisos, y descubrirlo después exigiría comparar las dos tablas.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    creado = await _crear_missing(alpha_client, viaje["id"])

    avisos = await _filas(
        "SELECT n.channel, n.status, n.attempt_count, n.delivered_at "
        "FROM missing_location_notification n "
        "JOIN missing_location_event e ON e.id = n.missing_location_event_id "
        "WHERE n.company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert len(avisos) == 1, avisos
    assert avisos[0]["channel"] == "in_platform", (
        "el canal que D-01 exige, y el único que se puede afirmar"
    )
    assert avisos[0]["status"] == "pending"
    assert avisos[0]["attempt_count"] == 0
    assert avisos[0]["delivered_at"] is None
    # La API devuelve el estado de entrega junto al hecho, por comodidad.
    assert creado["notification_status"] == "pending"


async def test_the_notification_state_can_advance(seeded, alpha_client):
    """El aviso sí avanza: es operacional, no histórico.

    Es la otra mitad de la decisión. Sin este test, cerrar la inmutabilidad
    congelando también la notificación parecería correcto y rompería §30.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])

    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE missing_location_notification "
                "SET status = 'notified', delivered_at = now(), attempt_count = 1 "
                "WHERE company_id = :c"
            ),
            {"c": seeded.alpha.id},
        )
        await sesion.commit()

    aviso = (
        await _filas(
            "SELECT status, attempt_count, delivered_at "
            "FROM missing_location_notification WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert aviso["status"] == "notified"
    assert aviso["delivered_at"] is not None

    # Y el hecho sigue sin tocarse: lo que cambió fue la entrega.
    hecho = (
        await _filas(
            "SELECT created_at, updated_at FROM missing_location_event "
            "WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]
    assert hecho["created_at"] == hecho["updated_at"], (
        "el hecho nunca se ha actualizado"
    )


async def test_a_delivered_notification_must_carry_its_delivery_time(
    seeded, alpha_client
):
    """`notified` sin fecha de entrega no puede existir.

    Lo garantiza un `CHECK`, no el servicio: una fila que dijera "entregado" sin
    decir cuándo haría imposible auditar la entrega, que es lo único para lo que
    esta tabla existe.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])

    mensaje = await _falla(
        "UPDATE missing_location_notification SET status = 'notified' "
        "WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert "ck_missing_location_notification_delivered" in mensaje, mensaje


async def test_one_notification_row_per_channel(seeded, alpha_client):
    """Un hecho y un canal, una fila. Un reintento avanza; no apila.

    Si apilara, "¿se avisó por plataforma?" tendría tantas respuestas como
    intentos.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])

    evento = (
        await _filas(
            "SELECT id FROM missing_location_event WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]["id"]

    mensaje = await _falla(
        "INSERT INTO missing_location_notification "
        "(company_id, missing_location_event_id, channel, status, attempt_count, "
        " created_at, updated_at) "
        "VALUES (:c, :e, 'in_platform', 'pending', 0, now(), now())",
        {"c": seeded.alpha.id, "e": evento},
    )
    assert "uq_missing_location_notification_channel" in mensaje, mensaje

    # Otro canal sí: §3 pide compatibilidad con canales futuros.
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "INSERT INTO missing_location_notification "
                "(company_id, missing_location_event_id, channel, status, "
                " attempt_count, created_at, updated_at) "
                "VALUES (:c, :e, 'email', 'pending', 0, now(), now())"
            ),
            {"c": seeded.alpha.id, "e": evento},
        )
        await sesion.commit()

    assert len(
        await _filas(
            "SELECT id FROM missing_location_notification WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    ) == 2


async def test_a_notification_cannot_reference_another_tenants_fact(
    seeded, alpha_client, beta_client
):
    """El registro de entrega no puede colgar del hecho de otra compañía.

    La FK es compuesta con `company_id`, así que es imposible por construcción y
    no por cuidado del servicio.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])
    evento_alpha = (
        await _filas(
            "SELECT id FROM missing_location_event WHERE company_id = :c",
            {"c": seeded.alpha.id},
        )
    )[0]["id"]

    # Canal `email` a propósito: `in_platform` ya tiene fila para ese hecho y
    # chocaría primero contra el único, que no es lo que este test mide. Con un
    # canal libre, lo único que puede rechazar la fila es la clave foránea
    # compuesta — y eso es lo que se quiere demostrar.
    mensaje = await _falla(
        "INSERT INTO missing_location_notification "
        "(company_id, missing_location_event_id, channel, status, attempt_count, "
        " created_at, updated_at) "
        "VALUES (:beta, :e, 'email', 'pending', 0, now(), now())",
        {"beta": seeded.beta.id, "e": evento_alpha},
    )
    assert "fk_missing_location_notification_event_same_company" in mensaje, mensaje


async def test_the_fact_cannot_be_deleted_from_under_its_notification(
    seeded, alpha_client
):
    """El hecho no se borra, y el aviso no puede llevárselo por delante.

    `RESTRICT` y el disparador append-only cubren los dos sentidos: el hecho no
    desaparece, y si alguien intentara borrarlo la FK también lo impediría.
    """
    _, viaje = await _jornada_con_viaje(alpha_client, seeded)
    await _crear_missing(alpha_client, viaje["id"])

    mensaje = await _falla(
        "DELETE FROM missing_location_event WHERE company_id = :c",
        {"c": seeded.alpha.id},
    )
    assert "append-only" in mensaje, mensaje
