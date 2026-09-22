"""
Infraestructura de la suite de tests.

Base de datos
-------------
**PostgreSQL 14 real, nunca SQLite** (D15). Media plataforma depende de cosas
que SQLite no tiene —índices únicos parciales, `JSONB`, claves foráneas
compuestas, `timestamptz`, `ilike`—, así que una suite sobre SQLite daría verde
mientras la aplicación real falla.

El ciclo por sesión de pytest es:

    1. crear la base de tests (o vaciarla si ya existe)
    2. `alembic upgrade head`   <- se prueba la migración, no `create_all`
    3. ejecutar los tests
    4. borrar el esquema

Usar Alembic y no `Base.metadata.create_all()` es deliberado: así los tests
corren contra el esquema que produce la migración, que es el que va a existir en
producción. Con `create_all` una migración rota pasaría desapercibida.

Aislamiento entre tests
-----------------------
Cada test corre dentro de una transacción que se deshace al terminar. Las
sesiones que abre la aplicación se enganchan a esa misma conexión mediante la
transacción ambiental de `app.core.db.session`, así que un test no puede ver ni
dejar datos de otro.

Cómo se ejecuta
---------------
    MODE=TEST TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest

La base indicada debe existir y el rol debe poder crear objetos en ella. Ver
`docs/technical-remediation/07-TESTING-AND-CI.md`.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

# La configuración se valida al importar `app.config`, así que el modo tiene que
# estar puesto antes de que ningún módulo de la aplicación entre en escena.
os.environ.setdefault("MODE", "TEST")
# El correo no sale a la red durante los tests: se acumula en memoria y se
# puede inspeccionar (ver la fixture `outbox`).
os.environ["EMAIL_BACKEND"] = "memory"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: necesita una base PostgreSQL 14 real (TEST_DATABASE_URL)",
    )


# ── Utilidades de base de datos ─────────────────────────────────────────────


def _run_alembic(command: str) -> None:
    """Ejecuta Alembic contra la base de tests, en un proceso aparte.

    En un proceso aparte porque `env.py` construye su propio engine desde la
    configuración; compartirlo con el de la sesión de pytest mezcla dos bucles
    de eventos.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "app/alembic.ini", command, "head"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "MODE": "TEST"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {command} falló en la base de tests:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def database_schema():
    """Deja la base de tests vacía y con el esquema al día, y la limpia al salir.

    **No es `autouse`** a propósito: los tests de cableado de páginas, catálogo
    de capacidades y superficie pública no tocan la base, y deben poder
    ejecutarse en cualquier máquina sin PostgreSQL. Solo las fixtures de
    integración la piden.
    """
    from app.config import settings

    if not settings.is_testing:
        pytest.exit(
            "La suite necesita MODE=TEST. Sin eso apuntaría a la base de "
            "desarrollo, y el ciclo de vida de esta fixture la vaciaría.",
            returncode=1,
        )

    _reset_schema()
    _run_alembic("upgrade")
    yield
    _reset_schema()


def _reset_schema() -> None:
    """Vacía el esquema `public` de la base de TESTS.

    La comprobación de `is_testing` está en la fixture, y `config.py` ya
    garantiza que `TEST_DATABASE_URL` no coincide con `DATABASE_URL`. Son dos
    barreras para la misma cosa a propósito: esta función borra tablas.
    """
    from sqlalchemy import text

    from app.database import engine

    async def _drop() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(_drop())


# ── Fixtures de aplicación ──────────────────────────────────────────────────


@pytest.fixture
def outbox():
    """Bandeja de salida en memoria. Se vacía antes de cada test."""
    from app.core.email.backends import MemoryEmailBackend, set_email_backend

    backend = MemoryEmailBackend()
    set_email_backend(backend)
    yield backend
    set_email_backend(None)


@pytest.fixture(autouse=True)
def clean_tenant_cache():
    """La resolución de tenant cachea 60 s; entre tests hay que olvidarla."""
    from app.core.middleware.company_resolver_middleware import invalidate_tenant_cache

    invalidate_tenant_cache()
    yield
    invalidate_tenant_cache()


@pytest.fixture(autouse=True)
def _platform_config_vacia():
    """Cada test empieza sin configuración de plataforma en memoria.

    La instantánea sobrevive entre tests dentro del mismo proceso. Sin esto, un
    test que configura un escáner o un bucket haría que las subidas de los tests
    siguientes intentaran hablar con Cloudmersive o con S3.
    """
    from app.core.platform.config_service import platform_config

    platform_config.reset()
    yield
    platform_config.reset()
