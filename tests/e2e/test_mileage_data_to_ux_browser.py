"""La cifra exacta, dibujada en las dos pantallas y en los dos tamaños.

Por qué hace falta otro archivo de navegador
---------------------------------------------
El suite de navegador que ya existe comprueba 12,4 millas, y 12,4 es el mismo
número por las dos fórmulas que convivían en el repositorio. Es decir: habría
seguido en verde con el defecto puesto.

Aquí se conduce el navegador contra **57 695 m**, que es donde las dos fórmulas
discrepan: la exacta publica 35,9 y la truncada 35,8. Eso convierte estas
comprobaciones en discriminantes — detectan el defecto, no sólo acompañan.

Qué cubre
---------
MV-03 y MV-05 del cierre: que lo que devuelven las APIs sea lo que el usuario
**ve**, en Today / Live y en Activity Explorer, en escritorio y en móvil.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from app.routers_api.mileage.routing import set_road_router
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.test_mileage_cross_surface import (
    _abrir_jornada,
    _calcular,
    _dia_de_la_jornada,
    _estado_de,
    _supervisor,
    _viaje_con_evidencia,
)
from tests.integration.test_mileage_data_to_ux import (
    METROS_DISCRIMINANTES,
    MILLAS_DE_LA_FORMULA_VIEJA,
    MILLAS_EXACTAS,
    RouterDeDistanciaFija,
)

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}


async def _viaje_discriminante(alpha_client, seeded, unidad: str):
    """Un viaje calculado con la distancia que separa las dos fórmulas."""
    fijo = RouterDeDistanciaFija(METROS_DISCRIMINANTES)
    previo = set_road_router(fijo)
    try:
        await _supervisor(alpha_client, seeded, unidad=unidad)
        jornada = await _abrir_jornada(alpha_client, seeded)
        viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
        await _calcular()
        estado, metros = await _estado_de(viaje["id"])
        assert estado == "calculated", f"la preparación no calculó: {estado}"
        assert metros == METROS_DISCRIMINANTES, metros
        return await _dia_de_la_jornada(jornada["id"])
    finally:
        set_road_router(previo)


async def _cifra_visible(page):
    """La cifra exacta está, y la de la fórmula vieja no está en ninguna parte.

    La segunda comprobación es la que convierte el verde en evidencia: sin ella,
    un cambio que dejara de dibujar millas pasaría si por casualidad el texto
    apareciera en otro sitio.
    """
    await expect(page.get_by_text(f"{MILLAS_EXACTAS} mi", exact=False).first).to_be_visible(
        timeout=20_000
    )
    await expect(
        page.get_by_text(f"{MILLAS_DE_LA_FORMULA_VIEJA} mi", exact=False)
    ).to_have_count(0)


async def _en_today_live(page):
    await page.goto("/admin/route/today")
    await expect(page.get_by_role("heading", name="Today / Live")).to_have_count(
        1, timeout=20_000
    )
    await _cifra_visible(page)


async def _en_activity(page, dia, *, fijar_fecha: bool = True):
    """El Explorer no toma la fecha de la URL: se fija con su control `Date`.

    En móvil ese control **no se dibuja** —la línea base V0.7 oculta los campos
    del filtro en pantalla estrecha—, así que allí sólo se puede mirar el día
    actual. Es exactamente el día del viaje, de modo que la comprobación sigue
    siendo válida; lo que no se puede en móvil es navegar a otro día.
    """
    await page.goto("/admin/route/activity")
    await expect(
        page.get_by_role("heading", name="Activity", exact=True)
    ).to_have_count(1, timeout=20_000)
    if fijar_fecha:
        await page.get_by_label("Date").fill(dia.isoformat())
    await _cifra_visible(page)


async def test_today_live_dibuja_la_cifra_exacta(seeded, alpha_client, live_server):
    """MV-03, escritorio."""
    from playwright.async_api import async_playwright

    await _viaje_discriminante(alpha_client, seeded, "V-UX-1")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await _en_today_live(page)
        finally:
            await navegador.close()


async def test_activity_dibuja_la_cifra_exacta(seeded, alpha_client, live_server):
    """MV-05, escritorio."""
    from playwright.async_api import async_playwright

    dia = await _viaje_discriminante(alpha_client, seeded, "V-UX-2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await _en_activity(page, dia, fijar_fecha=False)
        finally:
            await navegador.close()


async def test_el_movil_dibuja_la_misma_cifra_exacta(
    seeded, alpha_client, live_server
):
    """MV-03 y MV-05 en móvil: el mismo hecho, no una presentación distinta."""
    from playwright.async_api import async_playwright

    dia = await _viaje_discriminante(alpha_client, seeded, "V-UX-3")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await _en_today_live(page)
            await _en_activity(page, dia, fijar_fecha=False)
        finally:
            await navegador.close()
