"""El puerto de routing vial y sus adaptadores (RTE06-CP3, §22).

Por qué un puerto
-----------------
§22 exige que el proveedor sea reemplazable, que el dominio no dependa de sus
payloads y que ninguna credencial viva en el cliente del supervisor. Un
`Protocol` con dos adaptadores lo cumple sin abstracción de más, y es el mismo
patrón que `OdometerReader` en `app/routers_api/odometer/ocr.py` — que ya está
probado en este repositorio.

El dominio nunca ve la respuesta del proveedor: recibe `SegmentResult` con los
metros y la procedencia, o `RoutingUnavailable` con si el fallo es transitorio.

La decisión de proveedor, cerrada
---------------------------------
**Primario OSRM auto-alojado (BSD-2). Reserva Valhalla auto-alojado (MIT).**
Los dos sobre datos OSM.

Lo que decide no es el precio. §27 y §28 obligan a **guardar la distancia de
cada tramo para siempre** y a que siga siendo auditable, y los términos de
servicio de Google Routes y Mapbox Directions restringen justamente el
almacenamiento permanente de contenido derivado de su routing. Eso es un
conflicto directo con un criterio de aceptación, no un detalle de coste.

Segunda razón: un motor auto-alojado se puede levantar y **medir de verdad** sin
credenciales, sin contrato y sin gasto, lo que permite cerrar RTE06 con evidencia
real en vez de sólo con dobles.

Un proveedor comercial se enchufa aquí el día que CER lo decida, escribiendo un
adaptador. El motor de kilometraje no cambia.

Lo que el fallback **no** es
----------------------------
No es otra fórmula de distancia. §20 y §25 prohíben Haversine, odómetro y
totales parciales como kilometraje oficial, así que la reserva es **otro motor
de routing**. Si los dos fallan y se agota el reintento acotado, el estado
terminal correcto es `calculation_failed`: una respuesta veraz, no un fallo del
producto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx

from app.config import settings


@dataclass(frozen=True)
class Punto:
    """Una coordenada, ya validada. El dominio habla en esto, no en dicts."""

    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class SegmentResult:
    """Un tramo enrutado, con quién lo produjo.

    `provider`, `method` y `version` se guardan en la fila del tramo porque §23
    exige poder auditar "provider" y "method/version" de cada distancia mucho
    después de calcularla.
    """

    distance_meters: Decimal
    provider: str
    method: str
    version: str | None = None


class RoutingUnavailable(Exception):
    """El proveedor no dio un resultado utilizable.

    `transient` es la única distinción que el motor necesita, y por eso está
    aquí y no en el servicio: un timeout o un 503 se reintentan; una coordenada
    que el proveedor considera inenrutable no mejora repitiendo la pregunta.
    §25 hace depender de eso el estado terminal.
    """

    def __init__(self, mensaje: str, *, transient: bool) -> None:
        super().__init__(mensaje)
        self.transient = transient


class RoadRouter(Protocol):
    """Distancia vial entre dos puntos. Lo único que el dominio necesita."""

    @property
    def name(self) -> str: ...

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        """Metros de carretera entre los dos puntos.

        Lanza `RoutingUnavailable` cuando no puede responder.
        """
        ...


class UnconfiguredRouter:
    """El adaptador por defecto: no hay motor configurado, y lo dice.

    Es el equivalente de `NoSuggestionReader` en el odómetro. Falla de forma
    **transitoria** a propósito: sin motor configurado el kilometraje se queda
    `pending_calculation` y lo terminaliza el reintento acotado, en vez de
    marcar `calculation_failed` viajes cuya evidencia está intacta y cuyo único
    problema es que falta desplegar un contenedor. La diferencia importa: el
    primer estado se resuelve solo cuando el motor aparece; el segundo es una
    mentira sobre los datos.
    """

    name = "unconfigured"

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        raise RoutingUnavailable(
            "No road routing engine is configured (ROUTE_ROUTING_URL is empty).",
            transient=True,
        )


class OsrmRouter:
    """OSRM auto-alojado. El proveedor primario.

    Una llamada por tramo a `/route/v1/driving/{lon},{lat};{lon},{lat}`, con
    `overview=false` para no traer la geometría: aquí sólo hace falta la
    distancia, y pedir el trazado multiplicaría el tamaño de la respuesta sin
    que nada lo use.

    El orden es **longitud, latitud** — al revés de como se escribe una
    coordenada en casi todo lo demás. Es el orden de OSRM y del GeoJSON, y
    equivocarlo devuelve distancias plausibles pero de otro sitio, que es el
    peor modo de fallo posible: no rompe nada y miente. Por eso hay un test que
    comprueba el orden con coordenadas conocidas.
    """

    name = "osrm"

    def __init__(
        self, base_url: str, *, timeout: float, snap_radius_m: int | None = None
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._snap = snap_radius_m

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        ruta = (
            f"{self._base}/route/v1/driving/"
            f"{origen.longitude},{origen.latitude};"
            f"{destino.longitude},{destino.latitude}"
        )
        try:
            parametros = {"overview": "false", "alternatives": "false"}
            if self._snap is not None:
                # Un radio por punto. Sin esto OSRM ajusta **cualquier**
                # coordenada al grafo que tenga cargado y devuelve una
                # distancia plausible de otro sitio; medido contra un motor
                # real, dos puntos de Berlín contra un extracto de Mónaco
                # dieron 10,1 km. Con el radio dice `NoSegment`, que es la
                # verdad.
                parametros["radiuses"] = f"{self._snap};{self._snap}"
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.get(ruta, params=parametros)
        except httpx.TimeoutException as exc:
            raise RoutingUnavailable(f"OSRM timed out: {exc}", transient=True) from exc
        except httpx.HTTPError as exc:
            raise RoutingUnavailable(
                f"OSRM unreachable: {exc}", transient=True
            ) from exc

        # 5xx es del servidor y puede pasar: transitorio, sin mirar el cuerpo.
        if respuesta.status_code >= 500:
            raise RoutingUnavailable(
                f"OSRM returned {respuesta.status_code}", transient=True
            )

        # El cuerpo **antes** que el código HTTP para todo lo demás. Medido: OSRM
        # devuelve `NoSegment` con HTTP 400, así que clasificar por el status
        # primero daba el estado terminal correcto pero perdía el motivo — y
        # "no hay carretera dentro del radio" es accionable mientras "400" no
        # dice nada a quien lea la traza dentro de un año.
        try:
            cuerpo = respuesta.json()
        except ValueError as exc:
            if respuesta.status_code >= 400:
                raise RoutingUnavailable(
                    f"OSRM rejected the request with {respuesta.status_code}",
                    transient=False,
                ) from exc
            raise RoutingUnavailable(
                "OSRM returned a body that is not JSON", transient=True
            ) from exc

        codigo = cuerpo.get("code")
        if codigo == "NoSegment":
            # Ningún punto cae dentro del radio de una carretera del grafo
            # cargado. Permanente, y es la respuesta correcta: preferible un
            # `Not Calculable` veraz a una distancia de otro continente.
            raise RoutingUnavailable(
                "OSRM found no road within the snap radius of a waypoint",
                transient=False,
            )
        if codigo == "NoRoute":
            # El motor respondió bien: entre esos dos puntos no hay ruta.
            raise RoutingUnavailable(
                "OSRM found no road route between the waypoints", transient=False
            )
        if codigo == "InvalidQuery" or codigo == "InvalidValue":
            raise RoutingUnavailable(
                f"OSRM rejected the query: {codigo}", transient=False
            )
        if codigo != "Ok":
            # Un código que este adaptador no conoce. Si vino con 4xx es la
            # pregunta y no mejora repitiéndola; si vino con 2xx es del motor y
            # puede pasar.
            raise RoutingUnavailable(
                f"OSRM code={codigo}", transient=respuesta.status_code < 400
            )

        rutas = cuerpo.get("routes") or []
        if not rutas or rutas[0].get("distance") is None:
            raise RoutingUnavailable(
                "OSRM returned Ok with no distance", transient=True
            )

        return SegmentResult(
            distance_meters=Decimal(str(rutas[0]["distance"])),
            provider=self.name,
            method="driving",
            version=cuerpo.get("dataVersion"),
        )



class ValhallaRouter:
    """Valhalla auto-alojado. El motor de **reserva**.

    Segundo motor, no segunda fórmula: §20 y §25 prohíben Haversine, odómetro y
    totales parciales como kilometraje oficial, así que la reserva tiene que ser
    otro routing vial de verdad.

    Se eligió Valhalla y no un segundo OSRM porque un fallo de proceso lo cubren
    los dos, pero un fallo del **motor** —una versión con un defecto, un perfil
    que rechaza una geometría— sólo lo cubre una implementación distinta. Mismos
    datos OSM, código base distinto, licencia MIT.

    El contrato de Valhalla no se parece al de OSRM: la petición va en JSON, los
    puntos son `{lat, lon}` —en ese orden, al revés que OSRM— y la distancia
    viene en **kilómetros** dentro de `trip.summary`. Convertir aquí es
    exactamente el trabajo del adaptador: el dominio recibe metros y no sabe que
    existen dos convenciones.
    """

    name = "valhalla"

    def __init__(self, base_url: str, *, timeout: float) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        cuerpo = {
            "locations": [
                {"lat": float(origen.latitude), "lon": float(origen.longitude)},
                {"lat": float(destino.latitude), "lon": float(destino.longitude)},
            ],
            "costing": "auto",
            # Sin maniobras: aquí sólo hace falta la distancia, y pedir el
            # itinerario multiplicaría la respuesta sin que nada lo use.
            "directions_type": "none",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.post(f"{self._base}/route", json=cuerpo)
        except httpx.TimeoutException as exc:
            raise RoutingUnavailable(
                f"Valhalla timed out: {exc}", transient=True
            ) from exc
        except httpx.HTTPError as exc:
            raise RoutingUnavailable(
                f"Valhalla unreachable: {exc}", transient=True
            ) from exc

        if respuesta.status_code >= 500:
            raise RoutingUnavailable(
                f"Valhalla returned {respuesta.status_code}", transient=True
            )
        if respuesta.status_code >= 400:
            # Valhalla usa 400 tanto para una petición mal formada como para "no
            # hay ruta". Las dos son permanentes: repetir la misma pregunta da
            # la misma respuesta.
            raise RoutingUnavailable(
                f"Valhalla rejected the request with {respuesta.status_code}",
                transient=False,
            )

        try:
            cuerpo_json = respuesta.json()
        except ValueError as exc:
            raise RoutingUnavailable(
                "Valhalla returned a body that is not JSON", transient=True
            ) from exc

        resumen = (cuerpo_json.get("trip") or {}).get("summary") or {}
        kilometros = resumen.get("length")
        if kilometros is None:
            raise RoutingUnavailable(
                "Valhalla returned no trip length", transient=True
            )

        # Kilómetros a metros, con `Decimal` desde la cadena para no heredar el
        # ruido del float que trae el JSON.
        metros = (Decimal(str(kilometros)) * Decimal("1000")).quantize(
            Decimal("0.01")
        )
        return SegmentResult(
            distance_meters=metros,
            provider=self.name,
            method="auto",
            version=(cuerpo_json.get("trip") or {}).get("status_message"),
        )


class FallbackRouter:
    """Primario, y si falla, la reserva. Un solo puerto para el dominio.

    Por qué la cadena vive aquí y no en el motor de kilometraje
    ----------------------------------------------------------
    Porque "qué proveedor se usó" es infraestructura, y el motor no debe tener
    que saber que hay dos. Desde `MileageService` esto es un `RoadRouter`
    cualquiera; lo que cambia es que el `SegmentResult` puede venir con el
    nombre del segundo, y **eso** es lo que acaba escrito en la provenance del
    tramo — §23 exige registrar el proveedor realmente usado, no el configurado.

    Cuándo se intenta la reserva
    ----------------------------
    Sólo cuando el fallo del primario es **transitorio**. Si el primario dice
    que no hay carretera entre esos dos puntos —fallo permanente— preguntarle a
    otro motor sobre los mismos datos OSM da casi seguro la misma respuesta, y
    convertiría un terminal honesto en un intento más. El caso que la reserva
    cubre es el primario caído, no el primario respondiendo algo que no gusta.

    Si la reserva también falla se propaga **su** error, porque describe el
    estado actual; el del primario se conserva en el mensaje para que el
    diagnóstico no pierda la mitad.
    """

    def __init__(self, primary: RoadRouter, fallback: RoadRouter) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return f"{self._primary.name}+{self._fallback.name}"

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        try:
            return await self._primary.distance(origen, destino)
        except RoutingUnavailable as fallo_primario:
            if not fallo_primario.transient:
                raise
            try:
                return await self._fallback.distance(origen, destino)
            except RoutingUnavailable as fallo_reserva:
                raise RoutingUnavailable(
                    f"primary({self._primary.name}): {fallo_primario}; "
                    f"fallback({self._fallback.name}): {fallo_reserva}",
                    transient=fallo_reserva.transient,
                ) from fallo_reserva

def haversine_meters(origen: Punto, destino: Punto) -> Decimal:
    """Distancia en línea recta. **Diagnóstico, nunca kilometraje oficial.**

    §26 permite usarla internamente para comparar y §20 prohíbe publicarla. Vive
    aquí, junto al puerto, porque su único uso es contrastar lo que devuelve el
    proveedor: una distancia vial **menor** que la línea recta es imposible, y
    detectarlo es más útil que cualquier umbral.
    """
    radio = 6_371_008.8  # metros, radio medio de la Tierra (IUGG)
    lat1, lon1 = math.radians(float(origen.latitude)), math.radians(
        float(origen.longitude)
    )
    lat2, lon2 = math.radians(float(destino.latitude)), math.radians(
        float(destino.longitude)
    )
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return Decimal(str(round(2 * radio * math.asin(math.sqrt(a)), 2)))


#: El adaptador vivo. Se sustituye en tests y en el arranque, igual que el
#: lector de odómetro: un módulo, una variable, sin registro de plugins.
_router: RoadRouter | None = None


def get_road_router() -> RoadRouter:
    """El adaptador configurado, o el que declara que no hay ninguno.

    Con `ROUTE_ROUTING_FALLBACK_URL` puesta se monta la cadena; sin ella, el
    primario a secas. La reserva no se inventa: si nadie la configuró no existe,
    y el terminal de un fallo permanente del primario es el correcto.
    """
    global _router
    if _router is None:
        url = (settings.ROUTE_ROUTING_URL or "").strip()
        if not url:
            _router = UnconfiguredRouter()
            return _router

        tiempo = settings.ROUTE_ROUTING_TIMEOUT_SECONDS
        from app.core.platform.config_service import platform_config

        radio = int(platform_config.policy("route_mileage")["snap_radius_m"])
        primario = OsrmRouter(url, timeout=tiempo, snap_radius_m=radio)
        reserva_url = (settings.ROUTE_ROUTING_FALLBACK_URL or "").strip()
        if reserva_url:
            _router = FallbackRouter(
                primario, ValhallaRouter(reserva_url, timeout=tiempo)
            )
        else:
            _router = primario
    return _router


def set_road_router(router: RoadRouter | None) -> RoadRouter | None:
    """Sustituye el adaptador y devuelve el anterior. `None` vuelve al de config."""
    global _router
    previo = _router
    _router = router
    return previo
