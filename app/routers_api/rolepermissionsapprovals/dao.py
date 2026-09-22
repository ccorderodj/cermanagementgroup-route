"""
Acceso a datos de las solicitudes de cambio de capacidades.

`company_id` es obligatorio en la consulta base: el listado de solicitudes es
justo donde un revisor de la compania A veia —y podia resolver— las de la B
(AUD-SEC-007).
"""

from sqlalchemy import Select, select

from app.core.dao.base import BaseDAO
from app.routers_api.rolepermissionsapprovals.models import RolePermissionChangeRequest


class RolePermissionChangeRequestsDAO(BaseDAO):
    model = RolePermissionChangeRequest

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        role_id: int | None = None,
        requested_by_user_id: int | None = None,
        reviewed_by_user_id: int | None = None,
        status: str | None = None,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        model = cls.model
        stmt = select(model).where(model.company_id == company_id)

        if role_id is not None:
            stmt = stmt.where(model.role_id == role_id)
        if requested_by_user_id is not None:
            stmt = stmt.where(model.requested_by_user_id == requested_by_user_id)
        if reviewed_by_user_id is not None:
            stmt = stmt.where(model.reviewed_by_user_id == reviewed_by_user_id)
        if status is not None:
            stmt = stmt.where(model.status == status)
        if is_active is not None:
            stmt = stmt.where(model.is_active.is_(is_active))

        return stmt
