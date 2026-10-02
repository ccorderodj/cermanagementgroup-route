"""G1-G11: la etapa de recuperación exige precisión (F-1).

Por qué en el navegador y no en un test de Python
--------------------------------------------------
La regla vive en `location.ts`, y este proyecto no tiene runner de JavaScript:
`npm run check` sólo comprueba tipos y estilo. Lo único que ejecuta ese módulo
de verdad es un navegador, así que aquí es donde puede medirse.

Cómo se controla la precisión
-----------------------------
`context.set_geolocation()` de Playwright fija un único punto para toda la
sesión, y eso no permite distinguir las tres etapas: la primera lo aceptaría y
la de recuperación no llegaría a ejecutarse nunca.

Por eso se inyecta un `navigator.geolocation` guionizado con
`add_init_script`. Cada llamada consume el siguiente paso del guion, y el guion
distingue las etapas por sus opciones —la etapa 2 es la única que pide
`enableHighAccuracy: false`—, así que un test puede decir exactamente qué
devuelve cada una.

La ventana de recuperación
--------------------------
Por defecto son 180 s. Un test que la agote tardaría tres minutos, así que se
acorta en la política de plataforma, que es configurable justo para esto. Se
restaura al terminar.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from tests.e2e.conftest import abrir_sesion, lanzar_edge

pytestmark = [pytest.mark.integration, pytest.mark.browser]

pytest.importorskip("playwright", reason="playwright no está instalado")

MOVIL = {"width": 390, "height": 844}

#: El umbral aprobado por D-FIELD-01. Se lee de la politica, no se fija aqui.
UMBRAL_POR_DEFECTO = 100

#: Ventana corta para los tests. Suficiente para dos o tres intentos con la
#: pausa de 2 s del cliente, y lo bastante breve para no alargar la suite.
def _guion(pasos: list[dict]) -> str:
    """Un `navigator.geolocation` que devuelve lo que diga el guion.

    Cada paso es `{"accuracy": n}` para un punto, o `{"code": n}` para un
    fallo. Las etapas se distinguen por `enableHighAccuracy`: la cacheada es la
    unica que lo pide `false`, asi que un paso puede marcarse `"stage":
    "cached"` y solo responderle a ella.
    """
    return f"""
    (() => {{
        const guion = {json.dumps(pasos)};
        let i = 0;
        window.__geoLlamadas = [];
        navigator.geolocation.getCurrentPosition = (ok, err, opciones) => {{
            const cacheada = opciones && opciones.enableHighAccuracy === false;
            window.__geoLlamadas.push({{
                highAccuracy: !!(opciones && opciones.enableHighAccuracy),
                maximumAge: opciones ? opciones.maximumAge : null,
            }});
            const paso = guion[Math.min(i, guion.length - 1)];
            i += 1;
            if (paso.stage === 'cached' && !cacheada) {{
                // Un paso marcado para la etapa cacheada no le responde a otra.
                err({{ code: 3, message: 'timeout' }});
                return;
            }}
            if (paso.code) {{
                err({{ code: paso.code, message: 'guion' }});
                return;
            }}
            ok({{
                coords: {{
                    latitude: 33.945512,
                    longitude: -83.420400,
                    accuracy: paso.accuracy,
                }},
                timestamp: Date.now(),
            }});
        }};
    }})();
    """


@asynccontextmanager
async def _movil(live_server, email: str, pasos: list[dict]):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await lanzar_edge(p)
        try:
            contexto = await navegador.new_context(
                base_url=live_server, viewport=MOVIL,
                permissions=["geolocation"],
                geolocation={"latitude": 33.945512, "longitude": -83.420400},
            )
            await contexto.add_init_script(_guion(pasos))
            page = await contexto.new_page()

            # Los errores de la página se recogen y se imprimen al salir.
            #
            # Sin esto, una excepción dentro de la captura no deja rastro
            # alguno: el test ve "no hay punto y no hay Missing" y no puede
            # distinguir "la regla lo rechazó" de "el código se rompió a
            # mitad". Es exactamente la confusión que costó una vuelta entera
            # de diagnóstico en este cierre.
            fallos: list[str] = []
            page.on("pageerror", lambda e: fallos.append(f"pageerror: {e}"))
            page.on(
                "console",
                lambda m: (
                    fallos.append(f"console.{m.type}: {m.text}")
                    if m.type == "error"
                    else None
                ),
            )

            await abrir_sesion(page, email)
            try:
                yield contexto, page
            finally:
                if fallos:
                    print("\n--- errores del navegador ---")
                    for f in fallos[:20]:
                        print(f"  {f}")
        finally:
            await navegador.close()


async def _fijos(company_id: int, nivel: str | None = None) -> int:
    consulta = (
        "SELECT count(*) FROM location_fix WHERE company_id = :c"
        + (" AND evidence_level = :n" if nivel else "")
    )
    async with async_session_maker() as s:
        return await s.scalar(
            text(consulta),
            {"c": company_id, **({"n": nivel} if nivel else {})},
        )


async def _missing(company_id: int) -> list[tuple[str, dict]]:
    async with async_session_maker() as s:
        filas = (await s.execute(text(
            "SELECT reason_code, rejected_candidate FROM missing_location_event "
            "WHERE company_id = :c ORDER BY id"), {"c": company_id})).all()
    return [(r[0], r[1]) for r in filas]


async def _start_work(page, company_id: int) -> None:
    """Empieza la jornada y espera a que la captura **se resuelva**.

    Espera hasta que el sistema haya dicho algo -un punto o un Missing- en vez
    de dormir un tiempo fijo. Las dos cosas mejoran con eso:

    * los casos que aceptan el punto terminan en segundos en vez de esperar la
      ventana entera, que es lo que hacia la version anterior de esto y lo que
      convertia diez tests de veinte segundos en diez de tres minutos;
    * los casos que necesitan que la ventana se agote esperan **su** ventana,
      la que el servidor sirve de verdad, no una constante escrita aqui.

    Aqui habia una fixture que escribia `recovery_window_seconds: 7` en
    `platform_policy` para no esperar tres minutos. **No funcionaba, y no podia
    funcionar**: `app/main.py` vuelve de su evento de arranque antes de
    `platform_config.refresh()` cuando `settings.is_testing`, asi que el
    proceso de uvicorn de los e2e nunca carga la configuracion de plataforma y
    `policy()` devuelve siempre los valores de fabrica. Tampoco habia nadie
    escuchando su `NOTIFY`.

    Eso es deliberado -`_platform_config_vacia` aisla la configuracion por test
    por la misma razon-, de modo que lo que estaba mal era la fixture. Su
    efecto real fue que G3, G4, G6 y G7 median quince segundos contra una
    ventana de ciento ochenta y fallaban diciendo "falta el Missing", que
    parece un defecto del producto y no lo era.
    """
    await page.goto("/route")

    servida = await page.evaluate(
        """async () => {
            const r = await fetch('/api/location/policy', {
                credentials: 'include',
            });
            return r.ok ? await r.json() : { error: r.status };
        }"""
    )
    ventana = servida.get("recovery_window_seconds")
    assert isinstance(ventana, int), f"no se pudo leer la politica: {servida}"

    await page.get_by_role("button", name="Start Work").click()

    # El tope cubre la ventana entera mas el envio del hecho. Si se agota sin
    # que haya ni punto ni Missing, el test de turno lo dira con su propia
    # asercion; aqui no se decide si eso esta bien o mal.
    tope = ventana + 25
    esperado = 0
    while esperado < tope:
        await page.wait_for_timeout(2_000)
        esperado += 2
        if await _fijos(company_id) > 0 or await _missing(company_id):
            return


# ── G1, G2, G3, G4: el umbral en la etapa de recuperación ────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "precision,acepta,caso",
    [
        (50, True, "G1 — bien dentro del umbral"),
        (UMBRAL_POR_DEFECTO, True, "G2 — justo en el umbral"),
        (UMBRAL_POR_DEFECTO + 1, False, "G3 — uno por encima"),
        (2000, False, "G4 — groseramente impreciso"),
    ],
)
async def test_umbral_de_recuperacion(
    seeded, live_server, precision, acepta, caso
):
    """La etapa 3 aplica el mismo umbral que la 1.

    Las dos primeras etapas se hacen fallar a propósito para que el punto del
    guion llegue **a la recuperación**, que es la que se está probando.
    """
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    pasos = [
        {"accuracy": 5000},            # etapa 1: rechazada por imprecisa
        {"stage": "cached", "code": 3},  # etapa 2: sin punto cacheado
        {"accuracy": precision},        # etapa 3: el caso bajo prueba
    ]
    async with _movil(live_server, supervisor.email, pasos) as (_c, page):
        await _start_work(page, empresa.id)

    recuperados = await _fijos(empresa.id, "recovered")
    if acepta:
        assert recuperados == 1, f"{caso}: deberia haberse aceptado"
        assert await _missing(empresa.id) == [], f"{caso}: no deberia haber Missing"
    else:
        assert recuperados == 0, f"{caso}: NO deberia aceptarse"
        motivos = await _missing(empresa.id)
        assert len(motivos) == 1, f"{caso}: falta el Missing"


@pytest.mark.asyncio
async def test_g5_candidato_malo_y_luego_bueno(seeded, live_server):
    """Un candidato rechazado no cierra la ventana: se sigue intentando."""
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    pasos = [
        {"accuracy": 5000},
        {"stage": "cached", "code": 3},
        {"accuracy": 1500},   # recuperacion, rechazado
        {"accuracy": 40},     # recuperacion, aceptado
    ]
    async with _movil(live_server, supervisor.email, pasos) as (_c, page):
        await _start_work(page, empresa.id)

    assert await _fijos(empresa.id, "recovered") == 1, (
        "el segundo candidato, bueno, tenia que aceptarse")
    assert await _missing(empresa.id) == [], "no procede Missing si uno valio"


@pytest.mark.asyncio
async def test_g6_g7_todos_malos_dan_missing_con_su_motivo(
    seeded, live_server
):
    """Ventana agotada con candidatos: motivo propio, no el de 'sin punto'."""
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    pasos = [
        {"accuracy": 5000},
        {"stage": "cached", "code": 3},
        {"accuracy": 1800},   # todos los de recuperacion, imprecisos
    ]
    async with _movil(live_server, supervisor.email, pasos) as (_c, page):
        await _start_work(page, empresa.id)

    assert await _fijos(empresa.id, "recovered") == 0
    motivos = await _missing(empresa.id)
    assert len(motivos) == 1
    razon, rechazado = motivos[0]
    # G7: el motivo dice lo que paso de verdad. `recovery_window_exhausted`
    # significa "sin punto", y aqui si los hubo.
    assert razon == "recovery_accuracy_rejected", (
        f"motivo {razon!r}: sobrecarga un hecho distinto")

    # G8: queda la precision, nunca las coordenadas.
    assert rechazado is not None
    assert "accuracy_m" in rechazado
    for prohibido in ("latitude", "longitude", "lat", "lon"):
        assert prohibido not in json.dumps(rechazado), (
            f"§12: el candidato rechazado no puede guardar {prohibido}")


# ── G9, G10: que las otras dos etapas sigan igual ────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "precision,nivel_esperado",
    [(80, "fresh"), (UMBRAL_POR_DEFECTO, "fresh")],
)
async def test_g9_fresh_sigue_aceptando_dentro_del_umbral(
    seeded, live_server, precision, nivel_esperado
):
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    async with _movil(
        live_server, supervisor.email, [{"accuracy": precision}]
    ) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(4_000)

    assert await _fijos(empresa.id, nivel_esperado) == 1


@pytest.mark.asyncio
async def test_g10_cached_sigue_exigiendo_las_dos_cosas(seeded, live_server):
    """La etapa cacheada acepta dentro de edad y precisión, como antes."""
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    pasos = [
        {"accuracy": 5000},                        # etapa 1 rechazada
        {"stage": "cached", "accuracy": 300},      # etapa 2 dentro de 500 m
    ]
    async with _movil(live_server, supervisor.email, pasos) as (_c, page):
        await page.goto("/route")
        await page.get_by_role("button", name="Start Work").click()
        await page.wait_for_timeout(5_000)

    assert await _fijos(empresa.id, "degraded_cached") == 1


# ── G11: nada rechazado llega al kilometraje ─────────────────────────────

@pytest.mark.asyncio
async def test_g11_un_candidato_rechazado_no_es_waypoint(
    seeded, live_server
):
    """Lo rechazado no existe como `location_fix`, así que no puede ser waypoint.

    Es la garantía de fondo: `for_trip_waypoints()` selecciona de
    `location_fix` sin filtrar por nivel ni por precisión, de modo que la única
    defensa es que la fila **no se cree**.
    """
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    pasos = [
        {"accuracy": 5000},
        {"stage": "cached", "code": 3},
        {"accuracy": 2000},
    ]
    async with _movil(live_server, supervisor.email, pasos) as (_c, page):
        await _start_work(page, empresa.id)

    # Ni una fila, de ningun nivel: lo rechazado no deja rastro consultable
    # como evidencia.
    assert await _fijos(empresa.id) == 0


# ── G12: precisión que no se puede evaluar ──────────────────────────────────


@pytest.mark.asyncio
async def test_g12_precision_desconocida_no_es_autoritativa(seeded, live_server):
    """Un punto sin precisión medible no entra, en ninguna etapa.

    Es el hueco que CER señaló sobre el delta anterior: la regla aceptaba
    `precision <= umbral` **o** `precision desconocida`, tratándolas como
    equivalentes. Un punto de 12 m se midió y cumple; uno sin precisión no se
    pudo comprobar, y aceptarlo afirma que su calidad es buena sin mirarla.

    El guion devuelve posiciones con `accuracy: null` en las tres etapas, que es
    lo que hace un proveedor que da coordenadas sin decir con cuánto error. El
    resultado tiene que ser el mismo que para un punto groseramente impreciso:
    ningún `location_fix`, y el hecho resuelto por el modelo escalonado.

    La mitad de servidor de esto —que es la puerta real— está en
    `tests/integration/test_route_location_evidence.py::
    test_g12_unknown_accuracy_is_not_acceptable_accuracy`.
    """
    empresa = seeded.alpha
    supervisor = empresa.users["supervisor"]
    pasos = [
        {"accuracy": None},
        {"stage": "cached", "accuracy": None},
        {"accuracy": None},
    ]
    async with _movil(live_server, supervisor.email, pasos) as (_c, page):
        await _start_work(page, empresa.id)

    assert await _fijos(empresa.id) == 0, (
        "un punto cuya precisión no se puede evaluar acabó como evidencia"
    )

    motivos = await _missing(empresa.id)
    assert len(motivos) == 1, f"el hecho no se resolvió: {motivos}"
    razon, rechazado = motivos[0]
    assert razon == "recovery_accuracy_rejected", razon
    # Y no se inventa un número que no existía: sin precisión medible no hay
    # `accuracy_m` que guardar, y un 0 ahí sería falso.
    assert "accuracy_m" not in (rechazado or {}), rechazado
