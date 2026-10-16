"""Activity Explorer: del tenant desalineado a entrar, en el navegador.

Qué demuestra este archivo
---------------------------
El ciclo de vida completo de §7 visto desde la pantalla: el Administrador de un
tenant que no tiene la concesión no ve **Activity** en el menú y no abre la
página; se ejecuta la alineación compartida; y **sin volver a entrar** el menú
aparece y el explorador carga con sus datos.

Lo de «sin volver a entrar» se comprueba, no se supone: §9 pide expresamente no
exigir cerrar sesión salvo que la arquitectura lo imponga. No lo impone — la
cookie que pinta el menú se recalcula contra la base en cada petición— y eso
decide si CER tiene que pedirle a la gente que vuelva a entrar tras el
despliegue.

Sin `data-testid`
-----------------
El build de producción los elimina de los `.tsx`, así que un test que los
buscara fallaría contra el bundle que se despliega. Se localiza por rol y texto
visible.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from sqlalchemy import delete, select

from app.database import async_session_maker
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
RUTA = "/admin/route/activity"
CAPACIDAD = "route.activity.read"
#: El enlace del menú. Se localiza por **subcadena** y no con `exact`: su
#: nombre accesible incluye además la etiqueta del grupo —`Activity CER Route`—
#: así que una comparación exacta no casa nunca. Y eso importa sobre todo en el
#: test negativo: con `exact` habría dado cero aunque el enlace estuviera, y
#: habría pasado sin comprobar nada.
MENU = "Activity"


async def _quitar_la_concesion(company_id: int, rol: str = "route_admin") -> None:
    async with async_session_maker() as session:
        role_id = await session.scalar(
            select(Role.id).where(Role.company_id == company_id, Role.name == rol)
        )
        permission_id = await session.scalar(
            select(Permission.id).where(Permission.name == CAPACIDAD)
        )
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        await session.commit()


async def _un_supervisor(alpha_client, seeded, unidad: str) -> None:
    """Un supervisor con vehículo, para que el explorador tenga a quién mirar.

    Sin ningún perfil la pantalla carga su estado vacío, que es correcto y no
    demuestra gran cosa: el test quiere ver el explorador **con su contenido**,
    no su armazón.
    """
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


async def test_el_administrador_recupera_activity_sin_volver_a_entrar(
    seeded, alpha_client, live_server,
):
    """T5: los seis pasos, en orden, sobre una sola sesión de navegador.

    El orden importa: primero se comprueba que **de verdad** no entraba. Un
    verde al final sin ese paso no demostraría que la alineación hizo nada.
    """
    from playwright.async_api import async_playwright
    from app.db.scripts.align_role_capabilities import alinear

    await _un_supervisor(alpha_client, seeded, "V-RTE08-ACC")
    await _quitar_la_concesion(seeded.alpha.id)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            # 2. Estado desalineado: ni menú ni página.
            await page.goto("/admin")
            await expect(
                page.get_by_role("link", name=MENU)
            ).to_have_count(0, timeout=15_000)
            respuesta = await page.goto(RUTA)
            assert respuesta is not None and respuesta.status in (401, 403, 404), (
                f"la página se sirvió sin la capacidad (estado {respuesta and respuesta.status})"
            )

            # 3. La alineación compartida.
            resumen = await alinear()
            assert resumen.concesiones_anadidas >= 1

            # 4, 5 y 6. Recargar basta: el menú aparece y el explorador carga.
            await page.goto("/admin")
            enlace = page.get_by_role("link", name=MENU)
            await expect(enlace).to_have_count(1, timeout=15_000)
            await enlace.click()

            await expect(
                page.get_by_role("heading", name="Activity", exact=True)
            ).to_have_count(1, timeout=20_000)
            await expect(
                page.get_by_text("Explore operational history by supervisor and period")
            ).to_have_count(1)
            # Contenido real, no sólo el encabezado: el encabezado también
            # existe mientras carga, y afirmar fidelidad sobre el estado de
            # carga sería evidencia engañosa.
            await expect(page.get_by_text("estimated fuel")).to_have_count(
                1, timeout=20_000
            )
        finally:
            await navegador.close()


async def test_el_supervisor_no_ve_activity_ni_entra(
    seeded, alpha_client, live_server,
):
    """T7 en el navegador: la alineación no ensancha al Supervisor.

    El menú no lo ofrece y la URL directa no se sirve. Lo segundo es el
    control; lo primero es experiencia de usuario, y tienen que coincidir.
    """
    from playwright.async_api import async_playwright
    from app.db.scripts.align_role_capabilities import alinear

    await alinear()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/admin")
            await expect(
                page.get_by_role("link", name=MENU)
            ).to_have_count(0, timeout=15_000)

            respuesta = await page.goto(RUTA)
            assert respuesta is not None and respuesta.status in (401, 403, 404), (
                f"el Supervisor abrió Activity (estado {respuesta and respuesta.status})"
            )
        finally:
            await navegador.close()
