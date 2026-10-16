"""El Superadmin de plataforma aplica permisos al momento, desde Roles & Permissions.

El botón dice `Apply changes` (no `Submit for approval`); al pulsarlo el
permiso queda concedido y no hay ninguna solicitud pendiente. Captura en
`var/screenshots/superadmin-permissions/`.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO
from tests.integration.test_superadmin_direct_permissions import _concedidas, _filas, _id_permiso

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/superadmin-permissions")


async def test_el_superadmin_aplica_sin_aprobacion(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    rol = seeded.alpha.roles["viewer"]
    permiso = await _id_permiso("route.activity.map.read")
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=ESCRITORIO)
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.platform_admin.email)
            await page.goto("/admin/security/roles/list")
            await page.get_by_role("button", name=re.compile(r"^viewer", re.IGNORECASE)).first.click()
            casilla = page.locator(f"#perm-{permiso}")
            await expect(casilla).to_be_visible(timeout=20_000)
            await casilla.click()
            await expect(page.get_by_text("Applied immediately (platform superadmin).")).to_be_visible()
            boton = page.get_by_role("button", name="Apply changes")
            await expect(boton).to_be_enabled()
            await page.screenshot(path=str(DESTINO / "escritorio-apply-changes.png"), full_page=True)
            await boton.click()
            await expect(page.get_by_text("waiting for approval")).to_have_count(0, timeout=20_000)
            await expect(casilla).to_be_checked()
            await contexto.close()
        finally:
            await navegador.close()
    assert "route.activity.map.read" in await _concedidas(rol)
    pendientes = await _filas(
        "SELECT 1 FROM role_permission_change_request WHERE role_id = :r AND status = 'pending'", r=rol
    )
    assert pendientes == []
