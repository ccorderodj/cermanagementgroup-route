"""
Webhooks en las dos direcciones.

Entrantes
---------
Una contraparte envía `POST /api/v1/webhooks/inbound/{public_id}` al subdominio
del tenant, firmado con el secreto del endpoint (`signatures.py`). Aquí:

1. se resuelve el endpoint activo, entrante y de este tenant;
2. se verifica la firma y la marca de tiempo;
3. se deduplica por `X-CER-Event-Id` (idempotencia, ámbito `webhooks.inbound`);
4. se llama al manejador registrado para ese tipo de evento, dentro de una
   transacción; sin manejador se acepta y se registra como `unhandled`;
5. se deja `integration_event`.

Un módulo de dominio registra lo que maneja, y es lo único que escribe:

    @register_inbound_handler("staffing.employee.hired")
    async def on_hired(event: InboundEvent) -> None: ...

Salientes
---------
`enqueue_outbound(...)` crea una entrega por cada endpoint saliente activo que
esté suscrito al tipo de evento, en la **misma transacción** que el cambio de
dominio que lo origina: si el cambio se deshace, el evento no sale. Un job del
planificador (`deliver_due`) las envía firmadas y reintenta con espera
exponencial hasta `WEBHOOK_MAX_ATTEMPTS`.
"""

from __future__ import annotations

import json
import secrets as pysecrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy import select

from app.config import settings
from app.core.db.session import db_session, transaction
from app.core.integration import idempotency
from app.core.integration.events import current_request_id, record_integration_event
from app.core.integration.models import (
    DeliveryStatus,
    IntegrationEventStatus,
    WebhookDelivery,
    WebhookDirection,
    WebhookEndpoint,
)
from app.core.integration.signatures import (
    CORRELATION_HEADER,
    EVENT_ID_HEADER,
    EVENT_TYPE_HEADER,
    SIGNATURE_HEADER,
    SOURCE_APP_HEADER,
    SignatureError,
    body_sha256,
    build_header,
    verify,
)
from app.core.platform.secrets import seal, unseal
from app.logger import logger

INBOUND_SCOPE = "webhooks.inbound"
_SECRET_NAME = "signing_secret"


# ── Secretos ────────────────────────────────────────────────────────────────


def _slot(public_id: str) -> str:
    return f"webhook_endpoint:{public_id}"


def new_secret() -> str:
    return "whsec_" + pysecrets.token_urlsafe(32)


def seal_secret(public_id: str, plaintext: str) -> dict[str, Any]:
    sellado = seal(integration_key=_slot(public_id), secret_name=_SECRET_NAME, plaintext=plaintext)
    return {
        "secret_ciphertext": sellado.ciphertext,
        "secret_nonce": sellado.nonce,
        "secret_key_id": sellado.key_id,
        "secret_rotated_at": datetime.now(timezone.utc),
    }


def endpoint_secret(endpoint: WebhookEndpoint) -> str:
    return unseal(
        integration_key=_slot(endpoint.public_id),
        secret_name=_SECRET_NAME,
        ciphertext=endpoint.secret_ciphertext,
        nonce=endpoint.secret_nonce,
        stored_key_id=endpoint.secret_key_id,
    )


def new_public_id() -> str:
    return "we_" + uuid.uuid4().hex


# ── Entrantes ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InboundEvent:
    company_id: int
    endpoint_id: int
    counterpart_app: str
    event_id: str
    event_type: str
    correlation_id: str | None
    payload: Any


InboundHandler = Callable[[InboundEvent], Awaitable[None]]

#: Tipo de evento → manejador. La base no registra ninguno.
INBOUND_HANDLERS: dict[str, InboundHandler] = {}


def register_inbound_handler(event_type: str) -> Callable[[InboundHandler], InboundHandler]:
    def decorador(func: InboundHandler) -> InboundHandler:
        if event_type in INBOUND_HANDLERS:
            raise ValueError(f"An inbound handler for {event_type!r} is already registered.")
        INBOUND_HANDLERS[event_type] = func
        return func

    return decorador


class InboundRejected(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class InboundResult:
    status: str
    event_id: str


async def receive_inbound(
    *, company_id: int, public_id: str, headers: dict[str, str], body: bytes
) -> InboundResult:
    huella = body_sha256(body)
    event_id = (headers.get(EVENT_ID_HEADER.lower()) or "").strip()
    event_type = (headers.get(EVENT_TYPE_HEADER.lower()) or "").strip()
    correlation = headers.get(CORRELATION_HEADER.lower())

    async with db_session() as session:
        endpoint = await session.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.public_id == public_id,
                WebhookEndpoint.company_id == company_id,
                WebhookEndpoint.direction == WebhookDirection.INBOUND.value,
                WebhookEndpoint.is_active.is_(True),
            )
        )

    async def rechazar(status_code: int, detail: str) -> InboundRejected:
        await record_integration_event(
            direction=WebhookDirection.INBOUND.value,
            status=IntegrationEventStatus.REJECTED.value,
            company_id=company_id,
            endpoint_id=getattr(endpoint, "id", None),
            counterpart_app=headers.get(SOURCE_APP_HEADER.lower()),
            event_id=event_id or None,
            event_type=event_type or None,
            correlation_id=correlation,
            payload_sha256=huella,
            detail=detail,
        )
        return InboundRejected(status_code, detail)

    # Endpoint inexistente y firma inválida contestan igual: la contraparte no
    # debe poder enumerar endpoints probando identificadores.
    if endpoint is None:
        raise await rechazar(401, "Invalid webhook signature.")
    try:
        verify(
            endpoint_secret(endpoint),
            headers.get(SIGNATURE_HEADER.lower()),
            body,
            tolerance_seconds=settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
        )
    except SignatureError:
        raise await rechazar(401, "Invalid webhook signature.")

    if not event_id or not event_type:
        raise await rechazar(400, f"{EVENT_ID_HEADER} and {EVENT_TYPE_HEADER} are required.")
    if endpoint.event_types and event_type not in endpoint.event_types:
        raise await rechazar(422, f"This endpoint does not accept {event_type} events.")
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise await rechazar(400, "The body must be JSON.")

    clave = f"{endpoint.id}:{event_id}"
    previa = await idempotency.claim(
        scope=INBOUND_SCOPE, company_id=company_id, key=clave, request_body=body
    )
    if previa.replay:
        await record_integration_event(
            direction=WebhookDirection.INBOUND.value,
            status=IntegrationEventStatus.DUPLICATE.value,
            company_id=company_id,
            endpoint_id=endpoint.id,
            counterpart_app=endpoint.counterpart_app,
            event_id=event_id,
            event_type=event_type,
            correlation_id=correlation,
            payload_sha256=huella,
        )
        return InboundResult(status=IntegrationEventStatus.DUPLICATE.value, event_id=event_id)

    manejador = INBOUND_HANDLERS.get(event_type)
    estado = (
        IntegrationEventStatus.ACCEPTED.value if manejador else IntegrationEventStatus.UNHANDLED.value
    )
    evento = InboundEvent(
        company_id=company_id,
        endpoint_id=endpoint.id,
        counterpart_app=endpoint.counterpart_app,
        event_id=event_id,
        event_type=event_type,
        correlation_id=correlation,
        payload=payload,
    )
    # El manejador, la marca de idempotencia y el metadato se confirman juntos:
    # si el manejador falla, la contraparte reintenta y nada quedó a medias.
    async with transaction():
        if manejador is not None:
            await manejador(evento)
        await idempotency.remember(
            scope=INBOUND_SCOPE,
            company_id=company_id,
            key=clave,
            request_body=body,
            status_code=202,
            body={"status": estado, "event_id": event_id},
        )
        await record_integration_event(
            direction=WebhookDirection.INBOUND.value,
            status=estado,
            company_id=company_id,
            endpoint_id=endpoint.id,
            counterpart_app=endpoint.counterpart_app,
            event_id=event_id,
            event_type=event_type,
            correlation_id=correlation,
            payload_sha256=huella,
        )
    return InboundResult(status=estado, event_id=event_id)


# ── Salientes ───────────────────────────────────────────────────────────────


def _subscribed(endpoint: WebhookEndpoint, event_type: str) -> bool:
    return not endpoint.event_types or event_type in endpoint.event_types


async def enqueue_outbound(
    *,
    company_id: int,
    event_type: str,
    payload: Any,
    correlation_id: str | None = None,
) -> str:
    """Encola el evento para cada endpoint saliente suscrito. Devuelve su `event_id`."""
    event_id = "evt_" + uuid.uuid4().hex
    correlacion = correlation_id or current_request_id()
    cuerpo = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    async with db_session() as session:
        endpoints = (
            await session.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.company_id == company_id,
                    WebhookEndpoint.direction == WebhookDirection.OUTBOUND.value,
                    WebhookEndpoint.is_active.is_(True),
                )
            )
        ).scalars().all()
        destinos = [e for e in endpoints if _subscribed(e, event_type)]
        for endpoint in destinos:
            session.add(
                WebhookDelivery(
                    company_id=company_id,
                    endpoint_id=endpoint.id,
                    event_id=event_id,
                    event_type=event_type,
                    payload=payload,
                    correlation_id=correlacion,
                )
            )
        await session.commit()
    for endpoint in destinos:
        await record_integration_event(
            direction=WebhookDirection.OUTBOUND.value,
            status=IntegrationEventStatus.QUEUED.value,
            company_id=company_id,
            endpoint_id=endpoint.id,
            counterpart_app=endpoint.counterpart_app,
            event_id=event_id,
            event_type=event_type,
            correlation_id=correlacion,
            payload_sha256=body_sha256(cuerpo),
        )
    return event_id


def backoff(attempts: int) -> timedelta:
    """30 s, 1 min, 2 min, 4 min… con techo de 6 horas."""
    return min(timedelta(seconds=30 * (2 ** max(0, attempts - 1))), timedelta(hours=6))


@dataclass
class DeliveryReport:
    delivered: int = 0
    retried: int = 0
    failed: int = 0


async def deliver_due(*, limit: int = 50, client: httpx.AsyncClient | None = None) -> DeliveryReport:
    """Envía las entregas pendientes cuyo turno llegó. Seguro con varias instancias:
    `FOR UPDATE SKIP LOCKED` hace que dos procesos no tomen la misma entrega."""
    informe = DeliveryReport()
    propio = client is None
    http = client or httpx.AsyncClient(timeout=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS)
    try:
        async with transaction() as session:
            ahora = datetime.now(timezone.utc)
            filas = (
                await session.execute(
                    select(WebhookDelivery, WebhookEndpoint)
                    .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
                    .where(
                        WebhookDelivery.status == DeliveryStatus.PENDING.value,
                        WebhookDelivery.next_attempt_at <= ahora,
                    )
                    .order_by(WebhookDelivery.next_attempt_at)
                    .limit(limit)
                    .with_for_update(of=WebhookDelivery, skip_locked=True)
                )
            ).all()
            for entrega, endpoint in filas:
                cuerpo = json.dumps(entrega.payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
                entrega.attempts = (entrega.attempts or 0) + 1
                try:
                    respuesta = await http.post(
                        endpoint.url,
                        content=cuerpo,
                        headers={
                            "Content-Type": "application/json",
                            SIGNATURE_HEADER: build_header(endpoint_secret(endpoint), cuerpo),
                            EVENT_ID_HEADER: entrega.event_id,
                            EVENT_TYPE_HEADER: entrega.event_type,
                            SOURCE_APP_HEADER: settings.APP_NAME,
                            **({CORRELATION_HEADER: entrega.correlation_id} if entrega.correlation_id else {}),
                        },
                    )
                    entrega.last_status_code = respuesta.status_code
                    exito = 200 <= respuesta.status_code < 300
                    entrega.last_error = None if exito else f"HTTP {respuesta.status_code}"
                except httpx.HTTPError as exc:
                    exito = False
                    entrega.last_status_code = None
                    entrega.last_error = f"{type(exc).__name__}: {exc}"[:500]
                except Exception as exc:  # secreto ilegible, URL inválida…
                    exito = False
                    entrega.last_status_code = None
                    entrega.last_error = f"{type(exc).__name__}: {exc}"[:500]
                    logger.warning("WEBHOOK | delivery %s could not be sent", entrega.id, exc_info=True)

                if exito:
                    entrega.status = DeliveryStatus.DELIVERED.value
                    entrega.delivered_at = datetime.now(timezone.utc)
                    informe.delivered += 1
                elif entrega.attempts >= settings.WEBHOOK_MAX_ATTEMPTS:
                    entrega.status = DeliveryStatus.FAILED.value
                    informe.failed += 1
                else:
                    entrega.next_attempt_at = datetime.now(timezone.utc) + backoff(entrega.attempts)
                    informe.retried += 1
            await session.flush()
    finally:
        if propio:
            await http.aclose()
    return informe
