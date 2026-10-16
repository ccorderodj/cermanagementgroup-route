"""El ajuste AM/PM de T-1/T-2: horas limpias, sin sufijo de zona.

Decisión del PO: las horas se muestran en 12 h con AM/PM y **sin** sufijo de
zona junto a cada una. La zona de la jornada sigue gobernando la conversión;
sólo deja de imprimirse.

Lo que se comprueba, con navegadores deliberadamente incómodos
--------------------------------------------------------------
* **User Activity, el ejemplo del reporte** (AC-02): una jornada histórica con
  sólo desfase, `5:41 PM UTC-04:00–6:02 PM UTC-04:00`, ahora `5:41–6:02 PM`.
  El navegador está en Tokio y en español: si la hora dependiera de él, saldría
  otra hora o en 24 h.
* **My Route** en un teléfono en español: antes escribía `14:11`; ahora AM/PM.
* **Excepciones de odómetro**, revisadas desde Madrid: la hora es la de la
  jornada del supervisor, no la del administrador (AC-04).

La hora esperada se calcula aquí a partir del instante del API, así que nada
depende de la hora a la que se ejecute. Capturas en
`var/screenshots/time-format/`, fuera del árbol versionado.
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from playwright.async_api import expect
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge
from tests.e2e.test_rte08_activity_explorer_browser import DIA, _historia

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

DESTINO = pathlib.Path("var/screenshots/time-format")
ESCRITORIO = {"width": 1280, "height": 900}
MOVIL = {"width": 390, "height": 844}
ESTE = "America/New_York"

#: Una hora en 24 h (`14:11`) que no vaya seguida de AM/PM.
VEINTICUATRO_HORAS = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b(?!\s*[AP]M)")


def _reloj(instante: datetime, zona: str) -> str:
    local = instante.astimezone(ZoneInfo(zona))
    hora = local.hour % 12 or 12
    return f"{hora}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


async def test_user_activity_compacta_el_tramo_del_reporte(
    seeded, alpha_client, live_server
):
    """AC-02: `ABC Manufacturing · 5:41–6:02 PM`, sin `UTC-04:00`."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await _historia(alpha_client, seeded, unidad="V-AMPM")
    # La jornada histórica del reporte: sin zona IANA, sólo con el desfase del
    # Este, y la parada de 17:41 a 18:02 hora local de ese desfase.
    salida = datetime(DIA.year, DIA.month, DIA.day, 21, 41, tzinfo=timezone.utc)
    fin = salida + timedelta(minutes=21)
    async with async_session_maker() as s:
        await s.execute(
            text(
                "UPDATE work_session SET start_time_zone = NULL, "
                "start_utc_offset_minutes = -240 WHERE company_id = :c"
            ),
            {"c": seeded.alpha.id},
        )
        await s.execute(
            text(
                "UPDATE trip SET started_at = :s, arrived_at = :l WHERE company_id = :c"
            ),
            {"s": salida, "l": salida + timedelta(minutes=8), "c": seeded.alpha.id},
        )
        await s.execute(
            text(
                "UPDATE activity_execution SET started_at = :a, ended_at = :f "
                "WHERE company_id = :c"
            ),
            {"a": salida + timedelta(minutes=10), "f": fin, "c": seeded.alpha.id},
        )
        await s.commit()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            for viewport, sufijo in ((ESCRITORIO, "escritorio"), (MOVIL, "movil")):
                contexto = await navegador.new_context(
                    base_url=live_server,
                    viewport=viewport,
                    timezone_id="Asia/Tokyo",
                    locale="es-ES",
                )
                page = await contexto.new_page()
                await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
                await page.goto(f"/admin/route/activity?range=day&date={DIA.isoformat()}")
                tramo = page.get_by_text("ABC Manufacturing · 5:41–6:02 PM")
                await expect(tramo).to_be_visible(timeout=20_000)
                await page.screenshot(
                    path=str(DESTINO / f"user-activity-{sufijo}.png"), full_page=True
                )
                texto = await tramo.inner_text()
                assert "UTC" not in texto and "EDT" not in texto, texto
                await contexto.close()
        finally:
            await navegador.close()


async def test_my_route_escribe_am_pm_en_un_telefono_en_espanol(
    seeded, alpha_client, live_server
):
    """Antes `Working since 14:11`; ahora la hora de la jornada con AM/PM."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server,
                viewport=MOVIL,
                timezone_id=ESTE,
                locale="es-ES",
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)
            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("What's next?")).to_have_count(
                1, timeout=20_000
            )

            await alpha_client.login(seeded.alpha.users["supervisor"].email)
            jornada = (
                await alpha_client.get("/api/worksessions/current")
            ).json()["work_session"]
            # El teléfono mandó su zona al empezar (T-1/T-2).
            assert jornada["start_time_zone"] == ESTE
            esperada = _reloj(datetime.fromisoformat(jornada["started_at"]), ESTE)

            cabecera = page.get_by_text(esperada, exact=True)
            await expect(cabecera).to_be_visible(timeout=20_000)
            await page.screenshot(
                path=str(DESTINO / "my-route-movil-es.png"), full_page=True
            )
            assert not VEINTICUATRO_HORAS.search(await page.inner_text("body"))
        finally:
            await navegador.close()


async def test_las_excepciones_se_leen_en_la_hora_de_la_jornada(
    seeded, alpha_client, live_server
):
    """AC-04: el administrador en Madrid ve la hora del supervisor del Este."""
    from playwright.async_api import async_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Ford", "model": "Transit", "year": 2023, "unit": "V-EXC",
                "fuel_grade": "regular", "operational_mpg": "19.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (
        await alpha_client.post("/api/worksessions", json={"time_zone": ESTE})
    ).json()
    pedida = await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/exception",
        json={"reason": "camera_unavailable"},
    )
    assert pedida.status_code in (200, 201), pedida.text

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cola = (await alpha_client.get("/api/odometer/exceptions/pending")).json()
    assert cola and cola[0]["time_zone"] == ESTE
    local = datetime.fromisoformat(cola[0]["requested_at"]).astimezone(ZoneInfo(ESTE))
    esperada = f"{local.strftime('%b')} {local.day}, {_reloj(local, ESTE)}"

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server,
                viewport=ESCRITORIO,
                timezone_id="Europe/Madrid",
                locale="es-ES",
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)
            await page.goto("/admin/route/odometer-exceptions")
            await expect(page.get_by_text(esperada)).to_be_visible(timeout=20_000)
            await page.screenshot(
                path=str(DESTINO / "excepciones-madrid.png"), full_page=True
            )
        finally:
            await navegador.close()
