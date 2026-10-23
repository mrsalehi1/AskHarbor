"""Alembic environment: migrations read the URL from the app settings."""

from sqlalchemy import create_engine

from alembic import context
from app.config import Settings
from app.orm import Base

target_metadata = Base.metadata


def _database_url() -> str:
    # A fresh Settings instance, not the app's cached one: migrations are often
    # run with a different URL in the environment than the process started with,
    # for example by the test suite.
    url = context.config.get_main_option("sqlalchemy.url") or Settings().database_url
    if not url:
        raise SystemExit(
            "ASKHARBOR_DATABASE_URL is not set. Migrations need a PostgreSQL URL; "
            "see 'PostgreSQL storage' in README.md."
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
