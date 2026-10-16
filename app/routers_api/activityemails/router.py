"""
Correos de actividad (RTE-NOT-01): plantillas y destinatarios.

**Sólo configuración.** Ningún endpoint de aquí envía un correo ni programa un
envío: guardar, activar o previsualizar sólo deja datos guardados. El envío es
RTE-NOT-02/03 (BR-10, BR-12).

Todo exige `route.activityemails.manage`, la compañía del subdominio y, en
destinatarios, el alcance de la jerarquía: un manager con la capacidad sólo ve
y cambia a su rama, igual que en la administración de usuarios.
"""

from fastapi import APIRouter, Depends, Request

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
    RecipientsPaginationParams,
)
from app.routers_api.activityemails.service import ActivityEmailService
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
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
