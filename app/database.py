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

from sqlalchemy import NullPool, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
from app.core.database.query_profiler import (
    after_cursor_execute,
    before_cursor_execute,
)


if settings.is_testing:
    DATABASE_URL = settings.TEST_DATABASE_URL
    # Sin pool: cada test abre y cierra su conexión, y el pool mantiene vivas
    # conexiones que impiden borrar la base al terminar.
    DATABASE_PARAMS: dict = {"poolclass": NullPool}
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
