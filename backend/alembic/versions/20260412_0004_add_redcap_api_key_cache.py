"""Add encrypted session-scoped REDCap API key cache."""

from alembic import op
import sqlalchemy as sa


revision = "20260412_0004"
down_revision = "20260412_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redcap_api_key_cache",
        sa.Column("user_session_id", sa.Uuid(), nullable=False),
        sa.Column("redcap_host_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["redcap_host_id"],
            ["redcap_hosts.id"],
            name="fk_redcap_api_key_cache_redcap_host_id_redcap_hosts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_session_id"],
            ["user_sessions.id"],
            name="fk_redcap_api_key_cache_user_session_id_user_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_redcap_api_key_cache"),
        sa.UniqueConstraint("user_session_id", "redcap_host_id", name="uq_redcap_api_key_cache_session_host"),
    )
    op.create_index("ix_redcap_api_key_cache_expires_at", "redcap_api_key_cache", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_redcap_api_key_cache_expires_at", table_name="redcap_api_key_cache")
    op.drop_table("redcap_api_key_cache")
