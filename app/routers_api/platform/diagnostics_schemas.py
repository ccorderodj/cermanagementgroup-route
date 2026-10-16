"""Contratos de Diagnostics y de la preparación para producción."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.routers_api.platform.settings_schemas import IntegrationRead


class CheckRead(BaseModel):
    key: str
    title: str
    kind: str
    summary: str
    status: str
    detail: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None


class CheckRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    capability_key: str
    status: str
    detail: str | None = None
    checked_at: datetime
    duration_ms: int | None = None
    trigger: str
    actor_user_id: int | None = None


class GateRead(BaseModel):
    key: str
    title: str
    status: str
    blocks_production: bool
    detail: str
    action: str
    open_decision: str | None = None


class ReadinessRead(BaseModel):
    production_ready: bool
    mode: str
    counts: dict[str, int]
    gates: list[GateRead]


class PostureItemRead(BaseModel):
    key: str
    title: str
    value: str
    ok: bool
    detail: str


class VerifyRead(BaseModel):
    integration: IntegrationRead
    check: CheckRunRead


class TestMessageWrite(BaseModel):
    to: EmailStr
