from uuid import UUID


def process_job_in_background(
    *,
    job_id: UUID,
    actor_user_id: UUID,
    user_session_id: UUID,
    retry_row_ids: list[UUID] | None = None,
) -> None:
    """Worker entrypoint; delegates to run_job_processing in the UI router."""

    from app.ui.router import run_job_processing

    run_job_processing(
        job_id,
        actor_user_id,
        "",
        retry_row_ids or [],
        processing_mode="background",
        user_session_id=user_session_id,
    )
