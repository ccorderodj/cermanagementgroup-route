"""No poder leer el estado no es saber que no hay nada pendiente.

Qué cierra este archivo
-----------------------
El defecto que CER reprodujo en validación física: tras volver de la cámara en
el cierre, la tarea de odómetro desaparecía y el supervisor acababa en el
workbench, teniendo que pulsar End Work otra vez para recuperarla.

El mecanismo era que la lectura de la evidencia se hacía con
`fetchSessionOdometer(...).catch(() => null)`, y ese `null` significaba a la vez
"no hay evidencia" y "no pude preguntar". La pantalla decide con eso si hay una
lectura de cierre pendiente, de modo que un parpadeo de red acababa afirmando
que no había nada — que es justo lo que la regla de producto de esta revisión
prohíbe:

    no poder leer el estado no equivale a una ausencia autoritativa de estado.

Qué se simula y por qué así
---------------------------
Se intercepta **sólo** `GET /api/odometer/sessions/{id}` y se le responde 503
las primeras N veces. Es la clase de fallo que el análisis de campo identificó:
las primeras peticiones después de que Android recree la pestaña. El resto de la
aplicación sigue respondiendo, así que lo que se mide es exactamente la decisión
de la pantalla ante una lectura que no llega, y no una caída general.

El lector reintenta tres veces por reconciliación, así que para llegar a la
pantalla de incertidumbre hay que agotar esos tres intentos. Eso es deliberado:
un parpadeo de uno o dos intentos se resuelve solo y el supervisor no ve nada,
que es el caso bueno y el que más ocurre.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte06_odometer_lifecycle_browser import (
    CAPTURA,
    MOVIL,
    _evidencia,
    _jornada,
    _preparar_vehiculo,
    _recrear_pestana,
    _subir_foto,
    _viajes,
)


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


#: Más que los reintentos del lector, para que la primera reconciliación agote
#: su presupuesto y la pantalla tenga que decidir sin saber.
FALLOS = 3


async def _fallar_lectura_de_odometro(contexto, veces: int) -> dict:
    """Responde 503 a las primeras `veces` lecturas de evidencia.

    Devuelve un contador vivo para que el test pueda comprobar que la
    intercepción llegó a usarse — sin eso, un patrón que no case dejaría pasar
    el test sin haber simulado nada.
    """
    estado = {"fallos": 0, "pasadas": 0}

    async def _responder(ruta):
        peticion = ruta.request
        if peticion.method != "GET":
            await ruta.fallback()
            return
        if estado["fallos"] < veces:
            estado["fallos"] += 1
            await ruta.fulfill(
                status=503,
                content_type="application/json",
                body='{"detail": "temporarily unavailable"}',
            )
            return
        estado["pasadas"] += 1
        await ruta.fallback()

    await contexto.route("**/api/odometer/sessions/*", _responder)
    return estado


async def _dia_hasta_el_cierre(page) -> None:
    """Un día completo hasta tener la lectura de cierre pendiente."""
    await page.goto("/route")
    await page.get_by_role("button", name="Start Work").click()
    await page.get_by_role("button", name="Return Home").click()
    await page.get_by_role("button", name="Start Trip").click()
    await expect(page.get_by_text(CAPTURA)).to_have_count(1, timeout=25_000)
    await _subir_foto(page)
    await page.locator("#odometer-reading").fill("90000")
    await page.get_by_role("button", name="Confirm reading").click()
    await page.get_by_role("button", name="Arrived Home").click()
    await expect(page.get_by_text("What's next?")).to_have_count(1, timeout=25_000)
    await page.get_by_role("button", name="End Work").click()
    await expect(page.get_by_text("One last thing")).to_have_count(1, timeout=25_000)


async def test_e3_a_temporary_read_failure_does_not_erase_the_pending_end_task(
    seeded, alpha_client, live_server,
):
    """E3: la lectura falla, y la tarea de cierre **no** desaparece.

    El recorrido es el de campo, con el fallo donde el análisis dijo que estaba:

        cierre pendiente, con foto ya subida
        → se recrea la pestaña
        → la primera reconciliación no consigue leer la evidencia
        → la aplicación **no** colapsa al workbench
        → la lectura vuelve a funcionar
        → la misma tarea de cierre se restaura, con su foto

    La aserción que importa es la negativa: que no aparezca el workbench. Ahí
    es donde acababa el supervisor, y desde donde tenía que pulsar End Work una
    segunda vez.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-E3")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            await _dia_hasta_el_cierre(page)

            # La foto se sube: a partir de aquí la evidencia existe en el
            # servidor y la restauración tiene que devolverla.
            await _subir_foto(page)
            await expect(page.locator("#odometer-reading")).to_have_count(
                1, timeout=25_000
            )
            fin = await _evidencia(seeded.alpha.id, "end")
            assert fin.captured_at is not None, "la foto debía quedar subida"
            jornada_antes = await _jornada(seeded.alpha.id)
            viajes_antes = await _viajes(seeded.alpha.id)

            # ── La lectura deja de responder, y se recrea la pestaña ────────
            estado = await _fallar_lectura_de_odometro(contexto, FALLOS)
            await _recrear_pestana(page)

            # Lo que NO puede pasar: acabar en el workbench, que afirmaría en
            # silencio que no queda ninguna lectura pendiente.
            await expect(page.get_by_text("Your workday could not be loaded")).to_have_count(
                1, timeout=25_000
            )
            await expect(page.get_by_text("What's next?")).to_have_count(0)
            assert estado["fallos"] == FALLOS, (
                f"la intercepción no llegó a usarse: {estado}"
            )

            # ── Vuelve a funcionar: la misma tarea, con su foto ─────────────
            await page.get_by_role("button", name="Try again").click()
            await expect(page.get_by_text("One last thing")).to_have_count(
                1, timeout=25_000
            )
            await expect(
                page.get_by_role("button", name="Retake photo")
            ).to_have_count(1, timeout=25_000)
            assert estado["pasadas"] >= 1, (
                f"la lectura tenía que volver a pasar: {estado}"
            )

            # ── E6: restaurar no tocó el dominio ───────────────────────────
            jornada_despues = await _jornada(seeded.alpha.id)
            assert jornada_despues.id == jornada_antes.id, "se creó otra jornada"
            assert jornada_despues.status == jornada_antes.status, (
                "restaurar la pantalla cambió el estado de la jornada"
            )
            assert await _viajes(seeded.alpha.id) == viajes_antes, "se creó un viaje"

            # ── Y se puede terminar, sin pulsar End Work otra vez ───────────
            await page.locator("#odometer-reading").fill("90142.5")
            await page.get_by_role("button", name="Confirm reading").click()
            await expect(
                page.get_by_text("Ready to start your day?")
            ).to_have_count(1, timeout=25_000)

            resuelta = await _evidencia(seeded.alpha.id, "end")
            assert resuelta.status == "photo_confirmed", resuelta.status
            assert str(resuelta.confirmed_reading) == "90142.5"
        finally:
            await navegador.close()


async def test_e4_the_hardening_releases_when_the_answer_is_nothing_pending(
    seeded, alpha_client, live_server,
):
    """E4: no saber no puede convertirse en no avanzar nunca.

    La otra mitad de E3, y la que impide que el arreglo cambie un defecto por
    otro. Si la pantalla se quedara en "no se pudo cargar" aunque la lectura
    volviera a funcionar, el supervisor quedaría atrapado — que es peor que el
    defecto original, porque antes al menos podía seguir trabajando.

    Aquí la respuesta autoritativa es **que no hay lectura de cierre
    pendiente**, y lo que se comprueba es que en cuanto esa respuesta llega la
    pantalla la obedece.
    """
    from playwright.async_api import async_playwright

    await _preparar_vehiculo(alpha_client, seeded, "V-E4")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=25_000
            )
            assert await _evidencia(seeded.alpha.id, "end") is None, (
                "la jornada acaba de empezar: no puede haber lectura de cierre"
            )

            estado = await _fallar_lectura_de_odometro(contexto, FALLOS)
            await _recrear_pestana(page)

            # Mientras no se sabe, se dice que no se sabe.
            await expect(page.get_by_text("Your workday could not be loaded")).to_have_count(
                1, timeout=25_000
            )
            assert estado["fallos"] == FALLOS, estado

            # Y en cuanto se sabe, se obedece: no hay cierre pendiente, así que
            # el sitio correcto **es** el workbench.
            await page.get_by_role("button", name="Try again").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=25_000
            )
            await expect(
                page.get_by_text("Your workday could not be loaded")
            ).to_have_count(0)
        finally:
            await navegador.close()
