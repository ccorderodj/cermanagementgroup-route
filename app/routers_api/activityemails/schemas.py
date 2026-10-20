from datetime import date, datetime
from typing import Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.params import CommonQueryParams


class TokenHelp(BaseModel):
    token: str
    description: str
    required: bool


class ActivityEmailTemplateRead(BaseModel):
    template_type: str
    #: `motivational` o `strategic`: la pantalla los agrupa por esto.
    group: str
    label: str
    schedule_label: str
    #: Cuándo se envía; sin actividades completadas, no hay correo.
    send_condition: str
    subject: str
    body: str
    #: `True` mientras la compañía usa el texto aprobado sin cambios.
    is_default: bool
    #: 0 si nunca se ha guardado: es la versión que hay que enviar al guardar.
    version: int
    updated_at: datetime | None = None
    updated_by_name: str | None = None
    subject_tokens: list[str]
    tokens: list[TokenHelp]


class ActivityEmailTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=1000)
    body: str = Field(max_length=20000)
    version: int = Field(ge=0)


class ActivityEmailTemplateRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)


class ActivityEmailPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=1000)
    body: str = Field(max_length=20000)


class ActivityEmailPreview(BaseModel):
    #: Siempre `True`: la vista previa usa datos ficticios y no envía nada.
    is_sample: bool = True
    sample_label: str
    subject: str
    body: str


class ActivityEmailRecipientRead(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    username: str
    email: str
    role_name: str | None
    midday_enabled: bool
    end_of_day_enabled: bool
    #: Si hoy se le puede activar. `False` deja los interruptores bloqueados.
    eligible: bool
    #: `inactive` / `invalid_email`; `None` si es elegible.
    ineligible_reason: str | None
    version: int


class ActivityEmailRecipientUpdate(BaseModel):
    """Uno o los dos interruptores; el que no venga no se toca (UC-04)."""

    model_config = ConfigDict(extra="forbid")

    midday_enabled: bool | None = None
    end_of_day_enabled: bool | None = None
    version: int = Field(ge=0)


class RecipientsPaginationParams(CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        q: str | None = Query(None, max_length=150),
        include_self: bool = Query(False),
    ):
        super().__init__(page=page, page_size=page_size)
        self.q = (q or "").strip() or None
        # Sólo «Generate report»: un mando puede pedir su propio reporte, pero
        # no configura sus propios interruptores (la pestaña lo pide en False).
        self.include_self = include_self


class ActivityEmailTestTargets(BaseModel):
    """A quién se puede mandar una prueba, y si hay un proveedor real detrás."""

    recipients: list[str]
    provider_configured: bool
    limit: int
    window_minutes: int


class ActivityEmailTestSend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(min_length=3, max_length=254)


class ActivityEmailTestResult(BaseModel):
    #: `accepted_by_provider`, `not_sent_development_backend` o
    #: `captured_by_test_backend`. Los fallos responden 502.
    outcome: str
    to: str
    subject: str
    #: El tipo de backend que de verdad lo tomó (`m365_oauth`, `smtp_basic`,
    #: `console`, `memory`). Sin host ni cuenta.
    backend: str | None
    #: Siempre `False`: la entrega sólo la confirma la bandeja de destino.
    delivered_confirmed: bool


class StrategicRecipientRead(BaseModel):
    """Un mando y sus dos interruptores de reporte estratégico."""

    user_id: int
    first_name: str
    last_name: str
    email: str
    role_name: str | None
    #: Personas que hoy están en su rama: las que tendría su reporte.
    coverage: int
    strategic_midday_enabled: bool
    strategic_end_of_day_enabled: bool
    eligible: bool
    #: `inactive` / `invalid_email` / `no_team`; `None` si es elegible.
    ineligible_reason: str | None
    version: int


class StrategicRecipientUpdate(BaseModel):
    """Uno o los dos interruptores estratégicos; el otro, y los motivacionales,
    no cambian."""

    model_config = ConfigDict(extra="forbid")

    strategic_midday_enabled: bool | None = None
    strategic_end_of_day_enabled: bool | None = None
    version: int = Field(ge=0)


# ── Reportes reales a demanda (RTE-MAIL-CP4-02) ─────────────────────────────


class ReportRequest(BaseModel):
    """Qué reporte, de quién y de qué día. Ni correo, ni alcance, ni datos."""

    model_config = ConfigDict(extra="forbid")

    report_type: str = Field(max_length=40)
    recipient_user_id: int
    operational_date: date


class ReportSendRequest(ReportRequest):
    #: Por qué se envía a mano (recuperar un envío que no salió…). Auditado.
    reason: str | None = Field(default=None, max_length=300)


class ReportResendRequest(ReportRequest):
    #: Cuántos reenvíos vio quien pulsa. Si otro reenvió entre medias, 409.
    expected_resends: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=300)


class ResendRead(BaseModel):
    id: int
    sequence: int
    status: str
    reason_code: str | None
    requested_by_user_id: int | None
    provider_backend: str | None
    #: Aceptado por el proveedor; **no** es la entrega en el buzón.
    accepted_at: datetime | None
    created_at: datetime


class ResendResult(ResendRead):
    destination_masked: str | None


class DeliveryRead(BaseModel):
    id: int
    report_type: str
    recipient_user_id: int
    operational_date: date
    status: str
    source: str
    attempt_count: int
    cutoff_at: datetime | None
    due_at: datetime | None
    last_attempt_at: datetime | None
    #: Aceptado por el proveedor; **no** es la entrega en el buzón.
    accepted_at: datetime | None
    reason_code: str | None
    requested_by_user_id: int | None
    provider_backend: str | None


class HistoryResendRead(ResendRead):
    reason_message: str | None


class DeliveryHistoryRead(DeliveryRead):
    """Una fila de Delivery History. Sin asunto, cuerpo, notas ni destino."""

    recipient_name: str
    time_zone: str | None
    next_attempt_at: datetime | None
    #: Cuánto después del vencimiento salió (sólo envíos automáticos).
    delay_seconds: int | None
    reason_message: str | None
    resends: list[HistoryResendRead]


class HistoryParams(CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        report_type: str | None = Query(None, max_length=40),
        recipient_user_id: int | None = Query(None),
        trigger: Literal["scheduler", "reconcile", "manual", "resend"] | None = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.date_from, self.date_to = date_from, date_to
        self.report_type, self.recipient_user_id, self.trigger = report_type, recipient_user_id, trigger


class DispatchRunRead(BaseModel):
    source: str
    started_at: datetime
    finished_at: datetime
    outcome: str
    enabled: bool
    dry_run: bool
    counts: dict[str, int]


class OperationalStatusRead(BaseModel):
    """El estado del envío, leído del servidor (no el texto fijo de antes)."""

    provider_status: str
    provider_verified_at: datetime | None
    automation_enabled: bool
    dry_run: bool
    real_send_types: list[str]
    recovery_window_hours: int
    #: Última pasada vista de cada reloj; vacío si nunca se ha visto ninguna.
    runs: list[DispatchRunRead]


class ReportPreviewRead(BaseModel):
    """La vista previa **real**: nada se escribe ni se envía al generarla."""

    report_type: str
    recipient_user_id: int
    recipient_name: str
    destination_masked: str | None
    operational_date: date
    time_zone: str | None
    cutoff_at: datetime | None
    due_at: datetime | None
    generated_at: datetime
    #: `True` mientras la ventana no ha cerrado («Parcial»).
    provisional: bool
    eligible: bool
    reason_code: str | None
    reason_message: str | None
    coverage: int | None
    activity_count: int
    subject: str | None
    body: str | None
    can_send: bool
    blocked_reason: str | None
    blocked_message: str | None
    delivery: DeliveryRead | None
    can_resend: bool
    resend_blocked_reason: str | None
    resend_blocked_message: str | None
    resends: list[ResendRead]


class ReportSendResult(DeliveryRead):
    destination_masked: str | None
