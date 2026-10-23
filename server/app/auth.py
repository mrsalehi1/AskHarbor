"""Accounts: password hashing, login sessions and the bootstrap admin.

Passwords are hashed with Argon2id and never stored or logged in clear.
Sessions live in the database: the browser holds a random token, the table
holds only its SHA-256, and a session ends when it expires, is revoked by
logout, or is revoked because the user changed their password.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from .config import MIN_PASSWORD_LENGTH, Settings
from .orm import LoginSession, User

logger = logging.getLogger("askharbor")

# Argon2id with the library's current defaults (64 MiB, 3 passes, 4 lanes).
_hasher = PasswordHasher()

# Verified against when the username is unknown, so a failed login takes the
# same time whether or not the account exists.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

# Serializes bootstrap across workers. Any constant works; this one is "AskH".
BOOTSTRAP_LOCK_ID = 0x41736B48

MAX_PASSWORD_LENGTH = 200


class PasswordPolicyError(ValueError):
    pass


def check_password_policy(password: str, *, current: str | None = None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if current is not None and password == current:
        raise PasswordPolicyError("The new password must differ from the current one.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-time-ish check that also runs for unknown users."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# --- sessions -----------------------------------------------------------------


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_session(session: Session, user: User, lifetime: timedelta) -> str:
    """Store a new login session and return the token for the cookie."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        LoginSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + lifetime,
            last_seen_at=now,
        )
    )
    user.last_login_at = now
    return token


def find_session(session: Session, token: str) -> tuple[LoginSession, User] | None:
    """Return the live session and its active user for a cookie token, or None.

    Expired or revoked sessions and deactivated users do not count. A live
    session's last_seen_at is refreshed.
    """
    row = session.execute(
        select(LoginSession, User)
        .join(User, User.id == LoginSession.user_id)
        .where(LoginSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None
    login_session, user = row
    now = datetime.now(UTC)
    if login_session.revoked_at is not None or login_session.expires_at <= now:
        return None
    if not user.is_active:
        return None
    login_session.last_seen_at = now
    return login_session, user


def revoke_session(session: Session, login_session: LoginSession) -> None:
    login_session.revoked_at = datetime.now(UTC)


def revoke_other_sessions(session: Session, user: User, keep: LoginSession | None) -> int:
    """Revoke every live session of ``user`` except ``keep``. Returns how many."""
    statement = (
        update(LoginSession)
        .where(LoginSession.user_id == user.id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    if keep is not None:
        statement = statement.where(LoginSession.id != keep.id)
    return session.execute(statement).rowcount


def change_password(
    session: Session, user: User, current: str, new: str, keep: LoginSession | None
) -> None:
    """Set a new password after checking the current one and the policy.

    Clears the forced change flag and revokes the user's other sessions so a
    stolen session does not survive a password change.
    """
    if not verify_password(user.password_hash, current):
        raise PasswordPolicyError("The current password is not correct.")
    check_password_policy(new, current=current)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.password_changed_at = datetime.now(UTC)
    revoke_other_sessions(session, user, keep)


def purge_expired_sessions(session: Session) -> int:
    """Delete sessions that expired or were revoked more than a day ago."""
    cutoff = datetime.now(UTC) - timedelta(days=1)
    result = session.execute(
        text(
            "DELETE FROM sessions WHERE expires_at < :cutoff "
            "OR (revoked_at IS NOT NULL AND revoked_at < :cutoff)"
        ),
        {"cutoff": cutoff},
    )
    return result.rowcount


# --- bootstrap ------------------------------------------------------------------


def bootstrap_admin(session: Session, settings: Settings) -> bool:
    """Create the first admin once, no matter how many workers start together.

    Runs inside the caller's transaction. A transaction-level advisory lock
    serializes concurrent starts: the first worker to hold it sees an empty
    users table and inserts the admin; every later one sees that row after
    the first commit and does nothing. Existing accounts are never touched,
    so a restart cannot reset a changed password or recreate a deleted admin.
    Returns True when the admin was created.
    """
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": BOOTSTRAP_LOCK_ID})
    user_count = session.execute(select(func.count()).select_from(User)).scalar_one()
    if user_count > 0:
        logger.info("Bootstrap admin skipped: %d account(s) already exist.", user_count)
        return False
    session.add(
        User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_admin=True,
            is_active=True,
            must_change_password=True,
        )
    )
    logger.warning(
        "Bootstrap admin '%s' created. It must change its password before doing anything else.",
        settings.bootstrap_admin_username,
    )
    return True
