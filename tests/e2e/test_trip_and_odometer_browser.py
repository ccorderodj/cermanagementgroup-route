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
                page.get_by_role("button", name="Where to next?")
            ).to_be_enabled()

            # ── Contexto con dato obligatorio antes de salir ────────────────
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Employee Visit").click()
            await page.get_by_role("combobox").click()
            await page.get_by_role("option", name="Payroll question").click()
            await page.get_by_role("button", name="Prepare trip").click()

            # El plan ya existe y **sigue a la vista** mientras se resuelve la
            # lectura: eso es lo que significa "preservar el contexto debajo".
            await expect(page.get_by_text("Heading to")).to_have_count(1, timeout=20_000)
            await expect(page.get_by_text("Employee Visit")).to_have_count(1)
            await expect(page.get_by_text("Take a photo of the odometer, then confirm the reading.")).to_have_count(1)
            assert await _estado_del_viaje(seeded.alpha.id) == (
                "planning", "employee_visit",
            )

            await _capturar_odometro(page, "128437")

            # Y se vuelve al mismo viaje, sin volver a elegir nada.
            await expect(
                page.get_by_role("button", name="Start Trip")
            ).to_have_count(1, timeout=20_000)
            evidencia = await _evidencia(seeded.alpha.id, "start")
            assert evidencia.status == "photo_confirmed"
            assert evidencia.evidence_method == "photo"
            assert str(evidencia.confirmed_reading) == "128437.0"
            assert evidencia.ocr_detected_reading is None, (
                "sin OCR no hay sugerencia, y la evidencia sigue siendo fotográfica"
            )

            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)
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
            # El formulario abre **con el plan actual**, no con la lista en
            # blanco: cambiar de plan parte de lo que ya se había decidido. Para
            # elegir otro contexto hay que volver atrás explícitamente.
            await expect(
                page.get_by_role("button", name="Change", exact=True)
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("button", name="Change", exact=True).click()
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
                "un viaje operativo que llegó espera a RTE05; no se cierra solo"
            )
            # Y la pantalla lo dice en vez de enseñar un botón que no hace nada.
            await expect(page.get_by_text("RTE05")).to_have_count(1)
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

            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Return Home").click()
            await page.get_by_role("button", name="Prepare trip").click()
            await _capturar_odometro(page, "500")
            await page.get_by_role("button", name="Start Trip").click()
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
                page.get_by_role("button", name="Where to next?")
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
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Prepare trip").click()

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
            await page.reload()
            campo = page.locator("#odometer-reading")
            await expect(campo).to_have_count(1, timeout=20_000)
            await campo.fill("77000")
            await page.get_by_role("button", name="Confirm reading").click()

            await expect(
                page.get_by_role("button", name="Start Trip")
            ).to_have_count(1, timeout=20_000)

            evidencia = await _evidencia(seeded.alpha.id, "start")
            assert evidencia.status == "manual_exception_confirmed"
            assert evidencia.evidence_method == "manual_no_photo", (
                "una lectura sin foto no puede parecer evidencia fotográfica"
            )

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
    """Flujo 10: el camino normal de cierre, con foto.

    Y de paso la interacción D-07: el día no se cierra con un viaje en ruta sin
    que el supervisor lo decida explícitamente.
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
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Prepare trip").click()
            await _capturar_odometro(page, "90000")
            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)

            # ── D-07: con el viaje en ruta, cerrar es una revisión ─────────
            await page.get_by_role("button", name="End Work").click()
            await expect(
                page.get_by_text("You are still on route")
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("button", name="End Work Anyway").click()

            # El viaje queda interrumpido —sin llegada inventada— y **entonces**
            # se pide la lectura de cierre.
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            estado, _ = await _estado_del_viaje(seeded.alpha.id)
            assert estado == "interrupted", "no se fabrica una llegada"
            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "active", (
                "la lectura de cierre se pide antes de terminar, no después"
            )

            await _capturar_odometro(page, "90142.5")

            # Confirmar la lectura dispara el cierre de la jornada, que es otra
            # petición: se espera a que la pantalla lo diga antes de leer la base.
            await expect(page.get_by_text("Ending your day")).to_have_count(
                1, timeout=20_000
            )

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


async def test_the_day_ends_with_a_pending_end_exception_and_resolves_later(
    seeded, alpha_client, live_server,
):
    """Flujos 11 y 12 — la Opción B de CER, en el navegador.

    11. Excepción de cierre → la jornada termina con la evidencia pendiente.
    12. Aprobada después → la lectura manual resuelve la distancia **sin
        reabrir** la jornada y sin mover su hora de fin.
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
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Prepare trip").click()
            await _capturar_odometro(page, "10000")
            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Arrived", exact=True)
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("button", name="Arrived", exact=True).click()
            await expect(page.get_by_text("Arrived at")).to_have_count(1, timeout=20_000)

            # ── Flujo 11: cerrar con la excepción pedida ───────────────────
            await page.get_by_role("button", name="End Work").click()
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            await page.get_by_role("button", name="I can't take a photo").click()
            await page.get_by_role("combobox").click()
            await page.get_by_role("option", name="The photo is not readable").click()
            await page.get_by_role("button", name="Send request").click()

            await expect(
                page.get_by_text("Ending your day")
            ).to_have_count(1, timeout=20_000)

            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "ended", (
                "el día termina a su hora real aunque falte la evidencia"
            )
            hora_de_cierre = jornada.ended_at
            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.status == "exception_requested"
            assert fin.confirmed_reading is None

            # ── Flujo 12: aprobada después ─────────────────────────────────
            escritorio = await navegador.new_context(
                base_url=live_server, viewport={"width": 1280, "height": 800}
            )
            pagina_admin = await escritorio.new_page()
            await abrir_sesion(pagina_admin, admin.email)
            await pagina_admin.goto("/admin/route/odometer-exceptions")

            fila = pagina_admin.locator("tr", has_text="Supervisor Tester")
            await expect(fila).to_have_count(1, timeout=20_000)
            await expect(fila.get_by_text("End of day", exact=True)).to_have_count(1)
            await fila.get_by_role("button", name="Approve").click()
            await expect(
                pagina_admin.get_by_text("Nothing waiting for review.")
            ).to_have_count(1, timeout=20_000)
            await escritorio.close()

            # La lectura tardía se completa contra la jornada ya cerrada, por
            # API: la pantalla del supervisor ya no tiene jornada activa que
            # mostrar, y fabricarle una sería justo lo que CER prohíbe.
            await alpha_client.login(supervisor.email)
            confirmada = await alpha_client.post(
                f"/api/odometer/sessions/{jornada.id}/end/confirm",
                json={"reading": "10096.0"},
            )
            assert confirmada.status_code == 200
            assert confirmada.json()["status"] == "manual_exception_confirmed"

            estado = (
                await alpha_client.get(f"/api/odometer/sessions/{jornada.id}")
            ).json()
            assert estado["odometer_distance"] is not None
            assert float(estado["odometer_distance"]) == 96.0

            despues = await _jornada(seeded.alpha.id)
            assert despues.status == "ended", "no se reabre"
            assert despues.ended_at == hora_de_cierre, "la hora de fin no se movió"

            async with async_session_maker() as session:
                viajes = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )
            assert viajes == 1, "completar la evidencia no crea ningún viaje"
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
