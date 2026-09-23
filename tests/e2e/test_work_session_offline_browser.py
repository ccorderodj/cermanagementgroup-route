"""
Validación de la cola offline en un navegador real (cierre RTE03 002, §B).

Por qué existe este archivo
---------------------------
El resto de la suite ejercita la API con un transporte ASGI en memoria: no hay
navegador, así que no hay IndexedDB, ni ciclo de vida de pestaña, ni
reconexión. La entrega 001 de RTE03 lo declaró honestamente como no validado, y
el cierre 002 pide al menos **una** validación a nivel de navegador antes de
poder afirmar que ese comportamiento está confirmado.

Qué demuestra
-------------
1. La acción se encola mientras la API es inalcanzable.
2. La cola vive en IndexedDB y **sobrevive a recargar la página**.
3. Al recuperar conectividad se vacía y el servidor devuelve la jornada
   autoritativa.
4. No se crea una jornada duplicada: se comprueba contando filas en
   PostgreSQL, no confiando en la pantalla.
5. Perder y recuperar la sesión no descarta la acción pendiente (§B, última
   viñeta).

Cómo está montado
-----------------
Se levanta un `uvicorn` real contra la **misma base de tests** que ya sembró la
fixture `seeded` (que hace `commit`, así que otro proceso la ve), y se conduce
el Edge instalado en el sistema — sin descargar ningún navegador. El
`--host 127.0.0.1` con cabecera `Host: alpha.localhost` es solo para la sonda de
arranque: el navegador resuelve `*.localhost` por su cuenta.

Límite honesto: esto es Chromium/Edge de escritorio en Windows. **No** sustituye
la validación V-1/V-4 en hardware iOS/Android real, que sigue pendiente.

La falta de conectividad con la API se simula interceptando las peticiones a
`/api/**` en vez de con `context.set_offline(True)`: el modo offline de
Playwright también bloquea la petición del documento, y entonces no se podría
recargar la página, que es justo lo que hay que probar. Lo que se prueba es lo
mismo —la petición falla y la acción se queda en la cola—, y además permite
recargar.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_maker
from app.routers_api.worksessions.models import WorkSession
from tests.integration.conftest import TEST_PASSWORD


pytestmark = [pytest.mark.integration, pytest.mark.browser]

#: Sin el paquete no hay nada que ejecutar. Se omite en vez de fallar para que
#: la suite siga corriendo en un entorno sin herramientas de navegador.
pytest.importorskip("playwright", reason="playwright no está instalado")


REPO_ROOT = Path(__file__).resolve().parents[2]

#: Lee la cola tal y como la escribe `shared/lib/offlineQueue`. Si la base
#: todavía no existe —o existe sin el almacén— devuelve vacío en vez de fallar:
#: "no hay nada encolado" es una respuesta legítima, no un error.
READ_QUEUE_JS = """
() => new Promise((resolve, reject) => {
    const peticion = indexedDB.open('cer-route-offline');
    peticion.onerror = () => reject(peticion.error);
    peticion.onsuccess = () => {
        const db = peticion.result;
        if (!db.objectStoreNames.contains('pending_actions')) {
            resolve([]);
            return;
        }
        const tx = db.transaction('pending_actions', 'readonly');
        const todas = tx.objectStore('pending_actions').getAll();
        todas.onerror = () => reject(todas.error);
        todas.onsuccess = () => resolve(todas.result);
    };
})
"""

#: Inicia sesión desde dentro del propio navegador, con el mismo intercambio de
#: CSRF que hace la aplicación. Se evita rellenar el formulario a propósito:
#: este test valida la cola, no el marcado del login, y un cambio de maquetación
#: no debería romperlo.
LOGIN_JS = """
async ({ email, password, header }) => {
    const csrf = document.cookie
        .split('; ')
        .find((c) => c.startsWith('cer_csrf_token='));
    const respuesta = await fetch('/api/public/auth/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            [header]: csrf ? csrf.split('=')[1] : '',
        },
        body: JSON.stringify({ email, password }),
    });
    return respuesta.status;
}
"""

CSRF_HEADER = "X-CSRF-Token"


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_server(database_schema):
    """Un `uvicorn` de verdad contra la base de tests, para que haya navegador."""
    puerto = _puerto_libre()
    proceso = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(puerto), "--log-level", "warning",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "MODE": "TEST"},
    )

    limite = time.monotonic() + 90
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            raise RuntimeError("uvicorn terminó antes de aceptar conexiones")
        try:
            respuesta = httpx.get(
                f"http://127.0.0.1:{puerto}/login",
                headers={"Host": f"alpha.{settings.BASE_DOMAIN}"},
                timeout=3,
            )
            if respuesta.status_code < 500:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        proceso.terminate()
        raise RuntimeError("uvicorn no llegó a responder")

    yield f"http://alpha.{settings.BASE_DOMAIN}:{puerto}"

    proceso.terminate()
    try:
        proceso.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proceso.kill()


async def _contar_jornadas(company_id: int, user_id: int) -> int:
    async with async_session_maker() as session:
        return await session.scalar(
            select(func.count())
            .select_from(WorkSession)
            .where(
                WorkSession.company_id == company_id,
                WorkSession.user_id == user_id,
            )
        )


async def _lanzar_edge(playwright):
    """El Edge del sistema, sin descargar ningún navegador.

    Donde no haya —un CI Linux, por ejemplo— el test se omite con un motivo
    explícito: es mejor que un fallo rojo que no señala ningún defecto del
    producto, y mejor que silenciarlo sin decir por qué.
    """
    try:
        return await playwright.chromium.launch(channel="msedge")
    except Exception as error:  # noqa: BLE001 - el mensaje es lo que decide
        if "msedge" in str(error) or "executable doesn't exist" in str(error).lower():
            pytest.skip(f"Microsoft Edge no está disponible en esta máquina: {error}")
        raise


async def _abrir_sesion(page, email: str) -> None:
    await page.goto("/login")
    estado = await page.evaluate(
        LOGIN_JS,
        {"email": email, "password": TEST_PASSWORD, "header": CSRF_HEADER},
    )
    assert estado == 200, f"el login del navegador devolvió {estado}"


async def test_queued_start_work_survives_reload_and_reauthentication(
    seeded, live_server,
):
    """Un solo recorrido de campo, que es como ocurre de verdad.

    Las cinco cosas que pide §B se comprueban en la misma sesión de navegador a
    propósito, y no en tests separados: `seeded` resiembra entre tests y el
    `uvicorn` de al lado cachea la resolución de tenant sesenta segundos, así
    que un segundo test autenticaría contra la compañía anterior. Un único
    recorrido evita ese artefacto del arnés y además describe la secuencia real:
    encolar sin cobertura, reabrir la aplicación, perder la sesión,
    reautenticarse y sincronizar.
    """
    from playwright.async_api import async_playwright

    supervisor = seeded.alpha.users["supervisor"]

    async with async_playwright() as p:
        navegador = await _lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server,
                # Mobile-only: el shell del supervisor se valida al ancho real
                # en el que se usa, no en un escritorio.
                viewport={"width": 390, "height": 844},
            )
            page = await contexto.new_page()
            await _abrir_sesion(page, supervisor.email)

            await page.goto("/route")
            await page.wait_for_selector("text=Ready to start your day?", timeout=20_000)

            # ── Sin API alcanzable ──────────────────────────────────────────
            await contexto.route("**/api/worksessions**", lambda ruta: ruta.abort())

            await page.click("text=Start Work")
            await page.wait_for_selector("text=Starting your day…", timeout=20_000)

            encoladas = await page.evaluate(READ_QUEUE_JS)
            assert len(encoladas) == 1, (
                f"la acción debe quedar en IndexedDB antes de darse por aceptada: {encoladas}"
            )
            assert encoladas[0]["kind"] == "worksession.start"
            assert encoladas[0]["endpoint"] == "/worksessions"

            assert await _contar_jornadas(seeded.alpha.id, supervisor.id) == 0, (
                "nada debe haberse escrito en el servidor todavía"
            )

            # ── Recargar: la durabilidad de verdad ──────────────────────────
            await page.reload()
            await page.wait_for_selector("text=Starting your day…", timeout=20_000)

            tras_recargar = await page.evaluate(READ_QUEUE_JS)
            assert len(tras_recargar) == 1, (
                "la cola tiene que sobrevivir a reabrir la página"
            )
            assert tras_recargar[0]["id"] == encoladas[0]["id"], (
                "la misma acción, con la misma clave de idempotencia"
            )

            # ── Perder la sesión: lo que deja una expiración ────────────────
            # La cola vive en IndexedDB, que no tiene nada que ver con la cookie
            # de sesión. Borrar las cookies no puede perder una acción que el
            # supervisor ya dio por aceptada.
            await contexto.clear_cookies()
            await page.goto("/route")

            sin_sesion = await page.evaluate(READ_QUEUE_JS)
            assert len(sin_sesion) == 1, "la cola no se va con la sesión"
            assert sin_sesion[0]["id"] == encoladas[0]["id"]

            # ── Reautenticación y reconexión ────────────────────────────────
            await _abrir_sesion(page, supervisor.email)
            await contexto.unroute("**/api/worksessions**")
            await page.goto("/route")
            await page.wait_for_selector("text=Working since", timeout=20_000)

            assert await page.evaluate(READ_QUEUE_JS) == [], (
                "lo sincronizado sale de la cola"
            )
            assert await _contar_jornadas(seeded.alpha.id, supervisor.id) == 1, (
                "una sola jornada: ni el replay de la cola ni la reautenticación "
                "pueden duplicarla"
            )
        finally:
            await navegador.close()
