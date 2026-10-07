"""El motor de kilometraje oficial (RTE06-CP3).

La definición, entera
---------------------
§15: el kilometraje oficial es **la suma de las distancias viales entre los
waypoints autoritativos ordenados del viaje**:

    Start Trip → cada Change Plan en orden de ocurrencia → Arrived

Un `Change Plan` no cierra el viaje ni crea otro (§15.4): parte el cálculo en
tramos consecutivos dentro del **mismo** viaje, que tiene un solo resultado
oficial.

Lo que este módulo no hace nunca
--------------------------------
No usa odómetro, ni Haversine, ni breadcrumbs, ni el texto del destino, ni
coordenadas geocodificadas, ni un punto prestado de otro evento o de otro viaje
(§20). Y si falta un waypoint requerido, **no** calcula el resto y lo presenta
como total: §17 dice que el atajo silencioso Start→Arrived es precisamente lo
que hay que impedir, y que CER prefiere un `Not Calculable` veraz a un número
incompleto presentado como completo.

La inmutabilidad, en el `WHERE`
-------------------------------
Toda transición es `UPDATE ... WHERE state = 'pending_calculation'`. Si
`rowcount == 0`, la fila ya era terminal y no se toca — así que ningún
reintento, trabajo duplicado, cambio de proveedor o de umbral puede alterar un
`calculated` (§27). No es un permiso ni un disparador: es la forma de la
escritura, el mismo patrón que ya protege la terminalización de actividades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update

from app.core.audit.service import record_event
from app.core.db.session import db_session, transaction
from app.core.platform.config_service import platform_config
from app.routers_api.location.dao import LocationFixesDAO, MissingLocationEventsDAO
from app.routers_api.location.models import LocationEventKind, LocationFix
from app.routers_api.mileage.models import (
    MileageState,
    MileageTerminalReason,
    TripMileage,
    TripMileageSegment,
)
from app.routers_api.mileage.read import (
    DOS_DECIMALES,
    METROS_POR_MILLA,
    millas_oficiales,
)
from app.routers_api.mileage.routing import (
    Punto,
    RoutingUnavailable,
    get_road_router,
    haversine_meters,
)
from app.routers_api.trips.models import Trip, TripStatus

__all__ = ["METROS_POR_MILLA"]  # se reexporta: era público desde RTE06


def _politica() -> dict:
    return platform_config.policy("route_mileage")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def miles_from_meters(metros: Decimal | None) -> Decimal | None:
    """Millas con dos decimales. La conversión se hace al **leer**.

    En la base se guardan metros, que es lo que devuelve el proveedor. Guardar
    las dos unidades sería guardar el mismo hecho dos veces y redondearlo dos
    veces; la segunda copia acabaría no cuadrando con la primera.

    Delega en `millas_oficiales` y conserva su propia firma —`None` entra,
    `None` sale— porque aquí sí importa distinguir «no hay kilometraje» de
    «cero millas»: esta función responde por un viaje concreto, no por el total
    de una pantalla.
    """
    if metros is None:
        return None
    return millas_oficiales(metros, precision=DOS_DECIMALES)


@dataclass(frozen=True)
class Waypoint:
    """Un punto autoritativo del viaje, con su procedencia."""

    event_kind: str
    fix_id: int
    latitude: Decimal
    longitude: Decimal
    evidence_level: str
    accuracy_m: Decimal | None
    captured_at: datetime

    @classmethod
    def de_fix(cls, fila: LocationFix) -> Waypoint:
        return cls(
            event_kind=fila.event_kind,
            fix_id=fila.id,
            latitude=fila.latitude,
            longitude=fila.longitude,
            evidence_level=fila.evidence_level,
            accuracy_m=fila.accuracy_m,
            captured_at=fila.device_captured_at,
        )

    @property
    def punto(self) -> Punto:
        return Punto(latitude=self.latitude, longitude=self.longitude)


@dataclass(frozen=True)
class SecuenciaDeWaypoints:
    """El resultado de intentar reconstruir la secuencia autoritativa.

    Tres respuestas posibles, y las tres importan:

    * `waypoints` con contenido y `falta` a `None` → se puede calcular;
    * `falta` con una razón terminal → no se podrá nunca (§17, §19);
    * los dos a `None`/vacío → **todavía** no: hay un evento sin punto y sin
      Missing, así que sigue en ventana de recuperación y el viaje se queda
      pendiente. Confundir este caso con el anterior terminalizaría viajes cuya
      evidencia aún estaba en camino.
    """

    waypoints: tuple[Waypoint, ...] = ()
    falta: MileageTerminalReason | None = None
    esperando: bool = False


class MileageWaypointService:
    """Reconstruye la secuencia autoritativa de un viaje."""

    @staticmethod
    async def build(*, company_id: int, trip: Trip) -> SecuenciaDeWaypoints:
        """Start Trip → Change Plan(s) → Arrived, en orden de **ocurrencia**.

        El orden lo da el DAO desde las filas de dominio, no desde las horas de
        captura: un punto recuperado tres minutos después del evento se
        colocaría fuera de su sitio si se ordenara por `device_captured_at`, y
        eso es correlacionar por proximidad de tiempo — prohibido por §14.
        """
        if trip.status == TripStatus.INTERRUPTED.value and trip.arrived_at is None:
            # §19: no se fabrica llegada, no se usa End Work como destino y no
            # se infiere un endpoint. El viaje no tiene final que enrutar.
            return SecuenciaDeWaypoints(
                falta=MileageTerminalReason.INTERRUPTED_WITHOUT_ARRIVAL
            )

        puntos = await LocationFixesDAO.for_trip_waypoints(
            company_id=company_id, trip_id=trip.id
        )
        por_evento: dict[tuple[str, int], LocationFix] = {
            (p.event_kind, p.subject_id): p for p in puntos
        }
        perdidos = await MissingLocationEventsDAO.subject_ids_for_trip(
            company_id=company_id, trip_id=trip.id
        )

        requeridos = await MileageWaypointService._eventos_requeridos(
            company_id=company_id, trip=trip
        )

        secuencia: list[Waypoint] = []
        esperando = False
        for evento, subject_id, razon_si_falta in requeridos:
            fila = por_evento.get((evento.value, subject_id))
            if fila is not None:
                secuencia.append(Waypoint.de_fix(fila))
                continue
            if (evento.value, subject_id) in perdidos:
                # Dado por perdido: terminal. El Change Plan **se conserva** en
                # su historia; lo que no se puede es saltárselo y calcular
                # Start→Arrived como si el cambio no hubiera ocurrido (§17).
                return SecuenciaDeWaypoints(falta=razon_si_falta)
            # Ni punto ni Missing: sigue en ventana de recuperación.
            esperando = True

        if esperando:
            return SecuenciaDeWaypoints(esperando=True)
        return SecuenciaDeWaypoints(waypoints=tuple(secuencia))

    @staticmethod
    async def _eventos_requeridos(
        *, company_id: int, trip: Trip
    ) -> list[tuple[LocationEventKind, int, MileageTerminalReason]]:
        """Qué waypoints exige este viaje, en orden, y qué significa que falten.

        Los `Change Plan` se leen de `trip_purpose_change` ordenados por
        `changed_at`: son los que de verdad ocurrieron. HOME no es un caso
        aparte (§18): un viaje a casa tiene la misma secuencia y cierra en
        `Arrived` igual que cualquier otro.
        """
        from sqlalchemy import text as _text

        async with db_session() as sesion:
            cambios = (
                await sesion.execute(
                    _text(
                        "SELECT id FROM trip_purpose_change "
                        "WHERE trip_id = :t AND company_id = :c "
                        "ORDER BY changed_at, id"
                    ),
                    {"t": trip.id, "c": company_id},
                )
            ).scalars().all()

        requeridos: list[tuple[LocationEventKind, int, MileageTerminalReason]] = [
            (
                LocationEventKind.START_TRIP,
                trip.id,
                MileageTerminalReason.START_WAYPOINT_MISSING,
            )
        ]
        requeridos += [
            (
                LocationEventKind.CHANGE_PLAN,
                cambio_id,
                MileageTerminalReason.CHANGE_PLAN_WAYPOINT_MISSING,
            )
            for cambio_id in cambios
        ]
        requeridos.append(
            (
                LocationEventKind.ARRIVED,
                trip.id,
                MileageTerminalReason.ARRIVAL_WAYPOINT_MISSING,
            )
        )
        return requeridos


class MileageService:
    """Crea, calcula y terminaliza el kilometraje de un viaje."""

    @staticmethod
    async def ensure_pending(*, company_id: int, trip_id: int) -> TripMileage | None:
        """Crea la fila pendiente si el viaje aún no tiene.

        La llama la transición del viaje a `ARRIVED` o `INTERRUPTED`, dentro de
        la **misma** transacción: así ningún viaje terminado se queda sin fila
        de kilometraje, que es la única forma de que el sweeper pueda
        encontrarlos todos.

        Idempotente: la restricción única de `(trip_id, company_id)` hace que un
        trabajo duplicado no cree un segundo hecho oficial (§27).
        """
        async with db_session() as sesion:
            ya = await sesion.scalar(
                select(TripMileage).where(
                    TripMileage.company_id == company_id,
                    TripMileage.trip_id == trip_id,
                )
            )
        if ya is not None:
            return ya

        from sqlalchemy.exc import IntegrityError

        fila = TripMileage(
            company_id=company_id,
            trip_id=trip_id,
            state=MileageState.PENDING_CALCULATION.value,
            next_attempt_at=_ahora(),
        )
        try:
            async with transaction() as sesion:
                sesion.add(fila)
                await sesion.flush()
            return fila
        except IntegrityError:
            async with db_session() as sesion:
                return await sesion.scalar(
                    select(TripMileage).where(
                        TripMileage.company_id == company_id,
                        TripMileage.trip_id == trip_id,
                    )
                )

    @classmethod
    async def calculate(cls, *, mileage_id: int) -> str:
        """Intenta llevar un kilometraje pendiente a su estado terminal.

        Devuelve el estado resultante. Un `calculated` que llegue aquí sale sin
        tocarse: la lectura lo comprueba y, además, el `WHERE` de cada
        escritura lo haría imposible.
        """
        async with db_session() as sesion:
            km = await sesion.get(TripMileage, mileage_id)
            if km is None:
                return "missing"
            if km.state != MileageState.PENDING_CALCULATION.value:
                return km.state
            viaje = await sesion.scalar(
                select(Trip).where(
                    Trip.id == km.trip_id, Trip.company_id == km.company_id
                )
            )
        if viaje is None:
            return km.state

        secuencia = await MileageWaypointService.build(
            company_id=km.company_id, trip=viaje
        )

        if secuencia.falta is not None:
            await cls._terminalizar(
                km, MileageState.NOT_CALCULABLE, razon=secuencia.falta
            )
            return MileageState.NOT_CALCULABLE.value

        if secuencia.esperando or len(secuencia.waypoints) < 2:
            # Menos de dos waypoints con todo presente no debería ocurrir —la
            # secuencia siempre pide Start y Arrived—, pero si ocurre es porque
            # falta evidencia, no porque el viaje midiera cero.
            await cls._reprogramar(km, error="Waiting for location evidence")
            return MileageState.PENDING_CALCULATION.value

        return await cls._enrutar_y_consolidar(km, secuencia.waypoints)

    @classmethod
    async def _enrutar_y_consolidar(
        cls, km: TripMileage, waypoints: tuple[Waypoint, ...]
    ) -> str:
        """Enruta cada pareja consecutiva y consolida, o no consolida nada.

        §25: un total parcial **no** se publica como kilometraje final. Así que
        los tramos se calculan todos primero y sólo se escriben si todos
        salieron bien. Si uno falla de forma transitoria, la fila sigue
        pendiente y se reintenta; si falla de forma permanente o no es
        plausible tras agotar los intentos, el viaje entero va a
        `calculation_failed`.
        """
        router = get_road_router()
        politica = _politica()
        calculados: list[dict] = []

        for indice in range(len(waypoints) - 1):
            origen, destino = waypoints[indice], waypoints[indice + 1]
            try:
                resultado = await router.distance(origen.punto, destino.punto)
            except RoutingUnavailable as fallo:
                if fallo.transient:
                    return await cls._fallo_transitorio(km, str(fallo))
                return await cls._fallo_permanente(
                    km, str(fallo), MileageTerminalReason.ROUTING_EXHAUSTED
                )

            recta = haversine_meters(origen.punto, destino.punto)
            problema = _implausible(
                distancia=resultado.distance_meters,
                recta=recta,
                origen=origen,
                destino=destino,
                politica=politica,
            )
            if problema is not None:
                # §26: un tramo sospechoso **no se consolida**. Se reintenta, y
                # si insiste acaba en terminal — pero nunca se guarda.
                return await cls._fallo_transitorio(
                    km, f"Implausible segment {indice + 1}: {problema}",
                    razon_al_agotar=MileageTerminalReason.IMPLAUSIBLE_SEGMENT,
                )

            calculados.append(
                {
                    "sequence": indice + 1,
                    "from": origen,
                    "to": destino,
                    "distance_meters": resultado.distance_meters,
                    "provider": resultado.provider,
                    "method": resultado.method,
                    "provider_version": resultado.version,
                    "haversine_meters": recta,
                }
            )

        total = sum((t["distance_meters"] for t in calculados), Decimal("0"))
        return await cls._consolidar(km, calculados, total)

    @staticmethod
    async def _consolidar(
        km: TripMileage, tramos: list[dict], total: Decimal
    ) -> str:
        """Escribe los tramos y pasa a `calculated`, o no hace nada.

        Las dos cosas en una transacción, y el estado con su `WHERE`: si otro
        trabajo llegó antes, `rowcount == 0` y los tramos no se escriben. Sin
        eso, dos trabajos concurrentes podrían duplicar la provenance de un
        kilometraje que ya estaba resuelto.
        """
        ahora = _ahora()
        async with transaction() as sesion:
            resultado = await sesion.execute(
                update(TripMileage)
                .where(
                    TripMileage.id == km.id,
                    TripMileage.state == MileageState.PENDING_CALCULATION.value,
                )
                .values(
                    state=MileageState.CALCULATED.value,
                    total_meters=total,
                    calculated_at=ahora,
                    terminal_reason=None,
                    last_error=None,
                    next_attempt_at=None,
                )
            )
            if resultado.rowcount == 0:
                return "already_terminal"

            for tramo in tramos:
                origen, destino = tramo["from"], tramo["to"]
                sesion.add(
                    TripMileageSegment(
                        company_id=km.company_id,
                        trip_mileage_id=km.id,
                        sequence=tramo["sequence"],
                        from_event_kind=origen.event_kind,
                        from_latitude=origen.latitude,
                        from_longitude=origen.longitude,
                        from_evidence_level=origen.evidence_level,
                        from_accuracy_m=origen.accuracy_m,
                        from_captured_at=origen.captured_at,
                        from_fix_id=origen.fix_id,
                        to_event_kind=destino.event_kind,
                        to_latitude=destino.latitude,
                        to_longitude=destino.longitude,
                        to_evidence_level=destino.evidence_level,
                        to_accuracy_m=destino.accuracy_m,
                        to_captured_at=destino.captured_at,
                        to_fix_id=destino.fix_id,
                        distance_meters=tramo["distance_meters"],
                        provider=tramo["provider"],
                        method=tramo["method"],
                        provider_version=tramo["provider_version"],
                        computed_at=ahora,
                        haversine_meters=tramo["haversine_meters"],
                    )
                )

        await record_event(
            company_id=km.company_id,
            entity_type="trip_mileage",
            entity_id=km.id,
            action="calculated",
            actor_user_id=None,
            summary=f"Trip mileage calculated over {len(tramos)} routed segment(s)",
            changes={
                "state": {"old": MileageState.PENDING_CALCULATION.value, "new": MileageState.CALCULATED.value},
                "total_meters": str(total),
                "segments": len(tramos),
                "provider": tramos[0]["provider"] if tramos else None,
            },
        )
        return MileageState.CALCULATED.value

    @classmethod
    async def _fallo_transitorio(
        cls,
        km: TripMileage,
        error: str,
        *,
        razon_al_agotar: MileageTerminalReason = MileageTerminalReason.ROUTING_EXHAUSTED,
    ) -> str:
        """Reintenta, y si ya no quedan intentos, terminaliza diciendo por qué."""
        politica = _politica()
        if km.attempt_count + 1 >= int(politica["max_attempts"]):
            return await cls._fallo_permanente(km, error, razon_al_agotar)
        await cls._reprogramar(km, error=error)
        return MileageState.PENDING_CALCULATION.value

    @staticmethod
    async def _reprogramar(km: TripMileage, *, error: str) -> None:
        """Suma un intento y pone la próxima cita, con backoff exponencial."""
        politica = _politica()
        intento = km.attempt_count + 1
        espera = int(politica["backoff_base_seconds"]) * (2 ** (intento - 1))
        async with transaction() as sesion:
            await sesion.execute(
                update(TripMileage)
                .where(
                    TripMileage.id == km.id,
                    TripMileage.state == MileageState.PENDING_CALCULATION.value,
                )
                .values(
                    attempt_count=intento,
                    next_attempt_at=_ahora() + timedelta(seconds=espera),
                    last_error=error[:500],
                )
            )

    @classmethod
    async def _fallo_permanente(
        cls, km: TripMileage, error: str, razon: MileageTerminalReason
    ) -> str:
        await cls._terminalizar(
            km, MileageState.CALCULATION_FAILED, razon=razon, error=error
        )
        return MileageState.CALCULATION_FAILED.value

    @staticmethod
    async def _terminalizar(
        km: TripMileage,
        estado: MileageState,
        *,
        razon: MileageTerminalReason,
        error: str | None = None,
    ) -> None:
        """Pasa a un estado terminal de excepción. Nunca escribe un total.

        El `CHECK` de la tabla lo garantiza además: un estado distinto de
        `calculated` con `total_meters` no nulo no puede existir, así que un
        total parcial no puede colarse ni por error de programación (§25).
        """
        async with transaction() as sesion:
            resultado = await sesion.execute(
                update(TripMileage)
                .where(
                    TripMileage.id == km.id,
                    TripMileage.state == MileageState.PENDING_CALCULATION.value,
                )
                .values(
                    state=estado.value,
                    terminal_reason=razon.value,
                    last_error=(error or "")[:500] or None,
                    next_attempt_at=None,
                )
            )
            if resultado.rowcount == 0:
                return

        await record_event(
            company_id=km.company_id,
            entity_type="trip_mileage",
            entity_id=km.id,
            action="terminalized",
            actor_user_id=None,
            summary=f"Trip mileage {estado.value}: {razon.value}",
            changes={
                "state": {
                    "old": MileageState.PENDING_CALCULATION.value,
                    "new": estado.value,
                },
                "terminal_reason": razon.value,
            },
        )


def _implausible(
    *,
    distancia: Decimal,
    recta: Decimal,
    origen: Waypoint,
    destino: Waypoint,
    politica: dict,
) -> str | None:
    """Por qué este tramo no es creíble, o `None` si lo es (§26).

    Tres comprobaciones, de la más segura a la más discutible:

    1. **Más corto que la línea recta.** Geométricamente imposible: por
       carretera nunca se va menos que en línea recta. No depende de ningún
       umbral configurable, así que se aplica siempre — es la única de las tres
       que no puede dar un falso positivo.
    2. **Distancia absoluta desmedida.** Por encima del límite es casi seguro
       una coordenada mal formada, no un viaje.
    3. **Velocidad implícita imposible.** Distancia entre el tiempo que separa
       las dos capturas. Atrapa lo que un límite de distancia no ve: 50 km en
       cuatro minutos. Se omite si las capturas no están separadas en el tiempo,
       porque entonces la división no dice nada.
    """
    if distancia < recta:
        return (
            f"routed {distancia}m is shorter than the straight line {recta}m, "
            "which is geometrically impossible"
        )

    if not politica.get("plausibility_enabled", True):
        return None

    limite = Decimal(str(politica["segment_max_meters"]))
    if distancia > limite:
        return f"routed {distancia}m exceeds the {limite}m segment limit"

    segundos = (destino.captured_at - origen.captured_at).total_seconds()
    if segundos > 0:
        kmh = (distancia / Decimal("1000")) / (Decimal(str(segundos)) / Decimal("3600"))
        maximo = Decimal(str(politica["implied_speed_max_kmh"]))
        if kmh > maximo:
            return f"implied speed {kmh.quantize(Decimal('0.1'))} km/h exceeds {maximo}"

    return None


async def sweep_pending_mileage(*, limit: int = 100) -> dict[str, int]:
    """Reintenta lo vencido y terminaliza lo que agotó sus intentos (§24, R3).

    Es lo que garantiza que ningún viaje se queda `Pending` para siempre. Se
    registra en el scheduler existente con elección de líder, así que en varias
    instancias corre una sola vez.
    """
    ahora = _ahora()
    async with db_session() as sesion:
        pendientes = (
            await sesion.execute(
                select(TripMileage.id)
                .where(
                    TripMileage.state == MileageState.PENDING_CALCULATION.value,
                    TripMileage.next_attempt_at <= ahora,
                )
                .order_by(TripMileage.next_attempt_at)
                .limit(limit)
            )
        ).scalars().all()

    resumen = {"examined": len(pendientes)}
    for mileage_id in pendientes:
        estado = await MileageService.calculate(mileage_id=mileage_id)
        resumen[estado] = resumen.get(estado, 0) + 1
    return resumen
