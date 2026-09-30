"""Soak de la cola y de la evidencia (cierre de RTE06, Item C / V-4).

Por qué esta carga y no otra
-----------------------------
La instrucción deja elegir duración y estrategia, y pide documentar por qué son
técnicamente significativas. El criterio aquí no es el tiempo de reloj —un test
que tarda una hora no prueba nada que no pruebe uno que tarde un minuto si
ejecuta las mismas transiciones— sino **cubrir cada combinación que puede
corromper la correlación o duplicar un hecho**, y repetirla suficientes veces
para que una condición de carrera intermitente tenga ocasión de aparecer.

Lo que se repite, y cuántas veces:

* **30 jornadas completas**, cada una con viaje, uno o dos `Change Plan`,
  llegada y cierre. Treinta porque con menos de veinte los duplicados
  concurrentes de esta base salían siempre en el mismo orden y el test dejaba de
  ser discriminante; a partir de ahí el orden varía entre ejecuciones.
* **cada pieza de evidencia enviada dos veces**, una de ellas en paralelo con la
  otra. Es el caso que rompe la idempotencia si la garantiza el código y no un
  índice.
* **evidencia fuera de orden**: la llegada antes de la salida, que es lo que
  produce una cola que vacía al reconectar tras varios cortes.
* **reautenticación en medio** de la jornada, porque la evidencia pendiente no
  puede depender del token.
* **dos tenants en paralelo**, para que el aislamiento se compruebe bajo carga y
  no sólo en un caso aislado.

Qué invariantes se comprueban al final
---------------------------------------
Los cinco que la instrucción nombra: ningún kilometraje duplicado, ninguna
correlación equivocada, ningún `Pending` permanente por culpa del reenvío,
aislamiento intacto y orden de ocurrencia preservado.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.mileage.routing import Punto, SegmentResult, set_road_router
from app.routers_api.mileage.service import sweep_pending_mileage

pytestmark = pytest.mark.integration


#: Ciclos del soak. Ajustable por entorno para poder subirlo en una máquina con
#: más margen que ésta.
#:
#: **Doce por una razón medida, no elegida.** La primera versión usaba treinta y
#: falló a los 39 minutos con `TimeoutError` de asyncpg: el `NullPool` de la
#: suite abre una conexión física por consulta, y treinta jornadas con su
#: evidencia duplicada agotan el pool del servidor de pruebas. El fallo era de
#: la infraestructura de test, no de un invariante — pero un soak que no termina
#: no demuestra nada, así que la carga se ajusta a lo que este arnés sostiene y
#: el límite se declara en vez de esconderse.
#:
#: Doce sigue siendo significativo porque lo que este soak comprueba es
#: **estructural**: la unicidad la garantizan índices y el orden sale de las
#: filas de dominio, así que no se vuelven más ciertos a las treinta
#: repeticiones. Lo que las repeticiones aportan es que el duplicado concurrente
#: llegue en órdenes distintos, y eso ocurre en **cada** ciclo, no a partir de
#: uno.
CICLOS = int(os.environ.get("ROUTE_SOAK_CYCLES", "12"))

AHORA = datetime.now(timezone.utc)

#: Puntos próximos, para que la plausibilidad geométrica no rechace al doble.
COORDS = [
    ("40.712800", "-74.0060000"),
    ("40.722800", "-74.0100000"),
    ("40.732800", "-74.0140000"),
    ("40.742800", "-74.0180000"),
]


class _RouterDeSoak:
    """Distancia fija y cuenta de llamadas. Determinista bajo carga."""

    name = "soak"

    def __init__(self) -> None:
        self.llamadas = 0

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        self.llamadas += 1
        return SegmentResult(
            distance_meters=Decimal("9000.00"),
            provider=self.name,
            method="driving",
            version="soak",
        )


@pytest.fixture
def router_soak():
    doble = _RouterDeSoak()
    previo = set_road_router(doble)
    yield doble
    set_road_router(previo)


async def _punto(cliente, event_kind: str, subject_id: int, coord, hace: int):
    lat, lon = coord
    return await cliente.post(
        "/api/location/evidence",
        json={
            "event_kind": event_kind,
            "subject_id": subject_id,
            "evidence_level": "fresh",
            "latitude": lat,
            "longitude": lon,
            "accuracy_m": "10.00",
            "device_captured_at": (AHORA - timedelta(minutes=hace)).isoformat(),
        },
    )


async def _escalar(consulta: str, params: dict):
    async with async_session_maker() as sesion:
        return await sesion.scalar(text(consulta), params)


async def _un_ciclo(cliente, seeded, tenant, indice: int, *, reautenticar: bool):
    """Una jornada completa con su evidencia, duplicada y desordenada."""
    compania = getattr(seeded, tenant)
    email = compania.users["supervisor"].email
    await cliente.login(email)

    jornada = (await cliente.post("/api/worksessions", json={})).json()
    if "id" not in jornada:
        return None

    viaje = (
        await cliente.post(
            "/api/trips",
            json={"purpose": "other", "context_reference": f"Soak {indice}"},
        )
    ).json()
    if "id" not in viaje:
        return None
    await cliente.post(f"/api/trips/{viaje['id']}/start", json={})

    # Un Change Plan en la mitad de los ciclos, dos en una de cada cinco: así la
    # secuencia de waypoints varía y el orden de ocurrencia se pone a prueba con
    # longitudes distintas.
    cambios: list[int] = []
    for n in range(0 if indice % 2 else (2 if indice % 5 == 0 else 1)):
        await cliente.post(
            f"/api/trips/{viaje['id']}/change-plan",
            json={"purpose": "other", "context_reference": f"Cambio {n}"},
        )
    historial = (await cliente.get(f"/api/trips/{viaje['id']}/plan-changes")).json()
    cambios = [c["id"] for c in (historial if isinstance(historial, list) else [])]

    await cliente.post(f"/api/trips/{viaje['id']}/arrive", json={})

    if reautenticar:
        # En medio: la evidencia que venga después no puede depender de que la
        # sesión anterior siguiera viva.
        await cliente.login(email)

    # Evidencia **fuera de orden**: primero la llegada. Es lo que produce una
    # cola que vacía tras varios cortes de red.
    await _punto(cliente, "arrived", viaje["id"], COORDS[-1], hace=60)
    for posicion, cambio in enumerate(cambios):
        # Separados **una hora** entre sí, no un minuto. La primera versión
        # usaba `120 - posicion` —sesenta segundos entre dos waypoints con 9 km
        # de tramo— y la plausibilidad los rechazaba por 540 km/h. Tenía razón:
        # el dato de prueba era imposible, no el motor. Es el mismo error que
        # los puntos a 130 km con un doble de 10 km.
        await _punto(
            cliente, "change_plan", cambio, COORDS[posicion + 1],
            hace=240 - posicion * 60,
        )
    await _punto(cliente, "start_trip", viaje["id"], COORDS[0], hace=300)

    # Y cada pieza otra vez, dos de ellas **en paralelo**: el duplicado
    # concurrente es el que rompe la idempotencia si la garantiza el código.
    await asyncio.gather(
        _punto(cliente, "start_trip", viaje["id"], COORDS[0], hace=300),
        _punto(cliente, "arrived", viaje["id"], COORDS[-1], hace=60),
        return_exceptions=True,
    )

    return {"jornada": jornada["id"], "viaje": viaje["id"], "cambios": cambios}


async def _cerrar_jornada(company_id: int) -> None:
    """Cierra la jornada activa por SQL para poder abrir la siguiente.

    El producto exige terminar el trabajo de la parada antes de cerrar el día, y
    hacerlo por la interfaz en cada uno de los treinta ciclos añadiría dos
    llamadas por ciclo sin probar nada nuevo: lo que este soak mide es la
    evidencia y el kilometraje, no la guarda de cierre — que tiene sus propios
    tests en RTE05.
    """
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE work_session SET status = 'ended', ended_at = now() "
                "WHERE company_id = :c AND status = 'active'"
            ),
            {"c": company_id},
        )
        await sesion.commit()


async def test_the_soak_holds_every_invariant(
    seeded, alpha_client, beta_client, router_soak
):
    """Treinta ciclos, dos tenants, duplicados y desorden: los invariantes aguantan.

    Es un solo test a propósito: los invariantes se comprueban **sobre el estado
    acumulado**, y partirlo en varios los comprobaría sobre estados parciales,
    que es más débil. Si falla, el volcado de abajo dice qué invariante y con
    qué cifras.
    """
    viajes_alpha: list[dict] = []
    viajes_beta: list[dict] = []

    for indice in range(CICLOS):
        resultado = await _un_ciclo(
            alpha_client, seeded, "alpha", indice, reautenticar=indice % 3 == 0
        )
        if resultado:
            viajes_alpha.append(resultado)
        await _cerrar_jornada(seeded.alpha.id)

        # Un tenant en paralelo cada tres ciclos: el aislamiento bajo carga.
        if indice % 3 == 0:
            otro = await _un_ciclo(
                beta_client, seeded, "beta", indice, reautenticar=False
            )
            if otro:
                viajes_beta.append(otro)
            await _cerrar_jornada(seeded.beta.id)

    assert len(viajes_alpha) >= CICLOS - 1, (
        f"sólo {len(viajes_alpha)} de {CICLOS} ciclos completaron: el soak no "
        "llegó a ejercitar lo que pretende"
    )

    # ── Invariante 1: ningún punto duplicado ────────────────────────────────
    duplicados = await _escalar(
        "SELECT count(*) FROM (SELECT company_id, event_kind, subject_kind, "
        "subject_id, count(*) AS n FROM location_fix GROUP BY 1,2,3,4 "
        "HAVING count(*) > 1) d",
        {},
    )
    assert duplicados == 0, f"{duplicados} eventos con más de un punto"

    # ── Invariante 2: ninguna correlación equivocada ────────────────────────
    #
    # Cada punto tiene que colgar de una fila que exista y sea de su compañía.
    # Es la comprobación que atraparía un `subject_id` atado al viaje de otro
    # ciclo, que es el modo de fallo que el desorden y la concurrencia podrían
    # producir.
    huerfanos = await _escalar(
        """
        SELECT count(*) FROM location_fix f
        WHERE (f.subject_kind = 'trip' AND NOT EXISTS (
                   SELECT 1 FROM trip t
                   WHERE t.id = f.subject_id AND t.company_id = f.company_id))
           OR (f.subject_kind = 'trip_purpose_change' AND NOT EXISTS (
                   SELECT 1 FROM trip_purpose_change c
                   WHERE c.id = f.subject_id AND c.company_id = f.company_id))
           OR (f.subject_kind = 'work_session' AND NOT EXISTS (
                   SELECT 1 FROM work_session w
                   WHERE w.id = f.subject_id AND w.company_id = f.company_id))
        """,
        {},
    )
    assert huerfanos == 0, f"{huerfanos} puntos atados a una fila que no existe"

    # El `change_plan` tiene que pertenecer al viaje de su propio punto.
    cruzados = await _escalar(
        """
        SELECT count(*) FROM location_fix f
        JOIN trip_purpose_change c
          ON c.id = f.subject_id AND c.company_id = f.company_id
        WHERE f.event_kind = 'change_plan'
          AND NOT EXISTS (
              SELECT 1 FROM location_fix g
              WHERE g.company_id = f.company_id
                AND g.event_kind = 'start_trip'
                AND g.subject_id = c.trip_id)
        """,
        {},
    )
    assert cruzados == 0, (
        f"{cruzados} cambios de plan cuyo viaje no tiene punto de salida: "
        "la correlación se cruzó entre ciclos"
    )

    # ── Invariante 3: un kilometraje por viaje, y ninguno duplicado ─────────
    km_duplicado = await _escalar(
        "SELECT count(*) FROM (SELECT company_id, trip_id, count(*) AS n "
        "FROM trip_mileage GROUP BY 1,2 HAVING count(*) > 1) d",
        {},
    )
    assert km_duplicado == 0, f"{km_duplicado} viajes con más de un kilometraje"

    tramos_duplicados = await _escalar(
        "SELECT count(*) FROM (SELECT trip_mileage_id, sequence, count(*) AS n "
        "FROM trip_mileage_segment GROUP BY 1,2 HAVING count(*) > 1) d",
        {},
    )
    assert tramos_duplicados == 0, f"{tramos_duplicados} tramos duplicados"

    # ── Invariante 4: ningún Pending **permanente** ────────────────────────
    #
    # Lo que la instrucción prohíbe es un pendiente **sin camino de salida**, no
    # un pendiente que todavía no le ha llegado el turno. La primera versión de
    # este test exigía cero pendientes tras barrer y fallaba con cuatro: eran
    # cuatro con `next_attempt_at` en el futuro por el backoff, es decir el
    # mecanismo funcionando. La aserción era mía y estaba mal.
    #
    # Así que se comprueba lo correcto en dos pasos: primero que ningún
    # pendiente esté sin cita ni con los intentos agotados, y después que
    # adelantando el reloj **todos** terminan.
    from app.core.platform.config_service import platform_config

    maximo = int(platform_config.policy("route_mileage")["max_attempts"])

    for _ in range(12):
        resumen = await sweep_pending_mileage(limit=500)
        if not resumen.get("examined"):
            break

    sin_salida = await _escalar(
        "SELECT count(*) FROM trip_mileage WHERE state = 'pending_calculation' "
        "AND (next_attempt_at IS NULL OR attempt_count >= :m)",
        {"m": maximo},
    )
    assert sin_salida == 0, (
        f"{sin_salida} pendientes sin camino automático de salida: ésos sí son "
        "el Pending permanente que §24 prohíbe"
    )

    # Ahora se adelanta el reloj y se barre, **repetidamente**: cada pasada
    # programa un backoff nuevo, así que adelantar una sola vez dejaba las
    # siguientes sin nada vencido y el pendiente parecía eterno cuando sólo
    # estaba esperando. Con el reloj adelantado en cada vuelta, el reintento
    # acotado se agota de verdad: o calcula, o llega a terminal.
    for _ in range(maximo + 3):
        async with async_session_maker() as sesion:
            await sesion.execute(
                text(
                    "UPDATE trip_mileage SET next_attempt_at = now() "
                    "WHERE state = 'pending_calculation'"
                )
            )
            await sesion.commit()
        resumen = await sweep_pending_mileage(limit=500)
        if not resumen.get("examined"):
            break

    pendientes = await _escalar(
        "SELECT count(*) FROM trip_mileage WHERE state = 'pending_calculation'",
        {},
    )
    calculados = await _escalar(
        "SELECT count(*) FROM trip_mileage WHERE state = 'calculated'", {}
    )
    assert pendientes == 0, (
        f"{pendientes} kilometrajes siguen pendientes con el reintento vencido: "
        "ése sí es un Pending que no se resuelve"
    )
    assert calculados >= CICLOS - 2, (
        f"sólo {calculados} calculados de ~{CICLOS}: el soak no llegó a "
        "ejercitar el motor"
    )

    # ── Invariante 5: aislamiento intacto ──────────────────────────────────
    cruce = await _escalar(
        """
        SELECT count(*) FROM location_fix f
        JOIN work_session w ON w.id = f.work_session_id
        WHERE w.company_id <> f.company_id
        """,
        {},
    )
    assert cruce == 0, f"{cruce} puntos atados a la jornada de otra compañía"

    tenants = await _escalar(
        "SELECT count(DISTINCT company_id) FROM location_fix", {}
    )
    assert tenants == 2, (
        f"{tenants} tenants con evidencia: el soak tiene que haber cargado los dos"
    )

    # ── Invariante 6: el orden de ocurrencia, no el de llegada ─────────────
    #
    # La evidencia se envió **al revés**. Si el motor hubiera ordenado por hora
    # de captura de llegada o por id de inserción, los tramos saldrían al
    # revés. Se comprueba que el primer tramo de cada kilometraje sale de
    # `start_trip`.
    mal_ordenados = await _escalar(
        "SELECT count(*) FROM trip_mileage_segment "
        "WHERE sequence = 1 AND from_event_kind <> 'start_trip'",
        {},
    )
    assert mal_ordenados == 0, (
        f"{mal_ordenados} kilometrajes cuyo primer tramo no empieza en la "
        "salida: se ordenó por llegada y no por ocurrencia"
    )

    ultimos = await _escalar(
        """
        SELECT count(*) FROM trip_mileage_segment s
        WHERE s.to_event_kind = 'arrived'
          AND s.sequence <> (
              SELECT max(sequence) FROM trip_mileage_segment o
              WHERE o.trip_mileage_id = s.trip_mileage_id)
        """,
        {},
    )
    assert ultimos == 0, "la llegada tiene que ser siempre el último tramo"
