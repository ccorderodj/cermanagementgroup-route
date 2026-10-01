"""El adaptador de TomTom, sin red.

Qué se prueba aquí y qué no
---------------------------
Aquí se prueba que el adaptador construye bien la petición y clasifica bien las
respuestas. Que TomTom conteste lo que su documentación dice sólo lo demuestra
un motor real, y eso vive en `tests/integration/test_route_routing_live.py`
detrás de su puerta de entorno.

El caso que más importa es `test_orden_lat_lon`. El modo de fallo más peligroso
de un adaptador de routing es invertir las coordenadas: devuelve distancias
plausibles **de otro sitio**, así que no rompe nada y miente. TomTom usa
`lat,lon` y OSRM usa `lon,lat`, de modo que un copiar-pegar entre los dos es
exactamente cómo ocurriría.
"""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from app.routers_api.mileage.routing import (
    Punto,
    RoutingUnavailable,
    TomTomRouter,
)

#: Dos puntos de Athens, Georgia, separados unos 4 km.
A = Punto(latitude=Decimal("33.945512"), longitude=Decimal("-83.420400"))
B = Punto(latitude=Decimal("33.940328"), longitude=Decimal("-83.465930"))

CLAVE = "clave-super-secreta-123"


def _router(manejador, **kwargs) -> TomTomRouter:
    return TomTomRouter(
        CLAVE, timeout=5.0, transport=httpx.MockTransport(manejador), **kwargs
    )


def _ok(metros: float) -> dict:
    return {"formatVersion": "0.0.12",
            "routes": [{"summary": {"lengthInMeters": metros}}]}


@pytest.mark.asyncio
async def test_orden_lat_lon() -> None:
    """La URL lleva `lat,lon` y los puntos separados por `:`, no por `;`."""
    visto: dict[str, str] = {}

    def manejador(request: httpx.Request) -> httpx.Response:
        visto["path"] = request.url.path
        return httpx.Response(200, json=_ok(4521.0))

    await _router(manejador).distance(A, B)

    # Si alguien invierte el orden, esto falla aquí y no en producción con una
    # distancia creíble de otro continente.
    assert visto["path"].endswith(
        "/routing/1/calculateRoute/33.945512,-83.420400:33.940328,-83.465930/json"
    )


@pytest.mark.asyncio
async def test_pide_resumen_y_sin_trafico() -> None:
    """`traffic=false` y sólo el resumen: reproducibilidad y respuesta mínima."""
    visto: dict[str, list[str]] = {}

    def manejador(request: httpx.Request) -> httpx.Response:
        visto.update(parse_qs(request.url.query.decode()))
        return httpx.Response(200, json=_ok(4521.0))

    await _router(manejador).distance(A, B)

    # Sin esto, los mismos dos puntos devolverían distancias distintas segun
    # cuando se pregunte, y un kilometraje auditable dejaria de ser reproducible.
    assert visto["traffic"] == ["false"]
    assert visto["routeRepresentation"] == ["summaryOnly"]
    assert visto["key"] == [CLAVE]
    # `instructionsType` NO se manda. Este test lo afirmaba al reves —con
    # `"none"`— y pasaba, porque el doble acepta lo que se le diga. La API
    # real respondio `BAD_INPUT: Invalid InstructionsType value: [none]`.
    # Queda fijado para que nadie lo vuelva a anadir "por claridad".
    assert "instructionsType" not in visto


@pytest.mark.asyncio
async def test_devuelve_metros_sin_convertir() -> None:
    """TomTom ya da metros: aquí no hay conversión que equivocar."""
    resultado = await _router(
        lambda r: httpx.Response(200, json=_ok(4521.7))
    ).distance(A, B)

    assert resultado.distance_meters == Decimal("4521.7")
    assert resultado.provider == "tomtom"
    assert resultado.method == "car/fastest/no-traffic"
    assert resultado.version == "0.0.12"


@pytest.mark.asyncio
async def test_la_clave_nunca_sale_en_el_error() -> None:
    """El mensaje acaba en `trip_mileage.last_error`, que se conserva."""

    def manejador(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no se pudo conectar a {request.url}")

    with pytest.raises(RoutingUnavailable) as exc:
        await _router(manejador).distance(A, B)

    assert CLAVE not in str(exc.value)
    assert "***" in str(exc.value)
    assert exc.value.transient is True


@pytest.mark.asyncio
async def test_sin_clave_no_se_construye() -> None:
    with pytest.raises(ValueError):
        TomTomRouter("", timeout=5.0)


@pytest.mark.parametrize(
    "estado,cuerpo,transitorio,trozo",
    [
        # Del servidor: puede pasar, y el reintento acotado lo cubre.
        (503, None, True, "503"),
        # Límite por segundo: se rearma solo.
        (429, None, True, "rate limit"),
        # Credencial o cuota. Permanente a propósito: una cuota diaria no se
        # rearma dentro de los cinco intentos.
        (403, None, False, "credential or quota"),
        (401, None, False, "credential or quota"),
        # Ningún punto cae cerca de una carretera: describe los datos.
        (400, {"detailedError": {"code": "MAP_MATCHING_FAILURE",
                                 "message": "no road near waypoint"}},
         False, "MAP_MATCHING_FAILURE"),
        (400, {"detailedError": {"code": "NO_ROUTE_FOUND", "message": "sin ruta"}},
         False, "NO_ROUTE_FOUND"),
    ],
)
@pytest.mark.asyncio
async def test_clasificacion_de_fallos(estado, cuerpo, transitorio, trozo) -> None:
    """`transient` decide el estado terminal, así que cada caso va fijado."""
    def manejador(request: httpx.Request) -> httpx.Response:
        if cuerpo is None:
            return httpx.Response(estado, text="")
        return httpx.Response(estado, json=cuerpo)

    with pytest.raises(RoutingUnavailable) as exc:
        await _router(manejador).distance(A, B)

    assert exc.value.transient is transitorio
    assert trozo in str(exc.value)


@pytest.mark.asyncio
async def test_doscientos_sin_distancia_es_transitorio() -> None:
    """Respuesta bien formada pero vacía: del motor, puede pasar."""
    with pytest.raises(RoutingUnavailable) as exc:
        await _router(lambda r: httpx.Response(200, json={"routes": []})).distance(A, B)

    assert exc.value.transient is True
    assert "no route length" in str(exc.value)


@pytest.mark.asyncio
async def test_base_url_configurable() -> None:
    """Una cuenta dedicada puede tener otro punto de entrada."""
    visto: dict[str, str] = {}

    def manejador(request: httpx.Request) -> httpx.Response:
        visto["host"] = request.url.host
        return httpx.Response(200, json=_ok(100.0))

    await _router(manejador, base_url="https://api.eu.tomtom.com").distance(A, B)
    assert visto["host"] == "api.eu.tomtom.com"
