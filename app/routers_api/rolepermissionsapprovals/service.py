"""
Flujo de aprobación de cambios de capacidades (maker-checker).

Reglas:
  1. Enviar un cambio **no lo aplica**: crea una solicitud pendiente. Ni las
     capacidades que se conceden ni las que se revocan tocan `role_permission`
     hasta la aprobación.
  2. Quien solicita **no puede aprobar** lo suyo.
  3. Solo puede aprobar quien tiene autoridad: un administrador de plataforma, o
     alguien cuyo rol en la compañía sea de categoría `management`.
  4. Un rol tiene como mucho una solicitud pendiente a la vez. Ahora lo impone
     un índice único parcial en la base, no una comprobación previa que dos
     peticiones simultáneas podían esquivar (AUD-BE-029).
  5. **Todo está acotado a una compañía.** `role_id` sin `company_id` permitía
     que un revisor de la compañía A resolviera por id una solicitud de la B
     (AUD-SEC-007). Las firmas ya no dejan hacer esa llamada.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.core.db.session import db_session, transaction
from app.routers_api.companies.models import UserCompany
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.rolepermissionsapprovals.models import (
    ChangeRequestStatus,
    RolePermissionChangeRequest,
)
from app.routers_api.roles.models import Role, RoleCategory
from app.routers_api.users.models import Users


class RolePermissionApprovalService:

    # ── Consultas ───────────────────────────────────────────────────────────

    @staticmethod
    async def _granted_permission_ids(session, role_id: int) -> set[int]:
        result = await session.execute(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role_id,
                RolePermission.is_active.is_(True),
            )
        )
        return set(result.scalars().all())

    @classmethod
    async def pending_for_role(
        cls,
        *,
        role_id: int,
        company_id: int,
    ) -> RolePermissionChangeRequest | None:
        async with db_session() as session:
            return await session.scalar(
                select(RolePermissionChangeRequest).where(
                    RolePermissionChangeRequest.role_id == role_id,
                    RolePermissionChangeRequest.company_id == company_id,
                    RolePermissionChangeRequest.status == ChangeRequestStatus.PENDING,
                )
            )

    @classmethod
    async def diff_for_request(cls, request: RolePermissionChangeRequest) -> dict:
        """Qué concede y qué revoca esta solicitud, contra el estado actual.

        Se calcula al mirarla, no al crearla: lo que importa al revisar es el
        efecto sobre las capacidades que el rol tiene **ahora**.
        """
        async with db_session() as session:
            current = await cls._granted_permission_ids(session, request.role_id)
            wanted = set(request.requested_permission_ids or [])

            to_grant = wanted - current
            to_revoke = current - wanted

            names: dict[int, str] = {}
            if to_grant or to_revoke:
                rows = await session.execute(
                    select(Permission.id, Permission.name).where(
                        Permission.id.in_(to_grant | to_revoke)
                    )
                )
                names = {pid: name for pid, name in rows.all()}

            return {
                "to_grant": sorted(names.get(pid, str(pid)) for pid in to_grant),
                "to_revoke": sorted(names.get(pid, str(pid)) for pid in to_revoke),
            }

    @classmethod
    async def can_review(cls, *, user_id: int, company_id: int) -> bool:
        """Si este usuario tiene autoridad para revisar cambios de capacidades."""
        async with db_session() as session:
            user = await session.get(Users, user_id)
            if user is not None and user.is_superuser:
                return True

            category = await session.scalar(
                select(Role.category)
                .join(UserCompany, UserCompany.role_id == Role.id)
                .where(
                    UserCompany.user_id == user_id,
                    UserCompany.company_id == company_id,
                    UserCompany.is_active.is_(True),
                    Role.company_id == company_id,
                    Role.is_active.is_(True),
                    Role.category == RoleCategory.MANAGEMENT,
                )
                .limit(1)
            )
            return category is not None

    @classmethod
    async def _require_review_authority(cls, *, user_id: int, company_id: int) -> None:
        if not await cls.can_review(user_id=user_id, company_id=company_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only management roles can review permission changes. "
                    "Your role is operative."
                ),
            )

    @staticmethod
    async def _get_scoped_request(session, *, request_id: int, company_id: int):
        """La solicitud, solo si es de esta compañía.

        404 y no 403: una solicitud de otro tenant no debe ni confirmarse que
        exista.
        """
        request = await session.scalar(
            select(RolePermissionChangeRequest).where(
                RolePermissionChangeRequest.id == request_id,
                RolePermissionChangeRequest.company_id == company_id,
            )
        )
        if request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Request not found",
            )
        return request

    # ── Comandos ────────────────────────────────────────────────────────────

    @classmethod
    async def submit(
        cls,
        *,
        role_id: int,
        company_id: int,
        permission_ids: list[int],
        requested_by_user_id: int,
    ) -> RolePermissionChangeRequest:
        normalized = sorted(dict.fromkeys(permission_ids))

        async with transaction() as session:
            role = await session.scalar(
                select(Role).where(Role.id == role_id, Role.company_id == company_id)
            )
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Role not found",
                )

            if normalized:
                found = set(
                    (
                        await session.execute(
                            select(Permission.id).where(Permission.id.in_(normalized))
                        )
                    )
                    .scalars()
                    .all()
                )
                missing = [pid for pid in normalized if pid not in found]
                if missing:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Permissions not found: {missing}",
                    )

            current = await cls._granted_permission_ids(session, role_id)
            if current == set(normalized):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No changes to submit",
                )

            request = RolePermissionChangeRequest(
                role_id=role_id,
                company_id=company_id,
                requested_by_user_id=requested_by_user_id,
                requested_permission_ids=normalized,
                status=ChangeRequestStatus.PENDING,
                is_active=True,
            )
            session.add(request)

            try:
                await session.flush()
            except IntegrityError as exc:
                # Lo impone `uq_change_request_one_pending_per_role`.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This role already has a pending permission change. "
                        "It must be reviewed before submitting another one."
                    ),
                ) from exc

            await session.refresh(request)
            return request

    @classmethod
    async def approve(
        cls,
        *,
        request_id: int,
        reviewer_user_id: int,
        company_id: int,
    ) -> RolePermissionChangeRequest:
        await cls._require_review_authority(
            user_id=reviewer_user_id,
            company_id=company_id,
        )

        async with transaction() as session:
            request = await cls._get_scoped_request(
                session,
                request_id=request_id,
                company_id=company_id,
            )

            if request.status != ChangeRequestStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Request is already {request.status}",
                )
            if request.requested_by_user_id == reviewer_user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You cannot approve your own permission change request",
                )

            wanted = sorted(set(request.requested_permission_ids or []))

            # Se reescribe el conjunto entero: borrar todo y volver a insertar
            # lo aprobado deja el rol exactamente como pedía la solicitud, sin
            # depender de filas heredadas.
            await session.execute(
                RolePermission.__table__.delete().where(
                    RolePermission.role_id == request.role_id
                )
            )
            for permission_id in wanted:
                await session.execute(
                    RolePermission.__table__.insert().values(
                        role_id=request.role_id,
                        permission_id=permission_id,
                        is_active=True,
                    )
                )

            request.status = ChangeRequestStatus.APPROVED
            request.reviewed_by_user_id = reviewer_user_id
            request.is_active = False
            session.add(request)

            await session.flush()
            await session.refresh(request)
            return request

    @classmethod
    async def reject(
        cls,
        *,
        request_id: int,
        reviewer_user_id: int,
        company_id: int,
        note: str | None = None,
    ) -> RolePermissionChangeRequest:
        await cls._require_review_authority(
            user_id=reviewer_user_id,
            company_id=company_id,
        )

        async with transaction() as session:
            request = await cls._get_scoped_request(
                session,
                request_id=request_id,
                company_id=company_id,
            )

            if request.status != ChangeRequestStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Request is already {request.status}",
                )
            if request.requested_by_user_id == reviewer_user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You cannot reject your own permission change request",
                )

            request.status = ChangeRequestStatus.REJECTED
            request.reviewed_by_user_id = reviewer_user_id
            request.review_note = note
            request.is_active = False
            session.add(request)

            await session.flush()
            await session.refresh(request)
            return request
