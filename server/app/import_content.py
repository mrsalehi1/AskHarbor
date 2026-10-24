"""Import bot content files into the database.

Usage, from server/ with the environment active and ASKHARBOR_DATABASE_URL set:

    python -m app.import_content                # import server/content
    python -m app.import_content path/to/dir    # import another directory
    python -m app.import_content --replace      # overwrite bots that already exist

The whole batch is validated before anything is written and all rows are
committed in one transaction: if any file is invalid, or the database rejects
any row, nothing changes. Without --replace, a bot whose ID already exists in
the database is skipped and reported.
"""

import argparse
import sys
from pathlib import Path

from .config import get_settings
from .content import ContentLoadError
from .db import session_factory
from .storage import assert_database_ready, import_documents

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=None,
        help="Directory of bot content files (default: the configured content directory)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite bots whose ID already exists instead of skipping them",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.database_url:
        print(
            "ASKHARBOR_DATABASE_URL is not set. The import command writes to PostgreSQL; "
            "see 'PostgreSQL storage' in README.md.",
            file=sys.stderr,
        )
        return 2
    directory = args.directory if args.directory is not None else settings.content_dir

    factory = session_factory(settings.database_url)
    assert_database_ready(factory.kw["bind"], ALEMBIC_DIR)
    try:
        with factory() as session, session.begin():
            report = import_documents(session, directory, replace=args.replace)
    except ContentLoadError as error:
        print(f"Nothing was imported.\n{error}", file=sys.stderr)
        return 1
    print(f"Import finished: {report.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
