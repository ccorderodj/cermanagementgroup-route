"""Una pestaña abierta antes de un despliegue se entera al volver a usarse.

El servidor «despliega» interceptando la sonda (`HEAD main.js?check=…`) con
otro `X-CER-Build`. Volver a la pestaña o recuperar la red muestra el aviso;
la página **no** se recarga sola, y «Reload» trae la página entera de nuevo.
"""

from __future__ import annotations

import re

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import lanzar_edge
from tests.e2e.test_org_hierarchy_browser import MOVIL

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

SONDA = re.compile(r".*/static/javascript/main\.js\?check=.*")
AVISO = "A new version is available"


async def _abrir(navegador, live_server, build_del_servidor: str | None):
    contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
    page = await contexto.new_page()
    sondas: list[str] = []

    async def responder(route):
        sondas.append(route.request.method)
        if build_del_servidor is None:
            await route.continue_()
        else:
            await route.fulfill(status=200, headers={"x-cer-build": build_del_servidor})

    await page.route(SONDA, responder)
    await page.goto("/login")
    await expect(page.get_by_role("button", name="Sign In")).to_be_visible(timeout=20_000)
    return contexto, page, sondas


async def _volver_a_la_pestana(page):
    await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")


async def test_build_nuevo_avisa_sin_recargar_sola(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page, sondas = await _abrir(navegador, live_server, "build-desplegado")
            await page.evaluate("window.__sinRecargar = true")
            await page.get_by_label("Email").fill("a medias")

            await _volver_a_la_pestana(page)
            await expect(page.get_by_text(AVISO)).to_be_visible(timeout=10_000)
            assert sondas == ["HEAD"], "una sola sonda, sin sesión"
            assert await page.evaluate("window.__sinRecargar") is True, "no recarga sola"
            assert await page.get_by_label("Email").input_value() == "a medias", "lo escrito sigue ahí"

            await page.get_by_role("button", name="Reload").click()
            await page.wait_for_load_state("load")
            assert await page.evaluate("window.__sinRecargar === undefined"), "Reload trae la página entera"
            await contexto.close()
        finally:
            await navegador.close()


async def test_mismo_build_no_avisa_y_no_sondea_en_bucle(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page, sondas = await _abrir(navegador, live_server, None)

            await _volver_a_la_pestana(page)
            await page.evaluate("window.dispatchEvent(new Event('online'))")
            await page.wait_for_timeout(1_500)
            assert sondas == ["HEAD"], "el segundo evento en menos de un minuto no vuelve a preguntar"
            await expect(page.get_by_text(AVISO)).to_have_count(0)
            await contexto.close()
        finally:
            await navegador.close()


async def test_sin_red_no_pregunta(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page, sondas = await _abrir(navegador, live_server, "build-desplegado")
            await contexto.set_offline(True)
            await _volver_a_la_pestana(page)
            await page.wait_for_timeout(1_000)
            assert sondas == []
            await contexto.set_offline(False)
            await expect(page.get_by_text(AVISO)).to_be_visible(timeout=10_000)
            await contexto.close()
        finally:
            await navegador.close()


async def test_un_chunk_que_ya_no_existe_avisa_en_vez_de_dejar_la_pantalla_en_blanco(
    seeded, alpha_client, live_server,
):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            # El despliegue borró los chunks del build anterior.
            await page.route(re.compile(r".*/static/javascript/[^/]+\.[0-9a-f]{16,}\.js$"),
                             lambda route: route.fulfill(status=404, body="not found"))
            await page.goto("/login")
            await expect(page.get_by_text(AVISO)).to_be_visible(timeout=20_000)
            await contexto.close()
        finally:
            await navegador.close()
