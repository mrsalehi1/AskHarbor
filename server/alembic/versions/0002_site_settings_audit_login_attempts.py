"""Per website settings, audit log and shared login attempt counters.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("websites", sa.Column("domain", sa.String(253), nullable=True))
    op.add_column(
        "websites",
        sa.Column(
            "allowed_origins",
            ARRAY(sa.String(255)),
            nullable=False,
            server_default="{}",
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("username", sa.String(80), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=True),
        sa.Column("target_id", sa.String(120), nullable=True),
        sa.Column("website_slug", sa.String(100), nullable=True, index=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("client_address", sa.String(64), nullable=True),
    )
    op.create_index("audit_log_at_idx", "audit_log", ["at"])

    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_index("audit_log_at_idx", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_column("websites", "allowed_origins")
    op.drop_column("websites", "domain")
