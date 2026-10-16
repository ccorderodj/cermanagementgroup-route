"""Today / Live: la frescura y el fallo de relectura, en un navegador real.

Qué cierra este archivo
------------------------
El reporte 001 dejó cuatro comportamientos como «implementados pero sin
evidencia propia»: el refresco automático, el fallo de relectura que no vacía
la pantalla, la pausa con la pestaña oculta y la relectura inmediata al volver.
Estaban escritos y eran revisables; no estaban **medidos**. Aquí se miden.

Por qué se esperan los treinta segundos de verdad
--------------------------------------------------
El intervalo del producto es `INTERVALO_DE_REFRESCO_MS = 30_000`. Acortarlo
para que el test corriera antes sería cambiar comportamiento visible del
producto para comodidad de la prueba, que es justo lo que §7 de la instrucción
prohíbe. Así que estos tests esperan el turno real. Cuestan minuto y medio
entre todos, y lo que compran es que la afirmación «se refresca cada treinta
segundos» venga de haberlo visto ocurrir.

Cómo se esconde la pestaña, y qué se midió antes de elegirlo
-------------------------------------------------------------
Un navegador sin ventana no tiene pestaña que pasar a segundo plano, así que
hubo que buscar el mecanismo. Se probaron cuatro sobre este mismo arnés
(Edge headless por CDP):

    1. abrir una segunda pestaña en el contexto  -> la primera sigue `visible`
    2. CDP `Page.setWebLifecycleState: frozen`   -> sigue `visible`, sin evento
    3. CDP `Emulation.setPageVisibilityOverride` -> **retirado del protocolo**
    4. redefinir el getter + despachar el evento -> `hidden`, y el oyente corre

Se usa el cuarto porque es el único que funciona aquí. Lo que se simula es
**la señal del navegador**, no el producto: el `visibilitychange` es un evento
real, lo recibe el oyente que registra la página, ese oyente lee el
`document.visibilityState` real y llama a su `clearInterval` y su
`setInterval` de verdad. Nada del componente está sustituido, que es lo que
FC-03 pide cuando dice «no una aserción simulada desconectada del ciclo de
vida de la página».
"""

from __future__ import annotations

import asyncio

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

ESCRITORIO = {"width": 1280, "height": 900}
RUTA = "/admin/route/today"

#: El intervalo del producto, más margen para la petición y el render. No se
#: toca el del producto: se espera el suyo.
ESPERA_DE_UN_TURNO_MS = 45_000

#: Lo que tarda en verse una relectura **inmediata**. Es deliberadamente mucho
#: menor que el intervalo: si la aserción pasara con 30 s no distinguiría
#: «refrescó al volver» de «le tocaba el turno».
ESPERA_INMEDIATA_MS = 10_000

#: Un PNG de 1×1: la evidencia de odómetro no es lo que se prueba aquí.
FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

OCULTAR = """() => {
    Object.defineProperty(document, 'visibilityState',
        {configurable: true, get: () => 'hidden'});
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
    document.dispatchEvent(new Event('visibilitychange'));
}"""

MOSTRAR = """() => {
    Object.defineProperty(document, 'visibilityState',
        {configurable: true, get: () => 'visible'});
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});
    document.dispatchEvent(new Event('visibilitychange'));
}"""


def _estado_en_la_tabla(page, etiqueta: str):
    """La celda de estado de la fila, no cualquier texto de la pantalla.

    El escritorio enseña el estado **dos veces**: en la fila de la tabla y en
    el panel lateral del supervisor seleccionado. Buscar el texto suelto
    encontraba las dos y la aserción de cantidad fallaba por un defecto del
    test, no del producto. Se localiza la celda, que además es lo que V0.7
    llama la columna `Status`.
    """
    return page.get_by_role("cell", name=etiqueta, exact=True)


async def _supervisor_trabajando(alpha_client, seeded, unidad: str) -> dict:
    """Supervisor con vehículo y jornada abierta: el estado `Working`."""
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
    return jornada


async def _ponerse_en_ruta(alpha_client, seeded, jornada_id: int) -> None:
    """Lleva al supervisor de `Working` a `On Route`, por el camino del producto.

    Odómetro de inicio resuelto y viaje arrancado: son las guardas reales de
    RTE04, y saltárselas produciría un estado que el producto no alcanza.
    """
    from app.database import async_session_maker
    from app.routers_api.standardvalues.provisioning import provision_standard_values

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada_id}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada_id}/start/confirm",
        json={"reading": "100000.0"},
    )

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()
    valores = (await alpha_client.get("/api/standard-values/office_purposes")).json()
    assert valores, "no se sembró ningún propósito de oficina"
    valor = valores[0]["id"]

    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "office", "context_reference": "Acme",
                  "standard_value_id": valor},
        )
    ).json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text


async def _abrir_today_live(contexto, seeded):
    """Deja Today / Live cargado con datos reales y devuelve la página."""
    page = await contexto.new_page()
    await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
    await page.goto(RUTA)
    await expect(
        page.get_by_role("heading", name="Today / Live")
    ).to_have_count(1, timeout=20_000)
    # Hasta que no hay una fila no hay "estado conocido" del que hablar.
    await expect(_estado_en_la_tabla(page, "Working")).to_have_count(
        1, timeout=20_000
    )
    return page


# ── FC-01 — El refresco automático refleja un cambio real ──────────────────


async def test_el_refresco_automatico_refleja_un_cambio_real(
    seeded, alpha_client, live_server,
):
    """Cambia el dominio con la página abierta, y la página se entera sola.

    Lo que se afirma no es que un temporizador se disparó: es que la pantalla
    enseñaba `Working`, que el supervisor se puso en ruta por el camino normal
    del producto, y que la pantalla pasó a `On Route` **sin que nadie
    recargara**. Lo de «sin recargar» se comprueba con una marca puesta en
    `window` antes del cambio: si hubiera habido navegación, no sobreviviría.
    """
    from playwright.async_api import async_playwright

    jornada = await _supervisor_trabajando(alpha_client, seeded, "V-FRESH-01")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir_today_live(contexto, seeded)

            await page.evaluate("() => { window.__sinRecarga = true; }")

            await _ponerse_en_ruta(alpha_client, seeded, jornada["id"])

            await expect(_estado_en_la_tabla(page, "On Route")).to_have_count(
                1, timeout=ESPERA_DE_UN_TURNO_MS
            )
            await expect(_estado_en_la_tabla(page, "Working")).to_have_count(0)

            assert await page.evaluate("() => window.__sinRecarga === true"), (
                "la página se recargó: el cambio no lo trajo el refresco"
            )
        finally:
            await navegador.close()


# ── FC-02 — Un fallo de relectura conserva lo último cierto ─────────────────


async def test_un_fallo_de_relectura_conserva_el_ultimo_estado_cierto(
    seeded, alpha_client, live_server,
):
    """Un error de red no es "el supervisor no está trabajando".

    Es la afirmación de FR-10 y el riesgo real de un panel operativo: si una
    lectura fallida se dibujara como `Not started` o como `0 miles`, quien mira
    tomaría una decisión sobre un hecho que nadie ha observado. Aquí la
    relectura falla de verdad —se interceptan las peticiones y se responden
    500— y se comprueba lo que queda en pantalla.
    """
    from playwright.async_api import async_playwright

    await _supervisor_trabajando(alpha_client, seeded, "V-FRESH-02")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir_today_live(contexto, seeded)

            # El estado cierto que la pantalla ya enseña, antes de romper nada.
            fila_antes = await page.get_by_role("row").count()
            assert fila_antes >= 2, "hace falta una fila real para medir que se conserva"

            async def responder_mal(route):
                await route.fulfill(status=500, content_type="application/json",
                                    body='{"detail":"caida simulada"}')

            await page.route("**/api/live/today", responder_mal)

            # El aviso recuperable de la línea base, tras el turno de refresco.
            await expect(
                page.get_by_text("Could not refresh just now. Showing the last known state.")
            ).to_have_count(1, timeout=ESPERA_DE_UN_TURNO_MS)

            # Y lo que NO puede haber pasado.
            await expect(_estado_en_la_tabla(page, "Working")).to_have_count(1)
            await expect(_estado_en_la_tabla(page, "Not started")).to_have_count(0)
            await expect(
                page.get_by_text("Today / Live could not be read. It will retry on its own.")
            ).to_have_count(0)
            assert await page.get_by_role("row").count() == fila_antes, (
                "la lista se vació con una relectura fallida"
            )
            assert await page.get_by_role("heading", name="Supervisors", exact=True).count() == 1

            # Y se recupera sola en el turno siguiente, sin intervención.
            await page.unroute("**/api/live/today", responder_mal)
            await expect(
                page.get_by_text("Could not refresh just now. Showing the last known state.")
            ).to_have_count(0, timeout=ESPERA_DE_UN_TURNO_MS)
            await expect(_estado_en_la_tabla(page, "Working")).to_have_count(1)
        finally:
            await navegador.close()


# ── FC-03 — Con la pestaña oculta no se sigue trabajando ───────────────────


async def test_con_la_pestana_oculta_el_sondeo_se_detiene(
    seeded, alpha_client, live_server,
):
    """Oculta, la página no pide nada. Contado sobre la red, no supuesto.

    Se cuentan las peticiones a `/api/live/today` durante algo más de un turno
    completo con la pestaña oculta. Si el sondeo siguiera corriendo habría al
    menos una; la aserción es que hay **cero**.
    """
    from playwright.async_api import async_playwright

    await _supervisor_trabajando(alpha_client, seeded, "V-FRESH-03")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir_today_live(contexto, seeded)

            lecturas: list[str] = []
            page.on(
                "request",
                lambda peticion: (
                    lecturas.append(peticion.url)
                    if "/api/live/today" in peticion.url else None
                ),
            )

            await page.evaluate(OCULTAR)
            assert await page.evaluate("() => document.visibilityState") == "hidden"

            # Un turno completo y algo más: con el sondeo vivo, aquí caben dos.
            await asyncio.sleep(35)

            assert lecturas == [], (
                f"la pestaña oculta siguió leyendo {len(lecturas)} veces: {lecturas}"
            )

            # Control positivo, y no es un adorno: una aserción de "cero
            # peticiones" pasa igual de verde si el contador nunca estuvo
            # conectado. Al volver al frente tiene que registrar, y si no
            # registra entonces el cero de arriba no significaba nada.
            await page.evaluate(MOSTRAR)
            await expect(_estado_en_la_tabla(page, "Working")).to_have_count(
                1, timeout=ESPERA_INMEDIATA_MS
            )
            assert lecturas, (
                "el contador no registró ni la relectura de volver al frente: "
                "el cero de la pestaña oculta no demuestra nada"
            )
        finally:
            await navegador.close()


# ── FC-04 — Al volver al frente se relee de inmediato ──────────────────────


async def test_al_volver_al_frente_se_relee_de_inmediato(
    seeded, alpha_client, live_server,
):
    """Volver a mirar la pantalla enseña algo actual, no algo viejo.

    El cambio de estado ocurre **mientras la pestaña está oculta**, que es el
    caso que importa: al volver, la página no puede esperar hasta medio minuto
    para dejar de mentir. La aserción usa una espera deliberadamente corta
    —10 s frente a los 30 del intervalo— porque con 30 no distinguiría una
    relectura inmediata de que simplemente le tocaba el turno.
    """
    from playwright.async_api import async_playwright

    jornada = await _supervisor_trabajando(alpha_client, seeded, "V-FRESH-04")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir_today_live(contexto, seeded)

            await page.evaluate(OCULTAR)
            assert await page.evaluate("() => document.visibilityState") == "hidden"

            await _ponerse_en_ruta(alpha_client, seeded, jornada["id"])

            # Oculta, la pantalla sigue enseñando lo último que supo. Que es lo
            # correcto: no ha podido observar nada nuevo.
            await expect(_estado_en_la_tabla(page, "Working")).to_have_count(1)

            await page.evaluate(MOSTRAR)

            await expect(_estado_en_la_tabla(page, "On Route")).to_have_count(
                1, timeout=ESPERA_INMEDIATA_MS
            )
        finally:
            await navegador.close()
