"""RTE-MAIL-CLOSE-01 · CP2 en el navegador: estado leído, Delivery History y
zona operativa de la compañía, en escritorio y móvil.

Capturas en `var/screenshots/mail-close/`.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from app.routers_api.activityemails import delivery
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL
from tests.integration.test_activity_email_delivery import (  # noqa: F401 — fixture
    _activar,
    _capacidades,
    _jornada_en,
    _pedido,
    _utc,
    envio_real,
)
from tests.integration.test_activity_emails import _conceder

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/mail-close")
URL = "/admin/route/activity-emails"


@pytest.fixture
def mediodia_habilitado(monkeypatch):
    """Antes de `live_server`: el servidor de prueba hereda el entorno al arrancar."""
    monkeypatch.setenv("MAIL_REAL_SEND_TYPES", "midday_motivation")


async def _con_historial(seeded, cliente):
    await _jornada_en(cliente, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _conceder(seeded, "route_admin")
    await _capacidades(seeded, "route_admin", "route.activityemails.preview", "route.activityemails.send",
                       "route.activityemails.resend")
    await cliente.login(seeded.alpha.users["route_admin"].email)
    pedido = _pedido(seeded, "supervisor", "midday_motivation")
    assert (await cliente.post("/api/activity-emails/reports/send", json=pedido)).status_code == 200
    assert (await cliente.post("/api/activity-emails/reports/resend",
                               json={**pedido, "expected_resends": 0})).status_code == 200
    # Una pasada del job de DigitalOcean (apagado): el estado debe verla.
    await delivery.despachar_vencidos(source="reconcile")


async def test_estado_e_historial_en_escritorio(seeded, mediodia_habilitado, envio_real, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _con_historial(seeded, alpha_client)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(URL)
            estado = page.get_by_role("region", name="Delivery status")
            await expect(estado).to_contain_text("Real sending enabled for: Midday Motivation", timeout=20_000)
            await expect(estado).to_contain_text("Automatic delivery: Off")
            await expect(estado).to_contain_text("DigitalOcean job: last pass")
            await expect(estado).to_contain_text("In-app scheduler: not observed yet")
            await expect(estado).to_contain_text("does not confirm it reached the inbox")
            await expect(page.get_by_text("pendiente de habilitación")).to_have_count(0)

            await page.get_by_role("tab", name="Delivery history").click()
            historia = page.get_by_role("region", name="Delivery history")
            fila = historia.get_by_role("row", name="Midday Motivation")
            await expect(fila).to_contain_text("Supervisor Tester", timeout=20_000)
            await expect(fila).to_contain_text("Send now")
            await expect(fila).to_contain_text("Accepted by the mail provider (delivery not confirmed)")
            await expect(fila).to_contain_text("Resend #1")
            await expect(fila).to_contain_text("America/New_York")
            await page.screenshot(path=str(DESTINO / "escritorio-historial.png"), full_page=True)

            await historia.get_by_label("Trigger").select_option("scheduler")
            await expect(historia).to_contain_text("No deliveries match these filters.")
            await historia.get_by_label("Trigger").select_option("resend")
            await expect(historia.get_by_role("row", name="Midday Motivation")).to_be_visible()
            await contexto.close()
        finally:
            await navegador.close()


async def test_historial_en_movil_sin_scroll_horizontal(seeded, mediodia_habilitado, envio_real, alpha_client,
                                                        live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _con_historial(seeded, alpha_client)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(URL)
            await expect(page.get_by_role("region", name="Delivery status")).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "movil-estado.png"), full_page=True)
            await page.get_by_role("tab", name="Delivery history").click()
            historia = page.get_by_role("region", name="Delivery history")
            await expect(historia.get_by_role("listitem").first).to_contain_text("Resend #1", timeout=20_000)
            await page.screenshot(path=str(DESTINO / "movil-historial.png"), full_page=True)
            assert await page.evaluate("document.documentElement.scrollWidth") <= MOVIL["width"]
            await contexto.close()
        finally:
            await navegador.close()


async def test_zona_operativa_desde_el_perfil_de_la_compania(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    from tests.integration.test_org_hierarchy import _filas

    DESTINO.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["owner"].email)
            await page.goto("/admin/companies/profile")
            zona = page.get_by_label("Operational time zone")
            await expect(zona).to_have_value("", timeout=20_000)
            await zona.select_option("America/Chicago")
            await page.get_by_role("button", name="Save Changes").click()
            await expect(page.get_by_text("Company profile updated").first).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "escritorio-zona-compania.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()
    fila = (await _filas("SELECT operational_time_zone FROM company WHERE id = :c", c=seeded.alpha.id))[0]
    assert fila.operational_time_zone == "America/Chicago"
