"""El cero con motivo, dibujado. Escritorio y móvil.

Por qué hace falta el navegador aquí
-------------------------------------
El dato nuevo —`mileage_unresolved`— no sirve de nada si la pantalla no lo
enseña, y ésa fue exactamente la forma del problema original: el servidor sabía
que un viaje había terminado sin kilometraje y la interfaz lo dibujaba como un
cero mudo. Un test de API no habría detectado eso.

Se comprueba en los dos tamaños porque el marcador vive en tres componentes
distintos —la tabla, el panel de detalle y la tarjeta móvil— y los tres tenían
su propia copia de la leyenda de millas.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from app.routers_api.mileage.routing import set_road_router
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.test_mileage_cross_surface import (
    _abrir_jornada,
    _calcular,
    _estado_de,
    _supervisor,
    _viaje_con_evidencia,
)
from tests.integration.test_mileage_unresolved_visibility import RouterQueRechaza

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}


async def _un_viaje_sin_resolver(alpha_client, seeded, unidad: str) -> None:
    """Evidencia completa y el proveedor rechazando: `calculation_failed`."""
    previo = set_road_router(RouterQueRechaza())
    try:
        await _supervisor(alpha_client, seeded, unidad=unidad)
        await _abrir_jornada(alpha_client, seeded)
        viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
        await _calcular()
        estado, _ = await _estado_de(viaje["id"])
        assert estado == "calculation_failed", f"la preparación no falló: {estado}"
    finally:
        set_road_router(previo)


async def test_la_tabla_dice_por_que_el_cero_es_cero(
    seeded, alpha_client, live_server
):
    """Escritorio: `0.0 mi · 1 unresolved`, y **no** `+ pending`."""
    from playwright.async_api import async_playwright

    await _un_viaje_sin_resolver(alpha_client, seeded, "V-UNRES-1")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/today")

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)

            await expect(
                page.get_by_text("1 unresolved", exact=False).first
            ).to_be_visible(timeout=20_000)

            # El control que hace discriminante al anterior: un terminal no es
            # un pendiente, y confundirlos prometería una cifra que no llegará.
            await expect(page.get_by_text("+ pending", exact=False)).to_have_count(0)
        finally:
            await navegador.close()


async def test_el_movil_tambien_lo_dice(seeded, alpha_client, live_server):
    """Móvil: la tarjeta lleva el mismo motivo que la tabla."""
    from playwright.async_api import async_playwright

    await _un_viaje_sin_resolver(alpha_client, seeded, "V-UNRES-2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/today")

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)
            await expect(
                page.get_by_text("1 unresolved", exact=False).first
            ).to_be_visible(timeout=20_000)
        finally:
            await navegador.close()


async def test_sin_viajes_no_aparece_ningun_motivo(
    seeded, alpha_client, live_server
):
    """El control del conjunto: una jornada vacía no estrena marcador.

    Sin esto, un marcador que se dibujara siempre pasaría los dos tests de
    arriba — y habríamos cambiado un cero mudo por un ruido constante.
    """
    from playwright.async_api import async_playwright

    await _supervisor(alpha_client, seeded, unidad="V-UNRES-3")
    await _abrir_jornada(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/today")

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)
            await expect(page.get_by_text("unresolved", exact=False)).to_have_count(0)
            await expect(page.get_by_text("+ pending", exact=False)).to_have_count(0)
        finally:
            await navegador.close()
