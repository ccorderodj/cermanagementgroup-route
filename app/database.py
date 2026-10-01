"""
Motor y sesión de base de datos.

`MODE=TEST` apunta a `TEST_DATABASE_URL`, una base **distinta** de la de
desarrollo. Esto estaba a medio desmontar: `config.py` tenía la variable
comentada mientras este archivo seguía leyéndola, así que arrancar en modo TEST
fallaba con `AttributeError` y el modo de test declarado era inutilizable
(AUD-BE-002). `config.py` valida ahora que la URL exista y que no coincida con
la de desarrollo, porque la suite recrea el esquema.
"""

from typing import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
from app.core.database.query_profiler import (
    after_cursor_execute,
    before_cursor_execute,
)


if settings.is_testing:
    DATABASE_URL = settings.TEST_DATABASE_URL
    # Se reutilizan las conexiones, igual que en producción.
    #
    # Antes no había pool, con el motivo de que mantendría vivas conexiones que
    # impiden borrar la base al terminar. Ese motivo ya no se corresponde con el
    # código: `tests/conftest.py::_reset_schema` no borra la base, hace
    # `DROP SCHEMA public CASCADE` y acto seguido `await engine.dispose()`, que
    # cierra el pool entero. Y sólo se llama en los dos extremos de la sesión de
    # pytest, con el pool vacío en el primero.
    #
    # Lo que costaba, medido sobre 520 conexiones en 90 s de suite: cada
    # conexión vivía 156 ms para ejecutar 6,1 ms de consultas —el 96 % de su
    # vida era el saludo TCP y la autenticación—, y un test de integración abre
    # unas 16, que son ~2,5 s de los 2,74 s que tardaba.
    #
    # No cambia ninguna aserción: cambia cuántas veces se paga abrir la
    # conexión. `pool_pre_ping` está por el mismo motivo que en producción, y
    # aquí además cubre que una conexión sobreviva a un `DROP SCHEMA`. Los
    # tamaños son los que el propio proyecto declara en `config.py`: no se
    # inventa aquí una capacidad distinta de la que ya está decidida.
    DATABASE_PARAMS: dict = {
        "pool_pre_ping": True,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_POOL_MAX_OVERFLOW,
    }
else:
    DATABASE_URL = settings.DATABASE_URL
    DATABASE_PARAMS = {
        # Una conexión que el servidor cerró por inactividad no se detecta hasta
        # que se usa: sin esto, la primera petición tras un corte de red o un
        # reinicio de PostgreSQL falla (AUD-DB-010).
        "pool_pre_ping": True,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_POOL_MAX_OVERFLOW,
        "pool_recycle": 1800,
    }


engine = create_async_engine(DATABASE_URL, **DATABASE_PARAMS)


# El perfilador de consultas cuelga del engine síncrono que hay debajo del
# AsyncEngine. Alimenta las métricas `app_api_sql_queries_per_request` y
# `app_api_database_duration_seconds`.
event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
event.listen(engine.sync_engine, "after_cursor_execute", after_cursor_execute)


async_session_maker: Callable[[], AsyncSession] = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
