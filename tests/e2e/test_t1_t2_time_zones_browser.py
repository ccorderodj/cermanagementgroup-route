"""T-1/T-2 en el navegador: la hora del supervisor no depende de quién mira.

La validación decisiva de las instrucciones (§11): el mismo evento, visto desde
dos navegadores en zonas distintas, tiene que mostrar **la misma hora
operativa del supervisor**. Antes cada administrador veía la hora de su propio
navegador: el mismo `Start Trip` eran las 2:41 PM en Georgia y las 1:41 PM en
Texas.

Lo que se comprueba
-------------------
* Today, escritorio y móvil, con el navegador en el Este y en el Centro.
* User Activity, la tarjeta de la parada, en las dos zonas.
* Que la abreviatura de zona aparece **sólo** donde hace falta: en el navegador
  cuya zona no coincide con la de la jornada.
* El campo opcional del panel de supervisores: automático por defecto, y un
  override que se guarda.

La hora esperada se calcula aquí con `zoneinfo` a partir del instante que
devuelve el API, así que la prueba no depende de la hora a la que se ejecute
ni de si es horario de verano.

Las capturas van a `var/screenshots/t1-t2/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/t1-t2")
ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}
ESTE = "America/New_York"
CENTRO = "America/Chicago"


def _reloj(instante: datetime, zona: str) -> str:
    """`2:41 PM`, como lo escribe `Intl` en `en-US`."""
    local = instante.astimezone(ZoneInfo(zona))
    hora = local.hour % 12 or 12
    return f"{hora}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


async def _supervisor_en_ruta(alpha_client, seeded) -> dict:
    """Un supervisor del Este, en ruta, con su jornada y su viaje registrados."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
    )
    assert respuesta.status_code in (200, 201), respuesta.text

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (
        await alpha_client.post(
            "/api/worksessions",
            json={
                "time_zone": ESTE,
                "device_captured_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=20)
                ).isoformat(),
            },
        )
    ).json()
    assert jornada["start_time_zone"] == ESTE
    viaje = (await alpha_client.post("/api/trips", json={"purpose": "home"})).json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    hoy = (await alpha_client.get("/api/live/today")).json()
    fila = next(
        s for s in hoy["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["status"] == "route"
    return {"jornada": jornada, "fila": fila}


async def test_today_muestra_la_misma_hora_desde_el_este_y_el_centro(
    seeded, alpha_client, live_server
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    datos = await _supervisor_en_ruta(alpha_client, seeded)
    desde = datetime.fromisoformat(datos["fila"]["since"])
    esperada = _reloj(desde, ESTE)
    abreviatura = desde.astimezone(ZoneInfo(ESTE)).tzname()
    nombre = datos["fila"]["name"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            vistas: dict[str, str] = {}
            anchos: dict[str, int] = {}
            for zona_del_navegador, viewport, sufijo in (
                (ESTE, ESCRITORIO, "escritorio-este"),
                (CENTRO, ESCRITORIO, "escritorio-centro"),
                (CENTRO, MOVIL, "movil-centro"),
            ):
                contexto = await navegador.new_context(
                    base_url=live_server,
                    viewport=viewport,
                    timezone_id=zona_del_navegador,
                )
                page = await contexto.new_page()
                await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
                await page.goto("/admin/route/today")

                fila = (
                    page.locator("tr", has_text=nombre)
                    if viewport is ESCRITORIO
                    else page.get_by_role("button", name=nombre).first
                )
                await expect(fila.get_by_text(esperada).first).to_be_visible(
                    timeout=20_000
                )
                await page.screenshot(
                    path=str(DESTINO / f"today-{sufijo}.png"), full_page=True
                )
                if viewport is ESCRITORIO:
                    # El ancho que ocupa la tabla. La primera versión ponía la
                    # zona en la misma línea que la hora y la ensanchaba: `EDT`
                    # quedaba cortado contra el borde.
                    anchos[sufijo] = await fila.evaluate(
                        "(el) => el.closest('.overflow-x-auto').scrollWidth"
                    )
                vistas[sufijo] = await fila.inner_text()
                await contexto.close()

            # La misma hora en las tres vistas: la del supervisor.
            assert all(esperada in texto for texto in vistas.values()), vistas
            # La abreviatura sólo donde hace falta: el navegador del Centro.
            assert abreviatura not in vistas["escritorio-este"], vistas
            assert abreviatura in vistas["escritorio-centro"], vistas
            assert abreviatura in vistas["movil-centro"], vistas
            # Mostrar la zona no puede ensanchar la tabla: con ella (Centro)
            # ocupa lo mismo que sin ella (Este). Que la tabla ya desborde unos
            # píxeles a 1280 con este contenido es anterior a T-1/T-2 y está en
            # el reporte; lo que se defiende aquí es no empeorarlo.
            assert anchos["escritorio-centro"] <= anchos["escritorio-este"] + 1, anchos
        finally:
            await navegador.close()


async def test_user_activity_muestra_la_misma_hora_desde_el_este_y_el_centro(
    seeded, alpha_client, live_server
):
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    datos = await _supervisor_en_ruta(alpha_client, seeded)
    vista = (
        await alpha_client.get(
            "/api/activity-explorer",
            params={"supervisor_user_id": seeded.alpha.users["supervisor"].id},
        )
    ).json()
    parada = vista["activities"][0]
    assert parada["time_zone"] == ESTE
    esperada = _reloj(datetime.fromisoformat(parada["trip_started_at"]), ESTE)

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            textos: dict[str, str] = {}
            for zona_del_navegador in (ESTE, CENTRO):
                contexto = await navegador.new_context(
                    base_url=live_server,
                    viewport=ESCRITORIO,
                    timezone_id=zona_del_navegador,
                )
                page = await contexto.new_page()
                await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
                await page.goto("/admin/route/activity")
                tarjeta = page.get_by_role("heading", name="Home", exact=True).first
                await expect(tarjeta).to_be_visible(timeout=20_000)
                await expect(page.get_by_text(esperada).first).to_be_visible(
                    timeout=20_000
                )
                nombre = zona_del_navegador.split("/")[-1].lower()
                await page.screenshot(
                    path=str(DESTINO / f"user-activity-{nombre}.png"), full_page=True
                )
                textos[zona_del_navegador] = await page.inner_text("body")
                await contexto.close()

            assert esperada in textos[ESTE] and esperada in textos[CENTRO]
        finally:
            await navegador.close()


async def test_el_panel_ofrece_la_zona_opcional_y_guarda_el_override(
    seeded, alpha_client, live_server
):
    """Automática por defecto; fijarla es una excepción explícita que se guarda."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    nombre = f"{perfil['first_name']} {perfil['last_name']}"

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/supervisors")

            fila = page.locator("tr", has_text=nombre)
            selector = fila.get_by_role("combobox", name="Time zone")
            await expect(selector).to_have_text("Time zone: automatic", timeout=20_000)
            await page.screenshot(
                path=str(DESTINO / "panel-automatica.png"), full_page=True
            )

            await selector.click()
            await page.get_by_role("option", name=CENTRO).click()
            await expect(selector).to_have_text(CENTRO, timeout=20_000)
            await page.screenshot(
                path=str(DESTINO / "panel-override.png"), full_page=True
            )
        finally:
            await navegador.close()

    candidatos = (await alpha_client.get("/api/supervisors/candidates")).json()
    guardado = next(
        c for c in candidatos if c["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert guardado["supervisor_time_zone"] == CENTRO
