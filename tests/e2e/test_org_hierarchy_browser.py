"""Jerarquía con un rol por cargo (V1.3), en el navegador.

Lo que se comprueba
-------------------
* **Roles & Permissions** enseña CEO, COO, Regional Manager, OSM, Supervisor y
  Sales por su nombre, y cada uno con capacidades (no vacío).
* **Users de CER Route → Create / Edit user**: se elige el **rol** por su nombre
  y, debajo, **Reports to** con las personas que ese rol admite como superior —
  para Sales, sólo CEOs—. Lo guardado se ve al reabrir tras recargar.
* Un RM sólo ofrece OSM y Supervisor y sólo superiores de su rama.
* Today: el CEO ve a Sales; el COO y el RM, no (escritorio y móvil).
* Menús por cargo; OSM, Supervisor y Sales con los mismos permisos, la misma
  Activity propia y ninguna pantalla de administración.

El organigrama es el de `test_org_hierarchy`. Capturas en
`var/screenshots/hierarchy-v13/`, fuera del árbol versionado.
"""

from __future__ import annotations

import json
import pathlib
import re
from urllib.parse import unquote

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.conftest import TEST_PASSWORD
from tests.integration.test_org_hierarchy import EJECUTORES, _filas, _organigrama

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/hierarchy-v13")
ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}
ROLES_V13 = ("CEO", "COO", "Regional Manager", "OSM", "Supervisor", "Sales")


def _nombre(clave: str) -> str:
    return f"{clave.upper()} Org"


async def _entrar(navegador, live_server, seeded, clave, viewport=ESCRITORIO):
    contexto = await navegador.new_context(base_url=live_server, viewport=viewport)
    page = await contexto.new_page()
    await abrir_sesion(page, seeded.alpha.users[clave].email)
    return contexto, page


async def _opciones(page, selector: str) -> list[str]:
    await page.locator(selector).click()
    await expect(page.get_by_role("option").first).to_be_visible(timeout=20_000)
    textos = [t.strip() for t in await page.get_by_role("option").all_inner_texts()]
    await page.keyboard.press("Escape")
    return textos


async def _abrir_alta(page) -> None:
    await page.goto("/admin/route/users")
    disparador = page.get_by_role("button", name="Create User")
    await expect(disparador).to_have_count(1, timeout=20_000)
    await disparador.click()
    await expect(page.locator("#security-user-username")).to_have_count(1, timeout=20_000)


async def _rellenar(page, username: str) -> None:
    await page.locator("#security-user-username").fill(username)
    await page.locator("#security-user-email").fill(f"{username}@example.com")
    await page.locator("#security-user-first-name").fill("Nueva")
    await page.locator("#security-user-last-name").fill("Persona")
    await page.locator("#security-user-password").fill(TEST_PASSWORD)
    await page.locator("#security-user-confirm-password").fill(TEST_PASSWORD)
    await page.locator("#security-user-gender").click()
    await page.get_by_role("option", name="Male", exact=True).click()
    await page.locator("#security-user-status").click()
    await page.get_by_role("option", name="Active", exact=True).click()


async def _elegir(page, selector: str, opcion: str) -> None:
    await page.locator(selector).click()
    await page.get_by_role("option", name=opcion, exact=True).click()


async def test_roles_and_permissions_ensena_los_seis_roles_con_capacidades(
    seeded, alpha_client, live_server
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "owner")
            await page.goto("/admin/security/roles/list")
            for rol in ROLES_V13:
                # El nombre del rol tal cual; `supervisor` se ve con mayúscula por CSS.
                patron = re.compile(rf"^{re.escape(rol)}$", re.IGNORECASE)
                await expect(page.get_by_text(patron).first).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "escritorio-roles-and-permissions.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()
    # Y lo que enseña está respaldado: ninguno vacío.
    for rol in ("CEO", "COO", "Regional Manager", "OSM", "supervisor", "Sales"):
        n = await _filas(
            "SELECT count(*) AS n FROM role_permission WHERE role_id = :r", r=seeded.alpha.roles[rol]
        )
        assert n[0].n > 0, rol


async def test_superadmin_crea_sales_bajo_un_ceo_y_persiste_al_reabrir(
    seeded, alpha_client, live_server
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin")
            await _abrir_alta(page)
            await _rellenar(page, "alpha_nueva_sales")
            # El rol, por su nombre; todos los de la jerarquía están.
            roles = await _opciones(page, "#security-user-role")
            assert set(ROLES_V13) <= set(roles)
            await _elegir(page, "#security-user-role", "Sales")
            # Sales sólo admite un CEO como superior.
            assert sorted(await _opciones(page, "#security-user-superior")) == sorted(
                [f"{_nombre('ceo')} · CEO", "Ceo_base Tester · CEO"]
            )
            await _elegir(page, "#security-user-superior", f"{_nombre('ceo')} · CEO")
            await page.screenshot(path=str(DESTINO / "escritorio-alta-sales.png"), full_page=True)
            async with page.expect_response(lambda r: r.url.endswith("/api/route/users")) as info:
                await page.locator('form button[type="submit"]').click()
            creado = await (await info.value).json()
            fila = await _filas(
                "SELECT position, superior_user_id FROM org_assignment WHERE user_id = :u "
                "AND valid_to IS NULL", u=creado["id"],
            )
            assert (fila[0].position, fila[0].superior_user_id) == ("sales", seeded.alpha.users["ceo"].id)

            # Recargar y reabrir: el rol y el superior siguen ahí.
            await page.reload()
            buscador = page.get_by_placeholder("Search users...")
            await expect(buscador).to_be_visible(timeout=20_000)
            await buscador.fill("alpha_nueva_sales")
            fila_ui = page.get_by_role("row").filter(has_text="alpha_nueva_sales")
            await expect(fila_ui).to_have_count(1, timeout=20_000)
            await fila_ui.get_by_role("button", name="Open menu").click()
            await page.get_by_role("menuitem", name="Edit").click()
            await expect(page.locator("#security-user-role")).to_contain_text("Sales", timeout=20_000)
            await expect(page.locator("#security-user-superior")).to_contain_text(
                f"{_nombre('ceo')} · CEO", timeout=20_000
            )
            await page.screenshot(path=str(DESTINO / "escritorio-editar-sales.png"), full_page=True)
            await contexto.close()

            # Móvil: el mismo formulario con Rol y Reports to.
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin", MOVIL)
            await _abrir_alta(page)
            await _elegir(page, "#security-user-role", "Supervisor")
            await expect(page.locator("#security-user-superior")).to_be_visible(timeout=20_000)
            await page.screenshot(path=str(DESTINO / "movil-alta-supervisor.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()


async def test_un_rm_ofrece_solo_su_nivel_y_su_rama(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    await _organigrama(alpha_client, seeded, perfiles=False)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "rm_a")
            await page.goto("/admin/route/users")
            await expect(page.get_by_text("SUP_A").first).to_be_visible(timeout=20_000)
            for ajeno in ("SALES_A", "SUP_B", "RM_B", "COO", "CEO"):
                await expect(page.get_by_text(ajeno, exact=True)).to_have_count(0)
            await page.get_by_role("button", name="Create User").click()
            assert sorted(await _opciones(page, "#security-user-role")) == ["OSM", "Supervisor"]
            await _elegir(page, "#security-user-role", "Supervisor")
            assert await _opciones(page, "#security-user-superior") == [
                f"{_nombre('rm_a')} · Regional Manager"
            ]
            await contexto.close()
        finally:
            await navegador.close()


@pytest.mark.parametrize(
    ("clave", "visibles", "viewport"),
    [
        ("ceo", EJECUTORES, ESCRITORIO),
        ("coo", ("osm_a", "sup_a", "sup_c"), ESCRITORIO),
        ("rm_a", ("osm_a", "sup_a"), MOVIL),
        ("ceo", EJECUTORES, MOVIL),
    ],
)
async def test_today_el_ceo_ve_a_sales_y_coo_rm_no(seeded, alpha_client, live_server, clave, visibles, viewport):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, clave, viewport)
            async with page.expect_response(lambda r: "/api/live/today" in r.url) as info:
                await page.goto("/admin/route/today")
            cuerpo = await (await info.value).json()
            assert {s["user_id"] for s in cuerpo["supervisors"]} == {
                seeded.alpha.users[v].id for v in visibles
            }
            for v in visibles:
                await expect(page.get_by_text(_nombre(v)).first).to_be_visible(timeout=20_000)
            for otro in set(EJECUTORES) - set(visibles):
                await expect(page.get_by_text(_nombre(otro))).to_have_count(0)
            ancho = await page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert ancho <= 0, f"desborda {ancho}px"
            tipo = "movil" if viewport is MOVIL else "escritorio"
            await page.screenshot(path=str(DESTINO / f"{tipo}-{clave}-today.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()


async def _permisos(page) -> list[str]:
    cookie = next(c for c in await page.context.cookies() if c["name"] == "user_data")
    return sorted(json.loads(unquote(cookie["value"]))["permissions"])


async def test_menus_por_cargo_y_ejecutores_iguales(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            for clave in ("ceo", "coo", "rm_a"):
                contexto, page = await _entrar(navegador, live_server, seeded, clave)
                await page.goto("/admin/route/activity")
                for etiqueta in ("Today / Live", "Activity", "Reports"):
                    await expect(page.get_by_role("link", name=etiqueta, exact=True)).to_be_visible(
                        timeout=20_000
                    )
                await page.get_by_text("CER Route Configuration").click()
                await expect(page.locator('a[href="/admin/route/users"]')).to_be_visible()
                for ausente in ("Vehicles", "Supervisors", "Standardized Lists"):
                    await expect(page.get_by_role("link", name=ausente, exact=True)).to_have_count(0)
                assert (await page.goto("/admin/route/vehicles")).status == 403
                await contexto.close()

            vistos = {}
            for clave in ("osm_a", "sup_a", "sales_a"):
                contexto, page = await _entrar(navegador, live_server, seeded, clave, MOVIL)
                await page.goto("/route/activity")
                await expect(page.get_by_role("link", name="Activity")).to_have_attribute(
                    "aria-current", "page", timeout=20_000
                )
                await expect(page.locator("#explorer-supervisor")).to_have_count(0)
                vistos[clave] = await _permisos(page)
                for ruta in ("/admin/route/today", "/admin/route/activity", "/admin/route/users"):
                    assert (await page.goto(ruta)).status == 403, (clave, ruta)
                await page.goto("/route/activity")
                await page.screenshot(path=str(DESTINO / f"movil-{clave}-activity.png"), full_page=True)
                await contexto.close()
            assert vistos["osm_a"] == vistos["sup_a"] == vistos["sales_a"]
        finally:
            await navegador.close()
