"""La cola del dispositivo está acotada, y lo que deja de reintentar se cuenta.

Qué cierra este archivo
-----------------------
Es el último hueco del cierre de RTE06: que la cola de evidencia **no**
reintente indefinidamente, y que al dejar de reintentar el hecho operativo
acabe en una condición final veraz en vez de desaparecer.

Por qué no bastaba con lo que ya había
--------------------------------------
La mitad del servidor —el barrido que cierra un evento del que nadie volvió a
hablar— ya estaba probada. Lo que no estaba demostrado era la cota del cliente:
`attempts` se escribía y no se leía nunca, así que no existía ningún límite, y
un comentario del delta anterior afirmaba que sí. Ahora cada envío lleva
`expiresAt`, calculado con la ventana de recuperación de la compañía más el
margen del barrido —los mismos números con los que el servidor decide cerrar el
hecho por su cuenta—, y `haCaducado` lo consume.

Cómo se provoca la condición transitoria
----------------------------------------
Se intercepta **sólo** `POST /api/location/evidence` y se responde 409, que es
literalmente el caso del hallazgo de campo: la evidencia llega antes de que su
jornada esté `ACTIVE`. El resto de la aplicación sigue funcionando, así que la
recarga que vuelve a disparar el vaciado es la de verdad.

Y cómo se agota la ventana sin esperarla
----------------------------------------
Reescribiendo `expiresAt` de la entrada a una hora pasada. La alternativa era
esperar los cinco minutos reales de ventana más margen; esto ejercita el mismo
código —la cola real, en IndexedDB real, con el vaciado real— y lo único que se
adelanta es el reloj.

Los helpers se reutilizan de `test_rte06_offline_durability_browser`: es el
mismo arnés y duplicarlo daría dos sitios donde arreglar lo mismo.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.test_rte06_offline_durability_browser import (
    _evidencia_pendiente,
    _filas,
    _movil_con_gps,
    _puntos,
)


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


async def _caducar_pendientes(page) -> int:
    """Pone en el pasado la caducidad de lo que haya en la cola.

    Devuelve cuántas entradas tocó, para que el test no pueda pasar por haber
    envejecido cero.
    """
    return await page.evaluate(
        """() => new Promise((resolver) => {
            const solicitud = indexedDB.open('cer-route-offline');
            solicitud.onerror = () => resolver(0);
            solicitud.onsuccess = () => {
                const db = solicitud.result;
                if (!db.objectStoreNames.contains('pending_location_evidence')) {
                    resolver(0);
                    return;
                }
                const tx = db.transaction(
                    'pending_location_evidence', 'readwrite',
                );
                const almacen = tx.objectStore('pending_location_evidence');
                const todo = almacen.getAll();
                todo.onerror = () => resolver(0);
                todo.onsuccess = () => {
                    const filas = todo.result;
                    const pasado = new Date(Date.now() - 60000).toISOString();
                    filas.forEach((fila) => {
                        almacen.put(Object.assign({}, fila, {
                            expiresAt: pasado,
                        }));
                    });
                    tx.oncomplete = () => resolver(filas.length);
                    tx.onerror = () => resolver(0);
                };
            };
        })"""
    )


async def _rechazar_evidencia(contexto) -> None:
    """Responde 409 al envío de evidencia, y sólo a ése.

    409 no es una invención del test: es lo que devuelve el servidor cuando la
    evidencia llega antes de que su jornada esté activa, que es la carrera del
    hallazgo de campo. Desde el dispositivo es indistinguible del otro 409 del
    endpoint —la ventana de End Work ya cerrada—, y de ahí que la cota tenga
    que existir.
    """

    async def _responder(ruta):
        await ruta.fulfill(
            status=409,
            content_type="application/json",
            body='{"detail": "That work session is not active yet."}',
        )

    await contexto.route("**/api/location/evidence", _responder)


async def _hechos(company_id: int) -> list[dict]:
    return await _filas(
        "SELECT event_kind, reason_code, subject_id FROM missing_location_event "
        "WHERE company_id = :c ORDER BY id",
        company_id,
    )


async def _esperar_workbench(page) -> None:
    await expect(page.get_by_text("What's next?")).to_have_count(1, timeout=25_000)


async def test_an_expired_queue_entry_stops_retrying_and_the_fact_is_still_told(
    seeded, live_server,
):
    """AC-FINAL-01, 02 y 03: acotada, y sin perder el hecho al acotarla.

    El recorrido completo:

        se captura un punto bueno
        → el envío falla con una condición transitoria (409)
        → la entrada **se queda** en la cola y consta el intento
        → se agota su ventana válida
        → la entrada deja de reintentarse y se retira
        → el hecho operativo acaba en un Missing veraz

    El último paso es el que impide que esto sea un falso verde: que la entrada
    desaparezca no puede ser el criterio de éxito, porque desaparecer es
    exactamente lo que hacía el punto que antes se perdía en silencio.
    """
    from app.routers_api.location.service import sweep_unreported_windows

    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)

        await _rechazar_evidencia(contexto)
        await page.get_by_role("button", name="Start Work").click()
        await _esperar_workbench(page)
        await page.wait_for_timeout(4_000)

        # ── La entrada se queda, porque la condición es transitoria ─────────
        pendiente = await _evidencia_pendiente(page)
        assert len(pendiente) == 1, f"el punto tenía que quedar encolado: {pendiente}"
        entrada = pendiente[0]
        assert entrada["id"].startswith("start_work:"), entrada
        assert entrada["attempts"] >= 1, (
            f"se intentó y falló, así que el intento tiene que constar: {entrada}"
        )
        assert entrada.get("expiresAt"), (
            "sin caducidad no hay cota, y eso es justo lo que no podía quedar "
            f"sin demostrar: {entrada}"
        )
        assert await _puntos(seeded.alpha.id) == [], (
            "el servidor rechazó el envío, así que no puede haber punto"
        )

        # ── Se agota su ventana válida ──────────────────────────────────────
        envejecidas = await _caducar_pendientes(page)
        assert envejecidas == 1, f"no se envejeció ninguna entrada: {envejecidas}"

        # ── Vuelve a vaciarse: el envío sigue fallando, pero ya caducó ──────
        await page.reload()
        await _esperar_workbench(page)
        await page.wait_for_timeout(4_000)

        assert await _evidencia_pendiente(page) == [], (
            "una entrada caducada no puede seguir en la cola reintentándose"
        )
        assert await _puntos(seeded.alpha.id) == [], (
            "y retirarla no puede haber colado el punto que el servidor rechazó"
        )

    # ── El hecho se cuenta igual: lo cierra el barrido ──────────────────────
    #
    # Se envejece la jornada porque el corte del barrido se mide contra la hora
    # de ocurrencia. `start_work` no estaba cubierto por el barrido hasta este
    # cierre: la entrada se retiraba y nadie cerraba el hecho.
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE work_session SET started_at = now() - interval '2 hours' "
                "WHERE company_id = :c"
            ),
            {"c": seeded.alpha.id},
        )
        await sesion.commit()

    await sweep_unreported_windows()

    hechos = await _hechos(seeded.alpha.id)
    arranques = [h for h in hechos if h["event_kind"] == "start_work"]
    assert len(arranques) == 1, (
        f"el hecho se perdió: ni punto, ni Missing, ni cola. {hechos}"
    )
    assert arranques[0]["reason_code"] == "no_client_report", arranques[0]
    assert await _puntos(seeded.alpha.id) == [], (
        "y el cierre no fabrica coordenadas para rellenar el hueco"
    )


async def test_a_queued_entry_still_succeeds_when_the_condition_clears_in_time(
    seeded, live_server,
):
    """AC-FINAL-04: el camino bueno sigue funcionando.

    Es la mitad que hace significativo al test anterior. Sin esto, los dos
    pasarían igual contra una cola que tirara **todo**, y "acotada" se
    confundiría con "rota".

    La diferencia es una sola: aquí la condición transitoria se resuelve
    **dentro** de la ventana, y entonces la entrada desaparece por haberse
    enviado, no por haber caducado. Se distingue mirando si el punto llegó.
    """
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil_con_gps(live_server, supervisor.email) as (contexto, page):
        await page.goto("/route")
        await expect(
            page.get_by_role("button", name="Start Work")
        ).to_have_count(1, timeout=25_000)

        await _rechazar_evidencia(contexto)
        await page.get_by_role("button", name="Start Work").click()
        await _esperar_workbench(page)
        await page.wait_for_timeout(4_000)

        pendiente = await _evidencia_pendiente(page)
        assert len(pendiente) == 1, f"tenía que quedar encolado: {pendiente}"
        assert await _puntos(seeded.alpha.id) == []

        # La condición se resuelve, y **no** se toca la caducidad: la ventana
        # sigue abierta.
        await contexto.unroute("**/api/location/evidence")
        await page.reload()
        await _esperar_workbench(page)
        await page.wait_for_timeout(4_000)

        assert await _evidencia_pendiente(page) == [], (
            "enviado y confirmado, la entrada se retira"
        )

    puntos = await _puntos(seeded.alpha.id)
    assert len(puntos) == 1, f"el punto tuvo que llegar: {puntos}"
    assert puntos[0]["event_kind"] == "start_work"
    assert puntos[0]["evidence_level"] == "fresh", (
        "y llegar como se midió: esperar en la cola no cambia el nivel"
    )
    assert await _hechos(seeded.alpha.id) == [], (
        "y si el punto llegó, no puede haber además un Missing del mismo hecho"
    )
