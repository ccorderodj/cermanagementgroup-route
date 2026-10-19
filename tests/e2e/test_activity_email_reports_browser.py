"""«Generate report» y «Send now» en el navegador (RTE-MAIL-CP4-02).

* Con datos reales y la plantilla guardada; la vista previa dice ventana, zona,
  corte y si es Parcial o Final.
* «Send now» exige confirmación, va al destinatario configurado y el resultado
  dice «Accepted by the mail provider (delivery not confirmed)».
* Apagado por defecto: sin el tipo habilitado, el botón está deshabilitado y se
  dice por qué.

Capturas en `var/screenshots/activity-email-reports/`.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL
from tests.integration.test_activity_email_delivery import DIA, _activar, _capacidades, _jornada_en, _utc
from tests.integration.test_activity_emails import _conceder
from tests.integration.test_org_hierarchy import _filas

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/activity-email-reports")
URL = "/admin/route/activity-emails"


@pytest.fixture
def mediodia_habilitado(monkeypatch):
    """Antes de `live_server`: el servidor de prueba hereda el entorno al arrancar."""
    monkeypatch.setenv("MAIL_REAL_SEND_TYPES", "midday_motivation")


async def _preparar(seeded, cliente, *capacidades):
    await _jornada_en(cliente, seeded, "supervisor", inicio=_utc(13), fin_actividad=_utc(15), fin_jornada=_utc(21))
    await _activar(seeded, "supervisor", "midday_enabled")
    await _conceder(seeded, "route_admin")
    await _capacidades(seeded, "route_admin", *capacidades)


async def _abrir_generar(page):
    midday = page.get_by_role("region", name="Midday Motivation")
    await midday.get_by_role("button", name="Generate report").click()
    dialogo = page.get_by_role("dialog")
    await dialogo.get_by_label("Person").select_option(label="Supervisor Tester", timeout=20_000)
    await dialogo.get_by_label("Operational day").fill(DIA.isoformat())
    await dialogo.get_by_role("button", name="Generate report").click()
    return dialogo


async def test_generar_y_enviar_con_confirmacion(seeded, mediodia_habilitado, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _preparar(seeded, alpha_client, "route.activityemails.preview", "route.activityemails.send")
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(URL)
            dialogo = await _abrir_generar(page)
            vista = dialogo.get_by_role("region", name="Report preview")
            await expect(vista).to_contain_text("Final", timeout=20_000)
            await expect(vista).to_contain_text("1 activity")
            await expect(vista).to_contain_text("America/New_York")
            await expect(vista).to_contain_text("1 visita a cliente")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(DESTINO / "escritorio-vista-real.png"))

            await dialogo.get_by_role("button", name="Send now").click()
            await expect(dialogo.get_by_role("group", name="Confirm sending")).to_contain_text("Supervisor Tester")
            await dialogo.get_by_label("Reason (optional)").fill("Prueba E2E: el cron no corrió")
            await dialogo.get_by_role("button", name="Confirm and send").click()
            await expect(dialogo.get_by_role("status")).to_contain_text(
                "Accepted by the mail provider (delivery not confirmed)", timeout=20_000
            )
            await expect(dialogo).to_contain_text("History for this day")
            # Ya enviado: no se ofrece mandarlo otra vez, y se dice por qué.
            await expect(dialogo.get_by_role("button", name="Send now")).to_be_disabled()
            await expect(dialogo).to_contain_text("Already accepted by the mail provider")
            await page.screenshot(path=str(DESTINO / "escritorio-enviado.png"))
            await contexto.close()
        finally:
            await navegador.close()

    filas = await _filas("SELECT status, source, request_reason FROM activity_email_delivery")
    assert [(f.status, f.source, f.request_reason) for f in filas] == [
        ("accepted_by_provider", "manual", "Prueba E2E: el cron no corrió"),
    ]


async def test_apagado_por_defecto_lo_dice_en_movil(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _preparar(seeded, alpha_client, "route.activityemails.preview", "route.activityemails.send")
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(URL)
            dialogo = await _abrir_generar(page)
            await expect(dialogo).to_contain_text("Real sending of this report is not enabled yet", timeout=20_000)
            await expect(dialogo.get_by_role("button", name="Send now")).to_be_disabled()
            await page.screenshot(path=str(DESTINO / "movil-apagado.png"), full_page=True)
            assert await page.evaluate("document.documentElement.scrollWidth") <= MOVIL["width"]
            await contexto.close()
        finally:
            await navegador.close()
    assert await _filas("SELECT 1 FROM activity_email_delivery") == []


async def test_sin_permiso_de_envio_no_hay_boton(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    await _preparar(seeded, alpha_client, "route.activityemails.preview")
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(URL)
            dialogo = await _abrir_generar(page)
            await expect(dialogo.get_by_role("region", name="Report preview")).to_be_visible(timeout=20_000)
            await expect(dialogo.get_by_role("button", name="Send now")).to_have_count(0)
            await contexto.close()
        finally:
            await navegador.close()


async def test_un_mando_genera_su_propio_reporte(seeded, alpha_client, live_server):
    """El CEO se encuentra a sí mismo en la lista de «Generate report»."""
    from playwright.async_api import async_playwright

    from tests.integration.test_org_hierarchy import _organigrama

    await _organigrama(alpha_client, seeded, perfiles=False)
    await _capacidades(seeded, "CEO", "route.activityemails.manage", "route.activityemails.preview")
    yo = seeded.alpha.users["ceo"]
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, yo.email)
            await page.goto(URL)
            estrategico = page.get_by_role("region", name="Strategic Midday Report")
            await estrategico.get_by_role("button", name="Generate report").click()
            dialogo = page.get_by_role("dialog")
            await dialogo.get_by_label("Manager").select_option(value=str(yo.id), timeout=20_000)
            await dialogo.get_by_label("Operational day").fill(DIA.isoformat())
            await dialogo.get_by_role("button", name="Generate report").click()
            await expect(dialogo.get_by_role("region", name="Report preview")).to_be_visible(timeout=20_000)
            await contexto.close()
        finally:
            await navegador.close()
