"""Las millas, en la pantalla: Today / Live y Activity, el mismo número.

Qué cierra este archivo
------------------------
La última capa de la cadena. La integración ya demuestra que la cifra llega
entera a las dos APIs; aquí se comprueba que **se dibuja**, que es donde el
síntoma de campo se ve: «no se ven las millas».

Si la API dijera 12,4 y la pantalla `0.0 mi`, el defecto sería de cableado de
interfaz y habría que corregirlo ahí. Este test es lo que distingue ese caso de
un problema de datos aguas arriba.

Por qué se ejercita el motor y no se escribe la fila a mano
------------------------------------------------------------
Se sustituye el adaptador de routing por uno que devuelve una distancia
conocida y se deja que el motor haga su trabajo. Así lo que llega a la pantalla
ha pasado por los waypoints, la comprobación de plausibilidad y la
consolidación, que es el camino real.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.test_mileage_cross_surface import (
    MILLAS_ESPERADAS,
    RouterFijo,
    _abrir_jornada,
    _calcular,
    _dia_de_la_jornada,
    _estado_de,
    _supervisor,
    _viaje_con_evidencia,
)
from app.routers_api.mileage.routing import set_road_router

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}


async def _un_viaje_calculado(alpha_client, seeded, unidad: str):
    """Deja un viaje con kilometraje `calculated` y devuelve su día."""
    fijo = RouterFijo()
    previo = set_road_router(fijo)
    try:
        await _supervisor(alpha_client, seeded, unidad=unidad)
        jornada = await _abrir_jornada(alpha_client, seeded)
        viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
        await _calcular()
        estado, _ = await _estado_de(viaje["id"])
        assert estado == "calculated", f"la preparación no calculó: {estado}"
        return await _dia_de_la_jornada(jornada["id"])
    finally:
        set_road_router(previo)


async def test_today_live_dibuja_las_millas_calculadas(
    seeded, alpha_client, live_server,
):
    """§7: la fila del supervisor y el total del día enseñan la misma cifra.

    Se busca el número exacto. Una aserción sobre «hay algo parecido a millas»
    pasaría igual con `0.0`, que es justo el síntoma que se viene a descartar.
    """
    from playwright.async_api import async_playwright

    await _un_viaje_calculado(alpha_client, seeded, "V-MIL-UI-1")

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

            # La tarjeta del total del día.
            await expect(page.get_by_text("Total miles today")).to_have_count(1)
            # Y el número, en la fila y en el total. Aparece dos veces porque es
            # un solo supervisor: su fila **es** el total del día.
            await expect(
                page.get_by_text(MILLAS_ESPERADAS, exact=True)
            ).to_have_count(2, timeout=20_000)
            # Y no se dibuja como pendiente, porque ya no lo está.
            await expect(page.get_by_text("+ pending")).to_have_count(0)
        finally:
            await navegador.close()


async def test_activity_explorer_dibuja_las_millas_calculadas(
    seeded, alpha_client, live_server,
):
    """§8: el resumen del día y la tarjeta de la parada, con la misma cifra."""
    from playwright.async_api import async_playwright

    dia = await _un_viaje_calculado(alpha_client, seeded, "V-MIL-UI-2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/activity")

            await expect(
                page.get_by_role("heading", name="Activity", exact=True)
            ).to_have_count(1, timeout=20_000)
            await page.get_by_label("Date").fill(dia.isoformat())

            # El resumen del día: `12.4 mi`.
            await expect(
                page.get_by_text(f"{MILLAS_ESPERADAS} mi", exact=True)
            ).to_have_count(1, timeout=20_000)
            # Y la tarjeta de la parada, que lleva las millas de su viaje.
            await expect(
                page.get_by_text(f"{MILLAS_ESPERADAS} mi", exact=False)
            ).not_to_have_count(0)
            await expect(page.get_by_text("+ pending")).to_have_count(0)
        finally:
            await navegador.close()


async def test_un_calculo_pendiente_se_marca_en_las_dos_pantallas(
    seeded, alpha_client, live_server,
):
    """§4.3 en la pantalla: pendiente no se dibuja como un total cerrado.

    Es el estado real del entorno desplegado hoy, así que conviene que esté
    comprobado: lo que la gente ve cuando no hay motor de carretera.
    """
    from playwright.async_api import async_playwright

    await _supervisor(alpha_client, seeded, unidad="V-MIL-UI-3")
    jornada = await _abrir_jornada(alpha_client, seeded)
    await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    dia = await _dia_de_la_jornada(jornada["id"])

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
            await expect(page.get_by_text("+ pending").first).to_be_visible(
                timeout=20_000
            )

            await page.goto("/admin/route/activity")
            await expect(
                page.get_by_role("heading", name="Activity", exact=True)
            ).to_have_count(1, timeout=20_000)
            await page.get_by_label("Date").fill(dia.isoformat())
            await expect(page.get_by_text("+ pending").first).to_be_visible(
                timeout=20_000
            )
        finally:
            await navegador.close()


async def test_el_movil_enseña_la_misma_cifra(seeded, alpha_client, live_server):
    """§7.6: escritorio y móvil coinciden. No es una presentación distinta."""
    from playwright.async_api import async_playwright

    await _un_viaje_calculado(alpha_client, seeded, "V-MIL-UI-4")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/today")

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)
            await expect(
                page.get_by_text(MILLAS_ESPERADAS, exact=False).first
            ).to_be_visible(timeout=20_000)
        finally:
            await navegador.close()
