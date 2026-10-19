"""El formulario de login de verdad (incidente 19-10-2026).

Un supervisor no pudo entrar desde el móvil: la pestaña de login, restaurada
días después sin volver a pedirse al servidor, no tenía cookies («Company» en
vez del nombre de la compañía). Sin el testigo CSRF el login se rechazaba con
403 antes de mirar las credenciales, y la pantalla sólo decía «Uh oh! Something
went wrong.», el mismo texto para cualquier fallo.

* Una pestaña sin cookies se recupera sola: renueva las cookies y entra.
* Una contraseña incorrecta lo dice, y el formulario conserva lo escrito (antes
  el interceptor de 401 recargaba la página).
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import lanzar_edge
from tests.e2e.test_org_hierarchy_browser import MOVIL
from tests.integration.conftest import TEST_PASSWORD

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/login")


async def _formulario(page, email: str, password: str) -> None:
    await page.get_by_label("Email").fill(email)
    await page.get_by_role("textbox", name="Password", exact=True).fill(password)
    await page.get_by_role("button", name="Sign In").click()


async def test_una_pestana_sin_cookies_entra_igual(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await page.goto("/login")
            await expect(page.get_by_role("button", name="Sign In")).to_be_visible(timeout=20_000)
            # La pestaña sigue abierta, pero el navegador ya no tiene cookies.
            await contexto.clear_cookies()
            await _formulario(page, seeded.alpha.users["supervisor"].email, TEST_PASSWORD)
            await page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)
            nombres = {c["name"] for c in await contexto.cookies()}
            assert "cer_csrf_token" in nombres
            await contexto.close()
        finally:
            await navegador.close()


async def test_contrasena_incorrecta_lo_dice_y_no_recarga(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await page.goto("/login")
            email = seeded.alpha.users["supervisor"].email
            await _formulario(page, email, "no-es-la-clave")
            await expect(page.get_by_text("Incorrect email or password").first).to_be_visible(timeout=10_000)
            await expect(page.get_by_text("Uh oh! Something went wrong.")).to_have_count(0)
            # Sigue en la misma página, con el correo escrito.
            assert "next=" not in page.url
            await expect(page.get_by_label("Email")).to_have_value(email)
            await page.screenshot(path=str(DESTINO / "movil-contrasena-incorrecta.png"))
            await contexto.close()
        finally:
            await navegador.close()
