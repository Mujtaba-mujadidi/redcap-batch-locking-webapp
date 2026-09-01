"""Scope instrument mappings to a REDCap host as well as project ID."""

from collections import defaultdict
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260412_0003"
down_revision = "20260407_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("instrument_mappings") as batch_op:
            batch_op.add_column(sa.Column("redcap_host_id", sa.Uuid(), nullable=True))
            batch_op.create_foreign_key(
                "fk_instrument_mappings_redcap_host_id_redcap_hosts",
                "redcap_hosts",
                ["redcap_host_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column("instrument_mappings", sa.Column("redcap_host_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_instrument_mappings_redcap_host_id_redcap_hosts",
            "instrument_mappings",
            "redcap_hosts",
            ["redcap_host_id"],
            ["id"],
            ondelete="SET NULL",
        )

    mapping_rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                redcap_project_id,
                instrument_name,
                status,
                confidence,
                form_complete_field_name,
                crf_status_field_name,
                lock_date_field_name,
                coded_values_json,
                last_validated_at,
                drift_detected_at,
                confirmed_by_user_id,
                created_at,
                updated_at
            FROM instrument_mappings
            WHERE redcap_host_id IS NULL
            """
        )
    ).mappings()
    jobs_by_project = defaultdict(list)
    for row in bind.execute(
        sa.text(
            """
            SELECT redcap_project_id, redcap_host_id
            FROM jobs
            WHERE redcap_project_id IS NOT NULL AND redcap_host_id IS NOT NULL
            GROUP BY redcap_project_id, redcap_host_id
            ORDER BY redcap_project_id, redcap_host_id
            """
        )
    ).mappings():
        jobs_by_project[row["redcap_project_id"]].append(row["redcap_host_id"])

    update_host_stmt = sa.text(
        """
        UPDATE instrument_mappings
        SET redcap_host_id = :redcap_host_id
        WHERE id = :mapping_id
        """
    )
    insert_clone_stmt = sa.text(
        """
        INSERT INTO instrument_mappings (
            redcap_host_id,
            redcap_project_id,
            instrument_name,
            status,
            confidence,
            form_complete_field_name,
            crf_status_field_name,
            lock_date_field_name,
            coded_values_json,
            last_validated_at,
            drift_detected_at,
            confirmed_by_user_id,
            id,
            created_at,
            updated_at
        ) VALUES (
            :redcap_host_id,
            :redcap_project_id,
            :instrument_name,
            :status,
            :confidence,
            :form_complete_field_name,
            :crf_status_field_name,
            :lock_date_field_name,
            :coded_values_json,
            :last_validated_at,
            :drift_detected_at,
            :confirmed_by_user_id,
            :id,
            :created_at,
            :updated_at
        )
        """
    )

    for mapping_row in mapping_rows:
        host_ids = jobs_by_project.get(mapping_row["redcap_project_id"], [])
        if not host_ids:
            continue

        bind.execute(
            update_host_stmt,
            {
                "mapping_id": mapping_row["id"],
                "redcap_host_id": host_ids[0],
            },
        )
        for host_id in host_ids[1:]:
            bind.execute(
                insert_clone_stmt,
                {
                    "redcap_host_id": host_id,
                    "redcap_project_id": mapping_row["redcap_project_id"],
                    "instrument_name": mapping_row["instrument_name"],
                    "status": mapping_row["status"],
                    "confidence": mapping_row["confidence"],
                    "form_complete_field_name": mapping_row["form_complete_field_name"],
                    "crf_status_field_name": mapping_row["crf_status_field_name"],
                    "lock_date_field_name": mapping_row["lock_date_field_name"],
                    "coded_values_json": mapping_row["coded_values_json"],
                    "last_validated_at": mapping_row["last_validated_at"],
                    "drift_detected_at": mapping_row["drift_detected_at"],
                    "confirmed_by_user_id": mapping_row["confirmed_by_user_id"],
                    "id": uuid4(),
                    "created_at": mapping_row["created_at"],
                    "updated_at": mapping_row["updated_at"],
                },
            )

    if is_sqlite:
        with op.batch_alter_table("instrument_mappings") as batch_op:
            batch_op.drop_constraint("uq_instrument_mappings_project_instrument", type_="unique")
            batch_op.create_unique_constraint(
                "uq_instrument_mappings_host_project_instrument",
                ["redcap_host_id", "redcap_project_id", "instrument_name"],
            )
    else:
        op.drop_constraint("uq_instrument_mappings_project_instrument", "instrument_mappings", type_="unique")
        op.create_unique_constraint(
            "uq_instrument_mappings_host_project_instrument",
            "instrument_mappings",
            ["redcap_host_id", "redcap_project_id", "instrument_name"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    bind.execute(
        sa.text(
            """
            WITH ranked_mappings AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY redcap_project_id, instrument_name
                        ORDER BY created_at, id
                    ) AS row_number
                FROM instrument_mappings
            )
            DELETE FROM instrument_mappings
            WHERE id IN (
                SELECT id
                FROM ranked_mappings
                WHERE row_number > 1
            )
            """
        )
    )

    if is_sqlite:
        with op.batch_alter_table("instrument_mappings") as batch_op:
            batch_op.drop_constraint("uq_instrument_mappings_host_project_instrument", type_="unique")
            batch_op.create_unique_constraint(
                "uq_instrument_mappings_project_instrument",
                ["redcap_project_id", "instrument_name"],
            )
            batch_op.drop_constraint("fk_instrument_mappings_redcap_host_id_redcap_hosts", type_="foreignkey")
            batch_op.drop_column("redcap_host_id")
    else:
        op.drop_constraint("uq_instrument_mappings_host_project_instrument", "instrument_mappings", type_="unique")
        op.create_unique_constraint(
            "uq_instrument_mappings_project_instrument",
            "instrument_mappings",
            ["redcap_project_id", "instrument_name"],
        )
        op.drop_constraint("fk_instrument_mappings_redcap_host_id_redcap_hosts", "instrument_mappings", type_="foreignkey")
        op.drop_column("instrument_mappings", "redcap_host_id")
