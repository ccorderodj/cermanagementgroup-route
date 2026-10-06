"""El Administrador de CER Route y Today / Live, tras el defecto de campo.

Qué defiende este archivo
--------------------------
Que una capacidad **introducida después** de que un tenant existiera llegue de
verdad a su rol, por un camino soportado y sin parchear la base a mano.

El defecto que reportó CER no estaba en el código de RTE07: el catálogo
declara `route.live.read`, la plantilla de `route_admin` la incluye, y los tres
guardas —navegación, página y API— exigen exactamente esa capacidad. Lo que
faltaba era el puente entre el catálogo y los tenants que ya existían.

La asimetría, que es el fondo del asunto
-----------------------------------------
`seed_permissions` alinea la tabla `permission`, que es **global**. `seed_roles`
alinea las concesiones de **una sola compañía**: la que nombra
`BOOTSTRAP_COMPANY_SUBDOMAIN`. Así que una capacidad nueva aparece en el
catálogo de toda la instalación y se concede sólo en un tenant. Los demás se
quedan con el rol que tenían el día que se creó.

Estos tests reproducen ese estado y comprueban que el mecanismo de alineación
lo corrige, que no revoca nada y que ejecutarlo dos veces no cambia nada más.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for
from app.database import async_session_maker
from app.routers_api.permissions.models import Permission
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from app.routers_api.users.permissions import get_user_permissions

pytestmark = pytest.mark.integration

CAPACIDAD = "route.live.read"
ROL = "route_admin"


async def _id_de_capacidad(nombre: str) -> int:
    async with async_session_maker() as session:
        return await session.scalar(
            select(Permission.id).where(Permission.name == nombre)
        )


async def _rol_de(company_id: int, nombre: str = ROL) -> int:
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


async def _simular_tenant_anterior_a_rte07(company_id: int) -> int:
    """Quita la concesión, como en un tenant creado antes de que existiera.

    No es un atajo de test: es exactamente el estado en el que queda una
    compañía que ya tenía su rol `route_admin` cuando RTE07 introdujo la
    capacidad. La fila de `permission` existe —el catálogo es global— y la
    concesión al rol no.
    """
    role_id = await _rol_de(company_id)
    permission_id = await _id_de_capacidad(CAPACIDAD)
    async with async_session_maker() as session:
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        await session.commit()
    return role_id


# ── El defecto de campo, reproducido ────────────────────────────────────────


async def test_sin_la_concesion_el_administrador_no_entra(seeded, alpha_client):
    """El síntoma que reportó CER, reproducido de punta a punta.

    Mismo código, mismo rol, misma capacidad declarada: lo único que cambia es
    que la concesión no está en ese tenant. Y entonces el Administrador no ve
    el menú, no abre la página y la API le responde 403.
    """
    await _simular_tenant_anterior_a_rte07(seeded.alpha.id)
    admin = seeded.alpha.users["route_admin"]

    efectivas = await get_user_permissions(
        user_id=admin.id, company_id=seeded.alpha.id
    )
    assert CAPACIDAD not in efectivas, "la preparación no reprodujo el estado"

    await alpha_client.login(admin.email)
    assert (await alpha_client.get("/api/live/today")).status_code == 403
    assert (await alpha_client.get("/admin/route/today")).status_code in (401, 403, 404)


async def test_el_catalogo_y_la_plantilla_estaban_bien(seeded, alpha_client):
    """D2 y D3: el defecto no estaba en el código, y conviene dejarlo escrito.

    La capacidad existe una sola vez en el catálogo y la plantilla del
    Administrador la incluye. Si alguien «arregla» esto añadiendo una segunda
    capacidad con otro nombre, este test lo detiene.
    """
    plantilla = next(t for t in DEFAULT_ROLES if t.name == ROL)
    assert CAPACIDAD in capabilities_for(plantilla)

    async with async_session_maker() as session:
        filas = await session.execute(
            select(Permission.id).where(Permission.name == CAPACIDAD)
        )
        assert len(filas.scalars().all()) == 1, "la capacidad está duplicada"


# ── La alineación, que es la corrección ─────────────────────────────────────


async def test_la_alineacion_concede_la_capacidad_que_faltaba(seeded, alpha_client):
    """T6: el tenant que ya existía recibe la capacidad por el camino soportado.

    Y después entra: menú, página y API responden lo mismo porque dependen de
    la misma capacidad.
    """
    from app.db.scripts.align_role_capabilities import alinear

    role_id = await _simular_tenant_anterior_a_rte07(seeded.alpha.id)
    admin = seeded.alpha.users["route_admin"]

    resumen = await alinear()

    assert resumen.concesiones_anadidas >= 1
    assert CAPACIDAD in await _concesiones(role_id)

    efectivas = await get_user_permissions(
        user_id=admin.id, company_id=seeded.alpha.id
    )
    assert CAPACIDAD in efectivas

    await alpha_client.login(admin.email)
    assert (await alpha_client.get("/api/live/today")).status_code == 200
    assert (await alpha_client.get("/admin/route/today")).status_code == 200


async def test_la_alineacion_no_revoca_ni_toca_lo_que_no_le_toca(
    seeded, alpha_client
):
    """Añade y **nunca** quita. Es la misma semántica que el bootstrap.

    Un tenant tiene decisiones reales dentro: quitar por su cuenta lo que un
    administrador concedió sería destruir trabajo sin avisar. Aquí se concede
    a mano una capacidad que la plantilla no trae, se alinea, y se comprueba
    que sigue estando.
    """
    from app.db.scripts.align_role_capabilities import alinear

    role_id = await _rol_de(seeded.alpha.id)
    # Una capacidad del núcleo que la plantilla de `route_admin` no incluye.
    plantilla = next(t for t in DEFAULT_ROLES if t.name == ROL)
    de_la_plantilla = set(capabilities_for(plantilla))
    async with async_session_maker() as session:
        ajena = await session.scalar(
            select(Permission.id, Permission.name)
            .where(Permission.name.notin_(de_la_plantilla))
            .limit(1)
        )
        nombre_ajeno = await session.scalar(
            select(Permission.name).where(Permission.id == ajena)
        )
        session.add(RolePermission(role_id=role_id, permission_id=ajena, is_active=True))
        await session.commit()

    antes = await _concesiones(role_id)
    await alinear()
    despues = await _concesiones(role_id)

    assert nombre_ajeno in despues, "la alineación revocó una concesión manual"
    assert antes <= despues, f"desaparecieron concesiones: {antes - despues}"


async def test_la_alineacion_es_idempotente(seeded, alpha_client):
    """T6: una segunda ejecución no añade nada ni duplica concesiones."""
    from app.db.scripts.align_role_capabilities import alinear

    role_id = await _simular_tenant_anterior_a_rte07(seeded.alpha.id)

    primera = await alinear()
    assert primera.concesiones_anadidas >= 1

    antes = await _concesiones(role_id)
    segunda = await alinear()
    despues = await _concesiones(role_id)

    assert segunda.concesiones_anadidas == 0, (
        f"la segunda ejecución añadió {segunda.concesiones_anadidas} concesiones"
    )
    assert antes == despues

    # Y ninguna fila duplicada para el mismo par rol/capacidad.
    async with async_session_maker() as session:
        filas = await session.execute(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role_id
            )
        )
        ids = list(filas.scalars().all())
    assert len(ids) == len(set(ids)), "hay concesiones duplicadas"


async def test_la_alineacion_alcanza_a_todos_los_tenants(seeded, alpha_client):
    """El hueco real: el bootstrap alinea **una** compañía, no todas.

    Es la causa raíz de este checkpoint. `seed_permissions` toca la tabla
    global de capacidades; `seed_roles` sólo concede en la compañía que nombra
    `BOOTSTRAP_COMPANY_SUBDOMAIN`. Una capacidad nueva aparecía en el catálogo
    de toda la instalación y se concedía en un solo tenant.
    """
    from app.db.scripts.align_role_capabilities import alinear

    rol_alpha = await _simular_tenant_anterior_a_rte07(seeded.alpha.id)
    rol_beta = await _simular_tenant_anterior_a_rte07(seeded.beta.id)

    await alinear()

    assert CAPACIDAD in await _concesiones(rol_alpha)
    assert CAPACIDAD in await _concesiones(rol_beta), (
        "la alineación dejó fuera a un tenant: es el defecto que viene a corregir"
    )


# ── Lo que no puede cambiar ─────────────────────────────────────────────────


async def test_el_supervisor_sigue_sin_entrar(seeded, alpha_client):
    """T4: la separación certificada de roles no se toca.

    El Supervisor ejecuta su jornada; no vigila la de los demás. Que el
    Administrador recupere su acceso no puede ampliar el del Supervisor.
    """
    from app.db.scripts.align_role_capabilities import alinear

    await alinear()
    supervisor = seeded.alpha.users["supervisor"]

    efectivas = await get_user_permissions(
        user_id=supervisor.id, company_id=seeded.alpha.id
    )
    assert CAPACIDAD not in efectivas

    await alpha_client.login(supervisor.email)
    assert (await alpha_client.get("/api/live/today")).status_code == 403
    assert (await alpha_client.get("/admin/route/today")).status_code in (401, 403, 404)


async def test_los_roles_del_nucleo_no_se_reutilizan(seeded, alpha_client):
    """AC-10: la alineación no ensancha ningún rol del núcleo.

    Una corrección en la primera versión de este test
    --------------------------------------------------
    Afirmaba que ningún rol del núcleo debía tener `route.live.read`, y era
    falso: `owner` recibe **las 27 capacidades** del catálogo por plantilla y
    `admin` todas menos `roles.delete`. Eso es anterior a RTE07 y es la
    definición del núcleo, no un efecto de esta corrección.

    Lo que sí hay que defender es que la alineación **aplica las plantillas tal
    como están y nada más**: no mueve capacidades entre roles para compensar un
    hueco de aprovisionamiento de CER Route. Eso es lo que se comprueba aquí.

    Y los dos roles del núcleo que **no** deben verlo siguen sin verlo.
    """
    from app.db.scripts.align_role_capabilities import alinear

    await alinear()

    for nombre in ("manager", "viewer", "supervisor"):
        usuario = seeded.alpha.users[nombre]
        efectivas = await get_user_permissions(
            user_id=usuario.id, company_id=seeded.alpha.id
        )
        assert CAPACIDAD not in efectivas, (
            f"el rol '{nombre}' recibió una capacidad que su plantilla no declara"
        )

    # Y ningún rol acaba con más de lo que su plantilla declara.
    for plantilla in DEFAULT_ROLES:
        role_id = await _rol_de(seeded.alpha.id, plantilla.name)
        if role_id is None:
            continue
        sobrantes = await _concesiones(role_id) - set(capabilities_for(plantilla))
        assert not sobrantes, (
            f"la alineación concedió a '{plantilla.name}' capacidades que su "
            f"plantilla no declara: {sorted(sobrantes)}"
        )


async def test_el_aislamiento_entre_tenants_sigue_intacto(
    seeded, alpha_client, beta_client
):
    """T5: el Administrador de alpha no ve supervisores de beta."""
    from app.db.scripts.align_role_capabilities import alinear

    await alinear()

    await beta_client.login(seeded.beta.users["route_admin"].email)
    await beta_client.post(
        "/api/supervisors", json={"user_id": seeded.beta.users["supervisor"].id}
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = (await alpha_client.get("/api/live/today")).json()

    ajenos = {u.id for u in seeded.beta.users.values()}
    for s in cuerpo["supervisors"]:
        assert s["user_id"] not in ajenos, "alpha está viendo a un supervisor de beta"


async def test_navegacion_pagina_y_api_exigen_la_misma_capacidad(seeded):
    """T7: ningún estado donde una capa conceda y otra niegue.

    Se comprueba sobre las tres declaraciones, que es donde vive la verdad: la
    dependencia de la API, la de la ruta de página y el `requiredPermission`
    del menú. Si alguien cambia una y olvida las otras, esto lo detiene.
    """
    import pathlib
    import re

    api = pathlib.Path("app/routers_api/live/router.py").read_text(encoding="utf-8")
    assert f'require_permissions(["{CAPACIDAD}"])' in api

    paginas = pathlib.Path(
        "app/routers_pages/admin/route/router.py"
    ).read_text(encoding="utf-8")
    bloque = re.search(
        r'name="RouteTodayLivePage".*?\)\n', paginas, re.S
    )
    assert bloque and f'require_page_permissions(["{CAPACIDAD}"])' in bloque.group(0)

    menu = pathlib.Path(
        "app/components/react/app/providers/maincontent/config/navigation.ts"
    ).read_text(encoding="utf-8")
    entrada = re.search(r"title: 'Today / Live',.*?\}", menu, re.S)
    assert entrada and f"requiredPermission: '{CAPACIDAD}'" in entrada.group(0)


async def test_el_admin_del_nucleo_tambien_se_arregla_con_lo_mismo(
    seeded, alpha_client
):
    """La condición de STOP de §2, resuelta con evidencia en vez de con una duda.

    La instrucción manda parar si la cuenta afectada resultara ser un `admin`
    del **núcleo** y no el `route_admin` de CER Route, porque sostenerlo podría
    exigir cambiar el modelo de roles aprobado.

    No lo exige. Medido sobre el catálogo: la plantilla de `admin` del núcleo
    declara 26 de las 27 capacidades —todas menos `roles.delete`— y
    `route.live.read` está entre ellas desde que RTE07 la introdujo. Así que si
    la cuenta de campo fuera un `admin` del núcleo, el síntoma sería **el mismo
    hueco de aprovisionamiento** y lo arregla **el mismo mecanismo**, sin tocar
    el modelo de roles ni reutilizar nada.

    Por eso este checkpoint no se declara bloqueado: la respuesta no depende de
    cuál de los dos roles tenga la cuenta.
    """
    from app.db.scripts.align_role_capabilities import alinear

    role_id = await _rol_de(seeded.alpha.id, "admin")
    permission_id = await _id_de_capacidad(CAPACIDAD)
    async with async_session_maker() as session:
        await session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        await session.commit()

    usuario = seeded.alpha.users["admin"]
    await alpha_client.login(usuario.email)
    assert (await alpha_client.get("/api/live/today")).status_code == 403

    await alinear()

    efectivas = await get_user_permissions(
        user_id=usuario.id, company_id=seeded.alpha.id
    )
    assert CAPACIDAD in efectivas
    await alpha_client.login(usuario.email)
    assert (await alpha_client.get("/api/live/today")).status_code == 200
