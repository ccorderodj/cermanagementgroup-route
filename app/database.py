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


def libpq_dsn(url: str = "") -> str:
    """La misma base, en la forma que entiende `asyncpg.connect()` a pelo.

    Dos traducciones, y la segunda costó un incidente
    -------------------------------------------------
    1. `postgresql+asyncpg://` es el dialecto de SQLAlchemy; libpq quiere
       `postgresql://`.
    2. **`ssl=` pasa a `sslmode=`.** Es el que importa. SQLAlchemy acepta
       `?ssl=require` y lo traduce al llamar al driver, pero `asyncpg.connect()`
       recibe la cadena tal cual y no reconoce `ssl` como opción de conexión:
       lo manda al servidor como parámetro de sesión, y PostgreSQL responde

           CantChangeRuntimeParamError: parameter "ssl" cannot be changed now

       y la conexión **no se abre**. No es que se ignore y quede sin cifrar —
       que es lo que se supuso la primera vez— sino que falla entera.

    Qué se rompía cuando fallaba
    ----------------------------
    Las dos únicas conexiones crudas del proyecto, y ninguna de las dos avisa a
    gritos:

    * el escucha de configuración de plataforma, que deja de enterarse de los
      cambios de integraciones y políticas;
    * la elección de líder del scheduler — y sin líder **ningún trabajo
      programado se ejecuta**. Los jobs siguen apareciendo en el log como
      "executed successfully" porque `_only_leader` los envuelve y el envoltorio
      sí termina bien; lo que no corre es el trabajo de dentro. Un barrido de
      millaje que no barre y una purga que no purga, en silencio.

    Por eso esto vive aquí y no duplicado en cada sitio: hay dos llamadas
    crudas, y la tercera que alguien escriba debe encontrar la traducción hecha.
    """
    cruda = url or DATABASE_URL
    sin_dialecto = cruda.replace("postgresql+asyncpg://", "postgresql://", 1)
    return sin_dialecto.replace("?ssl=", "?sslmode=").replace("&ssl=", "&sslmode=")


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
