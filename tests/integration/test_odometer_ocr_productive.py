"""El OCR productivo en el camino de la foto, y lo que no puede costar nunca.

Qué cambia en RTE10-A01
------------------------
Hasta ahora el proveedor por defecto no sugería nada, así que el camino del OCR
no podía fallar: `NoSuggestionReader` devuelve `None` y no tiene forma de
levantar una excepción. Con un adaptador real —Tesseract, un proceso externo con
su plazo— sí la tiene, y el dominio lo llamaba **directamente** desde
`attach_photo`.

Ese era el defecto que estos tests cierran: la foto se guarda en el almacén
**antes** de consultar el OCR, así que una excepción del lector dejaba el objeto
escrito y la fila de evidencia sin su `storage_key`. El supervisor perdía la
foto que acababa de hacer y se quedaba bloqueado por un fallo del asistente, que
es exactamente lo que PR-02 prohíbe.

La propiedad que se fija
-------------------------
**Que el OCR falle y que el OCR no vea nada producen el mismo efecto visible.**
No hay un error de OCR que el supervisor pueda arreglar, así que mostrárselo
sólo le empujaría hacia una excepción que no necesita. Se registra en el log y
la foto sigue su camino.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.odometer import ocr as puerto_ocr
from app.routers_api.odometer.ocr import get_odometer_reader, set_odometer_reader
from tests.integration.test_odometer import FOTO, _jornada_con_vehiculo


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _restaurar_lector():
    """El registro del lector es global al proceso: se deja como estaba."""
    original = get_odometer_reader()
    yield
    set_odometer_reader(original)


class _LectorQueRevienta:
    """Un OCR que falla. Es el caso que antes costaba la foto."""

    def __init__(self) -> None:
        self.llamadas = 0

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        self.llamadas += 1
        raise RuntimeError("el motor de OCR se cayó")


class _LectorQueSeCuelga:
    """Un OCR que no vuelve. El otro modo de fallo, y el peor.

    Peor porque no produce ningún error: sin plazo, la petición de subida se
    queda abierta para siempre y el supervisor ve una rueda girando sin saber
    que la foto ya está guardada.
    """

    def __init__(self, segundos: float) -> None:
        self.segundos = segundos

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        time.sleep(self.segundos)
        return Decimal("1.0")


class _LectorPorTurnos:
    """Sugiere una cosa distinta en cada llamada. Para probar el *retake*."""

    def __init__(self, *respuestas: Decimal | None) -> None:
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        indice = min(self.llamadas, len(self.respuestas) - 1)
        self.llamadas += 1
        return self.respuestas[indice]


async def _subir(cliente, session_id: int, tipo: str = "start"):
    return await cliente.post(
        f"/api/odometer/sessions/{session_id}/{tipo}/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )


async def _evidencia(seeded, session_id: int, tipo: str = "start") -> dict:
    async with async_session_maker() as sesion:
        fila = (
            await sesion.execute(
                text(
                    "SELECT status, storage_key, ocr_detected_reading, "
                    "confirmed_reading, captured_at FROM odometer_evidence "
                    "WHERE company_id = :c AND work_session_id = :s "
                    "AND evidence_type = :t"
                ),
                {"c": seeded.alpha.id, "s": session_id, "t": tipo},
            )
        ).one()
    return dict(fila._mapping)


# ── PR-02: un OCR roto no bloquea nada ─────────────────────────────────────


@pytest.mark.parametrize("tipo", ["start", "end"])
async def test_un_ocr_que_revienta_no_cuesta_la_foto(seeded, alpha_client, tipo):
    """La foto se guarda, la respuesta llega sin sugerencia, y se puede confirmar.

    Se prueba en los dos extremos porque PR-04 exige la misma semántica en
    `START` y en `END`, y porque el camino de `END` tiene su propia guarda.
    """
    lector = _LectorQueRevienta()
    set_odometer_reader(lector)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    respuesta = await _subir(alpha_client, jornada["id"], tipo)

    assert respuesta.status_code == 200, respuesta.text
    assert lector.llamadas == 1, "el flujo real consultó el puerto"
    assert respuesta.json()["ocr_suggestion"] is None, (
        "un fallo del OCR se presenta igual que no haber visto nada"
    )

    fila = await _evidencia(seeded, jornada["id"], tipo)
    assert fila["storage_key"], (
        "la foto quedó guardada: esto es lo que el defecto perdía"
    )
    assert fila["captured_at"] is not None
    assert fila["ocr_detected_reading"] is None

    # Y el supervisor puede seguir: teclea lo que ve y confirma.
    confirmacion = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/{tipo}/confirm",
        json={"reading": "128437.0"},
    )
    assert confirmacion.status_code == 200, confirmacion.text
    assert confirmacion.json()["evidence_method"] == "photo", (
        "sigue siendo evidencia fotográfica normal: el OCR no la degrada"
    )


async def test_un_ocr_que_se_cuelga_no_bloquea_la_subida(
    seeded, alpha_client, monkeypatch
):
    """Pasado el plazo del puerto, la foto sigue su camino sin sugerencia.

    El plazo se recorta para que el test tarde décimas en vez de quince
    segundos. Lo que se prueba es el mecanismo, y ése es el mismo con cualquier
    número.
    """
    monkeypatch.setattr(puerto_ocr, "TIMEOUT_DEL_PUERTO_SEGUNDOS", 0.2)
    set_odometer_reader(_LectorQueSeCuelga(2.0))
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    comenzado = time.monotonic()
    respuesta = await _subir(alpha_client, jornada["id"])
    tardado = time.monotonic() - comenzado

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ocr_suggestion"] is None
    assert tardado < 1.5, (
        f"la subida esperó {tardado:.1f}s al OCR colgado; el plazo no se aplicó"
    )

    fila = await _evidencia(seeded, jornada["id"])
    assert fila["storage_key"], "la foto se guardó aunque el OCR no contestara"


# ── FR-02 y AC-2: la sugerencia no es autoridad ────────────────────────────


async def test_la_sugerencia_no_confirma_la_lectura_por_si_sola(
    seeded, alpha_client
):
    """Con sugerencia, la evidencia sigue `pending` y sin lectura confirmada.

    Es la propiedad central de PR-01. Si el OCR pudiera dejar la fila
    confirmada, la lectura autoritativa habría dejado de ser la de la persona
    sin que nadie cambiara el contrato.
    """
    set_odometer_reader(_LectorPorTurnos(Decimal("90210.0")))
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    cuerpo = (await _subir(alpha_client, jornada["id"])).json()
    assert cuerpo["ocr_suggestion"] == "90210.0"

    fila = await _evidencia(seeded, jornada["id"])
    assert fila["status"] == "pending", "una sugerencia no resuelve el extremo"
    assert fila["confirmed_reading"] is None, "y no confirma ninguna lectura"
    assert str(fila["ocr_detected_reading"]) == "90210.0", (
        "pero se conserva aparte, para poder comparar máquina y persona"
    )

    # Y la salida sigue bloqueada mientras nadie confirme.
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "client_visit"})
    ).json()
    rechazo = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert rechazo.status_code == 409, rechazo.text


# ── FR-05: rehacer la foto se lleva la sugerencia anterior ─────────────────


async def test_rehacer_la_foto_borra_la_sugerencia_de_la_anterior(
    seeded, alpha_client
):
    """La segunda foto no ve nada, y la sugerencia de la primera **desaparece**.

    Es el caso que de verdad importa de FR-05: si la columna conservara el
    valor de la foto descartada, la evidencia diría que el OCR leyó `90210` en
    una fotografía en la que no leyó nada. Quien revisara después la
    discrepancia entre máquina y persona estaría comparando con un número de
    otra imagen.
    """
    lector = _LectorPorTurnos(Decimal("90210.0"), None)
    set_odometer_reader(lector)
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    primera = (await _subir(alpha_client, jornada["id"])).json()
    assert primera["ocr_suggestion"] == "90210.0"

    segunda = (await _subir(alpha_client, jornada["id"])).json()

    assert lector.llamadas == 2, "el OCR corre contra la foto nueva"
    assert segunda["ocr_suggestion"] is None
    fila = await _evidencia(seeded, jornada["id"])
    assert fila["ocr_detected_reading"] is None, (
        f"quedó la sugerencia de la foto reemplazada: {fila['ocr_detected_reading']}"
    )


async def test_rehacer_la_foto_reemplaza_el_objeto_guardado(seeded, alpha_client):
    """Y la evidencia activa es la foto nueva, no la vieja.

    Una sola fila por jornada y extremo —lo garantiza
    `uq_odometer_evidence_session_type`— así que no hay dos evidencias
    compitiendo: la clave de almacenamiento se reemplaza. Lo que este test
    impide es que un cambio futuro deje la fila apuntando al primer objeto.
    """
    set_odometer_reader(_LectorPorTurnos(None))
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    await _subir(alpha_client, jornada["id"])
    primera = (await _evidencia(seeded, jornada["id"]))["storage_key"]

    await _subir(alpha_client, jornada["id"])
    segunda = (await _evidencia(seeded, jornada["id"]))["storage_key"]

    assert primera and segunda
    assert primera != segunda, (
        "la clave no cambió: la evidencia sigue apuntando a la foto reemplazada"
    )


async def test_la_auditoria_registra_que_sugirio_el_ocr(seeded, alpha_client):
    """Queda por escrito qué dijo la máquina en cada captura.

    Es lo que permite revisar después si el asistente está sugiriendo bien, sin
    tener que fiarse de la impresión de nadie — y es también la única forma de
    detectar que un OCR empezó a equivocarse de forma sistemática.
    """
    set_odometer_reader(_LectorPorTurnos(Decimal("55100.0")))
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    await _subir(alpha_client, jornada["id"])

    fila = await _evidencia(seeded, jornada["id"])
    async with async_session_maker() as sesion:
        eventos = (
            await sesion.execute(
                text(
                    "SELECT action, changes FROM audit_event "
                    "WHERE company_id = :c AND entity_type = 'odometer_evidence' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"c": seeded.alpha.id},
            )
        ).one()
    assert eventos.action == "photo_captured"
    assert eventos.changes["ocr_suggested"]["new"] == "55100.0"
    assert str(fila["ocr_detected_reading"]) == "55100.0"


# ── FR-07: reintentar no puede duplicar la evidencia activa ────────────────


async def test_subir_la_misma_foto_dos_veces_no_duplica_la_evidencia(
    seeded, alpha_client
):
    """Lo que garantiza FR-07, y lo garantiza **la base**, no el cliente.

    Un reintento tras recuperar la cobertura puede llegar cuando el primer
    envío sí había entrado: el aparato no siempre distingue "falló" de "no me
    llegó la respuesta". Si eso creara una segunda evidencia, la jornada
    tendría dos lecturas de inicio compitiendo por ser la buena.

    No hace falta un mecanismo de idempotencia para esto:
    `uq_odometer_evidence_session_type` admite **una sola fila** por jornada y
    extremo, así que el segundo envío reemplaza la clave de almacenamiento de
    la misma fila. Este test fija esa propiedad para que nadie la pierda
    relajando el índice — y para que nadie añada un mecanismo paralelo
    creyendo que falta.
    """
    set_odometer_reader(_LectorPorTurnos(None))
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    primera = await _subir(alpha_client, jornada["id"])
    segunda = await _subir(alpha_client, jornada["id"])
    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text

    async with async_session_maker() as sesion:
        cuantas = await sesion.scalar(
            text(
                "SELECT count(*) FROM odometer_evidence "
                "WHERE company_id = :c AND work_session_id = :s "
                "AND evidence_type = 'start'"
            ),
            {"c": seeded.alpha.id, "s": jornada["id"]},
        )
    assert cuantas == 1, f"hay {cuantas} evidencias de inicio para la misma jornada"


async def test_una_foto_solo_guardada_en_el_aparato_no_confirma_nada(
    seeded, alpha_client
):
    """La mitad de FR-08 que vive en el servidor.

    El cliente puede tener la foto guardada y enseñarlo, pero no puede
    convertirla en una lectura confirmada: sin `storage_key` y sin excepción
    aprobada, confirmar es un 409. Es lo que hace que la honestidad de la
    pantalla no dependa de que la pantalla sea honesta.
    """
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    # Nunca se subió ninguna foto: es el estado del aparato que tiene la suya
    # en espera y todavía no ha podido enviarla.
    intento = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "128437.0"},
    )

    assert intento.status_code == 409, intento.text
    assert "photo" in intento.json()["detail"].lower()


# ── §14 Security: lo que el servidor rechaza ───────────────────────────────


async def test_no_se_puede_subir_una_foto_a_la_jornada_de_otro(
    seeded, alpha_client, beta_client
):
    """La foto de odómetro se sube a **tu** jornada, y sólo a la tuya.

    Importa más desde que la foto se guarda en el aparato: el reintento manda
    la jornada en la URL, así que si el servidor no comprobara de quién es, un
    identificador cambiado a mano subiría evidencia a la jornada de otro — y de
    otro tenant. El aislamiento local por clave es comodidad; esto es el
    control.

    Se espera **404 y no 403**, que es la regla del repositorio: a quien
    pregunta por un recurso de otra compañía no se le confirma que exista.
    """
    set_odometer_reader(_LectorPorTurnos(None))
    jornada = await _jornada_con_vehiculo(alpha_client, seeded)

    # El mismo identificador, pedido desde el otro tenant.
    await beta_client.login(seeded.beta.users["supervisor"].email)
    intruso = await beta_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )

    assert intruso.status_code == 404, intruso.text

    # Y no se escribió nada en absoluto: ni una clave de almacenamiento, ni
    # la fila de evidencia que `ensure_row` habría creado al aceptar la foto.
    # Se consulta con `scalar` y no con `one` a propósito: "no hay fila" es el
    # resultado correcto aquí, y exigir una lo convertiría en un error.
    async with async_session_maker() as sesion:
        claves = (
            await sesion.execute(
                text(
                    "SELECT storage_key FROM odometer_evidence "
                    "WHERE work_session_id = :s AND evidence_type = 'start'"
                ),
                {"s": jornada["id"]},
            )
        ).scalars().all()
    assert all(k is None for k in claves), (
        f"la petición del otro tenant dejó algo escrito: {claves}"
    )
