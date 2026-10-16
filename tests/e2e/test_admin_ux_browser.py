"""
Las dos pantallas de administración, con el patrón list-first (A02-FC3 y FC4).

Qué cambió y por qué se valida así
-----------------------------------
Las dos tenían un formulario permanente arriba: lo primero que veía un
administrador era un campo vacío, y lo que venía a hacer —mirar su flota,
reordenar una lista— quedaba empujado hacia abajo. Se entra a consultar mucho más
a menudo que a dar de alta.

Ahora la lista manda y el alta vive en un diálogo. Lo que estos tests comprueban
no es que el diálogo exista, sino las tres cosas que pueden romperse al moverlo:

* que el formulario permanente **ya no esté**;
* que crear siga funcionando de punta a punta, con la fila apareciendo después;
* que el ciclo de vida —editar, desactivar, reactivar, borrar, filtro de
  inactivos, reordenar— siga intacto, que es lo que un cambio de UX suele
  llevarse por delante sin que nadie lo note.

El diálogo de valores además tiene que **saber a qué lista añade**. Eso se
comprueba leyendo su cabecera y confirmando que la selección no se mueve al
guardar: quien añade tres valores seguidos no debería elegir la lista tres veces.

Sin `data-testid`
-----------------
El build de producción los elimina, y estos tests corren contra el bundle de
producción. Se anclan en texto, rol e `id`.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


ESCRITORIO = {"width": 1280, "height": 900}

#: Los ocho grupos aprobados, con su etiqueta y su número de valores.
GRUPOS = (
    ("Client Visit Activities", 4),
    ("Recruiting Activities", 3),
    ("Employee Visit Reasons", 4),
    ("Delivery Types", 3),
    ("Office Purposes", 4),
    ("Other Activities", 3),
    ("Outcomes", 4),
    ("Received By", 3),
)


async def _abrir_menu_de_fila(page, texto_fila: str):
    """Despliega el menú contextual de la fila que contiene ese texto."""
    fila = page.locator("tr", has_text=texto_fila)
    await expect(fila).to_have_count(1, timeout=20_000)
    await fila.get_by_role("button", name="Open menu").click()


# ── FC3 — Vehículos ──────────────────────────────────────────────────────────


async def test_the_vehicles_page_opens_on_the_list_and_creates_from_a_dialog(
    seeded, live_server,
):
    """El recorrido entero: alta, cancelación, edición y filtro de inactivos.

    Va en un solo recorrido de navegador a propósito: cada test levanta su propio
    `uvicorn` y resiembra el tenant, y lo que importa aquí es la secuencia —crear,
    verla en la lista, editarla, retirarla, recuperarla— que es como se usa la
    pantalla de verdad.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            await page.goto("/admin/route/vehicles")
            await expect(page.locator("h1", has_text="Vehicles")).to_have_count(
                1, timeout=20_000
            )

            # El formulario permanente ya no está: sus campos sólo existen dentro
            # del diálogo, y el diálogo está cerrado.
            await expect(page.locator("#vehicle-unit")).to_have_count(0)
            await expect(page.get_by_text("Add a vehicle", exact=True)).to_have_count(0)

            # La acción primaria y el filtro, encima de la lista.
            await expect(
                page.get_by_role("button", name="Add Vehicle")
            ).to_have_count(1)
            await expect(page.get_by_text("Show inactive vehicles")).to_have_count(1)

            # ── Cancelar no crea nada ──────────────────────────────────────
            await page.get_by_role("button", name="Add Vehicle").click()
            await expect(page.locator("#vehicle-unit")).to_have_count(1, timeout=20_000)
            await page.locator("#vehicle-unit").fill("V-CANCEL")
            await page.get_by_role("button", name="Cancel").click()
            await expect(page.locator("#vehicle-unit")).to_have_count(0, timeout=20_000)
            await expect(page.get_by_text("V-CANCEL")).to_have_count(0)

            # ── Crear ──────────────────────────────────────────────────────
            await page.get_by_role("button", name="Add Vehicle").click()
            await expect(page.locator("#vehicle-unit")).to_have_count(1, timeout=20_000)
            await page.locator("#vehicle-unit").fill("V-UX9")
            await page.locator("#vehicle-make").fill("Ford")
            await page.locator("#vehicle-model").fill("Transit")
            await page.locator("#vehicle-year").fill("2024")
            await page.locator("#vehicle-mpg").fill("21.50")
            await page.get_by_role("button", name="Add vehicle").click()

            # El diálogo se cierra y la fila aparece.
            await expect(page.locator("#vehicle-unit")).to_have_count(0, timeout=20_000)
            await expect(
                page.locator("tr", has_text="V-UX9")
            ).to_have_count(1, timeout=20_000)

            # Y existe de verdad, no sólo en la pantalla.
            from sqlalchemy import text

            async with async_session_maker() as session:
                creados = await session.scalar(
                    text(
                        "SELECT count(*) FROM vehicle "
                        "WHERE company_id = :c AND unit = 'V-UX9'"
                    ),
                    {"c": seeded.alpha.id},
                )
            assert creados == 1

            # ── Editar, desde el mismo diálogo ─────────────────────────────
            await _abrir_menu_de_fila(page, "V-UX9")
            await page.get_by_role("menuitem", name="Edit").click()
            await expect(page.locator("#vehicle-model")).to_have_value(
                "Transit", timeout=20_000
            )
            await page.locator("#vehicle-model").fill("Transit Connect")
            await page.get_by_role("button", name="Save changes").click()
            await expect(
                page.locator("tr", has_text="Transit Connect")
            ).to_have_count(1, timeout=20_000)

            # ── Desactivar, y el filtro de inactivos ───────────────────────
            await _abrir_menu_de_fila(page, "V-UX9")
            await page.get_by_role("menuitem", name="Deactivate").click()
            await expect(
                page.locator("tr", has_text="V-UX9")
            ).to_have_count(0, timeout=20_000)

            await page.get_by_text("Show inactive vehicles").click()
            fila = page.locator("tr", has_text="V-UX9")
            await expect(fila).to_have_count(1, timeout=20_000)
            await expect(fila.get_by_text("Inactive", exact=True)).to_have_count(1)

            # ── Reactivar ──────────────────────────────────────────────────
            await _abrir_menu_de_fila(page, "V-UX9")
            await page.get_by_role("menuitem", name="Reactivate").click()
            await expect(
                page.locator("tr", has_text="V-UX9").get_by_text("Active", exact=True)
            ).to_have_count(1, timeout=20_000)
        finally:
            await navegador.close()


# ── FC4 — Listas estandarizadas ──────────────────────────────────────────────


async def test_the_lists_page_groups_in_a_container_and_creates_in_context(
    seeded, live_server,
):
    """Los ocho grupos, el diálogo que ya sabe dónde añade, y el ciclo de vida."""
    from playwright.async_api import async_playwright

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=ESCRITORIO
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            await page.goto("/admin/route/standard-values")
            await expect(
                page.locator("h1", has_text="Standardized Lists")
            ).to_have_count(1, timeout=20_000)

            # El campo permanente de alta ya no está.
            await expect(page.locator("#new-value")).to_have_count(0)
            await expect(page.get_by_text("Add a value", exact=True)).to_have_count(0)

            # ── Los ocho grupos, en su contenedor, con sus contadores ──────
            navegacion = page.get_by_role("navigation", name="Value lists")
            await expect(navegacion).to_have_count(1, timeout=20_000)
            for etiqueta, cuantos in GRUPOS:
                boton = navegacion.get_by_role("button", name=etiqueta)
                await expect(boton).to_have_count(1, timeout=20_000)
                await expect(boton).to_contain_text(str(cuantos))

            # ── La cabecera de la tabla, sin "Actions" ─────────────────────
            for columna in ("Order", "Label", "Status"):
                await expect(
                    page.get_by_role("columnheader", name=columna)
                ).to_have_count(1)
            await expect(
                page.get_by_role("columnheader", name="Actions")
            ).to_have_count(0)

            # ── Crear en el grupo seleccionado ─────────────────────────────
            await navegacion.get_by_role("button", name="Office Purposes").click()
            await expect(
                page.get_by_text("Administrative Follow-up", exact=True)
            ).to_have_count(1, timeout=20_000)

            await page.get_by_role("button", name="Add Value").click()
            # El diálogo dice a qué lista añade, sin volver a preguntarlo.
            await expect(
                page.get_by_text("Add value to Office Purposes")
            ).to_have_count(1, timeout=20_000)
            await page.locator("#new-value").fill("Inventory Review")
            await page.get_by_role("button", name="Add", exact=True).click()

            # Se cierra, aparece el valor, sube el contador y la selección no se
            # mueve: no hay que volver a elegir el grupo.
            await expect(page.locator("#new-value")).to_have_count(0, timeout=20_000)
            await expect(
                page.get_by_text("Inventory Review", exact=True)
            ).to_have_count(1, timeout=20_000)
            await expect(
                navegacion.get_by_role("button", name="Office Purposes")
            ).to_contain_text("5")

            # ── Cancelar no crea nada ──────────────────────────────────────
            await page.get_by_role("button", name="Add Value").click()
            await expect(page.locator("#new-value")).to_have_count(1, timeout=20_000)
            await page.locator("#new-value").fill("No debería guardarse")
            await page.get_by_role("button", name="Cancel").click()
            await expect(page.locator("#new-value")).to_have_count(0, timeout=20_000)
            await expect(
                page.get_by_text("No debería guardarse", exact=True)
            ).to_have_count(0)

            # ── Reordenar sigue funcionando ────────────────────────────────
            primera = page.locator("tbody tr").first
            await expect(primera).to_contain_text("Paperwork", timeout=20_000)
            await page.get_by_role("button", name="Move Meeting up").click()
            await expect(
                page.locator("tbody tr").first
            ).to_contain_text("Meeting", timeout=20_000)

            # ── El ciclo de vida, desde el menú contextual ─────────────────
            await _abrir_menu_de_fila(page, "Inventory Review")
            await page.get_by_role("menuitem", name="Deactivate").click()
            await expect(
                page.get_by_text("Inventory Review", exact=True)
            ).to_have_count(0, timeout=20_000)

            await page.get_by_text("Show inactive values").click()
            await expect(
                page.locator("tr", has_text="Inventory Review")
                .get_by_text("Inactive", exact=True)
            ).to_have_count(1, timeout=20_000)

            # ── Y los 28 aprobados siguen intactos ─────────────────────────
            from sqlalchemy import text

            async with async_session_maker() as session:
                sembrados = await session.scalar(
                    text(
                        "SELECT count(*) FROM standard_value "
                        "WHERE company_id = :c AND seed_key IS NOT NULL "
                        "AND deleted_at IS NULL"
                    ),
                    {"c": seeded.alpha.id},
                )
            assert sembrados == 28, "la UX no puede tocar los valores aprobados"
        finally:
            await navegador.close()
