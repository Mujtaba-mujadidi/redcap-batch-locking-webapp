from app.models.enums import JobStatus, JobType, RowResultStatus
from app.models.job import Job, JobRow, RowResult
from app.services.job_lifecycle import (
    INTERRUPTED_JOB_MESSAGE,
    build_job_outcome_copy,
    build_job_result_stats,
    format_row_count,
    recover_interrupted_active_jobs,
    resolve_processing_mode,
    summarize_retry_candidates,
)


def test_format_row_count():
    assert format_row_count(1) == "1 row"
    assert format_row_count(3) == "3 rows"


def test_resolve_processing_mode_uses_live_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.services.job_lifecycle.resolve_live_processing_max_rows",
        lambda: 5,
    )
    assert resolve_processing_mode(row_count=5) == "live"
    assert resolve_processing_mode(row_count=6) == "background"
    assert resolve_processing_mode(row_count=0) == "background"


def test_summarize_retry_candidates_failed_only():
    failed = JobRow(row_number=1)
    failed.row_result = RowResult(status=RowResultStatus.FAILED, processed_at=None)
    summary = summarize_retry_candidates([failed])
    assert summary["retry_scope"] == "failed_only"
    assert summary["action_label"] == "Retry Failed Rows"
    assert summary["failed_count"] == 1
    assert summary["unprocessed_count"] == 0


def test_summarize_retry_candidates_remaining_rows():
    pending = JobRow(row_number=1)
    pending.row_result = None
    failed = JobRow(row_number=2)
    failed.row_result = RowResult(status=RowResultStatus.FAILED, processed_at=None)
    summary = summarize_retry_candidates([pending, failed])
    assert summary["retry_scope"] == "remaining_rows"
    assert summary["action_label"] == "Resume Remaining Rows"
    assert summary["failed_count"] == 1
    assert summary["unprocessed_count"] == 1


def test_build_job_outcome_copy_completed_success():
    job = Job(
        status=JobStatus.COMPLETED,
        total_rows=2,
        processed_rows=2,
        locked_rows=2,
        unlocked_rows=0,
        ignored_rows=0,
        blocked_rows=0,
        failed_rows=0,
    )
    assert build_job_outcome_copy(job) == "Completed successfully."


def test_build_job_result_stats_includes_counts():
    job = Job(
        status=JobStatus.COMPLETED,
        total_rows=5,
        processed_rows=5,
        locked_rows=2,
        unlocked_rows=1,
        ignored_rows=1,
        blocked_rows=0,
        failed_rows=1,
    )
    assert build_job_result_stats(job) == ["2 locked", "1 unlocked", "1 skipped", "1 failed"]


def test_recover_interrupted_active_jobs_finalizes_orphans(monkeypatch):
    job = Job(
        status=JobStatus.RUNNING,
        job_type=JobType.LOCK,
        redcap_api_url="https://example.test/api/",
        total_rows=2,
        processed_rows=1,
        request_file_name="demo.csv",
    )
    finalize_calls: list[dict] = []

    def fake_finalize(*_args, **kwargs):
        finalize_calls.append(kwargs)
        kwargs["job"].status = JobStatus.CANCELLED
        kwargs["job"].last_error_summary = kwargs["cancellation_message"]
        return 1

    monkeypatch.setattr("app.services.job_lifecycle.finalize_job_cancellation", fake_finalize)
    monkeypatch.setattr("app.services.job_lifecycle.record_job_event", lambda *_args, **_kwargs: None)

    class _Scalars:
        def all(self):
            return [job]

    class _Session:
        def scalars(self, _statement):
            return _Scalars()

    recovered = recover_interrupted_active_jobs(_Session())
    assert recovered == 1
    assert job.status == JobStatus.CANCELLED
    assert job.last_error_summary == INTERRUPTED_JOB_MESSAGE
    assert finalize_calls[0]["cancellation_message"] == INTERRUPTED_JOB_MESSAGE
