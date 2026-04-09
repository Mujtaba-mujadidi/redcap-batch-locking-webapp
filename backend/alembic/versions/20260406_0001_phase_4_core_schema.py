"""Create Phase 4 core schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260406_0001"
down_revision = None
branch_labels = None
depends_on = None


role_enum = sa.Enum(
    "super_admin",
    "admin",
    "user",
    name="role",
    native_enum=False,
    create_constraint=True,
)
job_type_enum = sa.Enum(
    "lock",
    "unlock",
    name="job_type",
    native_enum=False,
    create_constraint=True,
)
job_status_enum = sa.Enum(
    "draft",
    "validating",
    "awaiting_mapping_confirmation",
    "ready",
    "queued",
    "running",
    "waiting_due_to_rate_limit",
    "cancel_requested",
    "cancelled",
    "completed",
    "completed_with_errors",
    "failed",
    name="job_status",
    native_enum=False,
    create_constraint=True,
)
row_action_enum = sa.Enum(
    "lock",
    "unlock",
    name="row_action",
    native_enum=False,
    create_constraint=True,
)
row_result_status_enum = sa.Enum(
    "pending",
    "success",
    "ignored",
    "blocked",
    "failed",
    "cancelled",
    name="row_result_status",
    native_enum=False,
    create_constraint=True,
)
mapping_status_enum = sa.Enum(
    "inferred",
    "confirmed",
    "stale",
    name="mapping_status",
    native_enum=False,
    create_constraint=True,
)
mapping_confidence_enum = sa.Enum(
    "high",
    "confirm",
    "not_found",
    name="mapping_confidence",
    native_enum=False,
    create_constraint=True,
)
report_type_enum = sa.Enum(
    "csv",
    "xlsx",
    name="report_type",
    native_enum=False,
    create_constraint=True,
)
event_level_enum = sa.Enum(
    "info",
    "warning",
    "error",
    name="event_level",
    native_enum=False,
    create_constraint=True,
)
job_status_transition_from_enum = sa.Enum(
    "draft",
    "validating",
    "awaiting_mapping_confirmation",
    "ready",
    "queued",
    "running",
    "waiting_due_to_rate_limit",
    "cancel_requested",
    "cancelled",
    "completed",
    "completed_with_errors",
    "failed",
    name="job_status_transition_from",
    native_enum=False,
    create_constraint=True,
)
job_status_transition_to_enum = sa.Enum(
    "draft",
    "validating",
    "awaiting_mapping_confirmation",
    "ready",
    "queued",
    "running",
    "waiting_due_to_rate_limit",
    "cancel_requested",
    "cancelled",
    "completed",
    "completed_with_errors",
    "failed",
    name="job_status_transition_to",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("totp_secret_encrypted", sa.String(length=512), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_role_is_active", "users", ["role", "is_active"], unique=False)

    op.create_table(
        "redcap_hosts",
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("max_concurrent_jobs", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name="pk_redcap_hosts"),
        sa.UniqueConstraint("base_url", name="uq_redcap_hosts_base_url"),
    )
    op.create_index("ix_redcap_hosts_is_active", "redcap_hosts", ["is_active"], unique=False)

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], name="fk_system_settings_updated_by_user_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_system_settings"),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )

    op.create_table(
        "audit_events",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.String(length=100), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_events_actor_user_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_actor_action_created_at", "audit_events", ["actor_user_id", "action", "created_at"], unique=False)
    op.create_index("ix_audit_events_object_type_object_id", "audit_events", ["object_type", "object_id"], unique=False)

    op.create_table(
        "instrument_mappings",
        sa.Column("redcap_project_id", sa.String(length=100), nullable=False),
        sa.Column("instrument_name", sa.String(length=255), nullable=False),
        sa.Column("status", mapping_status_enum, nullable=False),
        sa.Column("confidence", mapping_confidence_enum, nullable=False),
        sa.Column("form_complete_field_name", sa.String(length=255), nullable=True),
        sa.Column("crf_status_field_name", sa.String(length=255), nullable=True),
        sa.Column("lock_date_field_name", sa.String(length=255), nullable=True),
        sa.Column("coded_values_json", sa.JSON(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drift_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], name="fk_instrument_mappings_confirmed_by_user_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_instrument_mappings"),
        sa.UniqueConstraint("redcap_project_id", "instrument_name", name="uq_instrument_mappings_project_instrument"),
    )
    op.create_index("ix_instrument_mappings_status", "instrument_mappings", ["status"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("redcap_host_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", job_type_enum, nullable=False),
        sa.Column("status", job_status_enum, nullable=False, server_default=sa.text("'draft'")),
        sa.Column("redcap_api_url", sa.Text(), nullable=False),
        sa.Column("redcap_project_id", sa.String(length=100), nullable=True),
        sa.Column("redcap_project_title", sa.String(length=255), nullable=True),
        sa.Column("request_file_name", sa.String(length=255), nullable=True),
        sa.Column("queries_file_name", sa.String(length=255), nullable=True),
        sa.Column("source_file_checksum", sa.String(length=64), nullable=True),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("validation_summary_json", sa.JSON(), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unlocked_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ignored_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("blocked_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("retried_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_jobs_owner_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["redcap_host_id"], ["redcap_hosts.id"], name="fk_jobs_redcap_host_id_redcap_hosts", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_owner_status_created_at", "jobs", ["owner_id", "status", "created_at"], unique=False)
    op.create_index("ix_jobs_project_status", "jobs", ["redcap_project_id", "status"], unique=False)

    op.create_table(
        "job_rows",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("action", row_action_enum, nullable=False),
        sa.Column("record_id", sa.String(length=255), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=True),
        sa.Column("arm_name", sa.String(length=255), nullable=True),
        sa.Column("repeat_instance", sa.Integer(), nullable=True),
        sa.Column("repeat_instrument", sa.String(length=255), nullable=True),
        sa.Column("target_instrument", sa.String(length=255), nullable=False),
        sa.Column("target_field_name", sa.String(length=255), nullable=True),
        sa.Column("input_payload_json", sa.JSON(), nullable=True),
        sa.Column("has_unresolved_queries", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_job_rows_job_id_jobs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_job_rows"),
        sa.UniqueConstraint("job_id", "row_number", name="uq_job_rows_job_id_row_number"),
    )
    op.create_index("ix_job_rows_job_id_record_id", "job_rows", ["job_id", "record_id"], unique=False)
    op.create_index("ix_job_rows_job_id_target_instrument", "job_rows", ["job_id", "target_instrument"], unique=False)

    op.create_table(
        "reports",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", report_type_enum, nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_reports_job_id_jobs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
    )
    op.create_index("ix_reports_job_id_report_type", "reports", ["job_id", "report_type"], unique=False)

    op.create_table(
        "row_results",
        sa.Column("job_row_id", sa.Uuid(), nullable=False),
        sa.Column("status", row_result_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("outcome_code", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("redcap_http_status", sa.Integer(), nullable=True),
        sa.Column("query_blocking_count", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_row_id"], ["job_rows.id"], name="fk_row_results_job_row_id_job_rows", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_row_results"),
        sa.UniqueConstraint("job_row_id", name="uq_row_results_job_row_id"),
    )
    op.create_index("ix_row_results_status", "row_results", ["status"], unique=False)

    op.create_table(
        "job_events",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("job_row_id", sa.Uuid(), nullable=True),
        sa.Column("level", event_level_enum, nullable=False, server_default=sa.text("'info'")),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("status_from", job_status_transition_from_enum, nullable=True),
        sa.Column("status_to", job_status_transition_to_enum, nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_job_events_job_id_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_row_id"], ["job_rows.id"], name="fk_job_events_job_row_id_job_rows", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_job_events"),
    )
    op.create_index("ix_job_events_event_type", "job_events", ["event_type"], unique=False)
    op.create_index("ix_job_events_job_id_created_at", "job_events", ["job_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_events_job_id_created_at", table_name="job_events")
    op.drop_index("ix_job_events_event_type", table_name="job_events")
    op.drop_table("job_events")

    op.drop_index("ix_row_results_status", table_name="row_results")
    op.drop_table("row_results")

    op.drop_index("ix_reports_job_id_report_type", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_job_rows_job_id_target_instrument", table_name="job_rows")
    op.drop_index("ix_job_rows_job_id_record_id", table_name="job_rows")
    op.drop_table("job_rows")

    op.drop_index("ix_jobs_project_status", table_name="jobs")
    op.drop_index("ix_jobs_owner_status_created_at", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_instrument_mappings_status", table_name="instrument_mappings")
    op.drop_table("instrument_mappings")

    op.drop_index("ix_audit_events_object_type_object_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_action_created_at", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_table("system_settings")

    op.drop_index("ix_redcap_hosts_is_active", table_name="redcap_hosts")
    op.drop_table("redcap_hosts")

    op.drop_index("ix_users_role_is_active", table_name="users")
    op.drop_table("users")
