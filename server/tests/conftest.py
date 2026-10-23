import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app import main
from app.orm import Base

# Database tests run only against a disposable PostgreSQL named by this variable.
TEST_URL_VAR = "ASKHARBOR_TEST_DATABASE_URL"
TEST_URL = os.environ.get(TEST_URL_VAR, "")
SERVER_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_DIR = SERVER_DIR / "alembic"

requires_database = pytest.mark.skipif(
    not TEST_URL,
    reason=f"set {TEST_URL_VAR} to a disposable PostgreSQL database to run these",
)


@pytest.fixture(autouse=True)
def reset_message_limiter():
    """Keep the in-memory request counter from leaking between tests."""
    main.message_limiter.reset()
    yield
    main.message_limiter.reset()


@pytest.fixture(scope="session")
def engine():
    """A test database migrated from scratch with Alembic, the deployment path."""
    if not TEST_URL:
        pytest.skip(f"set {TEST_URL_VAR} to a disposable PostgreSQL database")
    engine = create_engine(TEST_URL)
    alembic_config = Config(str(SERVER_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(ALEMBIC_DIR))
    # Hand the URL to alembic directly rather than through the environment, so the
    # rest of the suite keeps running in file mode with accounts disabled.
    alembic_config.set_main_option("sqlalchemy.url", TEST_URL)
    # A disposable database: wipe whatever is there instead of trusting its
    # alembic state, then build the schema the way a deployment does.
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def clean_database(engine):
    """Every table empty before the test."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        connection.commit()
    yield engine


@pytest.fixture
def session(clean_database):
    with Session(clean_database) as session:
        yield session
