"""La captura de ubicación, vista desde la pantalla (RTE06 AC-8, §12, §36).

Qué sólo se puede demostrar aquí
--------------------------------
La suite de integración prueba que el servidor registra evidencia y declara
Missing. Lo que **no** puede probar es lo que el supervisor ve, y eso es un
criterio de aceptación por sí mismo: §12 enumera siete mensajes que no deben
aparecer nunca —"GPS captured", "GPS failed", "location unavailable", timeout,
aviso de precisión, estado del reintento, "Missing Location"— y §36 prohíbe
cualquier spinner que bloquee la acción.

Con el permiso denegado, que es el peor caso, el flujo de RTE05 tiene que
terminar exactamente igual. Esa es la aserción.

Por qué el permiso va denegado y no concedido
----------------------------------------------
Porque el fallo es el camino interesante. Concedido, la captura funciona y no
se vería nada aunque el código mostrara errores sólo al fallar. Denegado, el
módulo recorre su camino de fallo entero y declara Missing — y la pantalla
tiene que seguir muda.

Playwright deniega la geolocalización por defecto, así que esto es el estado
natural del contexto; se declara igualmente en el `new_context` para que quede
escrito y no dependa de un comportamiento por omisión.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}

#: Lo que §12 prohíbe mostrar durante el trabajo normal. La lista es literal, no
#: una aproximación: son las frases de la instrucción.
PROHIBIDO = (
    "GPS captured",
    "GPS failed",
    "location unavailable",
    "Location unavailable",
    "timeout",
    "Timeout",
    "accuracy",
    "Accuracy",
    "Missing Location",
    "retry",
)


@asynccontextmanager
async def _movil_sin_permiso(live_server, email: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server,
                viewport=MOVIL,
                # Explícito a propósito: es el estado que se quiere probar, no
                # un efecto secundario de que Playwright no lo conceda.
                permissions=[],
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


async def _sin_mensajes_de_ubicacion(page) -> None:
    """Ninguna de las frases de §12 está en pantalla."""
    for frase in PROHIBIDO:
        await expect(page.get_by_text(frase)).to_have_count(
            0, timeout=2_000
        ), f"§12 prohíbe mostrar «{frase}»"


async def _contar(consulta: str, company_id: int) -> int:
    async with async_session_maker() as sesion:
        return await sesion.scalar(text(consulta), {"c": company_id})


async def test_the_day_runs_normally_with_location_denied(seeded, live_server):
    """AC-8: con el permiso denegado, el día entero funciona y nada se ve.

    Se recorre el flujo de RTE05 completo —Start Work, preparar y salir,
    llegar— y se comprueba en cada pantalla que ninguna de las frases de §12
    aparece. El permiso está denegado, así que la captura falla en todos los
    eventos: es el caso en el que un módulo mal escrito hablaría.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_sin_permiso(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")

        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )
        await _sin_mensajes_de_ubicacion(page)

        # Un contexto que no exige valor de lista, para que el flujo no dependa
        # del catálogo sembrado.
        await page.get_by_role("button", name="Field task").click()
        await expect(
            page.get_by_role("button", name="Start Trip")
        ).to_have_count(1, timeout=20_000)
        await _sin_mensajes_de_ubicacion(page)

        await page.get_by_role("button", name="Start Trip").click()
        # `On Route` es la pantalla de tránsito de RTE05.
        await expect(page.get_by_role("button", name="Arrived")).to_have_count(
            1, timeout=20_000
        )
        await _sin_mensajes_de_ubicacion(page)

        await page.get_by_role("button", name="Arrived").click()
        # Llegar lleva a la parada; lo que importa aquí es que llegó.
        await expect(page.get_by_role("button", name="Arrived")).to_have_count(
            0, timeout=20_000
        )
        await _sin_mensajes_de_ubicacion(page)

    # Y el servidor sí se enteró: los eventos quedaron como Missing, que es
    # donde tiene que estar la noticia — no en la pantalla del supervisor.
    perdidos = await _contar(
        "SELECT count(*) FROM missing_location_event WHERE company_id = :c",
        seeded.alpha.id,
    )
    puntos = await _contar(
        "SELECT count(*) FROM location_fix WHERE company_id = :c", seeded.alpha.id
    )
    assert puntos == 0, "sin permiso no se puede fabricar una coordenada"
    assert perdidos >= 1, (
        "el administrador tiene que poder enterarse aunque el supervisor no vea nada"
    )


async def test_no_blocking_spinner_waits_for_location(seeded, live_server):
    """§36: la acción no espera a la ubicación.

    Se mide el tiempo entre pulsar `Start Work` y ver el workbench. El umbral es
    generoso —ocho segundos— porque lo que se quiere detectar no es lentitud:
    es que el flujo **no** esté esperando el timeout de adquisición, que por
    defecto es de diez segundos y sería inmediatamente visible aquí.

    Con el permiso denegado el error llega rápido, así que este test protege
    sobre todo contra que alguien ponga un `await` delante de `captureFor` en el
    futuro: con permiso concedido y GPS lento, ese `await` haría fallar esto.
    """
    import time

    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_sin_permiso(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")
        inicio = time.monotonic()
        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )
        transcurrido = time.monotonic() - inicio

    assert transcurrido < 8.0, (
        f"el workbench tardó {transcurrido:.1f}s: parece estar esperando a la "
        "ubicación, y §36 prohíbe que la acción espere"
    )
