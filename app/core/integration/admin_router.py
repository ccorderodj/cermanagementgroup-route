"""
Administración de webhooks del tenant: `/api/integrations/...`.

API interna (sesión + capacidad), no parte del contrato versionado. El secreto
de firma se devuelve **una sola vez**: al crear el endpoint y al rotarlo.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.audit import record_event
from app.core.dao.concurrency import ensure_version
from app.core.db.session import db_session, transaction
from app.core.integration.models import (
    IntegrationEvent,
    WebhookDelivery,
    WebhookDirection,
    WebhookEndpoint,
)
from app.core.integration.webhooks import new_public_id, new_secret, seal_secret
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions

router = APIRouter(prefix="/integrations", tags=["Integrations"])

EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")


def _normalize_event_types(valor: list[str]) -> list[str]:
    for tipo in valor:
        if not EVENT_TYPE_PATTERN.match(tipo):
            raise ValueError(
                f"invalid event type {tipo!r}: use dotted lowercase names like app.entity.action"
            )
    return sorted(set(valor))


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    name: str
    direction: str
    counterpart_app: str
    url: Optional[str] = None
    event_types: list[str]
    is_active: bool
    version: int
    inbound_path: Optional[str] = None


class EndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    direction: Literal["inbound", "outbound"]
    counterpart_app: str = Field(min_length=1, max_length=80)
    url: Optional[HttpUrl] = None
    event_types: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("event_types")
    @classmethod
    def _tipos(cls, valor: list[str]) -> list[str]:
        return _normalize_event_types(valor)


class EndpointUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    url: Optional[HttpUrl] = None
    event_types: list[str] = Field(default_factory=list, max_length=100)
    is_active: bool
    version: int

    @field_validator("event_types")
    @classmethod
    def _tipos(cls, valor: list[str]) -> list[str]:
        return _normalize_event_types(valor)


class EndpointWithSecret(EndpointRead):
    signing_secret: str


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    event_type: str
    status: str
    attempts: int
    last_status_code: Optional[int] = None
    last_error: Optional[str] = None
    correlation_id: Optional[str] = None
    delivered_at: Optional[object] = None
    next_attempt_at: object


class IntegrationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: str
    status: str
    counterpart_app: Optional[str] = None
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    correlation_id: Optional[str] = None
    request_id: Optional[str] = None
    detail: Optional[str] = None
    occurred_at: object


def _read(endpoint: WebhookEndpoint) -> dict:
    datos = EndpointRead.model_validate(endpoint).model_dump()
    if endpoint.direction == WebhookDirection.INBOUND.value:
        datos["inbound_path"] = f"/api/v1/webhooks/inbound/{endpoint.public_id}"
    return datos


def _validar_url(direction: str, url) -> str | None:
    if direction == WebhookDirection.OUTBOUND.value and url is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "An outbound endpoint needs a url.")
    if direction == WebhookDirection.INBOUND.value and url is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "An inbound endpoint has no url.")
    return str(url) if url is not None else None


async def _endpoint_or_404(session, *, company_id: int, endpoint_id: int, lock: bool = False) -> WebhookEndpoint:
    consulta = select(WebhookEndpoint).where(
        WebhookEndpoint.id == endpoint_id, WebhookEndpoint.company_id == company_id
    )
    if lock:
        consulta = consulta.with_for_update()
    endpoint = await session.scalar(consulta)
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook endpoint not found.")
    return endpoint


@router.get("/webhook-endpoints")
async def list_endpoints(
    current_company: TenantContext = Depends(get_company_required),
    _authz: None = Depends(require_permissions(["integrations.read"])),
) -> list[EndpointRead]:
    async with db_session() as session:
        filas = (
            await session.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.company_id == current_company.id)
                .order_by(WebhookEndpoint.name)
            )
        ).scalars().all()
    return [EndpointRead(**_read(f)) for f in filas]


@router.post("/webhook-endpoints", status_code=201)
async def create_endpoint(
    payload: EndpointCreate,
    current_company: TenantContext = Depends(get_company_required),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["integrations.manage"])),
) -> EndpointWithSecret:
    url = _validar_url(payload.direction, payload.url)
    public_id = new_public_id()
    secreto = new_secret()
    try:
        async with transaction() as session:
            endpoint = WebhookEndpoint(
                company_id=current_company.id,
                public_id=public_id,
                name=payload.name.strip(),
                direction=payload.direction,
                counterpart_app=payload.counterpart_app.strip(),
                url=url,
                event_types=payload.event_types,
                is_active=True,
                version=1,
                **seal_secret(public_id, secreto),
            )
            session.add(endpoint)
            await session.flush()
            await record_event(
                company_id=current_company.id,
                entity_type="webhook_endpoint",
                entity_id=endpoint.id,
                action="create",
                actor_user_id=current_user.id,
                summary=f"Webhook endpoint {endpoint.name} ({endpoint.direction}) created",
                changes={"direction": {"old": None, "new": endpoint.direction},
                         "counterpart_app": {"old": None, "new": endpoint.counterpart_app}},
            )
            datos = _read(endpoint)
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "A webhook endpoint with that name already exists.") from exc
    return EndpointWithSecret(**datos, signing_secret=secreto)


@router.put("/webhook-endpoints/{endpoint_id}")
async def update_endpoint(
    payload: EndpointUpdate,
    endpoint_id: int = Path(..., ge=1),
    current_company: TenantContext = Depends(get_company_required),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["integrations.manage"])),
) -> EndpointRead:
    async with transaction() as session:
        endpoint = await _endpoint_or_404(
            session, company_id=current_company.id, endpoint_id=endpoint_id, lock=True
        )
        ensure_version(current=endpoint.version, expected=payload.version)
        url = _validar_url(endpoint.direction, payload.url)
        antes = {"name": endpoint.name, "url": endpoint.url, "event_types": endpoint.event_types,
                 "is_active": endpoint.is_active}
        endpoint.name = payload.name.strip()
        endpoint.url = url
        endpoint.event_types = payload.event_types
        endpoint.is_active = payload.is_active
        endpoint.version = endpoint.version + 1
        await session.flush()
        despues = {"name": endpoint.name, "url": endpoint.url, "event_types": endpoint.event_types,
                   "is_active": endpoint.is_active}
        await record_event(
            company_id=current_company.id,
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
            action="update",
            actor_user_id=current_user.id,
            summary=f"Webhook endpoint {endpoint.name} updated",
            changes={k: {"old": antes[k], "new": despues[k]} for k in antes if antes[k] != despues[k]},
        )
        datos = _read(endpoint)
    return EndpointRead(**datos)


@router.post("/webhook-endpoints/{endpoint_id}/rotate-secret")
async def rotate_secret(
    endpoint_id: int = Path(..., ge=1),
    current_company: TenantContext = Depends(get_company_required),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["integrations.manage"])),
) -> EndpointWithSecret:
    secreto = new_secret()
    async with transaction() as session:
        endpoint = await _endpoint_or_404(
            session, company_id=current_company.id, endpoint_id=endpoint_id, lock=True
        )
        for campo, valor in seal_secret(endpoint.public_id, secreto).items():
            setattr(endpoint, campo, valor)
        endpoint.version = endpoint.version + 1
        await session.flush()
        await record_event(
            company_id=current_company.id,
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
            action="rotate_secret",
            actor_user_id=current_user.id,
            summary=f"Signing secret of webhook endpoint {endpoint.name} rotated",
        )
        datos = _read(endpoint)
    return EndpointWithSecret(**datos, signing_secret=secreto)


@router.get("/webhook-endpoints/{endpoint_id}/deliveries")
async def list_deliveries(
    endpoint_id: int = Path(..., ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_company: TenantContext = Depends(get_company_required),
    _authz: None = Depends(require_permissions(["integrations.read"])),
) -> list[DeliveryRead]:
    async with db_session() as session:
        await _endpoint_or_404(session, company_id=current_company.id, endpoint_id=endpoint_id)
        filas = (
            await session.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.endpoint_id == endpoint_id,
                       WebhookDelivery.company_id == current_company.id)
                .order_by(WebhookDelivery.id.desc())
                .limit(limit)
            )
        ).scalars().all()
    return [DeliveryRead.model_validate(f) for f in filas]


@router.get("/events")
async def list_integration_events(
    limit: int = Query(50, ge=1, le=200),
    correlation_id: Optional[str] = Query(None, max_length=64),
    current_company: TenantContext = Depends(get_company_required),
    _authz: None = Depends(require_permissions(["integrations.read"])),
) -> list[IntegrationEventRead]:
    consulta = select(IntegrationEvent).where(IntegrationEvent.company_id == current_company.id)
    if correlation_id:
        consulta = consulta.where(IntegrationEvent.correlation_id == correlation_id)
    async with db_session() as session:
        filas = (
            await session.execute(consulta.order_by(IntegrationEvent.id.desc()).limit(limit))
        ).scalars().all()
    return [IntegrationEventRead.model_validate(f) for f in filas]
