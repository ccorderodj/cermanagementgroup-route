"""Jerarquía V1.4 en el navegador: integridad, retiro y sustitución.

Lo que se comprueba
-------------------
* **CER Route → Users → Edit**: «Reports to» llega **precargado** con el
  superior vigente (H-2), también tras recargar.
* **Access control → Users**: cambiar el rol de un jefe se rechaza y el motivo
  aparece en el campo del rol; nada cambia.
* Sin CEO: el campo sigue visible y dice «No CEO assigned yet».
* **Replace manager…** y **Retire manager…** desde la fila: vista previa con a
  quién se mueve y a dónde, confirmación, lista recargada y árbol preservado.
  En escritorio y en móvil.

Capturas en `var/screenshots/hierarchy-v14/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import lanzar_edge
from tests.e2e.test_org_hierarchy_browser import ESCRITORIO, MOVIL, _abrir_alta, _elegir, _entrar, _rellenar
from tests.integration.test_org_hierarchy import _ejecutar, _filas, _organigrama

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/hierarchy-v14")


def _nombre(clave: str) -> str:
    return f"{clave.upper()} Org"


CEO = "Ceo_base Tester"


async def _menu_de_fila(page, ruta: str, username: str):
    await page.goto(ruta)
    buscador = page.get_by_placeholder("Search users...")
    await expect(buscador).to_be_visible(timeout=20_000)
    await buscador.fill(username)
    fila = page.get_by_role("row").filter(has_text=username)
    await expect(fila).to_have_count(1, timeout=20_000)
    # La búsqueda recarga la tabla con retardo, y esa recarga cierra un menú
    # ya abierto: se espera a que termine y se reintenta.
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1_000)
    for _ in range(6):
        await fila.get_by_role("button", name="Open menu").click()
        if await page.get_by_role("menuitem").count():
            return
        await page.wait_for_timeout(500)
    raise AssertionError("el menú de la fila no se abrió")


async def _accion(page, ruta: str, username: str, accion: str, abierto: str):
    """Abre la acción de la fila hasta que aparece `abierto` (el menú se anima)."""
    for _ in range(4):
        await _menu_de_fila(page, ruta, username)
        await page.get_by_role("menuitem", name=accion).click(timeout=5_000)
        try:
            await expect(page.locator(abierto)).to_be_visible(timeout=5_000)
            return
        except AssertionError:
            await page.keyboard.press("Escape")
    raise AssertionError(f"«{accion}» no se abrió")


async def _editar(page, ruta: str, username: str):
    await _accion(page, ruta, username, "Edit", "#security-user-role")


async def _vigente(seeded, clave):
    f = await _filas(
        "SELECT position, superior_user_id FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
        u=seeded.alpha.users[clave].id,
    )
    return tuple(f[0]) if f else None


async def test_edit_precarga_el_superior_y_la_pantalla_general_no_cambia_la_jerarquia(
    seeded, alpha_client, live_server
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin")
            # H-2: precargado al abrir, y otra vez tras recargar.
            for vuelta in range(2):
                await _editar(page, "/admin/route/users", "alpha_rm_a")
                await expect(page.locator("#security-user-superior")).to_contain_text(
                    f"{_nombre('coo')} · COO", timeout=20_000
                )
                if vuelta == 0:
                    await page.screenshot(path=str(DESTINO / "escritorio-edit-precargado.png"), full_page=True)
                await page.reload()

            # Access control → Users: el rol de un jefe no se cambia aquí.
            await _editar(page, "/admin/security/users/list", "alpha_coo")
            await _elegir(page, "#security-user-role", "Supervisor")
            await page.locator('form button[type="submit"]').click()
            await expect(page.get_by_text("managed in CER Route → Users").first).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "escritorio-access-control-409.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()
    assert await _vigente(seeded, "coo") == ("coo", seeded.alpha.users["ceo"].id)
    rol = await _filas(
        "SELECT r.name FROM user_company uc JOIN role r ON r.id = uc.role_id WHERE uc.user_id = :u",
        u=seeded.alpha.users["coo"].id,
    )
    assert rol[0].name == "COO"


async def test_ceo_y_coo_solo_por_replace_manager(seeded, alpha_client, live_server):
    """V1.5: en Edit, el rol y el superior de un COO están fijos y lo dicen; a
    un RM la lista ya no le ofrece CEO ni COO."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin")
            await _editar(page, "/admin/route/users", "alpha_coo")
            await expect(page.locator("#security-user-replace-only")).to_be_visible(timeout=20_000)
            await expect(page.locator("#security-user-role")).to_be_disabled()
            await expect(page.locator("#security-user-superior")).to_be_disabled()
            await page.screenshot(path=str(DESTINO / "escritorio-coo-solo-replace.png"), full_page=True)

            await page.reload()
            await _editar(page, "/admin/route/users", "alpha_rm_b")
            await page.locator("#security-user-role").click()
            opciones = [t.strip() for t in await page.get_by_role("option").all_inner_texts()]
            await page.keyboard.press("Escape")
            assert "CEO" not in opciones and "COO" not in opciones, opciones
            assert "Regional Manager" in opciones and "Supervisor" in opciones
            await contexto.close()
        finally:
            await navegador.close()


async def test_sin_ceo_el_campo_sigue_visible_y_lo_explica(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _ejecutar("DELETE FROM org_assignment WHERE company_id = :c", c=seeded.alpha.id)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin")
            await _abrir_alta(page)
            await _rellenar(page, "alpha_nuevo_coo")
            await _elegir(page, "#security-user-role", "COO")
            await expect(page.locator("#security-user-superior")).to_be_visible(timeout=20_000)
            await expect(page.get_by_text("No CEO assigned yet — assign a CEO first.")).to_be_visible()
            await page.screenshot(path=str(DESTINO / "escritorio-sin-ceo.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()


@pytest.mark.parametrize("viewport", ["escritorio", "movil"])
async def test_sustituir_y_retirar_desde_la_fila_con_vista_previa(
    seeded, alpha_client, live_server, viewport
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    tamano = ESCRITORIO if viewport == "escritorio" else MOVIL
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin", tamano)

            # Sustituir al COO por RM-B.
            await _accion(page, "/admin/route/users", "alpha_coo", "Replace manager…", "#succession-successor")
            await _elegir(page, "#succession-successor", f"{_nombre('rm_b')} · Regional Manager")
            vista = page.locator("#succession-preview")
            await expect(vista).to_contain_text(f"{_nombre('rm_b')} becomes COO under {CEO}", timeout=20_000)
            await expect(vista).to_contain_text(_nombre("rm_a"))
            await expect(vista).to_contain_text(_nombre("sup_c"))
            await expect(vista).to_contain_text(f"{_nombre('coo')} will be removed from this company.")
            await page.screenshot(path=str(DESTINO / f"{viewport}-sustituir-vista-previa.png"), full_page=True)
            assert await _vigente(seeded, "rm_a") == ("regional_manager", seeded.alpha.users["coo"].id), (
                "la vista previa no escribe"
            )
            await page.get_by_role("button", name="Confirm replacement").click()
            await expect(page.get_by_text("Manager replaced").first).to_be_visible(timeout=20_000)

            # Retirar al RM-A: su equipo sube al nuevo COO.
            await _accion(page, "/admin/route/users", "alpha_rm_a", "Retire manager…", "#succession-preview")
            vista = page.locator("#succession-preview")
            await expect(vista).to_contain_text(_nombre("osm_a"), timeout=20_000)
            await expect(vista).to_contain_text(_nombre("sup_a"))
            await expect(vista).to_contain_text(_nombre("rm_b"))
            await page.screenshot(path=str(DESTINO / f"{viewport}-retirar-vista-previa.png"), full_page=True)
            await page.get_by_role("button", name="Confirm retirement").click()
            await expect(page.get_by_text("Manager retired").first).to_be_visible(timeout=20_000)

            # La lista se recargó: los que salieron ya no están.
            buscador = page.get_by_placeholder("Search users...")
            await buscador.fill("alpha_rm_a")
            await expect(page.get_by_role("row").filter(has_text="alpha_rm_a")).to_have_count(0, timeout=20_000)
            await buscador.fill("")
            await page.screenshot(path=str(DESTINO / f"{viewport}-tras-cambios.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()

    rm_b = seeded.alpha.users["rm_b"].id
    assert await _vigente(seeded, "rm_b") == ("coo", seeded.alpha.users["ceo"].id)
    assert await _vigente(seeded, "sup_c") == ("supervisor", rm_b)
    assert await _vigente(seeded, "osm_a") == ("osm", rm_b)
    assert await _vigente(seeded, "sup_a") == ("supervisor", rm_b)
    assert await _vigente(seeded, "sales_a") == ("sales", seeded.alpha.users["ceo"].id)
    assert await _vigente(seeded, "coo") is None and await _vigente(seeded, "rm_a") is None
