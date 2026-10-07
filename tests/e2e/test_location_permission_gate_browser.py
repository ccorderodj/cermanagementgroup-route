"""La puerta de ubicación tal como la ve el supervisor (RTE10-A02).

Por qué esto no se puede probar sin navegador
----------------------------------------------
El permiso de ubicación **no existe en el servidor**. Vive en el navegador, se
concede y se revoca fuera de la pestaña, y la única forma de comprobar que la
puerta se abre y se cierra de verdad es conducir un navegador real y
concederlo y revocarlo como lo haría una persona.

Playwright lo permite por contexto: `permissions=["geolocation"]` concede y
`clear_permissions()` revoca. Eso cubre los dos sucesos que §7 y §13 exigen
detectar.

Los dos casos que no se pueden confundir
-----------------------------------------
Hay un test aquí que vale por todos los demás: **permiso concedido y sin
posición disponible**. Es lo que ocurre dentro de una nave o en una zona rural,
y §2.2 prohíbe bloquear ahí. Si la puerta se cerrara por falta de señal, media
plantilla se quedaría sin trabajar — y sería un fallo invisible en cualquier
test que conceda permiso *y* coordenadas a la vez.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

MOVIL = {"width": 390, "height": 844}
#: Atenas, Georgia. Sólo hace falta que sea una coordenada válida.
POSICION = {"latitude": 33.9519, "longitude": -83.3576}


@asynccontextmanager
async def _movil(live_server, email: str, *, conceder: bool, con_posicion=True):
    """Un navegador móvil con el permiso de ubicación concedido o no.

    `con_posicion=False` concede el permiso **sin** dar coordenadas: el
    navegador acepta la petición y no devuelve ningún punto, que es exactamente
    lo que pasa bajo techo.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            opciones: dict = {"base_url": live_server, "viewport": MOVIL}
            if conceder:
                opciones["permissions"] = ["geolocation"]
                if con_posicion:
                    opciones["geolocation"] = POSICION
            contexto = await navegador.new_context(**opciones)
            page = await contexto.new_page()
            # Aqui la ausencia de permiso ES la prueba, asi que el helper
            # no debe concederlo por su cuenta.
            await abrir_sesion(page, email, conceder_ubicacion=False)
            yield contexto, page
        finally:
            await navegador.close()


async def _esperar_puerta(page):
    await expect(
        page.get_by_role("heading", name="Location Required")
    ).to_be_visible(timeout=20_000)


async def _esperar_operativo(page):
    await expect(
        page.get_by_role("heading", name="Location Required")
    ).to_have_count(0, timeout=20_000)


# ── El permiso decide ───────────────────────────────────────────────────────


async def test_sin_permiso_la_puerta_bloquea_my_route(
    seeded, alpha_client, live_server
):
    """Sin permiso no hay experiencia operativa, y no hay forma de saltársela."""
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=False
    ) as (_ctx, page):
        await page.goto("/route")
        await _esperar_puerta(page)

        await expect(
            page.get_by_text("CER Route requires location access")
        ).to_be_visible()
        await expect(page.get_by_role("button", name="Enable Location")).to_be_visible()

        # Las tres ausencias que §5.1 exige, y son tan importantes como la
        # presencia de la puerta: cada una seria un camino para seguir sin
        # permiso.
        await expect(page.get_by_role("button", name="Start Work")).to_have_count(0)
        await expect(page.get_by_role("button", name="Check Again")).to_have_count(0)
        await expect(page.get_by_text("without location")).to_have_count(0)


async def test_con_permiso_la_pantalla_es_la_normal(seeded, alpha_client, live_server):
    """El control del conjunto: con permiso, la puerta no estorba.

    Sin este test, una puerta que bloqueara siempre pasaría el anterior.
    """
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=True
    ) as (_ctx, page):
        await page.goto("/route")
        await _esperar_operativo(page)
        await expect(page.get_by_role("button", name="Start Work")).to_be_visible(
            timeout=20_000
        )


async def test_permiso_concedido_sin_senal_NO_bloquea(
    seeded, alpha_client, live_server
):
    """§2.2 y §15.15: el caso de la nave industrial.

    Permiso concedido y ninguna coordenada disponible. El supervisor tiene que
    poder trabajar: la falta de señal la resuelve el modelo de evidencia que ya
    existe —Fresh, Cached, Recovery, Missing—, no una puerta.

    Es el test que separa «permiso» de «señal». Sin él, una implementación que
    exigiera un punto GPS para abrir pasaría todos los demás.
    """
    async with _movil(
        live_server,
        seeded.alpha.users["supervisor"].email,
        conceder=True,
        con_posicion=False,
    ) as (_ctx, page):
        await page.goto("/route")
        await _esperar_operativo(page)
        await expect(page.get_by_role("button", name="Start Work")).to_be_visible(
            timeout=20_000
        )


# ── Revocación y restauración ───────────────────────────────────────────────


async def test_revocar_el_permiso_cierra_la_puerta_al_recargar(
    seeded, alpha_client, live_server
):
    """§13: tras recargar no se usa un valor en memoria, se vuelve a preguntar."""
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=True
    ) as (contexto, page):
        await page.goto("/route")
        await _esperar_operativo(page)

        await contexto.clear_permissions()
        await page.reload()

        await _esperar_puerta(page)


async def test_conceder_el_permiso_abre_la_puerta_sin_boton_de_reintentar(
    seeded, alpha_client, live_server
):
    """§15.6: la recuperación es automática.

    El permiso se concede en los ajustes del navegador, fuera de la pestaña. Al
    volver, la pantalla tiene que enterarse sola — por eso §5.1 prohíbe el botón
    de «comprobar de nuevo». Aquí se concede desde fuera y se dispara el mismo
    suceso que produce volver a la pestaña.
    """
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=False
    ) as (contexto, page):
        await page.goto("/route")
        await _esperar_puerta(page)

        await contexto.grant_permissions(["geolocation"])
        await contexto.set_geolocation(POSICION)
        # Volver a la pestaña: es una de las cuatro vías que `observarPermiso`
        # escucha, y la que de verdad usa una persona.
        await page.dispatch_event("body", "focus")
        await page.evaluate(
            "document.dispatchEvent(new Event('visibilitychange'))"
        )

        await _esperar_operativo(page)


async def test_revocar_a_mitad_no_atrapa_la_jornada(
    seeded, alpha_client, live_server
):
    """§8: con jornada abierta la pantalla sigue, para poder cerrarla.

    Es la mitad que un bloqueo hecho con prisa se lleva por delante. Si la
    puerta tapara la pantalla con una jornada abierta, el supervisor no podría
    terminar el día y el registro quedaría abierto para siempre.
    """
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=True
    ) as (contexto, page):
        await page.goto("/route")
        await _esperar_operativo(page)
        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("Working since")).to_be_visible(timeout=20_000)

        await contexto.clear_permissions()
        await page.reload()

        # La jornada sigue abierta, así que NO se ve la puerta: se ve el
        # workbench, con su salida.
        await _esperar_operativo(page)
        await expect(page.get_by_text("Working since")).to_be_visible(timeout=20_000)
        await expect(page.get_by_role("button", name="End Work")).to_be_visible()
