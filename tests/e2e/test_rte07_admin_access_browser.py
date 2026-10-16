"""El Administrador recupera Today / Live, visto desde el navegador.

Qué demuestra este archivo
---------------------------
El recorrido completo del defecto de campo y de su corrección, en una sola
sesión de navegador: el Administrador **sin** la concesión no ve el menú y no
abre la página; se ejecuta la alineación; y **sin volver a entrar** el menú
aparece y la página carga.

Lo de «sin volver a entrar» no es un detalle de comodidad: es lo que decide si
CER tiene que pedirle a la gente que cierre sesión después del despliegue. La
cookie `user_data` que pinta el menú se recalcula contra la base en cada
petición, así que basta con recargar. El test lo comprueba en vez de suponerlo.

Sin `data-testid`
-----------------
Como el resto de la suite de navegador: el build de producción los elimina de
los `.tsx`, así que un test que los buscara fallaría contra el bundle que se
despliega. Se localiza por rol y texto visible.
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
RUTA = "/admin/route/today"
CAPACIDAD = "route.live.read"
MENU = "Today / Live"


async def _quitar_la_concesion(company_id: int) -> None:
    """Deja el tenant como estaba antes de que RTE07 existiera."""
    async with async_session_maker() as session:
        role_id = await session.scalar(
            select(Role.id).where(
                Role.company_id == company_id, Role.name == "route_admin"
            )
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


async def test_el_administrador_recupera_el_menu_y_la_pagina(
    seeded, alpha_client, live_server,
):
    """T2: de no ver nada a entrar, sin volver a iniciar sesión.

    El orden importa: primero se comprueba que **de verdad** no entraba —si no,
    el verde del final no demostraría nada— y después que la alineación lo
    arregla sobre la misma sesión abierta.
    """
    from playwright.async_api import async_playwright
    from app.db.scripts.align_role_capabilities import alinear

    await _quitar_la_concesion(seeded.alpha.id)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            # ── Antes: el defecto que reportó CER ──────────────────────────
            await page.goto("/admin")
            await expect(page.get_by_role("link", name=MENU)).to_have_count(
                0, timeout=15_000
            )
            respuesta = await page.goto(RUTA)
            assert respuesta is not None and respuesta.status in (401, 403, 404), (
                f"la página se sirvió sin la capacidad (estado {respuesta and respuesta.status})"
            )

            # ── La corrección, por el camino soportado ─────────────────────
            resumen = await alinear()
            assert resumen.concesiones_anadidas >= 1

            # ── Después: la misma sesión, sin volver a entrar ──────────────
            await page.goto("/admin")
            enlace = page.get_by_role("link", name=MENU)
            await expect(enlace).to_have_count(1, timeout=15_000)
            await enlace.click()

            await expect(
                page.get_by_role("heading", name="Today / Live")
            ).to_have_count(1, timeout=20_000)
            await expect(page.get_by_text("Supervisors working")).to_have_count(1)
        finally:
            await navegador.close()


async def test_el_supervisor_no_ve_el_destino_ni_entra(
    seeded, alpha_client, live_server,
):
    """T4, en el navegador: la corrección no ensancha al Supervisor.

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
            await expect(page.get_by_role("link", name=MENU)).to_have_count(
                0, timeout=15_000
            )

            respuesta = await page.goto(RUTA)
            assert respuesta is not None and respuesta.status in (401, 403, 404), (
                f"el Supervisor abrió Today / Live (estado {respuesta and respuesta.status})"
            )
        finally:
            await navegador.close()
