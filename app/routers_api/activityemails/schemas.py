from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.params import CommonQueryParams


class TokenHelp(BaseModel):
    token: str
    description: str
    required: bool


class ActivityEmailTemplateRead(BaseModel):
    template_type: str
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
    ):
        super().__init__(page=page, page_size=page_size)
        self.q = (q or "").strip() or None


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
