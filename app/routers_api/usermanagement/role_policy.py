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

Dos condiciones, y hacen falta las dos
---------------------------------------
Se acota la asignación cuando se cumple **cualquiera** de estas:

1. **El contexto es CER Route** — la petición entró por `/api/route/users`. Da
   igual quién llame: un Superadmin usando una pantalla de CER Route sólo puede
   conceder lo que CER Route ofrece (PD-02, el añadido de FC1).
2. **El actor es de CER Route** — su rol en esta compañía es `route_admin` o
   `supervisor`. Da igual por dónde llame (A02, y **no se puede quitar**).

La segunda parecía sobrar al llegar PD-02, y quitarla reabrió la escalada al
instante: un `route_admin` tiene `users.create`, así que llamando a `/api/users`
—el contrato del núcleo— volvía a poder crear un `owner`. Se midió contra la API
y devolvía 200. El contexto cierra la pantalla; el actor cierra la puerta de
atrás. Hacen falta las dos.

Quien administra desde el núcleo por el contrato del núcleo sigue exactamente
como estaba, que es lo que la resolución pide expresamente.

Lo que queda fuera, y se reporta
---------------------------------
`manager` tiene `users.create` y `users.update` en el núcleo y puede conceder
`owner` por el contrato del núcleo. Es exposición **del núcleo**, explícitamente
fuera de alcance en esta resolución, y sigue documentada como hueco aparte.

El servidor es la autoridad. Que la pantalla ofrezca dos opciones es experiencia
de usuario; lo que impide la escalada es esto.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.db.session import db_session
from app.core.rbac.catalog import ROUTE_PRODUCT_ROLES
from app.routers_api.usermanagement.product_context import es_contexto_de_route
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


async def acota_a_roles_de_route(*, actor_user_id: int, company_id: int) -> bool:
    """Si esta petición queda limitada a los dos roles de producto de CER Route.

    Una sola función para las dos caras del contrato —qué se ofrece y qué se
    acepta—, porque ofrecer una opción que el servidor después rechaza es peor
    que no ofrecerla.
    """
    if es_contexto_de_route():
        return True

    rol_del_actor = await _rol_de_quien_llama(
        user_id=actor_user_id, company_id=company_id
    )
    return rol_del_actor in ROUTE_PRODUCT_ROLES


async def ensure_assignable_role(
    *, actor_user_id: int, company_id: int, role_id: int | None
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

    # El administrador de plataforma **no** queda exento por el contexto, y es el
    # cambio central de FC1. Su autoridad es real y sigue intacta en el contrato
    # del núcleo; lo que no puede es usar una pantalla de CER Route para conceder
    # un rol que CER Route no ofrece.
    if not await acota_a_roles_de_route(
        actor_user_id=actor_user_id, company_id=company_id
    ):
        # Actor del núcleo por el contrato del núcleo: sigue como estaba. Lo que
        # el núcleo permita es una cuestión aparte, reportada y fuera de alcance.
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
