"""La migración 0014 y su bajada, incluida la que debe negarse.

Lo que importa de esta migración no es que suba —ampliar un `CHECK` es
trivial— sino que **baje con honestidad**. `missing_location_event` es
append-only por disparador, así que una bajada con filas que usen el motivo
nuevo no puede reescribirlas: o se niega con un mensaje útil, o PostgreSQL
falla con un error que no explica nada.
"""
from __future__ import annotations

import subprocess

import pytest
from sqlalchemy import text

from app.database import async_session_maker

pytestmark = pytest.mark.integration

HEAD = "0014_recovery_accuracy"
ANTES = "0013_client_action_key"
NUEVO = "recovery_accuracy_rejected"


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "alembic", "-c", "app/alembic.ini", *args],
        capture_output=True, text=True, shell=False,
    )


async def _version() -> str:
    async with async_session_maker() as s:
        return await s.scalar(text("SELECT version_num FROM alembic_version"))


async def _jornada(company_id: int, user_id: int) -> int:
    """Una jornada real, porque el INSERT de prueba tiene FK compuesta."""
    async with async_session_maker() as s:
        ws = await s.scalar(text(
            "INSERT INTO work_session(company_id,user_id,status,session_date,"
            "started_at,started_received_at,started_at_source,created_at,"
            "updated_at,version) VALUES (:c,:u,'active',current_date,now(),"
            "now(),'device',now(),now(),1) RETURNING id"),
            {"c": company_id, "u": user_id})
        await s.commit()
        return ws


async def _acepta(motivo: str, *, company_id: int, ws: int) -> bool:
    """Si la base acepta ese `reason_code`. Revierte siempre.

    Las claves son reales a proposito. Con ids inventados el INSERT falla por
    la clave foranea y **devuelve `False` para cualquier motivo**, con lo que
    el test del motivo invalido pasaria sin comprobar nada. Ocurrio.
    """
    async with async_session_maker() as s:
        try:
            await s.execute(text(
                "INSERT INTO missing_location_event(company_id,work_session_id,"
                "trip_id,event_kind,subject_kind,subject_id,occurred_at,"
                "reason_code,attempts,created_at,updated_at) "
                "VALUES (:c,:w,NULL,'start_work','work_session',:w,now(),"
                ":m,'[]'::jsonb,now(),now())"),
                {"c": company_id, "w": ws, "m": motivo})
            await s.flush()
            return True
        except Exception as exc:
            # Solo vale como "rechazado" si lo rechazo el CHECK del motivo.
            orig = getattr(exc, "orig", None)
            detalle = str(orig or exc)
            assert "ck_missing_location_reason" in detalle, (
                f"rechazado por otra cosa, no por el motivo: {detalle[:200]}")
            return False
        finally:
            await s.rollback()


@pytest.mark.asyncio
async def test_el_head_acepta_el_motivo_nuevo(seeded) -> None:
    empresa = seeded.alpha
    ws = await _jornada(empresa.id, next(iter(empresa.users.values())).id)
    assert await _version() == HEAD
    # No comprueba sólo que exista el valor: comprueba que la base lo acepta,
    # que es lo que el cliente necesita para poder declararlo.
    assert await _acepta(NUEVO, company_id=empresa.id, ws=ws) is True


@pytest.mark.asyncio
async def test_sigue_rechazando_un_motivo_inventado(seeded) -> None:
    """Ampliar el catálogo no puede convertirlo en texto libre."""
    empresa = seeded.alpha
    ws = await _jornada(empresa.id, next(iter(empresa.users.values())).id)
    assert await _acepta("gps_flojo", company_id=empresa.id, ws=ws) is False


@pytest.mark.asyncio
async def test_roundtrip_sin_filas_que_estorben(seeded) -> None:
    """Baja y sube limpio cuando nadie usa el motivo nuevo."""
    empresa = seeded.alpha
    ws = await _jornada(empresa.id, next(iter(empresa.users.values())).id)
    bajada = _alembic("downgrade", ANTES)
    assert bajada.returncode == 0, bajada.stdout + bajada.stderr
    try:
        assert await _version() == ANTES
        # Tras bajar, el motivo nuevo ya no se acepta.
        assert await _acepta(NUEVO, company_id=empresa.id, ws=ws) is False
    finally:
        subida = _alembic("upgrade", HEAD)
        assert subida.returncode == 0, (
            "la base quedó fuera del head y eso romperia los demas tests:\n"
            + subida.stdout + subida.stderr
        )
    assert await _version() == HEAD


@pytest.mark.asyncio
async def test_la_bajada_se_niega_si_hay_filas_con_el_motivo(seeded) -> None:
    """Y el mensaje tiene que decir cuántas son y cómo verlas.

    `missing_location_event` no admite `UPDATE` ni `DELETE`, así que esas filas
    no se pueden "arreglar". Bajar exigiria inventarles otro motivo, y eso
    seria reescribir un hecho.
    """
    empresa = seeded.alpha
    usuario = next(iter(empresa.users.values()))
    async with async_session_maker() as s:
        ws = await s.scalar(text(
            "INSERT INTO work_session(company_id,user_id,status,session_date,"
            "started_at,started_received_at,started_at_source,created_at,"
            "updated_at,version) VALUES (:c,:u,'active',current_date,now(),"
            "now(),'device',now(),now(),1) RETURNING id"),
            {"c": empresa.id, "u": usuario.id})
        await s.execute(text(
            "INSERT INTO missing_location_event(company_id,work_session_id,"
            "trip_id,event_kind,subject_kind,subject_id,occurred_at,"
            "reason_code,attempts,created_at,updated_at) "
            "VALUES (:c,:w,NULL,'start_work','work_session',:w,now(),"
            ":m,'[]'::jsonb,now(),now())"),
            {"c": empresa.id, "w": ws, "m": NUEVO})
        await s.commit()

    bajada = _alembic("downgrade", ANTES)
    salida = bajada.stdout + bajada.stderr

    assert bajada.returncode != 0, "bajó con filas que usan el motivo nuevo"
    assert "append-only" in salida
    assert NUEVO in salida
    # El mensaje tiene que traer la consulta, no sólo la queja.
    assert "SELECT id, company_id" in salida
    # Y la base se queda donde estaba: un fallo no puede dejarla a medias.
    assert await _version() == HEAD
