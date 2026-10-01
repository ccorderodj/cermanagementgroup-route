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
import pytest_asyncio
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
VENTANA_DE_PRUEBA = 7


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
            await abrir_sesion(page, email)
            yield contexto, page
        finally:
            await navegador.close()


@pytest_asyncio.fixture
async def ventana_corta():
    """Acorta la ventana de recuperación, **antes** de que arranque el servidor.

    **No depende de `database_schema`**: hacerlo la ponía a reiniciar la base
    antes que `seeded`, los usuarios desaparecían y el login del navegador
    devolvía 401 en los diez tests. Aquí sólo escribe una fila de política.

    Es fixture y no gestor de contexto por una razón medida: el cliente pide la
    política una sola vez, al arrancar la página, y el servidor cachea su
    instantánea de configuración. Cambiarla a mitad del test no llega a ningún
    sitio —se midieron 11 intentos de recuperación en 18 s, que es la ventana
    de 180 s por defecto—. Como fixture, se escribe antes de que `live_server`
    levante el proceso, que es cuando se lee.
    """
    async with async_session_maker() as s:
        previo = await s.scalar(text(
            "SELECT value FROM platform_policy WHERE key = 'route_location'"))
        await s.execute(text(
            "INSERT INTO platform_policy(key, value, version, updated_at) "
            "VALUES ('route_location', CAST(:v AS jsonb), 1, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = CAST(:v AS jsonb), "
            "  version = platform_policy.version + 1, updated_at = now()"),
            {"v": json.dumps({"recovery_window_seconds": VENTANA_DE_PRUEBA})})
        # El servidor cachea su instantánea de configuración, así que escribir
        # la fila no basta: sin esto sigue sirviendo la ventana de 180 s y el
        # test termina antes de que se declare el Missing. Medido.
        await s.execute(text("NOTIFY platform_config_changed"))
        await s.commit()
    try:
        yield
    finally:
        async with async_session_maker() as s:
            if previo is None:
                await s.execute(text(
                    "DELETE FROM platform_policy WHERE key = 'route_location'"))
            else:
                await s.execute(text(
                    "UPDATE platform_policy SET value = CAST(:v AS jsonb) "
                    "WHERE key = 'route_location'"),
                    {"v": json.dumps(previo)})
            await s.commit()


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


async def _start_work(page) -> None:
    await page.goto("/route")
    await page.get_by_role("button", name="Start Work").click()
    await page.wait_for_timeout(VENTANA_DE_PRUEBA * 1000 + 8_000)


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
    ventana_corta, seeded, live_server, precision, acepta, caso
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
        await _start_work(page)

    recuperados = await _fijos(empresa.id, "recovered")
    if acepta:
        assert recuperados == 1, f"{caso}: deberia haberse aceptado"
        assert await _missing(empresa.id) == [], f"{caso}: no deberia haber Missing"
    else:
        assert recuperados == 0, f"{caso}: NO deberia aceptarse"
        motivos = await _missing(empresa.id)
        assert len(motivos) == 1, f"{caso}: falta el Missing"


@pytest.mark.asyncio
async def test_g5_candidato_malo_y_luego_bueno(ventana_corta, seeded, live_server):
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
        await _start_work(page)

    assert await _fijos(empresa.id, "recovered") == 1, (
        "el segundo candidato, bueno, tenia que aceptarse")
    assert await _missing(empresa.id) == [], "no procede Missing si uno valio"


@pytest.mark.asyncio
async def test_g6_g7_todos_malos_dan_missing_con_su_motivo(
    ventana_corta, seeded, live_server
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
        await _start_work(page)

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
    ventana_corta, seeded, live_server
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
        await _start_work(page)

    # Ni una fila, de ningun nivel: lo rechazado no deja rastro consultable
    # como evidencia.
    assert await _fijos(empresa.id) == 0
