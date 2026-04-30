import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing the models modules ensures every model class is registered
# with the metadata before autogenerate runs.
from romarr.auth import models as _auth_models  # noqa: F401
from romarr.config import get_settings
from romarr.domain import (
    Base,
    models,  # noqa: F401
)
from romarr.downloaders import models as _downloader_models  # noqa: F401
from romarr.indexers import models as _indexer_models  # noqa: F401
from romarr.metadata import models as _metadata_models  # noqa: F401
from romarr.platform_packs import models as _platform_pack_models  # noqa: F401
from romarr.profiles import models as _profile_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use Romarr's runtime settings for the DB URL UNLESS the caller (e.g.,
# a test, or `alembic -x url=...`) has already overridden alembic.ini's
# placeholder. That way `ROMARR_DATABASE_URL` is the production knob,
# and `Config.set_main_option("sqlalchemy.url", ...)` from a test
# wins for that invocation.
_PLACEHOLDER_URL = "sqlite+aiosqlite:///./romarr.db"
_current_url = config.get_main_option("sqlalchemy.url")
if not _current_url or _current_url == _PLACEHOLDER_URL:
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support.
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
