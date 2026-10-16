"""
Retira el grant obsoleto `route_admin -> roles.read` (A02-FC4).

Por qué hace falta un script y no basta el bootstrap
-----------------------------------------------------
El bootstrap **añade y nunca revoca**. Es el comportamiento correcto para algo
que se ejecuta contra tenants con decisiones reales dentro: quitar por su cuenta
lo que un administrador concedió sería destruir trabajo sin avisar. Pero tiene una
consecuencia: una capacidad **retirada del catálogo** sigue concedida en los
tenants que ya la tenían, y la deriva es de un solo sentido.

A02 retiró `roles.read` del Administrador de CER Route —el formulario de usuarios
ya no pide el catálogo de roles del tenant, recibe sus dos opciones de
`/api/users/assignable-roles`— y el grant se quedó en el tenant alineado.

Qué hace, y qué **no**
----------------------
Hace exactamente una cosa: quita `roles.read` del rol `route_admin`, en las
compañías donde siga concedido. Nada más.

* **No** es un motor de revocación genérico. No lee el catálogo ni compara
  plantillas: la capacidad y el rol están escritos aquí, uno de cada.
* **No** toca la fila de `permission`: `roles.read` sigue existiendo y el núcleo
  la sigue usando. Lo que se retira es una concesión, no la capacidad.
* **No** cambia la semántica del bootstrap.
* **No** vuelve a añadir `roles.read` a la plantilla.

Es idempotente: una segunda ejecución no encuentra nada que quitar y lo dice.

Deja rastro
-----------
Cada revocación se registra en `audit_event` con el mismo mecanismo que el resto
del sistema. Quitar una autorización sin dejar constancia sería justo el tipo de
cambio silencioso que la auditoría existe para impedir.

    uv run python -m app.db.scripts.cleanup_route_admin_roles_read
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from app.core.audit.service import record_event
from app.core.db.session import transaction
from app.database import async_session_maker
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role


#: Lo único que este script retira. Escrito, no derivado.
ROL = "route_admin"
CAPACIDAD = "roles.read"


async def _concesiones_obsoletas() -> list[tuple[int, int, int]]:
    """`(company_id, role_id, permission_id)` de cada concesión que sobra."""
    async with async_session_maker() as session:
        filas = await session.execute(
            select(Role.company_id, Role.id, Permission.id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Role.name == ROL, Permission.name == CAPACIDAD)
        )
        return [tuple(f) for f in filas.all()]


async def main() -> None:
    print(f"Limpieza de '{ROL} -> {CAPACIDAD}'")

    obsoletas = await _concesiones_obsoletas()
    if not obsoletas:
        print(f"  = nada que hacer: '{CAPACIDAD}' ya no está concedida a '{ROL}'")
        return

    for company_id, role_id, permission_id in obsoletas:
        async with transaction() as session:
            await session.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission_id,
                )
            )

        await record_event(
            company_id=company_id,
            entity_type="role_permission",
            entity_id=role_id,
            action="revoke",
            # Sin actor: no lo pidió una persona desde una pantalla, lo ejecutó
            # una limpieza aprobada. Registrarlo a nombre de alguien sería
            # atribuirle una decisión que no tomó.
            actor_user_id=None,
            summary=(
                f"Obsolete grant '{CAPACIDAD}' revoked from '{ROL}' "
                "(RTE02-A02 FC4: the Route user form no longer reads the role catalog)"
            ),
            changes={CAPACIDAD: {"old": "granted", "new": None}},
        )
        print(f"  - compañía {company_id}: retirada de '{ROL}' (rol {role_id})")

    print(f"\nListo. {len(obsoletas)} concesión(es) retirada(s).")


if __name__ == "__main__":
    asyncio.run(main())
