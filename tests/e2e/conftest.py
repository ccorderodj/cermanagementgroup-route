"""
Fixtures para los tests de navegador.

`seeded` vive en `tests/integration/conftest.py` y pytest solo la ofrece a los
tests de ese directorio. Reexportarla aquí evita duplicar la siembra: un segundo
sembrado divergiría del primero en cuanto uno de los dos cambiara, y los tests
de navegador estarían comprobando un tenant que no es el que comprueba el resto
de la suite.

El servidor vivo y por qué es de función
----------------------------------------
Un navegador de verdad necesita un `uvicorn` de verdad, contra la **misma base
de tests** que ya sembró `seeded` (que hace `commit`, así que otro proceso la
ve).

`live_server` tiene alcance de **función**, no de módulo, y cuesta unos segundos
por test. Es deliberado: `seeded` resiembra entre tests y los identificadores de
compañía cambian, mientras el proceso de `uvicorn` cachea la resolución de
tenant sesenta segundos. Con un servidor compartido, el segundo test del módulo
autentica contra la compañía del primero, que ya no existe, y falla con un 401
que no señala ningún defecto del producto. Un servidor nuevo por test empieza
con la caché vacía y elimina esa clase entera de problema.
"""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from app.config import settings
from tests.integration.conftest import (  # noqa: F401
    TEST_PASSWORD,
    _pool_de_un_test,
    alpha_client,
    seeded,
)


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]

CSRF_HEADER = "X-CSRF-Token"

#: Inicia sesión desde dentro del propio navegador, con el mismo intercambio de
#: CSRF que hace la aplicación. Se evita rellenar el formulario a propósito:
#: estos tests validan el ciclo de vida del Admin, no el marcado del login, y un
#: cambio de maquetación no debería romperlos.
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


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live_server(database_schema):
    """Un `uvicorn` real contra la base de tests, uno por test (ver módulo)."""
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
            # Sonda por IP con cabecera `Host`: el navegador resuelve
            # `*.localhost` por su cuenta, pero el resolutor del sistema no
            # tiene por qué hacerlo.
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


async def lanzar_edge(playwright):
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


#: Atenas, Georgia. Sólo hace falta que sea una coordenada válida.
UBICACION_DE_PRUEBA = {"latitude": 33.9519, "longitude": -83.3576}


async def abrir_sesion(page, email: str, *, conceder_ubicacion: bool = True) -> None:
    """Deja la sesión iniciada en el contexto del navegador.

    `conceder_ubicacion` por omisión en `True` desde RTE10-A02: la puerta de
    permiso bloquea My Route cuando el navegador no tiene acceso a la
    ubicación, y lo normal en campo es que un supervisor lo tenga concedido.
    Sin esto, todos los tests de navegador del producto se quedarían mirando la
    puerta en vez del flujo que vienen a comprobar.

    Se concede el permiso **y** se da una coordenada: conceder sin posición deja
    cada captura esperando a un GPS que nunca responde, y convierte suites de
    segundos en suites de minutos.

    Los tests que vienen a comprobar la puerta pasan `False` y construyen su
    propio contexto — ahí la ausencia de permiso es el objeto de la prueba.
    """
    if conceder_ubicacion:
        await page.context.grant_permissions(["geolocation"])
        await page.context.set_geolocation(UBICACION_DE_PRUEBA)
    await page.goto("/login")
    estado = await page.evaluate(
        LOGIN_JS,
        {"email": email, "password": TEST_PASSWORD, "header": CSRF_HEADER},
    )
    assert estado == 200, f"el login del navegador devolvió {estado}"
