"""RTE-LOC-02 U1: la cola sin conexión es de quien la llenó.

El defecto (precheck P0): las acciones y los puntos pendientes no guardaban de
quién eran, el cierre de sesión no vaciaba IndexedDB y el envío usaba la cookie
del momento. En el mismo navegador, lo que A dejó sin conexión se habría
enviado como B.

* A encola sin red → cierra sesión → B entra: **B no envía nada de A** y lo de A
  sigue en el dispositivo.
* A vuelve: su acción y su punto salen, a su nombre.
* Lo encolado antes de esto (sin propietario) se retiene: ni se envía ni se borra.

El aislamiento entre tenants lo da el origen (cada tenant es un subdominio con
su propia IndexedDB); el propietario guarda también el host.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.integration.test_org_hierarchy import _organigrama

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

MOVIL = {"width": 390, "height": 844}
LAT, LON = 43.7311, 7.4197

_LEER = """(almacen) => new Promise((resolver) => {
    const solicitud = indexedDB.open('cer-route-offline');
    solicitud.onerror = () => resolver([]);
    solicitud.onsuccess = () => {
        const db = solicitud.result;
        if (!db.objectStoreNames.contains(almacen)) { resolver([]); return; }
        const todo = db.transaction(almacen, 'readonly').objectStore(almacen).getAll();
        todo.onsuccess = () => resolver(todo.result);
        todo.onerror = () => resolver([]);
    };
})"""

_SIN_PROPIETARIO = """(accion) => new Promise((resolver, fallar) => {
    const solicitud = indexedDB.open('cer-route-offline');
    solicitud.onsuccess = () => {
        const tx = solicitud.result.transaction('pending_actions', 'readwrite');
        tx.objectStore('pending_actions').add(accion);
        tx.oncomplete = () => resolver(true);
        tx.onerror = () => fallar(tx.error);
    };
})"""


@asynccontextmanager
async def _navegador(live_server):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL, permissions=["geolocation"],
                geolocation={"latitude": LAT, "longitude": LON, "accuracy": 12},
            )
            yield contexto, await contexto.new_page()
        finally:
            await navegador.close()


async def _entrar(page, email: str) -> None:
    await page.context.clear_cookies()  # cerrar sesión: el servidor borra las cookies
    await abrir_sesion(page, email, conceder_ubicacion=False)


async def _jornadas(company_id: int, user_id: int) -> int:
    async with async_session_maker() as s:
        return int(await s.scalar(
            text("SELECT count(*) FROM work_session WHERE company_id = :c AND user_id = :u"),
            {"c": company_id, "u": user_id},
        ))


async def _puntos(company_id: int) -> int:
    async with async_session_maker() as s:
        return int(await s.scalar(text("SELECT count(*) FROM location_fix WHERE company_id = :c"),
                                  {"c": company_id}))


async def test_lo_que_a_dejo_sin_red_no_sale_como_b(seeded, alpha_client, live_server):
    await _organigrama(alpha_client, seeded)
    alpha = seeded.alpha
    a, b = alpha.users["supervisor"], alpha.users["sup_a"]

    async with _navegador(live_server) as (contexto, page):
        await _entrar(page, a.email)
        await page.goto("/route")
        await expect(page.get_by_role("button", name="Start Work")).to_have_count(1, timeout=25_000)
        await contexto.route("**/api/**", lambda ruta: ruta.abort())
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(4_000)
        acciones = await page.evaluate(_LEER, "pending_actions")
        assert [x["owner"]["userId"] for x in acciones] == [a.id]
        assert len(await page.evaluate(_LEER, "pending_location_evidence")) == 1
        await contexto.unroute("**/api/**")

        # B en el mismo navegador, con red: carga My Route, que vacía la cola.
        await _entrar(page, b.email)
        await page.goto("/route")
        await expect(page.get_by_role("button", name="Start Work")).to_have_count(1, timeout=25_000)
        await page.wait_for_timeout(4_000)
        assert await _jornadas(alpha.id, b.id) == 0, "la acción de A no puede abrir la jornada de B"
        assert await _jornadas(alpha.id, a.id) == 0
        assert await _puntos(alpha.id) == 0
        assert len(await page.evaluate(_LEER, "pending_actions")) == 1, "lo de A no se borra"

        # Vuelve A: sale lo suyo.
        await _entrar(page, a.email)
        await page.goto("/route")
        await expect(page.get_by_text("What's next?")).to_have_count(1, timeout=25_000)
        await page.wait_for_timeout(4_000)
        assert await _jornadas(alpha.id, a.id) == 1
        assert await _puntos(alpha.id) == 1
        assert await page.evaluate(_LEER, "pending_actions") == []


async def test_lo_encolado_sin_propietario_se_retiene(seeded, live_server):
    alpha = seeded.alpha
    a = alpha.users["supervisor"]
    async with _navegador(live_server) as (_contexto, page):
        await _entrar(page, a.email)
        await page.goto("/route")
        await expect(page.get_by_role("button", name="Start Work")).to_have_count(1, timeout=25_000)
        # Una acción de un cliente anterior a RTE-LOC-02: sin `owner`.
        await page.evaluate(_SIN_PROPIETARIO, {
            "id": "00000000-0000-4000-8000-000000000001", "sequence": 1, "endpoint": "/worksessions",
            "method": "POST", "payload": {}, "kind": "worksession.start",
            "createdAt": "2026-10-20T12:00:00Z", "status": "pending", "locationPermission": "granted",
        })
        await page.reload()
        await expect(page.get_by_role("button", name="Start Work")).to_have_count(1, timeout=25_000)
        await page.wait_for_timeout(4_000)
        assert await _jornadas(alpha.id, a.id) == 0, "no se atribuye a quien tenga la sesión"
        assert len(await page.evaluate(_LEER, "pending_actions")) == 1, "ni se borra"
