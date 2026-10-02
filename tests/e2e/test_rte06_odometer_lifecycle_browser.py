"""La tarea de odómetro sobrevive a la cámara y a que la pestaña se recree.

Qué se prueba aquí y por qué no estaba probado
----------------------------------------------
El hallazgo de campo de RTE06 fue que el supervisor volvía de la cámara —o
Android recreaba la pestaña mientras la cámara estaba delante— y la pantalla
aparecía en el workbench, sin la tarea de lectura pendiente y sin nada que
dijera dónde estaba. El delta anterior lo corrigió; lo que faltaba era la
evidencia automatizada de que lo corrige, que es lo que CER pide en O1–O10.

Cómo se simula "Android recreó la pestaña"
------------------------------------------
Con `page.reload()`. Es la aproximación honesta y tiene un límite que conviene
escribir: recargar destruye el estado de React y vuelve a montar la página
contra el mismo `sessionStorage` y el mismo servidor, que es exactamente lo que
le pasa a la pestaña recreada. Lo que **no** reproduce es que Android mate el
proceso entero del navegador; eso sigue necesitando hardware real y queda
`PENDING` para la revalidación física de CER.

Por qué recorridos y no un test por caso
----------------------------------------
Lo mismo que en `test_trip_and_odometer_browser.py`: cada test levanta su propio
`uvicorn` y `seeded` resiembra entre tests, así que partir esto en nueve tests
multiplicaría por nueve el arranque sin demostrar nada que el recorrido no
demuestre. Y la tarea de odómetro sólo existe dentro de la secuencia del día.

Qué se mira para decidir si la interfaz es honesta
--------------------------------------------------
La etiqueta del botón, que sale de `evidence.captured_at` —verdad de dominio—:

    sin foto subida   → "Take photo",   y no hay campo de lectura
    con foto subida   → "Retake photo", y sí hay campo de lectura

Así que "la interfaz no finge que hay foto" no se comprueba leyendo el código:
se comprueba mirando lo que ve el supervisor, y contra la fila de la base.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from sqlalchemy import select

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

CAPTURA = "Take a photo of the odometer, then confirm the reading."


async def _preparar_vehiculo(alpha_client, seeded, unidad: str) -> None:
    """Supervisor con vehículo asignado, por API.

    Administrar la flota tiene su propia validación de navegador (RTE02-A01);
    repetirla aquí alargaría el recorrido sin demostrar nada nuevo.
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


async def _viajes(company_id: int) -> int:
    async with async_session_maker() as session:
        filas = await session.execute(
            select(Trip.id).where(Trip.company_id == company_id)
        )
        return len(list(filas))


async def _subir_foto(page) -> None:
    """Elige la foto, que es lo que hace el navegador al volver de la cámara."""
    await page.locator('input[type="file"]').set_input_files(
        {"name": "odo.png", "mimeType": "image/png", "buffer": FOTO_PNG}
    )


async def _recrear_pestana(page) -> None:
    """Lo más cerca que llega el escritorio de "Android recreó la pestaña".

    Tira el estado de React y vuelve a montar contra el mismo
    `sessionStorage` y el mismo servidor.
    """
    await page.reload()


# ── Recorrido A: la lectura de INICIO (O1–O5) ───────────────────────────────


async def test_the_start_reading_task_survives_the_camera_and_a_recreated_tab(
    seeded, alpha_client, live_server,
):
    """O1, O2, O3, O4 y O5, más la protección de `Start Trip` (FR-04).

    O1 — vuelta normal de la cámara.
    O3 — la pestaña se recrea **antes** de que la foto llegue a subirse.
    O2 — la pestaña se recrea **después**, con la foto ya persistida.
    O4 — foto válida, sin sugerencia de OCR, confirmación manual.
    O5 — volver a fotografiar.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-ODO-A")
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

            # El aviso aparece y **no** bloquea: el día puede empezar sin
            # conducir, así que fotografiar no es un diálogo forzado.
            await expect(
                page.get_by_text("Odometer pending", exact=True)
            ).to_have_count(1, timeout=20_000)
            await expect(page.get_by_text("What's next?")).to_have_count(1)

            # ── O1: se abre la tarea, como al volver de la cámara ───────────
            #
            # El aviso entero es el botón: su nombre accesible es el mensaje
            # más la acción, y se ancla en la acción porque es la que describe
            # lo que hace al pulsarlo.
            await page.get_by_role(
                "button", name="Capture before first trip"
            ).click()
            await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)

            # Sin foto todavía, y la interfaz lo dice: el botón ofrece hacerla,
            # no rehacerla, y no hay campo de lectura que rellenar.
            await expect(
                page.get_by_role("button", name="Take photo")
            ).to_have_count(1)
            await expect(page.locator("#odometer-reading")).to_have_count(0)
            assert (await _evidencia(seeded.alpha.id, "start")).captured_at is None

            # ── O3: la pestaña muere antes de que la foto se suba ───────────
            await _recrear_pestana(page)
            await expect(page.get_by_text(CAPTURA)).to_have_count(
                1, timeout=20_000
            ), "la tarea de inicio no se reanudó tras recrear la pestaña"
            # Y sigue sin fingir que hay foto.
            await expect(
                page.get_by_role("button", name="Take photo")
            ).to_have_count(1)
            assert (await _evidencia(seeded.alpha.id, "start")).captured_at is None, (
                "no se subió ninguna foto, así que no puede haber `captured_at`"
            )

            # ── O2: ahora sí hay foto, y la pestaña vuelve a morir ──────────
            await _subir_foto(page)
            await expect(page.locator("#odometer-reading")).to_have_count(
                1, timeout=20_000
            )
            evidencia = await _evidencia(seeded.alpha.id, "start")
            assert evidencia.captured_at is not None, "la foto debía quedar subida"

            await _recrear_pestana(page)
            await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)
            # Con foto persistida la interfaz ofrece **rehacerla**, y el campo
            # de lectura está: la foto sigue disponible para confirmarla.
            await expect(
                page.get_by_role("button", name="Retake photo")
            ).to_have_count(1, timeout=20_000)
            await expect(page.locator("#odometer-reading")).to_have_count(1)

            # ── O4: sin sugerencia de OCR, y eso no impide confirmar ────────
            assert evidencia.ocr_detected_reading is None, (
                "el OCR productivo está fuera de alcance: no debe sugerir nada"
            )
            await expect(page.locator("#odometer-reading")).to_have_value("")

            # ── O5: volver a fotografiar ───────────────────────────────────
            await _subir_foto(page)
            await expect(
                page.get_by_role("button", name="Retake photo")
            ).to_have_count(1, timeout=20_000)
            assert (await _evidencia(seeded.alpha.id, "start")).status != (
                "photo_confirmed"
            ), "rehacer la foto no confirma nada por sí solo"

            # ── FR-04: `Start Trip` sigue protegido ────────────────────────
            campo = page.locator("#odometer-reading")
            await campo.fill("128437")
            await page.get_by_role("button", name="Confirm reading").click()

            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )
            resuelta = await _evidencia(seeded.alpha.id, "start")
            assert resuelta.status == "photo_confirmed", resuelta.status
            assert resuelta.evidence_method == "photo"
            assert str(resuelta.confirmed_reading) == "128437.0"

            # Resuelta la tarea, recrear la pestaña **no** la reabre: la marca
            # se olvidó al resolverla, y la verdad de dominio ya dice que está
            # hecha.
            await _recrear_pestana(page)
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )
            await expect(page.get_by_text(CAPTURA)).to_have_count(0)
        finally:
            await navegador.close()


# ── Recorrido B: la lectura de CIERRE (O6–O9) ───────────────────────────────


async def test_the_end_reading_task_survives_a_recreated_tab_without_reopening_the_day(
    seeded, alpha_client, live_server,
):
    """O6, O7, O8 y O9, más la frontera de FR-05.

    O6 — vuelta normal de la cámara en el cierre.
    O9 — la pestaña se recrea antes de que la foto se persista.
    O7 — la pestaña se recrea después, con la foto ya subida.
    O8 — foto válida sin sugerencia de OCR, confirmación manual.

    Y lo que FR-05 prohíbe: restaurar la pantalla de cierre **no** puede
    reabrir la jornada. Se comprueba contra `ended_at` en la base, no contra
    la pantalla.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-ODO-B")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            # ── El día, hasta poder terminarlo ─────────────────────────────
            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await page.get_by_role("button", name="Return Home").click()
            await page.get_by_role("button", name="Start Trip").click()
            await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=20_000)
            await _subir_foto(page)
            await page.locator("#odometer-reading").fill("90000")
            await page.get_by_role("button", name="Confirm reading").click()
            await page.get_by_role("button", name="Arrived Home").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )

            # ── O6: se pide la lectura de cierre antes de cerrar ───────────
            await page.get_by_role("button", name="End Work").click()
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            jornada = await _jornada(seeded.alpha.id)
            assert jornada.status == "active", (
                "la lectura de cierre se pide antes de terminar, no después"
            )

            # ── O9: la pestaña muere antes de subir la foto de cierre ──────
            await _recrear_pestana(page)
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            ), "la tarea de cierre no se reanudó tras recrear la pestaña"
            await expect(
                page.get_by_role("button", name="Take photo")
            ).to_have_count(1)
            assert (await _evidencia(seeded.alpha.id, "end")).captured_at is None, (
                "la interfaz no puede dar por subida una foto que no se subió"
            )

            # ── O7: con la foto ya persistida ─────────────────────────────
            await _subir_foto(page)
            await expect(page.locator("#odometer-reading")).to_have_count(
                1, timeout=20_000
            )
            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.captured_at is not None

            await _recrear_pestana(page)
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=20_000
            )
            await expect(
                page.get_by_role("button", name="Retake photo")
            ).to_have_count(1, timeout=20_000)

            # ── O8: sin sugerencia de OCR, confirmación manual ────────────
            assert fin.ocr_detected_reading is None
            await expect(page.locator("#odometer-reading")).to_have_value("")

            # ── FR-05: restaurar la pantalla no reabrió nada ──────────────
            jornada_antes = await _jornada(seeded.alpha.id)
            viajes_antes = await _viajes(seeded.alpha.id)

            await page.locator("#odometer-reading").fill("90142.5")
            await page.get_by_role("button", name="Confirm reading").click()

            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=20_000)

            jornada_despues = await _jornada(seeded.alpha.id)
            assert jornada_despues.id == jornada_antes.id, (
                "restaurar el cierre creó una jornada nueva"
            )
            assert await _viajes(seeded.alpha.id) == viajes_antes, (
                "restaurar el cierre creó un viaje"
            )
            resuelta = await _evidencia(seeded.alpha.id, "end")
            assert resuelta.status == "photo_confirmed", resuelta.status
            assert str(resuelta.confirmed_reading) == "90142.5"
        finally:
            await navegador.close()
