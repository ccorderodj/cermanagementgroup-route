"""La convergencia del despliegue: repone lo que falta y no pisa lo que hay.

Qué defiende este archivo
--------------------------
Que un despliegue pueda **restaurar** la configuración que un despliegue puede
perder, sin convertirse a cambio en algo que sobrescribe decisiones.

Las dos mitades importan por igual y tiran en direcciones opuestas:

* si no repone, el incidente se repite — la integración de routing desapareció
  y el kilometraje estuvo seis días sin calcular;
* si repone de más, un administrador que eligió otro proveedor en la pantalla
  vería su decisión revertida en el siguiente despliegue, sin avisar.

Por eso casi todos los tests de aquí son del tipo «no tocó lo que no debía».
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.platform.models import PlatformIntegration, PlatformSecret
from app.database import async_session_maker
from app.db.scripts.converge import (
    CLAVE_ROUTING,
    PROVEEDOR_ROUTING,
    SECRETO_ROUTING,
    converger,
)
from app.routers_api.companies.models import Company
from app.routers_api.users.models import Users

pytestmark = pytest.mark.integration

CLAVE_DE_PRUEBA = "clave-de-tomtom-para-la-prueba"


@pytest.fixture
def master_key(monkeypatch):
    """Una llave maestra viva: sin ella no se puede cifrar nada."""
    from app.config import settings
    from app.core.platform import secrets

    clave = secrets.generate_master_key()
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY", clave)
    monkeypatch.setattr(settings, "PLATFORM_MASTER_KEY_PREVIOUS", "")
    return clave


@pytest.fixture
def con_clave(monkeypatch):
    """Como si el App Spec trajera `ROUTE_TOMTOM_API_KEY`."""
    from app.config import settings

    monkeypatch.setattr(settings, "ROUTE_TOMTOM_API_KEY", CLAVE_DE_PRUEBA)


async def _integracion() -> PlatformIntegration | None:
    async with async_session_maker() as session:
        return await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == CLAVE_ROUTING)
        )


async def _secretos(integration_id: int) -> list[str]:
    async with async_session_maker() as session:
        return list(
            (
                await session.scalars(
                    select(PlatformSecret.name).where(
                        PlatformSecret.integration_id == integration_id
                    )
                )
            ).all()
        )


# ── Reponer lo que falta ────────────────────────────────────────────────────


async def test_repone_la_integracion_que_desaparecio(seeded, master_key, con_clave):
    """El caso de campo: la fila no está, y el despliegue la devuelve."""
    assert await _integracion() is None, "la preparación ya traía integración"

    await converger()

    fila = await _integracion()
    assert fila is not None, "el despliegue no repuso la integración perdida"
    assert fila.provider == PROVEEDOR_ROUTING
    assert fila.enabled is True
    assert SECRETO_ROUTING in await _secretos(fila.id)


async def test_la_clave_queda_cifrada_y_se_puede_volver_a_leer(
    seeded, master_key, con_clave
):
    """Cifrada con la llave maestra, no en claro, y descifrable."""
    from app.core.platform.secrets import unseal

    await converger()
    fila = await _integracion()

    async with async_session_maker() as session:
        secreto = await session.scalar(
            select(PlatformSecret).where(
                PlatformSecret.integration_id == fila.id,
                PlatformSecret.name == SECRETO_ROUTING,
            )
        )

    assert CLAVE_DE_PRUEBA.encode() not in secreto.ciphertext, (
        "la clave quedó legible en la base"
    )
    assert (
        unseal(
            integration_key=CLAVE_ROUTING,
            secret_name=SECRETO_ROUTING,
            ciphertext=secreto.ciphertext,
            nonce=secreto.nonce,
            stored_key_id=secreto.key_id,
        )
        == CLAVE_DE_PRUEBA
    )


async def test_guarda_la_clave_cuando_la_fila_sobrevivio_pero_el_secreto_no(
    seeded, master_key, con_clave
):
    """El otro modo de fallo, y produce el mismo síntoma.

    La integración está, habilitada y con proveedor, pero sin credencial. El
    adaptador no se monta —`_desde_la_integracion` devuelve `None`— y desde
    fuera se ve igual que no tener integración: kilometraje pendiente y luego
    terminal.
    """
    await converger()
    fila = await _integracion()
    async with async_session_maker() as session:
        secreto = await session.scalar(
            select(PlatformSecret).where(PlatformSecret.integration_id == fila.id)
        )
        await session.delete(secreto)
        await session.commit()

    assert await _secretos(fila.id) == []

    await converger()

    assert SECRETO_ROUTING in await _secretos(fila.id)


# ── No pisar lo que hay ─────────────────────────────────────────────────────


async def test_no_cambia_el_proveedor_que_un_administrador_eligio(
    seeded, master_key, con_clave
):
    """Si alguien configuró OSRM en la pantalla, eso manda.

    Es la mitad que impide que esto se convierta en un problema peor que el que
    resuelve: un despliegue que revierte decisiones en silencio.
    """
    async with async_session_maker() as session:
        session.add(
            PlatformIntegration(
                key=CLAVE_ROUTING,
                provider="osrm",
                enabled=True,
                config={"base_url": "http://osrm.interno:5000"},
                version=1,
            )
        )
        await session.commit()

    await converger()

    fila = await _integracion()
    assert fila.provider == "osrm", "el despliegue revirtió la decisión del administrador"
    assert fila.config["base_url"] == "http://osrm.interno:5000"
    assert await _secretos(fila.id) == [], "guardó una clave de TomTom en una integración OSRM"


async def test_respeta_una_integracion_deshabilitada_a_proposito(
    seeded, master_key, con_clave
):
    """Deshabilitar es una decisión, no una ausencia."""
    await converger()
    async with async_session_maker() as session:
        fila = await session.scalar(
            select(PlatformIntegration).where(PlatformIntegration.key == CLAVE_ROUTING)
        )
        fila.enabled = False
        await session.commit()

    await converger()

    assert (await _integracion()).enabled is False, "volvió a habilitarla sola"


async def test_sin_la_variable_de_entorno_no_toca_nada(seeded, master_key):
    """Un entorno con motor auto-alojado, o sin proveedor todavía, se queda igual."""
    await converger()
    assert await _integracion() is None, (
        "inventó una integración sin que nadie diera una clave"
    )


# ── Idempotencia y límites ──────────────────────────────────────────────────


async def test_la_segunda_ejecucion_no_cambia_nada(seeded, master_key, con_clave):
    """Correrlo en cada despliegue no puede costar nada."""
    primera = await converger()
    assert sum(r.cambios for r in primera) > 0

    segunda = await converger()
    assert sum(r.cambios for r in segunda) == 0, (
        "la segunda pasada cambió algo: no es idempotente y no se puede poner "
        f"en un despliegue: {[(r.paso, r.detalle) for r in segunda if r.cambios]}"
    )


async def test_no_crea_companias_ni_usuarios(seeded, master_key, con_clave):
    """Converger reconcilia; crear es una decisión y sigue siendo del bootstrap."""
    async with async_session_maker() as session:
        companias_antes = len((await session.scalars(select(Company.id))).all())
        usuarios_antes = len((await session.scalars(select(Users.id))).all())

    await converger()

    async with async_session_maker() as session:
        assert len((await session.scalars(select(Company.id))).all()) == companias_antes
        assert len((await session.scalars(select(Users.id))).all()) == usuarios_antes


async def test_alinea_las_capacidades_de_todas_las_companias(
    seeded, master_key, con_clave
):
    """El paso que ya mordió cuatro veces, ahora dentro del despliegue."""
    from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for
    from app.routers_api.permissions.models import Permission
    from app.routers_api.rolepermissions.models import RolePermission
    from app.routers_api.roles.models import Role

    await converger()

    for compania in (seeded.alpha, seeded.beta):
        for plantilla in DEFAULT_ROLES:
            async with async_session_maker() as session:
                role_id = await session.scalar(
                    select(Role.id).where(
                        Role.company_id == compania.id, Role.name == plantilla.name
                    )
                )
                if role_id is None:
                    continue
                concedidas = set(
                    (
                        await session.scalars(
                            select(Permission.name)
                            .join(
                                RolePermission,
                                RolePermission.permission_id == Permission.id,
                            )
                            .where(RolePermission.role_id == role_id)
                        )
                    ).all()
                )
            faltan = set(capabilities_for(plantilla)) - concedidas
            assert not faltan, f"{compania.subdomain}/{plantilla.name} sin {faltan}"
