"""Las cuatro capturas que §18 exige de Today / Live.

Por qué es un test y no un script suelto
-----------------------------------------
Porque así se regeneran con el mismo arnés que valida el comportamiento —el
mismo `uvicorn`, el mismo tenant sembrado, los mismos tamaños de ventana— y no
dependen de que alguien recuerde cómo las sacó. Una captura que nadie puede
reproducir no es evidencia, es una ilustración.

Las imágenes van a `var/screenshots/rte07/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte07_today_live_browser import (
    ESCRITORIO,
    MOVIL,
    RUTA,
    _preparar_supervisor,
)

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/rte07")


async def test_capturas_de_escritorio_y_movil(seeded, alpha_client, live_server):
    """Lista y detalle, en los dos tamaños que la instrucción nombra."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _preparar_supervisor(alpha_client, seeded, "V-LIVE-SHOT")
    producidas: list[str] = []

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            # ── Escritorio 1280×900 ────────────────────────────────────────
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)
            # Se espera **contenido**, no el encabezado: el encabezado también
            # existe mientras carga, y una captura del estado de carga sería
            # evidencia engañosa de fidelidad visual.
            await expect(
                page.get_by_text("across active routes")
            ).to_have_count(1, timeout=20_000)

            destino = DESTINO / "01-desktop-list.png"
            await page.screenshot(path=str(destino))
            producidas.append(destino.name)

            await page.locator("tbody tr").first.click()
            await expect(page.locator("aside")).to_have_count(1, timeout=10_000)
            destino = DESTINO / "02-desktop-detail.png"
            await page.screenshot(path=str(destino))
            producidas.append(destino.name)
            await contexto.close()

            # ── Móvil 390×844 ──────────────────────────────────────────────
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)
            await expect(
                page.get_by_text("Supervisors working", exact=True)
            ).to_have_count(1, timeout=20_000)

            destino = DESTINO / "03-mobile-list.png"
            await page.screenshot(path=str(destino))
            producidas.append(destino.name)

            await page.get_by_role("button").filter(has_text="Since").first.click()
            await expect(
                page.get_by_role("button", name="Back to supervisors")
            ).to_have_count(1, timeout=10_000)
            destino = DESTINO / "04-mobile-detail.png"
            await page.screenshot(path=str(destino))
            producidas.append(destino.name)
        finally:
            await navegador.close()

    assert len(producidas) == 4, producidas
    for nombre in producidas:
        archivo = DESTINO / nombre
        assert archivo.exists() and archivo.stat().st_size > 1000, (
            f"{nombre} salió vacía o no se escribió"
        )
