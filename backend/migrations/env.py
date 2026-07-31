import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import get_settings
from src.core.database import Base
from src.models import *  # noqa: F401, F403 – ensure all models are imported

# Alembic Config object
config = context.config
settings = get_settings()

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from application settings
# Use config.attributes dict to avoid ConfigParser %-interpolation issues with
# URL-encoded characters in the database URL (e.g. %40 for @ in passwords).
config.attributes["sqlalchemy.url"] = settings.database_url

# Metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.  Calls to
    context.execute() here emit the given string to the script output.
    """
    url = config.attributes.get("sqlalchemy.url")
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
    """Run migrations in 'online' mode using an async engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    url = config.attributes.get("sqlalchemy.url")
    connectable = create_async_engine(url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point called by Alembic for online migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
