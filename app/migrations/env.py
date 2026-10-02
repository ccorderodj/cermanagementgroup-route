import sys
import importlib
from pathlib import Path
from os.path import abspath, dirname
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
"""
    Example:
    Let's say the script is located at:

    swift
    Copy
    /home/user/project/module/submodule/script.py
    abspath(__file__) would give /home/user/project/module/submodule/script.py.
    dirname(abspath(__file__)) would give /home/user/project/module/submodule.
    dirname(dirname(abspath(__file__))) would give /home/user/project/module.
    dirname(dirname(dirname(abspath(__file__)))) would give /home/user/project.
    So, the line would insert /home/user/project into sys.path, making Python able to find modules in
"""

sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))

from app.database import Base
# La URL **ya resuelta**, no `settings.DATABASE_URL`.
#
# `app/database.py` elige `TEST_DATABASE_URL` cuando MODE=TEST; el atributo
# `settings.DATABASE_URL` sigue apuntando siempre a la base de desarrollo. Usar
# el atributo hacia que `MODE=TEST alembic upgrade head` migrara la base de
# DESARROLLO mientras la suite se conectaba a la base de tests vacia: todos los
# tests de integracion habrian fallado con "relation does not exist", y la
# migracion se habria aplicado a la base equivocada.
from app.database import DATABASE_URL as RESOLVED_DATABASE_URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# El separador depende de si la URL ya trae query string, y eso dejó de ser
# hipotético: en cuanto `DB_SSL` añade `?ssl=require`, concatenar otro `?` deja
# una URL malformada y la conexión falla por un motivo que no tiene nada que ver
# con la migración.
_SEPARADOR = "&" if "?" in RESOLVED_DATABASE_URL else "?"
config.set_main_option(
    "sqlalchemy.url", f"{RESOLVED_DATABASE_URL}{_SEPARADOR}async_fallback=True"
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.
def import_all_models() -> None:
    """
    Load every models.py under app/routers_api and app/core.

    Un modelo que no se importa no está en `Base.metadata`, y el autogenerate
    propone entonces BORRAR su tabla. `app/core` entró en la lista cuando
    aparecieron los modelos compartidos (auditoría): viven fuera de un dominio
    a propósito, y quedarse fuera del recorrido los hacía invisibles aquí.
    """
    app_dir = Path(dirname(dirname(abspath(__file__))))

    for package, directory in (
        ("app.routers_api", app_dir / "routers_api"),
        ("app.core", app_dir / "core"),
    ):
        for model_file in sorted(directory.rglob("models.py")):
            module_rel = model_file.relative_to(directory).with_suffix("")
            module_name = ".".join(module_rel.parts)
            try:
                importlib.import_module(f"{package}.{module_name}")
            except ModuleNotFoundError:
                continue


def include_object(object, name, type_, reflected, compare_to):
    # Include all ORM tables by default.
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    import_all_models()

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    import_all_models()

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
