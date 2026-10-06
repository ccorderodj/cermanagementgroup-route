"""Activity Explorer en un navegador real: escritorio y móvil, contra V0.7.

Qué se valida aquí y qué no
----------------------------
No la exactitud de los datos —eso tiene sus propios tests de integración contra
PostgreSQL— sino la **fidelidad de la experiencia aprobada**: que la jerarquía
se recorra con las pestañas de rango y las filas que bajan un nivel, que las
etiquetas y el orden sean los del mockup, y que el móvil haga lo que el mockup
dice que haga.

Sin `data-testid`
-----------------
Como el resto de la suite de navegador, y no por estilo: el build de producción
los **elimina** de los `.tsx` (`isTsx && isProd` en `buildBabelLoader`), así que
un test que los buscara fallaría contra el bundle que se despliega. Se localiza
por rol y texto visible, que además es lo que ve el usuario.

Los filtros del móvil
----------------------
El mockup oculta el selector de supervisor y la fecha en móvil para **esta**
pantalla (`.app.device-mobile .fields-inline { display: none }`), y los deja en
Reports. Un test comprueba justamente eso, porque es la clase de detalle que se
"arregla" sin darse cuenta y rompe fidelidad.
"""

from __future__ import annotations

from datetime import date

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}

RUTA = "/admin/route/activity"

#: El día de negocio que la preparación coloca, y el que los tests piden.
DIA = date(2026, 9, 18)

FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def _valores(cliente, company_id: int, lista: str):
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()
    return (await cliente.get(f"/api/standard-values/{lista}")).json()


async def _historia(alpha_client, seeded, *, unidad: str) -> None:
    """Un supervisor con una parada completa en un día de negocio conocido.

    Pasa por las guardas reales del producto: odómetro resuelto, viaje
    planificado, salida, llegada, bloque de actividad y cierre. Después se
    coloca el `session_date` en el día que los tests piden, porque ese campo se
    calcula al abrir la jornada y no se puede pedir por API.
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

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "100000.0"},
    )
    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": "ABC Manufacturing"},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    actividades = await _valores(
        alpha_client, seeded.alpha.id, "client_visit_activities"
    )
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": [v["id"] for v in actividades[:2]]},
    )
    resultados = await _valores(alpha_client, seeded.alpha.id, "outcomes")
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={
            "action": "complete",
            "outcome_id": resultados[0]["id"],
            "notes": "Requested 4 additional workers",
        },
    )

    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE work_session SET session_date = :d WHERE id = :i"),
            {"d": DIA, "i": jornada["id"]},
        )
        await session.commit()


async def _sin_desborde(page) -> bool:
    return not await page.evaluate(
        "() => document.documentElement.scrollWidth > window.innerWidth + 1"
    )


async def _abrir(contexto, seeded, *, rango: str = "year"):
    """Abre el explorador y deja el rango pedido activo, por la interfaz."""
    page = await contexto.new_page()
    await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
    await page.goto(RUTA)
    await expect(page.get_by_role("heading", name="Activity", exact=True)).to_have_count(
        1, timeout=20_000
    )
    if rango != "day":
        await page.get_by_role("button", name=rango.capitalize(), exact=True).click()
    return page


# ── Escritorio ──────────────────────────────────────────────────────────────


async def test_la_raiz_de_escritorio_es_la_aprobada(seeded, alpha_client, live_server):
    """Título, subtítulo, acción y los cuatro rangos del mockup.

    La terminología se comprueba por su texto visible porque **es del
    producto**: §17 prohíbe cambiarla porque otra palabra parezca más clara, así
    que verificarla es verificar fidelidad.
    """
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-D1")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir(contexto, seeded, rango="day")

            await expect(
                page.get_by_text("Explore operational history by supervisor and period")
            ).to_have_count(1)
            await expect(
                page.get_by_role("link", name="Back to Today")
            ).to_have_count(1)

            # Los cuatro rangos, en el orden de la línea base.
            for etiqueta in ("Day", "Week", "Month", "Year"):
                await expect(
                    page.get_by_role("button", name=etiqueta, exact=True)
                ).to_have_count(1)

            # Los dos filtros de V0.7, y ninguno más.
            await expect(page.get_by_label("Supervisor")).to_have_count(1)
            await expect(page.get_by_label("Date")).to_have_count(1)

            assert await _sin_desborde(page), "el escritorio desborda en horizontal"
        finally:
            await navegador.close()


async def test_la_jerarquia_completa_se_recorre_bajando_nivel(
    seeded, alpha_client, live_server,
):
    """`Year → Month → Week → Day → Activity`, por el mecanismo del mockup.

    No es un acordeón: cada fila de grupo es un **botón** que baja un nivel, y
    el pie de la fila dice a dónde lleva (`View month`, `View week`,
    `View day`). Esto recorre los cuatro niveles y acaba en la tarjeta de la
    parada, que es la hoja de la jerarquía.
    """
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-D2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir(contexto, seeded, rango="day")

            # La fecha se mueve al día de la historia preparada.
            await page.get_by_label("Date").fill(DIA.isoformat())
            await page.get_by_role("button", name="Year", exact=True).click()

            # Año: agrupa por mes y la fila ofrece bajar a mes.
            await expect(page.get_by_text("2026", exact=True)).to_have_count(1, timeout=15_000)
            await expect(page.get_by_text("Grouped by month")).to_have_count(1)
            fila_mes = page.get_by_role("button").filter(has_text="View month")
            await expect(fila_mes).to_have_count(1)
            await expect(page.get_by_text("September", exact=True)).to_have_count(1)
            await fila_mes.click()

            # Mes: agrupa por semana.
            await expect(page.get_by_text("September 2026")).to_have_count(1, timeout=15_000)
            await expect(page.get_by_text("Grouped by week")).to_have_count(1)
            fila_semana = page.get_by_role("button").filter(has_text="View week")
            await expect(fila_semana).to_have_count(1)
            # La semana del 18 de septiembre de 2026 es la del lunes 14.
            await expect(page.get_by_text("Sep 14–20", exact=True)).to_have_count(1)
            await fila_semana.click()

            # Semana: agrupa por día.
            await expect(page.get_by_text("Grouped by day")).to_have_count(1, timeout=15_000)
            fila_dia = page.get_by_role("button").filter(has_text="View day")
            await expect(fila_dia).to_have_count(1)
            await expect(page.get_by_text("Fri Sep 18", exact=True)).to_have_count(1)
            await fila_dia.click()

            # Día: la hoja. Resumen y tarjeta de parada.
            await expect(page.get_by_text("activity time")).to_have_count(1, timeout=15_000)
            await expect(page.get_by_text("estimated fuel")).to_have_count(1)
            await expect(
                page.get_by_role("heading", name="Client Visit", exact=True)
            ).to_have_count(1)
            await expect(page.get_by_text("ABC Manufacturing")).to_have_count(1)

            assert await _sin_desborde(page), "el escritorio desborda tras bajar"
        finally:
            await navegador.close()


async def test_la_tarjeta_de_parada_tiene_las_lineas_de_la_linea_base(
    seeded, alpha_client, live_server,
):
    """`Travel`, `At destination`, `Reason`, `Outcome` y `Note`.

    Y las dos actividades seleccionadas aparecen en **una** tarjeta: un bloque
    de ejecución es un hecho histórico, y partirlo en dos fabricaría dos
    visitas donde hubo una (PR-03).
    """
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-D3")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir(contexto, seeded, rango="day")
            await page.get_by_label("Date").fill(DIA.isoformat())

            await expect(
                page.get_by_role("heading", name="Client Visit", exact=True)
            ).to_have_count(1, timeout=15_000)

            for linea in ("Travel", "At destination", "Reason", "Outcome", "Note"):
                await expect(page.get_by_text(linea, exact=True)).to_have_count(1)

            await expect(page.get_by_text("activity span · trip miles")).to_have_count(1)
            await expect(
                page.get_by_text("Requested 4 additional workers")
            ).to_have_count(1)

            # Una sola tarjeta para las dos actividades de la misma parada.
            await expect(
                page.get_by_role("heading", name="Client Visit", exact=True)
            ).to_have_count(1)
        finally:
            await navegador.close()


async def test_un_periodo_sin_registros_lo_dice_en_vez_de_inventar(
    seeded, alpha_client, live_server,
):
    """FR-08: no hay datos es un estado, no una fila de ceros."""
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-D4")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir(contexto, seeded, rango="day")
            await page.get_by_label("Date").fill("2019-05-05")

            await expect(
                page.get_by_text("No recorded activity on this day.")
            ).to_have_count(1, timeout=15_000)

            await page.get_by_role("button", name="Year", exact=True).click()
            await expect(
                page.get_by_text("No recorded activity in this period.")
            ).to_have_count(1, timeout=15_000)
            await expect(page.get_by_text("0 groups")).to_have_count(1)
        finally:
            await navegador.close()


async def test_un_fallo_de_lectura_no_se_presenta_como_un_periodo_vacio(
    seeded, alpha_client, live_server,
):
    """FR-09: un error de red no es "ese año no tuvo actividad".

    Es la afirmación que separa un explorador histórico honesto de uno que
    miente por omisión: si una lectura fallida se dibujara como un periodo
    vacío, quien mira concluiría que no se trabajó.
    """
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-D5")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            async def responder_mal(route):
                await route.fulfill(
                    status=500, content_type="application/json",
                    body='{"detail":"caida simulada"}',
                )

            await page.route("**/api/activity-explorer*", responder_mal)
            await page.goto(RUTA)

            await expect(
                page.get_by_text("Activity history could not be read. It will retry on its own.")
            ).to_have_count(1, timeout=20_000)
            await expect(
                page.get_by_text("No recorded activity on this day.")
            ).to_have_count(0)
            await expect(page.get_by_text("0 groups")).to_have_count(0)
        finally:
            await navegador.close()


async def test_sin_la_capacidad_la_pagina_no_se_sirve(seeded, alpha_client, live_server):
    """La puerta está en el servidor, no en el menú.

    Un supervisor que escriba la URL no entra. Ocultar el enlace es experiencia
    de usuario; el control es la dependencia de la ruta.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)
            respuesta = await page.goto(RUTA)

            assert respuesta is not None and respuesta.status in (401, 403, 404), (
                f"la página se sirvió con estado {respuesta and respuesta.status}"
            )
        finally:
            await navegador.close()


# ── Móvil ───────────────────────────────────────────────────────────────────


async def test_el_movil_mantiene_la_jerarquia_y_oculta_los_campos(
    seeded, alpha_client, live_server,
):
    """La misma jerarquía y la misma información; sin los dos campos.

    Es lo que dice el ámbito móvil del mockup para esta pantalla:
    `.fields-inline { display: none }`. Las pestañas de rango **sí** quedan,
    así que la jerarquía se recorre completa con el dedo.
    """
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-M1")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await _abrir(contexto, seeded, rango="day")

            # Los campos no se dibujan, como en la línea base.
            await expect(page.get_by_label("Supervisor")).to_have_count(0)
            await expect(page.get_by_label("Date")).to_have_count(0)
            # Y las pestañas sí.
            for etiqueta in ("Day", "Week", "Month", "Year"):
                await expect(
                    page.get_by_role("button", name=etiqueta, exact=True)
                ).to_have_count(1)

            assert await _sin_desborde(page), "el móvil desborda en horizontal"
        finally:
            await navegador.close()


async def test_el_movil_recorre_la_jerarquia_y_llega_a_la_parada(
    seeded, alpha_client, live_server,
):
    """Año → mes → semana → día → parada, con la misma interacción táctil.

    No hay dependencia de nada que sólo exista en escritorio: las filas de
    grupo son botones y el detalle es la misma tarjeta, reflujada a dos
    columnas como hace el mockup.
    """
    from playwright.async_api import async_playwright

    await _historia(alpha_client, seeded, unidad="V-RTE08-M2")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await _abrir(contexto, seeded, rango="year")

            await expect(page.get_by_text("Grouped by month")).to_have_count(
                1, timeout=20_000
            )
            await page.get_by_role("button").filter(has_text="View month").click()
            await expect(page.get_by_text("Grouped by week")).to_have_count(
                1, timeout=15_000
            )
            await page.get_by_role("button").filter(has_text="View week").click()
            await expect(page.get_by_text("Grouped by day")).to_have_count(
                1, timeout=15_000
            )
            await page.get_by_role("button").filter(has_text="View day").click()

            await expect(
                page.get_by_role("heading", name="Client Visit", exact=True)
            ).to_have_count(1, timeout=15_000)
            await expect(page.get_by_text("At destination", exact=True)).to_have_count(1)
            assert await _sin_desborde(page), "el móvil desborda en el detalle"
        finally:
            await navegador.close()
