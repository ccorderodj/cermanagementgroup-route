"""Las capturas lado a lado que §23 exige: mockup V0.7 y producción.

Por qué es un test y no un script suelto
-----------------------------------------
Porque así se regeneran con el mismo arnés que valida el comportamiento —el
mismo `uvicorn`, el mismo tenant sembrado, los mismos tamaños de ventana— y no
dependen de que alguien recuerde cómo las sacó. Una captura que nadie puede
reproducir no es evidencia, es una ilustración.

El mockup se abre en el navegador
----------------------------------
§23 lo autoriza de forma explícita cuando extraer la imagen del fichero no es
práctico, y aquí es lo correcto además por otro motivo: capturado **al mismo
viewport** que la implementación, la comparación es de verdad lado a lado y no
entre una captura de diseño y una pantalla real a otra escala.

El mockup se conduce por su propio estado
------------------------------------------
`standalone.html` es una aplicación: guarda `state.adminPage` y
`state.activityRange` y vuelve a pintar. Para llegar a la pantalla aprobada se
pulsan sus propios botones —`[data-apage="activity"]`, `[data-range="year"]`—
en vez de inventar una URL que no tiene. Y para el móvil se le pone su clase
`device-mobile`, que es el ámbito con el que el propio mockup define su
presentación móvil.

Las imágenes van a `var/screenshots/rte08/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte08_activity_explorer_browser import (
    DIA,
    ESCRITORIO,
    MOVIL,
    RUTA,
    _historia,
)

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/rte08")

MOCKUP = pathlib.Path(
    "_cer_delivery/CER_ROUTE_RTE01_PACKAGE_V1_0/04_Mockup_Reference_V0_7/standalone.html"
)

#: Pone el mockup en la pantalla de Activity con el rango pedido, usando sus
#: propios controles. `device-mobile` es su ámbito móvil declarado.
IR_A_ACTIVITY = """(args) => {
    // El mockup trae su propio conmutador de dispositivo en la barra de
    // prototipo. Se pulsa **el suyo** en vez de ponerle la clase a mano: la
    // primera versión de esta captura lo hacía a mano, el ámbito no se aplicó
    // y la referencia móvil salió con la barra lateral de escritorio visible.
    // Una captura de referencia equivocada invalida la comparación entera.
    const dispositivo = document.querySelector(
        `[data-device="${args.movil ? 'mobile' : 'desktop'}"]`,
    );
    if (dispositivo) dispositivo.click();
    const paso = document.querySelector('[data-apage="activity"]');
    if (paso) paso.click();
    return !!paso && !!dispositivo;
}"""

CAMBIAR_RANGO = """(rango) => {
    const b = document.querySelector(`[data-range="${rango}"]`);
    if (b) b.click();
    return !!b;
}"""


async def _capturar(page, nombre: str, producidas: list[str]) -> None:
    destino = DESTINO / nombre
    await page.screenshot(path=str(destino), full_page=False)
    assert destino.exists() and destino.stat().st_size > 0, f"{nombre} salió vacía"
    producidas.append(nombre)


async def test_capturas_de_v07_y_de_produccion(seeded, alpha_client, live_server):
    """Diez capturas: raíz, jerarquía y detalle, en V0.7 y en producción."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    assert MOCKUP.exists(), f"no está el mockup aprobado en {MOCKUP}"
    await _historia(alpha_client, seeded, unidad="V-RTE08-SHOT")
    producidas: list[str] = []

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            # ── V0.7 de referencia, al mismo tamaño ────────────────────────
            for etiqueta, medida, movil in (
                ("desktop", ESCRITORIO, False),
                ("mobile", MOVIL, True),
            ):
                contexto = await navegador.new_context(viewport=medida)
                page = await contexto.new_page()
                await page.goto(MOCKUP.resolve().as_uri())
                llegó = await page.evaluate(IR_A_ACTIVITY, {"movil": movil})
                assert llegó, "el mockup no tiene el botón de la pantalla Activity"
                await expect(
                    page.get_by_text(
                        "Explore operational history by supervisor and period"
                    )
                ).to_have_count(1, timeout=10_000)

                # Día: resumen y tarjetas de parada (el estado por defecto).
                await _capturar(page, f"01-v07-{etiqueta}-day-activity.png", producidas)

                # Año: la jerarquía agrupada.
                assert await page.evaluate(CAMBIAR_RANGO, "year")
                await expect(page.get_by_text("Grouped by month")).to_have_count(
                    1, timeout=10_000
                )
                await _capturar(page, f"02-v07-{etiqueta}-year-groups.png", producidas)
                await contexto.close()

            # ── Producción ─────────────────────────────────────────────────
            for etiqueta, medida in (("desktop", ESCRITORIO), ("mobile", MOVIL)):
                contexto = await navegador.new_context(
                    base_url=live_server, viewport=medida
                )
                page = await contexto.new_page()
                await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
                await page.goto(RUTA)

                # Se espera **contenido**, no el encabezado: el encabezado
                # también existe mientras carga, y una captura del estado de
                # carga sería evidencia engañosa de fidelidad visual.
                await expect(page.get_by_text("estimated fuel")).to_have_count(
                    1, timeout=20_000
                )
                # Cómo se llega al día con historia en cada tamaño, y no es
                # un detalle de la captura: en móvil el selector de fecha **no
                # existe** —la línea base lo oculta en esta pantalla—, así que
                # el único camino al pasado es bajar por la jerarquía. Que la
                # captura use ese camino es parte de la evidencia.
                if etiqueta == "desktop":
                    await page.get_by_label("Date").fill(DIA.isoformat())
                    await page.get_by_role("button", name="Year", exact=True).click()
                else:
                    await page.get_by_role("button", name="Year", exact=True).click()

                await expect(page.get_by_text("Grouped by month")).to_have_count(
                    1, timeout=15_000
                )
                await _capturar(page, f"04-prod-{etiqueta}-year-groups.png", producidas)

                # El nivel intermedio, donde se ve el mecanismo de desglose:
                # una fila que dice a dónde lleva.
                await page.get_by_role("button").filter(has_text="View month").click()
                await expect(page.get_by_text("Grouped by week")).to_have_count(
                    1, timeout=15_000
                )
                await _capturar(page, f"05-prod-{etiqueta}-month-groups.png", producidas)

                # Y la hoja: semana → día → paradas.
                await page.get_by_role("button").filter(has_text="View week").click()
                await expect(page.get_by_text("Grouped by day")).to_have_count(
                    1, timeout=15_000
                )
                await page.get_by_role("button").filter(has_text="View day").click()
                await expect(
                    page.get_by_role("heading", name="Client Visit", exact=True)
                ).to_have_count(1, timeout=15_000)
                await _capturar(page, f"03-prod-{etiqueta}-day-activity.png", producidas)
                await contexto.close()
        finally:
            await navegador.close()

    assert len(producidas) == 10, f"faltan capturas: {producidas}"
