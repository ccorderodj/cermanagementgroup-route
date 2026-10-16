"""El cableado entre la integración de plataforma y el adaptador de routing.

Lo que esto cubre y por qué faltaba
-----------------------------------
`TomTomRouter` tenía sus tests desde el principio, pero el camino real
—integración habilitada → secreto descifrado → adaptador montado— **no tenía
ninguno**. Era código escrito y no ejecutado, y se notó en cuanto se usó la
pantalla de administración: el botón `Verify` respondía *"This integration
cannot be verified"* porque se había declarado una capacidad sin implementar su
comprobación, y nada en la suite lo detectó.

`test_toda_integracion_tiene_comprobacion` existe para que no vuelva a pasar.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.platform import providers as provider_defs
from app.core.platform.config_service import platform_config
from app.core.platform.diagnostics import BY_KEY as CHECKS
from app.routers_api.mileage.routing import (
    OsrmRouter,
    TomTomRouter,
    UnconfiguredRouter,
    ValhallaRouter,
    get_road_router,
    set_road_router,
)


def test_toda_integracion_tiene_comprobacion() -> None:
    """Una capacidad declarada sin comprobación da un `Verify` que no verifica.

    Es exactamente el defecto que llegó a la pantalla: `road_routing` se
    declaró con `capability_key` y sin entrada en `CHECKS`, y el administrador
    se encontró un botón que no podía hacer nada. Los 74 tests de entonces
    pasaron igual.
    """
    sin_comprobacion = [
        i.key for i in provider_defs.INTEGRATIONS if i.capability_key not in CHECKS
    ]
    assert not sin_comprobacion, (
        f"estas integraciones se pueden configurar pero no verificar: "
        f"{sin_comprobacion}"
    )


@pytest.fixture
def sin_sustitucion():
    """Deja `get_road_router()` leyendo la configuración, y lo repone al salir."""
    previo = set_road_router(None)
    yield
    set_road_router(previo)


@pytest.fixture
def integracion(monkeypatch):
    """Finge el estado de la integración `road_routing` y sus secretos."""

    def configurar(provider, config=None, secreto=None, enabled=True):
        estado = SimpleNamespace(
            key="road_routing",
            provider=provider,
            enabled=enabled,
            config=config or {},
            secrets={},
            verified_at=None,
            version=1,
        )
        monkeypatch.setattr(
            platform_config,
            "integration",
            lambda key: estado if key == "road_routing" else None,
        )
        monkeypatch.setattr(
            platform_config, "secret", lambda k, n: secreto if k == "road_routing" else None
        )
        monkeypatch.setattr(
            platform_config, "policy", lambda key: {"snap_radius_m": 1000}
        )

    return configurar


def test_tomtom_se_monta_con_el_secreto_descifrado(
    sin_sustitucion, integracion
) -> None:
    integracion("tomtom", secreto="clave-de-prueba")
    motor = get_road_router()
    assert isinstance(motor, TomTomRouter)
    assert motor.name == "tomtom"


def test_tomtom_sin_clave_no_se_monta(sin_sustitucion, integracion, monkeypatch) -> None:
    """Seleccionado pero sin credencial: no se monta un motor que no responde.

    Cae al camino de las variables de entorno, y si tampoco hay, al adaptador
    que declara que no hay ninguno. Montar un `TomTomRouter` sin clave
    convertiría un problema de configuración en un fallo por tramo.
    """
    integracion("tomtom", secreto=None)
    monkeypatch.setattr(
        "app.routers_api.mileage.routing.settings.ROUTE_ROUTING_URL", ""
    )
    assert isinstance(get_road_router(), UnconfiguredRouter)


def test_osrm_se_monta_desde_la_integracion(sin_sustitucion, integracion) -> None:
    integracion("osrm", config={"base_url": "http://osrm:5000"})
    motor = get_road_router()
    assert isinstance(motor, OsrmRouter)


def test_valhalla_se_monta_desde_la_integracion(sin_sustitucion, integracion) -> None:
    integracion("valhalla", config={"base_url": "http://valhalla:8002"})
    assert isinstance(get_road_router(), ValhallaRouter)


def test_integracion_deshabilitada_no_se_usa(
    sin_sustitucion, integracion, monkeypatch
) -> None:
    integracion("tomtom", secreto="clave", enabled=False)
    monkeypatch.setattr(
        "app.routers_api.mileage.routing.settings.ROUTE_ROUTING_URL", ""
    )
    assert isinstance(get_road_router(), UnconfiguredRouter)


def test_un_cambio_de_proveedor_surte_efecto_sin_reiniciar(
    sin_sustitucion, integracion
) -> None:
    """El defecto que llevaba al administrador a reiniciar a ciegas.

    `get_road_router()` cacheaba el adaptador en una global, así que cambiar de
    proveedor en la pantalla no hacía nada hasta que alguien reiniciaba el
    proceso —y nada se lo decía—. Ahora se construye por llamada, igual que
    `get_storage()`; lo cacheado es el snapshot de configuración.
    """
    integracion("osrm", config={"base_url": "http://osrm:5000"})
    assert isinstance(get_road_router(), OsrmRouter)

    # Mismo proceso, sin reiniciar nada: el administrador cambia a TomTom.
    integracion("tomtom", secreto="clave-nueva")
    assert isinstance(get_road_router(), TomTomRouter)


def test_la_sustitucion_explicita_sigue_mandando(integracion) -> None:
    """`set_road_router` es para los tests, y tiene que ganar a la configuración."""
    integracion("tomtom", secreto="clave")
    doble = UnconfiguredRouter()
    previo = set_road_router(doble)
    try:
        assert get_road_router() is doble
    finally:
        set_road_router(previo)
