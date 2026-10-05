"""La foto del odómetro sobrevive al aparato (RTE10-A01, CP2).

Qué hueco cierra esto
---------------------
El ciclo de vida de la tarea ya sobrevivía a que Android recreara la página:
eso se cerró en RTE06 y sigue verde. Lo que **no** sobrevivía era la fotografía
en sí. Entre que la cámara la devolvía y que el servidor la confirmaba había una
ventana —segundos con una foto de varios megabytes subiendo por una red de
campo— y si la página moría ahí, el supervisor tenía que volver al vehículo a
repetirla. En un teléfono al que Android está matando la pestaña por memoria,
esa ventana es exactamente cuando ocurre.

Ahora la foto se escribe en IndexedDB **antes** de intentar subirla, en el mismo
módulo y la misma base que los otros dos carriles durables, y se retira cuando
el servidor confirma que la tiene.

La propiedad que importa, y que es fácil de romper
---------------------------------------------------
**Nunca se afirma una persistencia que no ocurrió** (FR-08). Es tentador marcar
la foto como subida en cuanto está guardada en el aparato —la pantalla queda más
limpia— y es justo la mentira que costaría una evidencia: el supervisor saldría
a conducir creyendo que su lectura está registrada. Por eso el almacén no tiene
un campo `uploaded`: una entrada significa "tomada, no confirmada", y se borra
al confirmarse.

Cómo se simula la caída de red, y por qué así
----------------------------------------------
Interceptando la ruta de subida y abortando, no con `context.set_offline(True)`.
El mismo motivo que en RTE06: el modo offline de Playwright también bloquea la
petición del documento, y entonces no se puede recargar la página, que es la
mitad de lo que hay que probar.

Límite honesto: esto es Edge de escritorio. **No** sustituye la validación en
hardware Android, que es de CER y sigue fuera de este entorno — en particular,
que Android mate el renderer por memoria no se puede provocar aquí.
"""

from __future__ import annotations

import json

import pytest
from playwright.async_api import expect
from sqlalchemy import select

from app.database import async_session_maker
from app.routers_api.odometer.models import OdometerEvidence
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


FOTO_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

MOVIL = {"width": 390, "height": 844}

CAPTURA = "Take a photo of the odometer, then confirm the reading."
GUARDADA_SIN_SUBIR = "Your photo is saved on this phone."


async def _preparar_vehiculo(alpha_client, seeded, unidad: str) -> None:
    """Supervisor con vehículo asignado, por API (igual que RTE06)."""
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


async def _evidencia(company_id: int, tipo: str = "start") -> OdometerEvidence | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(OdometerEvidence).where(
                OdometerEvidence.company_id == company_id,
                OdometerEvidence.evidence_type == tipo,
            )
        )


async def _jornada_actual(company_id: int):
    """La última jornada de la compañía, para comprobar que sigue abierta."""
    from app.routers_api.worksessions.models import WorkSession

    async with async_session_maker() as session:
        return await session.scalar(
            select(WorkSession)
            .where(WorkSession.company_id == company_id)
            .order_by(WorkSession.id.desc())
            .limit(1)
        )


async def _fotos_en_espera(page) -> list[dict]:
    """Lee el carril durable de fotos tal como lo escribe `offlineQueue`.

    Se abre **sin fijar versión**: pinchar un número aquí convierte el próximo
    almacén nuevo en un fallo de este test, que es lo que ya pasó una vez.
    El Blob no se devuelve —no viaja bien por el puente— pero su tamaño sí, que
    es lo que demuestra que hay una foto de verdad y no una entrada vacía.
    """
    return await page.evaluate(
        """() => new Promise((resolver) => {
            const solicitud = indexedDB.open('cer-route-offline');
            solicitud.onerror = () => resolver([]);
            solicitud.onsuccess = () => {
                const db = solicitud.result;
                if (!db.objectStoreNames.contains('pending_odometer_photos')) {
                    resolver([]);
                    return;
                }
                const tx = db.transaction('pending_odometer_photos', 'readonly');
                const todo = tx.objectStore('pending_odometer_photos').getAll();
                todo.onsuccess = () => resolver(todo.result.map((f) => ({
                    id: f.id,
                    sessionId: f.sessionId,
                    end: f.end,
                    contentType: f.contentType,
                    bytes: f.blob ? f.blob.size : 0,
                    attempts: f.attempts,
                    tieneCampoSubida: Object.hasOwn(f, 'uploaded'),
                })));
                todo.onerror = () => resolver([]);
            };
        })"""
    )


async def _abrir_tarea_de_inicio(page) -> None:
    await page.goto("/route")
    await page.get_by_role("button", name="Start Work").click()
    await expect(
        page.get_by_text("Odometer pending", exact=True)
    ).to_have_count(1, timeout=20_000)
    await page.get_by_role("button", name="Capture before first trip").click()
    await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)


async def _elegir_foto(page) -> None:
    await page.locator('input[type="file"]').set_input_files(
        {"name": "odo.png", "mimeType": "image/png", "buffer": FOTO_PNG}
    )


# ── La foto sobrevive a que la subida no llegue ─────────────────────────────


async def test_la_foto_queda_guardada_cuando_la_subida_no_llega(
    seeded, alpha_client, live_server,
):
    """El caso de campo: se hace la foto sin cobertura y **no se pierde**.

    Las tres cosas que se comprueban juntas, porque separadas no dicen nada:
    la foto está en el aparato con sus bytes, el servidor **no** la tiene, y la
    pantalla dice exactamente eso en vez de afirmar que está subida.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-A")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _abrir_tarea_de_inicio(page)

            # Se corta sólo la subida de la foto: el documento sigue cargando,
            # así que la página se puede recargar después.
            await contexto.route("**/api/odometer/**/photo", lambda ruta: ruta.abort())

            await _elegir_foto(page)

            await expect(
                page.get_by_text(GUARDADA_SIN_SUBIR)
            ).to_have_count(1, timeout=20_000)

            en_espera = await _fotos_en_espera(page)
            assert len(en_espera) == 1, f"no quedó guardada: {en_espera}"
            foto = en_espera[0]
            assert foto["end"] == "start"
            assert foto["bytes"] == len(FOTO_PNG), (
                f"se guardó una entrada sin la foto dentro: {foto}"
            )
            assert foto["tieneCampoSubida"] is False, (
                "el almacén no puede tener un campo `uploaded`: permitiría "
                "marcar como subida una foto que nadie confirmó"
            )

            # El servidor no la tiene, y la pantalla no dice que sí.
            evidencia = await _evidencia(seeded.alpha.id)
            assert evidencia.captured_at is None, (
                "la subida se abortó: no puede haber `captured_at`"
            )
            assert evidencia.storage_key is None

            # Y el campo de lectura no aparece: sin foto en el servidor no hay
            # nada que confirmar, y ofrecerlo sería prometer un camino cerrado.
            await expect(page.locator("#odometer-reading")).to_have_count(0)
        finally:
            await navegador.close()


async def test_la_foto_guardada_sobrevive_a_recrear_la_pagina_y_se_sube_sola(
    seeded, alpha_client, live_server,
):
    """Lo que el supervisor nota: vuelve la cobertura y la foto ya está arriba.

    La secuencia completa de FR-06 y FR-08: se hace la foto sin red, Android
    recrea la página, la red vuelve, y la foto llega al servidor **sin que
    nadie la repita**. Después el carril queda vacío, que es la otra mitad
    —FR-09— porque una foto que ya está en el servidor no tiene que seguir
    ocupando el teléfono.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-B")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _abrir_tarea_de_inicio(page)

            await contexto.route("**/api/odometer/**/photo", lambda ruta: ruta.abort())
            await _elegir_foto(page)
            await expect(
                page.get_by_text(GUARDADA_SIN_SUBIR)
            ).to_have_count(1, timeout=20_000)

            # Android recrea la pestaña. La foto está en IndexedDB, que
            # sobrevive a eso: es la razón de usarlo en vez de estado de React.
            await page.reload()
            await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)
            tras_recargar = await _fotos_en_espera(page)
            assert len(tras_recargar) == 1, (
                f"la foto no sobrevivió a recrear la página: {tras_recargar}"
            )

            # Vuelve la cobertura, y el navegador lo anuncia como lo haría al
            # salir del túnel. No se pulsa el botón de reintento a propósito:
            # lo que FR-06 promete al supervisor es que la foto sube **sola**,
            # y pulsar enmascararía que ese camino no funcionara.
            await contexto.unroute("**/api/odometer/**/photo")
            await page.evaluate("() => window.dispatchEvent(new Event('online'))")

            # Ahora sí: el servidor la tiene y el campo de lectura aparece.
            await expect(page.locator("#odometer-reading")).to_have_count(
                1, timeout=20_000
            )
            evidencia = await _evidencia(seeded.alpha.id)
            assert evidencia.captured_at is not None, "la foto debía haber llegado"
            assert evidencia.storage_key, "y con su clave de almacenamiento"

            # Y la copia local se retira: ya no protege nada.
            await expect(
                page.get_by_text(GUARDADA_SIN_SUBIR)
            ).to_have_count(0, timeout=20_000)
            assert await _fotos_en_espera(page) == [], (
                "la foto confirmada sigue ocupando espacio en el teléfono"
            )
        finally:
            await navegador.close()


async def test_rehacer_la_foto_reemplaza_la_que_estaba_en_espera(
    seeded, alpha_client, live_server,
):
    """La vieja no puede ganar (FR-05 y CP2).

    Dos fotos sin cobertura, una detrás de otra. Si quedaran las dos, el
    reintento podría subir la **descartada** y la evidencia acabaría siendo una
    fotografía que el supervisor rechazó a propósito. La clave del almacén es
    la tupla usuario-jornada-extremo, así que la segunda reemplaza a la primera
    en vez de apilarse.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-C")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _abrir_tarea_de_inicio(page)

            await contexto.route("**/api/odometer/**/photo", lambda ruta: ruta.abort())

            await _elegir_foto(page)
            await expect(
                page.get_by_text(GUARDADA_SIN_SUBIR)
            ).to_have_count(1, timeout=20_000)
            primera = await _fotos_en_espera(page)
            assert len(primera) == 1

            # Rehacerla: el botón ya ofrece "Retake photo" porque hay una foto
            # hecha, aunque todavía no esté subida.
            await expect(
                page.get_by_role("button", name="Retake photo")
            ).to_have_count(1)
            await _elegir_foto(page)
            await expect(
                page.get_by_text(GUARDADA_SIN_SUBIR)
            ).to_have_count(1, timeout=20_000)

            segunda = await _fotos_en_espera(page)
            assert len(segunda) == 1, (
                f"quedaron {len(segunda)} fotos en espera para la misma tarea: "
                f"el reintento podría subir la descartada"
            )
            assert segunda[0]["id"] == primera[0]["id"], (
                "la clave cambió, así que no reemplazó: son dos entradas"
            )
        finally:
            await navegador.close()


async def test_el_campo_de_lectura_no_finge_una_lectura_detectada(
    seeded, alpha_client, live_server,
):
    """FR-04, en la pantalla.

    El campo tenía `placeholder="0"`, y en un recuadro centrado de letra grande
    ese cero gris se lee como una lectura que el teléfono ya detectó. El
    supervisor que lo da por bueno confirma un cero: una evidencia de odómetro
    que dice que el vehículo tiene cero millas.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-D")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _abrir_tarea_de_inicio(page)

            await _elegir_foto(page)
            campo = page.locator("#odometer-reading")
            await expect(campo).to_have_count(1, timeout=20_000)

            # Vacío de verdad, y sin un cero que parezca detectado.
            await expect(campo).to_have_value("")
            marcador = await campo.get_attribute("placeholder")
            assert marcador != "0", (
                "el marcador vuelve a ser un cero: parece una lectura detectada"
            )

            # Y sin lectura no se puede confirmar: el botón no está disponible.
            confirmar = page.get_by_role("button", name="Confirm reading")
            await expect(confirmar).to_be_disabled()
        finally:
            await navegador.close()


# ── El cierre del día: la otra mitad que CP2 exige ──────────────────────────


async def _llegar_a_la_tarea_de_cierre(page) -> None:
    """Hasta `End Work`, resolviendo el inicio por el camino normal.

    El recorrido es el de RTE06 porque es el que el producto impone: no se
    puede pedir la lectura de cierre sin haber salido y vuelto.
    """
    await page.goto("/route")
    await page.get_by_role("button", name="Start Work").click()
    await page.get_by_role("button", name="Return Home").click()
    await page.get_by_role("button", name="Start Trip").click()
    await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)
    await _elegir_foto(page)
    await page.locator("#odometer-reading").fill("90000")
    await page.get_by_role("button", name="Confirm reading").click()
    await page.get_by_role("button", name="Arrived Home").click()
    await expect(page.get_by_text("What's next?")).to_have_count(1, timeout=20_000)
    await page.get_by_role("button", name="End Work").click()
    await expect(page.get_by_text("One last thing")).to_have_count(1, timeout=20_000)


async def test_la_foto_de_cierre_tambien_sobrevive_y_se_sube_sola(
    seeded, alpha_client, live_server,
):
    """END, el mismo contrato que START (PR-04 y CP2).

    Se prueba aparte y entero en vez de parametrizar porque el camino de
    cierre **no** es el de inicio con otra etiqueta: hay que salir, volver y
    pedir `End Work`, y el servidor tiene una guarda propia para la foto
    tardía. Un parámetro habría probado dos veces el mismo recorrido.

    Y se comprueba lo que RTE06 dejó fijado: restaurar la pantalla de cierre
    no puede reabrir la jornada.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-E")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _llegar_a_la_tarea_de_cierre(page)

            # Sin cobertura, se hace la foto de cierre.
            await contexto.route("**/api/odometer/**/photo", lambda ruta: ruta.abort())
            await _elegir_foto(page)
            await expect(
                page.get_by_text(GUARDADA_SIN_SUBIR)
            ).to_have_count(1, timeout=20_000)

            en_espera = await _fotos_en_espera(page)
            assert len(en_espera) == 1, f"no quedó guardada: {en_espera}"
            assert en_espera[0]["end"] == "end", (
                f"se guardó con el extremo equivocado: {en_espera[0]}"
            )
            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.captured_at is None, "la subida se abortó"

            # Android recrea la pestaña, y la foto de cierre sigue ahí.
            await page.reload()
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            assert len(await _fotos_en_espera(page)) == 1, (
                "la foto de cierre no sobrevivió a recrear la página"
            )

            # Vuelve la cobertura y sube sola.
            await contexto.unroute("**/api/odometer/**/photo")
            await page.evaluate("() => window.dispatchEvent(new Event('online'))")
            await expect(page.locator("#odometer-reading")).to_have_count(
                1, timeout=20_000
            )
            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.captured_at is not None, "la foto de cierre debía llegar"
            assert await _fotos_en_espera(page) == [], "la copia local no se limpió"

            # Y restaurar la pantalla de cierre no reabrió el día.
            jornada = await _jornada_actual(seeded.alpha.id)
            assert jornada.status == "active", (
                "la lectura de cierre se pide antes de terminar el día"
            )
        finally:
            await navegador.close()


# ── Caso 10 de §8: la página muere con el OCR en vuelo ─────────────────────


async def test_recrear_la_pagina_con_el_ocr_en_vuelo_no_pierde_la_foto(
    seeded, alpha_client, live_server,
):
    """§8.10, el caso que el OCR añade a la ventana de riesgo.

    Reconocer tarda, y ese tiempo se suma a la subida: la ventana en la que
    Android puede matar la pestaña con la foto a medio camino es ahora más
    larga que antes de este checkpoint. Si la foto no estuviera guardada
    **antes** de la red, activar el OCR habría empeorado justo el problema
    que el checkpoint viene a arreglar.

    La espera se simula retrasando la petición, que es lo que un OCR lento
    produce desde el punto de vista del cliente.
    """
    import asyncio as _asyncio

    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-F")
    supervisor = seeded.alpha.users["supervisor"]

    async def _lenta(ruta):
        await _asyncio.sleep(6)
        await ruta.continue_()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _abrir_tarea_de_inicio(page)

            await contexto.route("**/api/odometer/**/photo", _lenta)
            await _elegir_foto(page)

            # La foto ya está guardada en el aparato aunque la petición siga
            # en vuelo: eso es lo que hace que lo siguiente no la pierda. No se
            # espera a ninguna señal de pantalla porque todavía no hay ninguna:
            # la subida no ha vuelto, y es justo ese instante el que se prueba.
            en_vuelo = await _fotos_en_espera(page)
            assert len(en_vuelo) == 1, (
                f"la foto no se guardó antes de la red: {en_vuelo}"
            )
            assert en_vuelo[0]["bytes"] == len(FOTO_PNG)

            # Y ahora muere, con el reconocimiento a medias.
            await page.reload()
            await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)
            assert len(await _fotos_en_espera(page)) >= 1, (
                "la foto se perdió al recrear la página con el OCR en vuelo"
            )
        finally:
            await navegador.close()


# ── AC-8: una respuesta de OCR que llega tarde no puede ganar ──────────────


def _respuesta_de_foto(sugerencia: str | None, *, version: int) -> dict:
    """Un cuerpo válido para `odometerPhotoResultSchema`, construido a mano.

    Se construye en vez de reenviar el del servidor porque `Route.fetch` no
    sirve en este arnés: resolvería `alpha.localhost` con el resolutor del
    sistema, que no tiene por qué conocer los subdominios de `localhost` —el
    mismo límite que documenta el conftest—. La primera versión de este test
    lo usaba, el manejador reventaba, y el test **pasaba en vacío**: ninguna
    sugerencia llegaba nunca, así que no demostraba nada.

    Cuánta confianza merece un cuerpo escrito aquí lo decide la fase de
    control del test, que comprueba que con este mismo cuerpo la sugerencia
    sí aparece en pantalla. Sin esa fase, un cuerpo que Zod rechazara daría
    otra vez un verde vacío.
    """
    return {
        "evidence": {
            "id": 1,
            "work_session_id": 1,
            "vehicle_id": 1,
            "evidence_type": "start",
            "status": "pending",
            "evidence_method": None,
            "confirmed_reading": None,
            "ocr_detected_reading": sugerencia,
            "captured_at": "2026-10-05T12:00:00+00:00",
            "confirmed_at": None,
            "confirmed_by": None,
            "version": version,
        },
        "ocr_suggestion": sugerencia,
    }


async def test_la_sugerencia_de_la_foto_descartada_no_puede_llegar_tarde_y_ganar(
    seeded, alpha_client, live_server,
):
    """AC-8, ejecutado y con control positivo.

    Por qué la carrera es alcanzable
    ---------------------------------
    El botón se deshabilita durante la subida, así que pulsarlo dos veces no
    produce dos envíos. Pero `setBusy(true)` no es inmediato: entre el primer
    toque y el render que deshabilita el botón hay una ventana, y el `input` de
    tipo fichero puede recibir un segundo fichero sin pasar por el botón. El
    test usa esa vía porque reproduce la ventana sin inventar nada que el
    navegador no pueda hacer.

    Dos fases, y la primera es la que hace creíble a la segunda
    -----------------------------------------------------------
    **Control**: una sola subida, contestada con la sugerencia. Si el campo no
    la muestra, el cuerpo construido no sirve y el test se detiene aquí en vez
    de dar un verde que no significa nada.

    **Carrera**: dos subidas con el orden invertido —la primera contesta tarde
    y con sugerencia, la segunda enseguida y sin ninguna—. Sin el guardia, la
    sugerencia de la foto descartada aterrizaría al final y se quedaría en el
    campo, atada a una fotografía que el supervisor reemplazó.
    """
    import asyncio as _asyncio

    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-RTE10-G")
    supervisor = seeded.alpha.users["supervisor"]

    # Lo que viaja por el cable y lo que se ve en el campo no son la misma
    # cadena: el componente pasa la sugerencia por `readingAsNumber`, así que
    # la décima a cero desaparece al pintarla. Se distinguen las dos para que
    # el test compruebe lo que el supervisor ve de verdad.
    DESCARTADA = "11111.0"
    DESCARTADA_EN_PANTALLA = "11111"

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)
            await _abrir_tarea_de_inicio(page)

            # ── Fase de control ────────────────────────────────────────────
            async def _con_sugerencia(ruta):
                await ruta.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(_respuesta_de_foto(DESCARTADA, version=2)),
                )

            await contexto.route("**/api/odometer/**/photo", _con_sugerencia)
            await _elegir_foto(page)

            campo = page.locator("#odometer-reading")
            await expect(campo).to_have_count(1, timeout=20_000)
            await expect(campo).to_have_value(DESCARTADA_EN_PANTALLA, timeout=20_000), (
                "el cuerpo construido no llega a la pantalla: sin esto, la "
                "segunda fase daría un verde vacío"
            )
            await contexto.unroute("**/api/odometer/**/photo", _con_sugerencia)

            # ── Fase de carrera ────────────────────────────────────────────
            peticiones = {"n": 0}

            async def _desordenar(ruta):
                peticiones["n"] += 1
                if peticiones["n"] == 1:
                    # La foto que el supervisor va a descartar: tarda, y trae
                    # la sugerencia que no debe sobrevivir.
                    await _asyncio.sleep(5)
                    cuerpo = _respuesta_de_foto(DESCARTADA, version=3)
                else:
                    cuerpo = _respuesta_de_foto(None, version=4)
                await ruta.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(cuerpo),
                )

            await contexto.route("**/api/odometer/**/photo", _desordenar)

            await _elegir_foto(page)
            await page.wait_for_timeout(300)
            await _elegir_foto(page)

            # La segunda contesta enseguida y deja el campo vacío.
            await expect(campo).to_have_value("", timeout=20_000)

            # Y ahora se deja llegar a la primera.
            await page.wait_for_timeout(8000)
            assert peticiones["n"] == 2, (
                f"se esperaban dos subidas y hubo {peticiones['n']}"
            )
            await expect(campo).to_have_value("", timeout=5_000)
            # Y no aparece en ningún sitio de la página, no sólo en el campo:
            # la línea "Suggested from the photo: …" también la enseñaría. Se
            # busca por texto en vez de leer la sección entera porque la
            # sección puede haberse remontado, y lo que importa es que el
            # número no esté, no dónde se habría puesto.
            await expect(
                page.get_by_text(DESCARTADA_EN_PANTALLA, exact=False)
            ).to_have_count(0, timeout=5_000)
        finally:
            # Antes de cerrar: este test retrasa una respuesta a propósito y
            # puede quedar un manejador dormido, que al cerrarse el navegador
            # produce un error de cierre sin relación con el producto.
            await contexto.unroute_all(behavior="ignoreErrors")
            await navegador.close()
