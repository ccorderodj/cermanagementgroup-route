"""
Catálogo de capacidades del sistema. **Fuente única de verdad.**

Un permiso describe algo que la aplicación sabe hacer, así que lo define el
código, no un administrador: una capacidad inventada desde una pantalla no
tendría ningún endpoint detrás y no haría nada.

Por qué existe este archivo
---------------------------
Antes había dos listas de literales sin relación entre ellas: la del bootstrap
(`MODULE_ACTIONS`) y las 24 llamadas a `require_permissions([...])` repartidas
por los routers. Ya habían divergido: `regions.update` estaba en el código pero
nunca se sembró, así que los dos endpoints que lo exigían devolvían 403 a todo
el mundo salvo a los administradores de plataforma — y nadie lo notó
(AUD-DB-001).

Ahora la lista está aquí, el bootstrap la siembra desde aquí, y un test
comprueba en las dos direcciones que el catálogo y los `require_permissions` del
código dicen exactamente lo mismo.

Alcance
-------
El catálogo es **global**: `users.read` significa lo mismo en todos los tenants.
Lo que es del tenant son los roles, que agrupan capacidades (ver `Role`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    description: str


def _cap(module: str, action: str, description: str) -> Capability:
    return Capability(name=f"{module}.{action}", description=description)


# ── El catálogo ─────────────────────────────────────────────────────────────
# Cada entrada tiene al menos un endpoint que la exige. El test
# `test_permission_catalog.py` falla si se añade una capacidad que nadie usa o
# si un endpoint pide una que no está aquí.
CAPABILITIES: tuple[Capability, ...] = (
    # Organización
    _cap("companies", "read", "View the company profile"),
    _cap("companies", "update", "Edit the company profile"),
    # Ubicaciones
    _cap("regions", "read", "View operating states"),
    _cap("regions", "update", "Edit operating states"),
    # Usuarios del tenant
    _cap("users", "read", "View users of this company"),
    _cap("users", "create", "Add users to this company"),
    _cap("users", "update", "Edit users and suspend their access"),
    # Seguridad
    _cap("roles", "read", "View roles"),
    _cap("roles", "create", "Create roles"),
    _cap("roles", "update", "Edit roles"),
    _cap("roles", "delete", "Deactivate roles"),
    _cap("permissions", "read", "View the capability catalog"),
    _cap("rolepermissions", "read", "View which capabilities each role grants"),
    _cap("rolepermissions", "update", "Request and review changes to role capabilities"),
    _cap("rolepermissionsapprovals", "read", "View pending capability change requests"),
    # La configuración de plataforma **no** está aquí, y es deliberado. Lo que
    # se configura —la base, el almacén, el servidor de correo— es del
    # despliegue y no de una compañía, así que su superficie la protege
    # `require_platform_admin` igual que el listado de tenants, y no una
    # capacidad de tenant. Este catálogo es global en significado pero se
    # concede por rol dentro de una compañía; poner aquí `platform.read`
    # permitiría que el dueño de un tenant leyera el host de correo del
    # despliegue entero.
    # Integraciones entre aplicaciones (ver docs/INTEGRATION_GUIDE.md). Son
    # del tenant: qué contrapartes le envían o reciben eventos de esta compañía.
    _cap("integrations", "read", "View webhook endpoints, subscriptions and delivery history"),
    _cap("integrations", "manage", "Register webhook endpoints and subscriptions, rotate their secrets"),
    # ── CER Route ───────────────────────────────────────────────────────────
    #
    # Solo las capacidades que RTE02 **exige de verdad** en un endpoint. El
    # catálogo certificado de RTE01 contempla además `route.worksession.execute`,
    # `route.live.read`, `route.activity.read`, `route.reports.read`,
    # `route.reports.export`, `route.fuelreference.manage` y
    # `route.records.adjust`: entran con el checkpoint que construya su
    # superficie protegida, porque `test_permission_catalog.py` rechaza —a
    # propósito— una capacidad que ningún endpoint pide. Declararlas antes
    # concedería autoridad sobre algo que todavía no existe.
    _cap("route", "vehicles.read", "View Route vehicles and their assignments"),
    _cap("route", "vehicles.manage", "Create and edit Route vehicles and assign them to supervisors"),
    _cap("route", "standardvalues.manage", "Manage the Route admin-configurable value lists"),
)

CAPABILITY_NAMES: frozenset[str] = frozenset(c.name for c in CAPABILITIES)


# ── Roles por defecto de una compañía nueva ─────────────────────────────────
#
# Se crean POR compañía (D8). El nombre `superadmin` se retiró a propósito:
# se confundía con `Users.is_superuser`, que es privilegio de plataforma y no
# tiene nada que ver con un rol de tenant. El equivalente aquí es `owner`.
#
# `category` decide quién puede APROBAR cambios de permisos: solo los roles de
# dirección/gestión. Los operativos pueden solicitarlos.

ALL_CAPABILITIES = "*"


@dataclass(frozen=True)
class RoleTemplate:
    name: str
    description: str
    category: str
    capabilities: tuple[str, ...] | str


DEFAULT_ROLES: tuple[RoleTemplate, ...] = (
    RoleTemplate(
        name="owner",
        description="Full control of this company, including security administration",
        category="management",
        capabilities=ALL_CAPABILITIES,
    ),
    RoleTemplate(
        name="admin",
        description="Administers the company and reviews security changes",
        category="management",
        # Todo salvo eliminar roles: borrar el rol equivocado es la forma más
        # rápida de dejar una compañía sin nadie que pueda administrarla.
        capabilities=tuple(
            name for name in sorted(CAPABILITY_NAMES) if name != "roles.delete"
        ),
    ),
    RoleTemplate(
        name="manager",
        description="Day-to-day administration of users, no security changes",
        category="operative",
        # Una aplicación de dominio añade aquí las capacidades de su trabajo
        # diario. La base sólo conoce la administración de usuarios.
        capabilities=(
            "companies.read",
            "regions.read",
            "users.read",
            "users.create",
            "users.update",
            "integrations.read",
        ),
    ),
    RoleTemplate(
        name="viewer",
        description="Read-only access",
        category="operative",
        capabilities=(
            "companies.read",
            "regions.read",
            "users.read",
        ),
    ),
    # ── CER Route ───────────────────────────────────────────────────────────
    RoleTemplate(
        name="supervisor",
        description="CER Route field supervisor; mobile-only workday experience",
        category="operative",
        # Sin capacidades administrativas, y en RTE02 sin capacidades Route:
        # las suyas —`route.worksession.execute`— llegan con el checkpoint que
        # construya la jornada. Su espacio de trabajo móvil exige sesión, no un
        # permiso, igual que `ProfilePage`: es su propia pantalla, y lo que
        # pueda HACER en ella se autoriza cuando esos endpoints existan.
        #
        # El rol se crea igualmente porque es lo que permite a un administrador
        # designar supervisores y asignarles vehículo, que es trabajo de RTE02.
        capabilities=(),
    ),
    RoleTemplate(
        name="route_admin",
        description="Administers CER Route operational configuration within this company",
        category="operative",
        capabilities=(
            "companies.read",
            "regions.read",
            "users.read",
            "route.vehicles.read",
            "route.vehicles.manage",
            "route.standardvalues.manage",
        ),
    ),
)


def capabilities_for(template: RoleTemplate) -> tuple[str, ...]:
    if template.capabilities == ALL_CAPABILITIES:
        return tuple(sorted(CAPABILITY_NAMES))
    return tuple(template.capabilities)
