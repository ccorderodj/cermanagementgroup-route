"""La migración 0011 no puede descartar notas históricas (cierre final, Item B).

Qué decisión fija esto
---------------------
La primera versión contaba las filas con `notes` no vacío y las dejaba caer al
borrar la columna, confiando en que el número en el log bastara. CER lo rechazó:
contar algo antes de destruirlo no es preservarlo.

Ahora la migración **falla antes de tocar el esquema** si existe una sola nota
con contenido. El principio es el de la instrucción: si no se puede preservar el
significado sin inventar un modelo de producto nuevo, hay que detenerse y exigir
revisión explícita en vez de destruir.

Cómo se prueban migraciones aquí
---------------------------------
La suite construye el esquema con `alembic upgrade head`, así que la base de
tests está siempre en el último head. Para ejercitar el comportamiento de 0011
hay que **bajar hasta 0010**, sembrar el caso, y volver a subir. Eso es lo que
hacen estos tests, y por eso restauran el head al terminar aunque fallen: una
base a medias haría fallar todo lo que venga después por una razón ajena.
"""

from __future__ import annotations

import subprocess
import sys
from uuid import uuid4
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import async_session_maker

pytestmark = pytest.mark.integration


RAIZ = Path(__file__).resolve().parents[2]
HEAD = "head"
ANTES_DE_0011 = "0010_location_and_mileage"


def _alembic(*args: str) -> subprocess.CompletedProcess:
    """Lanza Alembic como proceso, igual que el conftest de la suite.

    Como proceso y no en el mismo intérprete a propósito: la migración escribe
    en su propia conexión y con su propio motor, y mezclarla con el del test
    produciría bloqueos difíciles de leer.
    """
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "app/alembic.ini", *args],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )


@pytest.fixture
async def en_0010(database_schema):
    """Deja la base en 0010, y la devuelve al head al terminar **pase lo que pase**."""
    bajada = _alembic("downgrade", ANTES_DE_0011)
    assert bajada.returncode == 0, bajada.stdout + bajada.stderr
    try:
        yield
    finally:
        # Las notas que **este** test sembro se vacian antes de subir.
        #
        # No es un atajo: es el propio preflight de 0011 funcionando. Un test que
        # deja una nota con contenido bloquea cualquier `upgrade` posterior, que
        # es exactamente lo que tiene que pasar en produccion. Vaciarlas aqui es
        # la remediacion documentada, aplicada al dato de prueba.
        if await _existe_columna("missing_location_event", "notes"):
            async with async_session_maker() as sesion:
                await sesion.execute(
                    text("UPDATE missing_location_event SET notes = NULL")
                )
                await sesion.commit()
        subida = _alembic("upgrade", HEAD)
        assert subida.returncode == 0, (
            "la base quedo fuera del head y eso romperia los demas tests:\n"
            + subida.stdout
            + subida.stderr
        )


async def _sembrar_hecho(*, notas: str | None, estado: str = "pending") -> int:
    """Un `missing_location_event` en el esquema de 0010, con sus columnas viejas.

    **Autosuficiente a propósito.** No usa el fixture `seeded`: ése siembra con
    los modelos de Python, que viven en el head y referencian columnas que en
    0010 no existen. Así que la compañía, el usuario y la jornada se crean aquí
    por SQL, que es lo único que funciona igual en las dos versiones del
    esquema.

    Todo por SQL directo por el mismo motivo: en 0010 el modelo de
    `MissingLocationEvent` ya no coincide con la tabla.
    """
    async with async_session_maker() as sesion:
        # Nombre y subdominio únicos por llamada: los dos llevan índice único y
        # varios de estos tests siembran en la misma base.
        sufijo = uuid4().hex[:10]
        company_id = await sesion.scalar(
            text(
                "INSERT INTO company (name, subdomain, is_active, created_at, "
                " updated_at) VALUES (:nom, :sub, true, now(), now()) "
                "RETURNING id"
            ),
            {"nom": f"Migracion {sufijo}", "sub": f"mig{sufijo}"},
        )
        usuario = await sesion.scalar(
            text(
                'INSERT INTO "user" (username, email, first_name, last_name, '
                ' password, is_active, is_superuser, created_at, updated_at) '
                "VALUES (:u, :e, 'Mig', 'Racion', 'x', true, false, now(), now()) "
                "RETURNING id"
            ),
            {"u": f"mig{sufijo}", "e": f"mig{sufijo}@example.com"},
        )
        jornada = await sesion.scalar(
            text(
                "INSERT INTO work_session (company_id, user_id, status, "
                " session_date, started_at, started_received_at, "
                " started_at_source, created_at, updated_at, version) "
                "VALUES (:c, :u, 'ended', current_date, now(), now(), "
                " 'server_receipt', now(), now(), 1) RETURNING id"
            ),
            {"c": company_id, "u": usuario},
        )

        # El disparador de 0010 admite `UPDATE` de las columnas de aviso pero no
        # bloquea el `INSERT`, así que sembrar es legítimo.
        fila = await sesion.scalar(
            text(
                "INSERT INTO missing_location_event (company_id, work_session_id, "
                " event_kind, subject_kind, subject_id, occurred_at, reason_code, "
                " attempts, notification_status, notes, created_at, updated_at) "
                "VALUES (:c, :w, 'start_work', 'work_session', :w, now(), "
                " 'acquisition_timeout', '[]'::jsonb, :st, :n, now(), now()) "
                "RETURNING id"
            ),
            {"c": company_id, "w": jornada, "st": estado, "n": notas},
        )
        await sesion.commit()
        return fila


async def _existe_columna(tabla: str, columna: str) -> bool:
    async with async_session_maker() as sesion:
        return bool(
            await sesion.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": tabla, "c": columna},
            )
        )


async def _existe_tabla(tabla: str) -> bool:
    async with async_session_maker() as sesion:
        return bool(
            await sesion.scalar(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
                ),
                {"t": tabla},
            )
        )


# ── M1: sin notas históricas ────────────────────────────────────────────────


async def test_m1_without_historical_notes_the_migration_completes(en_0010):
    """M1: sin notas, la migración sube, separa el aviso y endurece el hecho."""
    fila = await _sembrar_hecho(notas=None, estado="notified")

    resultado = _alembic("upgrade", HEAD)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    # Las columnas de aviso ya no están en el hecho.
    assert not await _existe_columna("missing_location_event", "notification_status")
    assert not await _existe_columna("missing_location_event", "notes")
    assert await _existe_tabla("missing_location_notification")

    # Y el estado se **movió**, no se perdió.
    async with async_session_maker() as sesion:
        aviso = (
            await sesion.execute(
                text(
                    "SELECT channel, status, delivered_at FROM "
                    "missing_location_notification WHERE missing_location_event_id = :i"
                ),
                {"i": fila},
            )
        ).first()
    assert aviso is not None, "el estado de aviso tenía que migrarse"
    assert aviso.channel == "in_platform"
    assert aviso.status == "notified"
    assert aviso.delivered_at is not None, (
        "`notified` migra con su fecha de entrega, que el CHECK exige"
    )

    # El hecho quedó estrictamente inmutable.
    async with async_session_maker() as sesion:
        with pytest.raises(Exception) as fallo:
            await sesion.execute(
                text(
                    "UPDATE missing_location_event SET reason_code = "
                    "'permission_denied' WHERE id = :i"
                ),
                {"i": fila},
            )
            await sesion.commit()
    assert "append-only" in str(fallo.value)


# ── M2: con una nota histórica ──────────────────────────────────────────────


async def test_m2_a_single_historical_note_stops_the_migration(en_0010):
    """M2: una sola nota con contenido **detiene** la migración, y no se pierde.

    Lo que se comprueba no es sólo que falle: es que **no queda estado a
    medias**. Alembic corre en una transacción, así que el `RuntimeError` deja
    la base exactamente como estaba — con sus columnas, sin la tabla nueva, y
    con la nota intacta.
    """
    fila = await _sembrar_hecho(notas="Revisado con el supervisor el 3 de marzo")

    resultado = _alembic("upgrade", HEAD)
    assert resultado.returncode != 0, "la migración tenía que detenerse"

    salida = resultado.stdout + resultado.stderr
    assert "0011 ABORTADA" in salida, salida[-1500:]
    assert "1 fila" in salida, "tiene que decir cuántas son"
    assert "SELECT id, company_id, event_kind" in salida, (
        "y cómo encontrarlas, o el operador no puede actuar"
    )

    # Nada a medias: el esquema de 0010 sigue en pie.
    assert await _existe_columna("missing_location_event", "notes")
    assert await _existe_columna("missing_location_event", "notification_status")
    assert not await _existe_tabla("missing_location_notification")

    # Y la nota sigue ahí, palabra por palabra.
    async with async_session_maker() as sesion:
        nota = await sesion.scalar(
            text("SELECT notes FROM missing_location_event WHERE id = :i"),
            {"i": fila},
        )
    assert nota == "Revisado con el supervisor el 3 de marzo"


async def test_m2_whitespace_only_notes_do_not_block(en_0010):
    """Una nota que sólo tiene espacios no es contenido, y no detiene nada.

    El preflight usa `btrim(notes) <> ''` a propósito: bloquear el despliegue por
    una columna con un espacio sería un falso positivo que obligaría a
    intervenir sin que hubiera nada que preservar.
    """
    await _sembrar_hecho(notas="   ")

    resultado = _alembic("upgrade", HEAD)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert not await _existe_columna("missing_location_event", "notes")


async def test_m2_the_migration_resumes_after_remediation(en_0010):
    """Cómo se reanuda: se vacía la nota y se vuelve a lanzar. Nada que deshacer.

    Es la mitad del Item B que un test de "falla" no cubre: que el camino de
    salida exista y funcione.
    """
    fila = await _sembrar_hecho(notas="texto que alguien tiene que decidir")

    primera = _alembic("upgrade", HEAD)
    assert primera.returncode != 0

    # Remediación: el operador decidió qué hacer con el texto y vació la columna.
    async with async_session_maker() as sesion:
        await sesion.execute(
            text("UPDATE missing_location_event SET notes = NULL WHERE id = :i"),
            {"i": fila},
        )
        await sesion.commit()

    segunda = _alembic("upgrade", HEAD)
    assert segunda.returncode == 0, segunda.stdout + segunda.stderr
    assert not await _existe_columna("missing_location_event", "notes")
    assert await _existe_tabla("missing_location_notification")


# ── M3: estado de aviso desconocido ────────────────────────────────────────


async def test_m3_an_unknown_notification_status_migrates_explicitly(en_0010):
    """M3: un estado que el enum nuevo no conoce migra como `pending`, y se cuenta.

    No debería existir —el `CHECK` anterior lo impedía— pero si apareciera,
    dejarlo caer en silencio sería perder el dato. **Ninguna fila desaparece.**
    """
    async with async_session_maker() as sesion:
        # Se retira el CHECK de 0010 para poder sembrar el caso imposible. Es una
        # excepción de la infraestructura de pruebas, no un camino del producto:
        # con el CHECK puesto, ese estado no puede existir.
        #
        # No se restaura después a propósito: la migración 0011 lo retira de
        # todas formas al borrar la columna, y volver a ponerlo aquí fallaría
        # porque la fila sembrada lo viola.
        await sesion.execute(
            text(
                "ALTER TABLE missing_location_event "
                "DROP CONSTRAINT IF EXISTS ck_missing_location_notification"
            )
        )
        await sesion.commit()

    # "desconocido" y no algo mas largo: la columna es varchar(20).
    fila = await _sembrar_hecho(notas=None, estado="desconocido")

    resultado = _alembic("upgrade", HEAD)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    salida = resultado.stdout + resultado.stderr
    assert "con estado desconocido migradas como pending" in salida
    assert "1 con estado desconocido" in salida, "el número tiene que aparecer"

    async with async_session_maker() as sesion:
        aviso = (
            await sesion.execute(
                text(
                    "SELECT status FROM missing_location_notification "
                    "WHERE missing_location_event_id = :i"
                ),
                {"i": fila},
            )
        ).first()
    assert aviso is not None, "la fila no puede desaparecer"
    assert aviso.status == "pending"


# ── M4 y M5: ida y vuelta, y roundtrip ─────────────────────────────────────


async def test_m4_upgrade_downgrade_upgrade_is_clean(en_0010):
    """M4: subir, bajar y volver a subir, con el estado de aviso de vuelta.

    La bajada devuelve el estado a la columna **antes** de tirar la tabla; al
    revés se perdería. Eso es lo que esta ida y vuelta comprueba.
    """
    fila = await _sembrar_hecho(notas=None, estado="notified")

    assert _alembic("upgrade", "0011_strict_missing_fact").returncode == 0
    assert _alembic("downgrade", ANTES_DE_0011).returncode == 0

    async with async_session_maker() as sesion:
        vuelto = (
            await sesion.execute(
                text(
                    "SELECT notification_status, notified_at FROM "
                    "missing_location_event WHERE id = :i"
                ),
                {"i": fila},
            )
        ).first()
    assert vuelto.notification_status == "notified", (
        "el estado volvió a la columna: la bajada no lo pierde"
    )
    assert vuelto.notified_at is not None

    assert _alembic("upgrade", HEAD).returncode == 0


async def test_m5_the_schema_roundtrip_proposes_nothing(database_schema):
    # El autogenerate se niega a correr si la base no está en head, y los tests
    # anteriores la mueven. Se asegura aquí en vez de depender del orden.
    assert _alembic("upgrade", HEAD).returncode == 0
    """M5: el autogenerate no propone nada tras las migraciones nuevas.

    Si propusiera algo, el modelo y el esquema habrían divergido, y una de las
    dos cosas sería mentira.
    """
    generada = _alembic("revision", "--autogenerate", "-m", "roundtrip_check")
    assert generada.returncode == 0, generada.stdout + generada.stderr

    versiones = RAIZ / "app" / "migrations" / "versions"
    candidatas = sorted(versiones.glob("*roundtrip_check.py"))
    assert candidatas, generada.stdout + generada.stderr
    try:
        cuerpo = candidatas[-1].read_text(encoding="utf-8")
        operaciones = [
            linea.strip()
            for linea in cuerpo.splitlines()
            if linea.strip().startswith(("op.create", "op.drop", "op.add", "op.alter"))
        ]
        assert operaciones == [], "el esquema y los modelos divergieron:\n" + "\n".join(
            operaciones
        )
    finally:
        for c in candidatas:
            c.unlink()
