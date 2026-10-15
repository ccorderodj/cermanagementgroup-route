"""Jerarquía V1.6 en el navegador.

* **Replace manager… → «Keep … with a lower role»**: se elige el rol inferior y
  a quién reporta; la vista previa lo dice y, al confirmar, la persona sigue en
  la compañía con su nuevo cargo. Escritorio y móvil.
* **Vaciar un mando a mano**: en Edit, llevarse al último del equipo de un RM
  se rechaza y el motivo aparece en «Reports to».

Capturas en `var/screenshots/hierarchy-v16/`.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import lanzar_edge
from tests.e2e.test_hierarchy_v14_browser import CEO, _accion, _editar
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL, _elegir, _entrar
from tests.integration.test_org_hierarchy import _filas, _organigrama

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/hierarchy-v16")


def _nombre(clave: str) -> str:
    return f"{clave.upper()} Org"


async def _vigente(seeded, clave):
    f = await _filas(
        "SELECT position, superior_user_id FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
        u=seeded.alpha.users[clave].id,
    )
    return tuple(f[0]) if f else None


@pytest.mark.parametrize("viewport", ["escritorio", "movil"])
async def test_sustituir_al_coo_y_dejarlo_como_rm(seeded, alpha_client, live_server, viewport):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    tamano = ESCRITORIO if viewport == "escritorio" else MOVIL
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin", tamano)
            await _accion(page, "/admin/route/users", "alpha_coo", "Replace manager…", "#succession-successor")
            await _elegir(page, "#succession-successor", f"{_nombre('rm_b')} · Regional Manager")
            await page.locator("#succession-keep").click()
            await _elegir(page, "#succession-keep-role", "Regional Manager")
            await _elegir(page, "#succession-keep-superior", f"{_nombre('rm_b')} · COO")
            vista = page.locator("#succession-preview")
            await expect(vista).to_contain_text(f"{_nombre('rm_b')} becomes COO under {CEO}", timeout=20_000)
            await expect(vista).to_contain_text(
                f"{_nombre('coo')} stays as Regional Manager under {_nombre('rm_b')}."
            )
            await page.screenshot(path=str(DESTINO / f"{viewport}-sustituir-y-bajar-de-rango.png"), full_page=True)
            await page.get_by_role("button", name="Confirm replacement").click()
            await expect(page.get_by_text("is now Regional Manager").first).to_be_visible(timeout=20_000)
            await contexto.close()
        finally:
            await navegador.close()
    rm_b = seeded.alpha.users["rm_b"].id
    assert await _vigente(seeded, "coo") == ("regional_manager", rm_b)
    assert await _vigente(seeded, "rm_b") == ("coo", seeded.alpha.users["ceo"].id)
    assert await _vigente(seeded, "rm_a") == ("regional_manager", rm_b)


async def test_vaciar_un_rm_desde_edit_se_explica(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    # RM-B tiene un solo supervisor: SUP-B.
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin")
            await _editar(page, "/admin/route/users", "alpha_sup_b")
            await _elegir(page, "#security-user-superior", f"{_nombre('coo')} · COO")
            await page.locator('form button[type="submit"]').click()
            await expect(page.get_by_text("without a team").first).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "escritorio-mando-sin-equipo.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()
    assert await _vigente(seeded, "sup_b") == ("supervisor", seeded.alpha.users["rm_b"].id)
