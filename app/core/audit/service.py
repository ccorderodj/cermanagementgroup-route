"""
Cómo se registra un evento de auditoría.

Se llama **dentro** de la transacción que hace el cambio:

    async with transaction():
        role = await RolesDAO.update(...)
        await record_event(
            company_id=company.id,
            entity_type="role",
            entity_id=role["id"],
            action="update",
            actor_user_id=user.id,
            changes=diff(before, after),
        )

Así el evento y el cambio se confirman o se deshacen juntos. Registrar fuera de
la transacción produce la peor combinación posible: una traza de algo que al
final no ocurrió, o un cambio del que no queda rastro.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import insert

from app.core.audit.models import AuditEvent
from app.core.db.session import db_session


def _serializable(value: Any) -> Any:
    """Valores que JSONB acepta sin sorpresas.

    `Decimal` y `date` no son serializables por defecto, y son justo los tipos
    de los campos que más interesa auditar: tarifas y fechas.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, dict]:
    """`{"campo": {"old": ..., "new": ...}}` con los campos que cambiaron.

    Solo los que cambiaron: un diff que repite los treinta campos de la ficha
    entera hace ilegible la única línea que importaba.
    """
    changes: dict[str, dict] = {}
    for field, new_value in after.items():
        old_value = before.get(field)
        if old_value == new_value:
            continue
        changes[field] = {
            "old": _serializable(old_value),
            "new": _serializable(new_value),
        }
    return changes


def _request_id() -> str | None:
    try:
        from asgi_correlation_id import correlation_id
    except ImportError:  # pragma: no cover - la dependencia está en pyproject
        return None
    valor = correlation_id.get()
    return valor[:64] if valor else None


async def _actor_role(session, *, company_id: int, actor_user_id: int | None) -> str | None:
    """El rol con el que actuó, congelado en el evento."""
    if actor_user_id is None:
        return None
    from sqlalchemy import select

    from app.routers_api.companies.models import UserCompany
    from app.routers_api.roles.models import Role

    return await session.scalar(
        select(Role.name)
        .join(UserCompany, UserCompany.role_id == Role.id)
        .where(UserCompany.user_id == actor_user_id, UserCompany.company_id == company_id)
        .limit(1)
    )


async def record_event(
    *,
    company_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    actor_user_id: int | None = None,
    summary: str | None = None,
    changes: Mapping[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    """Deja el evento con el contexto de la petición (fase 12, WP-9).

    `request_id`, IP y user agent salen del middleware; el rol, de la pertenencia
    del actor a esta compañía. Nadie los pasa a mano, así que ningún llamador
    puede olvidarlos ni inventarlos. Fuera de una petición —un job— quedan nulos.
    """
    from app.core.audit.context import current_request_context

    contexto = current_request_context()
    async with db_session() as session:
        rol = await _actor_role(session, company_id=company_id, actor_user_id=actor_user_id)
        await session.execute(
            insert(AuditEvent).values(
                company_id=company_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                summary=summary,
                changes=dict(changes) if changes else None,
                request_id=_request_id(),
                actor_role=rol[:60] if rol else None,
                ip_address=contexto.ip_address if contexto else None,
                user_agent=contexto.user_agent if contexto else None,
                reason=reason[:500] if reason else None,
            )
        )
        await session.commit()
