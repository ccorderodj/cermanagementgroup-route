"""
Las travesías de RTE04 que la línea base certificada de A02 obliga a añadir.

Qué cubre y por qué no estaba antes
------------------------------------
RTE04 se validó en navegador cuando el Administrador de CER Route **no podía**
ejecutar trabajo de campo: A02 lo cambió, así que su recorrido operativo nunca se
había recorrido. Eso es RV-01, y la resolución dice expresamente que no se infiera
de la tabla de capacidades.

Se añaden además las tres piezas que faltaban de las quince travesías exigidas:

* los dos contextos de pre-viaje que no se habían tocado en navegador —Check
  Delivery y Office—, porque el 403 que los hacía imposibles de arrancar vivía
  justo ahí y conviene que quede una red sobre cada uno;
* **Continue Working**, la mitad de D-07 que nadie había recorrido: se validó
  terminar de todos modos, no seguir trabajando;
* que una acción rechazada por el servidor **no vuelva** de la cola, que es KD-04
  y el defecto más silencioso de todos — un End Work abandonado reapareciendo
  días después para cerrar una jornada que nadie pidió cerrar.

Sin `data-testid`
-----------------
El build de producción los elimina; estos tests corren contra ese bundle y se
anclan en texto, rol e `id`.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from sqlalchemy import func, select, text

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}

FOTO_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

#: Lee la cola durable tal y como la escribe `shared/lib/offlineQueue`.
LEER_COLA = """
() => new Promise((resolve, reject) => {
    const peticion = indexedDB.open('cer-route-offline');
    peticion.onerror = () => reject(peticion.error);
    peticion.onsuccess = () => {
        const db = peticion.result;
        if (!db.objectStoreNames.contains('pending_actions')) { resolve([]); return; }
        const tx = db.transaction('pending_actions', 'readonly');
        const todas = tx.objectStore('pending_actions').getAll();
        todas.onerror = () => reject(todas.error);
        todas.onsuccess = () => resolve(todas.result);
    };
})
"""


async def _flota(alpha_client, seeded, *, unidad: str, para: str) -> None:
    """Deja a ese usuario con vehículo, que es lo que hace falta odómetro."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users[para].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": unidad,
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )


async def _capturar_odometro(page, lectura: str) -> None:
    await expect(
        page.get_by_text("Take a photo of the odometer, then confirm the reading.")
    ).to_have_count(1, timeout=20_000)
    await page.locator('input[type="file"]').set_input_files(
        {"name": "odo.png", "mimeType": "image/png", "buffer": FOTO_PNG}
    )
    campo = page.locator("#odometer-reading")
    await expect(campo).to_have_count(1, timeout=20_000)
    await campo.fill(lectura)
    await page.get_by_role("button", name="Confirm reading").click()


# ── RV-01: el Administrador ejecuta la ruta ──────────────────────────────────


async def test_the_administrator_runs_the_whole_operational_journey(
    seeded, alpha_client, live_server,
):
    """RV-01, de principio a fin y en el navegador.

    Es el recorrido que nunca se había hecho: cuando RTE04 se validó, el
    Administrador de CER Route no podía ejecutar trabajo de campo. A02 decidió que
    sí —un CEO o un COO usan ese rol y conducen—, así que su travesía operativa
    completa es evidencia nueva, no una repetición de la del Supervisor.

    Start Work → leer valores → planificar → odómetro → salir → cambiar de plan →
    llegar.
    """
    from playwright.async_api import async_playwright

    await _flota(alpha_client, seeded, unidad="V-ADM", para="route_admin")
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, seeded.alpha.users["route_admin"].email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("Working since")).to_have_count(
                1, timeout=20_000
            )

            # El aviso del odómetro aparece y **no** bloquea el trabajo.
            await expect(page.get_by_text("Odometer pending")).to_have_count(1)
            await expect(
                page.get_by_role("button", name="Where to next?")
            ).to_be_enabled()

            # Leer los valores obligatorios: el Administrador los lee con
            # `route.standardvalues.read`, igual que el Supervisor.
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Employee Visit").click()
            await page.get_by_role("combobox").click()
            await page.get_by_role("option", name="Attendance Issue").click()
            await page.get_by_role("button", name="Prepare trip").click()

            await _capturar_odometro(page, "55000")

            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)

            # Cambiar de plan: el mismo viaje, no uno nuevo.
            async with async_session_maker() as session:
                antes = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )
            await page.get_by_role("button", name="Change Plan").click()
            await page.get_by_role("button", name="Change", exact=True).click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Update plan").click()
            await expect(page.get_by_text("Originally:")).to_have_count(
                1, timeout=20_000
            )
            async with async_session_maker() as session:
                despues = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )
            assert despues == antes

            await page.get_by_role("button", name="Arrived", exact=True).click()
            await expect(page.get_by_text("Arrived at")).to_have_count(
                1, timeout=20_000
            )

            # Y la jornada es suya, con su identidad.
            async with async_session_maker() as session:
                propias = await session.scalar(
                    select(func.count()).select_from(WorkSession).where(
                        WorkSession.company_id == seeded.alpha.id,
                        WorkSession.user_id == seeded.alpha.users["route_admin"].id,
                        WorkSession.status == "active",
                    )
                )
            assert propias == 1
        finally:
            await navegador.close()


# ── RV-03: los dos contextos de pre-viaje que faltaban ───────────────────────


@pytest.mark.parametrize(
    "contexto_ui,valor",
    [("Check Delivery", "Payroll Check"), ("Office", "Paperwork")],
    ids=["check-delivery", "office"],
)
async def test_the_remaining_pretrip_values_load_persist_and_let_the_trip_start(
    seeded, alpha_client, live_server, contexto_ui, valor,
):
    """RV-03 para Check Delivery y Office.

    El 403 que hacía imposible arrancar estos contextos vivía justo aquí: el
    formulario exigía un valor de lista y recibía un rechazo al buscar las
    opciones. Se comprueban las tres cosas que pide la resolución —cargan, la
    selección persiste, y Start Trip la acepta— una por contexto.
    """
    from playwright.async_api import async_playwright

    await _flota(alpha_client, seeded, unidad=f"V-{contexto_ui[:3].upper()}", para="supervisor")
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            ctx = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await ctx.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await expect(page.get_by_text("Working since")).to_have_count(
                1, timeout=20_000
            )

            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name=contexto_ui).click()

            # 1) Las opciones cargan — un Supervisor las lee.
            await page.get_by_role("combobox").click()
            await expect(
                page.get_by_role("option", name=valor, exact=True)
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("option", name=valor, exact=True).click()

            # 2) La selección persiste en el formulario.
            await expect(page.get_by_text(valor, exact=True)).to_have_count(1)
            await page.get_by_role("button", name="Prepare trip").click()

            await _capturar_odometro(page, "70000")

            # 3) Start Trip la acepta.
            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)

            async with async_session_maker() as session:
                fila = (
                    await session.execute(
                        text(
                            "SELECT t.status, s.label FROM trip t "
                            "JOIN standard_value s ON s.id = t.current_standard_value_id "
                            "WHERE t.company_id = :c ORDER BY t.id DESC LIMIT 1"
                        ),
                        {"c": seeded.alpha.id},
                    )
                ).one()
            assert fila.status == "in_transit"
            assert fila.label == valor, "el valor elegido queda guardado en el viaje"
        finally:
            await navegador.close()


# ── D-07: la mitad que faltaba — seguir trabajando ───────────────────────────


async def test_continue_working_leaves_the_trip_exactly_as_it_was(
    seeded, alpha_client, live_server,
):
    """Travesía 11: `End Work` con viaje en ruta, y el supervisor decide seguir.

    Se había validado terminar de todos modos; esta es la otra opción, y la que
    más importa que no toque nada: no crea otro viaje, no cambia su estado, y no
    deja una acción esperando en la cola para cerrar el día más tarde.
    """
    from playwright.async_api import async_playwright

    await _flota(alpha_client, seeded, unidad="V-CONT", para="supervisor")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            ctx = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await ctx.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Prepare trip").click()
            await _capturar_odometro(page, "80000")
            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)

            async with async_session_maker() as session:
                antes = (
                    await session.execute(
                        text(
                            "SELECT t.id, t.status, t.version, w.status ws "
                            "FROM trip t JOIN work_session w ON w.id = t.work_session_id "
                            "WHERE t.company_id = :c ORDER BY t.id DESC LIMIT 1"
                        ),
                        {"c": seeded.alpha.id},
                    )
                ).one()

            # End Work abre la revisión…
            await page.get_by_role("button", name="End Work").click()
            await expect(
                page.get_by_text("You are still on route")
            ).to_have_count(1, timeout=20_000)

            # …y se elige seguir trabajando.
            await page.get_by_role("button", name="Cancel").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)

            async with async_session_maker() as session:
                despues = (
                    await session.execute(
                        text(
                            "SELECT t.id, t.status, t.version, w.status ws "
                            "FROM trip t JOIN work_session w ON w.id = t.work_session_id "
                            "WHERE t.company_id = :c ORDER BY t.id DESC LIMIT 1"
                        ),
                        {"c": seeded.alpha.id},
                    )
                ).one()
                cuantos = await session.scalar(
                    select(func.count()).select_from(Trip).where(
                        Trip.company_id == seeded.alpha.id
                    )
                )

            assert despues == antes, "ni el viaje ni la jornada cambiaron"
            assert cuantos == 1, "no se creó otro viaje"

            # Y nada quedó esperando para cerrar el día por su cuenta (KD-04).
            pendientes = await page.evaluate(LEER_COLA)
            assert not [a for a in pendientes if a["kind"] == "worksession.end"], (
                f"un End Work abandonado no puede quedarse en la cola: {pendientes}"
            )
        finally:
            await navegador.close()


# ── KD-04: lo rechazado no vuelve ────────────────────────────────────────────


async def test_a_rejected_end_work_does_not_come_back_from_the_queue(
    seeded, alpha_client, live_server,
):
    """Travesía 15 y KD-04, el defecto más silencioso de todos.

    La cola se detiene en el primer fallo para conservar el orden, así que una
    acción que el servidor rechaza para siempre bloquearía todo lo que venga
    detrás. Y si dejara de bloquear sería peor: el `End Work` que el supervisor
    abandonó al elegir seguir trabajando se reenviaría solo y le cerraría el día
    sin que nadie lo pidiera.

    Un 4xx sale de la cola. Se comprueba leyendo IndexedDB, no la pantalla, y se
    confirma después que la jornada sigue abierta.
    """
    from playwright.async_api import async_playwright

    await _flota(alpha_client, seeded, unidad="V-KD4", para="supervisor")

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            ctx = await navegador.new_context(base_url=live_server, viewport=MOVIL)
            page = await ctx.new_page()
            await abrir_sesion(page, seeded.alpha.users["supervisor"].email)

            await page.goto("/route")
            await page.get_by_role("button", name="Start Work").click()
            await page.get_by_role("button", name="Where to next?").click()
            await page.get_by_role("button", name="Client Visit").click()
            await page.get_by_role("button", name="Prepare trip").click()
            await _capturar_odometro(page, "90000")
            await page.get_by_role("button", name="Start Trip").click()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)

            # `End Work` con el viaje en ruta: el servidor responde 409, que es un
            # rechazo definitivo — reintentarlo diría lo mismo dentro de una hora.
            await page.get_by_role("button", name="End Work").click()
            await expect(
                page.get_by_text("You are still on route")
            ).to_have_count(1, timeout=20_000)
            await page.get_by_role("button", name="Cancel").click()

            pendientes = await page.evaluate(LEER_COLA)
            assert pendientes == [], f"la cola tiene que quedar limpia: {pendientes}"

            # Recargar y reconectar no lo resucita.
            await page.reload()
            await expect(
                page.get_by_role("button", name="Change Plan")
            ).to_have_count(1, timeout=20_000)
            assert await page.evaluate(LEER_COLA) == []

            async with async_session_maker() as session:
                abiertas = await session.scalar(
                    select(func.count()).select_from(WorkSession).where(
                        WorkSession.company_id == seeded.alpha.id,
                        WorkSession.status == "active",
                    )
                )
            assert abiertas == 1, "la jornada sigue abierta; nadie la cerró por detrás"
        finally:
            await navegador.close()
