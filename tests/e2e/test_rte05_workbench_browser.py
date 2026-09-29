"""
El workbench de My Route, recorrido en navegador (certificación 003).

Qué cierra este archivo
-----------------------
El realineamiento no cambia ninguna regla de negocio: cambia **cuántas
pantallas hay entre el supervisor y su trabajo**. Eso no se puede demostrar con
tests de integración —el dominio se comporta igual antes y después—, así que la
evidencia es necesariamente de navegador: se cuenta lo que hay que pulsar y se
comprueba qué está y qué no está en cada estado.

Las travesías J4 a J10 y J15 —los recorridos completos por contexto, la
recuperación al recargar y el segundo dispositivo— viven en
`test_activity_execution_browser.py`, que ya las cubría y ahora las recorre por
el flujo nuevo. Aquí están las que el flujo nuevo estrena: el workbench como
estado de reposo, la jornada sin viajes, la pantalla única de pre-viaje, el
`Back`, la reutilización de las opciones en `Change Plan`, dónde está y dónde no
está `End Work`, y la guarda de `/route`.

Sin `data-testid`
-----------------
El build de producción los elimina. Todo se ancla en texto, rol e `id`.

Límite honesto: Edge de escritorio en Windows a 390x844. **No** sustituye la
validación en hardware iOS/Android real.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import func, select

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}

#: Las siete opciones aprobadas, con la etiqueta que ve el supervisor.
OPCIONES = (
    "Client Visit",
    "Recruiting",
    "Employee Visit",
    "Check Delivery",
    "Office",
    "Other",
    "Return Home",
)


async def _sembrar_valores(company_id: int) -> None:
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()


@asynccontextmanager
async def _movil(live_server, email: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


async def _contar_viajes(company_id: int) -> int:
    async with async_session_maker() as session:
        return await session.scalar(
            select(func.count()).select_from(Trip).where(Trip.company_id == company_id)
        )


async def _jornada(company_id: int, user_id: int):
    async with async_session_maker() as session:
        return await session.scalar(
            select(WorkSession).where(
                WorkSession.company_id == company_id,
                WorkSession.user_id == user_id,
            )
        )


# ── J1 ───────────────────────────────────────────────────────────────────────


async def test_start_work_lands_directly_on_the_workbench(seeded, live_server):
    """J1. `Start Work` → `What's next?`, sin escala.

    Antes había una pantalla en medio que anunciaba que la jornada estaba
    abierta y ofrecía un botón para ver las opciones. Era una pulsación que no
    añadía información (PD-04), y aquí se comprueba que ya no está: al empezar el
    día se ven **las siete opciones**, no un botón que las esconde.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()

        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )
        for opcion in OPCIONES:
            await expect(
                page.get_by_role("button", name=opcion, exact=True)
            ).to_have_count(1)

        # El botón intermedio no existe en ninguna de sus dos formas.
        await expect(
            page.get_by_role("button", name="Where to next?")
        ).to_have_count(0)

        # `End Work` está, y es secundario: no compite con empezar la siguiente
        # tarea, pero tiene que poder pulsarse (FR-02).
        salir = page.get_by_role("button", name="End Work")
        await expect(salir).to_have_count(1)
        await expect(salir).to_be_enabled()


# ── J2 ───────────────────────────────────────────────────────────────────────


async def test_a_workday_without_any_trip_ends_from_the_workbench(
    seeded, live_server,
):
    """J2. Jornada sin un solo viaje, cerrada desde el workbench.

    Es A-1 y sigue intacto: hay trabajo que no se conduce —papeleo, llamadas— y
    el sistema **no** fabrica un viaje a casa falso para poder cerrar el día
    (PD-02). Se comprueba en la base: cero viajes.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )

        await page.get_by_role("button", name="End Work").click()
        await expect(page.get_by_text("Ready to start your day?")).to_have_count(
            1, timeout=20_000
        )

    assert await _contar_viajes(seeded.alpha.id) == 0, "no se inventa un viaje"
    jornada = await _jornada(seeded.alpha.id, supervisor.id)
    assert jornada is not None and jornada.status == "ended"


# ── J3 ───────────────────────────────────────────────────────────────────────


async def test_the_pre_trip_screen_is_one_screen_and_back_returns_empty_handed(
    seeded, live_server,
):
    """J3. Una pantalla de pre-viaje, y volver atrás no deja rastro.

    La acción principal es **Start Trip**, no un `Prepare trip` que lleve a una
    segunda pantalla a repetir el destino (PD-05). Y `Back` devuelve al
    workbench sin viaje: ni `PLANNING`, ni `IN_TRANSIT`, ni historia falsa
    (FR-04). Eso se comprueba contando filas, no leyendo la pantalla.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )

        await page.get_by_role("button", name="Client Visit", exact=True).click()

        # Su dato, y la acción principal. Nada de `Prepare trip`.
        await expect(page.locator("#trip-reference")).to_have_count(1, timeout=20_000)
        await expect(
            page.get_by_role("button", name="Start Trip")
        ).to_have_count(1)
        await expect(
            page.get_by_role("button", name="Prepare trip")
        ).to_have_count(0)

        # FR-11: de aquí no se termina el día.
        await expect(page.get_by_role("button", name="End Work")).to_have_count(0)

        await page.locator("#trip-reference").fill("Acme warehouse")
        await page.get_by_role("button", name="Back").click()

        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )

    assert await _contar_viajes(seeded.alpha.id) == 0, (
        "volver atrás no puede dejar un viaje fantasma"
    )


# ── J11 ──────────────────────────────────────────────────────────────────────


async def test_change_plan_reuses_the_same_seven_choices(seeded, live_server):
    """J11. Cambiar de plan usa las mismas siete opciones y el mismo viaje.

    No una taxonomía paralela (PD-07): son el mismo componente, así que no puede
    divergir. Y el viaje es el mismo —se cuenta— con su historia preservada: la
    pantalla dice de dónde venía.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()
        await page.get_by_role("button", name="Client Visit", exact=True).click()
        await page.get_by_role("button", name="Start Trip").click()
        await expect(
            page.get_by_role("button", name="Change Plan")
        ).to_have_count(1, timeout=20_000)

        antes = await _contar_viajes(seeded.alpha.id)

        await page.get_by_role("button", name="Change Plan").click()
        # Las siete, otra vez, con la misma presentación.
        for opcion in OPCIONES:
            await expect(
                page.get_by_role("button", name=opcion, exact=True)
            ).to_have_count(1, timeout=20_000)

        await page.get_by_role("button", name="Employee Visit", exact=True).click()
        await page.locator("#trip-standard-value").click()
        await page.get_by_role("option", name="Attendance Issue", exact=True).click()
        await page.get_by_role("button", name="Update plan").click()

        # Vuelve a On Route, con el original a la vista.
        await expect(
            page.get_by_role("button", name="Change Plan")
        ).to_have_count(1, timeout=20_000)
        await expect(page.get_by_text("Originally:")).to_have_count(1)

    assert await _contar_viajes(seeded.alpha.id) == antes, (
        "cambiar de plan no crea un viaje de reemplazo"
    )
    async with async_session_maker() as session:
        viaje = await session.scalar(
            select(Trip).where(Trip.company_id == seeded.alpha.id)
        )
    assert viaje.status == "in_transit", "ni cierra el viaje"
    assert viaje.current_purpose == "employee_visit"
    assert viaje.original_purpose == "client_visit", "la historia se preserva"


# ── J12 ──────────────────────────────────────────────────────────────────────


async def test_end_work_is_offered_only_from_the_workbench(seeded, live_server):
    """J12. Un solo sitio para terminar el día, recorrido estado por estado.

    Workbench sí. Pre-viaje no, en ruta no, llegada sin resolver no, parada en
    marcha no (PD-03, FR-11, FR-12). Y no hay atajo: el servidor mantiene sus
    guardas, que es lo que de verdad lo impide — esto sólo comprueba que la
    interfaz no ofrece lo que va a ser rechazado.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    def salir(pagina):
        return pagina.get_by_role("button", name="End Work")

    async with _movil(live_server, supervisor.email) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )
        await expect(salir(page)).to_have_count(1)

        # Pre-viaje: no.
        await page.get_by_role("button", name="Client Visit", exact=True).click()
        await expect(page.locator("#trip-reference")).to_have_count(1, timeout=20_000)
        await expect(salir(page)).to_have_count(0)

        # En ruta: no.
        await page.get_by_role("button", name="Start Trip").click()
        await expect(
            page.get_by_role("button", name="Change Plan")
        ).to_have_count(1, timeout=20_000)
        await expect(salir(page)).to_have_count(0)

        # Llegado y sin resolver: no.
        await page.get_by_role("button", name="Arrived", exact=True).click()
        await expect(page.get_by_text("What are you doing here?")).to_have_count(
            1, timeout=20_000
        )
        await expect(salir(page)).to_have_count(0)

        # Parada en marcha: no.
        await page.get_by_text("Service Review", exact=True).click()
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        await expect(salir(page)).to_have_count(0)

        # Resuelta la parada, se vuelve al workbench y allí sí.
        await page.get_by_role("button", name="Complete Activity", exact=True).click()
        await page.locator("#activity-outcome").click()
        await page.get_by_role("option", name="Completed", exact=True).click()
        await page.get_by_role("button", name="Complete Activity", exact=True).click()

        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )
        await expect(salir(page)).to_have_count(1)

    jornada = await _jornada(seeded.alpha.id, supervisor.id)
    assert jornada.status == "active", "nada cerró la jornada por detrás"


# ── J13 ──────────────────────────────────────────────────────────────────────


async def test_the_administrator_reaches_the_same_workbench(seeded, live_server):
    """J13. El Administrador entra por el menú y llega al mismo workbench.

    Sin escribir la URL. Y lo que ve es el mismo componente operativo: las
    mismas siete opciones y el mismo primer paso.
    """
    administrador = seeded.alpha.users["route_admin"]

    async with _movil(live_server, administrador.email) as (_c, page):
        await page.goto("/admin")
        await page.get_by_role("link", name="My Route").first.click()

        await page.get_by_role("button", name="Start Work").click()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=20_000
        )
        for opcion in OPCIONES:
            await expect(
                page.get_by_role("button", name=opcion, exact=True)
            ).to_have_count(1)


# ── J14 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "quien,permitido",
    [
        # Los dos roles de producto de CER Route.
        ("supervisor", True),
        ("route_admin", True),
        # `owner` tiene `ALL_CAPABILITIES` y `admin` todas menos `roles.delete`,
        # así que **sí** poseen la capacidad de ejecución por el modelo de roles
        # certificado. La guarda no puede negarles lo que tienen concedido, y el
        # modelo de roles está fuera de este alcance: FR-13 lo dice con esa
        # condición —"Core ... **without** Route execute: denied"—. Ver el
        # hallazgo del reporte 003.
        ("owner", True),
        ("admin", True),
        # Éstos no la tienen: 6 y 3 capacidades, ninguna operativa de ruta.
        ("manager", False),
        ("viewer", False),
    ],
)
async def test_the_route_shell_requires_the_execute_capability(
    seeded, live_server, quien, permitido,
):
    """J14. `/route` exige `route.worksession.execute`.

    Se comprueba por **URL directa**, que es el único camino que queda cuando el
    menú ya no ofrece el enlace: ocultar no es controlar, y la puerta tiene que
    estar en el servidor.

    Quién entra lo decide la capacidad, no el nombre del rol. No se añadió
    ninguna capacidad nueva: se exige la que ya protegía los endpoints.
    """
    usuario = seeded.alpha.users[quien]

    async with _movil(live_server, usuario.email) as (_c, page):
        respuesta = await page.goto("/route")
        assert respuesta is not None
        if permitido:
            assert respuesta.status == 200, f"{quien} debería entrar"
            await expect(
                page.get_by_role("button", name="Start Work")
            ).to_have_count(1, timeout=20_000)
        else:
            assert respuesta.status == 403, (
                f"{quien} no ejecuta ruta y no debería entrar: {respuesta.status}"
            )


async def test_platform_identity_alone_does_not_open_the_route_shell(
    seeded, live_server,
):
    """J14, la mitad que separa plataforma de operación (FR-13).

    Un superusuario de plataforma administra el despliegue; no ejecuta la
    jornada de nadie. La guarda del núcleo —`require_page_permissions`— le deja
    pasar a propósito, porque para las pantallas de administración eso es lo
    correcto. El shell operativo usa una guarda propia y más estricta, y por eso
    aquí la respuesta es 403 y no 200.
    """
    plataforma = seeded.platform_admin

    async with _movil(live_server, plataforma.email) as (_c, page):
        respuesta = await page.goto("/route")
        assert respuesta is not None and respuesta.status == 403, (
            f"la identidad de plataforma no ejecuta ruta: {respuesta}"
        )
