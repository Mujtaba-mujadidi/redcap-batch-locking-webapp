"""Shared job status and mapping-option constants.

Keep these in one place so the UI router, workspace views, and API routes
do not drift apart.
"""

from app.models.enums import JobStatus

# Sentinel values used in mapping review forms when the user picks
# "no field" or "auto-detect format".
MAPPING_NONE_OPTION = "__NONE__"
MAPPING_AUTO_OPTION = "__AUTO__"

ACTIVE_JOB_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.WAITING_DUE_TO_RATE_LIMIT,
    JobStatus.CANCEL_REQUESTED,
}

JOBS_VISIBLE_STATUSES = (
    JobStatus.AWAITING_MAPPING_CONFIRMATION,
    JobStatus.READY,
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.WAITING_DUE_TO_RATE_LIMIT,
    JobStatus.CANCEL_REQUESTED,
    JobStatus.CANCELLED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_ERRORS,
    JobStatus.FAILED,
)

REPORTABLE_JOB_STATUSES = {
    JobStatus.CANCELLED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_ERRORS,
    JobStatus.FAILED,
}

PRESTART_CANCELLABLE_JOB_STATUSES = {
    JobStatus.AWAITING_MAPPING_CONFIRMATION,
    JobStatus.READY,
    JobStatus.QUEUED,
}

USER_CANCELLABLE_JOB_STATUSES = {
    *PRESTART_CANCELLABLE_JOB_STATUSES,
    JobStatus.RUNNING,
    JobStatus.WAITING_DUE_TO_RATE_LIMIT,
}
