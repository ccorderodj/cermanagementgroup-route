"""
Alinea las capacidades de los roles por defecto en **todas** las compañías.

El hueco que cierra
--------------------
`bootstrap` hace dos cosas que parecen la misma y no lo son:

* `seed_permissions` alinea la tabla `permission`, que es **global**: una
  capacidad nueva del catálogo aparece para toda la instalación;
* `seed_roles` alinea las **concesiones**, pero sólo de la compañía que nombra
  `BOOTSTRAP_COMPANY_SUBDOMAIN`.

Así que una capacidad introducida después de que un tenant existiera llegaba al
catálogo y no a su rol. El tenant se quedaba con las concesiones que tenía el
día que se creó, y no había camino soportado para corregirlo: sólo editar la
base a mano, que es justo lo que un producto no puede pedir.

Eso es lo que le pasó a `route.live.read` con RTE07 —el Administrador dejó de
ver Today / Live— y le habría pasado igual a `route.activity.read` con RTE08, y
a la siguiente. Por eso esto no arregla una capacidad: arregla el camino.

Qué hace, y qué **no**
----------------------
Hace dos cosas, en este orden:

1. alinea la tabla de capacidades con el catálogo del código (reutilizando el
   mismo paso del bootstrap, no una copia);
2. en **cada compañía**, concede a cada rol por defecto las capacidades de su
   plantilla que le falten.

* **No revoca nunca.** Es la misma semántica del bootstrap y por la misma
  razón: un tenant tiene decisiones reales dentro, y quitar por su cuenta lo
  que un administrador concedió sería destruir trabajo sin avisar. Retirar una
  capacidad obsoleta sigue siendo un script explícito y escrito, como
  `cleanup_route_admin_roles_read`.
* **No crea roles.** Si una compañía no tiene un rol de la plantilla, se
  informa y no se inventa: un rol nuevo aparece en la pantalla de permisos de
  ese tenant, y eso es una decisión suya, no el efecto lateral de un
  alineamiento.
* **No toca usuarios ni asignaciones.** Quién tiene qué rol no es asunto de
  este script.
* **No cambia la semántica de los roles del núcleo.** Aplica las plantillas tal
  como están declaradas; no mueve capacidades entre roles.

Es idempotente: una segunda ejecución no encuentra nada que añadir y lo dice.

Deja rastro
-----------
Cada concesión se registra en `audit_event`, con el mismo mecanismo que el
resto del sistema. Conceder autorización sin dejar constancia sería el tipo de
cambio silencioso que la auditoría existe para impedir.

    uv run python -m app.db.scripts.align_role_capabilities
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.audit.service import record_event
from app.core.db.session import transaction
from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for
from app.database import async_session_maker
from app.routers_api.companies.models import Company
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role


@dataclass
class Resumen:
    """Lo que la ejecución hizo, para que el reporte no sea una impresión."""

    companias: int = 0
    concesiones_anadidas: int = 0
    #: `(subdominio, rol)` de los roles de plantilla que una compañía no tiene.
    #: Se informan; no se crean.
    roles_ausentes: list[tuple[str, str]] = field(default_factory=list)
    #: `(subdominio, rol, capacidad)` de cada concesión añadida.
    detalle: list[tuple[str, str, str]] = field(default_factory=list)


async def alinear(*, verbose: bool = False) -> Resumen:
    """Concede a cada rol por defecto lo que su plantilla declara y le falta."""
    from app.db.scripts.bootstrap import seed_permissions

    # 1. La tabla de capacidades, con el catálogo del código. Es el mismo paso
    #    del bootstrap y se reutiliza en vez de copiarse: dos implementaciones
    #    de la misma alineación acabarían diciendo cosas distintas.
    async with transaction() as session:
        capacidades = await seed_permissions(session)

    resumen = Resumen()

    async with async_session_maker() as session:
        companias = (
            (await session.execute(select(Company).order_by(Company.id)))
            .scalars()
            .all()
        )
        companias = [(c.id, c.subdomain) for c in companias]

    for company_id, subdominio in companias:
        resumen.companias += 1

        async with async_session_maker() as session:
            roles = {
                rol.name: rol.id
                for rol in (
                    await session.execute(
                        select(Role).where(Role.company_id == company_id)
                    )
                )
                .scalars()
                .all()
            }

        for plantilla in DEFAULT_ROLES:
            role_id = roles.get(plantilla.name)
            if role_id is None:
                resumen.roles_ausentes.append((subdominio, plantilla.name))
                continue

            async with async_session_maker() as session:
                concedidas = set(
                    (
                        await session.execute(
                            select(RolePermission.permission_id).where(
                                RolePermission.role_id == role_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

            faltantes: list[tuple[str, int]] = []
            for nombre in capabilities_for(plantilla):
                capacidad = capacidades.get(nombre)
                if capacidad is None or capacidad.id in concedidas:
                    continue
                faltantes.append((nombre, capacidad.id))

            if not faltantes:
                continue

            async with transaction() as session:
                for _, permission_id in faltantes:
                    session.add(
                        RolePermission(
                            role_id=role_id,
                            permission_id=permission_id,
                            is_active=True,
                        )
                    )

            await record_event(
                company_id=company_id,
                entity_type="role_permission",
                entity_id=role_id,
                action="grant",
                # Sin actor: no lo pidió una persona desde una pantalla, lo
                # ejecutó un alineamiento aprobado. Registrarlo a nombre de
                # alguien sería atribuirle una decisión que no tomó.
                actor_user_id=None,
                summary=(
                    f"{len(faltantes)} capability grant(s) aligned to role "
                    f"'{plantilla.name}' from the code catalog"
                ),
                changes={
                    nombre: {"old": None, "new": "granted"} for nombre, _ in faltantes
                },
            )

            resumen.concesiones_anadidas += len(faltantes)
            for nombre, _ in faltantes:
                resumen.detalle.append((subdominio, plantilla.name, nombre))
                if verbose:
                    print(f"  + {subdominio} · {plantilla.name} -> {nombre}")

    return resumen


async def main() -> None:
    print("Alineación de capacidades de los roles por defecto")
    resumen = await alinear(verbose=True)

    print(f"\n  compañías revisadas      : {resumen.companias}")
    print(f"  concesiones añadidas     : {resumen.concesiones_anadidas}")

    if resumen.roles_ausentes:
        print("\n  roles de plantilla que alguna compañía no tiene:")
        for subdominio, rol in resumen.roles_ausentes:
            print(f"    · {subdominio}: '{rol}' (no se crea; es decisión del tenant)")

    if not resumen.concesiones_anadidas:
        print("\n  = nada que añadir: todo estaba alineado.")


if __name__ == "__main__":
    asyncio.run(main())
