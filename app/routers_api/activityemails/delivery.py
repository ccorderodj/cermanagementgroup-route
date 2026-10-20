"""
El envío **real** de los correos de actividad (RTE-MAIL-CP4-01/02).

Un solo servicio para los tres caminos que pueden mandar un correo:

* **manual** — «Send now» en Activity Emails (CP4-02): recupera un envío que
  tocaba y no salió, o lo manda cuando hace falta ya;
* **schedule** — el programador interno (`PlatformScheduler`, cada minuto);
* **reconcile** — el Scheduled Job de DigitalOcean (cada 15 min, `--once`).

Y uno más, que no pasa por esa clave: **«Resend»**, el reenvío a mano de un
correo que ya salió (o cuyo resultado es incierto). Lo autoriza sólo la
capacidad `route.activityemails.resend`; cada reenvío es una fila numerada de
`activity_email_resend` y un doble clic no manda dos.

Los tres pasan por `reclamar` sobre la **misma clave única**
`(company, recipient, type, operational_date)` de `activity_email_delivery`, así
que dos réplicas, el cron y un clic a la vez no mandan el mismo correo dos
veces. La vista previa (`evaluar`) **no escribe** en el registro.

Lo que se comprueba siempre, en el momento de enviar
----------------------------------------------------
* que el envío real de ese tipo esté habilitado (`MAIL_REAL_SEND_TYPES`, vacío
  por defecto: nada sale hasta el GO del PO);
* que el destinatario siga activo, tenga un correo válido y el interruptor de
  ese correo encendido (todos apagados por defecto);
* que el reporte, calculado de nuevo, sea **final** y tenga contenido (sin
  actividad no hay motivacional);
* que ya haya vencido (`due_at`) — el botón recupera, no adelanta.

Resultados
----------
`accepted_by_provider` (no es «entregado»), `retryable_failure` (credenciales,
proveedor caído; con espera creciente), `permanent_failure` (el proveedor
rechazó el mensaje), `unknown_outcome` (se agotó el tiempo con el mensaje en
vuelo, o una reserva caducó: no se reenvía a ciegas) y `skipped` (no había
correo que mandar, con su motivo).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.core.audit.service import record_event
from app.core.db.session import db_session, transaction
from app.core.email import backends
from app.core.email.politica_de_prueba import correo_valido
from app.logger import logger
from app.routers_api.activityemails.content import ActivityEmailType
from app.routers_api.activityemails.models import (
    ActivityEmailDelivery,
    ActivityEmailPreference,
    ActivityEmailResend,
    DeliverySource,
    DeliveryStatus,
)
from app.routers_api.activityemails.real_reports import DE_MEDIODIA, ReporteReal, generar
from app.routers_api.companies.models import Company, UserCompany
from app.routers_api.users.models import Users
from app.routers_api.worksessions.time_zones import dia_local, zonas_de_referencia

#: Cuánto es de quien la reservó una entrega. Más que el plazo total de una
#: conversación con el proveedor (25 s), con margen.
RESERVA = timedelta(minutes=5)
MAX_INTENTOS = 5
#: Espera antes de cada reintento automático, por intento.
ESPERAS = (timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1))
#: Envíos manuales por persona y hora: un doble clic o un bucle no inundan.
LIMITE_MANUAL = 20

#: El interruptor de preferencia de cada tipo.
PREFERENCIA: dict[str, str] = {
    ActivityEmailType.MIDDAY_MOTIVATION.value: "midday_enabled",
    ActivityEmailType.END_OF_DAY_RECOGNITION.value: "end_of_day_enabled",
    ActivityEmailType.STRATEGIC_MIDDAY_REPORT.value: "strategic_midday_enabled",
    ActivityEmailType.STRATEGIC_END_OF_DAY_REPORT.value: "strategic_end_of_day_enabled",
}

#: Lo que la pantalla dice de cada bloqueo. Fijo: sin datos de nadie.
MOTIVOS: dict[str, str] = {
    "real_send_disabled": "Real sending of this report is not enabled yet (pending product decisions).",
    "recipient_inactive": "The recipient is not active in this company.",
    "recipient_invalid_email": "The recipient has no valid email address.",
    "recipient_not_enabled": "This report is switched off for the recipient in Recipients.",
    "configuration_required": (
        "The recipient has no time zone and the company has no operational time zone. "
        "Set one in Company Profile."
    ),
    "no_activity": "No eligible completed activities for this email.",
    "no_workday": "There is no workday on this date.",
    "no_team": "Nobody currently reports to this manager.",
    "partial_window": "Partial view: the report window has not closed yet.",
    "not_due_yet": "This report is not due yet: the button recovers due reports, it does not send early.",
    "already_sent": "Already accepted by the mail provider. Resending is not available.",
    "in_progress": "This report is being sent right now.",
    "needs_reconciliation": "The outcome of the previous attempt is uncertain and needs reconciliation.",
    "max_attempts": "The maximum number of attempts was reached.",
    "resend_not_sent_yet": "Nothing to resend: this report has not been sent yet.",
    "resend_in_progress": "A resend of this report is being sent right now.",
    "resend_conflict": "This report was resent a moment ago. Generate it again to see the history.",
}

#: Desde qué estados de la entrega original se puede reenviar: ya aceptada por
#: el proveedor, o incierta (quien reenvía ha comprobado que no llegó).
REENVIABLE = frozenset({DeliveryStatus.ACCEPTED_BY_PROVIDER.value, DeliveryStatus.UNKNOWN_OUTCOME.value})


def _habilitado(tipo: str) -> bool:
    return tipo in {t.strip() for t in settings.MAIL_REAL_SEND_TYPES.split(",") if t.strip()}


def _error(codigo: str, http: int = status.HTTP_409_CONFLICT) -> HTTPException:
    return HTTPException(status_code=http, detail={"code": codigo, "message": MOTIVOS[codigo]})


def _fila(f: ActivityEmailDelivery | None) -> dict | None:
    if f is None:
        return None
    return {
        "id": f.id,
        "report_type": f.report_type,
        "recipient_user_id": f.recipient_user_id,
        "operational_date": f.operational_date,
        "status": f.status,
        "source": f.source,
        "attempt_count": f.attempt_count,
        "cutoff_at": f.cutoff_at,
        "due_at": f.due_at,
        "last_attempt_at": f.last_attempt_at,
        "accepted_at": f.accepted_at,
        "reason_code": f.reason_code,
        "requested_by_user_id": f.requested_by_user_id,
        "provider_backend": f.provider_backend,
    }


async def _destinatario(company_id: int, user_id: int) -> dict | None:
    async with db_session() as session:
        fila = (
            await session.execute(
                select(
                    Users.email,
                    Users.is_active.label("platform_active"),
                    UserCompany.is_active.label("membership_active"),
                    ActivityEmailPreference,
                )
                .join(UserCompany, UserCompany.user_id == Users.id)
                .outerjoin(
                    ActivityEmailPreference,
                    (ActivityEmailPreference.user_id == Users.id)
                    & (ActivityEmailPreference.company_id == UserCompany.company_id),
                )
                .where(
                    Users.id == user_id,
                    UserCompany.company_id == company_id,
                    UserCompany.deleted_at.is_(None),
                )
            )
        ).first()
    if fila is None:
        return None
    pref = fila.ActivityEmailPreference
    return {
        "email": fila.email,
        "active": bool(fila.platform_active and fila.membership_active),
        "enabled": {tipo: bool(pref and getattr(pref, campo)) for tipo, campo in PREFERENCIA.items()},
    }


async def es_miembro(*, company_id: int, user_id: int) -> bool:
    """Si la persona pertenece a esta compañía (aunque esté suspendida)."""
    async with db_session() as session:
        return bool(
            await session.scalar(
                select(func.count()).select_from(UserCompany).where(
                    UserCompany.company_id == company_id,
                    UserCompany.user_id == user_id,
                    UserCompany.deleted_at.is_(None),
                )
            )
        )


async def _existente(company_id: int, user_id: int, tipo: str, dia: date) -> ActivityEmailDelivery | None:
    async with db_session() as session:
        return await session.scalar(
            select(ActivityEmailDelivery).where(
                ActivityEmailDelivery.company_id == company_id,
                ActivityEmailDelivery.recipient_user_id == user_id,
                ActivityEmailDelivery.report_type == tipo,
                ActivityEmailDelivery.operational_date == dia,
            )
        )


def _reenvio(r: ActivityEmailResend) -> dict:
    return {
        "id": r.id,
        "sequence": r.sequence,
        "status": r.status,
        "reason_code": r.reason_code,
        "requested_by_user_id": r.requested_by_user_id,
        "provider_backend": r.provider_backend,
        "accepted_at": r.accepted_at,
        "created_at": r.created_at,
    }


async def _reenvios(delivery_id: int) -> list[ActivityEmailResend]:
    async with db_session() as session:
        return list(
            (
                await session.scalars(
                    select(ActivityEmailResend)
                    .where(ActivityEmailResend.delivery_id == delivery_id)
                    .order_by(ActivityEmailResend.sequence)
                )
            ).all()
        )


@dataclass
class Evaluacion:
    reporte: ReporteReal
    can_send: bool
    blocked_reason: str | None
    delivery: dict | None
    destination_masked: str | None = None
    can_resend: bool = False
    resend_blocked_reason: str | None = None
    resends: list[dict] = field(default_factory=list)


def enmascarar(email: str) -> str:
    """`m***a@dominio.com`: quién recibe, sin enseñar la dirección entera."""
    local, _, dominio = email.partition("@")
    visible = local[0] + "***" + (local[-1] if len(local) > 1 else "")
    return f"{visible}@{dominio}"


def _bloqueo(ev_reporte: ReporteReal, dest: dict | None, existente, ahora: datetime) -> str | None:
    tipo = ev_reporte.report_type
    if existente is not None:
        if existente.status == DeliveryStatus.ACCEPTED_BY_PROVIDER.value:
            return "already_sent"
        if existente.status == DeliveryStatus.CLAIMED.value:
            return "in_progress" if existente.lease_expires_at and existente.lease_expires_at > ahora \
                else "needs_reconciliation"
        if existente.status == DeliveryStatus.UNKNOWN_OUTCOME.value:
            return "needs_reconciliation"
        if existente.attempt_count >= MAX_INTENTOS:
            return "max_attempts"
    if not _habilitado(tipo):
        return "real_send_disabled"
    if dest is None or not dest["active"]:
        return "recipient_inactive"
    if not correo_valido(dest["email"]):
        return "recipient_invalid_email"
    if not dest["enabled"][tipo]:
        return "recipient_not_enabled"
    if not ev_reporte.eligible:
        return ev_reporte.reason_code
    if ev_reporte.provisional:
        return ev_reporte.reason_code or "partial_window"
    if ev_reporte.due_at is None or ahora < ev_reporte.due_at:
        return "not_due_yet"
    return None


def _bloqueo_reenvio(
    ev_reporte: ReporteReal, dest: dict | None, existente, reenvios: list[ActivityEmailResend], ahora: datetime
) -> str | None:
    """La decisión de reenviar es del permiso; esto es sólo lo que hace falta
    para que el reenvío pueda salir de verdad y no se pise con otro."""
    if existente is None or existente.status not in REENVIABLE:
        return "resend_not_sent_yet"
    ultimo = reenvios[-1] if reenvios else None
    if ultimo is not None and ultimo.status == DeliveryStatus.CLAIMED.value and ultimo.created_at > ahora - RESERVA:
        return "resend_in_progress"
    # El interruptor de emergencia por tipo manda también aquí.
    if not _habilitado(ev_reporte.report_type):
        return "real_send_disabled"
    if dest is None or not dest["active"]:
        return "recipient_inactive"
    if not correo_valido(dest["email"]):
        return "recipient_invalid_email"
    if not ev_reporte.eligible:
        return ev_reporte.reason_code
    return None


async def evaluar(
    *, company_id: int, report_type: str, recipient_user_id: int, operational_date: date,
    ahora: datetime,
) -> Evaluacion:
    """El reporte con datos reales y si se puede enviar ahora. **No escribe.**"""
    reporte = await generar(
        company_id=company_id, report_type=report_type, recipient_user_id=recipient_user_id,
        operational_date=operational_date, ahora=ahora,
    )
    dest = await _destinatario(company_id, recipient_user_id)
    existente = await _existente(company_id, recipient_user_id, reporte.report_type, operational_date)
    motivo = _bloqueo(reporte, dest, existente, ahora)
    reenvios = await _reenvios(existente.id) if existente is not None else []
    motivo_reenvio = _bloqueo_reenvio(reporte, dest, existente, reenvios, ahora)
    return Evaluacion(
        reporte=reporte,
        can_send=motivo is None,
        blocked_reason=motivo,
        delivery=_fila(existente),
        destination_masked=enmascarar(dest["email"]) if dest and correo_valido(dest["email"]) else None,
        can_resend=motivo_reenvio is None,
        resend_blocked_reason=motivo_reenvio,
        resends=[_reenvio(r) for r in reenvios],
    )


# ── Reserva, entrega y omisión ─────────────────────────────────────────────


async def reclamar(
    *, company_id: int, reporte: ReporteReal, source: str, ahora: datetime,
    actor_user_id: int | None = None, reason: str | None = None,
) -> int:
    """Reserva la entrega o responde 409. Atómico sobre la clave única."""
    clave = dict(
        company_id=company_id, recipient_user_id=reporte.recipient_user_id,
        report_type=reporte.report_type, operational_date=reporte.operational_date,
    )
    async with transaction() as session:
        await session.execute(
            pg_insert(ActivityEmailDelivery)
            .values(**clave, status=DeliveryStatus.PENDING.value, source=source, version=1)
            .on_conflict_do_nothing(constraint="uq_activity_email_delivery_key")
        )
        fila = await session.scalar(
            select(ActivityEmailDelivery).filter_by(**clave).with_for_update()
        )
        if fila.status == DeliveryStatus.ACCEPTED_BY_PROVIDER.value:
            raise _error("already_sent")
        if fila.status == DeliveryStatus.CLAIMED.value:
            if fila.lease_expires_at and fila.lease_expires_at > ahora:
                raise _error("in_progress")
            # Una reserva caducada: quien la tenía pudo mandar o no. Incierto.
            fila.status = DeliveryStatus.UNKNOWN_OUTCOME.value
            fila.reason_code = "lease_expired"
            await session.flush()
            raise _error("needs_reconciliation")
        if fila.status == DeliveryStatus.UNKNOWN_OUTCOME.value:
            raise _error("needs_reconciliation")
        if fila.attempt_count >= MAX_INTENTOS:
            raise _error("max_attempts")
        fila.status = DeliveryStatus.CLAIMED.value
        fila.source = source
        fila.lease_expires_at = ahora + RESERVA
        fila.attempt_count += 1
        fila.last_attempt_at = ahora
        fila.next_attempt_at = None
        fila.cutoff_at = reporte.cutoff_at
        fila.due_at = reporte.due_at
        fila.template_version = reporte.template_version
        fila.requested_by_user_id = actor_user_id
        fila.request_reason = (reason or None) and reason[:300]
        fila.reason_code = None
        fila.version += 1
        await session.flush()
        return fila.id


def _clasificar(exc: backends.EmailFailure) -> str:
    if exc.step == "smtp_send_rejected":
        return DeliveryStatus.PERMANENT_FAILURE.value
    if exc.step == "smtp_timeout":
        # El mensaje pudo quedar transmitido: no se reenvía a ciegas.
        return DeliveryStatus.UNKNOWN_OUTCOME.value
    return DeliveryStatus.RETRYABLE_FAILURE.value


async def _mandar(reporte: ReporteReal, email: str) -> tuple[str, str | None, str | None]:
    """(estado, código, backend) de una conversación con el proveedor."""
    try:
        backend = await asyncio.to_thread(
            backends.send_email,
            to=email,
            subject=reporte.subject,
            body=reporte.body,
            headers={"X-CER-Route-Report": reporte.report_type},
        )
    except backends.EmailFailure as exc:
        return _clasificar(exc), exc.step, None
    if backend == "console":
        # El backend de desarrollo no saca nada del servidor: no es un envío.
        return DeliveryStatus.RETRYABLE_FAILURE.value, "provider_not_configured", backend
    return DeliveryStatus.ACCEPTED_BY_PROVIDER.value, None, backend


async def entregar(
    *, company_id: int, delivery_id: int, reporte: ReporteReal, email: str, ahora: datetime,
    actor_user_id: int | None,
) -> dict:
    """Manda el correo reservado y deja el resultado. Sin cuerpo en la traza."""
    estado, codigo, backend = await _mandar(reporte, email)

    async with transaction() as session:
        fila = await session.scalar(
            select(ActivityEmailDelivery).where(ActivityEmailDelivery.id == delivery_id).with_for_update()
        )
        fila.status = estado
        fila.reason_code = codigo
        fila.provider_backend = backend
        fila.lease_expires_at = None
        if estado == DeliveryStatus.ACCEPTED_BY_PROVIDER.value:
            fila.accepted_at = ahora
        if estado == DeliveryStatus.RETRYABLE_FAILURE.value:
            espera = ESPERAS[min(fila.attempt_count, len(ESPERAS)) - 1]
            fila.next_attempt_at = ahora + espera
        fila.version += 1
        await session.flush()
        resultado = _fila(fila)

    await record_event(
        company_id=company_id,
        entity_type="activity_email_delivery",
        entity_id=delivery_id,
        action=estado,
        actor_user_id=actor_user_id,
        summary=f"{reporte.report_type} for user {reporte.recipient_user_id} on {reporte.operational_date}: {estado}",
        changes={
            "report_type": {"old": None, "new": reporte.report_type},
            "recipient_user_id": {"old": None, "new": reporte.recipient_user_id},
            "operational_date": {"old": None, "new": reporte.operational_date.isoformat()},
            "status": {"old": DeliveryStatus.CLAIMED.value, "new": estado},
            "reason_code": {"old": None, "new": codigo},
            "source": {"old": None, "new": resultado["source"]},
        },
    )
    return resultado


async def omitir(*, company_id: int, reporte: ReporteReal, motivo: str, source: str) -> None:
    """Deja constancia de que tocaba y no había correo que mandar."""
    clave = dict(
        company_id=company_id, recipient_user_id=reporte.recipient_user_id,
        report_type=reporte.report_type, operational_date=reporte.operational_date,
    )
    async with transaction() as session:
        await session.execute(
            pg_insert(ActivityEmailDelivery)
            .values(**clave, status=DeliveryStatus.SKIPPED.value, source=source, reason_code=motivo,
                    cutoff_at=reporte.cutoff_at, due_at=reporte.due_at, version=1)
            .on_conflict_do_nothing(constraint="uq_activity_email_delivery_key")
        )


# ── El botón «Send now» (CP4-02) ───────────────────────────────────────────


async def _enviados_por(actor_user_id: int, ahora: datetime) -> int:
    """Envíos y reenvíos a mano de esta persona en la última hora."""
    desde = ahora - timedelta(hours=1)
    async with db_session() as session:
        envios = await session.scalar(
            select(func.count()).select_from(ActivityEmailDelivery).where(
                ActivityEmailDelivery.requested_by_user_id == actor_user_id,
                ActivityEmailDelivery.source == DeliverySource.MANUAL.value,
                ActivityEmailDelivery.last_attempt_at >= desde,
            )
        )
        reenvios = await session.scalar(
            select(func.count()).select_from(ActivityEmailResend).where(
                ActivityEmailResend.requested_by_user_id == actor_user_id,
                ActivityEmailResend.created_at >= desde,
            )
        )
    return int(envios or 0) + int(reenvios or 0)


def _limite_manual() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": "rate_limited", "message": f"Up to {LIMITE_MANUAL} manual sends per hour."},
    )


async def enviar_ahora(
    *, company_id: int, actor_user_id: int, report_type: str, recipient_user_id: int,
    operational_date: date, reason: str | None, ahora: datetime,
) -> dict:
    ev = await evaluar(
        company_id=company_id, report_type=report_type, recipient_user_id=recipient_user_id,
        operational_date=operational_date, ahora=ahora,
    )
    if not ev.can_send:
        raise _error(ev.blocked_reason)
    if await _enviados_por(actor_user_id, ahora) >= LIMITE_MANUAL:
        raise _limite_manual()
    delivery_id = await reclamar(
        company_id=company_id, reporte=ev.reporte, source=DeliverySource.MANUAL.value, ahora=ahora,
        actor_user_id=actor_user_id, reason=reason,
    )
    dest = await _destinatario(company_id, recipient_user_id)
    resultado = await entregar(
        company_id=company_id, delivery_id=delivery_id, reporte=ev.reporte, email=dest["email"],
        ahora=ahora, actor_user_id=actor_user_id,
    )
    return {**resultado, "destination_masked": ev.destination_masked}


async def reenviar(
    *, company_id: int, actor_user_id: int, report_type: str, recipient_user_id: int,
    operational_date: date, expected_resends: int, reason: str | None, ahora: datetime,
) -> dict:
    """Vuelve a mandar un correo que ya salió, con los datos de ahora.

    `expected_resends` es cuántos reenvíos vio quien pulsa: sólo uno puede
    ocupar el número siguiente, así que un doble clic responde 409.
    """
    ev = await evaluar(
        company_id=company_id, report_type=report_type, recipient_user_id=recipient_user_id,
        operational_date=operational_date, ahora=ahora,
    )
    if not ev.can_resend:
        raise _error(ev.resend_blocked_reason)
    if expected_resends != len(ev.resends):
        raise _error("resend_conflict")
    if await _enviados_por(actor_user_id, ahora) >= LIMITE_MANUAL:
        raise _limite_manual()

    delivery_id = ev.delivery["id"]
    try:
        async with transaction() as session:
            fila = ActivityEmailResend(
                company_id=company_id,
                delivery_id=delivery_id,
                sequence=expected_resends + 1,
                status=DeliveryStatus.CLAIMED.value,
                requested_by_user_id=actor_user_id,
                request_reason=(reason or None) and reason[:300],
            )
            session.add(fila)
            await session.flush()
            reenvio_id = fila.id
    except IntegrityError:
        raise _error("resend_conflict") from None

    dest = await _destinatario(company_id, recipient_user_id)
    estado, codigo, backend = await _mandar(ev.reporte, dest["email"])

    async with transaction() as session:
        fila = await session.get(ActivityEmailResend, reenvio_id, with_for_update=True)
        fila.status = estado
        fila.reason_code = codigo
        fila.provider_backend = backend
        if estado == DeliveryStatus.ACCEPTED_BY_PROVIDER.value:
            fila.accepted_at = ahora
        await session.flush()
        resultado = _reenvio(fila)

    await record_event(
        company_id=company_id,
        entity_type="activity_email_resend",
        entity_id=reenvio_id,
        action=estado,
        actor_user_id=actor_user_id,
        summary=(
            f"resend #{resultado['sequence']} of {report_type} for user {recipient_user_id} "
            f"on {operational_date}: {estado}"
        ),
        changes={
            "delivery_id": {"old": None, "new": delivery_id},
            "sequence": {"old": None, "new": resultado["sequence"]},
            "status": {"old": DeliveryStatus.CLAIMED.value, "new": estado},
            "reason_code": {"old": None, "new": codigo},
        },
    )
    return {**resultado, "destination_masked": ev.destination_masked}


async def historial(
    *, company_id: int, recipient_ids: set[int] | None, report_type: str | None,
    recipient_user_id: int | None, operational_date: date | None, limite: int = 50,
) -> list[dict]:
    """Los envíos de la compañía, acotados a quien mira. Sin contenido."""
    stmt = select(ActivityEmailDelivery).where(ActivityEmailDelivery.company_id == company_id)
    if recipient_ids is not None:
        stmt = stmt.where(ActivityEmailDelivery.recipient_user_id.in_(recipient_ids or {-1}))
    if report_type:
        stmt = stmt.where(ActivityEmailDelivery.report_type == report_type)
    if recipient_user_id is not None:
        stmt = stmt.where(ActivityEmailDelivery.recipient_user_id == recipient_user_id)
    if operational_date is not None:
        stmt = stmt.where(ActivityEmailDelivery.operational_date == operational_date)
    async with db_session() as session:
        filas = (
            await session.scalars(stmt.order_by(ActivityEmailDelivery.updated_at.desc()).limit(limite))
        ).all()
    return [_fila(f) for f in filas]


# ── El barrido (CP4-01): programador interno y cron de DigitalOcean ─────────


@dataclass
class Resumen:
    source: str
    enabled: bool
    dry_run: bool
    checked: int = 0
    due: int = 0
    claimed: int = 0
    accepted: int = 0
    retry: int = 0
    failed: int = 0
    unknown: int = 0
    skipped: int = 0
    not_enabled: int = 0
    would_send: int = 0
    errors: int = 0
    detalle: list[str] = field(default_factory=list)

    def linea(self) -> str:
        return (
            f"MAIL DISPATCH | source={self.source} enabled={self.enabled} dry_run={self.dry_run} "
            f"checked={self.checked} due={self.due} claimed={self.claimed} accepted={self.accepted} "
            f"retry={self.retry} failed={self.failed} unknown={self.unknown} skipped={self.skipped} "
            f"not_enabled={self.not_enabled} would_send={self.would_send} errors={self.errors}"
        )


async def _caducar_reservas(ahora: datetime) -> int:
    """Una reserva que nadie cerró (proceso caído): resultado incierto."""
    async with transaction() as session:
        r = await session.execute(
            update(ActivityEmailDelivery)
            .where(
                ActivityEmailDelivery.status == DeliveryStatus.CLAIMED.value,
                ActivityEmailDelivery.lease_expires_at < ahora,
            )
            .values(status=DeliveryStatus.UNKNOWN_OUTCOME.value, reason_code="lease_expired")
        )
        return r.rowcount or 0


async def _candidatos(company_id: int) -> list[tuple[int, str]]:
    """(persona, tipo) con el interruptor de ese correo encendido."""
    async with db_session() as session:
        prefs = (
            await session.scalars(
                select(ActivityEmailPreference).where(ActivityEmailPreference.company_id == company_id)
            )
        ).all()
    return [(p.user_id, tipo) for p in prefs for tipo, campo in PREFERENCIA.items() if getattr(p, campo)]


async def despachar_vencidos(*, ahora: datetime | None = None, source: str = DeliverySource.SCHEDULE.value) -> Resumen:
    """Manda lo que ya venció y no salió. Idempotente: se puede llamar siempre."""
    ahora = ahora or datetime.now(timezone.utc)
    resumen = Resumen(source=source, enabled=settings.MAIL_AUTOMATION_ENABLED, dry_run=settings.MAIL_AUTOMATION_DRY_RUN)
    if not settings.MAIL_AUTOMATION_ENABLED:
        return resumen
    if not resumen.dry_run:
        await _caducar_reservas(ahora)
    ventana = timedelta(hours=settings.MAIL_RECOVERY_WINDOW_HOURS)

    async with db_session() as session:
        companias = (await session.scalars(select(Company.id).where(Company.is_active.is_(True)))).all()

    for company_id in companias:
        candidatos = await _candidatos(company_id)
        zonas = await zonas_de_referencia(company_id=company_id, user_ids=sorted({u for u, _ in candidatos}))
        for user_id, tipo in candidatos:
            zona = zonas.get(user_id, (None, None))[0]
            hoy = dia_local(ahora, zona) if zona else ahora.date()
            # El fin de jornada de ayer puede vencer hoy (jornadas que cruzan
            # la medianoche); el mediodía, sólo el de hoy.
            dias = [hoy] if tipo in DE_MEDIODIA else [hoy, hoy - timedelta(days=1)]
            for dia in dias:
                resumen.checked += 1
                try:
                    await _uno(company_id, user_id, tipo, dia, ahora, ventana, source, resumen)
                except HTTPException:
                    # Otro camino lo reservó entre la evaluación y la reserva.
                    continue
                except Exception:
                    resumen.errors += 1
                    logger.warning("MAIL DISPATCH | error company=%s type=%s", company_id, tipo, exc_info=True)
    logger.info(resumen.linea())
    return resumen


async def _uno(company_id, user_id, tipo, dia, ahora, ventana, source, resumen: Resumen) -> None:
    existente = await _existente(company_id, user_id, tipo, dia)
    if existente is not None and existente.status != DeliveryStatus.RETRYABLE_FAILURE.value \
            and existente.status != DeliveryStatus.PENDING.value:
        return
    if existente is not None and existente.next_attempt_at and existente.next_attempt_at > ahora:
        return
    ev = await evaluar(
        company_id=company_id, report_type=tipo, recipient_user_id=user_id, operational_date=dia,
        ahora=ahora,
    )
    r = ev.reporte
    if r.due_at is None or r.provisional or ahora < r.due_at:
        return
    if r.due_at < ahora - ventana:
        return  # DP-RECOVERY: demasiado viejo para mandarlo ahora.
    resumen.due += 1
    if not _habilitado(tipo):
        resumen.not_enabled += 1
        return
    if resumen.dry_run:
        resumen.would_send += int(ev.can_send)
        resumen.detalle.append(f"{tipo} user={user_id} date={dia} would={'send' if ev.can_send else ev.blocked_reason}")
        return
    if not ev.can_send:
        await omitir(company_id=company_id, reporte=r, motivo=ev.blocked_reason, source=source)
        resumen.skipped += 1
        return
    delivery_id = await reclamar(company_id=company_id, reporte=r, source=source, ahora=ahora)
    resumen.claimed += 1
    dest = await _destinatario(company_id, user_id)
    fila = await entregar(
        company_id=company_id, delivery_id=delivery_id, reporte=r, email=dest["email"], ahora=ahora,
        actor_user_id=None,
    )
    resumen.accepted += fila["status"] == DeliveryStatus.ACCEPTED_BY_PROVIDER.value
    resumen.retry += fila["status"] == DeliveryStatus.RETRYABLE_FAILURE.value
    resumen.failed += fila["status"] == DeliveryStatus.PERMANENT_FAILURE.value
    resumen.unknown += fila["status"] == DeliveryStatus.UNKNOWN_OUTCOME.value
