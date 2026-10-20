"""
Correos de actividad (RTE-NOT-01): plantillas y destinatarios.

**Sólo configuración.** Ningún endpoint de aquí programa un envío ni escribe a
una persona real: guardar, activar o previsualizar sólo deja datos guardados. El
envío es RTE-NOT-02/03 (BR-10, BR-12). La única excepción es la **prueba
controlada** (RTE-MAIL-TEST-01): una plantilla con datos ficticios a un
destinatario de prueba autorizado (ver `envio_de_prueba`).

La configuración exige `route.activityemails.manage`; los reportes con datos
reales, `route.activityemails.preview` (ver) y `route.activityemails.send`
(enviar ahora, RTE-MAIL-CP4-02). Todo con la compañía del subdominio y el
alcance de la jerarquía: un manager con la capacidad sólo ve y cambia a su rama,
igual que en la administración de usuarios.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.activityemails.schemas import (
    ActivityEmailPreview,
    ActivityEmailPreviewRequest,
    ActivityEmailRecipientRead,
    ActivityEmailRecipientUpdate,
    ActivityEmailTemplateRead,
    ActivityEmailTemplateRestore,
    ActivityEmailTemplateUpdate,
    ActivityEmailTestResult,
    ActivityEmailTestSend,
    ActivityEmailTestTargets,
    DeliveryHistoryRead,
    DeliveryRead,
    HistoryParams,
    OperationalStatusRead,
    ReportPreviewRead,
    ReportRequest,
    ReportResendRequest,
    ReportSendRequest,
    ReportSendResult,
    ResendRead,
    ResendResult,
    RecipientsPaginationParams,
    StrategicRecipientRead,
    StrategicRecipientUpdate,
)
from app.routers_api.activityemails import delivery, envio_de_prueba
from app.routers_api.activityemails.content import ActivityEmailType
from app.routers_api.activityemails.service import ActivityEmailService
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.organization import delegation as delegada
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions

router = APIRouter(prefix="/activity-emails", tags=["Route · Activity emails"])

_GESTIONAR = require_permissions(["route.activityemails.manage"])


@router.get("/templates")
async def list_templates(
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> list[ActivityEmailTemplateRead]:
    return [
        ActivityEmailTemplateRead.model_validate(v)
        for v in await ActivityEmailService.list_templates(company_id=company.id)
    ]


@router.put("/templates/{template_type}")
async def update_template(
    template_type: str,
    payload: ActivityEmailTemplateUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> ActivityEmailTemplateRead:
    """Guarda **una** plantilla. 409 si alguien la cambió desde que se leyó."""
    vista = await ActivityEmailService.update_template(
        company_id=company.id,
        template_type=template_type,
        subject=payload.subject,
        body=payload.body,
        version=payload.version,
        actor_user_id=current_user.id,
    )
    return ActivityEmailTemplateRead.model_validate(vista)


@router.post("/templates/{template_type}/restore-default")
async def restore_template(
    template_type: str,
    payload: ActivityEmailTemplateRestore,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> ActivityEmailTemplateRead:
    """Vuelve al texto aprobado sólo esta plantilla; destinatarios intactos."""
    vista = await ActivityEmailService.restore_default(
        company_id=company.id,
        template_type=template_type,
        version=payload.version,
        actor_user_id=current_user.id,
    )
    return ActivityEmailTemplateRead.model_validate(vista)


@router.post("/templates/{template_type}/preview")
async def preview_template(
    template_type: str,
    payload: ActivityEmailPreviewRequest,
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> ActivityEmailPreview:
    """El borrador con datos **ficticios**. No guarda ni envía nada."""
    return ActivityEmailPreview.model_validate(
        ActivityEmailService.preview(
            template_type=template_type, subject=payload.subject, body=payload.body
        )
    )


@router.get("/recipients")
async def list_recipients(
    request: Request,
    params: RecipientsPaginationParams = Depends(),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[ActivityEmailRecipientRead]:
    filas, total = await ActivityEmailService.list_recipients(
        company_id=company.id,
        actor_user_id=current_user.id,
        q=params.q,
        include_self=params.include_self,
        page=params.page,
        page_size=params.page_size,
    )
    paginator = Paginator(
        total_items=total,
        page=params.page,
        page_size=params.page_size,
        results=[ActivityEmailRecipientRead.model_validate(f) for f in filas],
        request=request,
    )
    return schema.PaginatedResponse[ActivityEmailRecipientRead](**paginator.to_response())


@router.put("/recipients/{user_id}")
async def update_recipient(
    user_id: int,
    payload: ActivityEmailRecipientUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> ActivityEmailRecipientRead:
    """Uno o los dos interruptores de **una** persona; el otro no cambia."""
    fila = await ActivityEmailService.update_recipient(
        company_id=company.id,
        actor_user_id=current_user.id,
        user_id=user_id,
        midday_enabled=payload.midday_enabled,
        end_of_day_enabled=payload.end_of_day_enabled,
        version=payload.version,
    )
    return ActivityEmailRecipientRead.model_validate(fila)


@router.get("/strategic-recipients")
async def list_strategic_recipients(
    request: Request,
    params: RecipientsPaginationParams = Depends(),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[StrategicRecipientRead]:
    """Los mandos (CEO, COO, RM) que quien llama puede gestionar, con su
    cobertura real y sus dos interruptores estratégicos."""
    filas, total = await ActivityEmailService.list_strategic_recipients(
        company_id=company.id,
        actor_user_id=current_user.id,
        q=params.q,
        include_self=params.include_self,
        page=params.page,
        page_size=params.page_size,
    )
    paginator = Paginator(
        total_items=total,
        page=params.page,
        page_size=params.page_size,
        results=[StrategicRecipientRead.model_validate(f) for f in filas],
        request=request,
    )
    return schema.PaginatedResponse[StrategicRecipientRead](**paginator.to_response())


@router.put("/strategic-recipients/{user_id}")
async def update_strategic_recipient(
    user_id: int,
    payload: StrategicRecipientUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> StrategicRecipientRead:
    """Uno o los dos interruptores estratégicos de **un** mando. No da al mando
    ningún permiso nuevo ni cambia sus correos motivacionales."""
    fila = await ActivityEmailService.update_strategic_recipient(
        company_id=company.id,
        actor_user_id=current_user.id,
        user_id=user_id,
        strategic_midday_enabled=payload.strategic_midday_enabled,
        strategic_end_of_day_enabled=payload.strategic_end_of_day_enabled,
        version=payload.version,
    )
    return StrategicRecipientRead.model_validate(fila)


@router.get("/test-targets")
async def test_targets(
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> ActivityEmailTestTargets:
    """A qué direcciones puede mandar una prueba quien llama."""
    return ActivityEmailTestTargets(
        recipients=await envio_de_prueba.destinatarios_de_prueba(actor_user_id=current_user.id),
        provider_configured=envio_de_prueba.proveedor_configurado(),
        limit=envio_de_prueba.LIMITE,
        window_minutes=int(envio_de_prueba.VENTANA.total_seconds() // 60),
    )


@router.post("/templates/{template_type}/test-send")
async def test_send(
    template_type: str,
    payload: ActivityEmailTestSend,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> ActivityEmailTestResult:
    """Una prueba con datos ficticios a un destinatario autorizado. Auditada."""
    return ActivityEmailTestResult.model_validate(
        await envio_de_prueba.enviar_prueba(
            company_id=company.id,
            actor_user_id=current_user.id,
            template_type=template_type,
            to=payload.to,
        )
    )


# ── Reportes reales a demanda (RTE-MAIL-CP4-02) ─────────────────────────────
#
# Cuatro autoridades distintas (OD-10): configurar (`manage`), ver un reporte
# con datos reales (`preview`), enviarlo ahora (`send`) y reenviar uno que ya
# salió (`resend`). Las cuatro a demanda.

_VER_REAL = require_permissions(["route.activityemails.preview"])
_ENVIAR = require_permissions(["route.activityemails.send"])
_REENVIAR = require_permissions(["route.activityemails.resend"])


async def _objetivo(*, company_id: int, actor_user_id: int, recipient_user_id: int) -> None:
    """404 si el destinatario está fuera de lo que este actor puede gestionar.

    Un mando puede pedir **su propio** reporte; para cualquier otro, la misma
    delegación que la administración de usuarios (un manager, su rama).
    """
    # Primero, que sea de **esta** compañía: un administrador sin rol de mando
    # no está acotado por la delegación, y sin esto podía pedir el reporte de
    # alguien de otro tenant.
    if not await delivery.es_miembro(company_id=company_id, user_id=recipient_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this company")
    if recipient_user_id == actor_user_id:
        return
    d = await delegada.delegacion(company_id=company_id, actor_user_id=actor_user_id)
    await delegada.exigir_objetivo(d, company_id=company_id, user_id=recipient_user_id)


def _tipo(report_type: str) -> str:
    if report_type not in ActivityEmailType.values():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown activity email")
    return report_type


@router.post("/reports/preview")
async def preview_real_report(
    payload: ReportRequest,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_VER_REAL),
    company: TenantContext = Depends(get_company_required),
) -> ReportPreviewRead:
    """El reporte con datos reales y si se puede enviar. **No escribe ni envía.**"""
    tipo = _tipo(payload.report_type)
    await _objetivo(company_id=company.id, actor_user_id=current_user.id, recipient_user_id=payload.recipient_user_id)
    ev = await delivery.evaluar(
        company_id=company.id, report_type=tipo, recipient_user_id=payload.recipient_user_id,
        operational_date=payload.operational_date, ahora=datetime.now(timezone.utc),
    )
    r = ev.reporte
    return ReportPreviewRead(
        report_type=r.report_type,
        recipient_user_id=r.recipient_user_id,
        recipient_name=r.recipient_name,
        destination_masked=ev.destination_masked,
        operational_date=r.operational_date,
        time_zone=r.time_zone,
        cutoff_at=r.cutoff_at,
        due_at=r.due_at,
        generated_at=r.generated_at,
        provisional=r.provisional,
        eligible=r.eligible,
        reason_code=r.reason_code,
        reason_message=delivery.MOTIVOS.get(r.reason_code) if r.reason_code else None,
        coverage=r.coverage,
        activity_count=r.activity_count,
        subject=r.subject,
        body=r.body,
        can_send=ev.can_send,
        blocked_reason=ev.blocked_reason,
        blocked_message=delivery.MOTIVOS.get(ev.blocked_reason) if ev.blocked_reason else None,
        delivery=DeliveryRead.model_validate(ev.delivery) if ev.delivery else None,
        can_resend=ev.can_resend,
        resend_blocked_reason=ev.resend_blocked_reason,
        resend_blocked_message=delivery.MOTIVOS.get(ev.resend_blocked_reason) if ev.resend_blocked_reason else None,
        resends=[ResendRead.model_validate(r) for r in ev.resends],
    )


@router.post("/reports/send")
async def send_real_report(
    payload: ReportSendRequest,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_ENVIAR),
    company: TenantContext = Depends(get_company_required),
) -> ReportSendResult:
    """Envía **ya** un reporte que tocaba: al destinatario configurado, nunca a
    otra dirección. Recalcula todo; si ya salió o está saliendo, 409."""
    tipo = _tipo(payload.report_type)
    await _objetivo(company_id=company.id, actor_user_id=current_user.id, recipient_user_id=payload.recipient_user_id)
    resultado = await delivery.enviar_ahora(
        company_id=company.id, actor_user_id=current_user.id, report_type=tipo,
        recipient_user_id=payload.recipient_user_id, operational_date=payload.operational_date,
        reason=payload.reason, ahora=datetime.now(timezone.utc),
    )
    return ReportSendResult.model_validate(resultado)


@router.post("/reports/resend")
async def resend_real_report(
    payload: ReportResendRequest,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_REENVIAR),
    company: TenantContext = Depends(get_company_required),
) -> ResendResult:
    """Reenvía un reporte que ya salió (o cuyo resultado es incierto), con los
    datos de ahora y al destinatario configurado. Un doble clic responde 409."""
    tipo = _tipo(payload.report_type)
    await _objetivo(company_id=company.id, actor_user_id=current_user.id, recipient_user_id=payload.recipient_user_id)
    resultado = await delivery.reenviar(
        company_id=company.id, actor_user_id=current_user.id, report_type=tipo,
        recipient_user_id=payload.recipient_user_id, operational_date=payload.operational_date,
        expected_resends=payload.expected_resends, reason=payload.reason, ahora=datetime.now(timezone.utc),
    )
    return ResendResult.model_validate(resultado)


@router.get("/status")
async def get_operational_status(
    _authz: None = Depends(_GESTIONAR),
    _company: TenantContext = Depends(get_company_required),
) -> OperationalStatusRead:
    """Proveedor, interruptores, tipos activos y la última pasada de cada reloj."""
    return OperationalStatusRead.model_validate(await delivery.estado_operativo())


@router.get("/history")
async def delivery_history(
    request: Request,
    params: HistoryParams = Depends(),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_GESTIONAR),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[DeliveryHistoryRead]:
    """Delivery History: entregas y reenvíos, acotados a quien mira. Sin contenido."""
    if params.report_type:
        _tipo(params.report_type)
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    alcance = await delegada.gestionables(d, company_id=company.id)
    if alcance is not None:
        alcance = alcance | {current_user.id}
    filas, total = await delivery.historial_paginado(
        company_id=company.id, recipient_ids=alcance, report_type=params.report_type,
        recipient_user_id=params.recipient_user_id, desde=params.date_from, hasta=params.date_to,
        disparador=params.trigger, page=params.page, page_size=params.page_size,
    )
    paginator = Paginator(
        total_items=total, page=params.page, page_size=params.page_size,
        results=[DeliveryHistoryRead.model_validate(f) for f in filas], request=request,
    )
    return schema.PaginatedResponse[DeliveryHistoryRead](**paginator.to_response())


@router.get("/reports/deliveries")
async def list_deliveries(
    report_type: str | None = Query(None, max_length=40),
    recipient_user_id: int | None = Query(None),
    operational_date: date | None = Query(None),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(_VER_REAL),
    company: TenantContext = Depends(get_company_required),
) -> list[DeliveryRead]:
    """Historial de envíos reales, sin contenido, acotado a quien mira."""
    d = await delegada.delegacion(company_id=company.id, actor_user_id=current_user.id)
    alcance = await delegada.gestionables(d, company_id=company.id)
    if alcance is not None:
        alcance = alcance | {current_user.id}
    filas = await delivery.historial(
        company_id=company.id, recipient_ids=alcance, report_type=report_type,
        recipient_user_id=recipient_user_id, operational_date=operational_date,
    )
    return [DeliveryRead.model_validate(f) for f in filas]
