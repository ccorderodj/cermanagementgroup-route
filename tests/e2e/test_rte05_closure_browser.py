"""
Las travesías del cierre de RTE05 (instrucciones 002).

Dos deltas, y por qué hay que recorrerlos y no deducirlos
---------------------------------------------------------
**Delta 1** relaja `Received By` al marcharse de una entrega. El backend ya lo
tiene probado; lo que sólo se ve en el navegador es que el botón de confirmar
**deje de bloquear** — una validación de servidor correcta con un botón
deshabilitado es una función que el supervisor no puede usar.

**Delta 2** es navegación. La instrucción lo dice expresamente: *"A direct URL
is not sufficient evidence"*. Así que estas travesías **no** escriben `/route`:
entran, miran el menú y pulsan, que es lo que hace una persona. El defecto que
cierran era exactamente eso — `My Route` existía y funcionaba, pero no había
forma de llegar sin conocer la URL, y el Supervisor aterrizaba en una página sin
una sola tarjeta.

Sin `data-testid`
-----------------
El build de producción los elimina. Todo se ancla en texto, rol e `id`.

Límite honesto: Edge de escritorio en Windows a 390x844 y a 1280x900. **No**
sustituye la validación en hardware iOS/Android real.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_activity_execution_browser import (
    _bloque,
    _estado_del_viaje,
    _hasta_la_llegada,
)


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}
#: La navegación lateral se valida al ancho donde el menú está desplegado: el
#: shell de escritorio es donde un Administrador administra.
ESCRITORIO = {"width": 1280, "height": 900}

#: Los cinco destinos de configuración de CER Route.
CONFIGURACION = ("Users", "Supervisors", "Vehicles", "Standardized Lists",
                 "Odometer Exceptions")


async def _sembrar_valores(company_id: int) -> None:
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()


@asynccontextmanager
async def _navegador(live_server, email: str, viewport: dict):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=viewport
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


# ── Delta 2 · AC-04 ──────────────────────────────────────────────────────────


async def test_the_administrator_reaches_my_route_from_normal_navigation(
    seeded, live_server,
):
    """AC-04. Sin escribir la URL, que es la condición de la instrucción.

    Se entra, se aterriza en el inicio autenticado, se pulsa `My Route` y tiene
    que abrirse la pantalla operativa. Y la configuración tiene que seguir ahí:
    el Administrador no pierde nada por ganar acceso a su propia ruta.
    """
    administrador = seeded.alpha.users["route_admin"]

    async with _navegador(live_server, administrador.email, ESCRITORIO) as (_c, page):
        await page.goto("/admin")

        # El inicio autenticado saca sus tarjetas de la misma lista que el menú,
        # así que `My Route` aparece en los dos sitios o en ninguno.
        enlace = page.get_by_role("link", name="My Route").first
        await expect(enlace).to_have_count(1, timeout=20_000)

        await enlace.click()
        await expect(page.get_by_text("Ready to start your day?")).to_have_count(
            1, timeout=20_000
        )
        assert page.url.endswith("/route"), page.url

        # AC-04: la configuración sigue accesible desde la navegación normal.
        await page.goto("/admin")
        for destino in CONFIGURACION:
            await expect(
                page.get_by_role("link", name=destino).first
            ).to_have_count(1, timeout=20_000)


# ── Delta 2 · AC-05 ──────────────────────────────────────────────────────────


async def test_the_supervisor_reaches_my_route_and_sees_no_configuration(
    seeded, live_server,
):
    """AC-05. El Supervisor llega a lo suyo y no ve nada más.

    Antes del cierre 002 esta pantalla era inalcanzable para él: los cinco
    destinos del grupo exigían capacidades de administración, el grupo entero
    desaparecía por quedarse vacío, y el inicio autenticado —que se construye de
    esa misma lista— no tenía una sola tarjeta.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _navegador(live_server, supervisor.email, ESCRITORIO) as (_c, page):
        await page.goto("/admin")

        enlace = page.get_by_role("link", name="My Route").first
        await expect(enlace).to_have_count(1, timeout=20_000)

        # Nada de administración de CER Route, ni en el menú ni en el inicio.
        for destino in CONFIGURACION:
            await expect(
                page.get_by_role("link", name=destino)
            ).to_have_count(0)

        await enlace.click()
        await expect(page.get_by_text("Ready to start your day?")).to_have_count(
            1, timeout=20_000
        )

        # Y el servidor sigue siendo la puerta: ocultar no es controlar.
        respuesta = await page.goto("/admin/route/standard-values")
        assert respuesta is not None and respuesta.status == 403, (
            f"la URL directa tiene que seguir denegada: {respuesta}"
        )


# ── Delta 2 · AC-06 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("quien", ["route_admin", "supervisor"], ids=["admin", "sup"])
async def test_both_roles_open_the_same_my_route_experience(
    seeded, live_server, quien,
):
    """AC-06. La misma pantalla, no una por rol.

    Se comprueba en el ancho real del teléfono, que es donde se usa. Lo que
    distingue a los dos roles es lo que pueden administrar, no la experiencia
    operativa; bifurcar el móvil por rol duplicaría la mitad de RTE03-RTE05.
    """
    usuario = seeded.alpha.users[quien]

    async with _navegador(live_server, usuario.email, MOVIL) as (_c, page):
        await page.goto("/admin")
        await page.get_by_role("link", name="My Route").first.click()

        # El mismo componente: el mismo shell, el mismo título, el mismo primer
        # paso de la jornada.
        await expect(page.get_by_text("My Route").first).to_have_count(
            1, timeout=20_000
        )
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=20_000)


# ── Delta 1 · AC-01 ──────────────────────────────────────────────────────────


async def test_completing_a_check_delivery_still_demands_a_receiver(
    seeded, live_server,
):
    """AC-01 en pantalla: completar sin receptor no se puede confirmar.

    Delta 1 relaja el camino de marcharse; este no. Se comprueba que el botón
    está **deshabilitado** con el resultado ya elegido, porque un botón
    habilitado que después recibe un 422 es peor que uno que no se ofrece.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _navegador(live_server, supervisor.email, MOVIL) as (_c, page):
        await _hasta_la_llegada(
            page, contexto_ui="Check Delivery", valor="Payroll Check"
        )
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        await page.get_by_role("button", name="Complete Activity", exact=True).click()
        await expect(page.get_by_text("Received by")).to_have_count(1, timeout=20_000)

        # AC-03, la mitad de completar: sin resultado tampoco se confirma. Los
        # dos datos se comprueban por separado porque son dos reglas, y una
        # podría relajarse sin la otra.
        await expect(
            page.get_by_role("button", name="Complete Activity", exact=True)
        ).to_be_disabled()
        # Y al completar el campo del receptor va **sin** marca de opcional:
        # sólo la nota la lleva aquí.
        await expect(page.get_by_text("(optional)")).to_have_count(1)

        await page.locator("#activity-outcome").click()
        await page.get_by_role("option", name="Completed", exact=True).click()

        await expect(
            page.get_by_role("button", name="Complete Activity", exact=True)
        ).to_be_disabled()

        await page.locator("#activity-received-by").click()
        await page.get_by_role("option", name="Employee", exact=True).click()
        await page.get_by_role("button", name="Complete Activity", exact=True).click()

        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.received_by_label == "Employee"
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"


# ── Delta 1 · AC-02 ──────────────────────────────────────────────────────────


async def test_leaving_a_check_delivery_confirms_without_a_receiver(
    seeded, live_server,
):
    """AC-02 en pantalla, y es el corazón del cierre 002.

    Nadie recibió la entrega. El supervisor elige el resultado y se marcha, y la
    pantalla **le deja**: el campo sigue ahí por si hubo alguien, marcado como
    opcional, y no bloquea la confirmación. Obligarle a rellenarlo sería pedirle
    que se invente un receptor para poder cerrar la parada.

    El resultado, en cambio, sigue siendo obligatorio: se comprueba que sin él
    tampoco se confirma.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _navegador(live_server, supervisor.email, MOVIL) as (_c, page):
        await _hasta_la_llegada(
            page, contexto_ui="Check Delivery", valor="Payroll Check"
        )
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        await page.get_by_role("button", name="Leave", exact=True).click()
        await expect(page.get_by_text("How did it go?")).to_have_count(1, timeout=20_000)

        # El campo está, y dice que es opcional.
        await expect(page.get_by_text("Received by")).to_have_count(1)
        await expect(page.get_by_text("(optional)")).to_have_count(2)

        # AC-03: sin resultado no se confirma, ni marchándose.
        await expect(
            page.get_by_role("button", name="Leave", exact=True)
        ).to_be_disabled()

        await page.locator("#activity-outcome").click()
        await page.get_by_role("option", name="No Contact", exact=True).click()

        # Y con el resultado puesto, el receptor no bloquea.
        await expect(
            page.get_by_role("button", name="Leave", exact=True)
        ).to_be_enabled()
        await page.get_by_role("button", name="Leave", exact=True).click()

        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.status == "left"
    assert bloque.outcome_label == "No Contact"
    assert bloque.received_by_standard_value_id is None, "no se fabrica un receptor"
    assert bloque.received_by_label is None
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"
