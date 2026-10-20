"""
Reglas de la configuración de correos de actividad (RTE-NOT-01).

Plantillas
----------
* Leer devuelve el texto guardado o, si nunca se personalizó, el aprobado.
* Guardar valida contra `content` (variables permitidas, bloques obligatorios,
  texto plano) y exige la versión leída: quien guarda sobre un cambio ajeno
  recibe 409 en vez de pisarlo (UC-01). Una plantilla sin fila tiene versión 0.
* Restaurar pone el texto aprobado en **esa** plantilla y nada más (BR-09).

Destinatarios
-------------
* Las personas que ejecutan jornada (`route.worksession.execute` en su rol) y
  que el actor puede gestionar: la jerarquía acota a un manager a su rama, con
  la misma delegación que la administración de usuarios. Fuera de eso, 404.
* Activar exige pertenencia y cuenta activas y un correo válido en la cuenta.
  Desactivar se permite siempre: apagar nunca puede quedar bloqueado.
* Cada interruptor es independiente; el que no se envía no cambia.

Todo cambio queda en `audit_event`.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.audit.service import diff, record_event
from app.core.dao.concurrency import VersionConflict, ensure_version
from app.core.db.session import db_session, transaction
from app.core.email.politica_de_prueba import correo_valido
from app.routers_api.activityemails import content
from app.routers_api.activityemails.models import ActivityEmailPreference, ActivityEmailTemplate
from app.routers_api.activityemails.strategic import roster
from app.routers_api.companies.models import UserCompany
from app.core.rbac.catalog import ROUTE_PRODUCT_ROLE_LABELS
from app.routers_api.organization import delegation as delegada
from app.routers_api.organization.scope import ROLES_ACOTADOS
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from app.routers_api.users.models import Users

#: Quién puede recibir los reportes estratégicos: los mandos de la jerarquía y
#: los administradores de la compañía, porque hoy el CEO lo representa un
#: administrador (RTE-MAIL-CLOSE-01, decisión cerrada: no hay rol CEO aparte).
ROLES_ESTRATEGICOS: frozenset[str] = ROLES_ACOTADOS | {"owner", "admin"}

#: Quién puede recibir estos correos: quien ejecuta jornadas y tiene actividad.
CAPACIDAD_DE_DESTINATARIO = "route.worksession.execute"


def _error_de_validacion(errores: list[tuple[str, str]]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[
            {"loc": ["body", campo], "msg": mensaje, "type": "value_error"}
            for campo, mensaje in errores
        ],
    )


def _validar(template_type: str, *, subject: str, body: str) -> None:
    errores = content.validate(template_type, subject=subject, body=body)
    if errores:
        raise _error_de_validacion(errores)


def _tipo(template_type: str) -> str:
    if template_type not in content.ActivityEmailType.values():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown activity email")
    return template_type


class ActivityEmailService:
    # ── Plantillas ──────────────────────────────────────────────────────────

    @staticmethod
    def _vista(template_type: str, fila: ActivityEmailTemplate | None, editor: str | None) -> dict:
        s = content.spec(template_type)
        subject = fila.subject if fila else s.default_subject
        body = fila.body if fila else s.default_body
        return {
            "template_type": template_type,
            "group": s.group.value,
            "label": s.label,
            "schedule_label": s.schedule_label,
            "send_condition": s.send_condition,
            "subject": subject,
            "body": body,
            "is_default": subject == s.default_subject and body == s.default_body,
            "version": fila.version if fila else 0,
            "updated_at": fila.updated_at if fila else None,
            "updated_by_name": editor,
            "subject_tokens": list(s.subject_tokens),
            "tokens": [
                {
                    "token": t,
                    "description": content.TOKEN_HELP[t],
                    "required": t in s.required_tokens,
                }
                for t in s.body_tokens
            ],
        }

    @classmethod
    async def list_templates(cls, *, company_id: int) -> list[dict]:
        async with db_session() as session:
            filas = (
                await session.execute(
                    select(ActivityEmailTemplate, Users.first_name, Users.last_name)
                    .outerjoin(Users, Users.id == ActivityEmailTemplate.updated_by_user_id)
                    .where(ActivityEmailTemplate.company_id == company_id)
                )
            ).all()
        por_tipo = {f[0].template_type: f for f in filas}
        vistas = []
        for tipo in content.ActivityEmailType.values():
            f = por_tipo.get(tipo)
            editor = f"{f[1]} {f[2]}".strip() if f and f[1] is not None else None
            vistas.append(cls._vista(tipo, f[0] if f else None, editor))
        return vistas

    @classmethod
    async def get_template(cls, *, company_id: int, template_type: str) -> dict:
        tipo = _tipo(template_type)
        return next(v for v in await cls.list_templates(company_id=company_id) if v["template_type"] == tipo)

    @classmethod
    async def _guardar(
        cls,
        *,
        company_id: int,
        template_type: str,
        subject: str,
        body: str,
        expected_version: int,
        actor_user_id: int,
        action: str,
    ) -> dict:
        async with transaction() as session:
            fila = await session.scalar(
                select(ActivityEmailTemplate)
                .where(
                    ActivityEmailTemplate.company_id == company_id,
                    ActivityEmailTemplate.template_type == template_type,
                )
                .with_for_update()
            )
            s = content.spec(template_type)
            if fila is None:
                ensure_version(current=0, expected=expected_version)
                antes = {"subject": s.default_subject, "body": s.default_body}
                fila = ActivityEmailTemplate(
                    company_id=company_id,
                    template_type=template_type,
                    subject=subject,
                    body=body,
                    updated_by_user_id=actor_user_id,
                    version=1,
                )
                session.add(fila)
            else:
                ensure_version(current=fila.version, expected=expected_version)
                antes = {"subject": fila.subject, "body": fila.body}
                fila.subject = subject
                fila.body = body
                fila.updated_by_user_id = actor_user_id
                fila.version = fila.version + 1
            try:
                await session.flush()
            except IntegrityError as exc:
                # Dos primeras escrituras a la vez: la segunda choca con la
                # restricción única. Es el mismo conflicto que una versión vieja.
                raise VersionConflict(current_version=1) from exc
            fila_id = fila.id

        await record_event(
            company_id=company_id,
            entity_type="activity_email_template",
            entity_id=fila_id,
            action=action,
            actor_user_id=actor_user_id,
            summary=f"Activity email '{s.label}' {'restored to default' if action == 'restore_default' else 'updated'}",
            changes=diff(antes, {"subject": subject, "body": body}),
        )
        return await cls.get_template(company_id=company_id, template_type=template_type)

    @classmethod
    async def update_template(
        cls, *, company_id: int, template_type: str, subject: str, body: str, version: int, actor_user_id: int
    ) -> dict:
        tipo = _tipo(template_type)
        _validar(tipo, subject=subject, body=body)
        return await cls._guardar(
            company_id=company_id, template_type=tipo, subject=subject, body=body,
            expected_version=version, actor_user_id=actor_user_id, action="update",
        )

    @classmethod
    async def restore_default(
        cls, *, company_id: int, template_type: str, version: int, actor_user_id: int
    ) -> dict:
        tipo = _tipo(template_type)
        actual = await cls.get_template(company_id=company_id, template_type=tipo)
        ensure_version(current=actual["version"], expected=version)
        if actual["is_default"]:
            return actual
        s = content.spec(tipo)
        return await cls._guardar(
            company_id=company_id, template_type=tipo, subject=s.default_subject, body=s.default_body,
            expected_version=version, actor_user_id=actor_user_id, action="restore_default",
        )

    @staticmethod
    def preview(*, template_type: str, subject: str, body: str) -> dict:
        tipo = _tipo(template_type)
        _validar(tipo, subject=subject, body=body)
        return {
            "is_sample": True,
            "sample_label": content.SAMPLE_LABEL,
            "subject": content.render(subject, content.sample_values(tipo)),
            "body": content.render(body, content.sample_values(tipo)),
        }

    # ── Destinatarios ───────────────────────────────────────────────────────

    @staticmethod
    def _consulta_destinatarios(*, company_id: int, user_ids: set[int] | None, q: str | None):
        ejecuta = exists().where(
            RolePermission.role_id == UserCompany.role_id,
            RolePermission.is_active.is_(True),
            RolePermission.permission_id == Permission.id,
            Permission.name == CAPACIDAD_DE_DESTINATARIO,
        )
        stmt = (
            select(
                Users.id.label("user_id"),
                Users.first_name,
                Users.last_name,
                Users.username,
                Users.email,
                Users.is_active.label("platform_active"),
                UserCompany.is_active.label("membership_active"),
                Role.name.label("role_name"),
                func.coalesce(ActivityEmailPreference.midday_enabled, False).label("midday_enabled"),
                func.coalesce(ActivityEmailPreference.end_of_day_enabled, False).label("end_of_day_enabled"),
                func.coalesce(ActivityEmailPreference.version, 0).label("version"),
            )
            .select_from(UserCompany)
            .join(Users, Users.id == UserCompany.user_id)
            .join(Role, and_(Role.id == UserCompany.role_id, Role.company_id == UserCompany.company_id))
            .outerjoin(
                ActivityEmailPreference,
                and_(
                    ActivityEmailPreference.user_id == UserCompany.user_id,
                    ActivityEmailPreference.company_id == UserCompany.company_id,
                ),
            )
            .where(
                UserCompany.company_id == company_id,
                UserCompany.deleted_at.is_(None),
                ejecuta,
            )
        )
        if user_ids is not None:
            stmt = stmt.where(Users.id.in_(user_ids) if user_ids else false())
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Users.username.ilike(like),
                    Users.email.ilike(like),
                    Users.first_name.ilike(like),
                    Users.last_name.ilike(like),
                )
            )
        return stmt

    @staticmethod
    def _fila(row) -> dict:
        motivo = None
        if not (row.platform_active and row.membership_active):
            motivo = "inactive"
        elif not correo_valido(row.email):
            motivo = "invalid_email"
        return {
            "user_id": row.user_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "username": row.username,
            "email": row.email,
            "role_name": row.role_name,
            "midday_enabled": bool(row.midday_enabled),
            "end_of_day_enabled": bool(row.end_of_day_enabled),
            "eligible": motivo is None,
            "ineligible_reason": motivo,
            "version": row.version,
        }

    @staticmethod
    async def _alcance(*, company_id: int, actor_user_id: int, include_self: bool) -> set[int] | None:
        """A quién lista este actor; `None`: sin acotar.

        La rama de un mando nunca le incluye a él. `include_self` lo añade para
        pedir su propio reporte (lo que `_objetivo` del router ya permite); la
        consulta de cada lista sigue filtrando por rol, así que un mando sólo
        aparece en la lista estratégica si su rol es de mando.
        """
        d = await delegada.delegacion(company_id=company_id, actor_user_id=actor_user_id)
        alcance = await delegada.gestionables(d, company_id=company_id)
        if include_self and alcance is not None:
            alcance = alcance | {actor_user_id}
        return alcance

    @classmethod
    async def list_recipients(
        cls,
        *,
        company_id: int,
        actor_user_id: int,
        q: str | None,
        page: int,
        page_size: int,
        include_self: bool = False,
    ) -> tuple[list[dict], int]:
        alcance = await cls._alcance(company_id=company_id, actor_user_id=actor_user_id, include_self=include_self)
        stmt = cls._consulta_destinatarios(company_id=company_id, user_ids=alcance, q=q)
        async with db_session() as session:
            total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
            filas = (
                await session.execute(
                    stmt.order_by(Users.first_name, Users.last_name, Users.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        return [cls._fila(f) for f in filas], int(total or 0)

    @classmethod
    async def _destinatario(cls, *, company_id: int, actor_user_id: int, user_id: int) -> dict:
        d = await delegada.delegacion(company_id=company_id, actor_user_id=actor_user_id)
        await delegada.exigir_objetivo(d, company_id=company_id, user_id=user_id)
        stmt = cls._consulta_destinatarios(company_id=company_id, user_ids=None, q=None)
        async with db_session() as session:
            fila = (await session.execute(stmt.where(Users.id == user_id))).first()
        if fila is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this company")
        return cls._fila(fila)

    @classmethod
    async def update_recipient(
        cls,
        *,
        company_id: int,
        actor_user_id: int,
        user_id: int,
        midday_enabled: bool | None,
        end_of_day_enabled: bool | None,
        version: int,
    ) -> dict:
        if midday_enabled is None and end_of_day_enabled is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes to apply")
        actual = await cls._destinatario(company_id=company_id, actor_user_id=actor_user_id, user_id=user_id)
        activa = midday_enabled is True or end_of_day_enabled is True
        if activa and not actual["eligible"]:
            motivo = (
                "This user is not active in this company."
                if actual["ineligible_reason"] == "inactive"
                else "This user has no valid email address. Correct it in Users first."
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=motivo)

        await cls._guardar_preferencias(
            company_id=company_id,
            actor_user_id=actor_user_id,
            user_id=user_id,
            cambios={"midday_enabled": midday_enabled, "end_of_day_enabled": end_of_day_enabled},
            version=version,
        )
        return await cls._destinatario(company_id=company_id, actor_user_id=actor_user_id, user_id=user_id)

    # ── Preferencias: un solo registro por persona ──────────────────────────

    _CAMPOS = ("midday_enabled", "end_of_day_enabled", "strategic_midday_enabled", "strategic_end_of_day_enabled")

    @classmethod
    async def _guardar_preferencias(
        cls, *, company_id: int, actor_user_id: int, user_id: int, cambios: dict, version: int
    ) -> None:
        """Escribe sólo los interruptores pedidos; los demás no cambian. 409 si la
        versión es vieja. Auditado con el diff."""
        cambios = {k: v for k, v in cambios.items() if v is not None}
        async with transaction() as session:
            fila = await session.scalar(
                select(ActivityEmailPreference)
                .where(
                    ActivityEmailPreference.company_id == company_id,
                    ActivityEmailPreference.user_id == user_id,
                )
                .with_for_update()
            )
            if fila is None:
                ensure_version(current=0, expected=version)
                fila = ActivityEmailPreference(
                    company_id=company_id, user_id=user_id, version=0,
                    **{c: False for c in cls._CAMPOS},
                )
                session.add(fila)
            else:
                ensure_version(current=fila.version, expected=version)
            antes = {c: bool(getattr(fila, c)) for c in cls._CAMPOS}
            for campo, valor in cambios.items():
                setattr(fila, campo, valor)
            fila.updated_by_user_id = actor_user_id
            fila.version = fila.version + 1
            despues = {c: bool(getattr(fila, c)) for c in cls._CAMPOS}
            try:
                await session.flush()
            except IntegrityError as exc:
                raise VersionConflict(current_version=1) from exc
            fila_id = fila.id

        delta = diff(antes, despues)
        if delta:
            await record_event(
                company_id=company_id,
                entity_type="activity_email_preference",
                entity_id=fila_id,
                action="update",
                actor_user_id=actor_user_id,
                summary=f"Activity email recipients updated for user {user_id}",
                changes=delta,
            )

    # ── Reportes estratégicos: los mandos ───────────────────────────────────

    @staticmethod
    def _consulta_mandos(*, company_id: int, user_ids: set[int] | None, q: str | None):
        """Miembros que pueden recibir un reporte estratégico
        (`ROLES_ESTRATEGICOS`). El equipo se comprueba después, contra la
        jerarquía real."""
        stmt = (
            select(
                Users.id.label("user_id"),
                Users.first_name,
                Users.last_name,
                Users.email,
                Users.is_active.label("platform_active"),
                UserCompany.is_active.label("membership_active"),
                Role.name.label("role_name"),
                func.coalesce(ActivityEmailPreference.strategic_midday_enabled, False).label("strategic_midday_enabled"),
                func.coalesce(ActivityEmailPreference.strategic_end_of_day_enabled, False).label(
                    "strategic_end_of_day_enabled"
                ),
                func.coalesce(ActivityEmailPreference.version, 0).label("version"),
            )
            .select_from(UserCompany)
            .join(Users, Users.id == UserCompany.user_id)
            .join(Role, and_(Role.id == UserCompany.role_id, Role.company_id == UserCompany.company_id))
            .outerjoin(
                ActivityEmailPreference,
                and_(
                    ActivityEmailPreference.user_id == UserCompany.user_id,
                    ActivityEmailPreference.company_id == UserCompany.company_id,
                ),
            )
            .where(
                UserCompany.company_id == company_id,
                UserCompany.deleted_at.is_(None),
                Role.name.in_(ROLES_ESTRATEGICOS),
            )
        )
        if user_ids is not None:
            stmt = stmt.where(Users.id.in_(user_ids) if user_ids else false())
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Users.username.ilike(like),
                    Users.email.ilike(like),
                    Users.first_name.ilike(like),
                    Users.last_name.ilike(like),
                )
            )
        return stmt

    @staticmethod
    async def _mando(row, *, company_id: int) -> dict:
        """La fila de un mando con su cobertura: las personas activas que
        saldrían **hoy** en su reporte (`strategic.roster`, la misma lista)."""
        cobertura = len((await roster(company_id, row.user_id))[1])
        motivo = None
        if not (row.platform_active and row.membership_active):
            motivo = "inactive"
        elif not correo_valido(row.email):
            motivo = "invalid_email"
        elif cobertura == 0:
            motivo = "no_team"
        return {
            "user_id": row.user_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "role_name": ROUTE_PRODUCT_ROLE_LABELS.get(row.role_name, row.role_name),
            "coverage": cobertura,
            "strategic_midday_enabled": bool(row.strategic_midday_enabled),
            "strategic_end_of_day_enabled": bool(row.strategic_end_of_day_enabled),
            "eligible": motivo is None,
            "ineligible_reason": motivo,
            "version": row.version,
        }

    @classmethod
    async def list_strategic_recipients(
        cls,
        *,
        company_id: int,
        actor_user_id: int,
        q: str | None,
        page: int,
        page_size: int,
        include_self: bool = False,
    ) -> tuple[list[dict], int]:
        alcance = await cls._alcance(company_id=company_id, actor_user_id=actor_user_id, include_self=include_self)
        stmt = cls._consulta_mandos(company_id=company_id, user_ids=alcance, q=q)
        async with db_session() as session:
            total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
            filas = (
                await session.execute(
                    stmt.order_by(Users.first_name, Users.last_name, Users.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        return [await cls._mando(f, company_id=company_id) for f in filas], int(total or 0)

    @classmethod
    async def _mando_gestionable(cls, *, company_id: int, actor_user_id: int, user_id: int) -> dict:
        d = await delegada.delegacion(company_id=company_id, actor_user_id=actor_user_id)
        await delegada.exigir_objetivo(d, company_id=company_id, user_id=user_id)
        stmt = cls._consulta_mandos(company_id=company_id, user_ids=None, q=None)
        async with db_session() as session:
            fila = (await session.execute(stmt.where(Users.id == user_id))).first()
        if fila is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found for this company")
        return await cls._mando(fila, company_id=company_id)

    @classmethod
    async def update_strategic_recipient(
        cls,
        *,
        company_id: int,
        actor_user_id: int,
        user_id: int,
        strategic_midday_enabled: bool | None,
        strategic_end_of_day_enabled: bool | None,
        version: int,
    ) -> dict:
        if strategic_midday_enabled is None and strategic_end_of_day_enabled is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes to apply")
        actual = await cls._mando_gestionable(company_id=company_id, actor_user_id=actor_user_id, user_id=user_id)
        if (strategic_midday_enabled or strategic_end_of_day_enabled) and not actual["eligible"]:
            motivo = {
                "inactive": "This manager is not active in this company.",
                "invalid_email": "This manager has no valid email address. Correct it in Users first.",
                "no_team": "This manager has nobody in their branch to report on.",
            }[actual["ineligible_reason"]]
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=motivo)
        await cls._guardar_preferencias(
            company_id=company_id,
            actor_user_id=actor_user_id,
            user_id=user_id,
            cambios={
                "strategic_midday_enabled": strategic_midday_enabled,
                "strategic_end_of_day_enabled": strategic_end_of_day_enabled,
            },
            version=version,
        )
        return await cls._mando_gestionable(company_id=company_id, actor_user_id=actor_user_id, user_id=user_id)
