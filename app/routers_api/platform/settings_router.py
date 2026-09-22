"""
Settings de plataforma: integraciones, credenciales, políticas y su traza.

Qué cambió respecto al registro de sólo lectura
-----------------------------------------------
Antes Settings enseñaba variables de entorno y no dejaba cambiar nada: no había
dónde guardar una contraseña sin dejarla en claro (OD-07). Con D12-01 las
credenciales viven en PostgreSQL, cifradas con una llave que no está en la base,
así que ahora se configuran aquí.

Reglas que este router sostiene
-------------------------------
* **Un secreto nunca vuelve.** Se escribe y se reemplaza; ninguna respuesta lo
  lleva, ni entero ni truncado. Lo que vuelve es si está puesto, cuándo y hasta
  cuándo vale.
* **Guardar borra la verificación.** `verified_at` demuestra que funcionaba una
  configuración concreta; cualquier cambio la invalida.
* **Todo cambio deja traza** en `platform_audit_event`, con el valor de los
  secretos sustituido por `"changed"`.
* **Sólo administración de plataforma** (`require_platform_admin`): esto es del
  despliegue, no de un tenant (D6).
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import delete, select

from app.core.dao.concurrency import ensure_version
from app.core.db.session import transaction
from app.core.platform import policies as policy_defs
from app.core.platform import providers as provider_defs
from app.core.platform.audit import REDACTED, record_platform_event
from app.core.platform.config_service import notify_change, platform_config
from app.core.platform.models import (
    PlatformAuditEvent,
    PlatformIntegration,
    PlatformPolicy,
    PlatformSecret,
)
from app.core.platform.integration_status import load_status
from app.core.platform.secrets import MasterKeyUnavailable, seal
from app.routers_api.platform.settings_schemas import (
    DocLinkRead,
    GuideStepRead,
    IntegrationRead,
    IntegrationUpdate,
    PlatformAuditRead,
    PolicyRead,
    PolicyUpdate,
    ProviderFieldRead,
    ProviderRead,
    SecretStateRead,
    SecretWrite,
)
from app.routers_api.users.dependencies import require_platform_admin
from app.routers_api.users.models import Users

router = APIRouter(prefix="/platform", tags=["Platform settings"])


# ══ Lectura ═══════════════════════════════════════════════════════════════════


def _provider_read(provider: provider_defs.Provider) -> ProviderRead:
    return ProviderRead(
        key=provider.key,
        title=provider.title,
        summary=provider.summary,
        who=provider.who,
        recommended=provider.recommended,
        available=provider.available,
        steps=[GuideStepRead(text=s.text, link=s.link) for s in provider.steps],
        fields=[
            ProviderFieldRead(
                name=f.name,
                label=f.label,
                kind=f.kind.value,
                source=f.source,
                format=f.format,
                required=f.required,
                default=f.default,
                choices=list(f.choices),
                pattern=f.pattern,
                expires=f.expires,
            )
            for f in provider.fields
        ],
        warnings=list(provider.warnings),
        docs=[DocLinkRead(label=d.label, url=d.url) for d in provider.docs],
    )


async def _integration_read(session, definicion: provider_defs.Integration) -> IntegrationRead:
    """La tarjeta de una integración. El estado sale de `load_status`, el mismo
    cálculo que usan Diagnostics y la preparación para producción."""
    estado = await load_status(session, definicion)
    fila, secretos, proveedor = estado.row, estado.secrets, estado.provider
    por_nombre = {s.name: s for s in secretos}
    return IntegrationRead(
        key=definicion.key,
        title=definicion.title,
        summary=definicion.summary,
        required=definicion.required,
        open_decision=definicion.open_decision,
        providers=[_provider_read(p) for p in definicion.providers],
        provider=fila.provider if fila else None,
        enabled=bool(fila.enabled) if fila else True,
        status=estado.readiness.status,
        missing=estado.readiness.missing,
        config=dict(fila.config or {}) if fila else {},
        secrets=[
            SecretStateRead(
                name=f.name,
                label=f.label,
                present=f.name in por_nombre,
                set_at=por_nombre[f.name].set_at if f.name in por_nombre else None,
                expires_at=por_nombre[f.name].expires_at if f.name in por_nombre else None,
            )
            for f in (proveedor.secret_fields if proveedor else ())
        ],
        verified_at=fila.verified_at if fila else None,
        version=fila.version if fila else 0,
    )


@router.get("/integrations")
async def list_integrations(
    _admin: Users = Depends(require_platform_admin),
) -> list[IntegrationRead]:
    async with transaction() as session:
        return [await _integration_read(session, d) for d in provider_defs.INTEGRATIONS]


def _definicion_o_404(key: str) -> provider_defs.Integration:
    definicion = provider_defs.BY_KEY.get(key)
    if definicion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such integration.")
    return definicion


@router.get("/integrations/{key}")
async def get_integration(
    key: str = Path(..., min_length=1, max_length=60),
    _admin: Users = Depends(require_platform_admin),
) -> IntegrationRead:
    definicion = _definicion_o_404(key)
    async with transaction() as session:
        return await _integration_read(session, definicion)


# ══ Escritura ══════════════════════════════════════════════════════════════════


@router.put("/integrations/{key}")
async def update_integration(
    payload: IntegrationUpdate,
    request: Request,
    key: str = Path(..., min_length=1, max_length=60),
    admin: Users = Depends(require_platform_admin),
) -> IntegrationRead:
    definicion = _definicion_o_404(key)
    proveedor = definicion.provider(payload.provider)
    if proveedor is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{payload.provider}' is not a provider for {definicion.title}.",
        )
    if not proveedor.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{proveedor.title} cannot be configured yet: it requires a connector.",
        )
    limpio, errores = provider_defs.validate_config(proveedor, payload.config)
    if errores:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errores)

    async with transaction() as session:
        fila = await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == key).with_for_update()
        )
        antes = {}
        if fila is None:
            if payload.expected_version not in (None, 0):
                ensure_version(current=0, expected=payload.expected_version)
            fila = PlatformIntegration(key=key, version=1)
            session.add(fila)
        else:
            ensure_version(current=fila.version, expected=payload.expected_version)
            antes = {"provider": fila.provider, "enabled": fila.enabled, **dict(fila.config or {})}
            fila.version = fila.version + 1

        cambio_de_proveedor = fila.provider not in (None, proveedor.key)
        fila.provider = proveedor.key
        fila.enabled = payload.enabled
        fila.config = limpio
        fila.verified_at = None
        fila.verified_by_user_id = None
        fila.updated_by_user_id = admin.id
        await session.flush()

        if cambio_de_proveedor:
            # Los secretos del proveedor anterior no sirven al nuevo, y dejarlos
            # sería guardar credenciales que ya nadie usa.
            await session.execute(delete(PlatformSecret).where(PlatformSecret.integration_id == fila.id))

        despues = {"provider": fila.provider, "enabled": fila.enabled, **limpio}
        cambios = {
            campo: {"old": antes.get(campo), "new": valor}
            for campo, valor in despues.items()
            if antes.get(campo) != valor
        }
        await record_platform_event(
            request=request, actor=admin, action="integration.updated",
            target=f"integration:{key}",
            changes={**cambios, **({"secrets": "cleared by provider change"} if cambio_de_proveedor else {})},
        )
        await notify_change(session)
        leida = await _integration_read(session, definicion)

    await platform_config.refresh()
    return leida


@router.put("/integrations/{key}/secrets/{name}")
async def set_secret(
    payload: SecretWrite,
    request: Request,
    key: str = Path(..., min_length=1, max_length=60),
    name: str = Path(..., min_length=1, max_length=60),
    admin: Users = Depends(require_platform_admin),
) -> IntegrationRead:
    definicion = _definicion_o_404(key)
    async with transaction() as session:
        fila = await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == key).with_for_update()
        )
        proveedor = definicion.provider(fila.provider) if fila else None
        if proveedor is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Choose and save a provider before setting its credentials.",
            )
        campo = proveedor.field(name)
        if campo is None or not campo.secret:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{name}' is not a credential of {proveedor.title}.",
            )
        try:
            sellado = seal(integration_key=key, secret_name=name, plaintext=payload.value)
        except MasterKeyUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        caduca = (
            datetime.combine(payload.expires_at, time(23, 59, 59), tzinfo=timezone.utc)
            if payload.expires_at
            else None
        )
        existente = await session.scalar(
            select(PlatformSecret).where(
                PlatformSecret.integration_id == fila.id, PlatformSecret.name == name
            )
        )
        if existente is None:
            session.add(
                PlatformSecret(
                    integration_id=fila.id, name=name, ciphertext=sellado.ciphertext,
                    nonce=sellado.nonce, key_id=sellado.key_id, set_by_user_id=admin.id,
                    expires_at=caduca,
                )
            )
            accion = "secret.set"
        else:
            existente.ciphertext = sellado.ciphertext
            existente.nonce = sellado.nonce
            existente.key_id = sellado.key_id
            existente.set_by_user_id = admin.id
            existente.set_at = datetime.now(timezone.utc)
            existente.expires_at = caduca
            accion = "secret.replaced"

        fila.verified_at = None
        fila.verified_by_user_id = None
        fila.version = fila.version + 1
        await session.flush()
        await record_platform_event(
            request=request, actor=admin, action=accion, target=f"integration:{key}",
            changes={"secret": name, "value": REDACTED,
                     "expires_at": payload.expires_at.isoformat() if payload.expires_at else None},
        )
        await notify_change(session)
        leida = await _integration_read(session, definicion)

    await platform_config.refresh()
    return leida


@router.delete("/integrations/{key}/secrets/{name}")
async def clear_secret(
    request: Request,
    key: str = Path(..., min_length=1, max_length=60),
    name: str = Path(..., min_length=1, max_length=60),
    admin: Users = Depends(require_platform_admin),
) -> IntegrationRead:
    definicion = _definicion_o_404(key)
    async with transaction() as session:
        fila = await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == key).with_for_update()
        )
        if fila is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing is configured.")
        borradas = (
            await session.execute(
                delete(PlatformSecret).where(
                    PlatformSecret.integration_id == fila.id, PlatformSecret.name == name
                )
            )
        ).rowcount
        if not borradas:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That credential is not set.")
        fila.verified_at = None
        fila.verified_by_user_id = None
        fila.version = fila.version + 1
        await record_platform_event(
            request=request, actor=admin, action="secret.cleared", target=f"integration:{key}",
            changes={"secret": name, "value": REDACTED},
        )
        await notify_change(session)
        leida = await _integration_read(session, definicion)

    await platform_config.refresh()
    return leida


# ══ Políticas ═══════════════════════════════════════════════════════════════════


async def _policy_read(session, definicion: policy_defs.PolicyDefinition) -> PolicyRead:
    fila = await session.scalar(select(PlatformPolicy).where(PlatformPolicy.key == definicion.key))
    valor, _ = policy_defs.validate(definicion.key, dict(fila.value) if fila else {})
    return PolicyRead(
        key=definicion.key,
        title=definicion.title,
        summary=definicion.summary,
        value=valor or definicion.defaults(),
        defaults=definicion.defaults(),
        customized=fila is not None,
        version=fila.version if fila else 0,
    )


@router.get("/policies")
async def list_policies(_admin: Users = Depends(require_platform_admin)) -> list[PolicyRead]:
    async with transaction() as session:
        return [await _policy_read(session, d) for d in policy_defs.POLICIES]


@router.put("/policies/{key}")
async def update_policy(
    payload: PolicyUpdate,
    request: Request,
    key: str = Path(..., min_length=1, max_length=60),
    admin: Users = Depends(require_platform_admin),
) -> PolicyRead:
    definicion = policy_defs.BY_KEY.get(key)
    if definicion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such policy.")
    valor, errores = policy_defs.validate(key, payload.value)
    if errores:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errores)

    async with transaction() as session:
        fila = await session.scalar(
            select(PlatformPolicy).where(PlatformPolicy.key == key).with_for_update()
        )
        antes = dict(fila.value) if fila else definicion.defaults()
        if fila is None:
            if payload.expected_version not in (None, 0):
                ensure_version(current=0, expected=payload.expected_version)
            fila = PlatformPolicy(key=key, value=valor, version=1, updated_by_user_id=admin.id)
            session.add(fila)
        else:
            ensure_version(current=fila.version, expected=payload.expected_version)
            fila.value = valor
            fila.version = fila.version + 1
            fila.updated_by_user_id = admin.id
        await session.flush()
        await record_platform_event(
            request=request, actor=admin, action="policy.updated", target=f"policy:{key}",
            changes={c: {"old": antes.get(c), "new": v} for c, v in valor.items() if antes.get(c) != v},
        )
        await notify_change(session)
        leida = await _policy_read(session, definicion)

    await platform_config.refresh()
    return leida


# ══ Traza ═══════════════════════════════════════════════════════════════════════


@router.get("/audit")
async def list_platform_audit(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, ge=1),
    _admin: Users = Depends(require_platform_admin),
) -> list[PlatformAuditRead]:
    async with transaction() as session:
        consulta = select(PlatformAuditEvent).order_by(PlatformAuditEvent.id.desc()).limit(limit)
        if before_id:
            consulta = consulta.where(PlatformAuditEvent.id < before_id)
        filas = (await session.execute(consulta)).scalars().all()
        return [PlatformAuditRead.model_validate(f, from_attributes=True) for f in filas]
