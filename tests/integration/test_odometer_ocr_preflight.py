"""
Preflight del odómetro y del OCR, antes de RTE06.

Por qué existe este archivo
---------------------------
La instrucción pide **no** dar por bueno el flujo porque las suites anteriores
estén verdes. Estos tests no añaden funcionalidad: fijan por escrito el estado
as-built de las cosas que RTE04 declaró implementadas, incluida la que **no**
está activa, para que la clasificación del informe se apoye en mediciones y no
en una lectura del código.

Tres preguntas, y la tercera es la importante
----------------------------------------------
1. Con asignación de vehículo vigente, ¿nace la evidencia de inicio `PENDING` y
   bloquea de verdad `Start Trip`?
2. Sin asignación, ¿nace `NOT_REQUIRED` y no bloquea nada? — esa es la
   diferencia entre una regresión y un problema de datos.
3. ¿Qué OCR está enlazado en ejecución real?

La segunda importa tanto como la primera: si un supervisor sin asignación
vigente ve el mismo producto sin captura de odómetro, el síntoma "no aparece el
banner" tiene dos causas posibles y sólo una es un defecto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.odometer.ocr import (
    NoSuggestionReader,
    get_odometer_reader,
    set_odometer_reader,
)


pytestmark = pytest.mark.integration


FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def _restaurar_lector():
    """Deja el registro como estaba: es global al proceso."""
    original = get_odometer_reader()
    yield
    set_odometer_reader(original)


class _LectorFijo:
    """Un adaptador de prueba que sí sugiere. Demuestra que el puerto funciona."""

    def __init__(self, valor: Decimal) -> None:
        self.valor = valor
        self.llamadas = 0

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        self.llamadas += 1
        return self.valor


async def _perfil_y_vehiculo(alpha_client, seeded, *, unidad: str, asignar: bool):
    """Perfil de supervisor y vehículo; la asignación es opcional a propósito."""
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
    if asignar:
        respuesta = await alpha_client.post(
            f"/api/supervisors/{perfil['id']}/assignments",
            json={"vehicle_id": vehiculo["id"]},
        )
        assert respuesta.status_code in (200, 201), respuesta.text
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    return perfil, vehiculo


# ── Pasos 1 a 4: el estado real tras `Start Work` ───────────────────────────


async def test_with_a_current_assignment_the_start_reading_is_pending_and_blocks(
    seeded, alpha_client,
):
    """Pasos 1-4: con asignación vigente, la lectura de inicio es exigible.

    Lo que se fija aquí: la jornada guarda el vehículo, la evidencia de inicio
    nace `pending`, y el servidor **rechaza** `Start Trip` mientras siga sin
    resolverse. Es la condición de la que depende que la pantalla enseñe el
    aviso y la captura.
    """
    _, vehiculo = await _perfil_y_vehiculo(
        alpha_client, seeded, unidad="V-PRE1", asignar=True
    )

    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    # El vehículo queda en la jornada: es lo que decide si hace falta lectura.
    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT vehicle_id, mpg_snapshot FROM work_session WHERE id = :i"
                ),
                {"i": jornada["id"]},
            )
        ).one()
    assert fila.vehicle_id == vehiculo["id"], (
        "sin vehículo en la jornada la evidencia nace NOT_REQUIRED y no hay captura"
    )
    assert fila.mpg_snapshot is not None

    # El estado que lee la pantalla, tal cual.
    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "pending"
    assert estado["start"]["vehicle_id"] == vehiculo["id"]
    assert estado["start"]["confirmed_reading"] is None
    assert estado["start"]["evidence_method"] is None

    # Y el servidor bloquea la salida, que es el control de verdad.
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    rechazo = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert rechazo.status_code == 409, rechazo.text
    assert "odometer" in rechazo.json()["detail"].lower()


async def test_without_a_current_assignment_no_reading_is_required(
    seeded, alpha_client,
):
    """El otro lado, y el que distingue una regresión de un dato mal preparado.

    Un supervisor con perfil pero **sin** asignación vigente tiene una jornada
    igualmente válida: la evidencia nace `not_required` y `Start Trip` no se
    bloquea. Si alguien observa "no aparece el banner", este es el estado que
    hay que descartar antes de llamarlo defecto — el producto se comporta así
    por diseño (§6.1 de RTE04).
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-PRE2", asignar=False)

    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    async with async_session_maker() as session:
        vehiculo_de_la_jornada = await session.scalar(
            text("SELECT vehicle_id FROM work_session WHERE id = :i"),
            {"i": jornada["id"]},
        )
    assert vehiculo_de_la_jornada is None

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "not_required"
    assert estado["start"]["vehicle_id"] is None

    # Y por tanto la salida no se bloquea.
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text


async def test_an_assignment_with_an_end_date_is_not_current(seeded, alpha_client):
    """Qué significa "vigente", medido y no supuesto.

    `current_for_supervisor` considera vigente **la asignación sin fecha de
    fin**. Una cerrada no cuenta, y eso es correcto. Se fija por escrito porque
    es la vía más plausible por la que un supervisor con vehículo "asignado" en
    la pantalla de administración acabe con una jornada sin vehículo.
    """
    perfil, vehiculo = await _perfil_y_vehiculo(
        alpha_client, seeded, unidad="V-PRE3", asignar=True
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    asignaciones = (
        await alpha_client.get(f"/api/supervisors/{perfil['id']}/assignments")
    ).json()
    vigente = next(a for a in asignaciones if a["effective_to"] is None)
    cierre = await alpha_client.post(
        f"/api/supervisors/assignments/{vigente['id']}/end", json={}
    )
    assert cierre.status_code in (200, 204), cierre.text

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    estado = (
        await alpha_client.get(f"/api/odometer/sessions/{jornada['id']}")
    ).json()
    assert estado["start"]["status"] == "not_required", (
        "una asignación cerrada no es vigente, así que no se pide lectura"
    )
    assert vehiculo["id"] is not None


# ── Paso 5: el flujo visible completo, por API ──────────────────────────────


async def test_the_whole_capture_path_persists_photo_confirmed_and_unblocks(
    seeded, alpha_client,
):
    """Paso 5: foto → evidencia → lectura → confirmación → salida desbloqueada.

    Se recorre por API para fijar qué persiste en cada paso. El mismo recorrido
    en navegador ya existe en `test_trip_and_odometer_browser.py`; lo que aquí
    se comprueba es el **contenido** de la evidencia, no la pantalla.
    """
    _, vehiculo = await _perfil_y_vehiculo(
        alpha_client, seeded, unidad="V-PRE4", asignar=True
    )
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    foto = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    assert foto.status_code == 200, foto.text
    cuerpo = foto.json()

    # Con el proveedor por defecto no hay sugerencia, y **no es un error**.
    assert cuerpo["ocr_suggestion"] is None, (
        "el lector por defecto no sugiere; eso es el camino manual normal"
    )

    async with async_session_maker() as session:
        tras_foto = (
            await session.execute(
                text(
                    "SELECT status, storage_key, ocr_detected_reading, "
                    "confirmed_reading FROM odometer_evidence "
                    "WHERE work_session_id = :i AND evidence_type = 'start'"
                ),
                {"i": jornada["id"]},
            )
        ).one()
    # La foto **no** cambia el estado: `PHOTO_UPLOADED` no existe en el enum, y
    # es coherente — una foto sin lectura no es evidencia utilizable. La fila
    # sigue `pending` (y por tanto sigue bloqueando la salida) hasta que el
    # supervisor confirme lo que ve.
    assert tras_foto.status == "pending"
    assert tras_foto.storage_key, "la clave la genera el servidor"
    assert tras_foto.confirmed_reading is None, "la foto no confirma nada por sí sola"

    # La lectura la teclea y confirma el supervisor.
    confirmacion = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "128437.0"},
    )
    assert confirmacion.status_code == 200, confirmacion.text

    async with async_session_maker() as session:
        final = (
            await session.execute(
                text(
                    "SELECT status, evidence_method, confirmed_reading, vehicle_id "
                    "FROM odometer_evidence "
                    "WHERE work_session_id = :i AND evidence_type = 'start'"
                ),
                {"i": jornada["id"]},
            )
        ).one()
    assert final.status == "photo_confirmed"
    assert final.evidence_method == "photo"
    assert str(final.confirmed_reading) == "128437.0"
    assert final.vehicle_id == vehiculo["id"]

    # Y ahora sí se puede salir: es el regreso al viaje que se intentaba iniciar.
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text


# ── Paso 6: auditoría del OCR as-built ─────────────────────────────────────


def test_the_default_reader_is_the_one_wired_at_runtime():
    """Qué OCR está enlazado en ejecución real: **ninguno**.

    `NoSuggestionReader` no es un hueco por rellenar: es la implementación de
    "este despliegue no tiene OCR". Se fija por escrito porque el informe lo
    clasifica, y una clasificación sin medición es una opinión.
    """
    lector = get_odometer_reader()
    assert isinstance(lector, NoSuggestionReader), (
        f"el lector enlazado es {type(lector).__name__}"
    )
    assert lector.suggest(image=FOTO, content_type="image/png") is None


async def test_the_port_works_when_an_adapter_is_plugged_in(seeded, alpha_client):
    """Y el puerto funciona: lo que falta es un adaptador, no el cableado.

    Con un adaptador enchufado, la sugerencia llega a la respuesta y se guarda
    **separada** de la lectura confirmada. Eso es lo que hace que enchufar un
    OCR real sea escribir un adaptador y registrarlo, sin tocar el dominio — y
    es también lo que impide que una sugerencia se confunda con un hecho.
    """
    lector = _LectorFijo(Decimal("99120.0"))
    set_odometer_reader(lector)

    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-PRE5", asignar=True)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()

    cuerpo = (
        await alpha_client.post(
            f"/api/odometer/sessions/{jornada['id']}/start/photo",
            files={"photo": ("odo.png", FOTO, "image/png")},
        )
    ).json()
    assert lector.llamadas == 1, "el flujo real consulta el puerto"
    assert cuerpo["ocr_suggestion"] == "99120.0"

    # El supervisor corrige: la sugerencia no es autoridad.
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "99125.0"},
    )

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT ocr_detected_reading, confirmed_reading, evidence_method "
                    "FROM odometer_evidence "
                    "WHERE work_session_id = :i AND evidence_type = 'start'"
                ),
                {"i": jornada["id"]},
            )
        ).one()
    assert str(fila.ocr_detected_reading) == "99120.0", "la sugerencia se conserva"
    assert str(fila.confirmed_reading) == "99125.0", "y la corrección es la que vale"
    assert fila.evidence_method == "photo"
