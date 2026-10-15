"""Visor de ruta de Activity Admin en el navegador.

* Con el permiso del mapa, la tarjeta del viaje trae `View Route` bajo su
  resumen; **mientras está cerrado no se pide ni una tesela**.
* Al abrir: tres marcadores numerados (salida, cambio de plan, llegada), sin
  línea, la leyenda que lo dice, `Hide Route` y `aria-expanded`. Al cerrar, el
  mapa desaparece.
* Sin el permiso, no hay botón. A 390 px, sin desborde horizontal.

Las teselas se sirven desde la propia prueba (`page.route`): ni una petición
sale a OpenStreetMap. Capturas en `var/screenshots/activity-route-map/`.
"""

from __future__ import annotations

import base64
import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL
from tests.integration.test_activity_route_map import _conceder, _revocar, _viaje
from tests.integration.test_org_hierarchy import _organigrama

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/activity-route-map")
DIA = "2026-09-16"
#: Una tesela gris de 1×1: suficiente para que Leaflet pinte el fondo.
TESELA = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8+P9/PQAJYwPKx1rKgQAAAABJRU5ErkJggg=="
)


async def _abrir_activity(page, supervisor: str) -> None:
    await page.goto("/admin/route/activity")
    await expect(page.locator("#explorer-supervisor")).to_be_visible(timeout=20_000)
    await page.locator("#explorer-supervisor").select_option(label=supervisor)
    await page.locator("#explorer-date").fill(DIA)
    await page.locator("#explorer-date").press("Enter")


async def _sin_desborde(page) -> bool:
    return not await page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1")


@pytest.mark.parametrize("viewport", ["escritorio", "movil"])
async def test_view_route_abre_y_cierra_el_mapa_sin_teselas_antes(
    seeded, alpha_client, live_server, viewport
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "route_admin")
    await _viaje(alpha_client, seeded, "sup_c")
    teselas: list[str] = []
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()

            async def _tesela(ruta):
                teselas.append(ruta.request.url)
                await ruta.fulfill(status=200, content_type="image/png", body=TESELA)

            await page.route("https://tile.openstreetmap.org/**", _tesela)
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await _abrir_activity(page, "SUP_C Org")
            if viewport == "movil":
                # En móvil la vista no enseña el selector de fecha: el día se
                # elige en escritorio y se valida a 390 px.
                await expect(page.get_by_text("activity span · trip miles").first).to_be_visible(timeout=20_000)
                await page.set_viewport_size(MOVIL)

            boton = page.get_by_role("button", name="View Route")
            await expect(boton).to_be_visible(timeout=20_000)
            await expect(boton).to_have_attribute("aria-expanded", "false")
            await page.wait_for_timeout(500)
            assert teselas == [], "cerrado: ni una tesela"
            await page.screenshot(path=str(DESTINO / f"{viewport}-cerrado.png"), full_page=True)

            await boton.click()
            await expect(page.locator(".cer-route-pin")).to_have_count(3, timeout=20_000)
            await expect(page.get_by_role("button", name="Hide Route")).to_have_attribute("aria-expanded", "true")
            await expect(page.get_by_text("Not the route driven")).to_be_visible()
            assert await page.locator(".leaflet-overlay-pane path").count() == 0, "ninguna línea"
            assert teselas, "abierto: se piden teselas"
            assert await _sin_desborde(page)
            await page.screenshot(path=str(DESTINO / f"{viewport}-abierto.png"), full_page=True)

            await page.get_by_role("button", name="Hide Route").click()
            await expect(page.locator(".leaflet-container")).to_have_count(0)
            await contexto.close()
        finally:
            await navegador.close()


async def test_sin_el_permiso_no_hay_boton(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    await _organigrama(alpha_client, seeded)
    await _conceder(seeded, "route_admin")
    await _viaje(alpha_client, seeded, "sup_c")
    await _revocar(seeded, "route_admin")
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await _abrir_activity(page, "SUP_C Org")
            await expect(page.get_by_text("activity span · trip miles").first).to_be_visible(timeout=20_000)
            assert await page.get_by_role("button", name="View Route").count() == 0
            await contexto.close()
        finally:
            await navegador.close()
