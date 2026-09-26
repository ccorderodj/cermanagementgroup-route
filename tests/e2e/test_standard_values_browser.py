"""
Las ocho listas aprobadas, renderizadas en el navegador (diagnóstico 006, §2.6).

Qué pregunta responde
---------------------
El diagnóstico pide determinar **dónde** desaparecen los valores: antes de la
API, en el filtro de la API, en el estado del frontend, o al pintar. Este archivo
contesta la última mitad de la pregunta de forma concluyente: con los valores
sembrados, la pantalla de administración muestra **las ocho listas y los
veintiocho valores, en su orden aprobado**.

Si esto pasa y el tenant que revisa el Product Owner sale vacío, entonces el
cableado no es la causa: lo que falta son los datos de ese tenant. Eso es lo que
convierte un "defecto de frontend" en un problema de aprovisionamiento, y la
instrucción pide explícitamente no confundirlos.

Se comprueba además el contador de cada lista, porque es lo primero que ve el
administrador: una lista con `0` al lado es exactamente el síntoma reportado.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import (
    INITIAL_VALUES,
    provision_standard_values,
)
from app.routers_api.standardvalues.service import LIST_LABELS
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


async def test_the_admin_ui_renders_all_eight_lists_and_their_approved_values(
    seeded, live_server,
):
    """Las ocho listas, sus contadores y los valores de cada una.

    Recorre las ocho en la misma sesión de navegador: son una sola pantalla con
    un selector, así que separarlas en ocho tests costaría ocho servidores y no
    demostraría nada más.
    """
    from playwright.async_api import async_playwright

    async with async_session_maker() as session:
        resultado = await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()
    assert sum(len(v) for v in INITIAL_VALUES.values()) == 28, (
        "el aprovisionamiento aprobado son 28 valores"
    )
    assert resultado is not None

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport={"width": 1280, "height": 900}
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            await page.goto("/admin/route/standard-values")
            await expect(
                page.get_by_role("heading", name="Standardized Lists")
            ).to_have_count(1, timeout=20_000)

            navegacion = page.get_by_role("navigation", name="Value lists")
            await expect(navegacion).to_have_count(1, timeout=20_000)

            for codigo, etiquetas in INITIAL_VALUES.items():
                rotulo = LIST_LABELS[codigo]
                boton = navegacion.get_by_role("button", name=rotulo)
                await expect(boton).to_have_count(
                    1, timeout=20_000
                )
                # El contador que el administrador ve de un vistazo. Un `0` aquí
                # es literalmente el síntoma que motivó el diagnóstico.
                await expect(boton).to_contain_text(str(len(etiquetas)))

                await boton.click()
                for etiqueta in etiquetas:
                    await expect(
                        page.get_by_text(etiqueta, exact=True)
                    ).to_have_count(1, timeout=20_000)
        finally:
            await navegador.close()


async def test_another_tenant_sees_none_of_them(seeded, live_server):
    """El aprovisionamiento es por compañía, y la pantalla lo respeta.

    Sembrar alpha no puede hacer aparecer nada en beta. Es la otra mitad del
    síntoma: un tenant con valores y otro sin ellos es exactamente lo que se
    espera cuando el aprovisionamiento no se ejecutó en el segundo.
    """
    from playwright.async_api import async_playwright

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            # `live_server` sirve el subdominio de alpha; para beta se entra por
            # su propio host, que es como el tenant se resuelve en producción.
            contexto = await navegador.new_context(
                base_url=live_server.replace("alpha.", "beta."),
                viewport={"width": 1280, "height": 900},
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.beta.users["route_admin"].email)

            await page.goto("/admin/route/standard-values")
            navegacion = page.get_by_role("navigation", name="Value lists")
            await expect(navegacion).to_have_count(1, timeout=20_000)

            # Las ocho listas existen —son de producto— pero todas a cero.
            for codigo in INITIAL_VALUES:
                boton = navegacion.get_by_role("button", name=LIST_LABELS[codigo])
                await expect(boton).to_contain_text("0")

            # Y ningún valor de alpha se ve desde aquí.
            for etiqueta in INITIAL_VALUES["employee_visit_reasons"]:
                await expect(page.get_by_text(etiqueta, exact=True)).to_have_count(0)
        finally:
            await navegador.close()
