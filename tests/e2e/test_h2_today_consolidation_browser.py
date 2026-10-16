"""H-2: una fila por supervisor, con dos jornadas el mismo día.

Qué reproduce
-------------
La captura que llegó de campo: dos filas «Karina Aguirre», una con `Work Ended`
y `0.0 mi` y otra `Working` con 62,5 mi, y el panel lateral enseñando la
primera mientras el administrador había pulsado la segunda.

El modelo permite ese estado a propósito —`uq_work_session_one_active` es un
índice parcial sobre `status = 'active'`, así que las jornadas cerradas se
repiten— y la pantalla asumía una por persona.

Por qué en navegador y no sólo en integración
----------------------------------------------
Porque el defecto se partía entre dos mitades: el servidor devolvía dos filas y
el cliente resolvía la selección con `find` por `user_id`, quedándose con la
primera. Un test de API habría visto las dos filas y no habría visto nunca cuál
de ellas acaba en el panel, que es lo que el administrador miraba.

Las capturas van a `var/screenshots/h2/`, fuera del árbol versionado, con el
mismo arnés que el resto de la evidencia visual de Today.
"""

from __future__ import annotations

import pathlib

import pytest
from playwright.async_api import expect

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte07_today_live_browser import (
    ESCRITORIO,
    MOVIL,
    RUTA,
    _preparar_supervisor,
)

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/h2")

FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def _cerrar_la_jornada_abierta(alpha_client, seeded) -> None:
    """Cierra la jornada en curso resolviendo todo lo que la bloquea.

    No es ruido: `End Work` exige la parada resuelta y la lectura de cierre, y
    saltárselas dejaría la jornada abierta — con lo que la segunda ni siquiera
    podría crearse y el test estaría probando otra cosa.
    """
    actual = (await alpha_client.get("/api/worksessions/current")).json()
    jornada = actual["work_session"]

    # Un viaje no se planifica sin su dato de contexto, así que los valores
    # estándar tienen que existir antes. Es la regla del dominio, no una
    # comodidad del test.
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    valores = (
        await alpha_client.get("/api/standard-values/office_purposes")
    ).json()
    assert valores, "no se sembraron los valores estandar"
    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "office", "standard_value_id": valores[0]["id"]},
        )
    ).json()

    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "100000.0"},
    )
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )
    resultados = (await alpha_client.get("/api/standard-values/outcomes")).json()
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultados[0]["id"]},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "100100.0"},
    )
    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 200, cierre.text


async def _dos_jornadas_hoy(alpha_client, seeded, unidad: str) -> None:
    """El estado que reprodujo el defecto: una cerrada y otra abierta."""
    await _preparar_supervisor(alpha_client, seeded, unidad)
    await _cerrar_la_jornada_abierta(alpha_client, seeded)
    segunda = await alpha_client.post("/api/worksessions", json={})
    assert segunda.status_code in (200, 201), segunda.text


async def test_escritorio_una_fila_y_el_panel_correcto(
    seeded, alpha_client, live_server
):
    """Una sola fila, el panel que corresponde, y el refresco que no la mueve."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _dos_jornadas_hoy(alpha_client, seeded, "V-H2-DESK")
    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)

            filas = page.locator("tbody tr", has_text="Supervisor Tester")
            await expect(filas).to_have_count(1, timeout=20_000)

            await filas.first.click()

            # El panel describe la jornada ABIERTA, no la que se cerró antes.
            await expect(page.get_by_text("Working").first).to_be_visible()
            await expect(
                page.get_by_text("Work Ended", exact=True)
            ).to_have_count(0)

            await page.screenshot(
                path=str(DESTINO / "escritorio-una-fila-panel-correcto.png"),
                full_page=True,
            )

            # El refresco no mueve la selección. `visibilitychange` fuerza una
            # relectura inmediata, que es el mismo camino que el temporizador de
            # 30 s: así el test no espera medio minuto para probar lo mismo.
            await page.evaluate(
                "document.dispatchEvent(new Event('visibilitychange'))"
            )
            await page.wait_for_timeout(1_500)

            await expect(filas).to_have_count(1)
            await expect(page.get_by_text("Working").first).to_be_visible()

            await page.screenshot(
                path=str(DESTINO / "escritorio-tras-el-refresco.png"),
                full_page=True,
            )

            # Y la lista no repite a la persona: el servidor ya consolida.
            cuerpo = await page.evaluate(
                """async () => {
                    const r = await fetch('/api/live/today');
                    return (await r.json());
                }"""
            )
            suyas = [
                s for s in cuerpo["supervisors"] if s["user_id"] == supervisor.id
            ]
            assert len(suyas) == 1, suyas
            identificadores = [s["user_id"] for s in cuerpo["supervisors"]]
            assert len(identificadores) == len(set(identificadores))
            assert cuerpo["summary"]["supervisors_total"] == len(
                set(identificadores)
            )
        finally:
            await navegador.close()


async def test_movil_una_fila_y_su_detalle(seeded, alpha_client, live_server):
    """El mismo hecho en la arquitectura móvil, que es otra: lista y detalle.

    En móvil el detalle es una pantalla entera con vuelta, no un panel al lado,
    así que la comprobación no se puede copiar de escritorio: hay que entrar al
    detalle y mirar allí.
    """
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _dos_jornadas_hoy(alpha_client, seeded, "V-H2-MOV")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto(RUTA)

            tarjetas = page.locator(
                "button", has_text="Supervisor Tester"
            )
            await expect(tarjetas).to_have_count(1, timeout=20_000)

            await page.screenshot(
                path=str(DESTINO / "movil-lista-una-tarjeta.png"), full_page=True
            )

            await tarjetas.first.click()
            await expect(page.get_by_text("Working").first).to_be_visible(
                timeout=20_000
            )
            await expect(
                page.get_by_text("Work Ended", exact=True)
            ).to_have_count(0)

            await page.screenshot(
                path=str(DESTINO / "movil-detalle-jornada-abierta.png"),
                full_page=True,
            )
        finally:
            await navegador.close()
