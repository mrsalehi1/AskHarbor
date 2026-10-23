"""SQLAlchemy models for accounts, websites, memberships and bot content.

This round only defines the schema and the content tables are used. Login,
the bootstrap admin and the admin API arrive in later rounds, so ``users``,
``sessions`` and ``website_members`` exist but have no rows yet.

A website owns exactly one bot document. The public bot ID is the website
``slug``, which keeps existing embeds working when content moves from files
into the database. The document column holds the same validated JSON written
by the editor and the content files; ``revision`` increases by one on every
save and a save must name the revision it read, so two concurrent edits
cannot silently overwrite each other.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .content import ID_PATTERN

# Login names: same shape rules as content IDs, so they are URL and log safe.
USERNAME_PATTERN = ID_PATTERN
MAX_USERNAME_LENGTH = 80
MAX_WEBSITE_NAME_LENGTH = 80
MAX_SLUG_LENGTH = 100  # matches MAX_ID_LENGTH; the slug is the public bot ID

EDITOR_ROLE = "editor"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"username ~ '{USERNAME_PATTERN}'", name="users_username_shape"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(MAX_USERNAME_LENGTH), unique=True)
    # Argon2id hash once login lands; no plain passwords, ever.
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Set for new accounts and admin resets; cleared by the user's own change.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["WebsiteMember"]] = relationship(back_populates="user")


class LoginSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # SHA-256 hex of the cookie token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class Website(Base):
    __tablename__ = "websites"
    __table_args__ = (
        CheckConstraint(f"slug ~ '{ID_PATTERN}'", name="websites_slug_shape"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(MAX_WEBSITE_NAME_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list["WebsiteMember"]] = relationship(back_populates="website")
    bot_content: Mapped["BotContent | None"] = relationship(back_populates="website")


class WebsiteMember(Base):
    __tablename__ = "website_members"

    website_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("websites.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default=EDITOR_ROLE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    website: Mapped[Website] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class BotContent(Base):
    __tablename__ = "bot_contents"

    website_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("websites.id", ondelete="CASCADE"), primary_key=True
    )
    document: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Who saved last; empty until accounts exist. Kept if the user is deleted.
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )

    website: Mapped[Website] = relationship(back_populates="bot_content")
