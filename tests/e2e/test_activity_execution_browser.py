"""
Las travesías de RTE05 en un navegador real, contra el bundle de producción.

Qué se valida aquí y no en la integración
------------------------------------------
La integración ya demuestra las reglas: un bloque por parada, el resultado
obligatorio, la guarda de `End Work`, la idempotencia. Lo que sólo se puede
demostrar en el navegador es que **el supervisor llega a ellas**: que el
contexto que no debe preguntar no pregunta, que el que sí debe preguntar
pregunta al llegar y no antes, que recargar devuelve a la parada en marcha, y
que el rechazo del servidor aparece en pantalla en vez de perderse en una cola.

Sin odómetro, a propósito
-------------------------
Ninguna de estas travesías asigna vehículo. Sin vehículo la evidencia nace
`NOT_REQUIRED` y `Start Trip` no la exige, así que el camino hasta la llegada es
corto y lo que queda en medio es RTE05 y nada más. El odómetro tiene sus propias
travesías en `test_trip_and_odometer_browser.py` y
`test_rte04_closure_browser.py`; repetirlo aquí alargaría cada test sin añadir
evidencia nueva.

Sin `data-testid`
-----------------
El build de producción los elimina. Todo se ancla en texto, rol e `id`.

Límite honesto
--------------
Esto es Edge de escritorio en Windows a 390x844. **No** sustituye la validación
en hardware iOS/Android real, que sigue `PENDING VALIDATION`.

La travesía 16 —el Supervisor no alcanza la administración de catálogos— no se
repite aquí: la cubre `test_route_access_browser.py`, que comprueba
`/admin/route/standard-values` para el Supervisor y para el Administrador.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import expect
from sqlalchemy import func, select

from app.database import async_session_maker
from app.routers_api.activities.models import (
    ActivityExecution,
    ActivityExecutionActivity,
)
from app.routers_api.standardvalues.provisioning import provision_standard_values
from app.routers_api.trips.models import Trip
from app.routers_api.worksessions.models import WorkSession
from tests.e2e.conftest import abrir_sesion, lanzar_edge


pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")


MOVIL = {"width": 390, "height": 844}

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


# ── Utilidades ───────────────────────────────────────────────────────────────


async def _sembrar_valores(company_id: int) -> None:
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()


@asynccontextmanager
async def _movil(live_server, email: str):
    """Un Edge a tamaño de teléfono, con la sesión ya abierta."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL
            )
            page = await contexto.new_page()
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


async def _hasta_la_llegada(page, *, contexto_ui: str, valor: str | None = None):
    """Start Work → workbench → contexto → Start Trip → Arrived.

    El camino común de todas las travesías. Tras `Start Work` el workbench ya
    está: no hay un botón intermedio que revele las opciones (PD-04), y elegir
    contexto lleva a una sola pantalla que pide sus datos y ofrece `Start Trip`
    (PD-05). Sin vehículo no hay lectura que capturar en medio.
    """
    await page.goto("/route")
    await page.get_by_role("button", name="Start Work").click()
    await expect(page.get_by_text("What's next?")).to_have_count(1, timeout=20_000)

    await page.get_by_role("button", name=contexto_ui, exact=True).click()
    if valor is not None:
        await page.locator("#trip-standard-value").click()
        await page.get_by_role("option", name=valor, exact=True).click()

    await page.get_by_role("button", name="Start Trip").click()
    if contexto_ui == "Return Home":
        await page.get_by_role("button", name="Arrived Home").click()
    else:
        await page.get_by_role("button", name="Arrived", exact=True).click()
        await expect(page.get_by_text("Arrived at")).to_have_count(1, timeout=20_000)


async def _elegir_actividades(page, *etiquetas: str) -> None:
    await expect(page.get_by_text("What are you doing here?")).to_have_count(
        1, timeout=20_000
    )
    for etiqueta in etiquetas:
        await page.get_by_text(etiqueta, exact=True).click()


async def _salir(
    page,
    *,
    accion: str,
    resultado: str,
    receptor: str | None = None,
    nota: str | None = None,
) -> None:
    """Pulsa la salida, rellena lo que exige y confirma.

    `accion` es el texto del botón —"Complete Activity" o "Leave"—, que es el
    mismo en la pantalla en marcha y en la de confirmación: la primera lleva al
    formulario, la segunda lo envía.
    """
    await page.get_by_role("button", name=accion, exact=True).click()
    await expect(page.get_by_text("How did it go?")).to_have_count(1, timeout=20_000)

    await page.locator("#activity-outcome").click()
    await page.get_by_role("option", name=resultado, exact=True).click()

    if receptor is not None:
        await page.locator("#activity-received-by").click()
        await page.get_by_role("option", name=receptor, exact=True).click()

    if nota is not None:
        await page.locator("#activity-notes").fill(nota)

    await page.get_by_role("button", name=accion, exact=True).click()


async def _bloque(company_id: int):
    async with async_session_maker() as session:
        return await session.scalar(
            select(ActivityExecution).where(
                ActivityExecution.company_id == company_id
            )
        )


async def _etiquetas_del_bloque(company_id: int, execution_id: int) -> list[str]:
    async with async_session_maker() as session:
        filas = await session.execute(
            select(ActivityExecutionActivity.label)
            .where(
                ActivityExecutionActivity.company_id == company_id,
                ActivityExecutionActivity.activity_execution_id == execution_id,
            )
            .order_by(ActivityExecutionActivity.sort_order)
        )
        return list(filas.scalars().all())


async def _contar_bloques(company_id: int) -> int:
    async with async_session_maker() as session:
        return await session.scalar(
            select(func.count()).select_from(ActivityExecution).where(
                ActivityExecution.company_id == company_id
            )
        )


async def _estado_del_viaje(company_id: int) -> str | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(Trip.status).where(Trip.company_id == company_id)
        )


async def _estado_de_la_jornada(company_id: int, user_id: int) -> str | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(WorkSession.status).where(
                WorkSession.company_id == company_id,
                WorkSession.user_id == user_id,
            )
        )


# ── J1 · J12 · J14 ───────────────────────────────────────────────────────────


async def test_client_visit_with_two_activities_completes_and_closes_the_trip(
    seeded, live_server,
):
    """Travesías 1, 12 y 14, en un solo recorrido porque son un solo recorrido.

    Dos actividades elegidas, una sola parada: un inicio, un fin, un resultado y
    una nota. Al completar, el viaje queda `closed` y la jornada **sigue
    activa** — terminar una parada no termina el día.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")

        await _elegir_actividades(page, "Service Review", "Safety Follow-up")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        await expect(page.get_by_text("Doing")).to_have_count(1)
        # FR-07: la duración se presenta, no sólo la hora de inicio.
        await expect(page.get_by_text("just started")).to_have_count(1)

        await _salir(
            page,
            accion="Complete Activity",
            resultado="Completed",
            nota="Reviewed the service and walked the floor.",
        )

        # Cerrada la parada, la pantalla vuelve al trabajo: la jornada sigue.
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.status == "completed"
    assert bloque.terminal_action == "complete"
    assert bloque.outcome_label == "Completed"
    assert bloque.notes == "Reviewed the service and walked the floor."
    assert bloque.ended_at is not None

    etiquetas = await _etiquetas_del_bloque(seeded.alpha.id, bloque.id)
    assert etiquetas == ["Service Review", "Safety Follow-up"], (
        "dos actividades son dos etiquetas del mismo bloque, no dos bloques"
    )
    assert await _contar_bloques(seeded.alpha.id) == 1

    assert await _estado_del_viaje(seeded.alpha.id) == "closed"
    assert await _estado_de_la_jornada(seeded.alpha.id, supervisor.id) == "active"


# ── J2 · J13 ─────────────────────────────────────────────────────────────────


async def test_recruiting_with_several_activities_leaves_and_closes_the_trip(
    seeded, live_server,
):
    """Travesías 2 y 13. Marcharse es una salida **controlada**.

    Exige resultado igual que completar, y cierra el viaje igual que completar.
    Lo que cambia es el hecho que queda escrito, no el rigor.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Recruiting")

        await _elegir_actividades(page, "Candidate Sourcing", "Hiring Event")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        await _salir(page, accion="Leave", resultado="No Contact")

        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.status == "left"
    assert bloque.terminal_action == "leave"
    assert bloque.outcome_label == "No Contact"
    assert bloque.notes is None, "la nota es opcional y no se rellena sola"

    etiquetas = await _etiquetas_del_bloque(seeded.alpha.id, bloque.id)
    assert etiquetas == ["Candidate Sourcing", "Hiring Event"]

    assert await _estado_del_viaje(seeded.alpha.id) == "closed"
    assert await _estado_de_la_jornada(seeded.alpha.id, supervisor.id) == "active"


# ── J3 · J5 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "contexto_ui,valor",
    [("Employee Visit", "Attendance Issue"), ("Office", "Paperwork")],
    ids=["employee-visit", "office"],
)
async def test_the_contexts_that_already_asked_do_not_ask_again(
    seeded, live_server, contexto_ui, valor,
):
    """Travesías 3 y 5. Lo que ya se preguntó al planificar no se repite.

    Employee Visit trae su motivo y Office su propósito desde el pre-viaje.
    Poner aquí un selector para que todas las pantallas se parezcan sería
    preguntar dos veces lo mismo, y el dato duplicado acabaría discrepando.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui=contexto_ui, valor=valor)

        # Nada que elegir: sólo empezar.
        await expect(
            page.get_by_role("button", name="Start Activity")
        ).to_have_count(1, timeout=20_000)
        await expect(page.get_by_text("What are you doing here?")).to_have_count(0)

        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        # Y en marcha tampoco hay lista de actividades que enseñar.
        await expect(page.get_by_text("Doing")).to_have_count(0)

        await _salir(page, accion="Complete Activity", resultado="Completed")
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.status == "completed"
    assert await _etiquetas_del_bloque(seeded.alpha.id, bloque.id) == []
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"


# ── J4 ───────────────────────────────────────────────────────────────────────


async def test_check_delivery_asks_who_received_it_only_on_arrival(
    seeded, live_server,
):
    """Travesía 4. Quién recibió sólo se sabe al llegar.

    Por eso se pregunta al cerrar la parada y no al planificar, y por eso es
    obligatorio: una entrega sin receptor registrado no es una entrega
    verificable.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(
            page, contexto_ui="Check Delivery", valor="Payroll Check"
        )

        await expect(page.get_by_text("What are you doing here?")).to_have_count(0)
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        # El formulario de cierre pide el receptor, y sin él no deja confirmar.
        await page.get_by_role("button", name="Complete Activity", exact=True).click()
        await expect(page.get_by_text("Received by")).to_have_count(1, timeout=20_000)
        await page.locator("#activity-outcome").click()
        await page.get_by_role("option", name="Completed", exact=True).click()
        await expect(
            page.get_by_role("button", name="Complete Activity", exact=True)
        ).to_be_disabled()

        await page.locator("#activity-received-by").click()
        await page.get_by_role("option", name="Authorized Person", exact=True).click()
        await page.get_by_role("button", name="Complete Activity", exact=True).click()

        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.received_by_label == "Authorized Person"
    assert bloque.received_by_standard_value_id is not None
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"


# ── J6 ───────────────────────────────────────────────────────────────────────


async def test_other_completes_with_several_activities(seeded, live_server):
    """Travesía 6. `Other` tiene su propia lista y también es multi-selección."""
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Other")

        await _elegir_actividades(
            page, "Housing Visit", "Transportation Support", "Supply Pickup"
        )
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        await _salir(
            page, accion="Complete Activity", resultado="Follow-up Required"
        )
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.outcome_label == "Follow-up Required"
    etiquetas = await _etiquetas_del_bloque(seeded.alpha.id, bloque.id)
    assert etiquetas == ["Housing Visit", "Transportation Support", "Supply Pickup"]


# ── J7 ───────────────────────────────────────────────────────────────────────


async def test_going_home_never_reaches_the_activity_screen(seeded, live_server):
    """Travesía 7. Volver a casa no es una parada de trabajo.

    El viaje se cierra al llegar —eso es RTE04 y no cambia—, así que la pantalla
    de la parada nunca aparece y no queda ningún bloque que resolver. Terminar
    la jornada desde ahí no encuentra nada que reclamar.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Return Home")

        # Ni selector ni bloque: se vuelve directo al trabajo.
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)
        await expect(
            page.get_by_role("button", name="Start Activity")
        ).to_have_count(0)

        await page.get_by_role("button", name="End Work").click()
        # No se afirma "Ending your day…": es transitorio —`reconcile()` lo
        # sustituye en cuanto el servidor confirma— y afirmar un estado que
        # dura un viaje de red es una carrera, no una comprobación. Lo estable
        # es dónde queda el supervisor: sin jornada abierta.
        await expect(page.get_by_text("Ready to start your day?")).to_have_count(
            1, timeout=20_000
        )

    assert await _contar_bloques(seeded.alpha.id) == 0, "volver a casa no ejecuta nada"
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"
    assert await _estado_de_la_jornada(seeded.alpha.id, supervisor.id) == "ended"


# ── J8 ───────────────────────────────────────────────────────────────────────


async def test_reloading_resumes_the_running_execution(seeded, live_server):
    """Travesía 8. Recargar no pierde la parada en marcha.

    El estado autoritativo llega en la misma respuesta que la jornada, así que
    la pantalla vuelve a la parada sin deducir nada: las actividades elegidas
    siguen ahí y la hora de inicio es la original, no la de recargar.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")
        await _elegir_actividades(page, "Staffing Follow-up")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        antes = await page.get_by_text("Working here since").inner_text()

        await page.reload()

        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        assert await page.get_by_text("Working here since").inner_text() == antes, (
            "la hora de la parada es cuando empezó, no cuando se recargó"
        )
        await expect(page.get_by_text("Staffing Follow-up")).to_have_count(1)
        await expect(
            page.get_by_role("button", name="Start Activity")
        ).to_have_count(0)

        # Y desde ahí se puede terminar, que es lo que hace útil reanudar.
        await _salir(page, accion="Complete Activity", resultado="Completed")
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    assert await _contar_bloques(seeded.alpha.id) == 1, (
        "reanudar resuelve el mismo bloque, no crea otro"
    )


# ── J9 ───────────────────────────────────────────────────────────────────────


async def test_a_new_session_resolves_the_same_execution(seeded, live_server):
    """Travesía 9. Reautenticarse, o entrar desde otro dispositivo.

    Se borran las cookies y se vuelve a entrar: es lo que ocurre cuando la
    sesión caduca a media tarde, y es indistinguible de abrir la aplicación en
    un segundo teléfono. En los dos casos el servidor devuelve **la misma**
    parada, y terminarla desde ahí no fabrica una segunda.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (contexto, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")
        await _elegir_actividades(page, "Attendance Follow-up")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        bloque_antes = await _bloque(seeded.alpha.id)
        assert bloque_antes is not None

        await contexto.clear_cookies()
        await abrir_sesion(page, supervisor.email)
        await page.goto("/route")

        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        await expect(page.get_by_text("Attendance Follow-up")).to_have_count(1)

        await _salir(page, accion="Complete Activity", resultado="Escalated")
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque_despues = await _bloque(seeded.alpha.id)
    assert bloque_despues is not None
    assert bloque_despues.id == bloque_antes.id, "la misma parada, no otra"
    assert bloque_despues.status == "completed"
    assert bloque_despues.outcome_label == "Escalated"


# ── J10 ──────────────────────────────────────────────────────────────────────


async def test_end_work_is_not_offered_from_an_unresolved_arrival(
    seeded, live_server,
):
    """Travesía 10, con la expectativa que el cierre 003 sustituye.

    `old expectation` — pulsar `End Work` en la llegada sin resolver y ver el
    409 explicado en pantalla.

    `approved decision` — PD-03 y FR-07 del cierre 003: `End Work` no se expone
    mientras se seleccionan o ejecutan actividades post-llegada, y llegado sin
    resolver la pantalla entra en el flujo de la parada y no vuelve al
    workbench.

    `new expectation` — el botón **no está**. Lo que hay son las dos salidas de
    la parada. La guarda del servidor no cambió y sigue cubierta por la
    integración (`test_end_work_is_blocked_while_the_arrival_is_unresolved`):
    el control está en el backend, la ausencia del botón es experiencia de
    usuario. Tampoco se ofrece el "de todos modos", que es de D-07 y pertenece
    al viaje en ruta.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")

        await expect(page.get_by_text("What are you doing here?")).to_have_count(1)
        await expect(page.get_by_role("button", name="End Work")).to_have_count(0)
        await expect(
            page.get_by_role("button", name="End Work Anyway")
        ).to_have_count(0)
        # Ni se vuelve al workbench con el viaje sin resolver (FR-07).
        await expect(page.get_by_text("What's next?")).to_have_count(0)
        await expect(
            page.get_by_role("button", name="Start Activity")
        ).to_have_count(1)

    assert await _estado_de_la_jornada(seeded.alpha.id, supervisor.id) == "active"
    assert await _estado_del_viaje(seeded.alpha.id) == "arrived"


# ── J11 ──────────────────────────────────────────────────────────────────────


async def test_end_work_is_blocked_while_the_execution_runs(seeded, live_server):
    """Travesía 11. Con la parada en marcha, `End Work` no se ofrece.

    FR-14 lo pide literal: no disponible en la UX. No es esconder una salida —hay
    dos, terminar y marcharse—, es no ofrecer algo que el servidor va a rechazar.
    El rechazo del servidor sigue existiendo y lo cubre la integración
    (`test_end_work_is_blocked_while_the_execution_is_running`): el control está
    en el backend, la ausencia del botón es experiencia de usuario.

    Y al resolverla, `End Work` vuelve: un bloqueo que no se levanta es tan
    defectuoso como uno que no bloquea.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Recruiting")

        # Llegado y sin empezar tampoco se ofrece (PD-03): la parada se
        # resuelve, y el día se cierra después, desde el workbench.
        await expect(page.get_by_role("button", name="End Work")).to_have_count(0)

        await _elegir_actividades(page, "Referral Follow-up")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        await expect(page.get_by_role("button", name="End Work")).to_have_count(0)
        await expect(
            page.get_by_role("button", name="Complete Activity", exact=True)
        ).to_have_count(1)
        await expect(page.get_by_role("button", name="Leave", exact=True)).to_have_count(1)
        assert await _estado_de_la_jornada(seeded.alpha.id, supervisor.id) == "active"

        await _salir(page, accion="Leave", resultado="Follow-up Required")
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

        await page.get_by_role("button", name="End Work").click()
        # No se afirma "Ending your day…": es transitorio —`reconcile()` lo
        # sustituye en cuanto el servidor confirma— y afirmar un estado que
        # dura un viaje de red es una carrera, no una comprobación. Lo estable
        # es dónde queda el supervisor: sin jornada abierta.
        await expect(page.get_by_text("Ready to start your day?")).to_have_count(
            1, timeout=20_000
        )

    assert await _estado_de_la_jornada(seeded.alpha.id, supervisor.id) == "ended"
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"


# ── FR-01 ────────────────────────────────────────────────────────────────────


async def test_losing_the_network_does_not_hide_the_unresolved_stop(
    seeded, live_server,
):
    """FR-01: sin red tampoco se cae en un "Where to next?" genérico.

    El caso real: llega, pierde cobertura, y la pantalla se reconcilia al volver
    a primer plano. Antes colapsaba a la jornada sin viaje y ofrecía planificar
    otro — un viaje que el servidor iba a rechazar, porque hay uno solo vivo por
    jornada, y que además escondía el trabajo que quedaba en la parada.

    Ahora se queda en lo último que el servidor confirmó. Eso es cierto; lo otro
    era una simplificación que inventaba estado.

    Se prueban los **dos** caminos sin red, porque no son el mismo:

    * reconciliación dentro de la misma sesión de página —volver a primer plano,
      recuperar la red, terminar una acción—: se conserva la vista confirmada;
    * recarga completa: la memoria de la página se fue con ella, así que lo
      único cierto es que no se pudo leer el estado, y eso es lo que dice. No
      ofrece "Where to next?" en ninguno de los dos.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (contexto, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")
        await expect(page.get_by_text("What are you doing here?")).to_have_count(1)

        # Se cae la lectura de estado, que es de lo que vive esta pantalla.
        await contexto.route("**/api/worksessions/current", lambda ruta: ruta.abort())

        # Reconciliación en la misma página: es lo que ocurre al volver a primer
        # plano o al recuperar la red.
        await page.evaluate("() => window.dispatchEvent(new Event('online'))")

        await expect(page.get_by_text("Arrived at")).to_have_count(1, timeout=20_000)
        await expect(page.get_by_text("What are you doing here?")).to_have_count(1)
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(0)

        # Recarga sin red: se dice que no se pudo cargar, y tampoco se ofrece
        # planificar otro viaje.
        await page.reload()
        await expect(
            page.get_by_text("Your workday could not be loaded. Check your connection.")
        ).to_have_count(1, timeout=20_000)
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(0)

        # Y al volver la red, el servidor sigue siendo la autoridad.
        await contexto.unroute("**/api/worksessions/current")
        await page.get_by_role("button", name="Try again").click()
        await expect(page.get_by_text("What are you doing here?")).to_have_count(
            1, timeout=20_000
        )

    assert await _estado_del_viaje(seeded.alpha.id) == "arrived"


# ── J15 ──────────────────────────────────────────────────────────────────────


async def test_the_administrator_runs_an_rte05_operational_journey(
    seeded, live_server,
):
    """Travesía 15. El Administrador de CER Route también ejecuta.

    A02 decidió que sí —un CEO o un COO usan ese rol y conducen—, así que su
    recorrido de RTE05 es evidencia propia y no se infiere de la del Supervisor
    ni de la tabla de capacidades.
    """
    await _sembrar_valores(seeded.alpha.id)
    administrador = seeded.alpha.users["route_admin"]

    async with _movil(live_server, administrador.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")
        await _elegir_actividades(page, "Service Review")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )
        await _salir(page, accion="Complete Activity", resultado="Completed")
        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.user_id == administrador.id, (
        "quién ejecuta sale de la sesión, y la sesión es la del Administrador"
    )
    assert bloque.status == "completed"
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"


# ── J17 ──────────────────────────────────────────────────────────────────────


async def test_a_value_retired_mid_flight_is_rejected_on_the_screen(
    seeded, alpha_client, live_server,
):
    """Travesía 17. El valor se retira con la pantalla ya abierta.

    Es el caso real: el supervisor carga la lista, conduce media hora, y para
    entonces un administrador ha desactivado una de las opciones. El servidor lo
    rechaza —es él quien decide qué es elegible, no el navegador— y el rechazo
    **aparece en pantalla**, en vez de quedarse en la cola dando la acción por
    aceptada.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    valores = (
        await alpha_client.get("/api/standard-values/client_visit_activities")
    ).json()
    retirado = next(v for v in valores if v["label"] == "Service Review")

    async with _movil(live_server, supervisor.email) as (_ctx, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")
        await _elegir_actividades(page, "Service Review")

        # Ahora, con la selección hecha y sin recargar.
        respuesta = await alpha_client.put(
            f"/api/standard-values/{retirado['id']}",
            json={"is_active": False, "version": retirado["version"]},
        )
        assert respuesta.status_code == 200, respuesta.text

        await page.get_by_role("button", name="Start Activity").click()
        await expect(
            page.get_by_text("That value cannot be selected here.")
        ).to_have_count(1, timeout=20_000)

        # No se encoló como aceptada y no hay nada que reintentar después.
        assert await page.evaluate(LEER_COLA) == []

    assert await _contar_bloques(seeded.alpha.id) == 0, (
        "un valor no elegible no arranca ninguna parada"
    )
    assert await _estado_del_viaje(seeded.alpha.id) == "arrived"


# ── J18 ──────────────────────────────────────────────────────────────────────


async def test_an_execution_command_survives_a_disconnection(seeded, live_server):
    """Travesía 18. Sin cobertura, la parada se cierra igual — más tarde.

    Se interceptan sólo las peticiones de la parada: así el resto de la pantalla
    sigue leyendo su estado del servidor y lo que se prueba es exactamente la
    durabilidad del comando, no el comportamiento de la aplicación entera a
    oscuras (eso es RTE03 y tiene su propio test).

    Lo que se comprueba: el comando queda en IndexedDB, el servidor **no** lo ha
    aplicado, sobrevive a recargar, y al volver la red se aplica una sola vez.
    """
    await _sembrar_valores(seeded.alpha.id)
    supervisor = seeded.alpha.users["supervisor"]

    async with _movil(live_server, supervisor.email) as (contexto, page):
        await _hasta_la_llegada(page, contexto_ui="Client Visit")
        await _elegir_actividades(page, "Safety Follow-up")
        await page.get_by_role("button", name="Start Activity").click()
        await expect(page.get_by_text("Working here since")).to_have_count(
            1, timeout=20_000
        )

        await contexto.route("**/api/trips/*/activity/**", lambda ruta: ruta.abort())

        await _salir(page, accion="Complete Activity", resultado="Completed")

        encoladas = await page.evaluate(LEER_COLA)
        assert len(encoladas) == 1, f"el comando queda en la cola: {encoladas}"
        assert encoladas[0]["kind"] == "activity.complete"

        bloque = await _bloque(seeded.alpha.id)
        assert bloque is not None and bloque.status == "in_progress", (
            "nada se ha escrito en el servidor todavía"
        )

        # Durabilidad de verdad: recargar no lo pierde.
        await page.reload()
        tras_recargar = await page.evaluate(LEER_COLA)
        assert len(tras_recargar) == 1
        assert tras_recargar[0]["id"] == encoladas[0]["id"], (
            "la misma acción, con la misma clave de idempotencia"
        )

        await contexto.unroute("**/api/trips/*/activity/**")
        await page.goto("/route")

        await expect(
            page.get_by_text("What's next?")
        ).to_have_count(1, timeout=20_000)
        assert await page.evaluate(LEER_COLA) == [], "lo aplicado sale de la cola"

    bloque = await _bloque(seeded.alpha.id)
    assert bloque is not None
    assert bloque.status == "completed"
    assert bloque.outcome_label == "Completed"
    assert await _estado_del_viaje(seeded.alpha.id) == "closed"
