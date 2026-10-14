"""
Migración 0018: un rol por cargo, con sus capacidades **en la base**.

El defecto que cierra: la 0017 creó `route_manager` vacío y dejó las
capacidades a la alineación; donde se migró sin alinear, el rol quedó con 0
(lo que vio el PO en Roles & Permissions). Estas pruebas bajan a la 0017 con
compañías reales en la base, simulan ese estado y suben:

* los cinco roles nuevos aparecen en **cada** compañía con sus capacidades;
* `route_manager` recupera sus 9;
* no se asigna ningún rol a nadie ni se crea ninguna jerarquía;
* un rol propio con el mismo nombre detiene la migración, sin cambios.

Siempre devuelven la base al head, pase lo que pase.
"""

from __future__ import annotations

import subprocess

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.database import async_session_maker

pytestmark = pytest.mark.integration

HEAD = ScriptDirectory.from_config(Config("app/alembic.ini")).get_current_head()
ANTES = "0017_org_hierarchy"
NUEVOS = ("CEO", "COO", "Regional Manager", "OSM", "Sales")
MANDO = 9
EJECUCION = 2


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "alembic", "-c", "app/alembic.ini", *args],
        capture_output=True, text=True, shell=False,
    )


async def _filas(sql: str, **p):
    async with async_session_maker() as s:
        return (await s.execute(text(sql), p)).all()


async def _ejecutar(sql: str, **p):
    async with async_session_maker() as s:
        await s.execute(text(sql), p)
        await s.commit()


async def _capacidades_por_rol(company_id: int) -> dict[str, int]:
    return {
        f.name: f.n
        for f in await _filas(
            "SELECT r.name, count(rp.id) AS n FROM role r "
            "LEFT JOIN role_permission rp ON rp.role_id = r.id "
            "WHERE r.company_id = :c GROUP BY r.name",
            c=company_id,
        )
    }


async def _sin_miembros_en_roles_nuevos(seeded) -> None:
    """La fixture siembra un CEO raíz por tenant; para poder bajar, vuelve a un
    rol del núcleo y sin cargo (la bajada no deja a nadie sin rol)."""
    for empresa in (seeded.alpha, seeded.beta):
        await _ejecutar(
            "UPDATE user_company SET role_id = :r WHERE user_id = :u AND company_id = :c",
            r=empresa.roles["viewer"], u=empresa.users["ceo_base"].id, c=empresa.id,
        )
    await _ejecutar("DELETE FROM org_assignment")


def _subir_o_fallar() -> None:
    subida = _alembic("upgrade", HEAD)
    assert subida.returncode == 0, (
        "la base quedó fuera del head y eso rompería los demás tests:\n"
        + subida.stdout + subida.stderr
    )


async def test_crea_los_roles_con_capacidades_y_repara_route_manager(seeded) -> None:
    await _sin_miembros_en_roles_nuevos(seeded)
    miembros_antes = await _filas("SELECT user_id, company_id, role_id FROM user_company ORDER BY 1, 2")
    bajada = _alembic("downgrade", ANTES)
    assert bajada.returncode == 0, bajada.stdout + bajada.stderr
    try:
        for empresa in (seeded.alpha, seeded.beta):
            roles = await _capacidades_por_rol(empresa.id)
            assert not set(NUEVOS) & set(roles), "la bajada los retira"
        # El estado que vio el PO: `route_manager` sin ninguna capacidad.
        await _ejecutar(
            "DELETE FROM role_permission WHERE role_id IN "
            "(SELECT id FROM role WHERE name = 'route_manager')"
        )
    finally:
        _subir_o_fallar()

    for empresa in (seeded.alpha, seeded.beta):
        roles = await _capacidades_por_rol(empresa.id)
        for nombre in ("CEO", "COO", "Regional Manager", "route_manager"):
            assert roles[nombre] == MANDO, (empresa.subdomain, nombre, roles.get(nombre))
        for nombre in ("OSM", "Sales"):
            assert roles[nombre] == EJECUCION, (empresa.subdomain, nombre)
    # Nadie cambió de rol ni ganó una jerarquía.
    assert await _filas("SELECT user_id, company_id, role_id FROM user_company ORDER BY 1, 2") == miembros_antes
    assert await _filas("SELECT 1 FROM org_assignment") == []


async def test_un_rol_propio_con_el_mismo_nombre_detiene_la_migracion(seeded) -> None:
    await _sin_miembros_en_roles_nuevos(seeded)
    bajada = _alembic("downgrade", ANTES)
    assert bajada.returncode == 0, bajada.stdout + bajada.stderr
    try:
        await _ejecutar(
            "INSERT INTO role (company_id, name, description, category, is_active, created_at, updated_at) "
            "VALUES (:c, 'Sales', 'custom role made by hand', 'operative', true, now(), now())",
            c=seeded.alpha.id,
        )
        subida = _alembic("upgrade", HEAD)
        assert subida.returncode != 0
        assert "Rename it in Roles & Permissions" in subida.stdout + subida.stderr
        version = await _filas("SELECT version_num FROM alembic_version")
        assert version[0].version_num == ANTES, "nada se aplicó"
        assert await _filas(
            "SELECT 1 FROM role_permission rp JOIN role r ON r.id = rp.role_id "
            "WHERE r.name = 'Sales' AND r.company_id = :c", c=seeded.alpha.id,
        ) == [], "al rol propio no se le concedió nada"
        await _ejecutar("DELETE FROM role WHERE name = 'Sales' AND company_id = :c", c=seeded.alpha.id)
    finally:
        _subir_o_fallar()
    assert (await _filas("SELECT version_num FROM alembic_version"))[0].version_num == HEAD


async def test_la_bajada_conserva_los_roles_con_miembros(seeded, alpha_client) -> None:
    """Bajar no deja a nadie sin rol: el rol con miembros se queda; los vacíos,
    no. Y subir otra vez no duplica nada."""
    from tests.integration.test_org_hierarchy import _persona

    await _persona(alpha_client, seeded, "ceo_m", "CEO")
    bajada = _alembic("downgrade", ANTES)
    try:
        assert bajada.returncode == 0, bajada.stdout + bajada.stderr
        roles = await _capacidades_por_rol(seeded.alpha.id)
        assert "CEO" in roles, "tiene miembros: se conserva"
        assert "Sales" not in roles and "OSM" not in roles, "sin miembros: se retiran"
        miembro = await _filas(
            "SELECT r.name FROM user_company uc JOIN role r ON r.id = uc.role_id "
            "WHERE uc.user_id = :u", u=seeded.alpha.users["ceo_m"].id,
        )
        assert miembro[0].name == "CEO"
    finally:
        _subir_o_fallar()
    nombres = await _filas(
        "SELECT name, count(*) AS n FROM role WHERE company_id = :c GROUP BY name HAVING count(*) > 1",
        c=seeded.alpha.id,
    )
    assert nombres == [], "subir otra vez no duplica roles"


async def test_la_bajada_se_detiene_si_hay_cargos_sales(seeded, alpha_client) -> None:
    """El cargo `sales` no cabe en el CHECK de la 0017: no se borra para bajar."""
    from tests.integration.test_org_hierarchy import _persona

    await _persona(alpha_client, seeded, "sales_m", "Sales", "ceo_base")
    bajada = _alembic("downgrade", ANTES)
    try:
        assert bajada.returncode != 0
        assert (await _filas("SELECT version_num FROM alembic_version"))[0].version_num == HEAD
    finally:
        _subir_o_fallar()
