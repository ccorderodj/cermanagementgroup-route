"""
Contratos de Settings de plataforma.

Ningún esquema de salida tiene un campo para el valor de un secreto. No es que se
omita al serializar: es que no hay dónde ponerlo.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderFieldRead(BaseModel):
    name: str
    label: str
    kind: str
    source: str
    format: str
    required: bool
    default: str | int | bool | None = None
    choices: list[str] = []
    #: La expresión con la que valida el servidor, para que la guía avise antes
    #: de guardar y no después.
    pattern: str | None = None
    expires: bool = False


class GuideStepRead(BaseModel):
    text: str
    link: str | None = None


class DocLinkRead(BaseModel):
    label: str
    url: str


class ProviderRead(BaseModel):
    key: str
    title: str
    summary: str
    who: str
    recommended: bool
    available: bool
    steps: list[GuideStepRead]
    fields: list[ProviderFieldRead]
    warnings: list[str]
    docs: list[DocLinkRead]


class SecretStateRead(BaseModel):
    name: str
    label: str
    present: bool
    set_at: datetime | None = None
    expires_at: datetime | None = None


class IntegrationRead(BaseModel):
    key: str
    title: str
    summary: str
    required: bool
    open_decision: str | None = None
    providers: list[ProviderRead]
    provider: str | None = None
    enabled: bool
    status: str
    missing: list[str]
    config: dict[str, str | int | bool]
    secrets: list[SecretStateRead]
    verified_at: datetime | None = None
    version: int


class IntegrationUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    config: dict[str, str | int | bool] = {}
    enabled: bool = True
    expected_version: int | None = None


class SecretWrite(BaseModel):
    value: str = Field(min_length=1, max_length=4096)
    expires_at: date | None = None


class PolicyRead(BaseModel):
    key: str
    title: str
    summary: str
    value: dict
    defaults: dict
    customized: bool
    version: int


class PolicyUpdate(BaseModel):
    value: dict
    expected_version: int | None = None


class PlatformAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_user_id: int | None = None
    actor_role: str | None = None
    action: str
    target: str
    changes: dict | None = None
    request_id: str | None = None
