"""Today / Live en un navegador real: escritorio y móvil, contra V0.7.

Qué se valida aquí y qué no
----------------------------
No la exactitud de los datos —eso tiene sus propios tests de integración contra
PostgreSQL— sino la **fidelidad de la experiencia aprobada**: que el escritorio
sea resumen, lista y panel; que el móvil sea lista primero y detalle a pantalla
completa con vuelta; y que ninguna de las dos se desborde.

Sin `data-testid`
-----------------
Como el resto de la suite de navegador, y no por estilo: el build de producción
los **elimina** de los `.tsx` (`isTsx && isProd` en `buildBabelLoader`), así que
un test que los buscara fallaría contra el bundle que se despliega. Se localiza
por rol, encabezado y texto visible, que además es lo que ve el usuario.

La diferencia móvil no es un ancho
-----------------------------------
V0.7 define dos presentaciones distintas, no una con dos tamaños. Por eso el
test del detalle móvil comprueba que el panel lateral de escritorio **no está**:
si apareciera, significaría que alguien lo estrujó en una pantalla estrecha, que
es justo lo que §2.3 y §14 prohíben.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}

RUTA = "/admin/route/today"

#: Texto que sólo existe en la cabecera de la tabla de escritorio.
SUBTITULO_TABLA = "Select a supervisor to inspect current activity"
#: Y éste sólo en el panel lateral de escritorio.
MINI_ESTADISTICA = "activities today"


def _hueco_de_combustible(page):
    """El valor de la mini-estadística `estimated fuel`, no su etiqueta.

    Se localiza por la estructura —el `<b>` hermano de la etiqueta— porque lo
    que D-01 aprueba es el **valor neutro**, y comprobar sólo que la etiqueta
    existe dejaría pasar un número inventado debajo de ella.
    """
    return page.locator("div:has(> span:text-is('estimated fuel')) > b")


async def _preparar_supervisor(alpha_client, seeded, unidad: str) -> None:
    """Un supervisor con vehículo y jornada abierta, por API."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": unidad,
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})


async def _sin_desborde(page) -> bool:
    return not await page.evaluate(
        "() => document.documentElement.scrollWidth > window.innerWidth + 1"
    )


async def test_el_escritorio_tiene_la_estructura_aprobada(
    seeded, alpha_client, live_server,
):
    """Resumen, lista y panel, con las etiquetas y columnas de la línea base.

    Las cuatro tarjetas y las cinco columnas se comprueban por su texto visible
    porque **la terminología es del producto**: §14 prohíbe cambiarla porque
    otra palabra parezca más clara, así que verificarla es verificar fidelidad.
    """
    from playwright.async_api import async_playwright

    await _preparar_supervisor(alpha_client, seeded, "V-LIVE-D1")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)

            for etiqueta in (
                "Supervisors working", "Total miles today", "On route", "In activity",
            ):
                await expect(page.get_by_text(etiqueta, exact=True)).to_have_count(1)

            # Las pistas sólo existen en la presentación de escritorio: su
            # presencia distingue las tarjetas completas de las compactas.
            await expect(page.get_by_text("across active routes")).to_have_count(1)

            await expect(
                page.get_by_role("heading", name="Supervisors", exact=True)
            ).to_have_count(1)
            await expect(page.get_by_text(SUBTITULO_TABLA)).to_have_count(1)

            for columna in (
                "Supervisor", "Miles today", "Status",
                "Current / last activity", "Since",
            ):
                await expect(
                    page.get_by_role("columnheader", name=columna, exact=True)
                ).to_have_count(1)

            # El panel lateral está desde el principio, con el primer
            # supervisor seleccionado, como en la línea base.
            await expect(page.get_by_text(MINI_ESTADISTICA)).to_have_count(1)
            await expect(page.get_by_text("estimated fuel")).to_have_count(1)
            # D-01 de CER: el hueco se conserva y enseña el valor neutro. No un
            # coste calculado con un precio por galón inventado, que es lo que
            # la decisión descarta: un número fabricado se lee como un hecho.
            await expect(_hueco_de_combustible(page)).to_have_text("—")

            assert await _sin_desborde(page), "el escritorio desborda en horizontal"
        finally:
            await navegador.close()


async def test_seleccionar_un_supervisor_abre_el_panel(
    seeded, alpha_client, live_server,
):
    """La selección es la interacción principal de la línea base.

    El combustible estimado aparece como hueco con estado neutro: el precio por
    galón no existe en el dominio y no se inventa. Está listado como desviación
    en el reporte de entrega, no escondido aquí.
    """
    from playwright.async_api import async_playwright

    await _preparar_supervisor(alpha_client, seeded, "V-LIVE-D2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)

            fila = page.locator("tbody tr").first
            await expect(fila).to_have_count(1, timeout=20_000)
            await fila.click()

            # Acotado al panel: "Current / last activity" también es el nombre
            # de una columna, y la línea base usa el mismo rótulo en los dos
            # sitios a propósito. Buscarlo suelto encontraría los dos.
            panel = page.locator("aside")
            await expect(panel).to_have_count(1, timeout=10_000)
            await expect(panel.get_by_text("Current / last activity")).to_have_count(1)
            await expect(panel.get_by_text(MINI_ESTADISTICA)).to_have_count(1)
            await expect(panel.get_by_text("miles today")).to_have_count(1)
        finally:
            await navegador.close()


async def test_el_movil_es_lista_primero(seeded, alpha_client, live_server):
    """La lista no puede caer por debajo del pliegue.

    Es la filosofía *list-first* de la línea base, y se comprueba midiendo: la
    primera tarjeta de supervisor tiene que estar dentro de la ventana visible,
    no detrás de las tarjetas grandes.
    """
    from playwright.async_api import async_playwright

    await _preparar_supervisor(alpha_client, seeded, "V-LIVE-M1")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)

            # El resumen se condensa: las cifras siguen, las pistas no.
            await expect(page.get_by_text("Supervisors working", exact=True)).to_have_count(1)
            await expect(page.get_by_text("across active routes")).to_have_count(0)

            # Y la experiencia de escritorio no está: son dos presentaciones,
            # no una encogida.
            await expect(page.get_by_text(SUBTITULO_TABLA)).to_have_count(0)
            await expect(page.get_by_text(MINI_ESTADISTICA)).to_have_count(0)

            tarjeta = page.get_by_role("button").filter(has_text="Since").first
            await expect(tarjeta).to_have_count(1, timeout=10_000)
            caja = await tarjeta.bounding_box()
            assert caja is not None and caja["y"] < MOVIL["height"], (
                f"la lista empieza fuera de la ventana de {MOVIL['height']}px: "
                "las tarjetas la empujaron abajo"
            )

            assert await _sin_desborde(page), "el móvil desborda en horizontal"
        finally:
            await navegador.close()


async def test_el_detalle_movil_es_pantalla_completa_y_vuelve(
    seeded, alpha_client, live_server,
):
    """`adminMobileDetail`: empuje a pantalla completa y vuelta al contexto.

    Lo que se comprueba además de que abra y cierre: que **no** aparezca el
    panel lateral de escritorio. Si apareciera, sería el panel estrujado en una
    pantalla estrecha, que es lo que la línea base prohíbe.
    """
    from playwright.async_api import async_playwright

    await _preparar_supervisor(alpha_client, seeded, "V-LIVE-M2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)

            tarjeta = page.get_by_role("button").filter(has_text="Since").first
            await expect(tarjeta).to_have_count(1, timeout=20_000)
            await tarjeta.click()

            volver = page.get_by_role("button", name="Back to supervisors")
            await expect(volver).to_have_count(1, timeout=10_000)
            # Pantalla completa: ni la lista detrás ni el panel de escritorio.
            await expect(page.get_by_text("Vehicle", exact=True)).to_have_count(1)
            await expect(page.get_by_text(SUBTITULO_TABLA)).to_have_count(0)
            # D-01 también aquí: el detalle móvil conserva el hueco neutro.
            await expect(_hueco_de_combustible(page)).to_have_text("—")

            await volver.click()

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=10_000)
            await expect(
                page.get_by_role("button").filter(has_text="Since").first
            ).to_have_count(1), "la vuelta no restauró la lista"
            assert await _sin_desborde(page), "el móvil desborda tras volver"
        finally:
            await navegador.close()


async def test_sin_la_capacidad_la_pagina_no_se_sirve(
    seeded, alpha_client, live_server,
):
    """La puerta está en el servidor, no en que el menú esconda el enlace.

    Un supervisor que escriba la ruta a mano no entra: la página exige la misma
    capacidad que su API, así que el enlace nunca lleva a un 403 sorpresa ni la
    ausencia de enlace es lo que protege.
    """
    from playwright.async_api import async_playwright

    await _preparar_supervisor(alpha_client, seeded, "V-LIVE-403")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)
            respuesta = await page.goto(RUTA)

            assert respuesta is not None and respuesta.status in (403, 404), (
                f"un supervisor recibió {respuesta and respuesta.status}"
            )
        finally:
            await navegador.close()
