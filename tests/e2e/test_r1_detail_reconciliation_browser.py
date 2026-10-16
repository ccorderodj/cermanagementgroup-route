"""R-1: el detalle de User Activity explica su propio consolidado.

Qué reproduce
-------------
El caso que lo destapó: un día con `125,5 mi` arriba y `62,5` repartidos abajo.
Las millas que faltaban eran de un regreso a casa — un viaje que cierra al
llegar y **nunca abre parada**, así que aportaba al total y no existía para la
lista, porque la consulta del detalle partía de `ActivityExecution`.

Por qué en navegador y no sólo en integración
----------------------------------------------
Porque hay dos cosas que un test de API no ve: que la tarjeta sepa dibujar una
fila sin actividad —su clave de render era el identificador de la actividad, que
ahora es nulo— y que no la presente como `In progress`, que es lo que haría
`outcome_label || 'In progress'` sin un indicador explícito.

Las capturas van a `var/screenshots/r1/`, fuera del árbol versionado, con el
mismo arnés que el resto de la evidencia visual del explorador.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import lanzar_edge
from tests.e2e.test_rte08_activity_explorer_browser import (
    ESCRITORIO,
    FOTO,
    MOVIL,
    _abrir,
    _historia,
)

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/r1")


async def _regreso_a_casa(alpha_client, seeded, *, metros: str) -> int:
    """Un viaje a casa con millaje calculado y sin bloque de actividad.

    Se abre una jornada nueva porque `_historia` cierra la suya. No se fabrica
    ninguna parada: el objeto del checkpoint es que el dominio no la necesite.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "200000.0"},
    )
    viaje = (
        await alpha_client.post("/api/trips", json={"purpose": "home"})
    ).json()
    assert "id" in viaje, viaje
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    async with async_session_maker() as s:
        await s.execute(
            text(
                "UPDATE trip_mileage SET state='calculated', total_meters=:m, "
                "calculated_at=now() WHERE trip_id = :t"
            ),
            {"m": metros, "t": viaje["id"]},
        )
        # Las dos jornadas al mismo día de negocio: es el estado que se mira.
        #
        # Al día de la **primera**, no a `CURRENT_DATE`. `CURRENT_DATE` es la
        # fecha en la zona de sesión de PostgreSQL —aquí, Guatemala— y la
        # pantalla abre en el día del supervisor: de 18:00 a 24:00 hora local
        # eran fechas distintas y la prueba fallaba sin que nada estuviera mal
        # (T-1/T-2 autoriza corregir este fixture; las aserciones no cambian).
        await s.execute(
            text(
                "UPDATE work_session SET session_date = ("
                "  SELECT session_date FROM work_session"
                "  WHERE company_id = :c AND user_id = :u"
                "  ORDER BY started_at LIMIT 1"
                ") WHERE company_id = :c AND user_id = :u"
            ),
            {"c": seeded.alpha.id, "u": seeded.alpha.users["supervisor"].id},
        )
        await s.commit()
    return viaje["id"]


async def test_escritorio_el_detalle_muestra_el_trayecto_sin_parada(
    seeded, alpha_client, live_server
):
    """AC1, AC3 y AC9 en la pantalla: la tarjeta existe y no miente."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _historia(alpha_client, seeded, unidad="V-R1-E2E")
    await _regreso_a_casa(alpha_client, seeded, metros="16093.4")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await _abrir(contexto, seeded, rango="day")

            # El regreso a casa tiene su propia tarjeta.
            tarjeta = page.locator("div").filter(has_text="Home").first
            await expect(
                page.get_by_role("heading", name="Home", exact=True).first
            ).to_be_visible(timeout=20_000)

            # La captura va **antes** de las aserciones: si alguna falla, la
            # imagen del estado real es lo primero que hace falta para
            # entenderlo, y tomarla después no la produciría nunca.
            await page.screenshot(
                path=str(DESTINO / "escritorio-detalle-con-trayecto.png"),
                full_page=True,
            )
            assert tarjeta is not None

            # Y no se presenta como una parada abierta esperando resultado.
            await expect(page.get_by_text("In progress")).to_have_count(0)

            # El consolidado queda explicado por lo que se ve: se lee del
            # contrato, que es lo que la pantalla pinta.
            cuerpo = await page.evaluate(
                """async () => {
                    const r = await fetch('/api/activity-explorer?range=day');
                    return await r.json();
                }"""
            )
            total = float(cuerpo["summary"]["official_miles"])
            visible = sum(float(a["official_miles"]) for a in cuerpo["activities"])
            assert abs(total - visible) < 0.05, (
                f"el detalle no explica el total: {visible} de {total}"
            )

            # Y el contador sigue contando paradas, no tarjetas.
            paradas = sum(1 for a in cuerpo["activities"] if a["has_activity"])
            assert cuerpo["summary"]["activities"] == paradas
            assert len(cuerpo["activities"]) > paradas, (
                "la prueba no está mirando el caso: falta el trayecto sin parada"
            )
        finally:
            await navegador.close()


async def test_movil_conserva_su_disposicion_aprobada(
    seeded, alpha_client, live_server
):
    """AC9 en móvil: la misma jerarquía reflujada, sin arquitectura nueva."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _historia(alpha_client, seeded, unidad="V-R1-MOV")
    await _regreso_a_casa(alpha_client, seeded, metros="16093.4")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await _abrir(contexto, seeded, rango="day")

            await expect(
                page.get_by_role("heading", name="Home", exact=True).first
            ).to_be_visible(timeout=20_000)
            await expect(page.get_by_text("In progress")).to_have_count(0)

            # Sin desbordamiento horizontal: la disposición aprobada se mantiene.
            desborde = await page.evaluate(
                "() => document.documentElement.scrollWidth >"
                " document.documentElement.clientWidth + 1"
            )
            assert not desborde, "la tarjeta nueva desborda el ancho del móvil"

            await page.screenshot(
                path=str(DESTINO / "movil-detalle-con-trayecto.png"),
                full_page=True,
            )
        finally:
            await navegador.close()
