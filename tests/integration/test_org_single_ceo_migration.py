"""
Migración 0019: un único CEO vigente por compañía.

* Con dos CEO vigentes en un tenant, la subida **se detiene** sin aplicar nada
  y dice qué compañía: no elige a nadie.
* Regularizado, sube y el índice existe; bajar lo quita y volver a subir no
  duplica nada.

Siempre devuelven la base al head.
"""

from __future__ import annotations

import pytest

from tests.integration.test_route_roles_migration import HEAD, _alembic, _ejecutar, _filas, _subir_o_fallar

pytestmark = pytest.mark.integration

ANTES = "0018_route_distinct_roles"


async def _indice() -> bool:
    return bool(await _filas("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_org_assignment_one_ceo'"))


async def test_dos_ceo_vigentes_detienen_la_migracion_sin_cambios(seeded) -> None:
    bajada = _alembic("downgrade", ANTES)
    assert bajada.returncode == 0, bajada.stdout + bajada.stderr
    try:
        assert not await _indice()
        await _ejecutar(
            "INSERT INTO org_assignment (company_id, user_id, position, valid_from, version) "
            "VALUES (:c, :u, 'ceo', now(), 1)",
            c=seeded.alpha.id, u=seeded.alpha.users["viewer"].id,
        )
        subida = _alembic("upgrade", HEAD)
        assert subida.returncode != 0
        salida = subida.stdout + subida.stderr
        assert f"company {seeded.alpha.id}: 2 CEOs" in salida
        assert "Nothing was changed" in salida
        assert (await _filas("SELECT version_num FROM alembic_version"))[0].version_num == ANTES
        assert not await _indice()
        # Nadie fue elegido ni borrado.
        n = await _filas(
            "SELECT count(*) AS n FROM org_assignment WHERE company_id = :c AND position = 'ceo' AND valid_to IS NULL",
            c=seeded.alpha.id,
        )
        assert n[0].n == 2
        await _ejecutar(
            "DELETE FROM org_assignment WHERE user_id = :u", u=seeded.alpha.users["viewer"].id
        )
    finally:
        _subir_o_fallar()
    assert await _indice()


async def test_bajar_y_subir_es_limpio(seeded) -> None:
    assert await _indice()
    bajada = _alembic("downgrade", ANTES)
    try:
        assert bajada.returncode == 0, bajada.stdout + bajada.stderr
        assert not await _indice()
    finally:
        _subir_o_fallar()
    assert await _indice()
    assert (await _filas("SELECT version_num FROM alembic_version"))[0].version_num == HEAD
