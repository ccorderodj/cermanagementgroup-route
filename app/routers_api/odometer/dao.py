"""Acceso a datos de la evidencia de odómetro. Siempre acotado por compañía."""

from __future__ import annotations

from sqlalchemy import Select, select

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.odometer.models import (
    OdometerEvidence,
    OdometerExceptionRequest,
    OdometerExceptionStatus,
)


class OdometerEvidenceDAO(BaseDAO):
    model = OdometerEvidence

    @classmethod
    def query(
        cls, *, company_id: int, work_session_id: int | None = None, **_: object
    ) -> Select:
        stmt = select(OdometerEvidence).where(
            OdometerEvidence.company_id == company_id
        )
        if work_session_id is not None:
            stmt = stmt.where(OdometerEvidence.work_session_id == work_session_id)
        return stmt

    @classmethod
    def default_order(cls):
        return OdometerEvidence.evidence_type.asc()

    @classmethod
    async def find(
        cls, *, company_id: int, work_session_id: int, evidence_type: str
    ) -> OdometerEvidence | None:
        async with db_session() as session:
            return await session.scalar(
                select(OdometerEvidence).where(
                    OdometerEvidence.company_id == company_id,
                    OdometerEvidence.work_session_id == work_session_id,
                    OdometerEvidence.evidence_type == evidence_type,
                )
            )

    @classmethod
    async def get_for_owner(
        cls, *, evidence_id: int, company_id: int, user_id: int
    ) -> OdometerEvidence | None:
        """La evidencia, sólo si cuelga de una jornada de quien llama.

        Es la comprobación que protege la foto: la propiedad se resuelve contra
        `work_session`, y un identificador de otro supervisor o de otro tenant
        devuelve `None` — la respuesta no distingue cuál de los dos casos es.
        """
        from app.routers_api.worksessions.models import WorkSession

        async with db_session() as session:
            return await session.scalar(
                select(OdometerEvidence)
                .join(
                    WorkSession,
                    (WorkSession.id == OdometerEvidence.work_session_id)
                    & (WorkSession.company_id == OdometerEvidence.company_id),
                )
                .where(
                    OdometerEvidence.id == evidence_id,
                    OdometerEvidence.company_id == company_id,
                    WorkSession.user_id == user_id,
                )
            )


class OdometerExceptionRequestsDAO(BaseDAO):
    model = OdometerExceptionRequest

    @classmethod
    def query(cls, *, company_id: int, status: str | None = None, **_: object) -> Select:
        stmt = select(OdometerExceptionRequest).where(
            OdometerExceptionRequest.company_id == company_id
        )
        if status:
            stmt = stmt.where(OdometerExceptionRequest.status == status)
        return stmt

    @classmethod
    def default_order(cls):
        return OdometerExceptionRequest.requested_at.asc()

    @classmethod
    async def get_for_company(
        cls, *, request_id: int, company_id: int
    ) -> OdometerExceptionRequest | None:
        async with db_session() as session:
            return await session.scalar(
                select(OdometerExceptionRequest).where(
                    OdometerExceptionRequest.id == request_id,
                    OdometerExceptionRequest.company_id == company_id,
                )
            )

    @classmethod
    async def find_open(
        cls, *, company_id: int, work_session_id: int, evidence_type: str
    ) -> OdometerExceptionRequest | None:
        """La solicitud viva —pedida o aprobada— de ese extremo, si la hay."""
        async with db_session() as session:
            return await session.scalar(
                select(OdometerExceptionRequest).where(
                    OdometerExceptionRequest.company_id == company_id,
                    OdometerExceptionRequest.work_session_id == work_session_id,
                    OdometerExceptionRequest.evidence_type == evidence_type,
                    OdometerExceptionRequest.status.in_(
                        (
                            OdometerExceptionStatus.REQUESTED.value,
                            OdometerExceptionStatus.APPROVED.value,
                        )
                    ),
                )
            )

    @classmethod
    async def find_approved(
        cls, *, company_id: int, work_session_id: int, evidence_type: str
    ) -> OdometerExceptionRequest | None:
        """La autorización **aún sin consumir** de ese extremo.

        Exige coincidencia exacta de jornada y extremo: una aprobación de
        inicio no autoriza el cierre, y la de un día no sirve para otro. El
        alcance está en las columnas, no en la confianza.
        """
        async with db_session() as session:
            return await session.scalar(
                select(OdometerExceptionRequest).where(
                    OdometerExceptionRequest.company_id == company_id,
                    OdometerExceptionRequest.work_session_id == work_session_id,
                    OdometerExceptionRequest.evidence_type == evidence_type,
                    OdometerExceptionRequest.status
                    == OdometerExceptionStatus.APPROVED.value,
                )
            )

    @classmethod
    async def list_pending(cls, *, company_id: int) -> list[OdometerExceptionRequest]:
        """La cola del administrador: lo que espera decisión, lo más viejo primero."""
        async with db_session() as session:
            filas = await session.execute(
                select(OdometerExceptionRequest)
                .where(
                    OdometerExceptionRequest.company_id == company_id,
                    OdometerExceptionRequest.status
                    == OdometerExceptionStatus.REQUESTED.value,
                )
                .order_by(OdometerExceptionRequest.requested_at.asc())
            )
            return list(filas.scalars().all())
