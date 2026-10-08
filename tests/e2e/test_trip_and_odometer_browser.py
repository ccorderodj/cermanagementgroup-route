"""
Los trece flujos de navegador que pide RTE04-C5, en un navegador real.

Por qué van agrupados en recorridos y no uno por test
------------------------------------------------------
No es por ahorrar: es que el arnés no permite otra cosa. `seeded` resiembra
entre tests —los identificadores de compañía cambian— y el `uvicorn` de al lado
cachea la resolución de tenant sesenta segundos, así que un segundo test del
mismo módulo autenticaría contra una compañía que ya no existe y fallaría con un
401 que no señala ningún defecto del producto. Cada recorrido levanta su propio
servidor y empieza con la caché vacía.

Y resulta ser la forma correcta de describir esto, porque el odómetro sólo tiene
sentido dentro de la secuencia del día: la lectura de inicio importa *porque*
después hay que salir, y la de cierre *porque* antes se condujo.

Por qué no hay un solo `data-testid`
-------------------------------------
El build de producción los elimina a propósito
(`configwebpack/build/loaders/buildBabelLoader.ts`), y estos tests validan el
bundle de producción, no uno de desarrollo. Así que se anclan en lo que ve una
persona —texto y rol— y en los `id` de los campos, que sobreviven a la
minificación. Resulta ser lo correcto además de lo único posible: un test que
sigue pasando cuando la etiqueta que lee el supervisor cambió de significado no
está validando la pantalla.

Qué se comprueba contra la base y qué contra la pantalla
---------------------------------------------------------
El estado real se lee en PostgreSQL. La pantalla se comprueba para lo que sólo
la pantalla puede demostrar: que el aviso aparece sin bloquear, que el contexto
del viaje sigue debajo mientras se resuelve la foto, y que al terminar se vuelve
a ese mismo viaje sin volver a elegir destino.

Límite honesto: esto es Edge de escritorio en Windows con viewport de teléfono.
**No** sustituye la validación en hardware iOS/Android real, que sigue
`PENDING VALIDATION`.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from sqlalchemy import func, select, text

from app.database import async_session_maker
from app.routers_api.odometer.models import OdometerEvidence
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


#: Un PNG de 1x1. Lo que se valida es el flujo de evidencia, no la fotografía.
FOTO_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

MOVIL = {"width": 390, "height": 844}


# ── Preparación de datos, por API, no por pantalla ──────────────────────────


async def _preparar_vehiculo(alpha_client, seeded, unidad: str) -> None:
    """Deja al supervisor con vehículo asignado.

    Se hace por API a propósito: administrar la flota ya tiene su propia
    validación de navegador (RTE02-A01), y repetirla aquí alargaría cada
    recorrido sin demostrar nada nuevo.
    """
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


async def _sembrar_motivos(alpha_client, seeded) -> None:
    """Un valor en la lista de motivos de visita a empleado.

    Employee Visit exige su motivo **antes** de salir, así que sin al menos un
    valor configurado el recorrido no podría completarse — y eso es exactamente
    la regla que se quiere ejercitar, no un obstáculo del arnés.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "employee_visit_reasons", "label": "Payroll question"},
    )
    assert respuesta.status_code == 200, (
        f"la siembra del motivo falló: {respuesta.status_code} {respuesta.text}"
    )


async def _estado_del_viaje(company_id: int) -> tuple[str, str] | None:
    async with async_session_maker() as session:
        fila = await session.scalar(
            select(Trip)
            .where(Trip.company_id == company_id)
            .order_by(Trip.id.desc())
            .limit(1)
        )
    return (fila.status, fila.current_purpose) if fila else None


async def _evidencia(company_id: int, tipo: str) -> OdometerEvidence | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(OdometerEvidence).where(
                OdometerEvidence.company_id == company_id,
                OdometerEvidence.evidence_type == tipo,
            )
        )


async def _jornada(company_id: int) -> WorkSession | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(WorkSession)
            .where(WorkSession.company_id == company_id)
            .order_by(WorkSession.id.desc())
            .limit(1)
        )


async def _capturar_odometro(page, lectura: str) -> None:
    """Sube la foto y confirma la lectura, como lo hace una persona.

    El `input` está oculto porque el botón visible es el que abre la cámara;
    `set_input_files` funciona igual sobre él, que es lo que hace el navegador
    cuando alguien elige una foto.
    """
    await expect(page.get_by_text("Take a photo of the odometer, then confirm the reading.")).to_have_count(1, timeout=20_000)
    await page.locator('input[type="file"]').set_input_files(
        {"name": "odo.png", "mimeType": "image/png", "buffer": FOTO_PNG}
    )
    campo = page.locator("#odometer-reading")
    await expect(campo).to_have_count(1, timeout=20_000)
    await campo.fill(lectura)
    await page.get_by_role("button", name="Confirm reading").click()


# ── Recorrido A: flujos 1, 7, 2, 3 ──────────────────────────────────────────


async def test_start_work_odometer_start_trip_change_plan_and_arrived(
    seeded, alpha_client, live_server,
):
    """Flujos 1, 7, 2 y 3 en una sola jornada.

    1. Start Work → elegir contexto → dato obligatorio → odómetro → Start Trip.
    7. Foto de inicio + confirmación manual (el OCR no sugiere nada, y es normal).
    2. En ruta → Change Plan → **el mismo** viaje continúa.
    3. Llegada operativa → se queda en `arrived`, sin fabricar actividad.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-BR1")
    await _sembrar_motivos(alpha_client, seeded)
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await expect(page.get_by_text("Ready to start your day?")).to_have_count(
                1, timeout=20_000
            )
            await page.get_by_role("button", name="Start Work").click()

            # El aviso aparece **y no bloquea**: el botón principal sigue siendo
            # elegir destino, no fotografiar.
            await expect(page.get_by_text("Odometer pending", exact=True)).to_have_count(
                1, timeout=20_000
            )
            await expect(page.get_by_text("Capture before first trip")).to_have_count(1)
            await expect(
                page.get_by_text("What's next?")
            ).to_have_count(1)

            # ── Contexto con dato obligatorio antes de salir ────────────────
            await page.get_by_role("button", name="Employee Visit").click()
            await page.get_by_role("combobox").click()
            await page.get_by_role("option", name="Payroll question").click()
            await page.get_by_role("button", name="Start Trip").click()

            # La lectura se pide **antes de crear nada**: pulsar `Start Trip` con
            # el odómetro pendiente lleva a la captura, y en ese momento todavía
            # no hay viaje. Antes se creaba el `PLANNING` primero y la lectura se
            # resolvía encima; el cierre 003 (PD-05) fusionó preparar y salir en
            # una pulsación, así que un bloqueo previsible ya no deja un viaje a
            # medio crear.
            await expect(page.get_by_text("Take a photo of the odometer, then confirm the reading.")).to_have_count(1, timeout=20_000)
            assert await _estado_del_viaje(seeded.alpha.id) is None, (
                "sin lectura no se crea el viaje"
            )

            await _capturar_odometro(page, "128437")

            # Resuelta la lectura, el viaje sale solo: la interrupción fue del
            # sistema, no del supervisor, y no se le hace volver a elegir.
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)
            evidencia = await _evidencia(seeded.alpha.id, "start")
            assert evidencia.status == "photo_confirmed"
            assert evidencia.evidence_method == "photo"
            assert str(evidencia.confirmed_reading) == "128437.0"
            assert evidencia.ocr_detected_reading is None, (
                "sin OCR no hay sugerencia, y la evidencia sigue siendo fotográfica"
            )
            estado, _ = await _estado_del_viaje(seeded.alpha.id)
            assert estado == "in_transit"

            # ── Change Plan: el mismo viaje, no uno nuevo ──────────────────
            async with async_session_maker() as session:
                antes = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )

            await page.get_by_role("button", name="Change Plan").click()
            # `old expectation` — el formulario abría con el plan actual y había
            # que pulsar "Change" para volver a la lista.
            # `approved decision` — PD-07 del cierre 003: cambiar de plan
            # reutiliza las mismas siete opciones del workbench.
            # `new expectation` — las opciones están **ya**, sin paso previo.
            await expect(
                page.get_by_role("button", name="Client Visit")
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Update plan").click()

            await expect(page.get_by_text("Originally:")).to_have_count(
                1, timeout=20_000
            )
            async with async_session_maker() as session:
                despues = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )
            assert despues == antes, "cambiar el plan no crea otro viaje"
            estado, proposito = await _estado_del_viaje(seeded.alpha.id)
            assert (estado, proposito) == ("in_transit", "client_visit")

            # El plan original sobrevive: es append-only.
            async with async_session_maker() as session:
                cambios = await session.scalar(
                    text(
                        "SELECT count(*) FROM trip_purpose_change "
                        "WHERE company_id = :c"
                    ),
                    {"c": seeded.alpha.id},
                )
            assert cambios == 1

            # ── Llegada operativa: se queda ahí ────────────────────────────
            await page.get_by_role("button", name="Arrived", exact=True).click()
            await expect(page.get_by_text("Arrived at")).to_have_count(1, timeout=20_000)

            estado, _ = await _estado_del_viaje(seeded.alpha.id)
            assert estado == "arrived", (
                "llegar no cierra el viaje: lo cierra terminar o marcharse"
            )

            # `old expectation` — la pantalla mostraba el marcador "RTE05" que
            # decía honestamente que lo de después no estaba construido.
            # `approved decision` — RTE05 construyó el flujo post-llegada y el
            # marcador desapareció con él; el cierre 003 confirma que llegar
            # entra en ese flujo y no vuelve al workbench (FR-07).
            # `new expectation` — lo que hay es la parada: su selector de
            # actividades, y ninguna salida de jornada (PD-03).
            await expect(page.get_by_text("What are you doing here?")).to_have_count(
                1, timeout=20_000
            )
            await expect(page.get_by_text("What's next?")).to_have_count(0)
            await expect(page.get_by_role("button", name="End Work")).to_have_count(0)

            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "active"
        finally:
            await navegador.close()


# ── Recorrido B: flujos 4, 5, 6 ─────────────────────────────────────────────


async def test_home_closes_the_trip_and_state_survives_reload_and_second_device(
    seeded, alpha_client, live_server,
):
    """Flujos 4, 5 y 6.

    4. HOME → Arrived Home → viaje `closed`, jornada sigue `active`.
    5. Recargar reanuda el viaje vivo.
    6. Un segundo dispositivo resuelve **el mismo** viaje, sin crear otro.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-BR2")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("Odometer pending", exact=True)).to_have_count(
                1, timeout=20_000
            )

            await page.get_by_role("button", name="Return Home").click()
            await page.get_by_role("button", name="Start Trip").click()
            await _capturar_odometro(page, "500")
            await expect(
                page.get_by_role("button", name="Arrived Home")
            ).to_have_count(1, timeout=20_000)

            # ── Flujo 5: recargar reanuda ──────────────────────────────────
            await page.reload()
            await expect(
                page.get_by_role("button", name="Arrived Home")
            ).to_have_count(1, timeout=20_000)

            # ── Flujo 6: un segundo dispositivo, el mismo viaje ────────────
            async with async_session_maker() as session:
                viajes_antes = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )

            segundo = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            otra = await segundo.new_page()
            await abrir_sesion(otra, supervisor.email)
            await otra.goto("/route")
            await expect(
                otra.get_by_role("button", name="Arrived Home")
            ).to_have_count(1, timeout=20_000)

            async with async_session_maker() as session:
                viajes_despues = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )
            assert viajes_despues == viajes_antes, (
                "el segundo dispositivo resuelve el viaje existente, no crea otro"
            )
            await segundo.close()

            # ── Flujo 4: llegar a casa cierra el viaje, no el día ──────────
            await page.get_by_role("button", name="Arrived Home").click()
            await expect(
                page.get_by_text("What's next?")
            ).to_have_count(1, timeout=20_000)

            estado, proposito = await _estado_del_viaje(seeded.alpha.id)
            assert (estado, proposito) == ("closed", "home")
            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "active", (
                "llegar a casa no termina la jornada: puede volver a salir"
            )
        finally:
            await navegador.close()


# ── Recorrido C: flujos 8, 9 ────────────────────────────────────────────────


async def test_start_exception_blocks_the_trip_until_an_admin_approves_it(
    seeded, alpha_client, live_server,
):
    """Flujos 8 y 9.

    8. Excepción sin foto → el viaje sigue bloqueado.
    9. El Admin aprueba → una entrada manual → el viaje ya puede salir.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-BR3")
    supervisor = seeded.alpha.users["supervisor"]
    admin = seeded.alpha.users["route_admin"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            movil = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await movil.new_page()
            await abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Start Trip").click()

            # ── Flujo 8: pedir la excepción ────────────────────────────────
            await expect(page.get_by_text("Take a photo of the odometer, then confirm the reading.")).to_have_count(
                1, timeout=20_000
            )
            await page.get_by_role("button", name="I can't take a photo").click()
            await expect(
                page.get_by_text("Why can't you take the photo?")
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("combobox").click()
            await page.get_by_role("option", name="The camera is not working").click()
            await page.get_by_role("button", name="Send request").click()

            # Esperando revisión, y lo dice con esas palabras: se puede seguir
            # trabajando, pero no salir.
            await expect(page.get_by_text("waiting for review")).to_have_count(
                1, timeout=20_000
            )
            await expect(
                page.get_by_role("button", name="Start Trip")
            ).to_have_count(0)

            evidencia = await _evidencia(seeded.alpha.id, "start")
            assert evidencia.status == "exception_requested"
            assert evidencia.confirmed_reading is None

            # ── Flujo 9: el Admin decide, en su propio contexto ────────────
            escritorio = await navegador.new_context(
                base_url=live_server, viewport={"width": 1280, "height": 800}
            )
            pagina_admin = await escritorio.new_page()
            await abrir_sesion(pagina_admin, admin.email)
            await pagina_admin.goto("/admin/route/odometer-exceptions")

            await expect(
                pagina_admin.get_by_role("heading", name="Odometer Exceptions")
            ).to_have_count(1, timeout=20_000)
            # Nombre y vehículo, no identificadores: quien decide tiene que
            # saber sobre quién decide.
            fila = pagina_admin.locator("tr", has_text="Supervisor Tester")
            await expect(fila).to_have_count(1, timeout=20_000)
            await expect(fila.get_by_text("V-BR3", exact=True)).to_have_count(1)
            await expect(fila.get_by_text("Start of day", exact=True)).to_have_count(1)

            await fila.get_by_role("button", name="Approve").click()
            await expect(
                pagina_admin.get_by_text("Nothing waiting for review.")
            ).to_have_count(1, timeout=20_000)

            async with async_session_maker() as session:
                situacion = await session.scalar(
                    text(
                        "SELECT status FROM odometer_exception_request "
                        "WHERE company_id = :c"
                    ),
                    {"c": seeded.alpha.id},
                )
            assert situacion == "approved"
            await escritorio.close()

            # ── El supervisor teclea su lectura, una vez ───────────────────
            #
            # Al recargar se vuelve al workbench: el destino que había elegido
            # vivía en la memoria de la página y se fue con ella. No se perdió
            # nada del dominio —no había viaje creado, que es justo lo que
            # busca PD-05—, así que la lectura se retoma desde el aviso.
            await page.reload()
            await expect(page.get_by_text("Odometer ready to enter")).to_have_count(
                1, timeout=20_000
            )
            # Sin `data-testid`: el build de producción los elimina. El aviso
            # es un botón y su nombre accesible lleva ese texto.
            await page.get_by_role(
                "button", name="Odometer ready to enter"
            ).click()

            campo = page.locator("#odometer-reading")
            await expect(campo).to_have_count(1, timeout=20_000)
            await campo.fill("77000")
            await page.get_by_role("button", name="Confirm reading").click()

            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )

            evidencia = await _evidencia(seeded.alpha.id, "start")
            assert evidencia.status == "manual_exception_confirmed"
            assert evidencia.evidence_method == "manual_no_photo", (
                "una lectura sin foto no puede parecer evidencia fotográfica"
            )

            # Y con la lectura resuelta, el viaje sale en una sola pulsación.
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)
            estado, _ = await _estado_del_viaje(seeded.alpha.id)
            assert estado == "in_transit"
        finally:
            await navegador.close()


# ── Recorrido D: flujo 10 ───────────────────────────────────────────────────


async def test_end_work_asks_for_the_ending_reading_and_resolves_the_distance(
    seeded, alpha_client, live_server,
):
    """Flujo 10: el camino normal de cierre, con foto, y la distancia resuelta.

    `old expectation` — se llegaba a la lectura de cierre pulsando `End Work`
    con el viaje en ruta y aceptando la revisión de D-07.

    `approved decision` — PD-03 del cierre 003: conduciendo no se ofrece
    terminar el día.

    `new expectation` — se llega por el camino aprobado. Volver a casa cierra su
    viaje al llegar, devuelve al workbench, y desde ahí se termina el día. Lo que
    este test comprueba —que la lectura de cierre se pide antes de cerrar y que
    la distancia sale de las dos lecturas— no cambia. La regla de dominio de
    D-07 sigue cubierta en
    `test_trips.py::test_end_work_anyway_interrupts_without_faking_an_arrival`.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-BR4")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await page.get_by_role("button", name="Return Home").click()
            await page.get_by_role("button", name="Start Trip").click()
            await _capturar_odometro(page, "90000")
            await page.get_by_role("button", name="Arrived Home").click()

            # Volver a casa cierra su viaje al llegar: se vuelve al workbench,
            # que es desde donde se termina el día.
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )
            estado, _ = await _estado_del_viaje(seeded.alpha.id)
            assert estado == "closed", "HOME cierra al llegar, y eso no cambió"

            await page.get_by_role("button", name="End Work").click()

            # La lectura de cierre se pide **antes** de terminar, no después.
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "active", (
                "la lectura de cierre se pide antes de terminar, no después"
            )

            await _capturar_odometro(page, "90142.5")

            # No se afirma "Ending your day…": lo sustituye la reconciliación en
            # cuanto el servidor confirma, así que es una carrera. Lo estable es
            # dónde queda el supervisor: sin jornada abierta.
            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=20_000)

            async with async_session_maker() as session:
                jornada = await session.scalar(
                    select(WorkSession)
                    .where(WorkSession.company_id == seeded.alpha.id)
                    .order_by(WorkSession.id.desc())
                    .limit(1)
                )
                assert jornada.status == "ended"

            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.status == "photo_confirmed"
            assert str(fin.confirmed_reading) == "90142.5"
        finally:
            await navegador.close()


# ── Recorrido E: flujos 11, 12 ──────────────────────────────────────────────


async def test_i_cannot_take_a_photo_leads_to_the_manual_ending_reading(
    seeded, alpha_client, live_server,
):
    """Flujos 11 y 12 — el defecto de campo y su corrección, en el navegador.

    Lo que se reportó: `End Work` → `I can't take a photo` → `Submit Request`
    cerraba la jornada, se saltaba la lectura y dejaba `Ending Odometer` en
    `Missing`.

    Lo que se comprueba aquí, en el orden en que lo vive una persona:

    11. enviada la solicitud, la jornada **sigue abierta** y la misma pantalla
        pasa a pedir la lectura. Se recarga la página a mitad —que es lo que
        hace quien duda— y no se pierde ni se cierra nada. Tecleada y
        confirmada, el día se cierra y la distancia aparece.
    12. la excepción de cierre **no** llega a la cola del administrador: ya
        está decidida por la regla del flujo, y no hay nada que revisar.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-BR5")
    supervisor = seeded.alpha.users["supervisor"]
    admin = seeded.alpha.users["route_admin"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            movil = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await movil.new_page()
            await abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await page.get_by_role("button", name="Return Home").click()
            await page.get_by_role("button", name="Start Trip").click()
            await _capturar_odometro(page, "10000")
            await page.get_by_role("button", name="Arrived Home").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )

            # ── Flujo 11: la solicitud lleva al campo manual ───────────────
            await page.get_by_role("button", name="End Work").click()
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            await page.get_by_role("button", name="I can't take a photo").click()
            await page.get_by_role("combobox").click()
            await page.get_by_role("option", name="The photo is not readable").click()
            await page.get_by_role("button", name="Send request").click()

            # Aquí estaba el defecto: esto cerraba el día. Ahora aparece el
            # campo, y el texto dice que la jornada sigue abierta.
            campo = page.locator("#odometer-reading")
            await expect(campo).to_have_count(1, timeout=20_000)
            await expect(
                page.get_by_text("Approved: enter the reading you can see on the vehicle.")
            ).to_have_count(1)

            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "active", (
                "enviar la solicitud cerró la jornada: es el defecto reportado"
            )
            assert jornada.ended_at is None

            # Recargar a mitad no pierde ni cierra nada: el supervisor vuelve a
            # la misma pantalla con el mismo campo esperándole.
            await page.reload()
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            campo = page.locator("#odometer-reading")
            await expect(campo).to_have_count(1, timeout=20_000)

            recargada = await _jornada(seeded.alpha.id)
            assert recargada.status == "active", "la recarga cerró la jornada"

            # Y una lectura imposible se rechaza sin cerrar el día.
            await campo.fill("9000")
            await page.get_by_role("button", name="Confirm reading").click()
            await expect(
                page.get_by_text("cannot be lower", exact=False)
            ).to_have_count(1, timeout=20_000)
            assert (await _jornada(seeded.alpha.id)).status == "active"

            # La lectura buena cierra el día.
            await page.locator("#odometer-reading").fill("10096")
            await page.get_by_role("button", name="Confirm reading").click()
            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=30_000)

            cerrada = await _jornada(seeded.alpha.id)
            assert cerrada.status == "ended"
            assert cerrada.ended_at is not None

            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.status == "manual_exception_confirmed", (
                "la evidencia no puede quedarse en Missing por este camino"
            )
            assert float(fin.confirmed_reading) == 10096.0
            assert fin.evidence_method == "manual_no_photo", (
                "sin foto es manual para siempre, aunque el día haya cerrado"
            )

            estado = None
            await alpha_client.login(supervisor.email)
            estado = (
                await alpha_client.get(f"/api/odometer/sessions/{cerrada.id}")
            ).json()
            assert float(estado["odometer_distance"]) == 96.0

            # ── Flujo 12: nada que revisar en la cola ──────────────────────
            escritorio = await navegador.new_context(
                base_url=live_server, viewport={"width": 1280, "height": 800}
            )
            pagina_admin = await escritorio.new_page()
            await abrir_sesion(pagina_admin, admin.email)
            await pagina_admin.goto("/admin/route/odometer-exceptions")

            await expect(
                pagina_admin.get_by_text("Nothing waiting for review.")
            ).to_have_count(1, timeout=20_000)
            await escritorio.close()

            async with async_session_maker() as session:
                viajes = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )
            assert viajes == 1, "resolver la evidencia no crea ningún viaje"
        finally:
            await navegador.close()


# ── Recorrido F: flujo 13 ───────────────────────────────────────────────────


async def test_a_supervisor_cannot_reach_the_admin_exception_queue(
    seeded, live_server,
):
    """Flujo 13: la autoridad de decidir no se hereda de ejecutar la jornada.

    El menú no ofrece el enlace —eso es experiencia de usuario— y el servidor
    tampoco sirve la página, que es el control de verdad. Se comprueban las dos
    cosas, porque ocultar un enlace nunca ha protegido nada.
    """
    from playwright.async_api import async_playwright

    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            respuesta = await page.goto("/admin/route/odometer-exceptions")
            assert respuesta.status in (401, 403, 404), (
                f"el servidor sirvió la página de administración: {respuesta.status}"
            )
            await expect(
                page.get_by_role("heading", name="Odometer Exceptions")
            ).to_have_count(0)

            # Y la API que hay detrás dice lo mismo.
            estado = await page.evaluate(
                """async () => {
                    const r = await fetch('/api/odometer/exceptions/pending');
                    return r.status;
                }"""
            )
            assert estado == 403
        finally:
            await navegador.close()
