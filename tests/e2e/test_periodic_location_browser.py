"""RTE-LOC-02 U2 en el navegador.

* Configuración: la pantalla guarda, enseña el estado y el texto del aviso.
* Apagada (por defecto): cero muestras periódicas; los puntos de evento, igual.
* Encendida: la primera muestra sale al estar la jornada activa, y My Route
  dice que se registra la ubicación periódicamente.
* Dos pestañas de la misma jornada: una sola muestra por intervalo.

Lo que aquí **no** se prueba (PENDING VALIDATION en dispositivo real): pantalla
bloqueada, pestaña en segundo plano del sistema operativo, ahorro de batería.

Capturas en `var/screenshots/periodic-location/`.
"""

from __future__ import annotations

import pathlib
from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL
from tests.integration.test_activity_email_delivery import _capacidades
from tests.integration.test_activity_emails import _conceder

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/periodic-location")
LAT, LON = 43.7311, 7.4197
AVISO = "CER Route records your location periodically while you use the app during your workday."


@asynccontextmanager
async def _navegador(live_server, viewport=MOVIL):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=viewport, permissions=["geolocation"],
                geolocation={"latitude": LAT, "longitude": LON, "accuracy": 12},
            )
            yield contexto
        finally:
            await navegador.close()


async def _contar(tabla: str, company_id: int) -> int:
    async with async_session_maker() as s:
        return int(await s.scalar(text(f"SELECT count(*) FROM {tabla} WHERE company_id = :c"), {"c": company_id}))


async def _configurar(company_id: int, encendida: bool, intervalo: int = 60) -> None:
    async with async_session_maker() as s:
        await s.execute(
            text("INSERT INTO location_capture_setting (company_id, enabled, interval_seconds) VALUES (:c, :e, :i)"),
            {"c": company_id, "e": encendida, "i": intervalo},
        )
        await s.commit()


async def _empezar(page) -> None:
    await page.goto("/route")
    await page.get_by_role("button", name="Start Work").click(timeout=25_000)
    await expect(page.get_by_text("What's next?")).to_have_count(1, timeout=25_000)


async def _esperar_muestras(company_id: int, cuantas: int, segundos: int = 20) -> int:
    import asyncio

    for _ in range(segundos):
        if await _contar("location_sample", company_id) >= cuantas:
            break
        await asyncio.sleep(1)
    return await _contar("location_sample", company_id)


async def test_pantalla_de_configuracion(seeded, live_server):
    DESTINO.mkdir(parents=True, exist_ok=True)
    await _conceder(seeded, "route_admin")
    await _capacidades(seeded, "route_admin", "route.locationcapture.manage")
    async with _navegador(live_server, ESCRITORIO) as contexto:
        page = await contexto.new_page()
        await abrir_sesion(page, seeded.alpha.users["route_admin"].email, conceder_ubicacion=False)
        await page.goto("/admin/route/vehicles")
        await page.get_by_role("link", name="Location Capture").first.click()
        ajustes = page.get_by_role("region", name="Periodic Location Capture")
        await expect(ajustes.get_by_role("status")).to_contain_text("Off", timeout=20_000)
        await ajustes.get_by_label("Enable periodic capture").check()
        await expect(ajustes).to_contain_text(AVISO)
        await ajustes.get_by_role("button", name="Save").click()
        await expect(ajustes.get_by_role("status")).to_contain_text("On — every 300 s", timeout=20_000)
        await page.screenshot(path=str(DESTINO / "escritorio-configuracion.png"), full_page=True)

        await page.set_viewport_size(MOVIL)
        await page.screenshot(path=str(DESTINO / "movil-configuracion.png"), full_page=True)
        assert await page.evaluate("document.documentElement.scrollWidth") <= MOVIL["width"]

    async with async_session_maker() as s:
        fila = (await s.execute(text("SELECT enabled, interval_seconds FROM location_capture_setting"))).one()
    assert (fila.enabled, fila.interval_seconds) == (True, 300)


async def test_apagada_no_hay_muestras_y_los_eventos_siguen(seeded, live_server):
    alpha = seeded.alpha
    async with _navegador(live_server) as contexto:
        page = await contexto.new_page()
        await abrir_sesion(page, alpha.users["supervisor"].email, conceder_ubicacion=False)
        await _empezar(page)
        await expect(page.get_by_text(AVISO)).to_have_count(0)
        await page.wait_for_timeout(8_000)
    assert await _contar("location_sample", alpha.id) == 0
    assert await _contar("location_fix", alpha.id) == 1, "el punto de Start Work no depende del interruptor"


async def test_encendida_toma_la_primera_muestra_y_lo_dice(seeded, live_server):
    DESTINO.mkdir(parents=True, exist_ok=True)
    alpha = seeded.alpha
    await _configurar(alpha.id, True)
    async with _navegador(live_server) as contexto:
        page = await contexto.new_page()
        await abrir_sesion(page, alpha.users["supervisor"].email, conceder_ubicacion=False)
        await _empezar(page)
        await expect(page.get_by_text(AVISO)).to_have_count(1, timeout=20_000)
        await page.screenshot(path=str(DESTINO / "movil-my-route-aviso.png"), full_page=True)
        assert await _esperar_muestras(alpha.id, 1) == 1
    assert await _contar("location_fix", alpha.id) == 1, "la captura por evento no cambia"
    async with async_session_maker() as s:
        fila = (await s.execute(text("SELECT user_id, interval_seconds_applied FROM location_sample"))).one()
    assert (fila.user_id, fila.interval_seconds_applied) == (alpha.users["supervisor"].id, 60)


async def test_dos_pestanas_una_sola_muestra(seeded, live_server):
    alpha = seeded.alpha
    await _configurar(alpha.id, True)
    async with _navegador(live_server) as contexto:
        una = await contexto.new_page()
        await abrir_sesion(una, alpha.users["supervisor"].email, conceder_ubicacion=False)
        await _empezar(una)
        otra = await contexto.new_page()
        await otra.goto("/route")
        await expect(otra.get_by_text("What's next?")).to_have_count(1, timeout=25_000)
        await _esperar_muestras(alpha.id, 1)
        await una.wait_for_timeout(8_000)
        assert await _contar("location_sample", alpha.id) == 1, "una muestra por intervalo, no una por pestaña"
