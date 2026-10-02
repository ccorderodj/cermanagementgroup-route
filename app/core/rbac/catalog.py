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
    # Retirar a alguien de la compañía es más que suspenderlo, y por eso no va
    # dentro de `users.update`: esa capacidad dice "editar y suspender", y quien
    # la tenga no debería quedarse con el borrado de regalo por un cambio de
    # alcance silencioso. El catálogo ya separa `roles.delete` de
    # `roles.update` por el mismo motivo (RTE02-A01).
    _cap("users", "delete", "Remove users from this company"),
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
    # catálogo certificado de RTE01 contempla además `route.live.read`,
    # `route.activity.read`, `route.reports.read`, `route.reports.export`
    # y `route.fuelreference.manage`: entran con el
    # checkpoint que construya su superficie protegida, porque
    # `test_permission_catalog.py` rechaza —a propósito— una capacidad que
    # ningún endpoint pide. Declararlas antes concedería autoridad sobre algo
    # que todavía no existe.
    _cap("route", "vehicles.read", "View Route vehicles and their assignments"),
    _cap("route", "vehicles.manage", "Create and edit Route vehicles and assign them to supervisors"),
    # Leer para elegir y administrar la lista son dos autorizaciones, no una
    # (BR-03 de la resolución A02). Quien ejecuta la jornada necesita leer los
    # valores que su viaje exige antes de salir; no necesita —ni debe— poder
    # crearlos, renombrarlos, reordenarlos ni retirarlos.
    #
    # Esto reemplaza un atajo que introduje en RTE04-C5: entonces la lectura se
    # autorizó con `standardvalues.manage` **o** `worksession.execute`, que hacía
    # de "ejecutar" un permiso de lectura genérico. Funcionaba, y era exactamente
    # lo que A02 prohíbe: la separación Read / Execute / Manage dejaba de ser
    # legible en el catálogo.
    _cap("route", "standardvalues.read", "Read the Route operational value lists"),
    _cap("route", "standardvalues.manage", "Manage the Route admin-configurable value lists"),
    # RTE03: la Jornada. Quien la ejecuta solo puede ejecutar **la suya** —el
    # endpoint nunca acepta la identidad de otro usuario, siempre la de la
    # sesión autenticada—, así que una sola capacidad basta para Start Work,
    # End Work y el estado actual.
    #
    # La tienen los **dos** roles de producto de CER Route. RTE03 se la negó al
    # Administrador razonando que "acceder a Admin" y "ejecutar trabajo de campo"
    # son autorizaciones distintas; sigue siendo verdad que son distintas, pero
    # CER decidió en A02 que su Administrador también sale a ruta. Un CEO o un
    # COO usan ese rol y conducen. La separación que importa no es quién puede
    # ejecutar: es que ejecutar no conceda administrar (BR-02, BR-03).
    _cap("route", "worksession.execute", "Start and end the caller's own Work Session"),
    # RTE04: aprobar o rechazar una entrada manual de odómetro cuando el
    # supervisor no pudo obtener la foto. Es autoridad de administración, no de
    # campo: dársela a quien ejecuta la jornada permitiría aprobar su propia
    # excepción, y el control dejaría de serlo. Estaba en el catálogo
    # certificado de RTE01 y se activa ahora que hay endpoints que la exigen.
    _cap("route", "records.adjust", "Review and decide odometer manual-entry exceptions"),
    # Medida temporal de estabilización, autorizada por CER.
    #
    # Qué concede, exactamente
    # ------------------------
    # Que la excepción de odómetro que **el propio supervisor** pide se apruebe
    # sola, para que el día no se detenga esperando a un administrador. Nada
    # más: no deja revisar ni decidir la excepción de nadie, no da acceso a la
    # cola de administración, y no sustituye a `records.adjust`.
    #
    # Es deliberadamente estrecha por lo que dice el comentario de arriba: dar
    # `records.adjust` a quien ejecuta la jornada le dejaría aprobar cualquier
    # excepción, y eso sí desarmaría el control. Esta sólo quita la espera en el
    # caso que CER acotó.
    #
    # Lo que **no** cambia
    # --------------------
    # La excepción sigue siendo una excepción: mismo motivo cerrado, misma
    # trazabilidad, y la lectura sigue entrando como `manual_no_photo`. No se
    # fabrica foto ni lectura. El camino normal de foto y confirmación no se
    # toca.
    #
    # No se siembra en ningún rol
    # ---------------------------
    # No está en `DEFAULT_ROLES` a propósito: instalar este código no cambia el
    # comportamiento de nadie. Hay que concederla a mano al rol que corresponda,
    # en el tenant que corresponda, y por eso la reversión es retirarla —lo que
    # devuelve el flujo de `requested` y aprobación por administrador sin tocar
    # ninguna línea de código—.
    _cap(
        "route",
        "odometer.selfapprove",
        "Temporarily let the supervisor's own odometer exception be approved "
        "automatically, during CER stabilisation",
    ),
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
        # **Read + Execute, nunca Manage** (FR-03). Ejecuta su propia jornada y
        # lee los valores que sus viajes exigen antes de salir; no administra
        # usuarios, ni roles, ni vehículos, ni las listas, ni aprueba
        # excepciones. La lectura es una capacidad aparte justamente para que
        # esto se pueda decir en una línea y comprobarse en un test.
        capabilities=(
            "route.worksession.execute",
            "route.standardvalues.read",
        ),
    ),
    RoleTemplate(
        name="route_admin",
        description="Administers CER Route operational configuration within this company",
        category="operative",
        capabilities=(
            "companies.read",
            "regions.read",
            # Administración de usuarios del tenant. Son las capacidades del
            # **núcleo**, no unas propias de Route: el contrato de identidad ya
            # existe y duplicarlo crearía dos formas de autorizar lo mismo.
            #
            # `roles.read` entra porque el formulario de alta necesita ofrecer
            # los roles de la compañía; NO se concede `roles.create/update/
            # delete`, así que un Route Admin asigna roles existentes pero no
            # puede fabricarse uno con más capacidades.
            #
            # El límite de privilegio lo sostiene el propio contrato del núcleo:
            # `is_superuser` no está en ningún schema de entrada de estas APIs
            # (D6), así que esto no abre ninguna puerta a la plataforma.
            "users.read",
            "users.create",
            "users.update",
            # RTE02-A01: administrar Route incluye retirar del tenant a quien
            # ya no trabaja aquí, sin pedírselo a nadie más. Sigue siendo
            # pertenencia, no identidad: la persona no se destruye.
            "users.delete",
            # `roles.read` **ya no** se concede aquí. El formulario de usuarios
            # de Route ya no ofrece el catálogo de roles del tenant: ofrece los
            # dos roles de producto, y el servidor sólo acepta esos dos (FR-01,
            # FR-05). Leer los roles del núcleo dejó de tener uso, y la
            # capacidad que no hace falta no se concede.
            "route.vehicles.read",
            "route.vehicles.manage",
            # Read **y** manage: administra las listas y también las lee para
            # sus propios viajes.
            "route.standardvalues.read",
            "route.standardvalues.manage",
            "route.records.adjust",
            # A02/BR-02: el Administrador también sale a ruta. Usa la misma
            # experiencia móvil que el Supervisor, con la misma capacidad.
            "route.worksession.execute",
        ),
    ),
)


#: Los dos roles de producto de CER Route, por su código técnico interno.
#:
#: Son los **únicos** que el flujo de usuarios de CER Route puede asignar
#: (FR-01, FR-05). Los del núcleo —`owner`, `admin`, `manager`, `viewer`— siguen
#: existiendo y no se tocan: simplemente no son personas de este producto, y
#: concederlos desde aquí era la escalada que encontró el diagnóstico A01.
#:
#: Se conservan los códigos técnicos existentes a propósito: renombrarlos sólo
#: para cambiar la etiqueta visible obligaría a una migración destructiva de
#: `role.name` en cada tenant, y la resolución lo prohíbe explícitamente.
ROUTE_PRODUCT_ROLES: frozenset[str] = frozenset({"route_admin", "supervisor"})

#: Cómo se llaman en pantalla. El código técnico no se muestra nunca.
ROUTE_PRODUCT_ROLE_LABELS: dict[str, str] = {
    "route_admin": "Administrador",
    "supervisor": "Supervisor",
}


def capabilities_for(template: RoleTemplate) -> tuple[str, ...]:
    if template.capabilities == ALL_CAPABILITIES:
        return tuple(sorted(CAPABILITY_NAMES))
    return tuple(template.capabilities)
