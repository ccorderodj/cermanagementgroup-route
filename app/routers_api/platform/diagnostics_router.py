"""
Diagnostics y preparación para producción.

* `GET  /platform/readiness`                    el veredicto único y sus gates
* `GET  /platform/posture`                      la postura de seguridad
* `GET  /platform/diagnostics`                  cada comprobación y su último estado
* `POST /platform/diagnostics/run-all`          comprobar todo ahora
* `POST /platform/diagnostics/{key}/run`        comprobar una
* `GET  /platform/diagnostics/{key}/history`    su historial
* `POST /platform/integrations/{key}/verify`    comprobar y, si pasa, cerrar el gate
* `POST /platform/integrations/{key}/test-message`  sólo "email" o "email_fallback"
* `POST /platform/diagnostics/rescan-quarantine`

Sólo administración de plataforma.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import select

from app.config import settings
from app.core.db.session import transaction
from app.core.email import backends as email_backends
from app.core.platform import diagnostics, readiness
from app.core.platform import providers as provider_defs
from app.core.platform.audit import record_platform_event
from app.core.platform.config_service import notify_change, platform_config
from app.core.platform.integration_status import load_status
from app.core.platform.models import PlatformHealthCheck, PlatformHealthCheckRun, PlatformIntegration
from app.core.platform.posture import security_posture
from app.routers_api.platform.diagnostics_schemas import (
    CheckRead,
    CheckRunRead,
    GateRead,
    PostureItemRead,
    ReadinessRead,
    TestMessageWrite,
    VerifyRead,
)
from app.routers_api.platform.settings_router import _integration_read
from app.routers_api.users.dependencies import require_platform_admin
from app.routers_api.users.models import Users

router = APIRouter(prefix="/platform", tags=["Platform diagnostics"])


@router.get("/readiness")
async def get_readiness(_admin: Users = Depends(require_platform_admin)) -> ReadinessRead:
    async with transaction() as session:
        informe = await readiness.evaluate(session)
    return ReadinessRead(
        production_ready=informe.production_ready,
        mode=informe.mode,
        counts=informe.counts,
        gates=[GateRead(**g.__dict__) for g in informe.gates],
    )


@router.get("/posture")
async def get_posture(_admin: Users = Depends(require_platform_admin)) -> list[PostureItemRead]:
    return [PostureItemRead(**p.__dict__) for p in security_posture()]


@router.get("/diagnostics")
async def list_checks(_admin: Users = Depends(require_platform_admin)) -> list[CheckRead]:
    async with transaction() as session:
        filas = {
            f.capability_key: f
            for f in (await session.execute(select(PlatformHealthCheck))).scalars()
        }
    salida = []
    for c in diagnostics.CHECKS:
        fila = filas.get(c.key)
        salida.append(
            CheckRead(
                key=c.key, title=c.title, kind=c.kind, summary=c.summary,
                status=fila.last_status if fila else "unknown",
                detail=fila.last_detail if fila else "It has never been checked.",
                last_checked_at=fila.last_checked_at if fila else None,
                last_success_at=fila.last_success_at if fila else None,
            )
        )
    return salida


def _run_read(r: diagnostics.RunOutcome, trigger: str, actor: int | None) -> CheckRunRead:
    return CheckRunRead(
        capability_key=r.key, status=r.status, detail=r.detail, checked_at=r.checked_at,
        duration_ms=r.duration_ms, trigger=trigger, actor_user_id=actor,
    )


@router.post("/diagnostics/run-all")
async def run_all_checks(
    request: Request, admin: Users = Depends(require_platform_admin)
) -> list[CheckRunRead]:
    await platform_config.refresh()
    resultados = await diagnostics.run_all(trigger="manual", actor_user_id=admin.id)
    await record_platform_event(
        request=request, actor=admin, action="diagnostics.run_all", target="diagnostics",
        changes={r.key: r.status for r in resultados},
    )
    return [_run_read(r, "manual", admin.id) for r in resultados]


@router.post("/diagnostics/{key}/run")
async def run_one_check(
    request: Request,
    key: str = Path(..., min_length=1, max_length=100),
    admin: Users = Depends(require_platform_admin),
) -> CheckRunRead:
    if key not in diagnostics.BY_KEY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such check.")
    await platform_config.refresh()
    resultado = await diagnostics.run_check(key, trigger="manual", actor_user_id=admin.id)
    await record_platform_event(
        request=request, actor=admin, action="diagnostics.run", target=f"check:{key}",
        changes={"status": resultado.status},
    )
    return _run_read(resultado, "manual", admin.id)


@router.get("/diagnostics/{key}/history")
async def check_history(
    key: str = Path(..., min_length=1, max_length=100),
    limit: int = Query(25, ge=1, le=200),
    _admin: Users = Depends(require_platform_admin),
) -> list[CheckRunRead]:
    async with transaction() as session:
        filas = (
            await session.execute(
                select(PlatformHealthCheckRun)
                .where(PlatformHealthCheckRun.capability_key == key)
                .order_by(PlatformHealthCheckRun.id.desc())
                .limit(limit)
            )
        ).scalars().all()
    return [CheckRunRead.model_validate(f) for f in filas]


@router.post("/integrations/{key}/verify")
async def verify_integration(
    request: Request,
    key: str = Path(..., min_length=1, max_length=60),
    admin: Users = Depends(require_platform_admin),
) -> VerifyRead:
    definicion = provider_defs.BY_KEY.get(key)
    if definicion is None or key not in diagnostics.BY_KEY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This integration cannot be verified.")

    async with transaction() as session:
        estado = await load_status(session, definicion)
    if estado.readiness.status not in ("configured", "verified", "failing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=["Complete the configuration before verifying."] + estado.readiness.missing,
        )

    await platform_config.refresh()
    resultado = await diagnostics.run_check(key, trigger="verify", actor_user_id=admin.id)

    async with transaction() as session:
        fila = await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == key).with_for_update()
        )
        if resultado.status == diagnostics.HEALTHY:
            fila.verified_at = datetime.now(timezone.utc)
            fila.verified_by_user_id = admin.id
            accion = "integration.verified"
        else:
            fila.verified_at = None
            fila.verified_by_user_id = None
            accion = "integration.verification_failed"
        await session.flush()
        await record_platform_event(
            request=request, actor=admin, action=accion, target=f"integration:{key}",
            changes={"status": resultado.status, "detail": resultado.detail},
        )
        await notify_change(session)
        integracion = await _integration_read(session, definicion)

    await platform_config.refresh()
    return VerifyRead(integration=integracion, check=_run_read(resultado, "verify", admin.id))


_EMAIL_KEYS = ("email", "email_fallback")


@router.post("/integrations/{key}/test-message")
async def send_test_message(
    payload: TestMessageWrite,
    request: Request,
    key: str = Path(..., min_length=1, max_length=60),
    admin: Users = Depends(require_platform_admin),
):
    import asyncio

    if key not in _EMAIL_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not an email integration.")

    await platform_config.refresh()
    backend = email_backends.backend_from_platform_config(key)
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Configure and save this email provider first."
        )
    mensaje = email_backends.OutgoingEmail(
        to=str(payload.to),
        subject=f"{settings.APP_NAME} — test message",
        body=(
            "This is a test message sent from Settings to confirm that outbound email works.\n"
            "No action is needed.\n"
        ),
        sender=backend.sender or "",
    )
    try:
        await asyncio.to_thread(backend.send, mensaje)
    except (email_backends.EmailAuthFailed, email_backends.EmailUnreachable) as exc:
        await record_platform_event(
            request=request, actor=admin, action="email.test_failed", target=f"integration:{key}",
            changes={"to": str(payload.to), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await record_platform_event(
        request=request, actor=admin, action="email.test_sent", target=f"integration:{key}",
        changes={"to": str(payload.to)},
    )
    return {"sent": True, "to": str(payload.to)}

