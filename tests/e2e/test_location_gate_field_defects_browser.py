"""Los tres defectos que la puerta de ubicación tuvo en campo, reproducidos.

Por qué existe este archivo
----------------------------
La primera versión de RTE10-A02 pasó 446 tests y falló en producción. Los tres
defectos son de los que un test de laboratorio no ve si no se le pregunta
exactamente lo que pasa en la calle:

1. **La ubicación del teléfono apagada.** El permiso del sitio sigue
   «concedido» y la Permissions API lo dice; pero `getCurrentPosition` responde
   PERMISSION_DENIED. La puerta se fiaba de la API y no aparecía. Medido en
   producción: el 39 % de las denegaciones reales son así.

2. **La jornada ya abierta.** En campo casi todos tienen jornada abierta. La
   puerta se ocultaba en ese caso para dejar cerrar lo abierto, y el supervisor
   veía la pantalla normal con botones que fallaban, sin ningún
   `Enable Location`.

3. **Acciones encoladas antes del despliegue.** Se enviaban sin la aserción de
   permiso, recibían 403, y la cola —que trata cualquier 4xx como definitivo—
   las BORRABA. Trabajo de campo real perdido por un cambio de versión.

Cada test de aquí falla con la versión anterior. Eso es lo que lo hace valer.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import select

from app.database import async_session_maker
from app.routers_api.worksessions.models import WorkSession
from tests.e2e.conftest import UBICACION_DE_PRUEBA, abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

MOVIL = {"width": 390, "height": 844}

#: Simula la ubicación DEL DISPOSITIVO apagada: el sitio conserva el permiso
#: —la Permissions API dirá `granted`— pero toda petición de posición responde
#: PERMISSION_DENIED, que es lo que hacen Android e iOS con el interruptor de
#: ubicación apagado. Es exactamente el 39 % de las denegaciones de campo.
UBICACION_DEL_TELEFONO_APAGADA = """
(() => {
    const denegar = (exito, error) => setTimeout(() => error && error({
        code: 1, message: 'User denied Geolocation',
        PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3,
    }), 5);
    navigator.geolocation.getCurrentPosition = denegar;
    navigator.geolocation.watchPosition = (exito, error) => { denegar(exito, error); return 0; };
})();
"""

LEER_COLA = """
() => new Promise((resolve, reject) => {
    const r = indexedDB.open('cer-route-offline');
    r.onerror = () => reject(r.error);
    r.onsuccess = () => {
        const db = r.result;
        if (!db.objectStoreNames.contains('pending_actions')) { resolve([]); return; }
        const q = db.transaction('pending_actions', 'readonly')
            .objectStore('pending_actions').getAll();
        q.onsuccess = () => resolve(q.result);
        q.onerror = () => reject(q.error);
    };
})
"""

#: Escribe en la cola una acción como la dejaba el cliente ANTERIOR a
#: RTE10-A02: sin `locationPermission`. Es lo que tenía en el teléfono un
#: supervisor que trabajó sin cobertura mientras se desplegaba la puerta.
ENCOLAR_ACCION_HEREDADA = """
(accion) => new Promise((resolve, reject) => {
    const r = indexedDB.open('cer-route-offline');
    r.onerror = () => reject(r.error);
    r.onsuccess = () => {
        const tx = r.result.transaction('pending_actions', 'readwrite');
        tx.objectStore('pending_actions').put(accion);
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error);
    };
})
"""


@asynccontextmanager
async def _movil(live_server, email: str, *, conceder: bool = True, script: str | None = None):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            opciones: dict = {"base_url": live_server, "viewport": MOVIL}
            if conceder:
                opciones["permissions"] = ["geolocation"]
                opciones["geolocation"] = UBICACION_DE_PRUEBA
            contexto = await navegador.new_context(**opciones)
            if script:
                await contexto.add_init_script(script)
            page = await contexto.new_page()
            await abrir_sesion(page, email, conceder_ubicacion=False)
            yield contexto, page
        finally:
            await navegador.close()


async def _puerta_visible(page):
    await expect(page.get_by_role("heading", name="Location Required")).to_be_visible(
        timeout=20_000
    )


async def _abrir_jornada(page):
    await page.goto("/route")
    await expect(page.get_by_role("button", name="Start Work")).to_be_visible(
        timeout=20_000
    )
    await page.get_by_role("button", name="Start Work").click()
    await expect(page.get_by_text("What's next?")).to_be_visible(timeout=20_000)


# ── Defecto 1 · La ubicación del teléfono apagada ───────────────────────────


async def test_la_ubicacion_del_telefono_apagada_muestra_la_puerta(
    seeded, alpha_client, live_server
):
    """El caso que se reportó en campo: «cuando la ubicación no está activada».

    El sitio tiene el permiso concedido, así que la Permissions API dice
    `granted`. Pero el teléfono tiene la ubicación apagada y no entrega ningún
    punto. La primera versión se fiaba de la API y dejaba pasar.
    """
    async with _movil(
        live_server,
        seeded.alpha.users["supervisor"].email,
        conceder=True,
        script=UBICACION_DEL_TELEFONO_APAGADA,
    ) as (_c, page):
        estado = await page.evaluate(
            "async () => (await navigator.permissions.query({name:'geolocation'})).state"
        )
        assert estado == "granted", (
            "la preparación no reproduce el caso: la API debía decir granted"
        )

        await page.goto("/route")
        await _puerta_visible(page)
        await expect(page.get_by_role("button", name="Start Work")).to_have_count(0)


async def test_sin_senal_con_el_telefono_encendido_sigue_sin_bloquear(
    seeded, alpha_client, live_server
):
    """El control del defecto 1: verificar con el GPS no puede cerrar el paso
    por falta de señal. §2.2 lo prohíbe, y es el riesgo de la corrección.

    Permiso concedido, ubicación del teléfono encendida, ningún punto
    disponible: `getCurrentPosition` responde POSITION_UNAVAILABLE (2), no
    PERMISSION_DENIED (1). Eso es una nave industrial, y no se bloquea.
    """
    sin_senal = """
    (() => {
        navigator.geolocation.getCurrentPosition = (ok, err) => setTimeout(() => err && err({
            code: 2, message: 'Position unavailable',
            PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3,
        }), 5);
    })();
    """
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=True, script=sin_senal
    ) as (_c, page):
        await page.goto("/route")
        await expect(page.get_by_role("button", name="Start Work")).to_be_visible(
            timeout=20_000
        )
        await expect(page.get_by_role("heading", name="Location Required")).to_have_count(0)


# ── Defecto 2 · La jornada ya abierta ───────────────────────────────────────


async def test_con_jornada_abierta_la_puerta_aparece_y_solo_queda_cerrar(
    seeded, alpha_client, live_server
):
    """La situación normal en campo: jornada abierta, y el permiso se pierde.

    Antes: pantalla normal, «What's next?» con sus siete opciones, y cada una
    fallaba al pulsarla. Ahora: la puerta encima, `Enable Location` disponible,
    las opciones retiradas y `End Work` todavía ahí — porque terminar el día es
    un cierre, y §8 lo exige.
    """
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=True
    ) as (contexto, page):
        await _abrir_jornada(page)

        await contexto.clear_permissions()
        await page.reload()

        await _puerta_visible(page)
        await expect(page.get_by_role("button", name="Enable Location")).to_be_visible()
        await expect(page.get_by_text("What's next?")).to_have_count(0)
        await expect(page.get_by_role("button", name="Field task")).to_have_count(0)
        await expect(page.get_by_role("button", name="End Work")).to_be_visible()


async def test_conceder_el_permiso_devuelve_la_pantalla_completa(
    seeded, alpha_client, live_server
):
    """Y al recuperarlo, todo vuelve solo: sin botón de reintentar (§5.1)."""
    async with _movil(
        live_server, seeded.alpha.users["supervisor"].email, conceder=True
    ) as (contexto, page):
        await _abrir_jornada(page)
        await contexto.clear_permissions()
        await page.reload()
        await _puerta_visible(page)

        await contexto.grant_permissions(["geolocation"])
        await contexto.set_geolocation(UBICACION_DE_PRUEBA)
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

        await expect(page.get_by_text("What's next?")).to_be_visible(timeout=20_000)
        await expect(page.get_by_role("heading", name="Location Required")).to_have_count(0)


# ── Defecto 3 · Las acciones encoladas antes del despliegue ─────────────────


async def test_una_accion_encolada_antes_del_despliegue_no_se_pierde(
    seeded, alpha_client, live_server
):
    """La pérdida de datos: el defecto más grave de los tres.

    Una acción que el cliente anterior encoló sin cobertura llega sin aserción
    de permiso. El servidor la rechaza con 403 y —antes de la corrección— la
    cola la trataba como definitiva y la BORRABA. Aquí se coloca una en la cola
    tal como la dejaba el cliente viejo y se comprueba que sobrevive al rechazo
    y se aplica cuando el permiso vuelve.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email, conceder=False) as (contexto, page):
        await page.goto("/route")
        await _puerta_visible(page)

        heredada = {
            "id": "accion-heredada-de-antes-de-rte10-a02",
            "sequence": 1,
            "endpoint": "/worksessions",
            "method": "POST",
            "payload": {},
            "kind": "worksession.start",
            "createdAt": "2026-10-07T09:00:00.000Z",
            "status": "pending",
            # SIN `locationPermission`: es lo que la hace heredada.
        }
        await page.evaluate(ENCOLAR_ACCION_HEREDADA, heredada)

        # Vaciar la cola sin permiso: el servidor la rechaza.
        await page.reload()
        await _puerta_visible(page)
        await page.wait_for_timeout(3_000)

        cola = await page.evaluate(LEER_COLA)
        ids = [a["id"] for a in cola]
        assert heredada["id"] in ids, (
            "la acción heredada se BORRÓ al ser rechazada por falta de permiso: "
            f"trabajo de campo perdido. Cola: {json.dumps(cola)[:300]}"
        )

        async with async_session_maker() as session:
            jornadas = (
                await session.scalars(
                    select(WorkSession.id).where(WorkSession.user_id == supervisor.id)
                )
            ).all()
        assert jornadas == [], "sin permiso no debía aplicarse"

        # Vuelve el permiso: la acción se aplica y sale de la cola.
        await contexto.grant_permissions(["geolocation"])
        await contexto.set_geolocation(UBICACION_DE_PRUEBA)
        await page.reload()
        await expect(page.get_by_text("What's next?")).to_be_visible(timeout=30_000)

        cola = await page.evaluate(LEER_COLA)
        assert heredada["id"] not in [a["id"] for a in cola], (
            "con el permiso de vuelta la acción debía enviarse y salir de la cola"
        )
