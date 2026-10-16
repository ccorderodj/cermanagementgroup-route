"""`Keep working` después de un `End Work` pulsado sin querer.

El reporte de campo
-------------------
«Presioné sin querer `End Work` mientras manejaba y no me deja darle a
`Keep working`.» `End Work` deja la lectura de cierre pendiente en el servidor
antes de rechazar el cierre, la pantalla decide la fase por esa lectura —para
sobrevivir a que Android recree la pestaña (ODO-03)— y `Keep working` sólo
releía el estado: volvía a la misma pantalla. La única salida era cerrar el día.

Lo que se comprueba aquí es lo que el supervisor necesitaba: después de
`Keep working` puede **volver a salir**, y la captura de cierre no reaparece.

Las capturas van a `var/screenshots/keep-working/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte04_closure_browser import MOVIL, _capturar_odometro, _flota

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/keep-working")


async def test_keep_working_after_an_accidental_end_work_lets_the_day_go_on(
    seeded, alpha_client, live_server,
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _flota(alpha_client, seeded, unidad="V-KEEP", para="supervisor")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            ctx = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await ctx.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()

            # Un primer trayecto, para que el día tenga distancia que cerrar y
            # `End Work` pida la lectura final.
            await page.get_by_role("button", name="Return Home").click()
            await page.get_by_role("button", name="Start Trip").click()
            await _capturar_odometro(page, "70000")
            await page.get_by_role("button", name="Arrived Home").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )

            # La pulsación accidental.
            await page.get_by_role("button", name="End Work").click()
            await expect(
                page.get_by_text("One last thing before you finish.")
            ).to_have_count(1, timeout=20_000)
            await page.screenshot(
                path=str(DESTINO / "movil-1-cierre-pedido.png"), full_page=True
            )

            await page.get_by_role("button", name="Keep working").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )
            await page.screenshot(
                path=str(DESTINO / "movil-2-sigue-trabajando.png"), full_page=True
            )

            # Puede volver a salir: es lo que no podía hacer.
            await page.get_by_role("button", name="Return Home").click()
            await expect(
                page.get_by_role("button", name="Start Trip")
            ).to_be_enabled(timeout=20_000)

            # Y la captura de cierre no reaparece al recargar.
            await page.reload()
            await expect(
                page.get_by_text("One last thing before you finish.")
            ).to_have_count(0)
        finally:
            await navegador.close()
