"""T0 en el navegador (RTE-MAIL-UNIFIED-01, CP1): la prueba del proveedor.

En Platform › Integrations & Settings, el paso Verify de «Outbound email»
ofrece **Verify** y **Send Test Email** por separado, y el administrador de
plataforma escribe la dirección de la prueba (V1.2), precargada con la suya.
Captura en `var/screenshots/mail-provider-test/`.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/mail-provider-test")


@pytest.mark.parametrize("viewport", [ESCRITORIO, MOVIL], ids=["escritorio", "movil"])
async def test_t0_destino_editable(seeded, alpha_client, live_server, viewport):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    propio = seeded.platform_admin.email.lower()
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=viewport)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.platform_admin.email)
            await page.goto("/admin/platform/settings")
            await page.locator("#integration-email").get_by_role("button", name="Set up").click(timeout=20_000)
            hoja = page.get_by_role("dialog")
            for paso in ("Next: Get credentials", "Next: Enter credentials", "Next: Verify"):
                await hoja.get_by_role("button", name=paso).click()

            await expect(hoja.get_by_role("button", name="Verify", exact=True)).to_be_visible(timeout=10_000)
            await expect(hoja.get_by_role("button", name="Send Test Email")).to_be_visible()
            # V1.2: campo editable, precargado con el propio correo.
            campo = hoja.get_by_label("Test recipient")
            await expect(campo).to_have_value(propio, timeout=10_000)
            await campo.fill("externo.qa@otro-dominio.com")
            await expect(campo).to_have_value("externo.qa@otro-dominio.com")
            # Sin proveedor guardado, no se puede mandar.
            await expect(hoja.get_by_role("button", name="Send Test Email")).to_be_disabled()
            tipo = "movil" if viewport is MOVIL else "escritorio"
            await page.screenshot(path=str(DESTINO / f"{tipo}-t0.png"))
            if viewport is MOVIL:
                assert await page.evaluate("document.documentElement.scrollWidth") <= MOVIL["width"]
            await contexto.close()
        finally:
            await navegador.close()
