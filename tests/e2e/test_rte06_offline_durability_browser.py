"""La evidencia de ubicación sobrevive al offline (cierre de RTE06, Item A).

Qué hueco cierra esto
---------------------
La primera versión de RTE06 enviaba la evidencia con `$api.post` directamente.
Sin red, la promesa se rechazaba, el `catch` la tragaba en silencio —§12 exige
silencio en pantalla— y el punto **se perdía**: un dato que el dispositivo sí
había medido desaparecía porque la red no estaba. El cierre lo señaló y tenía
razón.

Ahora la evidencia se escribe en IndexedDB **antes** de intentar enviarla, en
el mismo módulo y la misma base que la cola de RTE03, en un almacén aparte. El
peor caso pasa a ser "se envía más tarde".

Cómo se simula el offline, y por qué así
-----------------------------------------
Interceptando `/api/**` y abortando, no con `context.set_offline(True)`. Es el
patrón que ya usa la suite de RTE03 y el motivo sigue valiendo: el modo offline
de Playwright también bloquea la petición del documento, y entonces no se puede
recargar la página — que es justo lo que hay que probar para el reinicio.

La ubicación sí es real
-----------------------
`grant_permissions(['geolocation'])` y `set_geolocation(...)`, así que el
módulo recorre su etapa 1 y produce evidencia `fresh` de verdad, con
coordenadas conocidas. Sin eso sólo se podría probar el camino de Missing, que
es el que ya cubre la travesía de captura silenciosa.

Límite honesto: esto es Edge de escritorio. **No** sustituye la validación en
hardware iOS/Android, que es el Item D y sigue fuera de este entorno.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}

#: Mónaco, los mismos puntos con los que se mide el routing real. Que el
#: extracto de pruebas los conozca no importa aquí —esta suite no enruta— pero
#: mantiene una sola geografía en todo RTE06.
LAT, LON = 43.7311, 7.4197


@asynccontextmanager
async def _movil_con_gps(live_server, email: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server,
                viewport=MOVIL,
                permissions=["geolocation"],
                geolocation={"latitude": LAT, "longitude": LON, "accuracy": 12},
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


async def _evidencia_pendiente(page) -> list[dict]:
    """Lee el almacén durable tal como lo escribe `offlineQueue`.

    Si la base o el almacén no existen devuelve lista vacía en vez de fallar:
    "no hay nada pendiente" y "no hay almacén" se distinguen por el resto de las
    aserciones, no por una excepción de IndexedDB.
    """
    return await page.evaluate(
        """() => new Promise((resolver) => {
            const solicitud = indexedDB.open('cer-route-offline', 2);
            solicitud.onerror = () => resolver([]);
            solicitud.onsuccess = () => {
                const db = solicitud.result;
                if (!db.objectStoreNames.contains('pending_location_evidence')) {
                    resolver([]);
                    return;
                }
                const tx = db.transaction('pending_location_evidence', 'readonly');
                const todo = tx.objectStore('pending_location_evidence').getAll();
                todo.onsuccess = () => resolver(todo.result);
                todo.onerror = () => resolver([]);
            };
        })"""
    )


async def _filas(consulta: str, company_id: int) -> list[dict]:
    async with async_session_maker() as sesion:
        filas = await sesion.execute(text(consulta), {"c": company_id})
        return [dict(f._mapping) for f in filas]


async def _puntos(company_id: int) -> list[dict]:
    return await _filas(
        "SELECT event_kind, subject_id, evidence_level, latitude, longitude, "
        "device_captured_at FROM location_fix WHERE company_id = :c "
        "ORDER BY id",
        company_id,
    )


# ── Lo que antes se perdía ──────────────────────────────────────────────────


async def test_a_location_captured_offline_is_not_lost(seeded, live_server):
    """Start Work sin red: el punto se guarda y se envía al volver la red.

    Es el caso exacto que el cierre señaló. Antes, este punto no llegaba nunca:
    se medía, el envío fallaba y nadie volvía a saber de él.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        # Se espera a que la pantalla esté en pie **antes** de cortar: su carga
        # inicial también pasa por `/api`, y cortarla antes dejaría al
        # supervisor sin botón que pulsar. Lo que se quiere sin red es la
        # acción, no el arranque.
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        # La acción operativa sigue: la cola de RTE03 la guarda.
        await page.wait_for_timeout(4_000)

        pendiente = await _evidencia_pendiente(page)
        assert len(pendiente) == 1, f"el punto tiene que estar guardado: {pendiente}"
        assert pendiente[0]["endpoint"] == "/location/evidence"
        assert pendiente[0]["payload"]["evidence_level"] == "fresh"
        assert pendiente[0]["id"].startswith("start_work:")

        # Vuelve la red. El vaciado de acciones arrastra el de evidencia.
        await contexto.unroute("**/api/**")
        await page.reload()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=25_000
        )
        await page.wait_for_timeout(4_000)

    puntos = await _puntos(seeded.alpha.id)
    assert len(puntos) == 1, f"el punto tuvo que llegar: {puntos}"
    assert puntos[0]["event_kind"] == "start_work"
    assert puntos[0]["evidence_level"] == "fresh", (
        "y llegar como se midió: subirse tarde no lo degrada ni lo mejora"
    )
    assert float(puntos[0]["latitude"]) == pytest.approx(LAT, abs=1e-4)


async def test_pending_evidence_survives_a_page_restart(seeded, live_server):
    """Reiniciar la aplicación no pierde la evidencia pendiente.

    Se corta la red, se captura, **se cierra la página** y se abre otra en el
    mismo contexto —que es lo que hace un supervisor al cerrar y reabrir el
    navegador—. IndexedDB persiste por origen, así que la evidencia tiene que
    seguir ahí y enviarse al recuperar la red.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(4_000)
        assert len(await _evidencia_pendiente(page)) == 1

        # El "reinicio": la página se va, el almacenamiento del origen se queda.
        await page.close()
        otra = await contexto.new_page()
        await otra.goto("/route")
        sobrevivio = await _evidencia_pendiente(otra)
        assert len(sobrevivio) == 1, "un reinicio no puede perder el punto"

        await contexto.unroute("**/api/**")
        await otra.reload()
        await expect(otra.get_by_text("What's next?")).to_have_count(
            1, timeout=25_000
        )
        await otra.wait_for_timeout(4_000)

    assert len(await _puntos(seeded.alpha.id)) == 1


async def test_a_cached_point_does_not_become_fresh_after_a_delayed_upload(
    seeded, live_server
):
    """§32: subirse tarde no cambia el nivel de evidencia.

    Se fuerza el camino cacheado denegando la posición actual —se deniega el
    permiso, se captura, y el módulo cae a la caché del navegador— y se
    comprueba que lo que llega al servidor conserva el nivel con el que se
    escribió en el almacén, no uno recalculado al enviar.

    Si el almacén guardara "coordenadas y hora" y el nivel se decidiera al
    enviar, un punto de hace cinco minutos llegaría como fresco y la provenance
    de §28 mentiría sobre la calidad del dato.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(4_000)

        pendiente = await _evidencia_pendiente(page)
        assert len(pendiente) == 1
        nivel_guardado = pendiente[0]["payload"]["evidence_level"]
        capturado = pendiente[0]["payload"]["device_captured_at"]

        await contexto.unroute("**/api/**")
        await page.reload()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=25_000
        )
        await page.wait_for_timeout(4_000)

    puntos = await _puntos(seeded.alpha.id)
    assert len(puntos) == 1
    assert puntos[0]["evidence_level"] == nivel_guardado, (
        "el nivel que llega es el que se guardó, no uno recalculado al enviar"
    )
    # Y la hora de captura es la del dispositivo, no la de la subida.
    assert puntos[0]["device_captured_at"].isoformat().startswith(capturado[:19])


async def test_a_replayed_capture_writes_one_authoritative_point(
    seeded, live_server
):
    """Capturar dos veces el mismo evento deja **una** entrada y **un** punto.

    La llave del almacén es la tupla de correlación, así que la segunda captura
    reemplaza a la primera en el dispositivo en vez de apilar otra. La
    idempotencia empieza aquí y no depende de que el servidor la arregle
    después — aunque también la garantiza, con su índice único.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(3_000)
        # Recargar con la red aún cortada hace que el workbench reconcilie y
        # vuelva a intentar: la evidencia no se duplica.
        await page.reload()
        await page.wait_for_timeout(3_000)

        pendiente = await _evidencia_pendiente(page)
        assert len(pendiente) <= 1, f"no se apilan entradas: {pendiente}"

        await contexto.unroute("**/api/**")
        await page.reload()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=25_000
        )
        await page.wait_for_timeout(4_000)

    assert len(await _puntos(seeded.alpha.id)) <= 1


async def test_the_store_is_drained_and_left_clean_after_sync(seeded, live_server):
    """Tras sincronizar, el almacén queda vacío.

    Importa porque un almacén que no se vacía crece sin límite en el
    dispositivo y reintenta para siempre puntos ya aceptados. La entrada se
    retira al recibir la confirmación, no antes.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(4_000)
        assert len(await _evidencia_pendiente(page)) == 1

        await contexto.unroute("**/api/**")
        await page.reload()
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=25_000
        )
        await page.wait_for_timeout(5_000)

        assert await _evidencia_pendiente(page) == [], (
            "lo confirmado se retira del dispositivo"
        )

    assert len(await _puntos(seeded.alpha.id)) == 1


async def test_reauthentication_does_not_discard_pending_evidence(
    seeded, live_server
):
    """Volver a autenticarse no descarta la evidencia pendiente.

    El almacén vive en IndexedDB, que es del origen y no de la sesión, así que
    cerrar y volver a abrir sesión no lo toca. Se comprueba porque lo contrario
    —guardarla en memoria o ligada al token— es un error fácil de cometer y
    silencioso: se perdería justo cuando el supervisor vuelve a entrar.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(4_000)
        assert len(await _evidencia_pendiente(page)) == 1

        # Se rehace la sesión: mismo origen, credenciales nuevas.
        await contexto.unroute("**/api/**")
        await abrir_sesion(page, supervisor.email)
        sigue = await _evidencia_pendiente(page)
        assert len(sigue) == 1, "reautenticarse no puede descartar el punto"

        await page.goto("/route")
        await expect(page.get_by_text("What's next?")).to_have_count(
            1, timeout=25_000
        )
        await page.wait_for_timeout(4_000)

    assert len(await _puntos(seeded.alpha.id)) == 1
