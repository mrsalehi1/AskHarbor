"""Failed-login limiter shared across workers through the database.

Same fixed window semantics as the in-memory limiter, but the counter rows
live in PostgreSQL, so several uvicorn workers or several instances see one
budget per client address and per username. Only failures are counted; the
caller checks ``peek`` first and calls ``hit`` after a failed attempt.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from .orm import LoginAttempt


class DatabaseLoginLimiter:
    def __init__(self, factory: sessionmaker[Session], limit: int, window_seconds: int) -> None:
        self.factory = factory
        self.limit = limit
        self.window_seconds = window_seconds

    def peek(self, key: str) -> int | None:
        if self.limit <= 0:
            return None
        with self.factory() as db:
            row = db.get(LoginAttempt, key)
            if row is None:
                return None
            now = datetime.now(UTC)
            window_end = row.window_start + timedelta(seconds=self.window_seconds)
            if now >= window_end or row.count < self.limit:
                return None
            return max(1, math.ceil((window_end - now).total_seconds()))

    def hit(self, key: str) -> None:
        """Count one failure. Starts a new window if the old one has passed."""
        if self.limit <= 0:
            return
        statement = text(
            """
            INSERT INTO login_attempts (key, window_start, count)
            VALUES (:key, :now, 1)
            ON CONFLICT (key) DO UPDATE SET
              count = CASE
                WHEN login_attempts.window_start + make_interval(secs => :window) <= :now
                THEN 1 ELSE login_attempts.count + 1 END,
              window_start = CASE
                WHEN login_attempts.window_start + make_interval(secs => :window) <= :now
                THEN :now ELSE login_attempts.window_start END
            """
        )
        with self.factory() as db, db.begin():
            db.execute(
                statement,
                {"key": key, "now": datetime.now(UTC), "window": float(self.window_seconds)},
            )

    def reset(self) -> None:
        with self.factory() as db, db.begin():
            db.execute(delete(LoginAttempt))

    def purge_expired(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.window_seconds)
        with self.factory() as db, db.begin():
            result = db.execute(delete(LoginAttempt).where(LoginAttempt.window_start < cutoff))
            return result.rowcount

    def tracked_keys(self) -> list[str]:
        with self.factory() as db:
            return list(db.execute(select(LoginAttempt.key)).scalars())
