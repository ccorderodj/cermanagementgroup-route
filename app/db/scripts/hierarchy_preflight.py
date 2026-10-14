"""Inventario de la jerarquía de CER Route antes de migrar a V1.4. Sólo lee.

Para qué existe
---------------
La 0019 instala un único CEO vigente por compañía y V1.4 cierra las vías que
dejaban rol y cargo desacompasados. Antes de migrar un entorno con datos hay
que saber qué hay en él (V1.4, §6):

* compañías con **más de un CEO** vigente (la 0019 se detendría);
* personas cuyo **rol no corresponde a su cargo** (p. ej. rol Supervisor con
  cargo COO, lo que dejaba la pantalla general);
* roles de la jerarquía **sin cargo**;
* cargos colgando de un superior **suspendido, retirado o sin cargo**.

No elige al CEO titular ni corrige nada: no hay `UPDATE`, ni `commit`, ni
`--aplicar`. Regularizar es una decisión de negocio que se hace después desde
CER Route → Users. La salida usa ids internos, nunca nombres ni correos.

    uv run python -m app.db.scripts.hierarchy_preflight
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.database import async_session_maker

ROL_CARGO = (
    "(r.name = 'CEO' AND oa.position = 'ceo') OR (r.name = 'COO' AND oa.position = 'coo') "
    "OR (r.name = 'Regional Manager' AND oa.position = 'regional_manager') "
    "OR (r.name = 'OSM' AND oa.position = 'osm') OR (r.name = 'supervisor' AND oa.position = 'supervisor') "
    "OR (r.name = 'Sales' AND oa.position = 'sales') "
    "OR (r.name = 'route_manager' AND oa.position IN ('ceo', 'coo', 'regional_manager'))"
)

CONSULTAS: dict[str, str] = {
    "Compañías con más de un CEO vigente": (
        "SELECT company_id, count(*) AS ceos FROM org_assignment "
        "WHERE position = 'ceo' AND valid_to IS NULL GROUP BY company_id HAVING count(*) > 1"
    ),
    "Rol y cargo que no se corresponden": (
        "SELECT oa.company_id, oa.user_id, r.name AS rol, oa.position AS cargo, "
        "oa.superior_user_id, uc.is_active AS activa, "
        "(SELECT count(*) FROM org_assignment d WHERE d.company_id = oa.company_id "
        " AND d.superior_user_id = oa.user_id AND d.valid_to IS NULL) AS directos "
        "FROM org_assignment oa "
        "JOIN user_company uc ON uc.user_id = oa.user_id AND uc.company_id = oa.company_id "
        "JOIN role r ON r.id = uc.role_id "
        f"WHERE oa.valid_to IS NULL AND NOT ({ROL_CARGO}) ORDER BY 1, 2"
    ),
    "Rol de la jerarquía sin cargo vigente": (
        "SELECT uc.company_id, uc.user_id, r.name AS rol, uc.is_active AS activa "
        "FROM user_company uc JOIN role r ON r.id = uc.role_id "
        "WHERE uc.deleted_at IS NULL "
        "AND r.name IN ('CEO', 'COO', 'Regional Manager', 'OSM', 'Sales', 'supervisor') "
        "AND NOT EXISTS (SELECT 1 FROM org_assignment oa WHERE oa.user_id = uc.user_id "
        " AND oa.company_id = uc.company_id AND oa.valid_to IS NULL) ORDER BY 1, 3, 2"
    ),
    "Cargos bajo un superior suspendido, retirado o sin cargo": (
        "SELECT oa.company_id, oa.user_id, oa.position, oa.superior_user_id, "
        "suc.is_active AS superior_activo, suc.deleted_at IS NOT NULL AS superior_retirado, "
        "s.id IS NULL AS superior_sin_cargo "
        "FROM org_assignment oa "
        "LEFT JOIN org_assignment s ON s.user_id = oa.superior_user_id "
        " AND s.company_id = oa.company_id AND s.valid_to IS NULL "
        "LEFT JOIN user_company suc ON suc.user_id = oa.superior_user_id AND suc.company_id = oa.company_id "
        "WHERE oa.valid_to IS NULL AND oa.superior_user_id IS NOT NULL "
        "AND (s.id IS NULL OR suc.is_active IS NOT TRUE OR suc.deleted_at IS NOT NULL) ORDER BY 1, 2"
    ),
    "Capacidades por rol de la jerarquía": (
        "SELECT r.company_id, r.name, count(rp.id) AS capacidades FROM role r "
        "LEFT JOIN role_permission rp ON rp.role_id = r.id "
        "WHERE r.name IN ('CEO', 'COO', 'Regional Manager', 'OSM', 'Sales', 'supervisor', "
        " 'route_admin', 'route_manager') GROUP BY 1, 2 ORDER BY 1, 2"
    ),
}


async def _principal() -> None:
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        for titulo, consulta in CONSULTAS.items():
            resultado = await session.execute(text(consulta))
            filas = resultado.all()
            print(f"\n== {titulo}: {len(filas)}")
            if filas:
                print("   " + " | ".join(resultado.keys()))
                for fila in filas:
                    print("   " + " | ".join(str(v) for v in fila))
        await session.rollback()


if __name__ == "__main__":
    asyncio.run(_principal())
