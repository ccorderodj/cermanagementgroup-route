"""
Las travesías de A03 en navegador: lo que el administrador ve y puede hacer.

Qué sólo se puede demostrar aquí
--------------------------------
La integración ya prueba que el servidor clasifica y readmite. Lo que A03
arregla es que **el administrador se enterara**: antes, una contraseña corta y
un nombre repetido producían el mismo aviso —`Submission failed`— sin decir qué
corregir ni ofrecer salida. Eso no se puede comprobar con un test de API: hay
que mirar la pantalla.

Sin `data-testid`
-----------------
El build de producción los elimina. Todo se ancla en texto, rol e `id`.
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


ESCRITORIO = {"width": 1280, "height": 900}
BUENA = "Contrasena10"
# El respaldo del cliente cuando el cuerpo del error no dice nada utilizable.
RESPALDO = 'Something went wrong. Please try again.'


@asynccontextmanager
async def _navegador(live_server, email: str):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


async def _abrir_alta(page) -> None:
    """Configuration → Users → Create User, por navegación normal.

    El disparador del panel y el botón de envío del formulario se llaman igual,
    así que una vez abierto el diálogo hay dos. Se pulsa el del panel **antes**
    de abrirlo, cuando es el único, y después el envío se localiza por su tipo.
    """
    await page.goto("/admin/route/users")
    disparador = page.get_by_role("button", name="Create User")
    await expect(disparador).to_have_count(1, timeout=20_000)
    await disparador.click()
    await expect(page.locator("#security-user-username")).to_have_count(
        1, timeout=20_000
    )


def _enviar(page):
    """El botón de envío del formulario, no el del panel."""
    return page.locator('form button[type="submit"]')


async def _rellenar(page, *, username: str, password: str, rol: str) -> None:
    await page.locator("#security-user-username").fill(username)
    await page.locator("#security-user-email").fill(f"{username}@example.com")
    await page.locator("#security-user-first-name").fill("Nueva")
    await page.locator("#security-user-last-name").fill("Persona")
    await page.locator("#security-user-password").fill(password)
    await page.locator("#security-user-confirm-password").fill(password)
    await page.locator("#security-user-gender").click()
    await page.get_by_role("option", name="Male", exact=True).click()
    await page.locator("#security-user-status").click()
    await page.get_by_role("option", name="Active", exact=True).click()
    await page.locator("#security-user-role").click()
    await page.get_by_role("option", name=rol, exact=True).click()


async def _pertenencias(company_id: int, username: str) -> list[dict]:
    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                'SELECT uc.id, uc.is_active, uc.deleted_at, uc.role_id '
                'FROM user_company uc JOIN "user" u ON u.id = uc.user_id '
                "WHERE uc.company_id = :c AND u.username = :n ORDER BY uc.id"
            ),
            {"c": company_id, "n": username},
        )
        return [dict(f._mapping) for f in filas]


# ── FR-01: el mínimo, dicho y validado ──────────────────────────────────────


async def test_the_form_states_the_real_minimum_and_rejects_short_passwords(
    seeded, live_server,
):
    """FR-01 y AC-01/02/03.

    `old expectation` — el formulario decía «at least 6 characters» y validaba
    con 6, mientras el servidor exigía 10.

    `approved A03 decision` — D-A03-01: alinear la pantalla al mínimo
    autoritativo del servidor, que es 10.

    `new expectation` — el requisito se **dice antes de escribir**, y 6 y 9
    producen un error en el campo de la contraseña, no un aviso genérico.
    """
    administrador = seeded.alpha.users["route_admin"]

    async with _navegador(live_server, administrador.email) as (_c, page):
        await _abrir_alta(page)

        # El requisito está a la vista, y con el número del servidor.
        await expect(page.get_by_text("Minimum 10 characters")).to_have_count(1)
        await expect(page.get_by_text("at least 6 characters")).to_have_count(0)

        await _rellenar(page, username="corta", password="a" * 9, rol="Supervisor")
        await _enviar(page).click()

        # El error va al campo, y dice el número correcto.
        await expect(
            page.get_by_text("Password must be at least 10 characters")
        ).to_have_count(1, timeout=20_000)
        # Y no es sólo un aviso genérico (AC-06).
        await expect(page.get_by_text("Submission failed")).to_have_count(0)

    assert await _pertenencias(seeded.alpha.id, "corta") == [], (
        "una validación fallida no crea nada"
    )


# ── FR-03/FR-04: ya trabaja aquí ────────────────────────────────────────────


async def test_an_active_duplicate_is_explained_at_the_username_field(
    seeded, live_server, alpha_client,
):
    """FR-04 y AC-07: se explica que ya existe, en el campo que lo causa.

    `old expectation` — `Username already exists…` colapsado en
    `Submission failed`, sin salida.

    `approved A03 decision` — D-A03-02 y FR-03: el conflicto se nombra y es
    accionable.

    `new expectation` — el mensaje aparece en el campo del nombre de usuario, y
    **no** se ofrece readmitir a quien no se fue.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    async with async_session_maker() as session:
        nombre = await session.scalar(
            text('SELECT username FROM "user" WHERE id = :i'),
            {"i": seeded.alpha.users["supervisor"].id},
        )

    async with _navegador(live_server, seeded.alpha.users["route_admin"].email) as (
        _c, page,
    ):
        await _abrir_alta(page)
        await _rellenar(page, username=nombre, password=BUENA, rol="Supervisor")
        await _enviar(page).click()

        await expect(
            page.get_by_text("already exists in this company")
        ).to_have_count(1, timeout=20_000)
        await expect(page.get_by_role("button", name="Re-add user")).to_have_count(0)


# ── FR-06/FR-07: la readmisión, con confirmación explícita ──────────────────


async def test_a_removed_user_is_re_added_only_after_explicit_confirmation(
    seeded, live_server, alpha_client,
):
    """FR-06, FR-07, §10 y AC-09/13/14: el corazón de A03.

    Se comprueba lo que la instrucción pide en ese orden: que el primer Submit
    **no** restaure en silencio, que la confirmación identifique a la persona y
    diga el rol, que Cancel no escriba nada, y que confirmar devuelva el acceso
    reutilizando la misma identidad.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (
        await alpha_client.post(
            "/api/route/users",
            json={
                "username": "readmitida",
                "email": "readmitida@example.com",
                "first_name": "Vuelve",
                "last_name": "Persona",
                "password": BUENA,
                "gender": True,
                "role_id": seeded.alpha.roles["supervisor"],
            },
        )
    ).json()
    await alpha_client.delete(f"/api/route/users/{creado['id']}")

    antes = await _pertenencias(seeded.alpha.id, "readmitida")
    assert len(antes) == 1 and antes[0]["deleted_at"] is not None

    async with _navegador(live_server, seeded.alpha.users["route_admin"].email) as (
        _c, page,
    ):
        await _abrir_alta(page)
        await _rellenar(
            page, username="readmitida", password=BUENA, rol="Administrador"
        )
        await _enviar(page).click()

        # El primer Submit **no** restaura: pide confirmación.
        await expect(page.get_by_text("Re-add user?")).to_have_count(
            1, timeout=20_000
        )
        await expect(
            page.get_by_text("previously belonged to this company")
        ).to_have_count(1)
        # Nada de vocabulario interno en lo que se lee.
        for interno in ("user_company", "deleted_at", "tombstone"):
            await expect(page.get_by_text(interno)).to_have_count(0)

        # Cancel no escribe nada (§10).
        await page.get_by_role("button", name="Cancel").click()
        sin_cambios = await _pertenencias(seeded.alpha.id, "readmitida")
        assert sin_cambios[0]["deleted_at"] is not None, "Cancel no puede mutar"

        # Y confirmando, se restaura.
        await _enviar(page).click()
        await expect(page.get_by_text("Re-add user?")).to_have_count(
            1, timeout=20_000
        )
        await page.get_by_role("button", name="Re-add user").click()
        await expect(
            page.get_by_text("access to this company has been restored")
        ).to_have_count(1, timeout=20_000)

    despues = await _pertenencias(seeded.alpha.id, "readmitida")
    assert len(despues) == 1, "no se crea una segunda pertenencia"
    assert despues[0]["id"] == antes[0]["id"], "es la misma fila"
    assert despues[0]["deleted_at"] is None
    assert despues[0]["is_active"] is True
    assert despues[0]["role_id"] == seeded.alpha.roles["route_admin"], (
        "se aplica el rol elegido en el formulario"
    )

    async with async_session_maker() as session:
        identidades = await session.scalar(
            text('SELECT count(*) FROM "user" WHERE username = :n'),
            {"n": "readmitida"},
        )
    assert identidades == 1, "una sola identidad de plataforma"


# ── D-A03-06: sólo dos roles, también aquí ──────────────────────────────────


async def test_the_route_form_offers_only_the_two_product_roles(
    seeded, live_server,
):
    """AC-15/16: readmitir no abre una puerta a los roles del núcleo.

    Es la protección de A02 y sigue intacta: el formulario de CER Route ofrece
    exactamente Administrador y Supervisor. El servidor lo vuelve a comprobar
    por su cuenta, y eso lo cubre la integración.
    """
    async with _navegador(live_server, seeded.alpha.users["route_admin"].email) as (
        _c, page,
    ):
        await _abrir_alta(page)
        await page.locator("#security-user-role").click()

        for permitido in ("Administrador", "Supervisor"):
            await expect(
                page.get_by_role("option", name=permitido, exact=True)
            ).to_have_count(1, timeout=20_000)
        for prohibido in ("owner", "admin", "manager", "viewer"):
            await expect(
                page.get_by_role("option", name=prohibido, exact=True)
            ).to_have_count(0)


# ── FR-02 y §13.19-20: lo que el cliente no puede provocar por sí solo ──────


def _solo_al_crear(estado: int, cuerpo: str):
    """Responde `cuerpo` al POST de creación y deja pasar todo lo demás.

    El filtro por método no es cosmético: la misma URL sirve el listado del
    panel, y capturarlo también dejaría la pantalla sin datos por una razón que
    no tiene nada que ver con lo que se está probando.
    """

    async def manejar(ruta):
        if ruta.request.method != "POST":
            await ruta.fallback()
            return
        await ruta.fulfill(
            status=estado, content_type="application/json", body=cuerpo
        )

    return manejar


async def test_a_server_validation_error_lands_on_its_field(seeded, live_server):
    """FR-02 y AC-05: un 422 del servidor llega **al campo que nombra**.

    Hay que interceptar la petición, y no es un atajo. El cliente valida la
    longitud antes de enviar —FR-01—, así que el 422 de contraseña del servidor
    es inalcanzable desde la pantalla: probar sólo el camino alcanzable dejaría
    el **mapeo** sin evidencia, y el mapeo es lo que FR-02 pide. El cuerpo que
    se devuelve es el que Pydantic emite de verdad, con su `loc`.
    """
    administrador = seeded.alpha.users["route_admin"]

    async with _navegador(live_server, administrador.email) as (contexto, page):
        await _abrir_alta(page)
        await contexto.route(
            "**/api/route/users",
            _solo_al_crear(
                422,
                '{"detail":[{"loc":["body","password"],'
                '"msg":"String should have at least 10 characters",'
                '"type":"string_too_short"}]}',
            ),
        )

        await _rellenar(page, username="mapeada", password=BUENA, rol="Supervisor")
        await _enviar(page).click()

        # El mensaje del servidor, junto al campo del servidor.
        mensaje = page.get_by_text("String should have at least 10 characters")
        await expect(mensaje).to_have_count(1, timeout=20_000)
        # Y el aviso dirige a los campos, en vez de repetir el fallo.
        await expect(
            page.get_by_text("Please review the highlighted fields.")
        ).to_have_count(1)
        # Nada de `loc` ni de JSON crudo en pantalla.
        await expect(page.get_by_text('"loc"')).to_have_count(0)


def _reintento_del_aviso(page):
    """El botón `Try again` del aviso, localizado **dentro** del aviso.

    No por rol, y la razón es del producto, no del test: mientras el diálogo de
    creación está abierto, Radix marca `aria-hidden="true"` todo lo que queda
    fuera de él, y el avisador se monta en la raíz. El botón se ve y se pulsa
    —`is_visible()` es cierto—, pero sale del árbol de accesibilidad:
    `get_by_role` devuelve 0 y con `include_hidden=True` devuelve 1. Es un hueco
    de accesibilidad real, ajeno al alcance de A03, y queda reportado como
    hallazgo incidental en vez de corregido de tapadillo.
    """
    return page.locator("li[data-state=open]").filter(
        has_text=RESPALDO
    ).locator("button", has_text="Try again")


@pytest.mark.parametrize(
    "estado,cuerpo,caso",
    [
        (500, '{"detail":"Internal Server Error"}', "inesperado"),
        (422, '{"detail":{"unexpected":"shape"}}', "malformado"),
    ],
    ids=["error-inesperado", "validacion-malformada"],
)
async def test_an_unexpected_or_malformed_error_falls_back_safely(
    seeded, live_server, estado, cuerpo, caso,
):
    """§13.19 y §13.20: el respaldo no deja la pantalla muda ni rota.

    Un 500 y un 422 con una forma que nadie previó. Los dos acaban en el mismo
    respaldo, y por caminos distintos: el 422 malformado no trae `code` ni la
    lista de Pydantic, así que `interpretarDetalle` cae en el mensaje genérico;
    el 500 no llega siquiera como cuerpo —`handleAsyncError` sólo reenvía el del
    servidor para 400, 401, 403, 404, 409 y 422, y para el resto rechaza con la
    cadena `Request failed with status 500`—, que tampoco tiene `detail`.

    Que el 500 **no** enseñe `Internal Server Error` es lo correcto: el texto
    interno del servidor no es un mensaje para el administrador.
    """
    administrador = seeded.alpha.users["route_admin"]
    nombre = f"respaldo{caso}"

    async with _navegador(live_server, administrador.email) as (contexto, page):
        await _abrir_alta(page)
        await contexto.route("**/api/route/users", _solo_al_crear(estado, cuerpo))

        await _rellenar(page, username=nombre, password=BUENA, rol="Supervisor")
        await _enviar(page).click()

        # Hay aviso, y dice qué no se pudo hacer.
        await expect(page.get_by_text(RESPALDO)).to_have_count(1, timeout=20_000)
        await expect(page.get_by_text("Could not create user")).to_have_count(1)
        # Ofrece salida, visible y pulsable.
        await expect(_reintento_del_aviso(page)).to_be_visible()
        # Sin filtraciones: ni el texto interno del 500 ni las claves del cuerpo.
        await expect(page.get_by_text("Internal Server Error")).to_have_count(0)
        await expect(page.get_by_text("unexpected")).to_have_count(0)
        # Y el formulario sigue en pie, con lo escrito: se puede reintentar.
        await expect(page.locator("#security-user-username")).to_have_value(nombre)

    assert await _pertenencias(seeded.alpha.id, nombre) == [], (
        "un error no puede crear nada"
    )
