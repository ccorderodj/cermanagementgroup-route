"""
Validación en navegador del ciclo de vida del Admin (cierre RTE02-A01, 005).

Por qué existe este archivo
---------------------------
El addendum RTE02-A01 es, sobre todo, un cambio de interfaz: separar borrar de
desactivar y ofrecer cada acción sólo cuando tiene sentido. La entrega 001 lo
validó con typecheck, lint, build y 61 tests de integración — todo ello contra
la API, sin navegador. Ninguna de esas comprobaciones puede decir si el menú
contextual aparece, si el diálogo de confirmación existe, o si la fila
desaparece de la tabla.

Este archivo conduce el Edge instalado en el sistema contra un `uvicorn` real y
comprueba el **estado resultante**, no que se haya pulsado un botón: después de
cada acción se lee la tabla, y cuando la propiedad es del servidor (que la
identidad del núcleo sobreviva, que la pertenencia quede con lápida) se lee
PostgreSQL directamente.

Cuatro recorridos, uno por superficie, tal y como los enumera §"Tests / Evidence
Required" del cierre.

Límite honesto: esto es Edge de escritorio en Windows. No sustituye una
validación en hardware móvil real, que sigue siendo materia de RTE03 y no de
este addendum.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from sqlalchemy import select

from app.database import async_session_maker
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.models import Users
from app.routers_api.vehicles.models import SupervisorProfile
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 1280, "height": 900}


async def _abrir(navegador, live_server, email: str, ruta: str):
    """Contexto nuevo, sesión iniciada y página cargada."""
    contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
    page = await contexto.new_page()
    await abrir_sesion(page, email)
    await page.goto(ruta)
    return contexto, page


async def _esperar_filas(page, texto: str, cantidad: int) -> None:
    """Espera a que la tabla tenga exactamente esas filas.

    No se usa `wait_for_timeout`: los paneles desmontan la tabla mientras
    recargan, asi que una espera fija puede leer 0 filas en mitad de una
    recarga en vuelo y dar por bueno —o por malo— un estado que no es el final.
    `expect` reintenta hasta que el estado se cumple o vence el plazo.
    """
    await expect(page.locator("tr", has_text=texto)).to_have_count(
        cantidad, timeout=20_000
    )


async def _abrir_menu_de_fila(page, texto_fila: str):
    """Abre el menú contextual (`...`) de la fila que contiene ese texto."""
    fila = page.locator("tr", has_text=texto_fila).first
    await fila.get_by_role("button", name="Open menu").click()


# ── 1. Vehículos ────────────────────────────────────────────────────────────


async def test_vehicle_lifecycle_in_the_browser(seeded, live_server):
    """Desactivar, ver inactivos, reactivar, borrar, y borrado bloqueado."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador,
                live_server,
                seeded.alpha.users["route_admin"].email,
                "/admin/route/vehicles",
            )

            # Alta desde la propia pantalla: sin Postman ni API directa. Desde
            # A02-FC3 el formulario no está permanentemente arriba: lo abre
            # `Add Vehicle` en un diálogo.
            await page.get_by_role("button", name="Add Vehicle").click()
            await page.wait_for_selector("#vehicle-unit", timeout=20_000)
            await page.get_by_label("Unit").fill("V-UX1")
            await page.get_by_label("Make").fill("Toyota")
            await page.get_by_label("Model").fill("RAV4")
            await page.get_by_label("Operational MPG").fill("27.00")
            await page.get_by_role("button", name="Add vehicle").click()
            await page.wait_for_selector("text=V-UX1", timeout=20_000)

            # ── Fila activa: ofrece Deactivate, no Reactivate ───────────────
            await _abrir_menu_de_fila(page, "V-UX1")
            assert await page.get_by_role("menuitem", name="Deactivate").is_visible()
            assert await page.get_by_role("menuitem", name="Delete").is_visible()
            assert await page.get_by_role(
                "menuitem", name="Reactivate"
            ).count() == 0, "una fila activa no debe ofrecer Reactivate"

            await page.get_by_role("menuitem", name="Deactivate").click()
            # Sin "ver inactivos", el desactivado sale de la tabla.
            await _esperar_filas(page, "V-UX1", 0)

            # ── Ver inactivos lo recupera ───────────────────────────────────
            await page.get_by_label("Show inactive vehicles").check()
            await _esperar_filas(page, "V-UX1", 1)
            await expect(
                page.locator("tr", has_text="V-UX1").get_by_text("Inactive", exact=True)
            ).to_be_visible(timeout=20_000)

            # ── Fila inactiva: ofrece Reactivate, no Deactivate ─────────────
            await _abrir_menu_de_fila(page, "V-UX1")
            assert await page.get_by_role("menuitem", name="Reactivate").is_visible()
            assert await page.get_by_role("menuitem", name="Delete").is_visible()
            assert await page.get_by_role(
                "menuitem", name="Deactivate"
            ).count() == 0, "una fila inactiva no debe ofrecer Deactivate"

            await page.get_by_role("menuitem", name="Reactivate").click()
            # `exact=True` importa: "Inactive" contiene "Active", asi que una
            # coincidencia por subcadena daria por buena la fila desactivada.
            await expect(
                page.locator("tr", has_text="V-UX1").get_by_text("Active", exact=True)
            ).to_be_visible(timeout=20_000)

            # ── Borrar exige confirmación ───────────────────────────────────
            await _abrir_menu_de_fila(page, "V-UX1")
            await page.get_by_role("menuitem", name="Delete").click()
            await page.wait_for_selector("text=Delete V-UX1?", timeout=10_000)

            # Cancelar no borra: la confirmación es real, no decorativa.
            await page.get_by_role("button", name="Cancel").click()
            await expect(page.locator("text=Delete V-UX1?")).to_have_count(
                0, timeout=10_000
            )
            await _esperar_filas(page, "V-UX1", 1)

            await _abrir_menu_de_fila(page, "V-UX1")
            await page.get_by_role("menuitem", name="Delete").click()
            await page.get_by_role("button", name="Delete", exact=True).last.click()

            # Con "ver inactivos" todavia marcado sigue sin aparecer: ahi esta
            # la diferencia entre borrar y desactivar, vista en pantalla.
            await _esperar_filas(page, "V-UX1", 0)
            assert await page.get_by_label(
                "Show inactive vehicles"
            ).is_checked(), "la comprobacion solo vale si los inactivos se muestran"

            await contexto.close()
        finally:
            await navegador.close()


async def test_a_vehicle_with_a_current_assignment_cannot_be_deleted_in_the_browser(
    seeded, live_server, alpha_client,
):
    """El borrado bloqueado explica el motivo en la propia pantalla."""
    from playwright.async_api import async_playwright

    # Preparación por API: lo que se valida es el bloqueo en la interfaz, no el
    # alta del vehículo, que ya se validó en el recorrido anterior.
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
                "make": "Ford", "model": "Transit", "year": 2023, "unit": "V-BLOCK",
                "fuel_grade": "regular", "operational_mpg": "22.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador,
                live_server,
                seeded.alpha.users["route_admin"].email,
                "/admin/route/vehicles",
            )
            await page.wait_for_selector("text=V-BLOCK", timeout=20_000)

            await _abrir_menu_de_fila(page, "V-BLOCK")
            await page.get_by_role("menuitem", name="Delete").click()
            await page.get_by_role("button", name="Delete", exact=True).last.click()

            # El servidor responde 409 y la pantalla enseña su motivo.
            await page.wait_for_selector("text=Action unavailable", timeout=20_000)
            texto = await page.locator("text=end the current vehicle assignment").count()
            assert texto >= 1, "el motivo de negocio tiene que ser legible"

            # `.first` porque el propio Dialog aporta su aspa, tambien
            # llamada "Close".
            await page.get_by_role("button", name="Close").first.click()
            await _esperar_filas(page, "V-BLOCK", 1)

            await contexto.close()
        finally:
            await navegador.close()


# ── 2. Designaciones de supervisor ──────────────────────────────────────────


async def test_supervisor_designation_lifecycle_in_the_browser(
    seeded, live_server, alpha_client,
):
    """Retirar, restaurar, borrar — y el usuario del núcleo sobrevive."""
    from playwright.async_api import async_playwright

    usuario_id = seeded.alpha.users["supervisor"].id
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post("/api/supervisors", json={"user_id": usuario_id})
    nombre = seeded.alpha.users["supervisor"].email

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador,
                live_server,
                seeded.alpha.users["route_admin"].email,
                "/admin/route/supervisors",
            )
            await page.wait_for_selector(f"text={nombre}", timeout=20_000)

            # ── Activa: retirar designación ─────────────────────────────────
            await _abrir_menu_de_fila(page, nombre)
            await page.get_by_role("menuitem", name="Remove designation").click()
            await expect(
                page.locator("tr", has_text=nombre).get_by_text("Removed", exact=True)
            ).to_be_visible(timeout=20_000)

            # ── Inactiva: ofrece restaurar, no retirar ──────────────────────
            await _abrir_menu_de_fila(page, nombre)
            assert await page.get_by_role(
                "menuitem", name="Restore designation"
            ).is_visible()
            assert await page.get_by_role(
                "menuitem", name="Remove designation"
            ).count() == 0

            await page.get_by_role("menuitem", name="Restore designation").click()
            await expect(
                page.locator("tr", has_text=nombre).get_by_text("Removed", exact=True)
            ).to_have_count(0, timeout=20_000)

            # ── Borrar, con confirmación ────────────────────────────────────
            await _abrir_menu_de_fila(page, nombre)
            await page.get_by_role("menuitem", name="Delete designation").click()
            await page.wait_for_selector(
                "text=Delete this Route designation?", timeout=10_000
            )
            await page.get_by_role("button", name="Delete", exact=True).last.click()
            await expect(
                page.locator("text=Delete this Route designation?")
            ).to_have_count(0, timeout=20_000)
            # La designacion desaparece: la persona vuelve a figurar como
            # candidata, sin designacion.
            await expect(
                page.locator("tr", has_text=nombre).get_by_role(
                    "button", name="Open menu"
                )
            ).to_have_count(0, timeout=20_000)

            await contexto.close()
        finally:
            await navegador.close()

    # El estado resultante se comprueba en la base, que es donde vive la
    # propiedad que importa: la designación con lápida y la persona intacta.
    async with async_session_maker() as session:
        perfil = await session.scalar(
            select(SupervisorProfile).where(
                SupervisorProfile.user_id == usuario_id,
                SupervisorProfile.company_id == seeded.alpha.id,
            )
        )
        usuario = await session.scalar(select(Users).where(Users.id == usuario_id))
        pertenencia = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == usuario_id,
                UserCompany.company_id == seeded.alpha.id,
            )
        )

    assert perfil is not None and perfil.deleted_at is not None, (
        "la designación queda borrada, con su fila intacta para la historia"
    )
    assert usuario is not None and usuario.is_active is True, (
        "el usuario del núcleo sobrevive al borrado de la designación"
    )
    assert pertenencia is not None and pertenencia.deleted_at is None, (
        "y su pertenencia a la compañía tampoco se toca"
    )


# ── 3. Valores de lista estandarizada ───────────────────────────────────────


async def test_standard_value_lifecycle_in_the_browser(seeded, live_server):
    """Editar, desactivar, ver inactivos, reactivar, borrar."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador,
                live_server,
                seeded.alpha.users["route_admin"].email,
                "/admin/route/standard-values",
            )
            # Desde A02-FC4 el alta es un diálogo que ya sabe a qué lista añade.
            await page.get_by_role("button", name="Add Value").click()
            await page.wait_for_selector("#new-value", timeout=20_000)

            await page.get_by_placeholder("New value").fill("Browser Check")
            await page.get_by_role("button", name="Add", exact=True).click()
            await page.wait_for_selector("text=Browser Check", timeout=20_000)

            # ── Editar ──────────────────────────────────────────────────────
            await _abrir_menu_de_fila(page, "Browser Check")
            await page.get_by_role("menuitem", name="Edit").click()
            campo = page.get_by_label("Rename Browser Check")
            await campo.fill("Browser Check Renamed")
            await page.get_by_role("button", name="Save", exact=True).click()
            await page.wait_for_selector("text=Browser Check Renamed", timeout=20_000)

            # ── Desactivar: sale de la vista normal ─────────────────────────
            await _abrir_menu_de_fila(page, "Browser Check Renamed")
            await page.get_by_role("menuitem", name="Deactivate").click()
            await _esperar_filas(page, "Browser Check Renamed", 0)

            # ── Ver inactivos lo recupera, y ofrece Reactivate ──────────────
            await page.get_by_label("Show inactive values").check()
            await _esperar_filas(page, "Browser Check Renamed", 1)

            await _abrir_menu_de_fila(page, "Browser Check Renamed")
            assert await page.get_by_role("menuitem", name="Reactivate").is_visible()
            assert await page.get_by_role("menuitem", name="Deactivate").count() == 0
            await page.get_by_role("menuitem", name="Reactivate").click()
            # Se espera al estado final antes de seguir: la fila en memoria
            # lleva su `version`, y actuar sobre una recarga a medias mandaria
            # una version obsoleta, que el servidor rechaza con 409.
            await expect(
                page.locator("tr", has_text="Browser Check Renamed").get_by_text(
                    "Active", exact=True
                )
            ).to_be_visible(timeout=20_000)

            # ── Borrar, con confirmación ────────────────────────────────────
            await _abrir_menu_de_fila(page, "Browser Check Renamed")
            await page.get_by_role("menuitem", name="Delete").click()
            await page.wait_for_selector(
                "text=Delete Browser Check Renamed?", timeout=10_000
            )
            await page.get_by_role("button", name="Delete", exact=True).last.click()

            # Con "ver inactivos" todavia marcado, sigue sin aparecer: es la
            # diferencia entre borrar y desactivar, vista en pantalla.
            await _esperar_filas(page, "Browser Check Renamed", 0)
            assert await page.get_by_label("Show inactive values").is_checked()

            # El selector operativo tampoco lo devuelve. Se pregunta al servidor
            # desde el propio navegador, con la sesión del administrador.
            devueltos = await page.evaluate(
                """async () => {
                    const r = await fetch('/api/standard-values/outcomes');
                    const filas = await r.json();
                    return filas.map((f) => f.label);
                }"""
            )
            assert "Browser Check Renamed" not in devueltos

            await contexto.close()
        finally:
            await navegador.close()


# ── 4. Usuarios: el ciclo de vida a nivel de tenant ─────────────────────────


async def test_user_delete_is_reachable_and_complete_from_the_admin_ui(
    seeded, live_server, alpha_client,
):
    """Un Route Admin retira a alguien del tenant sin salir de la pantalla."""
    from playwright.async_api import async_playwright

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (
        await alpha_client.post(
            "/api/users",
            json={
                "username": "browserremove",
                "email": "browserremove@alpha.example.com",
                "first_name": "Browser",
                "last_name": "Remove",
                "password": "Str0ng!Passw0rd",
                # Un rol de CER Route: desde A02 el Administrador sólo concede
                # los dos de producto, y aquí hace falta "un usuario", no uno
                # del núcleo.
                "role_id": seeded.alpha.roles["supervisor"],
            },
        )
    ).json()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador,
                live_server,
                seeded.alpha.users["route_admin"].email,
                "/admin/route/users",
            )
            await page.wait_for_selector("text=browserremove", timeout=20_000)

            # ── La acción existe y exige confirmación ───────────────────────
            await _abrir_menu_de_fila(page, "browserremove")
            await page.get_by_role("menuitem", name="Remove from company").click()
            await page.wait_for_selector("text=Remove browserremove", timeout=10_000)

            # Cancelar no retira a nadie.
            await page.get_by_role("button", name="Cancel").click()
            await expect(page.locator("text=Remove browserremove")).to_have_count(
                0, timeout=10_000
            )
            await _esperar_filas(page, "browserremove", 1)

            await _abrir_menu_de_fila(page, "browserremove")
            await page.get_by_role("menuitem", name="Remove from company").click()
            await page.get_by_role("button", name="Remove", exact=True).last.click()
            await _esperar_filas(page, "browserremove", 0)

            await contexto.close()
        finally:
            await navegador.close()

    async with async_session_maker() as session:
        usuario = await session.scalar(select(Users).where(Users.id == creado["id"]))
        pertenencia = await session.scalar(
            select(UserCompany).where(
                UserCompany.user_id == creado["id"],
                UserCompany.company_id == seeded.alpha.id,
            )
        )

    assert pertenencia is not None and pertenencia.deleted_at is not None, (
        "la pertenencia queda retirada"
    )
    assert usuario is not None and usuario.is_active is True, (
        "la identidad de plataforma no se destruye: puede estar en otros tenants"
    )


async def test_a_role_without_the_capability_never_sees_user_delete(
    seeded, live_server,
):
    """`manager` edita y suspende, pero no ve la acción de retirar.

    Ocultarla es experiencia de usuario; el control está en el servidor y ya lo
    prueba `test_removing_a_user_requires_the_delete_capability`. Lo que este
    test añade es que no se le ofrece una acción que iba a fallar.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador,
                live_server,
                seeded.alpha.users["manager"].email,
                "/admin/security/users/list",
            )
            await page.wait_for_selector("table", timeout=20_000)

            objetivo = seeded.alpha.users["viewer"].username
            await _abrir_menu_de_fila(page, objetivo)

            assert await page.get_by_role("menuitem", name="Edit").is_visible(), (
                "manager sí puede editar: la comparación es contra Delete"
            )
            assert await page.get_by_role(
                "menuitem", name="Remove from company"
            ).count() == 0, "sin users.delete no se ofrece retirar"

            await contexto.close()
        finally:
            await navegador.close()
