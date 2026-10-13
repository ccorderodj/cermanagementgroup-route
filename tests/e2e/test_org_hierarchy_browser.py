"""Jerarquía y alcance en el navegador: cinco cargos, Superadmin y dos ramas.

Lo que se comprueba
-------------------
* El Superadmin asigna **Cargo** y **Superior** desde el formulario existente
  de Route Users; la asignación queda en la base.
* Un RM sólo ve su rama en Route Users y en Today, sólo puede dar cargos por
  debajo del suyo y sólo bajo su rama; lo que crea queda bajo él.
* Cada cargo ve en Today exactamente su rama (escritorio y móvil).
* Menús: los managers ven Today, Activity, Reports y Users de Route, y **no**
  Supervisors ni Vehicles; OSM y Supervisor tienen exactamente los mismos
  permisos, la misma Activity propia y ninguna pantalla de administración.

El organigrama es el de `test_org_hierarchy`. Capturas en
`var/screenshots/hierarchy/`, fuera del árbol versionado.
"""

from __future__ import annotations

import json
import pathlib
from urllib.parse import unquote

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.conftest import TEST_PASSWORD
from tests.integration.test_org_hierarchy import _filas, _organigrama

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/hierarchy")
ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}


def _nombre(clave: str) -> str:
    return f"{clave.upper()} Org"


async def _entrar(navegador, live_server, seeded, clave, viewport=ESCRITORIO):
    contexto = await navegador.new_context(base_url=live_server, viewport=viewport)
    page = await contexto.new_page()
    await abrir_sesion(page, seeded.alpha.users[clave].email)
    return contexto, page


async def _alta(page, *, username: str, rol: str, cargo: str, jefe: str) -> None:
    await page.goto("/admin/route/users")
    disparador = page.get_by_role("button", name="Create User")
    await expect(disparador).to_have_count(1, timeout=20_000)
    await disparador.click()
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
    await page.locator("#security-user-role").click()
    await page.get_by_role("option", name=rol, exact=True).click()
    await expect(page.locator("#security-user-position")).to_be_visible(timeout=20_000)
    await page.locator("#security-user-position").click()
    await page.get_by_role("option", name=cargo, exact=True).click()
    await page.locator("#security-user-superior").click()
    await page.get_by_role("option", name=jefe).click()


async def _opciones(page, selector: str) -> list[str]:
    await page.locator(selector).click()
    await expect(page.get_by_role("option").first).to_be_visible(timeout=20_000)
    textos = [t.strip() for t in await page.get_by_role("option").all_inner_texts()]
    await page.keyboard.press("Escape")
    return textos


async def test_superadmin_asigna_cargo_y_superior(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "route_admin")
            await _alta(page, username="alpha_nuevo_sa", rol="Supervisor", cargo="Supervisor",
                        jefe=f"{_nombre('rm_a')} · Regional Manager")
            await page.screenshot(path=str(DESTINO / "escritorio-superadmin-formulario.png"), full_page=True)
            async with page.expect_response(lambda r: r.url.endswith("/api/route/users")) as info:
                await page.locator('form button[type="submit"]').click()
            creado = await (await info.value).json()
            fila = await _filas(
                "SELECT position, superior_user_id FROM org_assignment WHERE user_id = :u "
                "AND valid_to IS NULL", u=creado["id"],
            )
            assert (fila[0].position, fila[0].superior_user_id) == (
                "supervisor", seeded.alpha.users["rm_a"].id
            )
            await contexto.close()
        finally:
            await navegador.close()


async def test_rm_solo_su_rama_en_usuarios_y_alta_acotada(seeded, alpha_client, live_server):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded, perfiles=False)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _entrar(navegador, live_server, seeded, "rm_a")
            await page.goto("/admin/route/users")
            await expect(page.get_by_text(_nombre("sup_a").split()[0]).first).to_be_visible(timeout=20_000)
            for ajeno in ("sup_b", "rm_b", "coo", "ceo"):
                await expect(page.get_by_text(ajeno.upper(), exact=True)).to_have_count(0)
            await page.screenshot(path=str(DESTINO / "escritorio-rm-a-usuarios.png"), full_page=True)

            await page.get_by_role("button", name="Create User").click()
            await page.locator("#security-user-role").click()
            await expect(page.get_by_role("option")).to_have_count(1, timeout=20_000)
            assert [t.strip() for t in await page.get_by_role("option").all_inner_texts()] == ["Supervisor"]
            await page.keyboard.press("Escape")
            assert await _opciones(page, "#security-user-position") == ["OSM", "Supervisor"]
            await page.locator("#security-user-position").click()
            await page.get_by_role("option", name="Supervisor", exact=True).click()
            assert await _opciones(page, "#security-user-superior") == [
                f"{_nombre('rm_a')} · Regional Manager"
            ]
            await contexto.close()

            contexto, page = await _entrar(navegador, live_server, seeded, "rm_a")
            await _alta(page, username="alpha_nuevo_rm", rol="Supervisor", cargo="Supervisor",
                        jefe=f"{_nombre('rm_a')} · Regional Manager")
            async with page.expect_response(lambda r: r.url.endswith("/api/route/users")) as info:
                await page.locator('form button[type="submit"]').click()
            respuesta = await info.value
            assert respuesta.status in (200, 201)
            creado = await respuesta.json()
            fila = await _filas(
                "SELECT superior_user_id FROM org_assignment WHERE user_id = :u AND valid_to IS NULL",
                u=creado["id"],
            )
            assert fila[0].superior_user_id == seeded.alpha.users["rm_a"].id
            await contexto.close()
        finally:
            await navegador.close()


@pytest.mark.parametrize(
    ("clave", "visibles", "viewport"),
    [
        ("ceo", ("osm_a", "sup_a", "sup_b", "sup_c"), ESCRITORIO),
        ("coo", ("osm_a", "sup_a", "sup_c"), ESCRITORIO),
        ("rm_a", ("osm_a", "sup_a"), ESCRITORIO),
        ("rm_b", ("sup_b",), MOVIL),
        ("rm_a", ("osm_a", "sup_a"), MOVIL),
    ],
)
async def test_today_muestra_solo_la_rama(seeded, alpha_client, live_server, clave, visibles, viewport):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _organigrama(alpha_client, seeded)
    todos = ("osm_a", "sup_a", "sup_b", "sup_c")
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
            for otro in set(todos) - set(visibles):
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


async def test_menus_por_cargo_y_osm_igual_a_supervisor(seeded, alpha_client, live_server):
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
                await page.screenshot(path=str(DESTINO / f"escritorio-{clave}-menu.png"), full_page=True)
                await contexto.close()

            vistos = {}
            for clave in ("osm_a", "sup_a"):
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
            assert vistos["osm_a"] == vistos["sup_a"]
        finally:
            await navegador.close()
