from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


class JobType(str, Enum):
    LOCK = "lock"
    UNLOCK = "unlock"


class JobStatus(str, Enum):
    DRAFT = "draft"
    VALIDATING = "validating"
    AWAITING_MAPPING_CONFIRMATION = "awaiting_mapping_confirmation"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_DUE_TO_RATE_LIMIT = "waiting_due_to_rate_limit"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class RowAction(str, Enum):
    LOCK = "lock"
    UNLOCK = "unlock"


class RowResultStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    IGNORED = "ignored"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MappingStatus(str, Enum):
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    STALE = "stale"


class MappingConfidence(str, Enum):
    HIGH = "high"
    CONFIRM = "confirm"
    NOT_FOUND = "not_found"


class ReportType(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"


class EventLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
