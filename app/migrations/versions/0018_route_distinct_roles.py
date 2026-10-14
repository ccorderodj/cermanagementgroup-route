"""Un rol por cargo en CER Route: CEO, COO, Regional Manager, OSM y Sales.

Revision ID: 0018_route_distinct_roles
Revises: 0017_org_hierarchy
Create Date: 2026-10-13

Qué añade (V1.3)
----------------
* Los roles **CEO**, **COO**, **Regional Manager**, **OSM** y **Sales** en cada
  compañía, con su nombre visible como nombre (Roles & Permissions y la lista
  de usuarios enseñan `role.name`). El Supervisor ya existe (`supervisor`).
* **Sus capacidades, aquí mismo.** La 0017 creó `route_manager` vacío y dejó
  las capacidades a la alineación (*converge*); en un entorno donde se migró y
  no se alineó, el rol quedó con **0** capacidades, que es lo que vio el PO.
  Ésta no repite el error: crea cada rol **y** le concede las capacidades de su
  plantilla, y repara de paso las 9 de `route_manager`. Sólo añade concesiones
  que faltan (idempotente) y sólo con capacidades que ya existen en `permission`.
* El cargo `sales` en `org_assignment` (CHECK ampliado).

Lo que **no** hace
------------------
* No asigna ningún rol a nadie ni cambia el rol de ninguna persona (AC-10).
* No crea, cambia ni infiere ninguna relación de jerarquía.
* No toca Estado operativo ni Zona horaria.

Un rol con el mismo nombre que ya existiera
-------------------------------------------
Si una compañía ya tiene un rol llamado igual que uno de éstos —creado a mano
en Roles & Permissions, es decir, con otra descripción—, la migración **se
detiene** y lo dice. (Uno con el mismo nombre **y** la descripción de esta
migración es el que conservó una bajada anterior por tener miembros: se
reutiliza.) Reutilizarlo
en silencio le concedería capacidades de mando a sus miembros actuales. Hay
que renombrarlo antes de migrar.

La bajada
---------
Devuelve el CHECK sin `sales` (falla si hay asignaciones con ese cargo: no se
borran datos para poder bajar) y borra, con sus concesiones, los roles nuevos
**que no tienen miembros**. Un rol con miembros **se conserva**: bajar no deja a
nadie sin rol, y en la 0017 un rol de más es sólo un rol. Las concesiones
reparadas de `route_manager` se conservan: son las de su plantilla.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0018_route_distinct_roles"
down_revision = "0017_org_hierarchy"
branch_labels = None
depends_on = None

EJECUCION = ("route.worksession.execute", "route.standardvalues.read")
MANDO = EJECUCION + (
    "route.live.read",
    "route.activity.read",
    "route.reports.read",
    "route.reports.export",
    "users.read",
    "users.create",
    "users.update",
)

#: Rol nuevo → (descripción, capacidades). Copia de la plantilla del catálogo
#: a fecha de esta migración: una migración no importa el código vivo.
ROLES_NUEVOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "CEO": ("CER Route CEO; sees and manages only their branch", MANDO),
    "COO": ("CER Route COO; sees and manages only their branch", MANDO),
    "Regional Manager": (
        "CER Route Regional Manager; sees and manages only their branch", MANDO,
    ),
    "OSM": ("CER Route on-site manager; mobile workday, own activity only", EJECUCION),
    "Sales": (
        "CER Route sales; mobile workday, own activity only; reports to a CEO", EJECUCION,
    ),
}

CON_SALES = "'ceo', 'coo', 'regional_manager', 'osm', 'supervisor', 'sales'"
SIN_SALES = "'ceo', 'coo', 'regional_manager', 'osm', 'supervisor'"


def _conceder(conexion, nombre_rol: str, capacidades: tuple[str, ...]) -> None:
    conexion.execute(
        text(
            """
            INSERT INTO role_permission (role_id, permission_id, is_active,
                                         created_at, updated_at)
            SELECT r.id, p.id, true, now(), now()
            FROM role AS r
            JOIN permission AS p ON p.name = ANY(CAST(:capacidades AS varchar[]))
            WHERE r.name = CAST(:rol AS varchar)
              AND NOT EXISTS (
                  SELECT 1 FROM role_permission AS rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ),
        {"rol": nombre_rol, "capacidades": list(capacidades)},
    )


def upgrade() -> None:
    conexion = op.get_bind()

    # Un rol con el nombre **y la descripción** de esta migración es suyo: lo
    # dejó una bajada anterior porque tenía miembros, y se reutiliza. Con el
    # mismo nombre y otra descripción, lo hizo alguien a mano.
    existentes = conexion.execute(
        text(
            "SELECT company_id, name, description FROM role "
            "WHERE name = ANY(CAST(:nombres AS varchar[])) ORDER BY 1, 2"
        ),
        {"nombres": list(ROLES_NUEVOS)},
    ).all()
    choques = [e for e in existentes if e.description != ROLES_NUEVOS[e.name][0]]
    if choques:
        detalle = ", ".join(f"company {c.company_id}: '{c.name}'" for c in choques)
        raise RuntimeError(
            "0018: these companies already have a role with the name of a new CER Route "
            f"role ({detalle}). Rename it in Roles & Permissions before migrating; reusing "
            "it would grant management capabilities to its current members."
        )

    op.drop_constraint("ck_org_assignment_position", "org_assignment", type_="check")
    op.create_check_constraint(
        "ck_org_assignment_position", "org_assignment", f"position IN ({CON_SALES})"
    )

    for nombre, (descripcion, _) in ROLES_NUEVOS.items():
        conexion.execute(
            text(
                """
                INSERT INTO role (company_id, name, description, category, is_active,
                                  created_at, updated_at)
                SELECT c.id, CAST(:nombre AS varchar), CAST(:descripcion AS varchar),
                       'operative', true, now(), now()
                FROM company AS c
                WHERE NOT EXISTS (
                    SELECT 1 FROM role AS r
                    WHERE r.company_id = c.id AND r.name = CAST(:nombre AS varchar)
                )
                """
            ),
            {"nombre": nombre, "descripcion": descripcion},
        )

    for nombre, (_, capacidades) in ROLES_NUEVOS.items():
        _conceder(conexion, nombre, capacidades)
    # La reparación del rol que la 0017 dejó vacío.
    _conceder(conexion, "route_manager", MANDO)


def downgrade() -> None:
    op.drop_constraint("ck_org_assignment_position", "org_assignment", type_="check")
    op.create_check_constraint(
        "ck_org_assignment_position", "org_assignment", f"position IN ({SIN_SALES})"
    )
    conexion = op.get_bind()
    sin_miembros = """
        SELECT r.id FROM role AS r
        WHERE r.name = ANY(CAST(:nombres AS varchar[]))
          AND NOT EXISTS (SELECT 1 FROM user_company AS uc WHERE uc.role_id = r.id)
    """
    conexion.execute(
        text(f"DELETE FROM role_permission WHERE role_id IN ({sin_miembros})"),
        {"nombres": list(ROLES_NUEVOS)},
    )
    conexion.execute(
        text(f"DELETE FROM role WHERE id IN ({sin_miembros})"),
        {"nombres": list(ROLES_NUEVOS)},
    )
