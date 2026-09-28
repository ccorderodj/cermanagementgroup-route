"""
El aprovisionamiento y sus semánticas de ciclo de vida (A02-C4).

Qué se protege aquí
-------------------
Que sembrar un tenant sea **seguro de repetir**. Es lo que permite ejecutar el
bootstrap en un entorno desalineado sin miedo, y es exactamente lo que hacía
falta: el diagnóstico A01 encontró un tenant con cero valores y un `supervisor`
sin ninguna capacidad, y la única forma responsable de arreglarlo era un
mecanismo que no destruyera nada de lo que el tenant hubiera decidido.

Las tres decisiones del tenant que el aprovisionamiento respeta —renombrar,
desactivar y borrar— se comprueban una por una. No son casos raros: son lo que
un administrador hace con una lista a lo largo de un año, y un segundo sembrado
que las pisara borraría trabajo real sin avisar.

Lo que **no** hace el bootstrap
--------------------------------
Revocar. Alinea lo que falta y nunca quita lo que sobra, así que una capacidad
retirada del catálogo sigue concedida en los tenants que ya la tenían. Está
comprobado abajo, porque es una propiedad del mecanismo que hay que conocer
antes de confiar en él para alinear un entorno.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.rbac.catalog import CAPABILITIES, DEFAULT_ROLES, capabilities_for
from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import (
    INITIAL_VALUES,
    provision_standard_values,
    seed_key_for,
)


pytestmark = pytest.mark.integration


TOTAL_APROBADO = sum(len(v) for v in INITIAL_VALUES.values())


async def _sembrar(company_id: int):
    async with async_session_maker() as session:
        resultado = await provision_standard_values(session, company_id=company_id)
        await session.commit()
    return resultado


async def _contar(company_id: int, *, solo_activos: bool = False) -> int:
    condicion = " AND is_active AND deleted_at IS NULL" if solo_activos else ""
    async with async_session_maker() as session:
        return await session.scalar(
            text(f"SELECT count(*) FROM standard_value WHERE company_id = :c{condicion}"),
            {"c": company_id},
        )


# ── Primera y segunda pasada ─────────────────────────────────────────────────


async def test_the_first_run_provisions_exactly_the_approved_values(seeded):
    assert await _contar(seeded.alpha.id) == 0, "el tenant empieza vacío"

    await _sembrar(seeded.alpha.id)

    assert await _contar(seeded.alpha.id) == TOTAL_APROBADO == 28
    async with async_session_maker() as session:
        con_marca = await session.scalar(
            text(
                "SELECT count(*) FROM standard_value "
                "WHERE company_id = :c AND seed_key IS NOT NULL"
            ),
            {"c": seeded.alpha.id},
        )
    assert con_marca == 28, "todo lo sembrado queda marcado como sembrado"


async def test_the_second_run_changes_nothing(seeded):
    await _sembrar(seeded.alpha.id)

    async with async_session_maker() as session:
        antes = (
            await session.execute(
                text(
                    "SELECT id, label, sort_order, is_active, updated_at "
                    "FROM standard_value WHERE company_id = :c ORDER BY id"
                ),
                {"c": seeded.alpha.id},
            )
        ).all()

    await _sembrar(seeded.alpha.id)

    async with async_session_maker() as session:
        despues = (
            await session.execute(
                text(
                    "SELECT id, label, sort_order, is_active, updated_at "
                    "FROM standard_value WHERE company_id = :c ORDER BY id"
                ),
                {"c": seeded.alpha.id},
            )
        ).all()

    assert despues == antes, "ni una fila nueva, ni una fila tocada"


# ── Las tres decisiones del tenant ───────────────────────────────────────────


async def test_a_renamed_seeded_value_is_not_reset(seeded, alpha_client):
    """Si el tenant lo renombró, sabía lo que hacía."""
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valores = (
        await alpha_client.get("/api/standard-values/office_purposes")
    ).json()
    objetivo = next(v for v in valores if v["label"] == "Paperwork")
    renombrado = await alpha_client.put(
        f"/api/standard-values/{objetivo['id']}", json={"label": "Trámites"}
    )
    assert renombrado.status_code == 200

    await _sembrar(seeded.alpha.id)

    etiquetas = [
        v["label"]
        for v in (await alpha_client.get("/api/standard-values/office_purposes")).json()
    ]
    assert "Trámites" in etiquetas, "el nombre del tenant sobrevive"
    assert "Paperwork" not in etiquetas, "y no reaparece el original al lado"
    assert await _contar(seeded.alpha.id) == 28, "sin duplicar"


async def test_a_deactivated_seeded_value_is_not_reactivated(seeded, alpha_client):
    """Retirado del uso operativo, se queda retirado."""
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valores = (await alpha_client.get("/api/standard-values/outcomes")).json()
    objetivo = next(v for v in valores if v["label"] == "Escalated")
    await alpha_client.put(
        f"/api/standard-values/{objetivo['id']}", json={"is_active": False}
    )

    await _sembrar(seeded.alpha.id)

    activos = [
        v["label"] for v in (await alpha_client.get("/api/standard-values/outcomes")).json()
    ]
    assert "Escalated" not in activos, "no se reactiva solo"
    assert await _contar(seeded.alpha.id) == 28, "ni se crea un gemelo activo"


async def test_a_deleted_seeded_value_is_not_resurrected(seeded, alpha_client):
    """Borrado como lápida: el segundo sembrado no lo revive."""
    await _sembrar(seeded.alpha.id)
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    valores = (await alpha_client.get("/api/standard-values/received_by")).json()
    objetivo = next(v for v in valores if v["label"] == "Office Staff")
    borrado = await alpha_client.delete(f"/api/standard-values/{objetivo['id']}")
    assert borrado.status_code == 204

    await _sembrar(seeded.alpha.id)

    etiquetas = [
        v["label"] for v in (await alpha_client.get("/api/standard-values/received_by")).json()
    ]
    assert "Office Staff" not in etiquetas, "lo borrado no vuelve"
    assert await _contar(seeded.alpha.id) == 28, "y no se crea otro con el mismo nombre"

    # La lápida sigue ahí: una actividad de marzo guardó ese identificador y
    # tiene que poder resolverlo.
    async with async_session_maker() as session:
        lapida = await session.scalar(
            text(
                "SELECT count(*) FROM standard_value "
                "WHERE company_id = :c AND deleted_at IS NOT NULL"
            ),
            {"c": seeded.alpha.id},
        )
    assert lapida == 1


async def test_a_tenant_authored_value_is_never_touched(seeded, alpha_client):
    """Lo que creó el administrador no lleva `seed_key` y no le concierne."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    propio = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "other_activities", "label": "Visita al taller"},
    )
    assert propio.status_code == 200

    await _sembrar(seeded.alpha.id)

    etiquetas = [
        v["label"]
        for v in (await alpha_client.get("/api/standard-values/other_activities")).json()
    ]
    assert "Visita al taller" in etiquetas
    assert await _contar(seeded.alpha.id) == 29, "los 28 aprobados más el suyo"

    async with async_session_maker() as session:
        sin_marca = await session.scalar(
            text(
                "SELECT count(*) FROM standard_value "
                "WHERE company_id = :c AND seed_key IS NULL"
            ),
            {"c": seeded.alpha.id},
        )
    assert sin_marca == 1, "lo del tenant no se marca como sembrado"


def test_the_seed_key_derives_from_the_approved_label_not_the_current_one():
    """La identidad estable: sobrevive al renombrado, que es su razón de ser."""
    clave = seed_key_for("office_purposes", "Paperwork")
    assert clave == seed_key_for("office_purposes", "Paperwork")
    assert clave != seed_key_for("office_purposes", "Trámites")
    assert clave != seed_key_for("other_activities", "Paperwork"), (
        "la lista forma parte de la identidad"
    )


# ── Los grants, contra el catálogo ───────────────────────────────────────────


async def test_a_freshly_seeded_tenant_matches_the_capability_catalog(seeded):
    """Lo que la resolución pide: los grants coinciden con el catálogo.

    Se comprueba sobre un tenant recién sembrado. En un tenant que ya existía
    puede haber capacidades **de más**: el bootstrap alinea lo que falta y nunca
    revoca, así que una capacidad retirada del catálogo sigue concedida. Es una
    propiedad del mecanismo, no un fallo — y hay que conocerla, porque retirar
    una capacidad exige una acción operativa que el bootstrap no hace.
    """
    async with async_session_maker() as session:
        for plantilla in DEFAULT_ROLES:
            esperadas = set(capabilities_for(plantilla))
            filas = await session.execute(
                text(
                    "SELECT p.name FROM role r "
                    "JOIN role_permission rp ON rp.role_id = r.id "
                    "JOIN permission p ON p.id = rp.permission_id "
                    "WHERE r.name = :n AND r.company_id = :c"
                ),
                {"n": plantilla.name, "c": seeded.alpha.id},
            )
            reales = {f[0] for f in filas.all()}
            assert reales == esperadas, (
                f"'{plantilla.name}': faltan {sorted(esperadas - reales)}, "
                f"sobran {sorted(reales - esperadas)}"
            )


async def test_every_catalogued_capability_is_seeded(seeded):
    """Sin esto, un endpoint devuelve 403 a todo el mundo y nadie lo nota.

    Es el incidente AUD-DB-001, y es exactamente lo que le pasaba al `supervisor`
    del entorno revisado: `route.worksession.execute` no estaba sembrada, así que
    su rol tenía cero capacidades y toda la experiencia de campo devolvía 403.
    """
    async with async_session_maker() as session:
        filas = await session.execute(text("SELECT name FROM permission"))
        sembradas = {f[0] for f in filas.all()}

    del_catalogo = {c.name for c in CAPABILITIES}
    assert del_catalogo <= sembradas, (
        f"sin sembrar: {sorted(del_catalogo - sembradas)}"
    )


async def test_the_supervisor_is_never_left_without_operational_capability(seeded):
    """La condición que la resolución nombra: ya no se queda a cero."""
    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT p.name FROM role r "
                "JOIN role_permission rp ON rp.role_id = r.id "
                "JOIN permission p ON p.id = rp.permission_id "
                "WHERE r.name = 'supervisor' AND r.company_id = :c"
            ),
            {"c": seeded.alpha.id},
        )
        concedidas = {f[0] for f in filas.all()}

    assert "route.worksession.execute" in concedidas
    assert "route.standardvalues.read" in concedidas
    assert len(concedidas) == 2, f"Read + Execute y nada más: {sorted(concedidas)}"


async def test_the_two_product_roles_hold_exactly_twelve_and_two_capabilities(
    seeded,
):
    """Los números que la resolución fija como criterio de aceptación.

    Se comprueban por separado del contraste con el catálogo porque son un hecho
    del producto, no un detalle de implementación: que el Administrador tenga
    doce y el Supervisor dos es lo que CER certifica. Si mañana alguien añade una
    capacidad a una plantilla sin pasar por CER, esto falla y obliga a decirlo.
    """
    esperado = {"route_admin": 12, "supervisor": 2}

    async with async_session_maker() as session:
        for nombre, cuantas in esperado.items():
            filas = await session.execute(
                text(
                    "SELECT p.name FROM role r "
                    "JOIN role_permission rp ON rp.role_id = r.id "
                    "JOIN permission p ON p.id = rp.permission_id "
                    "WHERE r.name = :n AND r.company_id = :c"
                ),
                {"n": nombre, "c": seeded.alpha.id},
            )
            concedidas = {f[0] for f in filas.all()}

            assert len(concedidas) == cuantas, (
                f"'{nombre}': {len(concedidas)} capacidades, se esperaban "
                f"{cuantas} — {sorted(concedidas)}"
            )
            assert "roles.read" not in concedidas, (
                f"'{nombre}' no debe leer el catálogo de roles del tenant"
            )
