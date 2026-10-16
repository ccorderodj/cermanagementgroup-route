"""Activity Explorer: que la capacidad llegue a los tenants que ya existían.

Qué cierra este archivo
------------------------
El mismo hueco que se corrigió para Today / Live, comprobado ahora sobre
`route.activity.read` y las superficies de RTE08. No es otro parche: es el
**mismo** mecanismo compartido, verificado para esta capacidad.

Por qué conviene probarlo otra vez y no dar por hecho que vale
---------------------------------------------------------------
Porque lo que falló en campo no fue el código de la capacidad, sino el puente
entre el catálogo y las concesiones de cada tenant. Ese puente ahora existe, y
lo que hay que demostrar es que **esta** capacidad lo cruza: que un tenant con
el rol antiguo la recibe, que el menú, la página y la API coinciden, y que el
Supervisor sigue fuera.

El invariante que se defiende
------------------------------
    concesiones efectivas  ⊆  concesiones de la plantilla aprobada
    y, tras alinear, están todas las que el producto necesita

No «dos roles y punto»: si `owner` y `admin` declaran la capacidad en sus
plantillas —y la declaran, desde antes de RTE08— eso se **preserva**. Quitarla
para forzar una lectura de dos roles sería inventar una regla que nadie aprobó.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.rbac.catalog import CAPABILITIES, DEFAULT_ROLES, capabilities_for
from app.database import async_session_maker
from app.routers_api.companies.models import Company
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from app.routers_api.users.permissions import get_user_permissions

pytestmark = pytest.mark.integration

CAPACIDAD = "route.activity.read"
RUTA_API = "/api/activity-explorer"
RUTA_PAGINA = "/admin/route/activity"


async def _rol_de(company_id: int, nombre: str) -> int | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(Role.id).where(Role.company_id == company_id, Role.name == nombre)
        )


async def _concesiones(role_id: int) -> set[str]:
    async with async_session_maker() as session:
        filas = await session.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return set(filas.scalars().all())


async def _tenant_anterior_a_rte08(company_id: int, rol: str = "route_admin") -> int:
    """Quita la concesión: el estado de un tenant creado antes de RTE08.

    La fila de `permission` existe —el catálogo es global— y la concesión al
    rol no. Es exactamente lo que se encontró en la base real.
    """
    role_id = await _rol_de(company_id, rol)
    async with async_session_maker() as session:
        permission_id = await session.scalar(
            select(Permission.id).where(Permission.name == CAPACIDAD)
        )
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        await session.commit()
    return role_id


# ── T1 y T2: catálogo y plantillas ──────────────────────────────────────────


async def test_la_capacidad_existe_una_sola_vez(seeded):
    """T1. Y en la base, no sólo en el código.

    Si alguien «arregla» un problema de permisos creando una segunda capacidad
    con otro nombre, esto lo detiene: a partir de ahí habría dos verdades sobre
    quién puede explorar la historia.
    """
    assert [c.name for c in CAPABILITIES].count(CAPACIDAD) == 1

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Permission.id).where(Permission.name == CAPACIDAD)
        )
        assert len(filas.scalars().all()) == 1


async def test_las_plantillas_la_declaran_donde_toca(seeded):
    """T2. `route_admin` sí, `supervisor` no, y el resto como ya estaba.

    No se inventan reglas de plantilla nuevas: se fija la que hay. `owner` y
    `admin` del núcleo la declaran por sus plantillas existentes y eso se
    preserva — §5 lo dice de forma explícita.
    """
    por_nombre = {t.name: set(capabilities_for(t)) for t in DEFAULT_ROLES}

    assert CAPACIDAD in por_nombre["route_admin"]
    assert CAPACIDAD not in por_nombre["supervisor"]
    assert CAPACIDAD not in por_nombre["manager"]
    assert CAPACIDAD not in por_nombre["viewer"]
    # Los del núcleo, tal como estaban.
    assert CAPACIDAD in por_nombre["owner"]
    assert CAPACIDAD in por_nombre["admin"]


# ── T3 y T4: el ciclo de vida del tenant existente ──────────────────────────


async def test_el_ciclo_completo_del_tenant_existente(seeded, alpha_client):
    """T3 y T4: los once pasos de §7, en orden y con sus aserciones.

    Antes de alinear, el Administrador **no** entra; después entra; y una
    segunda alineación no añade nada.
    """
    from app.db.scripts.align_role_capabilities import alinear

    role_id = await _tenant_anterior_a_rte08(seeded.alpha.id)
    admin = seeded.alpha.users["route_admin"]

    # 4. La concesión no está, y se nota donde importa.
    efectivas = await get_user_permissions(user_id=admin.id, company_id=seeded.alpha.id)
    assert CAPACIDAD not in efectivas
    await alpha_client.login(admin.email)
    assert (await alpha_client.get(RUTA_API)).status_code == 403
    assert (await alpha_client.get(RUTA_PAGINA)).status_code in (401, 403, 404)

    # 5 y 6. El mecanismo compartido.
    primera = await alinear()
    assert primera.concesiones_anadidas >= 1
    assert CAPACIDAD in await _concesiones(role_id)

    # 8 y 9. Página y API.
    efectivas = await get_user_permissions(user_id=admin.id, company_id=seeded.alpha.id)
    assert CAPACIDAD in efectivas
    await alpha_client.login(admin.email)
    assert (await alpha_client.get(RUTA_PAGINA)).status_code == 200
    respuesta = await alpha_client.get(RUTA_API)
    assert respuesta.status_code == 200, respuesta.text
    assert "supervisors" in respuesta.json()

    # 10 y 11. Idempotencia.
    antes = await _concesiones(role_id)
    segunda = await alinear()
    assert segunda.concesiones_anadidas == 0
    assert await _concesiones(role_id) == antes


async def test_la_alineacion_no_toca_lo_que_no_declara_la_plantilla(
    seeded, alpha_client
):
    """T3: sólo añade lo declarado, y no altera lo demás.

    Dos comprobaciones en una: ninguna otra concesión cambia, y ningún rol
    acaba con capacidades que su plantilla no declare. Es el invariante de §5
    escrito como aserción.
    """
    from app.db.scripts.align_role_capabilities import alinear

    role_id = await _tenant_anterior_a_rte08(seeded.alpha.id)
    antes = await _concesiones(role_id)

    await alinear()

    despues = await _concesiones(role_id)
    assert despues - antes == {CAPACIDAD}, (
        f"la alineación cambió más de lo que faltaba: {despues - antes}"
    )

    for plantilla in DEFAULT_ROLES:
        rid = await _rol_de(seeded.alpha.id, plantilla.name)
        if rid is None:
            continue
        sobrantes = await _concesiones(rid) - set(capabilities_for(plantilla))
        assert not sobrantes, (
            f"'{plantilla.name}' acabó con capacidades fuera de su plantilla: "
            f"{sorted(sobrantes)}"
        )


async def test_un_rol_ausente_se_informa_y_no_se_crea(seeded):
    """T3 y §6: si una compañía no tiene un rol de plantilla, no se inventa.

    Un rol nuevo aparece en la pantalla de permisos de ese tenant: crearlo por
    su cuenta sería tomar una decisión que es suya. Se informa y se sigue.
    """
    from app.db.scripts.align_role_capabilities import alinear

    async with async_session_maker() as session:
        compania = Company(
            name="Tenant Sin Roles",
            subdomain="sinroles",
            domain="sinroles.localhost",
        )
        session.add(compania)
        await session.commit()
        nueva_id = compania.id

    resumen = await alinear()

    ausentes = {rol for sub, rol in resumen.roles_ausentes if sub == "sinroles"}
    assert ausentes == {t.name for t in DEFAULT_ROLES}, (
        f"no se informaron todos los roles ausentes: {ausentes}"
    )

    async with async_session_maker() as session:
        creados = (
            await session.execute(select(Role.id).where(Role.company_id == nueva_id))
        ).scalars().all()
    assert creados == [], "la alineación creó roles en una compañía que no los tenía"


# ── T7 y T8: lo que no puede cambiar ────────────────────────────────────────


async def test_el_supervisor_sigue_sin_explorar(seeded, alpha_client):
    """T7: su plantilla no la declara, así que no la recibe."""
    from app.db.scripts.align_role_capabilities import alinear

    await alinear()
    supervisor = seeded.alpha.users["supervisor"]

    efectivas = await get_user_permissions(
        user_id=supervisor.id, company_id=seeded.alpha.id
    )
    assert CAPACIDAD not in efectivas

    await alpha_client.login(supervisor.email)
    assert (await alpha_client.get(RUTA_API)).status_code == 403
    assert (await alpha_client.get(RUTA_PAGINA)).status_code in (401, 403, 404)


async def test_el_aislamiento_entre_tenants_sigue_intacto(
    seeded, alpha_client, beta_client
):
    """T8: alinear las dos compañías no mezcla la historia de ninguna."""
    from app.db.scripts.align_role_capabilities import alinear

    await _tenant_anterior_a_rte08(seeded.alpha.id)
    await _tenant_anterior_a_rte08(seeded.beta.id)
    await alinear()

    # Beta prepara un supervisor suyo.
    await beta_client.login(seeded.beta.users["route_admin"].email)
    await beta_client.post(
        "/api/supervisors", json={"user_id": seeded.beta.users["supervisor"].id}
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = (await alpha_client.get(RUTA_API)).json()

    ajenos = {u.id for u in seeded.beta.users.values()}
    for s in cuerpo["supervisors"]:
        assert s["user_id"] not in ajenos, "alpha ve un supervisor de beta"

    # Y pedir el de beta por identificador no confirma que exista.
    respuesta = await alpha_client.get(
        RUTA_API, params={"supervisor_user_id": seeded.beta.users["supervisor"].id}
    )
    assert respuesta.status_code == 404


async def test_navegacion_pagina_y_api_exigen_la_misma_capacidad(seeded):
    """§8: ninguna capa puede usar un permiso distinto.

    Se comprueba sobre las tres declaraciones, que es donde vive la verdad. Si
    alguien cambia una y olvida las otras, esto lo detiene antes de que
    aparezca un menú que lleva a un 403.
    """
    import pathlib
    import re

    api = pathlib.Path(
        "app/routers_api/activityexplorer/router.py"
    ).read_text(encoding="utf-8")
    assert f'require_permissions(["{CAPACIDAD}"])' in api

    paginas = pathlib.Path(
        "app/routers_pages/admin/route/router.py"
    ).read_text(encoding="utf-8")
    bloque = re.search(r'name="RouteActivityExplorerPage".*?\)\n', paginas, re.S)
    assert bloque and f'require_page_permissions(["{CAPACIDAD}"])' in bloque.group(0)

    menu = pathlib.Path(
        "app/components/react/app/providers/maincontent/config/navigation.ts"
    ).read_text(encoding="utf-8")
    entrada = re.search(r"title: 'Activity',.*?\}", menu, re.S)
    assert entrada and f"requiredPermission: '{CAPACIDAD}'" in entrada.group(0)
