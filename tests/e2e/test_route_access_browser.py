"""
El modelo de acceso de A02, en un navegador real (A02-C5).

Qué añade sobre los tests de API
--------------------------------
Los de integración ya demuestran que el servidor rechaza un rol del núcleo. Aquí
se comprueba lo que sólo la pantalla puede decir: que el selector **ofrece
exactamente dos opciones**, con sus etiquetas de producto y sin el vocabulario
técnico; que los dos roles entran a la misma experiencia móvil; y que el
Supervisor no ve navegación de administración.

Y una cosa que conviene no confundir: ocultar `Owner` del desplegable no es la
protección. La protección está en `ensure_assignable_role` y se prueba contra la
API. Esto prueba que la pantalla no ofrece algo que el servidor rechazaría, que
es un problema distinto —de experiencia— y también real.

Sin `data-testid`
-----------------
El build de producción los elimina
(`configwebpack/build/loaders/buildBabelLoader.ts`), y estos tests corren contra
el bundle de producción. Se anclan en texto, rol e `id`, que es además el ancla
honesta: un test que sigue pasando cuando la etiqueta que lee una persona cambió
de significado no está validando la pantalla.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from app.core.rbac.catalog import ROUTE_PRODUCT_ROLE_LABELS
from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from tests.integration.conftest import TEST_PASSWORD, TenantClient
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}
ESCRITORIO = {"width": 1280, "height": 900}

#: Los nombres que **no** pueden aparecer como opción de rol en CER Route.
ROLES_DEL_NUCLEO = ("Owner", "Admin", "Manager", "Viewer")


async def test_the_route_user_form_offers_exactly_the_two_product_roles(
    seeded, live_server,
):
    """FR-01 y caso límite 20, en pantalla.

    Se abre el formulario de alta desde la pantalla de usuarios de CER Route y se
    despliega el selector de rol. Tiene que ofrecer Administrador y Supervisor, y
    ninguno de los cuatro roles del núcleo.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            await page.goto("/admin/route/users")
            # El `h1` de `PageHeader`: "heading" a secas también encuentra el
            # grupo del menú lateral, que se llama igual.
            await expect(
                page.locator("h1", has_text="Users")
            ).to_have_count(1, timeout=20_000)

            # Abrir el formulario de alta.
            await page.get_by_role("button", name="Create User").click()
            await expect(
                page.get_by_text("Role in this company")
            ).to_have_count(1, timeout=20_000)

            # El selector de rol es el que está junto a su etiqueta; los otros
            # `combobox` del formulario son género y estado.
            selector = page.locator("[role='combobox']").last
            await selector.click()

            opciones = page.get_by_role("option")
            await expect(opciones).to_have_count(2, timeout=20_000)

            textos = sorted(await opciones.all_inner_texts())
            assert textos == sorted(ROUTE_PRODUCT_ROLE_LABELS.values()), (
                f"el selector debe ofrecer exactamente los dos roles: {textos}"
            )

            # Y ni rastro del núcleo ni del código técnico.
            for nombre in ROLES_DEL_NUCLEO:
                await expect(
                    page.get_by_role("option", name=nombre, exact=True)
                ).to_have_count(0)
            assert "route_admin" not in " ".join(textos), (
                "el código técnico no se muestra"
            )
        finally:
            await navegador.close()


@pytest.mark.parametrize("rol", ["route_admin", "supervisor"])
async def test_both_product_roles_enter_the_mobile_experience_and_start_work(
    seeded, live_server, rol,
):
    """FR-04 y casos límite 13-14.

    La misma pantalla para los dos, sin bifurcar el flujo operativo. El
    Administrador no podía entrar antes de A02.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users[rol].email)

            await page.goto("/route")
            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=20_000)

            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("Working since")).to_have_count(
                1, timeout=20_000
            )

            # Y la jornada existe de verdad, no sólo en la pantalla.
            from sqlalchemy import text

            async with async_session_maker() as session:
                abiertas = await session.scalar(
                    text(
                        "SELECT count(*) FROM work_session "
                        "WHERE company_id = :c AND user_id = :u AND status = 'active'"
                    ),
                    {"c": seeded.alpha.id, "u": seeded.alpha.users[rol].id},
                )
            assert abiertas == 1
        finally:
            await navegador.close()


async def test_the_supervisor_sees_no_route_administration(seeded, live_server):
    """FR-03: comparten la experiencia móvil, no la administración.

    Se comprueba en los dos planos, porque ocultar un enlace nunca ha protegido
    nada: el menú no lo ofrece **y** el servidor no sirve la página.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/route")
            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=20_000)

            # Sin cromo de administración dentro de la experiencia operativa.
            for enlace in ("Users", "Vehicles", "Standardized Lists", "Odometer Exceptions"):
                await expect(page.get_by_role("link", name=enlace)).to_have_count(0)

            # Y el servidor tampoco sirve esas páginas.
            for ruta in (
                "/admin/route/users",
                "/admin/route/vehicles",
                "/admin/route/standard-values",
                "/admin/route/odometer-exceptions",
            ):
                respuesta = await page.goto(ruta)
                assert respuesta.status in (401, 403, 404), (
                    f"{ruta} se sirvió a un supervisor: {respuesta.status}"
                )
        finally:
            await navegador.close()


async def test_the_administrator_reaches_both_admin_and_mobile(seeded, live_server):
    """FR-02: las dos experiencias, con el mismo usuario y la misma sesión."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            # Administración.
            for ruta, titulo in (
                ("/admin/route/users", "Users"),
                ("/admin/route/vehicles", "Vehicles"),
                ("/admin/route/standard-values", "Standardized Lists"),
                ("/admin/route/odometer-exceptions", "Odometer Exceptions"),
            ):
                await page.goto(ruta)
                await expect(
                    page.locator("h1", has_text=titulo)
                ).to_have_count(1, timeout=20_000)

            # Y la experiencia operativa, sin volver a autenticarse.
            await page.goto("/route")
            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=20_000)
        finally:
            await navegador.close()


async def test_the_supervisor_reads_the_values_their_trip_needs(seeded, live_server):
    """Caso límite 15 en el navegador, donde importa.

    El formulario del viaje tiene que poder ofrecer el motivo obligatorio. Es el
    403 que hacía imposible arrancar tres contextos, ahora resuelto con una
    capacidad de lectura propia en vez de con `execute` haciendo de comodín.
    """
    from playwright.async_api import async_playwright

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("Working since")).to_have_count(
                1, timeout=20_000
            )

            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Employee Visit").click()
            await page.get_by_role("combobox").click()

            # Los cuatro motivos aprobados, leídos por un supervisor.
            for motivo in (
                "Attendance Issue",
                "Document Follow-up",
                "Transportation Issue",
                "Employee Support",
            ):
                await expect(
                    page.get_by_role("option", name=motivo, exact=True)
                ).to_have_count(1, timeout=20_000)

            # Pero administrarlos, no: la pantalla de listas no se le sirve.
            respuesta = await page.goto("/admin/route/standard-values")
            assert respuesta.status in (401, 403, 404)
        finally:
            await navegador.close()


# ── FR-03: el escenario que destapó el hueco, en el navegador ────────────────


@pytest.mark.parametrize(
    "quien",
    ["platform_admin", "owner", "admin"],
    ids=["superadmin", "core-owner", "core-admin"],
)
async def test_the_route_user_form_shows_two_roles_to_every_authority(
    seeded, alpha_client, live_server, quien,
):
    """FR-03, declarado test de aceptación obligatorio, y el test #3.

    El caso que CER encontró: alguien con toda la autoridad de la plataforma —o
    un `owner` del núcleo— entrando por `CER Route > Users` seguía recibiendo el
    catálogo completo del tenant. La autoridad de quien mira no debería cambiar
    lo que una pantalla de producto ofrece.

    Se recorre en el navegador porque es donde ocurría, y se cierra con la
    comprobación por API: el paso 7 de FR-03 pide intentar la asignación directa
    saltándose el selector, y el 8 que no se escriba nada.
    """
    from playwright.async_api import async_playwright

    email = (
        seeded.platform_admin.email
        if quien == "platform_admin"
        else seeded.alpha.users[quien].email
    )

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)

            await page.goto("/admin/route/users")
            await expect(
                page.locator("h1", has_text="Users")
            ).to_have_count(1, timeout=20_000)

            await page.get_by_role("button", name="Create User").click()
            await expect(
                page.get_by_text("Role in this company")
            ).to_have_count(1, timeout=20_000)

            selector = page.locator("[role='combobox']").last
            await selector.click()

            opciones = page.get_by_role("option")
            await expect(opciones).to_have_count(2, timeout=20_000)

            textos = sorted(await opciones.all_inner_texts())
            assert textos == ["Administrador", "Supervisor"], (
                f"{quien} debería ver exactamente los dos roles de producto: {textos}"
            )

            # Paso 5: ninguna etiqueta del núcleo.
            for nombre in ROLES_DEL_NUCLEO:
                await expect(
                    page.get_by_role("option", name=nombre, exact=True)
                ).to_have_count(0)

            # Paso 6: ningún código técnico.
            assert "route_admin" not in " ".join(textos)
            assert "supervisor" not in " ".join(textos)
        finally:
            await navegador.close()

    # ── Pasos 7 y 8: por API, saltándose el selector ────────────────────────
    async with TenantClient("alpha") as cliente:
        await cliente.login(email)
        respuesta = await cliente.post(
            "/api/route/users",
            json={
                "username": f"fr03_{quien}",
                "email": f"fr03_{quien}@alpha.example.com",
                "first_name": "FR03",
                "last_name": quien,
                "password": TEST_PASSWORD,
                "role_id": seeded.alpha.roles["owner"],
            },
        )

    assert respuesta.status_code == 403, respuesta.text

    from sqlalchemy import text

    async with async_session_maker() as session:
        escrito = await session.scalar(
            text('SELECT count(*) FROM "user" WHERE email = :e'),
            {"e": f"fr03_{quien}@alpha.example.com"},
        )
    assert escrito == 0, "el rechazo precede a la escritura"
