"""Database-backed bot content: reads, revision-checked saves and import.

The public widget endpoints only need ``get(bot_id)``. ``DatabaseContentSource``
provides it with the same return type as the file repository, so the endpoints
and their responses are identical in both modes. Documents are validated with
the shared content rules before they are written, never on the way out.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from .content import (
    definition_from_document,
    load_content_documents,
    validate_bot_content,
)
from .models import BotDefinition
from .orm import BotContent, Website

ORIGIN_PATTERN = re.compile(r"^https?://[^/\s]+$")
DOMAIN_PATTERN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")

logger = logging.getLogger("askharbor")


class RevisionConflict(Exception):
    """A save named a revision that is no longer current.

    Someone else saved in between. The caller must reload revision
    ``current_revision``, reapply the change and save again; nothing was
    written.
    """

    def __init__(self, website_slug: str, expected_revision: int, current_revision: int) -> None:
        self.website_slug = website_slug
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            f"Bot content for '{website_slug}' is at revision {current_revision}, "
            f"not {expected_revision}. Reload the content and apply the change again."
        )


class DatabaseContentSource:
    """Serves bot definitions from the database, keyed by website slug."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        # Built definitions keyed by slug, invalidated by revision, so a busy
        # widget does not re-validate an unchanged document on every request.
        self._cache: dict[str, tuple[int, BotDefinition]] = {}

    def get(self, bot_id: str) -> BotDefinition | None:
        with self._factory() as session:
            row = session.execute(
                select(BotContent.document, BotContent.revision)
                .join(Website, Website.id == BotContent.website_id)
                .where(Website.slug == bot_id)
            ).first()
        if row is None:
            return None
        document, revision = row
        cached = self._cache.get(bot_id)
        if cached is not None and cached[0] == revision:
            return cached[1]
        definition = definition_from_document(document)
        self._cache[bot_id] = (revision, definition)
        return definition

    def ids(self) -> list[str]:
        with self._factory() as session:
            slugs = session.execute(
                select(Website.slug).join(BotContent).order_by(Website.slug)
            ).scalars()
            return list(slugs)


def get_bot_document(session: Session, slug: str) -> tuple[Any, int] | None:
    """Return the raw document and its revision for an editor to load."""
    row = session.execute(
        select(BotContent.document, BotContent.revision)
        .join(Website, Website.id == BotContent.website_id)
        .where(Website.slug == slug)
    ).first()
    return None if row is None else (row[0], row[1])


def save_bot_document(
    session: Session,
    slug: str,
    document: Any,
    expected_revision: int,
    updated_by: int | None = None,
) -> int:
    """Replace a website's bot document, guarded by its revision.

    The document is fully validated first. The update only applies while the
    stored revision still equals ``expected_revision``; otherwise nothing is
    written and ``RevisionConflict`` reports the current revision. Returns the
    new revision. The caller commits.
    """
    validate_bot_content(document)
    website_id = session.execute(
        select(Website.id).where(Website.slug == slug)
    ).scalar_one_or_none()
    if website_id is None:
        raise LookupError(f"No website with slug '{slug}'")
    result = session.execute(
        update(BotContent)
        .where(BotContent.website_id == website_id, BotContent.revision == expected_revision)
        .values(
            document=document,
            revision=expected_revision + 1,
            updated_at=func.now(),
            updated_by=updated_by,
        )
    )
    if result.rowcount == 0:
        current = session.execute(
            select(BotContent.revision).where(BotContent.website_id == website_id)
        ).scalar_one_or_none()
        raise RevisionConflict(slug, expected_revision, current if current is not None else 0)
    return expected_revision + 1


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"imported {len(self.imported)} ({', '.join(self.imported) or 'none'}), "
            f"replaced {len(self.replaced)} ({', '.join(self.replaced) or 'none'}), "
            f"skipped {len(self.skipped)} ({', '.join(self.skipped) or 'none'})"
        )


def import_documents(
    session: Session, directory: Path, replace: bool = False
) -> ImportReport:
    """Import every content file in ``directory`` into the database.

    ``load_content_documents`` validates the whole batch first and raises with
    every problem if any file is bad, so an invalid batch writes nothing. The
    rest runs in the caller's transaction: all rows commit together or none
    do. A bot whose slug already exists is skipped, or replaced with a normal
    revision bump when ``replace`` is set. New websites take their name from
    the bot's config.
    """
    documents = load_content_documents(directory)
    report = ImportReport()
    for slug in sorted(documents):
        document = documents[slug]
        existing = session.execute(
            select(BotContent.revision)
            .join(Website, Website.id == BotContent.website_id)
            .where(Website.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            if not replace:
                report.skipped.append(slug)
                continue
            save_bot_document(session, slug, document, expected_revision=existing)
            report.replaced.append(slug)
            continue
        website = session.execute(
            select(Website).where(Website.slug == slug)
        ).scalar_one_or_none()
        if website is None:
            website = Website(slug=slug, name=document["config"]["name"])
            session.add(website)
            session.flush()
        session.add(BotContent(website_id=website.id, document=document, revision=1))
        report.imported.append(slug)
    return report


def assert_database_ready(engine: Engine, alembic_dir: Path) -> None:
    """Refuse to serve from a database that is missing or behind on migrations."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(alembic_dir))
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    except Exception as error:  # missing table, missing database, bad credentials
        raise SystemExit(
            "AskHarbor cannot start in database mode: the database is not reachable or "
            f"has no migrations applied ({error}). Check ASKHARBOR_DATABASE_URL and run "
            "'python -m alembic upgrade head' from server/."
        ) from None
    if current != head:
        raise SystemExit(
            f"AskHarbor cannot start: the database is at migration '{current}' but the "
            f"code expects '{head}'. Run 'python -m alembic upgrade head' from server/."
        )


# --- websites and their settings -------------------------------------------------


class InvalidSetting(ValueError):
    pass


def normalize_origins(values: list[str]) -> list[str]:
    """Trim, drop trailing slashes, de-duplicate and insist on scheme://host[:port]."""
    cleaned: list[str] = []
    for raw in values:
        origin = raw.strip().rstrip("/")
        if not origin:
            continue
        if not ORIGIN_PATTERN.match(origin):
            raise InvalidSetting(
                f"'{raw.strip()}' is not an origin. Use the scheme and host only, "
                "for example https://www.example.com or http://localhost:3000."
            )
        if origin not in cleaned:
            cleaned.append(origin)
    return cleaned


def normalize_domain(value: str | None) -> str | None:
    domain = (value or "").strip().lower()
    if not domain:
        return None
    if len(domain) > 253 or not DOMAIN_PATTERN.match(domain):
        raise InvalidSetting(
            f"'{value}' is not a domain name. Use the host only, for example www.example.com."
        )
    return domain


def get_website(session: Session, slug: str) -> Website | None:
    return session.execute(select(Website).where(Website.slug == slug)).scalar_one_or_none()


def starter_document(slug: str, name: str) -> dict[str, Any]:
    """The first bot document of a new website, so its widget works immediately."""
    return {
        "format_version": 1,
        "config": {
            "id": slug,
            "name": name,
            "greeting": "Hi! Pick a question to see its answer.",
            "launcher_label": f"Open {name} help",
            "primary_color": "#155eef",
            "opening_option_ids": ["example-question"],
        },
        "answers": [
            {
                "id": "example-question",
                "label": "Where does this answer come from?",
                "answer": "From the AskHarbor editor. Replace this text with your first answer.",
            }
        ],
    }


class SiteOriginsLookup:
    """Per website allowed origins for the CORS middleware, with a short cache.

    Every widget request would otherwise hit the database twice. Entries live
    for ``ttl`` seconds; ``forget`` drops one after a settings change so the
    worker that handled the change answers correctly at once (other workers
    catch up within the ttl).
    """

    def __init__(self, factory: sessionmaker[Session], ttl: float = 2.0) -> None:
        self._factory = factory
        self._ttl = ttl
        self._cache: dict[str, tuple[float, list[str]]] = {}

    def __call__(self, slug: str) -> list[str]:
        cached = self._cache.get(slug)
        now = time.monotonic()
        if cached is not None and cached[0] > now:
            return cached[1]
        with self._factory() as session:
            origins = session.execute(
                select(Website.allowed_origins).where(Website.slug == slug)
            ).scalar_one_or_none()
        result = list(origins or [])
        self._cache[slug] = (now + self._ttl, result)
        return result

    def forget(self, slug: str) -> None:
        self._cache.pop(slug, None)


def seed_sample_content(session: Session, directory: Path) -> ImportReport | None:
    """Load the sample bots once, when there are no websites at all.

    Runs inside the caller's transaction (the bootstrap lock is already held)
    so concurrent workers cannot both seed. Returns None when websites exist.
    """
    if session.execute(select(func.count()).select_from(Website)).scalar_one() > 0:
        return None
    report = import_documents(session, directory)
    logger.warning(
        "Sample bots loaded into the empty database from %s: %s. They are fictional "
        "content for trying the application; delete them from the admin panel when done.",
        directory,
        ", ".join(report.imported),
    )
    return report
