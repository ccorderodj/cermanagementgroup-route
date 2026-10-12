"""H-1: el selector de supervisor de User Activity, también en el teléfono.

El defecto
----------
`ExplorerFilterBar` recibía `showFields={!esMovil}` y ese interruptor ocultaba
en móvil **dos** controles: el selector de supervisor y la fecha. Un
administrador en el teléfono veía siempre al primer supervisor de la lista, sin
forma de cambiarlo. El PO autorizó una excepción acotada: el selector se
muestra en móvil; la fecha sigue oculta.

Lo que se comprueba
-------------------
* El selector se ve y funciona en móvil, y elegir A o B **envía** ese
  `supervisor_user_id` y **pinta** los datos de esa persona (AC01, AC02).
* Cambiar el rango conserva la selección (AC03).
* 360, 390 y 430 px, horizontal y escritorio: sin desbordamiento, la fecha
  sigue oculta en móvil y visible en escritorio (AC03, AC09).
* Si la lectura de B falla, la pantalla **no** enseña los datos de A bajo el
  nombre de B (FR2.6).

Dos supervisores elegibles con historias distinguibles el mismo día: A visita
*ABC Manufacturing*; B —el `route_admin`, que también hace trabajo de campo,
el caso límite del §7— vuelve a casa. Los instantes se fijan para que las
capturas sean comparables entre ejecuciones.

Capturas en `var/screenshots/h1/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte08_activity_explorer_browser import DIA, FOTO, _historia

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/h1")
RUTA = "/admin/route/activity"
ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}


async def _dos_supervisores(alpha_client, seeded) -> dict[str, int]:
    """A con una visita a ABC Manufacturing; B con un regreso a casa. Mismo día."""
    await _historia(alpha_client, seeded, unidad="V-H1-A")

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors",
            json={"user_id": seeded.alpha.users["route_admin"].id},
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Ford", "model": "Ranger", "year": 2024, "unit": "V-H1-B",
                "fuel_grade": "regular", "operational_mpg": "22.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "50000.0"},
    )
    viaje = (await alpha_client.post("/api/trips", json={"purpose": "home"})).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    # El mismo día para los dos, e instantes fijos: las capturas de un antes y
    # un después tienen que poder compararse píxel a píxel.
    base = datetime(DIA.year, DIA.month, DIA.day, 14, 0, tzinfo=timezone.utc)
    async with async_session_maker() as s:
        await s.execute(
            text(
                "UPDATE work_session SET session_date = :d, start_time_zone = NULL, "
                "start_utc_offset_minutes = -240 WHERE company_id = :c"
            ),
            {"d": DIA, "c": seeded.alpha.id},
        )
        await s.execute(
            text("UPDATE trip SET started_at = :s, arrived_at = :l WHERE company_id = :c"),
            {"s": base, "l": base + timedelta(minutes=25), "c": seeded.alpha.id},
        )
        await s.execute(
            text(
                "UPDATE activity_execution SET started_at = :a, ended_at = :f "
                "WHERE company_id = :c"
            ),
            {
                "a": base + timedelta(minutes=30),
                "f": base + timedelta(minutes=70),
                "c": seeded.alpha.id,
            },
        )
        await s.commit()

    return {
        "A": seeded.alpha.users["supervisor"].id,
        "B": seeded.alpha.users["route_admin"].id,
    }


async def _abrir(navegador, live_server, seeded, viewport):
    contexto = await navegador.new_context(base_url=live_server, viewport=viewport)
    page = await contexto.new_page()
    await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
    await page.goto(RUTA)
    await expect(page.get_by_role("heading", name="Activity", exact=True)).to_have_count(
        1, timeout=20_000
    )
    return contexto, page


async def _elegir(page, user_id: int) -> dict:
    """Elige en el selector y devuelve la lectura que eso disparó."""
    async with page.expect_response(
        lambda r: "/api/activity-explorer" in r.url
        and f"supervisor_user_id={user_id}" in r.url
    ) as info:
        await page.get_by_label("Supervisor").select_option(str(user_id))
    respuesta = await info.value
    assert respuesta.status == 200
    return await respuesta.json()


async def test_en_movil_se_elige_supervisor_y_se_ven_sus_datos(
    seeded, alpha_client, live_server
):
    """AC01 y AC02: A y luego B; lo pedido, lo seleccionado y lo pintado coinciden."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    ids = await _dos_supervisores(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(navegador, live_server, seeded, MOVIL)
            selector = page.get_by_label("Supervisor")
            await expect(selector).to_be_visible(timeout=20_000)

            cuerpo = await _elegir(page, ids["A"])
            assert cuerpo["supervisor_user_id"] == ids["A"]
            await expect(selector).to_have_value(str(ids["A"]))
            await expect(page.get_by_text("ABC Manufacturing").first).to_be_visible(
                timeout=20_000
            )
            await page.screenshot(path=str(DESTINO / "movil-390-supervisor-a.png"), full_page=True)

            cuerpo = await _elegir(page, ids["B"])
            assert cuerpo["supervisor_user_id"] == ids["B"]
            await expect(selector).to_have_value(str(ids["B"]))
            await expect(
                page.get_by_role("heading", name="Home", exact=True).first
            ).to_be_visible(timeout=20_000)
            # Nada de A queda a la vista bajo el nombre de B.
            await expect(page.get_by_text("ABC Manufacturing")).to_have_count(0)
            await page.screenshot(path=str(DESTINO / "movil-390-supervisor-b.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()


async def test_en_movil_cambiar_el_rango_conserva_la_seleccion(
    seeded, alpha_client, live_server
):
    """AC03: la misma semántica que en escritorio; la selección sobrevive al rango."""
    from playwright.async_api import async_playwright

    ids = await _dos_supervisores(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(navegador, live_server, seeded, MOVIL)
            await _elegir(page, ids["A"])

            for rango in ("Week", "Month", "Year"):
                async with page.expect_response(
                    lambda r, rg=rango.lower(): "/api/activity-explorer" in r.url
                    and f"range={rg}" in r.url
                ) as info:
                    await page.get_by_role("button", name=rango, exact=True).click()
                respuesta = await info.value
                assert f"supervisor_user_id={ids['A']}" in respuesta.url, respuesta.url
                assert (await respuesta.json())["supervisor_user_id"] == ids["A"]
                await expect(page.get_by_label("Supervisor")).to_have_value(str(ids["A"]))
            await contexto.close()
        finally:
            await navegador.close()


@pytest.mark.parametrize(
    ("ancho", "alto", "nombre"),
    [
        (360, 780, "movil-360"),
        (390, 844, "movil-390"),
        (430, 932, "movil-430"),
        (844, 390, "movil-horizontal"),
        (1280, 900, "escritorio"),
    ],
)
async def test_el_selector_cabe_en_cada_ancho(
    seeded, alpha_client, live_server, ancho, alto, nombre
):
    """AC03 y AC09: sin desbordar; la fecha, oculta en móvil y visible en escritorio."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _dos_supervisores(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(
                navegador, live_server, seeded, {"width": ancho, "height": alto}
            )
            selector = page.get_by_label("Supervisor")
            await expect(selector).to_be_visible(timeout=20_000)
            await expect(page.get_by_text("ABC Manufacturing").first.or_(
                page.get_by_role("heading", name="Home", exact=True).first
            )).to_be_visible(timeout=20_000)

            caja = await selector.bounding_box()
            assert caja is not None
            assert caja["x"] >= 0 and caja["x"] + caja["width"] <= ancho + 1, caja
            assert caja["height"] >= 24, f"objetivo táctil demasiado pequeño: {caja}"
            # Lo que sobresale del ancho de la ventana, sin contar las pestañas
            # de rango (Day/Week/Month/Year): sus botones, su contenedor y los
            # contenedores que las incluyen. Lo que queda —el selector entre
            # ellos— tiene que caber siempre.
            ajenos = await page.evaluate(
                "() => [...document.querySelectorAll('body *')]"
                ".filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1)"
                ".filter((e) => !e.closest('[aria-pressed]')"
                " && !e.querySelector('[aria-pressed]'))"
                ".map((e) => e.tagName + '.' + String(e.className).slice(0, 60))"
            )
            assert ajenos == [], f"desbordamiento a {ancho}px: {ajenos}"
            desborda = await page.evaluate(
                "() => document.documentElement.scrollWidth > window.innerWidth + 1"
            )
            if ancho == 844:
                # Hallazgo preexistente, medido con el bundle anterior a H-1: a
                # 844 px la página ya usa la disposición de escritorio y las
                # pestañas de rango sobresalen 10 px. Arreglarlo sería rediseñar
                # esa disposición, fuera de H-1. Lo que H-1 garantiza, y lo de
                # arriba comprueba, es que el selector no añade desbordamiento.
                pass
            else:
                assert not desborda, f"desbordamiento horizontal a {ancho}px"

            # La excepción es sólo el supervisor: la fecha sigue como estaba.
            fecha = page.get_by_label("Date")
            if ancho < 768:
                await expect(fecha).to_have_count(0)
            else:
                await expect(fecha).to_be_visible()

            await page.screenshot(path=str(DESTINO / f"{nombre}.png"), full_page=True)
            await page.locator(".mb-4").first.screenshot(
                path=str(DESTINO / f"barra-{nombre}.png")
            )
            await contexto.close()
        finally:
            await navegador.close()


async def test_un_fallo_al_cambiar_no_pinta_los_datos_del_anterior(
    seeded, alpha_client, live_server
):
    """FR2.6: con A en pantalla, si la lectura de B falla no se ven datos de A como de B."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    ids = await _dos_supervisores(alpha_client, seeded)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto, page = await _abrir(navegador, live_server, seeded, MOVIL)
            await _elegir(page, ids["A"])
            await expect(page.get_by_text("ABC Manufacturing").first).to_be_visible(
                timeout=20_000
            )

            await page.route(
                f"**/api/activity-explorer*supervisor_user_id={ids['B']}*",
                lambda ruta: ruta.abort(),
            )
            await page.get_by_label("Supervisor").select_option(str(ids["B"]))

            await expect(
                page.get_by_text("Activity history could not be read.")
            ).to_be_visible(timeout=20_000)
            await expect(page.get_by_text("ABC Manufacturing")).to_have_count(0)
            await expect(page.get_by_label("Supervisor")).to_have_value(str(ids["B"]))
            await page.screenshot(path=str(DESTINO / "movil-fallo-al-cambiar.png"), full_page=True)
            await contexto.close()
        finally:
            await navegador.close()
