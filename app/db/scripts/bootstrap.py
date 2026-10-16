"""
Siembra y reconciliación de una aplicación CER.

Crea lo mínimo para poder entrar al sistema y, cada vez que se ejecuta, deja el
catálogo de capacidades alineado con `app/core/rbac/catalog.py`.

Es IDEMPOTENTE. Lo que ya existe se respeta; solo se añade lo que falta y se
desactiva lo que el catálogo ya no reconoce.

    .venv/Scripts/python.exe -m app.db.scripts.bootstrap

La compañía y el administrador inicial salen del entorno (valores por defecto
entre paréntesis):

    BOOTSTRAP_COMPANY_NAME        (CER Management Group LLC)
    BOOTSTRAP_COMPANY_SUBDOMAIN   (cer)
    BOOTSTRAP_ADMIN_EMAIL         (admin@example.com)
    BOOTSTRAP_ADMIN_USERNAME      (admin)
    BOOTSTRAP_STATES              (GA)       estados de operación, separados por comas
    BOOTSTRAP_MAIN_STATE          (el primero de BOOTSTRAP_STATES)
    ADMIN_PASSWORD                (se genera y se muestra una sola vez)

Qué NO hace, a propósito
------------------------
No reescribe las capacidades de un rol que ya existe. Los permisos de un rol se
cambian por el flujo de aprobación (maker-checker), y un script que los
sobreescribiera al ejecutarse anularía ese control sin que nadie lo revisara.
Solo **añade** las que el rol debería tener por plantilla y le faltan.
"""

import asyncio
import os
import secrets
import string

from dotenv import load_dotenv

# Las variables BOOTSTRAP_* y ADMIN_PASSWORD se leen de `os.environ` al
# importar este módulo. `Settings` carga `.env` por su cuenta, pero sólo para
# sus propios campos: sin esto, lo declarado en `.env` se ignoraría en silencio.
load_dotenv()

from sqlalchemy import select, update

from app.core.db.session import transaction
from app.core.rbac.catalog import (
    CAPABILITIES,
    CAPABILITY_NAMES,
    DEFAULT_ROLES,
    capabilities_for,
)
from app.routers_api.companies.models import Company, CompanyState, UserCompany
from app.routers_api.permissions.models import Permission
from app.routers_api.regions.models import Region
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from app.routers_api.standardvalues.provisioning import provision_standard_values
from app.routers_api.users.auth import get_password_hash
from app.routers_api.users.models import Users


# ── Compañía ────────────────────────────────────────────────────────────────
# El subdominio es obligatorio: `CompanyResolverMiddleware` resuelve la compañía
# a partir de `<subdominio>.<BASE_DOMAIN>`. En desarrollo, con
# BASE_DOMAIN=localhost, la app se abre en http://cer.localhost:8000
_SUBDOMINIO = os.environ.get("BOOTSTRAP_COMPANY_SUBDOMAIN", "cer").strip().lower()
COMPANY = {
    "name": os.environ.get("BOOTSTRAP_COMPANY_NAME", "CER Management Group LLC"),
    "subdomain": _SUBDOMINIO,
    "domain": f"{_SUBDOMINIO}.localhost",
    "email": os.environ.get("BOOTSTRAP_COMPANY_EMAIL") or None,
    "website": os.environ.get("BOOTSTRAP_COMPANY_WEBSITE") or None,
    # Paleta de marca tomada de los mockups del propio CER.
    "brand_primary_color": "#003b5c",
    "brand_secondary_color": "#30c3e5",
    "pdf_text_color": "#1e2d3d",
    "pdf_muted_text_color": "#6e7b86",
    "pdf_surface_color": "#f4f7f9",
}

# ── Estados ─────────────────────────────────────────────────────────────────
# `region` es el catálogo (los 50 estados + DC). `company_state` dice en cuáles
# opera este tenant, y cuál es la sede principal.
US_STATES: list[tuple[str, str]] = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"),
    ("DE", "Delaware"), ("DC", "District of Columbia"), ("FL", "Florida"),
    ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"),
    ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"), ("KY", "Kentucky"),
    ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"),
    ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"),
    ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"), ("SC", "South Carolina"), ("SD", "South Dakota"),
    ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

# Estados donde opera el tenant inicial. El principal, si no se indica, es el primero.
CER_STATES = [
    c.strip().upper() for c in os.environ.get("BOOTSTRAP_STATES", "GA").split(",") if c.strip()
]
CER_MAIN_STATE = (os.environ.get("BOOTSTRAP_MAIN_STATE") or CER_STATES[0]).strip().upper()

ADMIN = {
    "email": os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com").strip().lower(),
    "username": os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin").strip(),
    "first_name": "Application",
    "last_name": "Administrator",
}

# El rol que recibe el administrador inicial de la compañía.
ADMIN_ROLE = "owner"


def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def seed_company(session) -> Company:
    company = await session.scalar(
        select(Company).where(Company.subdomain == COMPANY["subdomain"])
    )

    if company:
        print(f"  = compañía '{company.name}' ya existía (id={company.id})")
        return company

    company = Company(**COMPANY)
    session.add(company)
    await session.flush()
    print(f"  + compañía '{company.name}' creada (id={company.id})")
    return company


async def seed_states(session, company: Company) -> None:
    """Catálogo de estados + los estados donde opera el tenant."""
    existing = {
        region.code: region
        for region in (await session.execute(select(Region))).scalars().all()
    }

    created = 0
    for code, name in US_STATES:
        if code in existing:
            continue
        region = Region(code=code, name=name)
        session.add(region)
        existing[code] = region
        created += 1

    await session.flush()
    print(f"  + {created} estados creados en el catálogo ({len(US_STATES)} en total)")

    linked = {
        row.state_id: row
        for row in (
            await session.execute(
                select(CompanyState).where(CompanyState.company_id == company.id)
            )
        )
        .scalars()
        .all()
    }

    added = 0
    for code in CER_STATES:
        region = existing.get(code)
        if region is None:
            continue

        is_main = code == CER_MAIN_STATE
        link = linked.get(region.id)

        if link is None:
            session.add(
                CompanyState(
                    company_id=company.id,
                    state_id=region.id,
                    is_main=is_main,
                )
            )
            added += 1
        elif link.is_main != is_main:
            link.is_main = is_main

    await session.flush()
    print(f"  + {added} estados de operación vinculados a '{company.name}'")
    print(f"      sede principal: {CER_MAIN_STATE}")


async def seed_permissions(session) -> dict[str, Permission]:
    """Alinea la tabla `permission` con el catálogo definido en código.

    Tres acciones, en este orden:
      1. crear las capacidades del catálogo que falten;
      2. actualizar la descripción de las que existan;
      3. **desactivar** —no borrar— las que la tabla tenga y el catálogo ya no
         reconozca. No se borran porque `role_permission` las referencia; al
         quedar inactivas dejan de conceder nada, que es el efecto buscado.
    """
    existing = {
        permission.name: permission
        for permission in (await session.execute(select(Permission))).scalars().all()
    }

    created = 0
    reactivated = 0
    for capability in CAPABILITIES:
        permission = existing.get(capability.name)
        if permission is None:
            permission = Permission(
                name=capability.name,
                description=capability.description,
            )
            session.add(permission)
            existing[capability.name] = permission
            created += 1
            continue

        if permission.description != capability.description:
            permission.description = capability.description
        if not permission.is_active:
            permission.is_active = True
            reactivated += 1

    obsolete = sorted(set(existing) - CAPABILITY_NAMES)
    deactivated = 0
    for name in obsolete:
        permission = existing[name]
        if permission.is_active:
            permission.is_active = False
            deactivated += 1

    await session.flush()

    print(f"  + {created} capacidades creadas ({len(CAPABILITIES)} en el catálogo)")
    if reactivated:
        print(f"  ~ {reactivated} reactivadas")
    if deactivated:
        print(f"  - {deactivated} desactivadas por no estar ya en el catálogo:")
        for name in obsolete:
            print(f"      {name}")

    return existing


async def seed_roles(
    session,
    company: Company,
    permissions: dict[str, Permission],
) -> dict[str, Role]:
    """Roles por defecto de la compañía. Los roles son del tenant (D8)."""
    existing = {
        role.name: role
        for role in (
            await session.execute(select(Role).where(Role.company_id == company.id))
        )
        .scalars()
        .all()
    }

    roles: dict[str, Role] = {}

    for template in DEFAULT_ROLES:
        role = existing.get(template.name)

        if role is None:
            role = Role(
                company_id=company.id,
                name=template.name,
                description=template.description,
                category=template.category,
            )
            session.add(role)
            await session.flush()
            print(f"  + rol '{template.name}' creado (id={role.id})")
        else:
            # La categoría sí se sincroniza: es política de seguridad —decide
            # quién puede aprobar cambios— no un dato que el usuario edite.
            if role.category != template.category:
                role.category = template.category
                print(f"  ~ rol '{template.name}': categoría -> {template.category}")
            else:
                print(f"  = rol '{template.name}' ya existía (id={role.id})")

        roles[template.name] = role

        granted = set(
            (
                await session.execute(
                    select(RolePermission.permission_id).where(
                        RolePermission.role_id == role.id
                    )
                )
            )
            .scalars()
            .all()
        )

        added = 0
        for capability_name in capabilities_for(template):
            permission = permissions.get(capability_name)
            if permission is None or permission.id in granted:
                continue
            session.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    is_active=True,
                )
            )
            added += 1

        if added:
            print(f"      + {added} capacidades añadidas a '{template.name}'")

    await session.flush()
    return roles


async def seed_admin(
    session,
    company: Company,
    role: Role,
    password: str,
) -> tuple[Users, bool]:
    user = await session.scalar(select(Users).where(Users.email == ADMIN["email"]))

    if user is None:
        user = Users(
            **ADMIN,
            password=get_password_hash(password),
            is_superuser=True,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        print(f"  + usuario '{user.email}' creado (id={user.id})")
        created = True
    else:
        print(
            f"  = usuario '{user.email}' ya existía (id={user.id}); "
            "no se toca su contraseña"
        )
        created = False

    membership = await session.scalar(
        select(UserCompany).where(
            UserCompany.user_id == user.id,
            UserCompany.company_id == company.id,
        )
    )
    if membership is None:
        session.add(
            UserCompany(
                user_id=user.id,
                company_id=company.id,
                role_id=role.id,
                is_active=True,
            )
        )
        print(f"      + vinculado a '{company.name}' con rol '{role.name}'")

    await session.flush()
    return user, created


async def main() -> None:
    password = os.environ.get("ADMIN_PASSWORD") or generate_password()

    async with transaction() as session:
        print("Compañía")
        company = await seed_company(session)

        print("Estados")
        await seed_states(session, company)

        print("Capacidades")
        permissions = await seed_permissions(session)

        print("Roles")
        roles = await seed_roles(session, company, permissions)

        print("Listas estandarizadas de Route")
        resultado = await provision_standard_values(session, company_id=company.id)
        print(
            f"  + {resultado.created} valores creados, "
            f"{resultado.skipped} ya existían ({resultado.total} aprobados)"
        )
        if resultado.skipped:
            print(
                "      los existentes no se tocan: un valor renombrado, "
                "desactivado o borrado por el administrador se queda como está"
            )

        print("Administrador")
        _, created = await seed_admin(session, company, roles[ADMIN_ROLE], password)

    print()
    print("=" * 62)
    print("Siembra completada.")
    print(f"  URL      http://{COMPANY['subdomain']}.localhost:8000")
    print(f"  Usuario  {ADMIN['email']}")
    if created:
        print(f"  Clave    {password}")
        print()
        print("  Guarda esta contraseña: no se vuelve a mostrar.")
    else:
        print("  Clave    (sin cambios; el usuario ya existía)")
    print("=" * 62)


if __name__ == "__main__":
    asyncio.run(main())
