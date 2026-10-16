"""Activity Emails en el navegador (RTE-NOT-01): Templates y Recipients.

Recorrido de quien tiene `route.activityemails.manage`:

* llega por el menú «CER Route Configuration › Activity Emails»;
* la página dice que sólo configura (no envía);
* edita el asunto de Midday, ve la vista previa marcada como ejemplo, guarda y
  al recargar sigue ahí; End of Day no cambia;
* restaurar pide confirmación y deja el texto aprobado;
* en Recipients, los dos interruptores nacen apagados y se activan por
  separado; persisten al recargar;
* en móvil, tarjetas apiladas sin desbordamiento horizontal.

Capturas en `var/screenshots/activity-emails/`.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL
from tests.integration.test_activity_emails import _conceder
from tests.integration.test_org_hierarchy import _filas

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/activity-emails")
URL = "/admin/route/activity-emails"


async def test_templates_y_recipients_en_escritorio(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _conceder(seeded, "route_admin")
    supervisor = seeded.alpha.users["supervisor"].id
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            # Por el menú, no escribiendo la URL.
            await page.goto("/admin/route/vehicles")
            await page.get_by_role("link", name="Activity Emails").first.click()
            await expect(page.get_by_role("heading", name="Activity Emails", level=1)).to_be_visible(timeout=20_000)
            await expect(page.get_by_role("status")).to_contain_text("Envío automático pendiente de habilitación")

            midday = page.get_by_role("region", name="Midday Motivation")
            await expect(midday.get_by_label("Subject")).to_have_value("¡Buen trabajo! Sigamos adelante 💪")
            await page.screenshot(path=str(DESTINO / "escritorio-templates.png"), full_page=True)

            await midday.get_by_label("Subject").fill("¡Gran mañana, {{user_first_name}}! 💪")
            await expect(midday.get_by_text("Unsaved changes", exact=True)).to_be_visible()
            await midday.get_by_role("button", name="Preview").click()
            vista = page.get_by_role("dialog")
            await expect(vista).to_contain_text("Ejemplo / Vista previa")
            await expect(vista).to_contain_text("¡Gran mañana, María! 💪")
            await expect(vista).to_contain_text("2 visitas a clientes")
            # La captura, cuando el diálogo ya terminó de aparecer.
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(DESTINO / "escritorio-preview.png"))
            await page.keyboard.press("Escape")

            await midday.get_by_role("button", name="Save changes").click()
            await expect(midday.get_by_text("Customized", exact=True)).to_be_visible(timeout=10_000)

            # Un cuerpo sin el bloque obligatorio se rechaza en su campo.
            fin = page.get_by_role("region", name="End of Day Recognition")
            await fin.get_by_label("Body").fill("Gracias, {{user_first_name}}.")
            await fin.get_by_role("button", name="Save changes").click()
            await expect(fin.get_by_role("alert").first).to_contain_text("activity summary is required")
            await page.screenshot(path=str(DESTINO / "escritorio-validacion.png"), full_page=True)

            # Al recargar: Midday guardado, End of Day con su texto aprobado.
            page.on("dialog", lambda d: d.accept())
            await page.reload()
            midday = page.get_by_role("region", name="Midday Motivation")
            fin = page.get_by_role("region", name="End of Day Recognition")
            await expect(midday.get_by_label("Subject")).to_have_value("¡Gran mañana, {{user_first_name}}! 💪", timeout=20_000)
            await expect(fin.get_by_text("Approved default", exact=True)).to_be_visible()

            # Restaurar pide confirmación y sólo toca Midday.
            await midday.get_by_role("button", name="Restore default").click()
            await expect(page.get_by_role("dialog")).to_contain_text("Midday Motivation")
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(DESTINO / "escritorio-restaurar.png"))
            await page.get_by_role("dialog").get_by_role("button", name="Restore default").click()
            await expect(midday.get_by_label("Subject")).to_have_value("¡Buen trabajo! Sigamos adelante 💪", timeout=10_000)

            # Recipients: apagados, independientes, persisten.
            await page.get_by_role("tab", name="Recipients").click()
            mediodia = page.get_by_role("switch", name="Midday Motivation for Supervisor Tester")
            fin_dia = page.get_by_role("switch", name="End of Day Recognition for Supervisor Tester")
            await expect(mediodia).to_be_visible(timeout=20_000)
            await expect(mediodia).to_have_attribute("aria-checked", "false")
            await expect(fin_dia).to_have_attribute("aria-checked", "false")
            await mediodia.click()
            await expect(mediodia).to_have_attribute("aria-checked", "true", timeout=10_000)
            await expect(fin_dia).to_have_attribute("aria-checked", "false")
            await page.screenshot(path=str(DESTINO / "escritorio-recipients.png"), full_page=True)

            await page.reload()
            await page.get_by_role("tab", name="Recipients").click()
            await expect(
                page.get_by_role("switch", name="Midday Motivation for Supervisor Tester")
            ).to_have_attribute("aria-checked", "true", timeout=20_000)
            await contexto.close()
        finally:
            await navegador.close()

    fila = (await _filas(
        "SELECT midday_enabled, end_of_day_enabled FROM activity_email_preference WHERE user_id = :u",
        u=supervisor,
    ))[0]
    assert fila.midday_enabled is True and fila.end_of_day_enabled is False


async def test_recipients_en_movil_sin_desbordar(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _conceder(seeded, "route_admin")
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(URL)
            await expect(page.get_by_role("region", name="Midday Motivation")).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "movil-templates.png"), full_page=True)
            await page.get_by_role("tab", name="Recipients").click()
            # La tabla se oculta en móvil: el interruptor visible es el de la tarjeta.
            tarjeta = page.get_by_role("switch", name="Midday Motivation for Supervisor Tester")
            await expect(tarjeta).to_be_visible(timeout=20_000)
            await expect(page.get_by_role("table")).to_be_hidden()
            await page.screenshot(path=str(DESTINO / "movil-recipients.png"), full_page=True)
            ancho = await page.evaluate("document.documentElement.scrollWidth")
            assert ancho <= MOVIL["width"], ancho
            await contexto.close()
        finally:
            await navegador.close()


async def test_sin_la_capacidad_no_hay_enlace_ni_pagina(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/vehicles")
            await expect(page.get_by_text("Vehicles").first).to_be_visible(timeout=20_000)
            await expect(page.get_by_role("link", name="Activity Emails")).to_have_count(0)
            await page.goto(URL)
            await expect(page.get_by_role("tab", name="Recipients")).to_have_count(0)
            await contexto.close()
        finally:
            await navegador.close()
