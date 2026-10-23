"""Basic audit logging: one row per meaningful action, written in the same
transaction as the change it describes so the log and the data agree."""

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .orm import AuditEntry, User


def record(
    session: Session,
    action: str,
    *,
    user: User | None,
    request: Request | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    website_slug: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        user_id=user.id if user is not None else None,
        username=user.username if user is not None else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        website_slug=website_slug,
        details=details,
        client_address=(request.client.host if request is not None and request.client else None),
    )
    session.add(entry)
    return entry


def recent(
    session: Session, *, website_slug: str | None = None, limit: int = 100
) -> list[AuditEntry]:
    statement = select(AuditEntry).order_by(AuditEntry.at.desc(), AuditEntry.id.desc())
    if website_slug is not None:
        statement = statement.where(AuditEntry.website_slug == website_slug)
    return list(session.execute(statement.limit(limit)).scalars())
