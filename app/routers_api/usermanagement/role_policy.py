"""
Qué roles puede conceder quien administra usuarios de CER Route (A02, FR-05).

El problema que cierra
----------------------
El diagnóstico A01 lo midió contra la API: un usuario con solo los permisos de
`route_admin` podía crear una cuenta con el rol `owner`, ponerle la contraseña,
entrar con ella y borrar un rol — algo que su propio rol le niega, y que el
catálogo retira incluso al `admin`. Tres llamadas y control total del tenant.

Lo único que se comprobaba al entrar era que el rol **perteneciera a la
compañía**. Nada comprobaba si quien llamaba podía concederlo.

Por qué esta regla y no la que se propuso antes
------------------------------------------------
El diagnóstico A01 propuso "nadie concede autoridad que no tenga". CER la
descartó, y con razón: el Administrador tiene que poder crear un Supervisor, y
los dos roles tienen capacidades **distintas a propósito** —el Supervisor no
administra nada—, así que aquella regla habría bloqueado el caso normal.

La regla aprobada es más simple y más estrecha: **quien administra usuarios
desde CER Route sólo concede roles de CER Route.** No depende de comparar
capacidades, no necesita jerarquía, y no cambia nada para quien administra desde
el núcleo.

Alcance deliberadamente estrecho
---------------------------------
Se aplica cuando **quien llama** tiene un rol de producto de Route. Un `owner` o
un `admin` del núcleo siguen administrando como siempre: esta resolución cierra
la superficie de CER Route y pide reportar aparte lo que quede expuesto en el
núcleo. `manager` tiene `users.create` y `users.update` y está en la misma
situación que estaba `route_admin`; eso es exposición **del núcleo**, se reporta
y no se toca aquí (§103 de la resolución).

El servidor es la autoridad. Que la pantalla ofrezca dos opciones es experiencia
de usuario; lo que impide la escalada es esto.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.db.session import db_session
from app.core.rbac.catalog import ROUTE_PRODUCT_ROLES
from app.routers_api.companies.models import UserCompany
from app.routers_api.roles.models import Role


async def _nombre_del_rol(*, role_id: int, company_id: int) -> str | None:
    async with db_session() as session:
        return await session.scalar(
            select(Role.name).where(
                Role.id == role_id, Role.company_id == company_id
            )
        )


async def _rol_de_quien_llama(*, user_id: int, company_id: int) -> str | None:
    """El rol del actor **en esta compañía**. `None` si no es miembro activo."""
    async with db_session() as session:
        return await session.scalar(
            select(Role.name)
            .join(UserCompany, UserCompany.role_id == Role.id)
            .where(
                UserCompany.user_id == user_id,
                UserCompany.company_id == company_id,
                UserCompany.is_active.is_(True),
            )
        )


async def ensure_assignable_role(
    *,
    actor_user_id: int,
    actor_is_superuser: bool,
    company_id: int,
    role_id: int | None,
) -> None:
    """403 si quien administra desde Route intenta conceder un rol del núcleo.

    No sustituye a la comprobación de que el rol sea de la compañía —ésa sigue
    en el DAO y responde 404 sin confirmar existencia—, la precede: primero si
    **puede** conceder ese rol, después si el rol existe aquí.

    `role_id` puede venir vacío en una actualización que no cambia el rol; en ese
    caso no hay nada que autorizar.
    """
    if role_id is None:
        return

    # El administrador de plataforma está por encima de cualquier tenant (D6) y
    # no administra "desde CER Route": su autoridad es de otra naturaleza.
    if actor_is_superuser:
        return

    rol_del_actor = await _rol_de_quien_llama(
        user_id=actor_user_id, company_id=company_id
    )
    if rol_del_actor not in ROUTE_PRODUCT_ROLES:
        # Quien administra desde el núcleo sigue como estaba. Lo que el núcleo
        # permita o no es una cuestión aparte, reportada y fuera de este alcance.
        return

    objetivo = await _nombre_del_rol(role_id=role_id, company_id=company_id)
    if objetivo is None:
        # Un rol que no es de esta compañía. Se deja al DAO, que responde 404 sin
        # confirmar si existe en otro sitio.
        return

    if objetivo in ROUTE_PRODUCT_ROLES:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CER Route users can only be assigned a CER Route role.",
    )
