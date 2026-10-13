"""RTE08 personal: la pestaña Activity de My Route, en el navegador.

Lo que se comprueba
-------------------
* `/route/activity` ya no es el marcador de RTE08: es el explorador, dentro del
  shell de My Route, con la pestaña Activity activa y **sin** selector de
  supervisor ni cromo de administración.
* El supervisor baja de Year a su día y ve sus paradas; vuelve a My Route y a
  Me por la barra inferior; la URL directa y la recarga funcionan.
* Lo que ve coincide con lo que un administrador ve al elegirlo en
  `/admin/route/activity`.
* Dos personas, cada una lo suyo.
* Una lectura que falla al cambiar de pestaña no presenta el periodo anterior
  bajo la pestaña nueva.
* 360, 365, 390 y 430 px sin desbordamiento ni contenido bajo la barra
  inferior; escritorio dentro del shell.

Datos (los de `test_my_activity`): el supervisor, el 16 de septiembre de 2026,
una visita, un regreso a casa sin actividad y una oficina; el 15, otra visita.
El `route_admin` hace campo el 16: una visita de 7 mi.

Capturas en `var/screenshots/rte08-personal/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.test_my_activity import _dos_supervisores

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/rte08-personal")
RUTA = "/route/activity"
ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 365, "height": 800}


async def _entrar(navegador, live_server, email: str, viewport, ruta: str = "/route"):
    contexto = await navegador.new_context(base_url=live_server, viewport=viewport)
    page = await contexto.new_page()
    await abrir_sesion(page, email)
    await page.goto(ruta)
    return contexto, page


async def _al_dia(page) -> None:
    """Year → September → Sep 14–20 → Wed Sep 16, el mecanismo del explorador."""
    await page.get_by_role("button", name="Year", exact=True).click()
    for fila in ("September", "Sep 14–20", "Wed Sep 16"):
        boton = page.locator("button", has_text=fila).first
        await expect(boton).to_be_visible(timeout=20_000)
        await boton.click()
    await expect(page.get_by_role("button", name="Day", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )


async def _resumen(page) -> list[str]:
    caja = page.locator("div.grid.grid-cols-2").first
    await expect(caja).to_be_visible(timeout=20_000)
    return [t.strip() for t in await caja.locator("b").all_inner_texts()]


async def _tarjetas(page) -> list[str]:
    return [t.strip() for t in await page.locator("h4").all_inner_texts()]


async def _sin_desbordar(page, cuando: str) -> None:
    ancho = await page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert ancho <= 0, f"{cuando}: desborda {ancho}px"


async def test_movil_desde_my_route_hasta_el_dia_y_de_vuelta(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _dos_supervisores(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(
                navegador, live_server, seeded.alpha.users["supervisor"].email, MOVIL
            )
            await page.get_by_role("link", name="Activity").click()
            await page.wait_for_url(f"**{RUTA}")
            await expect(page.get_by_role("link", name="Activity")).to_have_attribute(
                "aria-current", "page"
            )
            await expect(page.get_by_text("is not built yet")).to_have_count(0)
            await expect(page.locator("#explorer-supervisor")).to_have_count(0)
            await expect(page.get_by_text("Back to Today")).to_have_count(0)
            await expect(page.get_by_text("Explore operational history by supervisor")).to_have_count(0)

            await _al_dia(page)
            assert await _resumen(page) == ["17.0 mi", "0m", "2", "—"]
            tarjetas = await _tarjetas(page)
            assert sorted(tarjetas) == ["Client Visit", "Home", "Office"]
            await _sin_desbordar(page, "día a 365 px")

            # Lo último de la lista no queda bajo la barra inferior.
            await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            await page.wait_for_function(
                "window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1"
            )
            barra = await page.get_by_role("navigation", name="Route sections").bounding_box()
            ultima = await page.locator("main div.overflow-hidden").last.bounding_box()
            assert barra and ultima and ultima["y"] + ultima["height"] <= barra["y"], (ultima, barra)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.screenshot(path=str(DESTINO / "movil-365-dia.png"), full_page=True)

            await page.get_by_role("button", name="Week", exact=True).click()
            await expect(page.locator("button", has_text="Wed Sep 16").first).to_be_visible()
            await page.screenshot(path=str(DESTINO / "movil-365-semana.png"), full_page=True)

            # De vuelta por la barra inferior.
            await page.get_by_role("link", name="Me").click()
            await page.wait_for_url("**/route/me")
            await page.get_by_role("link", name="My Route").click()
            await page.wait_for_url("**/route")
            await page.get_by_role("link", name="Activity").click()
            await page.wait_for_url(f"**{RUTA}")
            await expect(page.locator("#explorer-supervisor")).to_have_count(0)

            # URL directa y recarga.
            await page.reload()
            await expect(page.get_by_role("button", name="Year", exact=True)).to_be_visible(
                timeout=20_000
            )
            await expect(page.get_by_text("is not built yet")).to_have_count(0)
            await contexto.close()
        finally:
            await navegador.close()


@pytest.mark.parametrize("ancho", [360, 390, 430])
async def test_movil_anchos_sin_desbordar(seeded, alpha_client, live_server, ancho):
    from playwright.async_api import async_playwright

    await _dos_supervisores(alpha_client, seeded)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(
                navegador, live_server, seeded.alpha.users["supervisor"].email,
                {"width": ancho, "height": 800}, RUTA,
            )
            await _al_dia(page)
            await _sin_desbordar(page, f"día a {ancho} px")
            for rango in ("Week", "Month", "Year"):
                await page.get_by_role("button", name=rango, exact=True).click()
                await expect(page.locator("button", has_text="View").first).to_be_visible()
                await _sin_desbordar(page, f"{rango} a {ancho} px")
            await contexto.close()
        finally:
            await navegador.close()


async def test_lo_propio_coincide_con_lo_que_ve_el_administrador(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _dos_supervisores(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(
                navegador, live_server, seeded.alpha.users["supervisor"].email, ESCRITORIO, RUTA
            )
            # Escritorio dentro del shell: la fecha sí, el supervisor no.
            await expect(page.locator("#explorer-date")).to_be_visible(timeout=20_000)
            await expect(page.locator("#explorer-supervisor")).to_have_count(0)
            await page.locator("#explorer-date").fill("2026-09-16")
            propio_resumen = await _resumen(page)
            await expect(page.locator("h4")).to_have_count(3)
            propio_tarjetas = sorted(await _tarjetas(page))
            await page.screenshot(path=str(DESTINO / "escritorio-propio-dia.png"), full_page=True)
            await contexto.close()

            contexto, page = await _entrar(
                navegador, live_server, seeded.alpha.users["route_admin"].email, ESCRITORIO,
                "/admin/route/activity",
            )
            await expect(page.locator("#explorer-supervisor")).to_be_visible(timeout=20_000)
            await page.locator("#explorer-supervisor").select_option(
                str(seeded.alpha.users["supervisor"].id)
            )
            await page.locator("#explorer-date").fill("2026-09-16")
            await expect(page.locator("h4")).to_have_count(3, timeout=20_000)
            admin_resumen = await _resumen(page)
            admin_tarjetas = sorted(await _tarjetas(page))
            await page.screenshot(path=str(DESTINO / "escritorio-admin-mismo-dia.png"), full_page=True)
            await contexto.close()

            assert propio_resumen == admin_resumen == ["17.0 mi", "0m", "2", "—"]
            assert propio_tarjetas == admin_tarjetas
        finally:
            await navegador.close()


async def test_dos_personas_cada_una_lo_suyo(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    await _dos_supervisores(alpha_client, seeded)
    esperado = {"supervisor": "17.0 mi", "route_admin": "7.0 mi"}

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            for quien, millas in esperado.items():
                contexto, page = await _entrar(
                    navegador, live_server, seeded.alpha.users[quien].email, MOVIL, RUTA
                )
                respuestas = []
                page.on(
                    "response",
                    lambda r: respuestas.append(r) if "/api/activity-explorer" in r.url else None,
                )
                await _al_dia(page)
                assert (await _resumen(page))[0] == millas
                await expect(page.locator("#explorer-supervisor")).to_have_count(0)
                # Sólo el endpoint propio: nunca el de administración, que traería
                # a otras personas para filtrarlas aquí.
                assert respuestas and all("/activity-explorer/me" in r.url for r in respuestas)
                await contexto.close()
        finally:
            await navegador.close()


async def test_una_lectura_fallida_no_presenta_el_periodo_anterior(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    await _dos_supervisores(alpha_client, seeded)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(
                navegador, live_server, seeded.alpha.users["supervisor"].email, MOVIL, RUTA
            )
            await _al_dia(page)
            await expect(page.locator("h4")).to_have_count(3)

            # La lectura de Month falla: bajo la pestaña Month no pueden quedar
            # las paradas del día.
            await page.route("**/activity-explorer/me?*range=month*", lambda r: r.abort())
            await page.get_by_role("button", name="Month", exact=True).click()
            await expect(page.get_by_text("could not be read")).to_be_visible(timeout=20_000)
            await expect(page.locator("h4")).to_have_count(0)
            await contexto.close()
        finally:
            await navegador.close()
