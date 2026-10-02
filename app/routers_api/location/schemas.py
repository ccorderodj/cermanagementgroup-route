"""Contratos de entrada y salida de la evidencia de ubicación (RTE06-CP2).

Lo que el cliente **no** puede decir
------------------------------------
Ni la compañía, ni quién actúa, ni la jornada. Salen de la sesión autenticada y
del subdominio (§31). El cliente dice qué evento, de qué sujeto, y qué midió el
dispositivo; el servidor decide si eso puede pertenecerle.

`evidence_level` sí lo dice el cliente, y es deliberado: sólo el dispositivo
sabe si el punto salió de una medición nueva o de la caché. Lo que el servidor
**no** acepta es la combinación incoherente — un `fresh` con edad declarada, o
un `degraded_cached` sin ella— y eso lo rechazan a la vez el schema y el `CHECK`
de la tabla.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.routers_api.location.models import (
    LocationEventKind,
    LocationEvidenceLevel,
    LocationPermissionState,
    MissingLocationReason,
)


class LocationAttempt(BaseModel):
    """Una etapa de adquisición, tal como la vivió el cliente.

    Es evidencia de intento (§29), no diagnóstico interpretado: `stage`,
    cuánto tardó y qué error dio la plataforma. Nada de conclusiones sobre por
    qué falló el GPS, que es lo que §29 prohíbe inventar.
    """

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(max_length=40)
    started_at: datetime
    duration_ms: int = Field(ge=0, le=10 * 60 * 1000)
    #: El código de error de la plataforma, si lo hubo. `1` permiso, `2`
    #: posición no disponible, `3` timeout, en la Geolocation API.
    error_code: int | None = Field(default=None, ge=0, le=99)
    error_message: str | None = Field(default=None, max_length=300)


class LocationEvidenceIn(BaseModel):
    """Un punto capturado para un evento del ciclo de vida."""

    model_config = ConfigDict(extra="forbid")

    event_kind: LocationEventKind
    #: La fila de dominio a la que pertenece el evento. Qué tabla es lo decide
    #: `event_kind`, no el cliente: ver `subject_kind_for`.
    #:
    #: Opcional desde el cierre final: sin red el id **todavía no existe**, y
    #: entonces se identifica el sujeto por `client_action_key`.
    subject_id: int | None = Field(default=None, gt=0)
    #: La clave durable de la acción que **creó** la fila del sujeto.
    #:
    #: Es lo que hace que un punto capturado sin red se ate después a su acción
    #: exacta: el servidor busca la fila con esa clave. Un identificador, no
    #: autoridad — la comprobación de propiedad se aplica igual (§12).
    client_action_key: str | None = Field(default=None, max_length=64)

    evidence_level: LocationEvidenceLevel
    latitude: Decimal = Field(ge=-90, le=90, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, decimal_places=7)
    accuracy_m: Decimal | None = Field(default=None, ge=0, le=1_000_000)

    #: Cuándo lo midió el dispositivo. Es la hora que manda: un punto cacheado
    #: no pasa a fresco porque se suba tarde (§32).
    device_captured_at: datetime
    #: Sólo para `degraded_cached`, y obligatoria ahí.
    source_age_seconds: int | None = Field(default=None, ge=0, le=86_400 * 30)
    permission_state: LocationPermissionState | None = None

    @model_validator(mode="after")
    def _identifica_el_sujeto(self) -> LocationEvidenceIn:
        """Exactamente una forma de identificar el sujeto, nunca ninguna ni dos.

        Dos formas a la vez permitirían que el cliente mandara un id de una
        fila y la clave de otra, y el servidor tendría que decidir cuál cree.
        Esa decisión no debe existir.
        """
        if (self.subject_id is None) == (self.client_action_key is None):
            raise ValueError(
                "provide exactly one of subject_id or client_action_key"
            )
        return self

    @model_validator(mode="after")
    def _coherencia_del_nivel(self) -> LocationEvidenceIn:
        cacheado = self.evidence_level is LocationEvidenceLevel.DEGRADED_CACHED
        if cacheado and self.source_age_seconds is None:
            raise ValueError(
                "degraded_cached evidence must state source_age_seconds"
            )
        if not cacheado and self.source_age_seconds is not None:
            raise ValueError(
                "source_age_seconds only applies to degraded_cached evidence"
            )
        return self


class MissingLocationIn(BaseModel):
    """La ventana de recuperación se agotó sin punto para este evento."""

    model_config = ConfigDict(extra="forbid")

    event_kind: LocationEventKind
    subject_id: int | None = Field(default=None, gt=0)
    #: Igual que en la evidencia: sin red el id no existe todavía.
    client_action_key: str | None = Field(default=None, max_length=64)
    reason_code: MissingLocationReason
    permission_state: LocationPermissionState | None = None
    attempts: list[LocationAttempt] = Field(default_factory=list, max_length=20)
    #: Metadatos del último punto rechazado: su edad y su precisión. **Nunca**
    #: sus coordenadas — saber que había un punto de hace dos horas con 3 km de
    #: error explica el fallo; guardar dónde estaba sería conservar una
    #: ubicación que el sistema decidió no usar.
    rejected_age_seconds: int | None = Field(default=None, ge=0)
    rejected_accuracy_m: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _identifica_el_sujeto(self) -> MissingLocationIn:
        if (self.subject_id is None) == (self.client_action_key is None):
            raise ValueError(
                "provide exactly one of subject_id or client_action_key"
            )
        return self


class LocationEvidenceRead(BaseModel):
    """Lo que se devuelve tras registrar. Sin coordenadas.

    El cliente ya sabe dónde estaba: devolvérselas no añade nada y multiplica
    los sitios por los que una coordenada puede acabar en un log (§35).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_kind: str
    subject_id: int
    evidence_level: str
    device_captured_at: datetime
    server_received_at: datetime
    #: `True` cuando esta llamada no escribió nada porque el punto ya estaba.
    #: El reenvío de la cola offline es idempotente y esto lo hace visible.
    replayed: bool = False


class MissingLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_kind: str
    subject_id: int
    reason_code: str
    occurred_at: datetime
    #: El estado de **entrega** del aviso, leído de
    #: `missing_location_notification`. Se devuelve aquí por comodidad del
    #: cliente; no es un campo del hecho, que es inmutable
    #: (D-RTE06-MISSING-01).
    notification_status: str = "pending"
    replayed: bool = False


class LocationPolicyRead(BaseModel):
    """Los umbrales que el cliente necesita para capturar.

    Por qué existe
    --------------
    El cliente tenía estos cinco números escriturados en el bundle y no había
    forma de que los de la compañía llegaran: `setLocationPolicy` estaba
    exportada y no la llamaba nadie, así que `route_location` —que es política
    de plataforma, editable— no tenía ningún efecto en el dispositivo. Un
    administrador que bajara `fresh_max_accuracy_m` veía la pantalla aceptar el
    cambio y el teléfono seguía con 100.

    No es un control: el servidor vuelve a comprobar los criterios al recibir
    (`LocationEvidenceService._validar_calidad`). Esto evita que el cliente
    gaste capturas que el servidor va a rechazar, y que la ventana de
    recuperación dure algo distinto de lo que la compañía configuró.
    """

    model_config = ConfigDict(from_attributes=True)

    fresh_timeout_seconds: int
    fresh_max_accuracy_m: int
    cached_max_age_seconds: int
    cached_max_accuracy_m: int
    recovery_window_seconds: int
    #: Va con los demas porque el cliente necesita saber **cuando deja de tener
    #: sentido reintentar** un envio: pasada la ventana mas este margen, el
    #: servidor cierra el hecho por su cuenta y el reintento no puede ganar.
    sweeper_grace_seconds: int
