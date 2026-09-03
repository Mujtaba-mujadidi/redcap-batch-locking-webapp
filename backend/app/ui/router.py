import csv
from datetime import datetime
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
from time import perf_counter
from urllib.parse import urlencode, urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import utc_now
from app.db.session import SessionLocal, get_db_session
from app.models.audit import AuditEvent
from app.models.enums import EventLevel, JobStatus, JobType, MappingConfidence, MappingStatus, ReportType, Role, RowAction, RowResultStatus
from app.models.job import Job, JobEvent, JobRow, Report, RowResult
from app.models.mapping import InstrumentMapping
from app.models.redcap import REDCapHost
from app.models.session import UserSession
from app.models.user import User
from app.services.audit import record_audit_event
from app.core.desktop import get_desktop_session
from app.services.auth import get_valid_session_by_token
from app.services.mappings import (
    DATE_FORMAT_OPTIONS,
    build_mapping_review_bundle,
    get_mapping_label_aliases,
    refresh_mapping_review_bundle,
    resolve_date_field_configuration,
    resolve_status_field_configuration,
    save_mapping_label_aliases,
)
from app.services.redcap_api_keys import (
    get_cached_redcap_api_key,
    has_cached_redcap_api_key,
    store_redcap_api_key,
)
from app.services.redcap import (
    RedcapServiceError,
    apply_locking_action,
    canonicalize_redcap_api_url,
    canonicalize_redcap_host_base_url,
    export_record_rows,
    fetch_redcap_preflight_bundle,
    fetch_locking_status,
    import_record_update,
    redcap_rate_limit_notifications,
    redcap_rate_limit_scope,
    set_redcap_rate_limit_for_host,
    set_redcap_rate_limit_for_scope,
)
from app.services.users import (
    UserManagementError,
    allowed_creatable_roles,
    can_manage_target,
    create_managed_user,
    get_user_by_id,
    list_users_for_actor,
    reset_user_password,
    set_user_active_state,
    set_user_role,
)
from app.services.job_queue import enqueue_job_processing, revoke_job_processing
from app.services.job_constants import (
    ACTIVE_JOB_STATUSES,
    JOBS_VISIBLE_STATUSES,
    MAPPING_AUTO_OPTION,
    MAPPING_NONE_OPTION,
    PRESTART_CANCELLABLE_JOB_STATUSES,
    REPORTABLE_JOB_STATUSES,
    USER_CANCELLABLE_JOB_STATUSES,
)
from app.services.form_complete import (
    expected_form_complete_field_name,
    fetch_form_complete_snapshot,
    is_form_marked_complete,
    row_uses_repeat_context,
    select_exported_record_row,
)


settings = get_settings()
router = APIRouter(include_in_schema=False)
app_dir = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(app_dir / "templates"))
templates.env.globals["asset_version"] = str(int((app_dir / "static" / "auth.css").stat().st_mtime))

REQUEST_TEMPLATE_FILENAME = "redcap-batch-request-template.csv"
PROCESS_MODAL_ID = "process-job-modal"
REQUEST_REQUIRED_COLUMNS = ("record_id", "target_instrument", "action")
REQUEST_ALLOWED_ACTIONS = {"lock", "unlock"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_FILENAME_LENGTH = 255
MAX_TEXT_INPUT_LENGTH = 2048
MAX_API_KEY_LENGTH = 512
MAX_CSV_CELL_LENGTH = 512
RECENT_JOBS_LIMIT = 3
DEFAULT_LIVE_PROCESSING_MAX_ROWS = 5
QUERY_COLUMN_ALIASES = {
    "record": {"record", "record id", "record / instance"},
    "field": {"field", "field variable", "field name"},
    "status": {"status", "query status"},
    "event": {"event", "redcap event name"},
    "instance": {"instance", "repeat instance", "redcap repeat instance"},
}
REQUEST_TEMPLATE_COLUMNS = (
    {
        "name": "record_id",
        "required": True,
        "description": "REDCap record identifier for the target record.",
        "example": "10001",
    },
    {
        "name": "repeat_instance",
        "required": False,
        "description": "Repeat instance number for repeating instruments or events. Leave blank to use instance 1.",
        "example": "1",
    },
    {
        "name": "event_name",
        "required": False,
        "description": "Event unique name for longitudinal projects. Leave blank for classic projects.",
        "example": "visit_1_arm_1",
    },
    {
        "name": "arm_name",
        "required": False,
        "description": "Arm name when the project uses multiple arms and you want to preserve that context explicitly.",
        "example": "arm_1",
    },
    {
        "name": "target_instrument",
        "required": True,
        "description": "Instrument or form unique name that should be locked or unlocked.",
        "example": "eligibility_form",
    },
    {
        "name": "action",
        "required": True,
        "description": "Action to perform for this row. Use either lock or unlock.",
        "example": "lock",
    },
)


def get_optional_session(request: Request, db: Session) -> tuple[str | None, UserSession | None]:
    if settings.is_desktop:
        desktop_session = get_desktop_session(db)
        if desktop_session is not None:
            db.commit()
            return None, desktop_session

    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None, None

    session = get_valid_session_by_token(db, raw_token)
    return raw_token, session


def _can_manage_users(user: User) -> bool:
    return user.role in (Role.ADMIN, Role.SUPER_ADMIN)


def _build_sidebar_context(*, active_path: str, current_user: User | None = None) -> dict[str, object]:
    can_manage_users = current_user is not None and _can_manage_users(current_user)
    if current_user is None:
        nav_items = [
            {"label": "Sign In", "href": "/login", "is_active": active_path == "/login", "is_disabled": False},
            {"label": "Dashboard", "href": "/app", "is_active": False, "is_disabled": True},
            {"label": "Jobs", "href": "/jobs", "is_active": False, "is_disabled": True},
            {"label": "Mappings", "href": "/mappings", "is_active": False, "is_disabled": True},
            {"label": "Reports", "href": "/reports", "is_active": False, "is_disabled": True},
            {"label": "Users", "href": "/users", "is_active": False, "is_disabled": True},
        ]
    elif settings.is_desktop:
        nav_items = [
            {"label": "Jobs", "href": "/jobs", "is_active": active_path == "/jobs", "is_disabled": False},
            {"label": "Mappings", "href": "/mappings", "is_active": active_path == "/mappings", "is_disabled": False},
            {"label": "Reports", "href": "/reports", "is_active": active_path == "/reports", "is_disabled": False},
        ]
    else:
        nav_items = [
            {"label": "Dashboard", "href": "/app", "is_active": active_path == "/app", "is_disabled": False},
            {"label": "Jobs", "href": "/jobs", "is_active": active_path == "/jobs", "is_disabled": False},
            {"label": "Mappings", "href": "/mappings", "is_active": active_path == "/mappings", "is_disabled": False},
            {"label": "Reports", "href": "/reports", "is_active": active_path == "/reports", "is_disabled": False},
            {
                "label": "Users",
                "href": "/users",
                "is_active": active_path == "/users",
                "is_disabled": not can_manage_users,
            },
        ]
    return {
        "nav_items": nav_items,
        "sidebar_user": None if settings.is_desktop else current_user,
        "show_logout": current_user is not None and not settings.is_desktop,
        "is_desktop": settings.is_desktop,
    }


def _redirect_with_message(destination: str, *, success: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {key: value for key, value in {"success": success, "error": error}.items() if value}
    url = destination if not params else f"{destination}?{urlencode(params)}"
    return RedirectResponse(url, status_code=303)


def _build_request_template_csv() -> str:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow([column["name"] for column in REQUEST_TEMPLATE_COLUMNS])
    return buffer.getvalue()


def _build_jobs_redirect(
    *,
    success: str | None = None,
    error: str | None = None,
    open_modal: str | None = None,
    process_job_id: UUID | None = None,
    open_import: bool = False,
    import_error: str | None = None,
    import_api_url: str | None = None,
) -> RedirectResponse:
    params = {
        key: value
        for key, value in {
            "success": success,
            "error": error,
            "open_modal": open_modal,
            "process_job_id": str(process_job_id) if process_job_id else None,
            "open_import": "1" if open_import else None,
            "import_error": import_error,
            "import_api_url": import_api_url,
        }.items()
        if value
    }
    return RedirectResponse(f"/jobs?{urlencode(params)}" if params else "/jobs", status_code=303)


def _build_mappings_redirect(
    job_id: UUID,
    *,
    success: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    params = {"job_id": str(job_id)}
    if success:
        params["success"] = success
    if error:
        params["error"] = error
    return RedirectResponse(f"/mappings?{urlencode(params)}", status_code=303)


def _is_mapping_refresh_prompt_pending(job: Job) -> bool:
    options = job.options_json if isinstance(job.options_json, dict) else {}
    return bool(options.get("mapping_refresh_prompt_pending"))


def _get_mapping_refresh_continue_status(job: Job) -> JobStatus:
    options = job.options_json if isinstance(job.options_json, dict) else {}
    raw_status = str(options.get("mapping_refresh_continue_status") or "").strip()
    if raw_status:
        try:
            return JobStatus(raw_status)
        except ValueError:
            pass
    return JobStatus.READY if not options.get("mapping_review_required") else JobStatus.AWAITING_MAPPING_CONFIRMATION


def _clear_mapping_refresh_prompt(job: Job) -> None:
    options = dict(job.options_json) if isinstance(job.options_json, dict) else {}
    options.pop("mapping_refresh_prompt_pending", None)
    options.pop("mapping_refresh_continue_status", None)
    options.pop("mapping_refresh_confirmed_instrument_count", None)
    options.pop("mapping_refresh_confirmed_instruments", None)
    job.options_json = options


def _refresh_job_mapping_review(
    db: Session,
    *,
    job: Job,
    user_session_id: UUID,
) -> int:
    if not isinstance(job.validation_summary_json, dict) or not job.redcap_project_id:
        raise ValueError("This job does not have a stored mapping review bundle.")
    if job.redcap_host_id is None:
        raise ValueError("This job is not linked to a REDCap host configuration.")

    cleaned_api_key = get_cached_redcap_api_key(
        db,
        user_session_id=user_session_id,
        redcap_host_id=job.redcap_host_id,
    )
    if not cleaned_api_key:
        raise ValueError(
            "A valid REDCap API key is required to refresh mapping options. "
            "Re-import the request or start processing from the Jobs page after entering the API key again."
        )

    resolved_rate_limit = set_redcap_rate_limit_for_scope(
        job.redcap_api_url,
        _resolve_job_rate_limit(job),
        job.redcap_project_id,
    )
    with redcap_rate_limit_scope(job.redcap_api_url, job.redcap_project_id):
        preflight_bundle = fetch_redcap_preflight_bundle(job.redcap_api_url, cleaned_api_key)
    if not preflight_bundle["locking_api_available"]:
        reason = preflight_bundle["locking_api_probe"]["reason"]
        raise ValueError(f"locking_api is not enabled or not reachable for this REDCap project. {reason}")

    project_info = preflight_bundle["project_info"]
    refreshed_project_id = str(project_info.get("project_id") or "").strip()
    if not refreshed_project_id:
        raise ValueError("REDCap project information did not include a project_id during refresh.")
    if job.redcap_project_id and refreshed_project_id != job.redcap_project_id:
        raise ValueError(
            "The refreshed REDCap API key points to a different REDCap project than this job. "
            "Use the correct project API key and try again."
        )

    rows = list(db.scalars(select(JobRow).where(JobRow.job_id == job.id).order_by(JobRow.row_number)).all())
    if not rows:
        raise ValueError("This job does not contain any request rows to remap.")

    instrument_lookup = {
        str(item.get("instrument_name") or ""): item for item in preflight_bundle["instruments"] if item.get("instrument_name")
    }
    lower_instrument_lookup = {key.lower(): key for key in instrument_lookup}
    missing_instruments: list[str] = []
    for row in rows:
        canonical_instrument_name = instrument_lookup.get(row.target_instrument)
        if canonical_instrument_name is None:
            lowered_match = lower_instrument_lookup.get(row.target_instrument.lower())
            if lowered_match is None:
                missing_instruments.append(row.target_instrument)
                continue
            row.target_instrument = lowered_match

    if missing_instruments:
        raise ValueError(
            "The stored request references instrument names that were not found in REDCap anymore: "
            f"{', '.join(sorted(set(missing_instruments)))}."
        )

    target_instruments = _extract_target_instruments(
        [
            {"target_instrument": row.target_instrument}
            for row in rows
        ]
    )

    alias_bank = get_mapping_label_aliases(db)
    refreshed_bundle = build_mapping_review_bundle(
        instrument_rows=preflight_bundle["instruments"],
        metadata_rows=preflight_bundle["metadata"],
        export_field_name_rows=preflight_bundle["export_field_names"],
        target_instruments=target_instruments,
        alias_bank=alias_bank,
    )
    instrument_sequence = refreshed_bundle.get("instrument_sequence", [])
    instrument_reviews = refreshed_bundle.get("instrument_reviews", {})
    if not instrument_sequence or not instrument_reviews:
        raise ValueError("This job does not have a stored mapping review bundle.")

    now = utc_now()
    existing_mappings = {
        mapping.instrument_name: mapping
        for mapping in db.scalars(
            select(InstrumentMapping).where(
                InstrumentMapping.redcap_host_id == job.redcap_host_id,
                InstrumentMapping.redcap_project_id == job.redcap_project_id,
                InstrumentMapping.instrument_name.in_(instrument_sequence),
            )
        ).all()
    }

    for instrument_name in instrument_sequence:
        review = instrument_reviews.get(instrument_name)
        if not isinstance(review, dict):
            continue

        mapping = existing_mappings.get(instrument_name)
        field_names = {
            str(field.get("field_name") or "")
            for field in review.get("field_catalog", [])
            if isinstance(field, dict) and field.get("field_name")
        }
        existing_mapping_was_stale = False

        if mapping is None:
            mapping = InstrumentMapping(
                redcap_host_id=job.redcap_host_id,
                redcap_project_id=job.redcap_project_id,
                instrument_name=instrument_name,
            )
            db.add(mapping)
            _apply_inferred_mapping_defaults(mapping, review)
        elif mapping.status == MappingStatus.CONFIRMED and _mapping_fields_exist(mapping, field_names):
            if not mapping.form_complete_field_name:
                mapping.form_complete_field_name = _expected_form_complete_field_name(instrument_name)
            mapping.last_validated_at = now
        else:
            if mapping.status == MappingStatus.CONFIRMED:
                mapping.drift_detected_at = now
                existing_mapping_was_stale = True
            _apply_inferred_mapping_defaults(mapping, review)
            if existing_mapping_was_stale and mapping.confidence != MappingConfidence.HIGH:
                mapping.status = MappingStatus.STALE

        if mapping.last_validated_at is None:
            mapping.last_validated_at = now
        review["requires_confirmation"] = mapping.status != MappingStatus.CONFIRMED and mapping.confidence != MappingConfidence.HIGH

    review_instrument_count = sum(
        1 for instrument_name in instrument_sequence if instrument_reviews.get(instrument_name, {}).get("requires_confirmation")
    )
    validation_summary = dict(job.validation_summary_json)
    validation_summary["project_info"] = project_info
    validation_summary["locking_api_available"] = preflight_bundle["locking_api_available"]
    validation_summary["locking_api_listed"] = preflight_bundle["locking_api_listed"]
    validation_summary["locking_api_probe"] = preflight_bundle["locking_api_probe"]
    validation_summary["instrument_sequence"] = instrument_sequence
    validation_summary["instrument_reviews"] = instrument_reviews
    job.validation_summary_json = validation_summary

    options = job.options_json if isinstance(job.options_json, dict) else {}
    options["mapping_review_required"] = review_instrument_count > 0
    options["mapping_review_instrument_count"] = review_instrument_count
    job.options_json = options
    _clear_mapping_refresh_prompt(job)
    job.redcap_project_id = refreshed_project_id
    job.redcap_project_title = str(project_info.get("project_title") or "").strip() or None
    job.status = JobStatus.AWAITING_MAPPING_CONFIRMATION if review_instrument_count else JobStatus.READY
    if review_instrument_count == 0:
        job.last_error_summary = None
    _set_job_runtime_state(
        job,
        rate_limit_per_minute=resolved_rate_limit,
    )

    return review_instrument_count


def _continue_job_with_existing_mappings(job: Job) -> JobStatus:
    if not _is_mapping_refresh_prompt_pending(job):
        raise ValueError("This job does not need a mapping refresh decision.")

    continue_status = _get_mapping_refresh_continue_status(job)
    _clear_mapping_refresh_prompt(job)
    job.status = continue_status
    if continue_status == JobStatus.READY:
        job.last_error_summary = None
    return continue_status


def _contains_control_characters(value: str, *, allow_newlines: bool = False) -> bool:
    allowed_controls = {"\t"}
    if allow_newlines:
        allowed_controls.update({"\n", "\r"})

    return any(ord(character) < 32 and character not in allowed_controls for character in value)


def _strip_unsupported_control_characters(value: str, *, allow_newlines: bool = False) -> str:
    allowed_controls = {"\t"}
    if allow_newlines:
        allowed_controls.update({"\n", "\r"})

    return "".join(character for character in value if ord(character) >= 32 or character in allowed_controls)


def _sanitize_text_input(
    value: str,
    *,
    label: str,
    max_length: int = MAX_TEXT_INPUT_LENGTH,
    required: bool = True,
) -> str:
    cleaned_value = value.strip()
    if required and not cleaned_value:
        raise ValueError(f"Enter the {label}.")

    if len(cleaned_value) > max_length:
        raise ValueError(f"The {label} is too long.")

    if _contains_control_characters(cleaned_value):
        raise ValueError(f"The {label} contains unsupported characters.")

    return cleaned_value


def _sanitize_filename(filename: str, *, label: str) -> str:
    cleaned_filename = Path(filename.strip()).name
    if not cleaned_filename:
        raise ValueError(f"Choose a {label}.")

    if _contains_control_characters(cleaned_filename):
        raise ValueError(f"The {label} name contains unsupported characters.")

    cleaned_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", cleaned_filename)
    cleaned_filename = cleaned_filename.lstrip(".")[:MAX_FILENAME_LENGTH].strip()
    if not cleaned_filename:
        raise ValueError(f"Choose a {label}.")

    return cleaned_filename


def _read_uploaded_text_file(
    upload_file: UploadFile,
    *,
    label: str,
    repair_control_characters: bool = False,
) -> tuple[str, bytes]:
    file_bytes = upload_file.file.read(MAX_UPLOAD_BYTES + 1)
    if not file_bytes:
        raise ValueError(f"The selected {label} is empty.")

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"The selected {label} is too large.")

    try:
        decoded_text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label.capitalize()} must be UTF-8 encoded.") from exc

    if repair_control_characters:
        decoded_text = _strip_unsupported_control_characters(decoded_text, allow_newlines=True)
    elif _contains_control_characters(decoded_text, allow_newlines=True):
        raise ValueError(f"The selected {label} contains unsupported characters.")

    return decoded_text, file_bytes


def _sanitize_csv_cell(
    value: str,
    *,
    row_index: int,
    column_name: str,
    repair_control_characters: bool = False,
    max_length: int | None = MAX_CSV_CELL_LENGTH,
) -> str:
    cleaned_value = (
        _strip_unsupported_control_characters(value)
        if repair_control_characters
        else value
    ).strip()
    if max_length is not None and len(cleaned_value) > max_length:
        raise ValueError(f"Row {row_index} has a value that is too long in {column_name}.")

    if _contains_control_characters(cleaned_value):
        raise ValueError(f"Row {row_index} contains unsupported characters in {column_name}.")

    return cleaned_value


def _coerce_repeat_instance(value: str, *, row_index: int) -> int:
    cleaned_value = value.strip()
    if not cleaned_value:
        return 1

    try:
        repeat_instance = int(cleaned_value)
    except ValueError as exc:
        raise ValueError(f"Row {row_index} repeat_instance must be a whole number.") from exc

    if repeat_instance <= 0:
        raise ValueError(f"Row {row_index} repeat_instance must be greater than zero.")
    return repeat_instance


def _parse_request_import_file(request_file: UploadFile) -> tuple[str, list[dict[str, object]], bytes]:
    filename = _sanitize_filename(request_file.filename or "", label="request CSV file")

    if not filename.lower().endswith(".csv"):
        raise ValueError("Request import only accepts .csv files.")

    decoded_csv, file_bytes = _read_uploaded_text_file(request_file, label="request CSV")
    reader = csv.reader(StringIO(decoded_csv, newline=""))
    header = next(reader, None)
    if header is None:
        raise ValueError("The selected request CSV does not contain a header row.")

    normalized_header = [_sanitize_csv_cell(cell, row_index=1, column_name="header") for cell in header]
    expected_header = [column["name"] for column in REQUEST_TEMPLATE_COLUMNS]
    if normalized_header != expected_header:
        raise ValueError("Request CSV headers must match the current downloadable template.")

    parsed_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(reader, start=2):
        normalized_row = [
            _sanitize_csv_cell(
                cell,
                row_index=row_index,
                column_name=expected_header[position] if position < len(expected_header) else f"column_{position + 1}",
            )
            for position, cell in enumerate(row)
        ]
        if not any(normalized_row):
            continue

        if len(normalized_row) > len(expected_header) and any(normalized_row[len(expected_header):]):
            raise ValueError(f"Row {row_index} contains unexpected extra values.")

        row_values = {
            column_name: (normalized_row[position] if position < len(normalized_row) else "")
            for position, column_name in enumerate(expected_header)
        }

        missing_fields = [field for field in REQUEST_REQUIRED_COLUMNS if not row_values.get(field)]
        if missing_fields:
            raise ValueError(
                f"Row {row_index} is missing required value"
                f"{'s' if len(missing_fields) != 1 else ''}: {', '.join(missing_fields)}."
            )

        action_value = row_values["action"].lower()
        if action_value not in REQUEST_ALLOWED_ACTIONS:
            raise ValueError(f"Row {row_index} has an invalid action. Use lock or unlock.")

        parsed_rows.append(
            {
                "row_number": len(parsed_rows) + 1,
                "record_id": row_values["record_id"],
                "repeat_instance": _coerce_repeat_instance(row_values["repeat_instance"], row_index=row_index),
                "event_name": row_values["event_name"] or None,
                "arm_name": row_values["arm_name"] or None,
                "target_instrument": row_values["target_instrument"],
                "action": action_value,
            }
        )

    if not parsed_rows:
        raise ValueError("Add at least one request row before importing the CSV.")

    return filename, parsed_rows, file_bytes


def _validate_redcap_api_url(redcap_api_url: str) -> str:
    cleaned_url = _sanitize_text_input(redcap_api_url, label="REDCap API URL")

    parsed_url = urlparse(cleaned_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise ValueError("Enter a valid REDCap API URL that starts with http:// or https://.")

    return cleaned_url


def _validate_redcap_api_key(redcap_api_key: str) -> str:
    return _sanitize_text_input(redcap_api_key, label="REDCap API key", max_length=MAX_API_KEY_LENGTH)


def _normalize_header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _resolve_query_column_indexes(normalized_header: list[str]) -> dict[str, int]:
    column_indexes: dict[str, int] = {}
    for column_name, aliases in QUERY_COLUMN_ALIASES.items():
        for index, header_value in enumerate(normalized_header):
            if header_value in aliases or any(alias in header_value for alias in aliases):
                column_indexes[column_name] = index
                break

    missing_columns = [column_name for column_name in ("record", "field", "status") if column_name not in column_indexes]
    if missing_columns:
        raise ValueError(
            "The existing queries CSV must include columns for record, field, and status."
        )

    return column_indexes


def _build_field_to_form_lookup(metadata_rows: list[dict[str, object]]) -> dict[str, str]:
    field_to_form: dict[str, str] = {}
    form_names: set[str] = set()
    for metadata_row in metadata_rows:
        field_name = str(metadata_row.get("field_name") or "").strip()
        form_name = str(metadata_row.get("form_name") or "").strip()
        if form_name:
            form_names.add(form_name)
        if field_name and form_name and field_name not in field_to_form:
            field_to_form[field_name] = form_name

    for form_name in form_names:
        complete_field_name = f"{form_name}_complete"
        field_to_form.setdefault(complete_field_name, form_name)

    return field_to_form


def _extract_query_field_name(field_value: str, *, row_index: int) -> str:
    match = re.match(r"([A-Za-z0-9_]+)", field_value.strip())
    if match is None:
        raise ValueError(f"Could not parse the REDCap field name from the existing queries CSV at row {row_index}.")
    field_name = match.group(1)
    if len(field_name) > MAX_CSV_CELL_LENGTH:
        raise ValueError(f"Row {row_index} has a value that is too long in Field.")
    return field_name


def _parse_optional_positive_int(value: str, *, row_index: int, label: str) -> int | None:
    cleaned_value = value.strip()
    if not cleaned_value:
        return None
    try:
        parsed_value = int(cleaned_value)
    except ValueError as exc:
        raise ValueError(f"Row {row_index} has an invalid {label}.") from exc
    if parsed_value <= 0:
        raise ValueError(f"Row {row_index} has an invalid {label}.")
    return parsed_value


def _parse_query_record_context(
    record_value: str,
    *,
    row_index: int,
    explicit_instance_value: str | None = None,
) -> tuple[str, int | None]:
    normalized_record_value = record_value.strip()
    inferred_instance: int | None = None
    combined_match = re.match(r"^(.*?)\s*\(#\s*(\d+)\s*\)\s*$", normalized_record_value)
    if combined_match is not None:
        normalized_record_value = combined_match.group(1).strip()
        inferred_instance = int(combined_match.group(2))

    if not normalized_record_value:
        raise ValueError(f"Row {row_index} in the existing queries CSV is missing a record identifier.")

    explicit_instance = _parse_optional_positive_int(explicit_instance_value or "", row_index=row_index, label="query instance")
    return normalized_record_value, explicit_instance if explicit_instance is not None else inferred_instance


def _is_unresolved_query_status(status_value: str) -> bool:
    return status_value.strip().lower() != "closed"


def _query_matches_request_row(query_row: dict[str, object], request_row: dict[str, object]) -> bool:
    if str(query_row.get("form_name") or "").strip().lower() != str(request_row.get("target_instrument") or "").strip().lower():
        return False

    if str(query_row.get("record_id") or "").strip() != str(request_row.get("record_id") or "").strip():
        return False

    query_event = str(query_row.get("event_name") or "").strip().lower()
    request_event = str(request_row.get("event_name") or "").strip().lower()
    if query_event and query_event != request_event:
        return False

    query_instance = query_row.get("repeat_instance")
    request_instance = request_row.get("repeat_instance")
    if isinstance(query_instance, int) and query_instance != request_instance:
        return False
    if query_instance is None and isinstance(request_instance, int) and request_instance > 1:
        return False

    return True


def _inspect_queries_import_file(
    queries_file: UploadFile | None,
    *,
    metadata_rows: list[dict[str, object]],
    parsed_request_rows: list[dict[str, object]],
) -> tuple[str | None, int | None, dict[int, int]]:
    if queries_file is None or not (queries_file.filename or "").strip():
        return None, None, {}

    filename = _sanitize_filename(queries_file.filename or "", label="existing queries CSV")
    if not filename.lower().endswith(".csv"):
        raise ValueError("Existing queries import only accepts .csv files.")

    decoded_csv, _ = _read_uploaded_text_file(
        queries_file,
        label="existing queries CSV",
        repair_control_characters=True,
    )
    reader = csv.reader(StringIO(decoded_csv, newline=""))
    header = next(reader, None)
    if header is None:
        raise ValueError("The selected existing queries CSV does not contain a header row.")

    normalized_header = [
        _sanitize_csv_cell(
            cell,
            row_index=1,
            column_name="header",
            repair_control_characters=True,
        )
        for cell in header
    ]
    if not any(normalized_header):
        raise ValueError("The selected existing queries CSV does not contain a valid header row.")
    query_column_indexes = _resolve_query_column_indexes([_normalize_header_key(cell) for cell in normalized_header])
    field_to_form_lookup = _build_field_to_form_lookup(metadata_rows)

    row_count = 0
    unresolved_queries: list[dict[str, object]] = []
    for row_index, row in enumerate(reader, start=2):
        row_values = {
            column_name: _sanitize_csv_cell(
                row[index] if index < len(row) else "",
                row_index=row_index,
                column_name=normalized_header[index] if index < len(normalized_header) else column_name,
                repair_control_characters=True,
                max_length=None if column_name == "field" else MAX_CSV_CELL_LENGTH,
            )
            for column_name, index in query_column_indexes.items()
        }
        if not any(row_values.values()):
            continue

        row_count += 1
        record_value = row_values["record"]
        field_value = row_values["field"]
        status_value = row_values["status"]
        event_value = row_values.get("event", "")
        instance_value = row_values.get("instance", "")

        record_id, repeat_instance = _parse_query_record_context(
            record_value,
            row_index=row_index,
            explicit_instance_value=instance_value,
        )
        field_name = _extract_query_field_name(field_value, row_index=row_index)
        form_name = field_to_form_lookup.get(field_name)
        if form_name is None or not _is_unresolved_query_status(status_value):
            continue

        unresolved_queries.append(
            {
                "record_id": record_id,
                "repeat_instance": repeat_instance,
                "event_name": event_value or None,
                "field_name": field_name,
                "form_name": form_name,
            }
        )

    if row_count == 0:
        raise ValueError("Add at least one row to the existing queries CSV before importing it.")

    query_match_counts: dict[int, int] = {}
    for request_row in parsed_request_rows:
        row_number = int(request_row["row_number"])
        matches = sum(1 for query_row in unresolved_queries if _query_matches_request_row(query_row, request_row))
        if matches:
            query_match_counts[row_number] = matches

    return filename, row_count, query_match_counts


def _normalize_optional_form_value(value: str, *, label: str, max_length: int = MAX_TEXT_INPUT_LENGTH) -> str | None:
    cleaned_value = _sanitize_text_input(value, label=label, max_length=max_length, required=False)
    return cleaned_value or None


def _can_access_job(current_user: User, job: Job) -> bool:
    return current_user.role in (Role.ADMIN, Role.SUPER_ADMIN) or job.owner_id == current_user.id


def _extract_target_instruments(parsed_rows: list[dict[str, object]]) -> list[str]:
    seen: set[str] = set()
    ordered_instruments: list[str] = []
    for row in parsed_rows:
        instrument_name = str(row["target_instrument"])
        if instrument_name not in seen:
            seen.add(instrument_name)
            ordered_instruments.append(instrument_name)
    return ordered_instruments


def _determine_job_type(parsed_rows: list[dict[str, object]]) -> tuple[JobType, bool]:
    actions = {str(row["action"]) for row in parsed_rows}
    if actions == {"unlock"}:
        return JobType.UNLOCK, False
    return JobType.LOCK, len(actions) > 1


def _upsert_redcap_host(db: Session, api_url: str) -> REDCapHost:
    host_base_url = canonicalize_redcap_host_base_url(api_url)
    host = db.scalar(select(REDCapHost).where(REDCapHost.base_url == host_base_url))
    if host is not None:
        if host.rate_limit_per_minute is None:
            host.rate_limit_per_minute = settings.redcap_rate_limit_per_minute_default
            db.flush()
        set_redcap_rate_limit_for_host(host.base_url, host.rate_limit_per_minute)
        return host

    host = REDCapHost(
        base_url=host_base_url,
        display_name=urlparse(host_base_url).netloc,
        rate_limit_per_minute=settings.redcap_rate_limit_per_minute_default,
    )
    db.add(host)
    db.flush()
    set_redcap_rate_limit_for_host(host.base_url, host.rate_limit_per_minute)
    return host


def _resolve_job_rate_limit(job: Job) -> int:
    host_limit = job.redcap_host.rate_limit_per_minute if job.redcap_host is not None else None
    resolved_limit = host_limit or settings.redcap_rate_limit_per_minute_default
    return max(1, int(resolved_limit))


def _find_active_project_job(db: Session, *, job: Job) -> Job | None:
    statement = select(Job).where(
        Job.id != job.id,
        Job.status.in_(tuple(ACTIVE_JOB_STATUSES)),
    )
    if job.redcap_host_id is not None:
        statement = statement.where(Job.redcap_host_id == job.redcap_host_id)
    else:
        statement = statement.where(Job.redcap_api_url == job.redcap_api_url)

    if job.redcap_project_id:
        statement = statement.where(Job.redcap_project_id == job.redcap_project_id)

    statement = statement.order_by(Job.created_at.asc()).limit(1)
    return db.scalar(statement)


def _mapping_fields_exist(mapping: InstrumentMapping, field_names: set[str]) -> bool:
    for field_name in (mapping.form_complete_field_name, mapping.crf_status_field_name, mapping.lock_date_field_name):
        if field_name and field_name not in field_names:
            return False
    return True


def _expected_form_complete_field_name(instrument_name: str) -> str:
    return expected_form_complete_field_name(instrument_name)


def _apply_inferred_mapping_defaults(mapping: InstrumentMapping, review: dict[str, object]) -> None:
    selected_status = review.get("selected_status_candidate") or {}
    selected_date = review.get("selected_date_candidate") or {}
    mapping.form_complete_field_name = _expected_form_complete_field_name(mapping.instrument_name)
    mapping.crf_status_field_name = selected_status.get("field_name")
    mapping.lock_date_field_name = selected_date.get("field_name")
    mapping.status = MappingStatus.INFERRED
    mapping.confidence = MappingConfidence(str(review.get("confidence") or MappingConfidence.CONFIRM.value))
    mapping.coded_values_json = {
        "status_field": selected_status,
        "date_field": selected_date,
        "instrument_label": review.get("instrument_label"),
    }
    mapping.confirmed_by_user_id = None


def _get_mapping_job(
    db: Session,
    *,
    current_user: User,
    job_id: UUID | None,
) -> Job | None:
    if job_id is not None:
        job = db.get(Job, job_id)
        if job is None or not _can_access_job(current_user, job):
            return None
        return job

    if current_user.role in (Role.ADMIN, Role.SUPER_ADMIN):
        statement = (
            select(Job)
            .where(Job.status == JobStatus.AWAITING_MAPPING_CONFIRMATION)
            .order_by(Job.created_at.desc())
        )
    else:
        statement = (
            select(Job)
            .where(
                Job.owner_id == current_user.id,
                Job.status == JobStatus.AWAITING_MAPPING_CONFIRMATION,
            )
            .order_by(Job.created_at.desc())
        )

    candidates = list(db.scalars(statement.limit(20)).all())
    for candidate in candidates:
        if not _is_mapping_refresh_prompt_pending(candidate):
            return candidate
    return None


def _derive_review_status_lock_value(
    field_definition: dict[str, object] | None,
    alias_bank: dict[str, list[str]],
    *,
    fallback_value: str,
) -> str:
    if fallback_value:
        return fallback_value
    if not isinstance(field_definition, dict):
        return fallback_value

    try:
        status_configuration = resolve_status_field_configuration(field_definition, alias_bank)
    except ValueError:
        return fallback_value

    if str(status_configuration.get("mode") or "").strip().lower() == "checkbox":
        return str(
            status_configuration.get("choice_value")
            or status_configuration.get("export_field_name")
            or fallback_value
            or ""
        ).strip()
    return str(status_configuration.get("lock_value") or fallback_value or "").strip()


def _build_mapping_rows(
    job: Job,
    mappings: list[InstrumentMapping],
    *,
    alias_bank: dict[str, list[str]],
) -> list[dict[str, object]]:
    validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
    review_lookup = validation_summary.get("instrument_reviews", {})
    instrument_sequence = validation_summary.get("instrument_sequence", [])
    mapping_lookup = {mapping.instrument_name: mapping for mapping in mappings}

    review_rows: list[dict[str, object]] = []
    for instrument_name in instrument_sequence:
        mapping = mapping_lookup.get(instrument_name)
        review = review_lookup.get(instrument_name)
        if mapping is None or not isinstance(review, dict):
            continue
        if not bool(review.get("requires_confirmation")):
            continue

        field_catalog = review.get("field_catalog", [])
        status_options = [
            field
            for field in field_catalog
            if field.get("field_type") in {"yesno", "truefalse", "checkbox", "radio", "dropdown"}
        ]
        date_options = [field for field in field_catalog if field.get("field_type") == "text"]
        coded_values = mapping.coded_values_json if isinstance(mapping.coded_values_json, dict) else {}
        status_config = coded_values.get("status_field") if isinstance(coded_values.get("status_field"), dict) else {}
        date_config = coded_values.get("date_field") if isinstance(coded_values.get("date_field"), dict) else {}
        selected_status_candidate = review.get("selected_status_candidate") if isinstance(review.get("selected_status_candidate"), dict) else {}
        selected_date_candidate = review.get("selected_date_candidate") if isinstance(review.get("selected_date_candidate"), dict) else {}
        use_confirmed_mapping_defaults = mapping.status == MappingStatus.CONFIRMED
        selected_status_field_name = (
            mapping.crf_status_field_name
            if use_confirmed_mapping_defaults
            else selected_status_candidate.get("field_name")
        ) or MAPPING_NONE_OPTION
        selected_date_field_name = (
            mapping.lock_date_field_name
            if use_confirmed_mapping_defaults
            else selected_date_candidate.get("field_name")
        ) or MAPPING_NONE_OPTION
        selected_status_field_definition = next(
            (field for field in status_options if field.get("field_name") == selected_status_field_name),
            None,
        )
        selected_status_field_type = str(selected_status_field_definition.get("field_type") or "").strip().lower() if isinstance(selected_status_field_definition, dict) else ""
        selected_status_lock_value = (
            (status_config.get("choice_value") or status_config.get("lock_value"))
            if use_confirmed_mapping_defaults
            else selected_status_candidate.get("lock_value")
        ) or ""
        selected_status_lock_value = _derive_review_status_lock_value(
            selected_status_field_definition if isinstance(selected_status_field_definition, dict) else None,
            alias_bank,
            fallback_value=str(selected_status_lock_value),
        )
        selected_status_value_help = None
        if selected_status_field_type == "checkbox":
            matching_export = None
            for export_item in selected_status_field_definition.get("export_field_names", []) if isinstance(selected_status_field_definition, dict) else []:
                choice_value = str(export_item.get("choice_value") or "").strip()
                export_field_name = str(export_item.get("export_field_name") or "").strip()
                if selected_status_lock_value and (
                    choice_value == selected_status_lock_value or export_field_name == selected_status_lock_value
                ):
                    matching_export = export_item
                    break
            if selected_status_lock_value:
                export_field_name = str(matching_export.get("export_field_name") or "").strip() if isinstance(matching_export, dict) else ""
                if export_field_name:
                    selected_status_value_help = (
                        f"Pre-filled with checkbox choice {selected_status_lock_value} "
                        f"({export_field_name}). Change this only if a different checkbox option should mean locked."
                    )
                else:
                    selected_status_value_help = (
                        f"Pre-filled with checkbox choice {selected_status_lock_value}. "
                        "Change this only if a different checkbox option should mean locked."
                    )
            else:
                selected_status_value_help = (
                    "Enter the checkbox choice code or REDCap export field name that should mean locked."
                )
        elif selected_status_field_type in {"radio", "dropdown"}:
            if selected_status_lock_value:
                selected_status_value_help = (
                    f"Pre-filled with coded choice {selected_status_lock_value}. "
                    "Change this only if another coded option should mean locked."
                )
            else:
                selected_status_value_help = "Enter the coded choice value that should mean locked."
        elif selected_status_field_type in {"yesno", "truefalse"}:
            selected_status_value_help = "This field locks with value 1 and clears automatically on unlock."
        selected_date_format = (
            date_config.get("date_format")
            if use_confirmed_mapping_defaults
            else selected_date_candidate.get("date_format")
        ) or MAPPING_AUTO_OPTION

        review_rows.append(
            {
                "mapping": mapping,
                "review": review,
                "status_options": status_options,
                "date_options": date_options,
                "selected_status_field_name": selected_status_field_name,
                "selected_date_field_name": selected_date_field_name,
                "selected_status_lock_value": selected_status_lock_value,
                "selected_status_value_help": selected_status_value_help,
                "selected_date_format": selected_date_format,
            }
        )

    return review_rows


def _get_review_instruments(job: Job) -> list[str]:
    validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
    instrument_sequence = validation_summary.get("instrument_sequence", [])
    review_lookup = validation_summary.get("instrument_reviews", {})
    return [
        instrument_name
        for instrument_name in instrument_sequence
        if isinstance(review_lookup.get(instrument_name), dict) and review_lookup[instrument_name].get("requires_confirmation")
    ]


def _format_row_count(count: int) -> str:
    return f"{count} row{'s' if count != 1 else ''}"


def _resolve_live_processing_max_rows() -> int:
    return max(int(getattr(settings, "live_processing_max_rows", DEFAULT_LIVE_PROCESSING_MAX_ROWS) or 0), 0)


def _resolve_processing_mode(*, row_count: int) -> str:
    live_processing_max_rows = _resolve_live_processing_max_rows()
    if live_processing_max_rows > 0 and 0 < row_count <= live_processing_max_rows:
        return "live"
    return "background"


def _resolve_retry_processing_mode(*, job: Job, row_count: int) -> str:
    runtime_mode = str(_get_job_runtime_state(job).get("mode") or "").strip()
    if runtime_mode in {"live", "background"}:
        return runtime_mode
    return _resolve_processing_mode(row_count=row_count)


def _has_shared_redcap_api_key_cache_secret() -> bool:
    return bool((settings.redcap_api_key_cache_secret or "").strip())


def _processing_mode_runtime_phrase(processing_mode: str) -> str:
    return "live in this browser session" if processing_mode == "live" else "in the background"


def _processing_mode_action_label(processing_mode: str) -> str:
    return "live processing" if processing_mode == "live" else "background processing"


def _processing_mode_title(processing_mode: str) -> str:
    return "Live" if processing_mode == "live" else "Background"


def _get_retryable_rows(db: Session, *, job_id: UUID) -> list[JobRow]:
    return list(
        db.scalars(
            select(JobRow)
            .options(selectinload(JobRow.row_result))
            .outerjoin(RowResult, RowResult.job_row_id == JobRow.id)
            .where(JobRow.job_id == job_id)
            .where(
                or_(
                    RowResult.id.is_(None),
                    RowResult.status == RowResultStatus.FAILED,
                    RowResult.status == RowResultStatus.CANCELLED,
                    and_(
                        RowResult.status == RowResultStatus.PENDING,
                        RowResult.processed_at.is_(None),
                    ),
                )
            )
            .order_by(JobRow.row_number)
        ).all()
    )


def _summarize_retry_candidates(rows: list[JobRow]) -> dict[str, object]:
    failed_count = 0
    unprocessed_count = 0

    for row in rows:
        row_result = row.row_result
        if row_result is not None and row_result.status == RowResultStatus.FAILED:
            failed_count += 1
        else:
            unprocessed_count += 1

    if unprocessed_count > 0:
        selection_copy = (
            f"{_format_row_count(failed_count)} that failed and {_format_row_count(unprocessed_count)} that were not processed yet"
            if failed_count > 0
            else f"{_format_row_count(unprocessed_count)} that were not processed yet"
        )
        return {
            "count": len(rows),
            "failed_count": failed_count,
            "unprocessed_count": unprocessed_count,
            "retry_scope": "remaining_rows",
            "action_label": "Retry Remaining Rows",
            "selection_copy": selection_copy,
            "progress_summary": "remaining rows",
        }

    return {
        "count": len(rows),
        "failed_count": failed_count,
        "unprocessed_count": 0,
        "retry_scope": "failed_only",
        "action_label": "Retry Failed Rows",
        "selection_copy": f"{_format_row_count(failed_count)} that failed",
        "progress_summary": "failed rows",
    }


def _mark_unprocessed_rows_as_cancelled(
    db: Session,
    *,
    job_id: UUID,
    reason: str,
    message: str = "Row was not processed because the background run stopped early.",
) -> int:
    rows = list(db.scalars(select(JobRow).where(JobRow.job_id == job_id).order_by(JobRow.row_number)).all())
    cancelled_count = 0

    for row in rows:
        row_result = row.row_result
        if row_result is not None and row_result.processed_at is not None:
            continue

        if row_result is None:
            row_result = RowResult(job_row_id=row.id)
            db.add(row_result)

        row_result.status = RowResultStatus.CANCELLED
        row_result.outcome_code = "not_processed"
        row_result.message = message
        row_result.redcap_http_status = None
        row_result.query_blocking_count = None
        row_result.details_json = {
            "job_failure_reason": reason,
            "processing_steps": [
                message,
            ],
        }
        row_result.duration_ms = None
        row_result.processed_at = None
        cancelled_count += 1

    return cancelled_count


def _build_job_outcome_copy(job: Job) -> str:
    unprocessed_rows = max((job.total_rows or 0) - (job.processed_rows or 0), 0)

    if job.status == JobStatus.COMPLETED:
        if job.ignored_rows and not job.locked_rows and not job.unlocked_rows:
            verb = "was" if job.ignored_rows == 1 else "were"
            return f"No lock changes were applied. {_format_row_count(job.ignored_rows).capitalize()} {verb} skipped."
        if job.ignored_rows:
            verb = "was" if job.ignored_rows == 1 else "were"
            return (
                f"Completed with changes. {_format_row_count(job.ignored_rows).capitalize()} {verb} skipped."
            )
        return "Completed successfully."

    if job.failed_rows == 0 and job.blocked_rows > 0:
        return job.last_error_summary or (
            f"{_format_row_count(job.blocked_rows).capitalize()} could not run because REDCap reported that the target "
            "form has no existing data yet."
        )

    parts: list[str] = []
    if job.failed_rows:
        parts.append(f"{_format_row_count(job.failed_rows).capitalize()} failed.")
    if job.blocked_rows:
        verb = "was" if job.blocked_rows == 1 else "were"
        parts.append(f"{_format_row_count(job.blocked_rows).capitalize()} {verb} blocked.")
    if unprocessed_rows:
        verb = "was" if unprocessed_rows == 1 else "were"
        parts.append(f"{_format_row_count(unprocessed_rows).capitalize()} {verb} not processed after the run stopped early.")
    if job.last_error_summary:
        parts.append(job.last_error_summary)

    return " ".join(parts) if parts else "Processing failed."


def _build_job_result_stats(job: Job) -> list[str]:
    if job.status not in REPORTABLE_JOB_STATUSES and job.processed_rows <= 0:
        return []

    stats: list[str] = []
    if job.locked_rows:
        stats.append(f"{job.locked_rows} locked")
    if job.unlocked_rows:
        stats.append(f"{job.unlocked_rows} unlocked")
    if job.ignored_rows:
        stats.append(f"{job.ignored_rows} skipped")
    if job.blocked_rows:
        stats.append(f"{job.blocked_rows} blocked")
    if job.failed_rows:
        stats.append(f"{job.failed_rows} failed")

    unprocessed_rows = max((job.total_rows or 0) - (job.processed_rows or 0), 0)
    if unprocessed_rows:
        stats.append(f"{unprocessed_rows} not processed")

    return stats


def _build_job_scope_filter(current_user: User):
    if current_user.role in (Role.ADMIN, Role.SUPER_ADMIN):
        return None
    return Job.owner_id == current_user.id


def _get_job_runtime_state(job: Job) -> dict[str, object]:
    options = job.options_json if isinstance(job.options_json, dict) else {}
    runtime_state = options.get("runtime")
    return runtime_state if isinstance(runtime_state, dict) else {}


def _set_job_runtime_state(job: Job, **updates: object) -> None:
    options = dict(job.options_json) if isinstance(job.options_json, dict) else {}
    runtime_state = dict(options.get("runtime") or {})
    runtime_state.update(updates)
    options["runtime"] = runtime_state
    job.options_json = options


def _get_job_worker_task_id(job: Job) -> str | None:
    runtime_state = _get_job_runtime_state(job)
    task_id = str(runtime_state.get("worker_task_id") or "").strip()
    return task_id or None


def _finalize_job_cancellation(
    db: Session,
    *,
    job: Job,
    previous_status: JobStatus,
    cancellation_message: str,
    row_message: str,
    event_message: str,
    actor_user_id: UUID | None = None,
    processing_mode: str | None = None,
    request: Request | None = None,
) -> int:
    cancelled_count = _mark_unprocessed_rows_as_cancelled(
        db,
        job_id=job.id,
        reason=cancellation_message,
        message=row_message,
    )
    _recalculate_job_rollups(db, job=job)
    job.status = JobStatus.CANCELLED
    job.cancellation_requested_at = job.cancellation_requested_at or utc_now()
    job.completed_at = utc_now()
    job.last_error_summary = cancellation_message
    resolved_mode = str(_get_job_runtime_state(job).get("mode") or processing_mode or "background").strip() or "background"
    _set_job_runtime_state(
        job,
        mode=resolved_mode,
        phase="cancelled",
        latest_message=cancellation_message,
        rate_limit_wait_until=None,
    )
    _record_job_event(
        db,
        job=job,
        event_type="job.cancelled",
        message=event_message,
        status_from=previous_status,
        status_to=JobStatus.CANCELLED,
        payload_json={
            "cancelled_rows": cancelled_count,
            "processing_mode": resolved_mode,
        },
    )
    rows = _load_job_rows_for_report(db, job_id=job.id)
    _upsert_job_report(db, job=job, rows=rows)
    if actor_user_id is not None:
        record_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="jobs.cancel",
            object_type="job",
            object_id=str(job.id),
            request=request,
            metadata={
                "previous_status": previous_status.value,
                "cancelled_rows": cancelled_count,
                "processing_mode": resolved_mode,
            },
        )
    return cancelled_count


def _parse_runtime_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _summarize_job_progress(job: Job) -> dict[str, object]:
    runtime_state = _get_job_runtime_state(job)
    total_rows = max(int(runtime_state.get("active_row_count") or job.total_rows or 0), 0)
    processed_rows = max(job.processed_rows, 0)
    progress_percent = int((processed_rows / total_rows) * 100) if total_rows else 0
    latest_message = str(runtime_state.get("latest_message") or "").strip()
    processing_mode = str(runtime_state.get("mode") or "live").strip() or "live"
    resolved_rate_limit = int(runtime_state.get("rate_limit_per_minute") or _resolve_job_rate_limit(job))
    retry_scope = str(runtime_state.get("retry_scope") or "").strip()
    wait_until = _parse_runtime_timestamp(runtime_state.get("rate_limit_wait_until"))
    wait_seconds_remaining: int | None = None
    wait_message: str | None = None
    if wait_until is not None:
        wait_seconds_remaining = max(0, int((wait_until - utc_now()).total_seconds()))
        if wait_seconds_remaining > 0:
            wait_message = (
                f"Rate limit reached for this REDCap project. Resuming in about {wait_seconds_remaining} seconds."
            )

    if job.status == JobStatus.QUEUED and not latest_message:
        latest_message = (
            "Queued to start in the background."
            if processing_mode == "background"
            else "Preparing to start live processing in this browser session."
        )
    elif job.status == JobStatus.RUNNING and not latest_message:
        latest_message = (
            "Processing rows in the background."
            if processing_mode == "background"
            else "Processing rows live in this browser session."
        )
    elif job.status == JobStatus.CANCEL_REQUESTED and not latest_message:
        latest_message = "Cancellation requested. Waiting for the current step to finish before stopping this job."
    elif job.status == JobStatus.WAITING_DUE_TO_RATE_LIMIT and not latest_message:
        latest_message = "Paused because the REDCap API rate limit was reached."

    summary_copy = f"{processed_rows} of {total_rows} rows processed" if total_rows else "No rows queued"
    if retry_scope == "failed_only":
        summary_copy = f"{processed_rows} of {total_rows} failed rows retried" if total_rows else "No failed rows to retry"
    elif retry_scope == "remaining_rows":
        summary_copy = f"{processed_rows} of {total_rows} remaining rows retried" if total_rows else "No rows left to retry"
    detail_parts = []
    if job.locked_rows:
        detail_parts.append(f"{job.locked_rows} locked")
    if job.unlocked_rows:
        detail_parts.append(f"{job.unlocked_rows} unlocked")
    if job.ignored_rows:
        detail_parts.append(f"{job.ignored_rows} skipped")
    if job.blocked_rows:
        detail_parts.append(f"{job.blocked_rows} blocked")
    if job.failed_rows:
        detail_parts.append(f"{job.failed_rows} failed")

    return {
        "visible": job.status in ACTIVE_JOB_STATUSES,
        "percent": progress_percent,
        "summary": summary_copy,
        "message": latest_message,
        "detail": ", ".join(detail_parts) if detail_parts else "",
        "wait_message": wait_message,
        "wait_seconds_remaining": wait_seconds_remaining,
        "mode": processing_mode,
        "rate_limit_copy": f"Rate limit: {resolved_rate_limit} calls/min for this REDCap project.",
        "rate_limit_per_minute": resolved_rate_limit,
        "retry_scope": retry_scope,
    }
def _recalculate_job_rollups(db: Session, *, job: Job) -> None:
    rows = list(db.scalars(select(JobRow).where(JobRow.job_id == job.id).order_by(JobRow.row_number)).all())
    processed_rows = 0
    locked_rows = 0
    unlocked_rows = 0
    ignored_rows = 0
    blocked_rows = 0
    failed_rows = 0

    for row in rows:
        row_result = row.row_result
        if row_result is None:
            continue
        if row_result.processed_at is not None:
            processed_rows += 1
        if row_result.status == RowResultStatus.SUCCESS:
            if row_result.outcome_code == "locked":
                locked_rows += 1
            elif row_result.outcome_code == "unlocked":
                unlocked_rows += 1
        elif row_result.status == RowResultStatus.IGNORED:
            ignored_rows += 1
        elif row_result.status == RowResultStatus.BLOCKED:
            blocked_rows += 1
        elif row_result.status == RowResultStatus.FAILED:
            failed_rows += 1

    job.processed_rows = processed_rows
    job.locked_rows = locked_rows
    job.unlocked_rows = unlocked_rows
    job.ignored_rows = ignored_rows
    job.blocked_rows = blocked_rows
    job.failed_rows = failed_rows


def _list_visible_jobs(
    db: Session,
    *,
    current_user: User,
    limit: int | None = None,
) -> list[Job]:
    statement = (
        select(Job)
        .options(selectinload(Job.redcap_host))
        .where(Job.status.in_(JOBS_VISIBLE_STATUSES))
        .order_by(Job.updated_at.desc())
    )
    scope_filter = _build_job_scope_filter(current_user)
    if scope_filter is not None:
        statement = statement.where(scope_filter)
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement).all())


def _get_job_report_map(db: Session, jobs: list[Job]) -> dict[UUID, Report]:
    if not jobs:
        return {}
    reports = list(
        db.scalars(
            select(Report)
            .where(
                Report.job_id.in_([job.id for job in jobs]),
                Report.report_type == ReportType.CSV,
            )
            .order_by(Report.created_at.desc())
        ).all()
    )
    report_map: dict[UUID, Report] = {}
    for report in reports:
        report_map.setdefault(report.job_id, report)
    return report_map


def _build_job_report_filename(job: Job) -> str:
    source_name = job.request_file_name or f"job-{job.id}"
    sanitized_name = _sanitize_filename(source_name, label="job request")
    stem = Path(sanitized_name).stem or f"job-{job.id}"
    return f"{stem}-report.csv"


def _serialize_report_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _serialize_processing_steps(details: dict[str, object]) -> str:
    raw_steps = details.get("processing_steps")
    if not isinstance(raw_steps, list):
        return ""
    return " | ".join(str(step) for step in raw_steps if str(step).strip())


def _build_job_report_csv(job: Job, rows: list[JobRow]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Job Type",
            "Project ID",
            "Project Title",
            "Request File Name",
            "Record ID",
            "Target Instrument",
            "Action",
            "Event Name",
            "Arm Name",
            "Repeat Instance",
            "Request Status",
            "Outcome",
            "Message",
            "Form Open Queries Count",
            "REDCap HTTP Status",
            "Action Called",
            "Locked By",
            "Locked At",
            "Status Before",
            "Status After",
        ]
    )

    for row in rows:
        row_result = row.row_result
        details = row_result.details_json if row_result and isinstance(row_result.details_json, dict) else {}
        writer.writerow(
            [
                job.job_type.value,
                job.redcap_project_id or "",
                job.redcap_project_title or "",
                job.request_file_name or "",
                row.record_id,
                row.target_instrument,
                row.action.value,
                row.event_name or "",
                row.arm_name or "",
                row.repeat_instance or "",
                row_result.status.value if row_result else "",
                row_result.outcome_code if row_result else "",
                row_result.message if row_result else "",
                row_result.query_blocking_count if row_result and row_result.query_blocking_count is not None else "",
                row_result.redcap_http_status if row_result and row_result.redcap_http_status is not None else "",
                _serialize_report_cell(details.get("action_called")),
                _serialize_report_cell(details.get("locked_by")),
                _serialize_report_cell(details.get("locked_at")),
                _serialize_report_cell(details.get("status_before")),
                _serialize_report_cell(details.get("status_after")),
            ]
        )

    return output.getvalue().encode("utf-8")


def _load_job_rows_for_report(db: Session, *, job_id: UUID) -> list[JobRow]:
    return list(
        db.scalars(
            select(JobRow)
            .options(selectinload(JobRow.row_result))
            .where(JobRow.job_id == job_id)
            .order_by(JobRow.row_number)
        ).all()
    )


def _upsert_job_report(db: Session, *, job: Job, rows: list[JobRow]) -> Report:
    report = db.scalar(
        select(Report).where(
            Report.job_id == job.id,
            Report.report_type == ReportType.CSV,
        )
    )
    report_bytes = _build_job_report_csv(job, rows)
    checksum = hashlib.sha256(report_bytes).hexdigest()
    file_name = _build_job_report_filename(job)

    if report is None:
        report = Report(
            job_id=job.id,
            report_type=ReportType.CSV,
            storage_path=f"generated://job/{job.id}/{file_name}",
            file_name=file_name,
            content_type="text/csv",
        )
        db.add(report)

    report.file_name = file_name
    report.content_type = "text/csv"
    report.storage_path = f"generated://job/{job.id}/{file_name}"
    report.byte_size = len(report_bytes)
    report.checksum_sha256 = checksum
    return report


def _ensure_report_record(db: Session, *, job: Job) -> Report:
    report = db.scalar(
        select(Report).where(
            Report.job_id == job.id,
            Report.report_type == ReportType.CSV,
        )
    )
    file_name = _build_job_report_filename(job)
    if report is None:
        report = Report(
            job_id=job.id,
            report_type=ReportType.CSV,
            storage_path=f"generated://job/{job.id}/{file_name}",
            file_name=file_name,
            content_type="text/csv",
        )
        db.add(report)
        return report

    report.file_name = report.file_name or file_name
    report.content_type = report.content_type or "text/csv"
    report.storage_path = report.storage_path or f"generated://job/{job.id}/{report.file_name}"
    return report


def _ensure_report_records_for_jobs(db: Session, jobs: list[Job]) -> None:
    for job in jobs:
        if job.status not in REPORTABLE_JOB_STATUSES:
            continue
        _ensure_report_record(db, job=job)


def _build_report_rows(
    db: Session,
    *,
    current_user: User,
    excluded_job_ids: set[UUID] | None = None,
) -> list[dict[str, object]]:
    statement = (
        select(Report)
        .options(selectinload(Report.job).selectinload(Job.redcap_host))
        .join(Job, Report.job_id == Job.id)
        .where(Report.report_type == ReportType.CSV)
        .order_by(Job.updated_at.desc())
    )
    scope_filter = _build_job_scope_filter(current_user)
    if scope_filter is not None:
        statement = statement.where(scope_filter)
    if excluded_job_ids:
        statement = statement.where(~Report.job_id.in_(excluded_job_ids))

    reports = list(db.scalars(statement).all())
    return [
        {
            "report": report,
            "job": report.job,
            "host_label": (
                (report.job.redcap_host.display_name if report.job.redcap_host is not None else None)
                or urlparse(report.job.redcap_api_url).netloc
                or report.job.redcap_api_url
            ),
            "download_href": f"/reports/{report.id}/download",
        }
        for report in reports
    ]


def _build_job_review_rows(jobs: list[Job], *, db: Session, user_session_id: UUID) -> list[dict[str, object]]:
    report_map = _get_job_report_map(db, jobs)
    job_rows: list[dict[str, object]] = []
    for job in jobs:
        review_instruments = _get_review_instruments(job)
        report = report_map.get(job.id)
        progress = _summarize_job_progress(job)
        host_label = (
            (job.redcap_host.display_name if job.redcap_host is not None else None)
            or urlparse(job.redcap_api_url).netloc
            or job.redcap_api_url
        )
        action_href = None
        action_label = None
        action_kind = None
        cancel_label = None
        continue_label = None
        remap_label = None
        launch_mode: str | None = None
        status_label = job.status.value.replace("_", " ").title()
        if job.status == JobStatus.AWAITING_MAPPING_CONFIRMATION and _is_mapping_refresh_prompt_pending(job):
            action_hint = (
                "This REDCap project already has saved extra-field mappings. "
                "Refresh mappings from REDCap if the project metadata may have changed, or continue with the existing saved mappings."
            )
            status_tone = "status-review"
            status_label = "Refresh Decision"
            cancel_label = "Cancel Job"
            continue_label = "Use existing mappings"
            remap_label = "Refresh mappings"
        elif job.status == JobStatus.AWAITING_MAPPING_CONFIRMATION:
            action_href = f"/mappings?job_id={job.id}"
            action_label = "Review mappings"
            action_kind = "link"
            action_hint = "Manual review needed before execution."
            status_tone = "status-review"
            cancel_label = "Cancel Job"
            remap_label = "Refresh options"
        elif job.status == JobStatus.READY:
            launch_mode = _resolve_processing_mode(row_count=job.total_rows or 0)
            if has_cached_redcap_api_key(db, user_session_id=user_session_id, redcap_host_id=job.redcap_host_id):
                action_label = "Process"
                action_kind = "process_cached"
                action_hint = (
                    "Starts live processing in this browser session for this REDCap project using the saved API key. "
                    if launch_mode == "live"
                    else "Starts background processing for this REDCap project using the saved API key. "
                ) + (
                    f"{progress['rate_limit_copy']}"
                )
            else:
                action_label = "Process"
                action_kind = "process"
                action_hint = (
                    "Enter the REDCap API key to start live processing in this browser session for this REDCap project. "
                    if launch_mode == "live"
                    else "Enter the REDCap API key to start background processing for this REDCap project. "
                ) + (
                    f"{progress['rate_limit_copy']}"
                )
            status_tone = "status-active"
            cancel_label = "Cancel Job"
        elif job.status == JobStatus.QUEUED:
            active_mode = str(progress["mode"])
            action_hint = (
                f"Queued {_processing_mode_runtime_phrase(active_mode)} for this REDCap project. {progress['rate_limit_copy']}"
            )
            status_tone = "status-review"
            cancel_label = "Cancel Job"
        elif job.status == JobStatus.RUNNING:
            active_mode = str(progress["mode"])
            action_hint = (
                f"This job is currently being processed {_processing_mode_runtime_phrase(active_mode)}. "
                f"{progress['rate_limit_copy']}"
            )
            status_tone = "status-review"
            cancel_label = "Cancel Job"
        elif job.status == JobStatus.WAITING_DUE_TO_RATE_LIMIT:
            active_mode = str(progress["mode"])
            action_hint = progress["wait_message"] or (
                "Waiting for the REDCap API rate-limit window to reopen before "
                f"{_processing_mode_action_label(active_mode)} continues."
            )
            status_tone = "status-review"
            cancel_label = "Cancel Job"
        elif job.status == JobStatus.CANCEL_REQUESTED:
            action_hint = progress["message"] or "Cancellation requested. Waiting for the current step to finish."
            status_tone = "status-review"
        elif job.status == JobStatus.CANCELLED:
            retry_rows = _get_retryable_rows(db, job_id=job.id)
            retry_summary = _summarize_retry_candidates(retry_rows)
            retry_launch_mode = _resolve_retry_processing_mode(job=job, row_count=int(retry_summary["count"]))
            launch_mode = retry_launch_mode if retry_summary["count"] else None
            if retry_summary["count"] and has_cached_redcap_api_key(db, user_session_id=user_session_id, redcap_host_id=job.redcap_host_id):
                action_label = "Re-process"
                action_kind = "process_cached"
                action_hint = (
                    f"{job.last_error_summary or 'Processing was cancelled.'} "
                    f"Re-process will continue with {retry_summary['selection_copy']} "
                    f"{_processing_mode_runtime_phrase(retry_launch_mode)} using the saved API key."
                )
            elif retry_summary["count"]:
                action_label = "Re-process"
                action_kind = "process"
                action_hint = (
                    f"{job.last_error_summary or 'Processing was cancelled.'} "
                    f"Re-process will continue with {retry_summary['selection_copy']} "
                    f"{_processing_mode_runtime_phrase(retry_launch_mode)} once you enter the API key."
                )
            elif report is not None:
                action_href = f"/reports/{report.id}/download"
                action_label = "Export Report"
                action_kind = "download"
                action_hint = _build_job_outcome_copy(job)
            else:
                action_hint = job.last_error_summary or "Cancelled before processing started."
            status_tone = "status-inactive"
        elif job.status == JobStatus.COMPLETED:
            action_href = f"/reports/{report.id}/download" if report is not None else None
            action_label = "Export Report" if report is not None else None
            action_kind = "download" if report is not None else None
            action_hint = _build_job_outcome_copy(job)
            status_tone = "status-active"
        elif job.status in {JobStatus.COMPLETED_WITH_ERRORS, JobStatus.FAILED}:
            retry_rows = _get_retryable_rows(db, job_id=job.id)
            retry_summary = _summarize_retry_candidates(retry_rows)
            retry_launch_mode = _resolve_retry_processing_mode(job=job, row_count=int(retry_summary["count"]))
            launch_mode = retry_launch_mode if retry_summary["count"] else None
            if retry_summary["count"] and has_cached_redcap_api_key(db, user_session_id=user_session_id, redcap_host_id=job.redcap_host_id):
                action_label = str(retry_summary["action_label"])
                action_kind = "process_cached"
                action_hint = (
                    f"{_build_job_outcome_copy(job)} Retry will process {retry_summary['selection_copy']} only "
                    f"{_processing_mode_runtime_phrase(retry_launch_mode)} with the saved API key."
                )
            elif retry_summary["count"]:
                action_label = str(retry_summary["action_label"])
                action_kind = "process"
                action_hint = (
                    f"{_build_job_outcome_copy(job)} Retry will process {retry_summary['selection_copy']} only "
                    f"{_processing_mode_runtime_phrase(retry_launch_mode)} once you enter the API key."
                )
            elif report is not None:
                action_href = f"/reports/{report.id}/download"
                action_label = "Export Report"
                action_kind = "download"
                action_hint = _build_job_outcome_copy(job)
            else:
                action_hint = _build_job_outcome_copy(job)
            status_tone = "status-inactive"
        else:
            action_hint = "Processing failed."
            status_tone = "status-inactive"

        job_rows.append(
            {
                "job": job,
                "host_label": host_label,
                "review_instruments": review_instruments,
                "review_count": len(review_instruments),
                "result_stats": _build_job_result_stats(job),
                "status_label": status_label,
                "status_tone": status_tone,
                "action_href": action_href,
                "action_label": action_label,
                "action_kind": action_kind,
                "action_hint": action_hint,
                "cancel_label": cancel_label,
                "continue_label": continue_label,
                "remap_label": remap_label,
                "launch_mode": launch_mode,
                "report_href": f"/reports/{report.id}/download" if report is not None else None,
                "progress": progress,
            }
        )
    return job_rows


def _is_truthy_flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _extract_record_id_field_name(metadata_rows: list[dict[str, object]]) -> str:
    for row in metadata_rows:
        field_name = str(row.get("field_name") or "").strip()
        if field_name:
            return field_name
    raise ValueError("REDCap metadata did not include a record ID field.")


def _normalize_query_match_counts(raw_value: object) -> dict[int, int]:
    if not isinstance(raw_value, dict):
        return {}

    query_match_counts: dict[int, int] = {}
    for row_number, count in raw_value.items():
        try:
            normalized_row_number = int(str(row_number))
            normalized_count = int(count)
        except (TypeError, ValueError):
            continue
        if normalized_row_number > 0 and normalized_count > 0:
            query_match_counts[normalized_row_number] = normalized_count
    return query_match_counts


# Thin aliases so existing call sites in this module keep working while the
# real implementations live in app.services.form_complete.
_row_uses_repeat_context = row_uses_repeat_context
_select_exported_record_row = select_exported_record_row
_is_form_marked_complete = is_form_marked_complete
_fetch_form_complete_snapshot = fetch_form_complete_snapshot


def _format_redcap_temporal_value(
    current_timestamp: datetime,
    *,
    date_format: str,
    value_strategy: str,
    validation_type: str,
) -> str:
    if date_format == "DMY":
        date_fragment = current_timestamp.strftime("%d/%m/%Y")
    elif date_format == "MDY":
        date_fragment = current_timestamp.strftime("%m/%d/%Y")
    else:
        date_fragment = current_timestamp.strftime("%Y-%m-%d")

    if value_strategy != "current_datetime":
        return date_fragment

    time_fragment = "%H:%M:%S" if "seconds" in validation_type else "%H:%M"
    return f"{date_fragment} {current_timestamp.strftime(time_fragment)}"


def _build_shadow_field_payload(
    *,
    record_id_field_name: str,
    row: JobRow,
    mapping: InstrumentMapping | None,
    is_longitudinal: bool,
    repeating_forms_events: list[dict[str, object]],
) -> dict[str, object] | None:
    if mapping is None or not isinstance(mapping.coded_values_json, dict):
        return None

    status_config = mapping.coded_values_json.get("status_field")
    date_config = mapping.coded_values_json.get("date_field")
    if not isinstance(status_config, dict):
        status_config = {"mode": "none"}
    if not isinstance(date_config, dict):
        date_config = {"mode": "none"}

    payload: dict[str, object] = {record_id_field_name: row.record_id}
    if is_longitudinal and row.event_name:
        payload["redcap_event_name"] = row.event_name
    if _row_uses_repeat_context(row, repeating_forms_events=repeating_forms_events):
        payload["redcap_repeat_instrument"] = row.target_instrument
        payload["redcap_repeat_instance"] = row.repeat_instance

    status_field_name = str(status_config.get("field_name") or mapping.crf_status_field_name or "").strip()
    status_field_type = str(status_config.get("field_type") or "").strip().lower()
    status_mode = str(status_config.get("mode") or status_field_type).strip().lower()
    if status_field_name:
        payload_field_name = status_field_name
        lock_value = str(status_config.get("lock_value") or "1")
        unlock_value = str(status_config.get("unlock_value") if "unlock_value" in status_config else "")

        if status_mode == "checkbox" or status_field_type == "checkbox":
            checkbox_choice_value = str(status_config.get("choice_value") or status_config.get("lock_value") or "1").strip() or "1"
            payload_field_name = (
                str(status_config.get("export_field_name") or "").strip()
                or f"{status_field_name}___{checkbox_choice_value}"
            )
            if "unlock_value" not in status_config:
                unlock_value = "0"
            if not lock_value:
                lock_value = "1"
        elif status_mode in {"yesno", "truefalse"} and "unlock_value" not in status_config:
            unlock_value = ""

        if payload_field_name and status_mode not in {"", "none"}:
            payload[payload_field_name] = lock_value if row.action == RowAction.LOCK else unlock_value

    field_name = str(date_config.get("field_name") or "").strip()
    date_mode = str(date_config.get("mode") or "").strip().lower()
    if field_name and date_mode != "none":
        if row.action == RowAction.LOCK:
            payload[field_name] = _format_redcap_temporal_value(
                utc_now(),
                date_format=str(date_config.get("date_format") or "YMD"),
                value_strategy=str(date_config.get("value_strategy") or "current_date"),
                validation_type=str(date_config.get("validation_type") or ""),
            )
        else:
            payload[field_name] = date_config.get("unlock_value", "")

    context_only_keys = {
        record_id_field_name,
        "redcap_event_name",
        "redcap_repeat_instrument",
        "redcap_repeat_instance",
    }
    if set(payload.keys()).issubset(context_only_keys):
        return None
    return payload


def _extract_shadow_import_date_format(mapping: InstrumentMapping | None) -> str | None:
    if mapping is None or not isinstance(mapping.coded_values_json, dict):
        return None

    date_config = mapping.coded_values_json.get("date_field")
    if not isinstance(date_config, dict):
        return None

    date_mode = str(date_config.get("mode") or "").strip().lower()
    if date_mode == "none":
        return None

    date_format = str(date_config.get("date_format") or "").strip().upper()
    return date_format or None


def _record_job_event(
    db: Session,
    *,
    job: Job,
    event_type: str,
    level: EventLevel = EventLevel.INFO,
    message: str | None = None,
    job_row_id: UUID | None = None,
    payload_json: dict[str, object] | None = None,
    status_from: JobStatus | None = None,
    status_to: JobStatus | None = None,
) -> None:
    db.add(
        JobEvent(
            job_id=job.id,
            job_row_id=job_row_id,
            level=level,
            event_type=event_type,
            status_from=status_from,
            status_to=status_to,
            message=message,
            payload_json=payload_json,
        )
    )


def _status_state_is_ambiguous(*, lock_state: str, locked_by: str | None, locked_at: str | None) -> bool:
    return lock_state == "" and bool(locked_by or locked_at)


@router.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    destination = "/app" if session else "/login"
    return RedirectResponse(destination, status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session:
        return RedirectResponse("/app", status_code=303)

    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "page_title": "Sign In",
            "has_users": user_count > 0,
            "user_count": user_count,
            **_build_sidebar_context(active_path="/login"),
        },
    )


@router.get("/app", response_class=HTMLResponse)
def app_home(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    now = utc_now()
    dashboard_stats = {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "super_admins": db.scalar(
            select(func.count()).select_from(User).where(User.role == Role.SUPER_ADMIN)
        )
        or 0,
        "active_sessions": db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        )
        or 0,
        "jobs": db.scalar(select(func.count()).select_from(Job)) or 0,
        "reports": db.scalar(select(func.count()).select_from(Report)) or 0,
        "mappings": db.scalar(select(func.count()).select_from(InstrumentMapping)) or 0,
        "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
    }

    return templates.TemplateResponse(
        request=request,
        name="app_home.html",
        context={
            "page_title": "Workspace",
            "user": session.user,
            "session": session,
            "dashboard_stats": dashboard_stats,
            "can_manage_users": _can_manage_users(session.user),
            **_build_sidebar_context(active_path="/app", current_user=session.user),
        },
    )


def _render_workspace_placeholder(
    request: Request,
    *,
    current_user: User,
    page_title: str,
    section_label: str,
    heading: str,
    copy: str,
    active_path: str,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="placeholder_page.html",
        context={
            "page_title": page_title,
            "user": current_user,
            "section_label": section_label,
            "heading": heading,
            "copy": copy,
            **_build_sidebar_context(active_path=active_path, current_user=current_user),
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    process_job_param = request.query_params.get("process_job_id")
    try:
        process_job_id = UUID(process_job_param) if process_job_param else None
    except ValueError:
        process_job_id = None

    jobs = _list_visible_jobs(db, current_user=session.user, limit=RECENT_JOBS_LIMIT)
    _ensure_report_records_for_jobs(db, jobs)
    db.commit()

    job_review_rows = _build_job_review_rows(jobs, db=db, user_session_id=session.id)
    selected_process_job = next((row for row in job_review_rows if row["job"].id == process_job_id), None)

    return templates.TemplateResponse(
        request=request,
        name="jobs.html",
        context={
            "page_title": "Jobs",
            "user": session.user,
            "session": session,
            "job_review_rows": job_review_rows,
            "recent_jobs_limit": RECENT_JOBS_LIMIT,
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
            "import_card_open": request.query_params.get("open_import") == "1"
            or bool(request.query_params.get("import_error")),
            "import_error_message": request.query_params.get("import_error"),
            "import_form_values": {
                "redcap_api_url": request.query_params.get("import_api_url") or "",
            },
            "open_modal": request.query_params.get("open_modal"),
            "process_modal_id": PROCESS_MODAL_ID,
            "selected_process_job": selected_process_job,
            **_build_sidebar_context(active_path="/jobs", current_user=session.user),
        },
    )


@router.get("/jobs/progress")
def jobs_progress(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    jobs = _list_visible_jobs(db, current_user=session.user, limit=RECENT_JOBS_LIMIT)
    job_review_rows = _build_job_review_rows(jobs, db=db, user_session_id=session.id)
    serialized_rows = [
        {
            "job_id": str(row["job"].id),
            "status": row["job"].status.value,
            "status_label": row["status_label"],
            "status_tone": row["status_tone"],
            "action_hint": row["action_hint"],
            "updated_at": row["job"].updated_at.isoformat(),
            "progress": row["progress"],
        }
        for row in job_review_rows
    ]
    return JSONResponse(
        {
            "jobs": serialized_rows,
            "has_active_jobs": any(row["job"].status in ACTIVE_JOB_STATUSES for row in job_review_rows),
        }
    )


@router.get("/jobs/template.csv")
def download_jobs_template(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    record_audit_event(
        db,
        actor_user_id=session.user.id,
        action="jobs.template_download",
        object_type="job_request_template",
        object_id=REQUEST_TEMPLATE_FILENAME,
        request=request,
        metadata={"column_count": len(REQUEST_TEMPLATE_COLUMNS)},
    )
    db.commit()

    return Response(
        content=_build_request_template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{REQUEST_TEMPLATE_FILENAME}"'},
    )


@router.post("/jobs/import")
def import_jobs_request_file(
    request: Request,
    redcap_api_url: str = Form(default=""),
    redcap_api_key: str = Form(default=""),
    request_file: UploadFile | None = File(default=None),
    queries_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    submitted_api_url = str(redcap_api_url or "").strip()[:MAX_TEXT_INPUT_LENGTH]
    try:
        cleaned_api_url = canonicalize_redcap_api_url(_validate_redcap_api_url(redcap_api_url))
        cleaned_api_key = _validate_redcap_api_key(redcap_api_key)
    except ValueError as exc:
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="jobs.import_request_failed",
            object_type="job_request_import",
            request=request,
            metadata={"reason": str(exc)},
        )
        db.commit()
        return _build_jobs_redirect(
            open_import=True,
            import_error=str(exc),
            import_api_url=submitted_api_url,
        )

    if request_file is None:
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="jobs.import_request_failed",
            object_type="job_request_import",
            request=request,
            metadata={"reason": "No file selected."},
        )
        db.commit()
        return _build_jobs_redirect(
            open_import=True,
            import_error="Choose a request CSV file to import.",
            import_api_url=cleaned_api_url,
        )

    try:
        filename, parsed_rows, request_file_bytes = _parse_request_import_file(request_file)
        preflight_bundle = fetch_redcap_preflight_bundle(cleaned_api_url, cleaned_api_key)
        queries_filename, queries_row_count, query_match_counts = _inspect_queries_import_file(
            queries_file,
            metadata_rows=preflight_bundle["metadata"],
            parsed_request_rows=parsed_rows,
        )
    except (RedcapServiceError, ValueError) as exc:
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="jobs.import_request_failed",
            object_type="job_request_import",
            object_id=request_file.filename or None,
            request=request,
            metadata={"reason": str(exc)},
        )
        db.commit()
        return _build_jobs_redirect(
            open_import=True,
            import_error=str(exc),
            import_api_url=cleaned_api_url,
        )

    if not preflight_bundle["locking_api_available"]:
        reason = preflight_bundle["locking_api_probe"]["reason"]
        error_message = f"locking_api is not enabled or not reachable for this REDCap project. {reason}"
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="jobs.import_request_failed",
            object_type="job_request_import",
            object_id=filename,
            request=request,
            metadata={"reason": error_message, "api_url": cleaned_api_url},
        )
        db.commit()
        return _build_jobs_redirect(
            open_import=True,
            import_error=error_message,
            import_api_url=cleaned_api_url,
        )

    project_info = preflight_bundle["project_info"]
    redcap_project_id = str(project_info.get("project_id") or "").strip()
    if not redcap_project_id:
        error_message = "REDCap project information did not include a project_id."
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="jobs.import_request_failed",
            object_type="job_request_import",
            object_id=filename,
            request=request,
            metadata={"reason": error_message, "api_url": cleaned_api_url},
        )
        db.commit()
        return _build_jobs_redirect(
            open_import=True,
            import_error=error_message,
            import_api_url=cleaned_api_url,
        )

    instrument_lookup = {
        str(item.get("instrument_name") or ""): item for item in preflight_bundle["instruments"] if item.get("instrument_name")
    }
    lower_instrument_lookup = {key.lower(): key for key in instrument_lookup}
    missing_instruments: list[str] = []
    for row in parsed_rows:
        target_instrument = str(row["target_instrument"])
        canonical_instrument_name = instrument_lookup.get(target_instrument)
        if canonical_instrument_name is None:
            lowered_match = lower_instrument_lookup.get(target_instrument.lower())
            if lowered_match is None:
                missing_instruments.append(target_instrument)
                continue
            row["target_instrument"] = lowered_match

    if missing_instruments:
        error_message = (
            "The request CSV references instrument names that were not found in REDCap: "
            f"{', '.join(sorted(set(missing_instruments)))}."
        )
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="jobs.import_request_failed",
            object_type="job_request_import",
            object_id=filename,
            request=request,
            metadata={"reason": error_message, "api_url": cleaned_api_url},
        )
        db.commit()
        return _build_jobs_redirect(
            open_import=True,
            import_error=error_message,
            import_api_url=cleaned_api_url,
        )

    redcap_host = _upsert_redcap_host(db, cleaned_api_url)
    store_redcap_api_key(
        db,
        user_session_id=session.id,
        redcap_host_id=redcap_host.id,
        api_key=cleaned_api_key,
    )
    target_instruments = _extract_target_instruments(parsed_rows)
    alias_bank = get_mapping_label_aliases(db)
    mapping_review_bundle = build_mapping_review_bundle(
        instrument_rows=preflight_bundle["instruments"],
        metadata_rows=preflight_bundle["metadata"],
        export_field_name_rows=preflight_bundle["export_field_names"],
        target_instruments=target_instruments,
        alias_bank=alias_bank,
    )

    now = utc_now()
    existing_mappings = {
        mapping.instrument_name: mapping
        for mapping in db.scalars(
            select(InstrumentMapping).where(
                InstrumentMapping.redcap_host_id == redcap_host.id,
                InstrumentMapping.redcap_project_id == redcap_project_id,
                InstrumentMapping.instrument_name.in_(target_instruments),
            )
        ).all()
    }
    reused_confirmed_mapping_instruments: list[str] = []

    for instrument_name in target_instruments:
        review = mapping_review_bundle["instrument_reviews"][instrument_name]
        mapping = existing_mappings.get(instrument_name)
        field_names = {field["field_name"] for field in review["field_catalog"]}
        existing_mapping_was_stale = False

        if mapping is None:
            mapping = InstrumentMapping(
                redcap_host_id=redcap_host.id,
                redcap_project_id=redcap_project_id,
                instrument_name=instrument_name,
            )
            db.add(mapping)
            _apply_inferred_mapping_defaults(mapping, review)
        elif mapping.status == MappingStatus.CONFIRMED and _mapping_fields_exist(mapping, field_names):
            if not mapping.form_complete_field_name:
                mapping.form_complete_field_name = _expected_form_complete_field_name(instrument_name)
            mapping.last_validated_at = now
            reused_confirmed_mapping_instruments.append(instrument_name)
        else:
            if mapping.status == MappingStatus.CONFIRMED:
                mapping.drift_detected_at = now
                existing_mapping_was_stale = True
            _apply_inferred_mapping_defaults(mapping, review)
            if existing_mapping_was_stale and mapping.confidence != MappingConfidence.HIGH:
                mapping.status = MappingStatus.STALE

        if mapping.last_validated_at is None:
            mapping.last_validated_at = now
        review["requires_confirmation"] = mapping.status != MappingStatus.CONFIRMED and mapping.confidence != MappingConfidence.HIGH

    review_instrument_count = sum(
        1 for instrument_name in target_instruments if mapping_review_bundle["instrument_reviews"][instrument_name]["requires_confirmation"]
    )
    mapping_refresh_prompt_pending = bool(reused_confirmed_mapping_instruments)
    continue_status = JobStatus.AWAITING_MAPPING_CONFIRMATION if review_instrument_count else JobStatus.READY
    job_type, has_mixed_actions = _determine_job_type(parsed_rows)
    job = Job(
        owner_id=session.user.id,
        redcap_host_id=redcap_host.id,
        job_type=job_type,
        status=JobStatus.AWAITING_MAPPING_CONFIRMATION if (review_instrument_count or mapping_refresh_prompt_pending) else JobStatus.READY,
        redcap_api_url=cleaned_api_url,
        redcap_project_id=redcap_project_id,
        redcap_project_title=str(project_info.get("project_title") or "").strip() or None,
        request_file_name=filename,
        queries_file_name=queries_filename,
        source_file_checksum=hashlib.sha256(request_file_bytes).hexdigest(),
        total_rows=len(parsed_rows),
        options_json={
            "queries_file_attached": bool(queries_filename),
            "queries_row_count": queries_row_count,
            "rows_with_unresolved_queries": len(query_match_counts),
            "has_mixed_actions": has_mixed_actions,
            "mapping_review_required": review_instrument_count > 0,
            "mapping_review_instrument_count": review_instrument_count,
            "mapping_refresh_prompt_pending": mapping_refresh_prompt_pending,
            "mapping_refresh_continue_status": continue_status.value if mapping_refresh_prompt_pending else None,
            "mapping_refresh_confirmed_instrument_count": len(reused_confirmed_mapping_instruments),
            "mapping_refresh_confirmed_instruments": reused_confirmed_mapping_instruments,
        },
        validation_summary_json={
            "project_info": project_info,
            "locking_api_available": preflight_bundle["locking_api_available"],
            "locking_api_listed": preflight_bundle["locking_api_listed"],
            "locking_api_probe": preflight_bundle["locking_api_probe"],
            "instrument_sequence": mapping_review_bundle["instrument_sequence"],
            "instrument_reviews": mapping_review_bundle["instrument_reviews"],
            "queries_file_name": queries_filename,
            "queries_row_count": queries_row_count,
            "query_matches_by_row_number": {str(row_number): count for row_number, count in query_match_counts.items()},
        },
    )
    db.add(job)
    db.flush()

    for row in parsed_rows:
        db.add(
            JobRow(
                job_id=job.id,
                row_number=int(row["row_number"]),
                action=RowAction(str(row["action"])),
                record_id=str(row["record_id"]),
                event_name=row["event_name"],
                arm_name=row["arm_name"],
                repeat_instance=int(row["repeat_instance"]),
                target_instrument=str(row["target_instrument"]),
                has_unresolved_queries=int(row["row_number"]) in query_match_counts,
            )
        )

    record_audit_event(
        db,
        actor_user_id=session.user.id,
        action="jobs.preflight_created",
        object_type="job",
        object_id=str(job.id),
        request=request,
        metadata={
            "api_url": cleaned_api_url,
            "project_id": redcap_project_id,
            "project_title": job.redcap_project_title,
            "row_count": len(parsed_rows),
            "instrument_count": len(target_instruments),
            "queries_file_name": queries_filename,
            "queries_row_count": queries_row_count,
        },
    )
    del cleaned_api_key
    db.commit()

    if mapping_refresh_prompt_pending:
        confirmed_mapping_count = len(reused_confirmed_mapping_instruments)
        confirmed_mapping_copy = f"{confirmed_mapping_count} form{'s' if confirmed_mapping_count != 1 else ''}"
        if review_instrument_count:
            success_message = (
                f"Imported {filename}. This REDCap project already has saved mappings for "
                f"{confirmed_mapping_copy}. Confirm whether REDCap changed before continuing to mapping review."
            )
        else:
            success_message = (
                f"Imported {filename}. This REDCap project already has saved mappings for "
                f"{confirmed_mapping_copy}. Confirm whether REDCap changed before this job is marked ready."
            )
    elif review_instrument_count:
        success_message = (
            f"Imported {filename}. Review {review_instrument_count} form mapping"
            f"{'s' if review_instrument_count != 1 else ''} from the Jobs queue before the execution stage."
        )
    else:
        success_message = f"Imported {filename}. The form mappings were identified automatically and no manual review is needed."

    return _build_jobs_redirect(success=success_message)


def run_job_processing(
    job_id: UUID,
    actor_user_id: UUID,
    api_key: str,
    retry_row_ids: list[UUID],
    *,
    processing_mode: str = "background",
    user_session_id: UUID | None = None,
) -> None:
    processing_mode = "live" if processing_mode == "live" else "background"
    db = SessionLocal()
    try:
        retry_row_ids = [UUID(str(row_id)) for row_id in retry_row_ids]
        job = db.get(Job, job_id)
        if job is None:
            return
        if job.status == JobStatus.CANCELLED and not retry_row_ids:
            return

        def cancel_if_requested(cancellation_message: str) -> bool:
            db.refresh(job, attribute_names=["status", "cancellation_requested_at"])
            if job.status != JobStatus.CANCEL_REQUESTED:
                return False
            _finalize_job_cancellation(
                db,
                job=job,
                previous_status=JobStatus.CANCEL_REQUESTED,
                cancellation_message=cancellation_message,
                row_message="Row was not processed because the job was cancelled during background processing.",
                event_message="Cancelled during background processing. Remaining rows were marked as not processed.",
                actor_user_id=actor_user_id,
                processing_mode=processing_mode,
            )
            db.commit()
            return True

        if cancel_if_requested("Job was cancelled before background processing started."):
            return
        cleaned_api_key = api_key.strip()
        if not cleaned_api_key and user_session_id is not None and job.redcap_host_id is not None:
            cached_api_key = get_cached_redcap_api_key(
                db,
                user_session_id=user_session_id,
                redcap_host_id=job.redcap_host_id,
            )
            if cached_api_key:
                cleaned_api_key = cached_api_key
        if not cleaned_api_key:
            if processing_mode == "background" and not _has_shared_redcap_api_key_cache_secret():
                raise ValueError(
                    "Background processing requires REDCAP_API_KEY_CACHE_SECRET to be configured with the same value "
                    "for the API and worker services before the encrypted REDCap API key cache can be reused."
                )
            raise ValueError(
                "A valid REDCap API key was not available for this background job. Please start the job again from the Jobs page."
            )

        resolved_rate_limit = set_redcap_rate_limit_for_scope(
            job.redcap_api_url,
            _resolve_job_rate_limit(job),
            job.redcap_project_id,
        )

        def on_rate_limit_event(event_type: str, payload: dict[str, object]) -> None:
            wait_seconds = max(1, int(float(payload.get("wait_seconds") or 0) + 0.999))
            if event_type == "waiting":
                wait_until = utc_now().timestamp() + wait_seconds
                previous_status = job.status
                job.status = JobStatus.WAITING_DUE_TO_RATE_LIMIT
                _set_job_runtime_state(
                    job,
                    mode=processing_mode,
                    phase="rate_limited",
                    latest_message=(
                        f"Paused after reaching the REDCap API limit of {int(payload.get('rate_limit_per_minute') or resolved_rate_limit)} "
                        f"calls per minute for this REDCap project during {_processing_mode_action_label(processing_mode)}."
                    ),
                    rate_limit_wait_until=datetime.fromtimestamp(wait_until, tz=utc_now().tzinfo).isoformat(),
                    rate_limit_per_minute=int(payload.get("rate_limit_per_minute") or resolved_rate_limit),
                )
                _record_job_event(
                    db,
                    job=job,
                    event_type="job.rate_limit_wait_started",
                    message=f"Rate limit reached for this REDCap project. Waiting about {wait_seconds} seconds before resuming.",
                    status_from=previous_status,
                    status_to=JobStatus.WAITING_DUE_TO_RATE_LIMIT,
                    payload_json={
                        "wait_seconds": wait_seconds,
                        "rate_limit_per_minute": int(payload.get("rate_limit_per_minute") or resolved_rate_limit),
                    },
                )
                db.commit()
            elif event_type == "resumed":
                db.refresh(job, attribute_names=["status", "cancellation_requested_at"])
                if job.status == JobStatus.CANCEL_REQUESTED:
                    return
                previous_status = job.status
                job.status = JobStatus.RUNNING
                _set_job_runtime_state(
                    job,
                    mode=processing_mode,
                    phase="processing_rows",
                    latest_message=f"Rate-limit window reopened. Resuming {_processing_mode_action_label(processing_mode)}.",
                    rate_limit_wait_until=None,
                    rate_limit_per_minute=int(payload.get("rate_limit_per_minute") or resolved_rate_limit),
                )
                _record_job_event(
                    db,
                    job=job,
                    event_type="job.rate_limit_wait_finished",
                    message=f"Rate-limit window reopened. {_processing_mode_title(processing_mode)} processing resumed.",
                    status_from=previous_status,
                    status_to=JobStatus.RUNNING,
                )
                db.commit()

        previous_status = job.status
        job.cancellation_requested_at = None
        job.processed_rows = 0
        job.locked_rows = 0
        job.unlocked_rows = 0
        job.ignored_rows = 0
        job.blocked_rows = 0
        job.failed_rows = 0
        job.last_error_summary = None
        job.started_at = utc_now()
        job.completed_at = None
        job.status = JobStatus.RUNNING
        retry_scope = "failed_only" if retry_row_ids else "all_rows"
        active_row_count = len(retry_row_ids) if retry_row_ids else job.total_rows
        retry_failed_count = len(retry_row_ids)
        retry_unprocessed_count = 0
        if retry_row_ids:
            retry_rows = list(db.scalars(select(JobRow).where(JobRow.id.in_(retry_row_ids)).order_by(JobRow.row_number)).all())
            retry_summary = _summarize_retry_candidates(retry_rows)
            retry_scope = str(retry_summary["retry_scope"])
            active_row_count = int(retry_summary["count"])
            retry_failed_count = int(retry_summary["failed_count"])
            retry_unprocessed_count = int(retry_summary["unprocessed_count"])
        _set_job_runtime_state(
            job,
            mode=processing_mode,
            phase="preflight",
            latest_message=(
                f"Checking REDCap access and loading project details before retrying remaining rows {_processing_mode_runtime_phrase(processing_mode)}."
                if retry_scope == "remaining_rows"
                else f"Checking REDCap access and loading project details before retrying failed rows {_processing_mode_runtime_phrase(processing_mode)}."
                if retry_row_ids
                else f"Checking REDCap access and loading project details {_processing_mode_runtime_phrase(processing_mode)}."
            ),
            rate_limit_wait_until=None,
            rate_limit_per_minute=resolved_rate_limit,
            retry_scope=retry_scope,
            active_row_count=active_row_count,
            retry_failed_count=retry_failed_count,
            retry_unprocessed_count=retry_unprocessed_count,
        )
        _record_job_event(
            db,
            job=job,
            event_type="job.processing_started",
            message=(
                f"{_processing_mode_title(processing_mode)} retry started for remaining rows from the Jobs page."
                if retry_scope == "remaining_rows"
                else f"{_processing_mode_title(processing_mode)} retry started for failed rows from the Jobs page."
                if retry_row_ids
                else f"{_processing_mode_title(processing_mode)} job execution started from the Jobs page."
            ),
            status_from=previous_status,
            status_to=JobStatus.RUNNING,
        )
        db.commit()

        if cancel_if_requested("Job was cancelled before background processing started."):
            return

        with redcap_rate_limit_scope(job.redcap_api_url, job.redcap_project_id), redcap_rate_limit_notifications(on_rate_limit_event):
            preflight_bundle = fetch_redcap_preflight_bundle(job.redcap_api_url, cleaned_api_key)
            if not preflight_bundle["locking_api_available"]:
                raise RedcapServiceError("locking_api is not enabled or not reachable for this REDCap project.")

            row_statement = select(JobRow).where(JobRow.job_id == job.id)
            if retry_row_ids:
                row_statement = row_statement.where(JobRow.id.in_(retry_row_ids))
            rows = list(db.scalars(row_statement.order_by(JobRow.row_number)).all())
            target_instruments = sorted({row.target_instrument for row in rows})
            mappings = {
                mapping.instrument_name: mapping
                for mapping in db.scalars(
                    select(InstrumentMapping).where(
                        InstrumentMapping.redcap_host_id == job.redcap_host_id,
                        InstrumentMapping.redcap_project_id == job.redcap_project_id,
                        InstrumentMapping.instrument_name.in_(target_instruments),
                    )
                ).all()
            }

            metadata_rows = preflight_bundle["metadata"]
            project_info = preflight_bundle["project_info"]
            repeating_forms_events = preflight_bundle["repeating_forms_events"]
            validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
            query_match_counts = _normalize_query_match_counts(validation_summary.get("query_matches_by_row_number"))
            is_longitudinal = any(
                _is_truthy_flag(project_info.get(key))
                for key in ("is_longitudinal", "is_longitudinal_project", "has_repeating_instruments_or_events")
            ) or bool({str(row.get("unique_event_name") or row.get("event_name") or "").strip() for row in repeating_forms_events if row})
            record_id_field_name = _extract_record_id_field_name(metadata_rows)

            _set_job_runtime_state(
                job,
                mode=processing_mode,
                phase="processing_rows",
                latest_message=(
                    f"Retrying remaining rows against REDCap {_processing_mode_runtime_phrase(processing_mode)}."
                    if retry_scope == "remaining_rows"
                    else f"Retrying failed rows against REDCap {_processing_mode_runtime_phrase(processing_mode)}."
                    if retry_row_ids
                    else f"Processing request rows against REDCap {_processing_mode_runtime_phrase(processing_mode)}."
                ),
                rate_limit_wait_until=None,
                rate_limit_per_minute=resolved_rate_limit,
                retry_scope=retry_scope,
                active_row_count=len(rows),
                retry_failed_count=retry_failed_count,
                retry_unprocessed_count=retry_unprocessed_count,
            )
            db.commit()

            if cancel_if_requested("Job was cancelled during background processing."):
                return

            for row in rows:
                if cancel_if_requested("Job was cancelled during background processing."):
                    return
                started = perf_counter()
                row_result = row.row_result
                if row_result is None:
                    row_result = RowResult(job_row_id=row.id)
                    db.add(row_result)

                row_result.status = RowResultStatus.PENDING
                row_result.outcome_code = None
                row_result.message = None
                row_result.redcap_http_status = None
                row_result.details_json = None
                row_result.query_blocking_count = None
                row_result.processed_at = None

                mapping = mappings.get(row.target_instrument)
                try:
                    if mapping is None:
                        raise ValueError(f"No mapping is available for {row.target_instrument}.")

                    repeat_context_instance = (
                        row.repeat_instance if _row_uses_repeat_context(row, repeating_forms_events=repeating_forms_events) else None
                    )
                    locking_instance = row.repeat_instance if row.repeat_instance is not None else repeat_context_instance
                    status_response = fetch_locking_status(
                        job.redcap_api_url,
                        cleaned_api_key,
                        record_id=row.record_id,
                        instrument_name=row.target_instrument,
                        event_name=row.event_name,
                        arm_name=row.arm_name,
                        repeat_instance=locking_instance,
                    )
                    lock_state = str(status_response.get("lock_status") or "").strip()
                    locked_by = str(status_response.get("username") or "").strip() or None
                    locked_at = str(status_response.get("timestamp") or "").strip() or None
                    processing_steps = [f"Checked locking status. REDCap returned '{lock_state or '<empty>'}'."]
                    status_debug_details = {
                        "initial_lock_state": lock_state,
                        "locked_by": locked_by,
                        "locked_at": locked_at,
                        "locking_instance_sent": locking_instance,
                        "repeat_context_instance": repeat_context_instance,
                        "status_raw": status_response.get("raw"),
                        "status_selected_row": status_response.get("selected_row"),
                        "processing_steps": processing_steps,
                    }
                    ambiguous_status = _status_state_is_ambiguous(lock_state=lock_state, locked_by=locked_by, locked_at=locked_at)
                    shadow_field_payload = _build_shadow_field_payload(
                        record_id_field_name=record_id_field_name,
                        row=row,
                        mapping=mapping,
                        is_longitudinal=is_longitudinal,
                        repeating_forms_events=repeating_forms_events,
                    )
                    shadow_import_date_format = _extract_shadow_import_date_format(mapping)

                    if row.action == RowAction.LOCK and lock_state == "1":
                        processing_steps.append("Skipped because the form was already locked.")
                        row_result.status = RowResultStatus.IGNORED
                        row_result.outcome_code = "already_locked"
                        row_result.message = "Skipped because the form was already locked."
                        row_result.redcap_http_status = int(status_response["http_status"])
                        row_result.details_json = {
                            **status_debug_details,
                            "action_called": False,
                            "shadow_fields_phase": "none",
                        }
                        job.ignored_rows += 1
                    elif row.action == RowAction.LOCK and lock_state == "":
                        processing_steps.append("Blocked because REDCap reported no data for the target form.")
                        row_result.status = RowResultStatus.BLOCKED
                        row_result.outcome_code = "no_form_data"
                        row_result.message = "No form data exists yet, so REDCap cannot lock this form."
                        row_result.redcap_http_status = int(status_response["http_status"])
                        row_result.details_json = {
                            **status_debug_details,
                            "action_called": False,
                            "shadow_fields_phase": "none",
                        }
                        job.blocked_rows += 1
                        if not job.last_error_summary:
                            job.last_error_summary = (
                                "REDCap could not lock at least one requested form because no form data exists yet. "
                                "Data-level locks only work after the form has data."
                            )
                    elif row.action == RowAction.UNLOCK and lock_state == "0":
                        processing_steps.append("Detected that the form was already unlocked.")
                        row_result.status = RowResultStatus.IGNORED
                        row_result.outcome_code = "already_unlocked"
                        row_result.message = "Form was already unlocked."
                        row_result.redcap_http_status = int(status_response["http_status"])
                        row_result.details_json = {
                            **status_debug_details,
                            "action_called": False,
                            "shadow_fields_phase": "after_unlock" if shadow_field_payload is not None else "none",
                            "shadow_fields_payload": shadow_field_payload,
                        }
                        if shadow_field_payload is not None:
                            processing_steps.append("Cleared mapped shadow fields after detecting the form was already unlocked.")
                            import_record_update(
                                job.redcap_api_url,
                                cleaned_api_key,
                                record=shadow_field_payload,
                                date_format=shadow_import_date_format,
                            )
                            row.input_payload_json = shadow_field_payload
                            row_result.status = RowResultStatus.SUCCESS
                            row_result.outcome_code = "unlocked"
                            row_result.message = "Form was already unlocked. Shadow lock fields were cleared."
                            job.unlocked_rows += 1
                        else:
                            job.ignored_rows += 1
                    elif row.action == RowAction.UNLOCK and lock_state == "" and not ambiguous_status:
                        processing_steps.append("Skipped unlock because REDCap reported that no form data exists.")
                        row_result.status = RowResultStatus.IGNORED
                        row_result.outcome_code = "already_unlocked"
                        row_result.message = "Form has no existing data, so there was nothing to unlock."
                        row_result.redcap_http_status = int(status_response["http_status"])
                        row_result.details_json = {
                            **status_debug_details,
                            "action_called": False,
                            "shadow_fields_phase": "none",
                        }
                        job.ignored_rows += 1
                    else:
                        if row.action == RowAction.LOCK:
                            form_complete_field_name, form_complete_value, form_complete_row = _fetch_form_complete_snapshot(
                                api_url=job.redcap_api_url,
                                api_key=cleaned_api_key,
                                row=row,
                                mapping=mapping,
                                record_id_field_name=record_id_field_name,
                                repeating_forms_events=repeating_forms_events,
                            )
                            selected_repeat_instrument = (
                                str((form_complete_row or {}).get("redcap_repeat_instrument") or "").strip() or None
                            )
                            selected_repeat_instance = (
                                str((form_complete_row or {}).get("redcap_repeat_instance") or "").strip() or None
                            )
                            processing_steps.append(
                                f"Read form complete field {form_complete_field_name}: "
                                f"'{form_complete_value if form_complete_value is not None else '<empty>'}'"
                                + (
                                    f" (instrument={selected_repeat_instrument or row.target_instrument}, "
                                    f"instance={selected_repeat_instance or row.repeat_instance})."
                                    if selected_repeat_instance or selected_repeat_instrument
                                    else "."
                                )
                            )
                            if not _is_form_marked_complete(form_complete_value):
                                processing_steps.append("Skipped because the form is not marked complete.")
                                row_result.status = RowResultStatus.IGNORED
                                row_result.outcome_code = "form_not_complete"
                                row_result.message = "Skipped because the form is not marked complete."
                                row_result.redcap_http_status = int(status_response["http_status"])
                                row_result.details_json = {
                                    **status_debug_details,
                                    "form_complete_field_name": form_complete_field_name,
                                    "form_complete_value": form_complete_value,
                                    "form_complete_row": form_complete_row,
                                    "selected_repeat_instrument": selected_repeat_instrument,
                                    "selected_repeat_instance": selected_repeat_instance,
                                    "action_called": False,
                                    "shadow_fields_phase": "none",
                                }
                                job.ignored_rows += 1
                                continue

                            unresolved_query_count = query_match_counts.get(row.row_number, 0)
                            if unresolved_query_count > 0 or row.has_unresolved_queries:
                                query_count_value = unresolved_query_count or 1
                                query_count_label = (
                                    "1 unresolved query" if query_count_value == 1 else f"{query_count_value} unresolved queries"
                                )
                                query_count_verb = "exists" if query_count_value == 1 else "exist"
                                processing_steps.append(
                                    f"Blocked because {query_count_label} {query_count_verb} for this form."
                                )
                                row_result.status = RowResultStatus.BLOCKED
                                row_result.outcome_code = "unresolved_queries"
                                row_result.message = f"Lock blocked because {query_count_label} {query_count_verb} for this form."
                                row_result.redcap_http_status = int(status_response["http_status"])
                                row_result.query_blocking_count = unresolved_query_count or 1
                                row_result.details_json = {
                                    **status_debug_details,
                                    "form_complete_field_name": form_complete_field_name,
                                    "form_complete_value": form_complete_value,
                                    "query_blocking_count": unresolved_query_count or 1,
                                    "action_called": False,
                                    "shadow_fields_phase": "none",
                                }
                                job.blocked_rows += 1
                                if not job.last_error_summary:
                                    job.last_error_summary = (
                                        "REDCap could not lock at least one requested form because unresolved queries were found."
                                    )
                                continue

                        if row.action == RowAction.LOCK and shadow_field_payload is not None:
                            processing_steps.append("Wrote mapped shadow fields before locking.")
                            import_record_update(
                                job.redcap_api_url,
                                cleaned_api_key,
                                record=shadow_field_payload,
                                date_format=shadow_import_date_format,
                            )
                            row.input_payload_json = shadow_field_payload
                        elif row.action == RowAction.LOCK:
                            processing_steps.append("No mapped shadow fields needed before locking.")

                        processing_steps.append(f"Called REDCap {row.action.value} action.")
                        action_response = apply_locking_action(
                            job.redcap_api_url,
                            cleaned_api_key,
                            action=row.action.value,
                            record_id=row.record_id,
                            instrument_name=row.target_instrument,
                            event_name=row.event_name,
                            arm_name=row.arm_name,
                            repeat_instance=locking_instance,
                        )
                        if row.action == RowAction.UNLOCK and shadow_field_payload is not None:
                            processing_steps.append("Cleared mapped shadow fields after unlocking.")
                            import_record_update(
                                job.redcap_api_url,
                                cleaned_api_key,
                                record=shadow_field_payload,
                                date_format=shadow_import_date_format,
                            )
                            row.input_payload_json = shadow_field_payload

                        verification_response = fetch_locking_status(
                            job.redcap_api_url,
                            cleaned_api_key,
                            record_id=row.record_id,
                            instrument_name=row.target_instrument,
                            event_name=row.event_name,
                            arm_name=row.arm_name,
                            repeat_instance=locking_instance,
                        )
                        final_lock_state = str(verification_response.get("lock_status") or "").strip()
                        final_locked_by = str(verification_response.get("username") or "").strip() or None
                        final_locked_at = str(verification_response.get("timestamp") or "").strip() or None
                        processing_steps.append(
                            f"Verified final locking state. REDCap returned '{final_lock_state or '<empty>'}'."
                        )

                        expected_reached = final_lock_state == "1" if row.action == RowAction.LOCK else final_lock_state == "0"
                        if not expected_reached:
                            raise RedcapServiceError(
                                "REDCap did not report the expected lock state after the action completed."
                            )

                        row_result.status = RowResultStatus.SUCCESS
                        row_result.outcome_code = "locked" if row.action == RowAction.LOCK else "unlocked"
                        row_result.message = (
                            "Form locked successfully." if row.action == RowAction.LOCK else "Form unlocked successfully."
                        )
                        row_result.redcap_http_status = int(action_response["http_status"])
                        row_result.details_json = {
                            "status_before": lock_state,
                            "status_after": final_lock_state,
                            "locked_by": final_locked_by,
                            "locked_at": final_locked_at,
                            "locking_instance_sent": locking_instance,
                            "repeat_context_instance": repeat_context_instance,
                            "status_raw": status_response.get("raw"),
                            "status_selected_row": status_response.get("selected_row"),
                            "form_complete_field_name": form_complete_field_name if row.action == RowAction.LOCK else None,
                            "form_complete_value": form_complete_value if row.action == RowAction.LOCK else None,
                            "shadow_fields_phase": "before_lock" if row.action == RowAction.LOCK else "after_unlock",
                            "shadow_fields_payload": shadow_field_payload,
                            "action_called": True,
                            "action_raw": action_response.get("raw"),
                            "action_selected_row": action_response.get("selected_row"),
                            "verification_raw": verification_response.get("raw"),
                            "verification_selected_row": verification_response.get("selected_row"),
                            "processing_steps": processing_steps,
                        }
                        if row.action == RowAction.LOCK:
                            job.locked_rows += 1
                        else:
                            job.unlocked_rows += 1

                    _record_job_event(
                        db,
                        job=job,
                        job_row_id=row.id,
                        event_type="job.row_processed",
                        message=row_result.message,
                        payload_json={
                            "row_number": row.row_number,
                            "record_id": row.record_id,
                            "instrument": row.target_instrument,
                            "outcome_code": row_result.outcome_code,
                        },
                    )
                except (RedcapServiceError, ValueError) as exc:
                    row_result.status = RowResultStatus.FAILED
                    row_result.outcome_code = "processing_error"
                    row_result.message = str(exc)
                    row_result.details_json = {"error": str(exc)}
                    row_result.redcap_http_status = None
                    job.failed_rows += 1
                    if not job.last_error_summary:
                        job.last_error_summary = str(exc)
                    _record_job_event(
                        db,
                        job=job,
                        job_row_id=row.id,
                        event_type="job.row_failed",
                        level=EventLevel.ERROR,
                        message=str(exc),
                        payload_json={
                            "row_number": row.row_number,
                            "record_id": row.record_id,
                            "instrument": row.target_instrument,
                        },
                    )
                except Exception as exc:
                    row_result.status = RowResultStatus.FAILED
                    row_result.outcome_code = "unexpected_processing_error"
                    row_result.message = f"Unexpected error while processing the row: {exc}"
                    row_result.details_json = {
                        "exception_type": exc.__class__.__name__,
                    }
                    row_result.redcap_http_status = None
                    job.failed_rows += 1
                    if not job.last_error_summary:
                        job.last_error_summary = row_result.message
                    _record_job_event(
                        db,
                        job=job,
                        job_row_id=row.id,
                        event_type="job.row_failed",
                        level=EventLevel.ERROR,
                        message=row_result.message,
                        payload_json={
                            "row_number": row.row_number,
                            "record_id": row.record_id,
                            "instrument": row.target_instrument,
                            "exception_type": exc.__class__.__name__,
                        },
                    )
                finally:
                    row_result.duration_ms = max(1, int((perf_counter() - started) * 1000))
                    row_result.processed_at = utc_now()
                    job.processed_rows += 1
                    current_status = db.scalar(select(Job.status).where(Job.id == job.id)) or job.status
                    is_cancel_requested = current_status == JobStatus.CANCEL_REQUESTED
                    job.status = JobStatus.CANCEL_REQUESTED if is_cancel_requested else JobStatus.RUNNING
                    _set_job_runtime_state(
                        job,
                        mode=processing_mode,
                        phase="cancelling" if is_cancel_requested else "processing_rows",
                        latest_message=(
                            "Cancellation requested. Waiting for the current step to finish before stopping this job."
                            if is_cancel_requested
                            else f"Retried {job.processed_rows} of {len(rows)} remaining rows {_processing_mode_runtime_phrase(processing_mode)}."
                            if retry_scope == "remaining_rows"
                            else f"Retried {job.processed_rows} of {len(rows)} failed rows {_processing_mode_runtime_phrase(processing_mode)}."
                            if retry_row_ids
                            else f"Processed {job.processed_rows} of {len(rows)} rows {_processing_mode_runtime_phrase(processing_mode)}."
                        ),
                        rate_limit_wait_until=None,
                        rate_limit_per_minute=resolved_rate_limit,
                        retry_scope=retry_scope,
                        active_row_count=len(rows),
                        retry_failed_count=retry_failed_count,
                        retry_unprocessed_count=retry_unprocessed_count,
                    )
                    db.commit()

        final_previous_status = job.status
        _recalculate_job_rollups(db, job=job)
        job.completed_at = utc_now()
        if job.failed_rows == job.total_rows and job.total_rows > 0:
            job.status = JobStatus.FAILED
        elif job.failed_rows or job.blocked_rows:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        else:
            job.status = JobStatus.COMPLETED

        _set_job_runtime_state(
            job,
            mode=processing_mode,
            phase="completed",
            latest_message=f"{_processing_mode_title(processing_mode)} processing finished.",
            rate_limit_wait_until=None,
            rate_limit_per_minute=resolved_rate_limit,
            retry_scope=retry_scope,
            active_row_count=job.total_rows,
            retry_failed_count=retry_failed_count,
            retry_unprocessed_count=retry_unprocessed_count,
        )
        _record_job_event(
            db,
            job=job,
            event_type="job.processing_completed",
            message=f"{_processing_mode_title(processing_mode)} job execution finished.",
            status_from=final_previous_status,
            status_to=job.status,
            payload_json={
                "processed_rows": job.processed_rows,
                "locked_rows": job.locked_rows,
                "unlocked_rows": job.unlocked_rows,
                "ignored_rows": job.ignored_rows,
                "blocked_rows": job.blocked_rows,
                "failed_rows": job.failed_rows,
            },
        )
        rows = _load_job_rows_for_report(db, job_id=job.id)
        _upsert_job_report(db, job=job, rows=rows)
        record_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="jobs.process",
            object_type="job",
            object_id=str(job.id),
            metadata={
                "final_status": job.status.value,
                "processed_rows": job.processed_rows,
                "failed_rows": job.failed_rows,
                "processing_mode": processing_mode,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            previous_status = job.status
            cancelled_count = _mark_unprocessed_rows_as_cancelled(db, job_id=job.id, reason=str(exc))
            _recalculate_job_rollups(db, job=job)
            job.status = JobStatus.FAILED
            job.completed_at = utc_now()
            job.last_error_summary = str(exc)
            _set_job_runtime_state(
                job,
                mode=processing_mode,
                phase="failed",
                latest_message=str(exc),
                rate_limit_wait_until=None,
            )
            _record_job_event(
                db,
                job=job,
                event_type="job.processing_failed",
                level=EventLevel.ERROR,
                message=(
                    f"{exc} {_format_row_count(cancelled_count).capitalize()} "
                    f"{'was' if cancelled_count == 1 else 'were'} left unprocessed."
                    if cancelled_count
                    else str(exc)
                ),
                status_from=previous_status,
                status_to=JobStatus.FAILED,
            )
            rows = _load_job_rows_for_report(db, job_id=job.id)
            _upsert_job_report(db, job=job, rows=rows)
            record_audit_event(
                db,
                actor_user_id=actor_user_id,
                action="jobs.process_failed",
                object_type="job",
                object_id=str(job.id),
                metadata={
                    "reason": str(exc),
                    "processing_mode": processing_mode,
                    "unprocessed_rows": cancelled_count,
                    "processed_rows": job.processed_rows,
                },
            )
            db.commit()
    finally:
        db.close()


@router.post("/jobs/{job_id}/process")
def process_job_from_ui(
    job_id: UUID,
    request: Request,
    redcap_api_key: str = Form(default=""),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    job = db.get(Job, job_id)
    if job is None or not _can_access_job(session.user, job):
        return RedirectResponse("/jobs", status_code=303)

    if job.status not in {JobStatus.READY, JobStatus.CANCELLED, JobStatus.FAILED, JobStatus.COMPLETED_WITH_ERRORS}:
        return _build_jobs_redirect(error="Only ready or retryable jobs can be processed.", process_job_id=job.id)

    cleaned_api_key = ""
    provided_api_key = bool(redcap_api_key.strip())
    if provided_api_key:
        try:
            cleaned_api_key = _validate_redcap_api_key(redcap_api_key)
        except ValueError as exc:
            return _build_jobs_redirect(
                error=str(exc),
                open_modal=PROCESS_MODAL_ID,
                process_job_id=job.id,
            )
    elif job.redcap_host_id:
        cached_api_key = get_cached_redcap_api_key(
            db,
            user_session_id=session.id,
            redcap_host_id=job.redcap_host_id,
        )
        if cached_api_key:
            cleaned_api_key = cached_api_key

    if not cleaned_api_key:
        return _build_jobs_redirect(
            error="Enter the REDCap API key to process this job.",
            open_modal=PROCESS_MODAL_ID,
            process_job_id=job.id,
        )

    retry_rows: list[JobRow] = []
    retry_row_ids: list[UUID] = []
    retry_summary = {
        "count": 0,
        "failed_count": 0,
        "unprocessed_count": 0,
        "retry_scope": "all_rows",
        "action_label": "Process",
        "selection_copy": _format_row_count(job.total_rows or 0),
        "progress_summary": "rows",
    }
    is_retry_attempt = job.status in {JobStatus.CANCELLED, JobStatus.FAILED, JobStatus.COMPLETED_WITH_ERRORS}
    if is_retry_attempt:
        retry_rows = _get_retryable_rows(db, job_id=job.id)
        retry_row_ids = [row.id for row in retry_rows]
        retry_summary = _summarize_retry_candidates(retry_rows)
        if not retry_row_ids:
            return _build_jobs_redirect(error="This job has no failed or unprocessed rows left to retry.")
    active_row_count = len(retry_row_ids) if retry_row_ids else int(job.total_rows or 0)
    launch_mode = (
        _resolve_retry_processing_mode(job=job, row_count=active_row_count)
        if is_retry_attempt
        else _resolve_processing_mode(row_count=active_row_count)
    )
    if launch_mode == "background" and not _has_shared_redcap_api_key_cache_secret():
        return _build_jobs_redirect(
            error=(
                "Background processing requires REDCAP_API_KEY_CACHE_SECRET to be configured with the same value "
                "for the API and worker services. Update the environment and try again."
            ),
            process_job_id=job.id,
        )

    active_project_job = _find_active_project_job(db, job=job)
    if active_project_job is not None:
        active_job_label = active_project_job.request_file_name or "another request"
        return _build_jobs_redirect(
            error=(
                f"{active_job_label} is already active for this REDCap project. "
                "Wait for it to finish before starting another job against the same project."
            )
        )

    resolved_rate_limit = set_redcap_rate_limit_for_scope(
        job.redcap_api_url,
        _resolve_job_rate_limit(job),
        job.redcap_project_id,
    )

    if job.redcap_host_id:
        store_redcap_api_key(
            db,
            user_session_id=session.id,
            redcap_host_id=job.redcap_host_id,
            api_key=cleaned_api_key,
        )

    if launch_mode == "live":
        db.commit()
        run_job_processing(job.id, session.user.id, cleaned_api_key, retry_row_ids, processing_mode="live")
        db.expire_all()
        refreshed_job = db.get(Job, job.id)
        job_label = (refreshed_job.request_file_name if refreshed_job is not None else None) or (job.request_file_name or "job")
        if refreshed_job is not None and refreshed_job.status == JobStatus.CANCELLED:
            return _build_jobs_redirect(
                error=f"Live processing for {job_label} was cancelled before it could finish. Try again from the Jobs page.",
                process_job_id=job.id,
            )
        if refreshed_job is not None and refreshed_job.status == JobStatus.FAILED:
            return _build_jobs_redirect(
                error=f"Live processing failed for {job_label}. Review the Jobs page for details.",
                process_job_id=job.id,
            )
        live_message = (
            f"Finished live retry for {retry_summary['selection_copy']} in {job_label}. "
            if retry_row_ids
            else f"Finished live processing for {job_label}. "
        )
        if refreshed_job is not None and refreshed_job.status == JobStatus.COMPLETED_WITH_ERRORS:
            live_message += "Some rows were blocked or failed."
            if refreshed_job.last_error_summary:
                live_message += f" {refreshed_job.last_error_summary}"
            live_message += " Review the Jobs page for details."
        else:
            live_message += "Results are now available on the Jobs page."
        return _build_jobs_redirect(success=live_message)

    previous_status = job.status
    previous_started_at = job.started_at
    previous_completed_at = job.completed_at
    previous_cancellation_requested_at = job.cancellation_requested_at
    previous_last_error_summary = job.last_error_summary
    previous_processed_rows = job.processed_rows
    previous_locked_rows = job.locked_rows
    previous_unlocked_rows = job.unlocked_rows
    previous_ignored_rows = job.ignored_rows
    previous_blocked_rows = job.blocked_rows
    previous_failed_rows = job.failed_rows
    previous_options_json = job.options_json
    queued_task_id = str(uuid4())
    job.status = JobStatus.QUEUED
    job.cancellation_requested_at = None
    job.started_at = None
    job.completed_at = None
    job.processed_rows = 0
    job.locked_rows = 0
    job.unlocked_rows = 0
    job.ignored_rows = 0
    job.blocked_rows = 0
    job.failed_rows = 0
    job.last_error_summary = None
    _set_job_runtime_state(
        job,
        mode="background",
        phase="queued",
        latest_message=(
            f"Queued to retry {retry_summary['selection_copy']} in the background for this REDCap project."
            if retry_row_ids
            else "Queued to start in the background for this REDCap project."
        ),
        rate_limit_wait_until=None,
        rate_limit_per_minute=resolved_rate_limit,
        retry_scope=str(retry_summary["retry_scope"]) if retry_row_ids else "all_rows",
        active_row_count=active_row_count,
        retry_failed_count=int(retry_summary["failed_count"]) if retry_row_ids else 0,
        retry_unprocessed_count=int(retry_summary["unprocessed_count"]) if retry_row_ids else 0,
        worker_backend="desktop",
        worker_task_id=queued_task_id,
    )
    _record_job_event(
        db,
        job=job,
        event_type="job.processing_queued",
        message=(
            f"Job was queued from the Jobs page to retry {retry_summary['selection_copy']} in the background."
            if retry_row_ids
            else "Job was queued from the Jobs page for background processing."
        ),
        status_from=previous_status,
    )
    db.commit()
    try:
        enqueue_job_processing(
            job_id=job.id,
            actor_user_id=session.user.id,
            user_session_id=session.id,
            retry_row_ids=retry_row_ids,
            task_id=queued_task_id,
        )
    except Exception as exc:
        db.rollback()
        queued_job = db.get(Job, job.id)
        if queued_job is not None:
            dispatch_failed_from = queued_job.status
            queued_job.status = previous_status
            queued_job.cancellation_requested_at = previous_cancellation_requested_at
            queued_job.started_at = previous_started_at
            queued_job.completed_at = previous_completed_at
            queued_job.last_error_summary = previous_last_error_summary
            queued_job.processed_rows = previous_processed_rows
            queued_job.locked_rows = previous_locked_rows
            queued_job.unlocked_rows = previous_unlocked_rows
            queued_job.ignored_rows = previous_ignored_rows
            queued_job.blocked_rows = previous_blocked_rows
            queued_job.failed_rows = previous_failed_rows
            queued_job.options_json = previous_options_json
            _record_job_event(
                db,
                job=queued_job,
                event_type="job.processing_queue_failed",
                level=EventLevel.ERROR,
                message=f"Could not queue the background worker task: {exc}",
                status_from=dispatch_failed_from,
                status_to=previous_status,
            )
            db.commit()
        return _build_jobs_redirect(error="Could not queue this job for background processing. Please try again.")
    return _build_jobs_redirect(
        success=(
            (
                f"Started background retry for {retry_summary['selection_copy']} in {job.request_file_name or 'job'}. "
            )
            if retry_row_ids
            else f"Started background processing for {job.request_file_name or 'job'}. "
        )
        + "Progress will appear on the Jobs page and rate-limit waits will be shown there."
    )


@router.post("/jobs/{job_id}/cancel")
def cancel_job_from_ui(
    job_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    job = db.get(Job, job_id)
    if job is None or not _can_access_job(session.user, job):
        return RedirectResponse("/jobs", status_code=303)

    if job.status == JobStatus.CANCEL_REQUESTED:
        return _build_jobs_redirect(error="Cancellation has already been requested for this job.")
    if job.status not in USER_CANCELLABLE_JOB_STATUSES:
        return _build_jobs_redirect(error="Only jobs that are still awaiting action or actively processing can be cancelled.")

    previous_status = job.status
    job_label = job.request_file_name or "job"
    if job.status in PRESTART_CANCELLABLE_JOB_STATUSES:
        worker_task_id = _get_job_worker_task_id(job)
        if worker_task_id:
            try:
                revoke_job_processing(worker_task_id)
            except Exception:
                pass
        cancellation_message = "Job was cancelled before processing started."
        _finalize_job_cancellation(
            db,
            job=job,
            previous_status=previous_status,
            cancellation_message=cancellation_message,
            row_message="Row was not processed because the job was cancelled before execution started.",
            event_message="Cancelled before processing started. Remaining rows were marked as not processed.",
            actor_user_id=session.user.id,
            processing_mode="background",
            request=request,
        )
        if previous_status == JobStatus.QUEUED:
            job.started_at = None
        db.commit()
        return _build_jobs_redirect(success=f"Cancelled job for {job_label}.")

    job.status = JobStatus.CANCEL_REQUESTED
    job.cancellation_requested_at = utc_now()
    _set_job_runtime_state(
        job,
        phase="cancelling",
        latest_message="Cancellation requested. The current step will finish before this job stops.",
        rate_limit_wait_until=None,
    )
    _record_job_event(
        db,
        job=job,
        event_type="job.cancel_requested",
        message="Cancellation was requested from the Jobs page.",
        status_from=previous_status,
        status_to=JobStatus.CANCEL_REQUESTED,
        payload_json={"worker_task_id": _get_job_worker_task_id(job)},
    )
    record_audit_event(
        db,
        actor_user_id=session.user.id,
        action="jobs.cancel_requested",
        object_type="job",
        object_id=str(job.id),
        request=request,
        metadata={"previous_status": previous_status.value},
    )
    db.commit()
    return _build_jobs_redirect(
        success=f"Cancellation requested for {job_label}. The current step will finish before the job stops."
    )


@router.get("/mappings", response_class=HTMLResponse)
def mappings_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    requested_job_id = request.query_params.get("job_id")
    try:
        parsed_job_id = UUID(requested_job_id) if requested_job_id else None
    except ValueError:
        parsed_job_id = None
    job = _get_mapping_job(db, current_user=session.user, job_id=parsed_job_id)
    if job is not None and _is_mapping_refresh_prompt_pending(job):
        return _build_jobs_redirect(
            error="Choose whether to refresh the saved project mappings from the Jobs page before opening mapping review."
        )

    mapping_rows: list[dict[str, object]] = []
    if job is not None and job.redcap_project_id:
        validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
        alias_bank = get_mapping_label_aliases(db)
        refreshed_summary = refresh_mapping_review_bundle(validation_summary, alias_bank=alias_bank)
        if refreshed_summary.get("instrument_reviews"):
            job.validation_summary_json = refreshed_summary
            validation_summary = refreshed_summary
        project_mappings = db.scalars(
            select(InstrumentMapping).where(
                InstrumentMapping.redcap_host_id == job.redcap_host_id,
                InstrumentMapping.redcap_project_id == job.redcap_project_id,
                InstrumentMapping.instrument_name.in_(validation_summary.get("instrument_sequence", [])),
            )
        ).all()
        mapping_rows = _build_mapping_rows(job, list(project_mappings), alias_bank=alias_bank)

    return templates.TemplateResponse(
        request=request,
        name="mappings.html",
        context={
            "page_title": "Mappings",
            "user": session.user,
            "session": session,
            "job": job,
            "mapping_rows": mapping_rows,
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
            "mapping_none_option": MAPPING_NONE_OPTION,
            "mapping_auto_option": MAPPING_AUTO_OPTION,
            "date_format_options": sorted(DATE_FORMAT_OPTIONS),
            **_build_sidebar_context(active_path="/mappings", current_user=session.user),
        },
    )


@router.post("/mappings/{job_id}/refresh")
def refresh_mappings_from_ui(
    job_id: UUID,
    request: Request,
    return_to: str = Form(default="mappings"),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    job = db.get(Job, job_id)
    if job is None or not _can_access_job(session.user, job):
        return RedirectResponse("/jobs", status_code=303)

    if job.status != JobStatus.AWAITING_MAPPING_CONFIRMATION:
        return _build_jobs_redirect(error="Only jobs that are awaiting mapping confirmation can be remapped.")

    try:
        review_instrument_count = _refresh_job_mapping_review(db, job=job, user_session_id=session.id)
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="mappings.refresh",
            object_type="job",
            object_id=str(job.id),
            request=request,
            metadata={
                "review_instrument_count": review_instrument_count,
                "job_status_after_refresh": job.status.value,
            },
        )
        db.commit()
    except (RedcapServiceError, ValueError) as exc:
        db.rollback()
        if str(return_to).strip().lower() == "mappings":
            return _build_mappings_redirect(job_id, error=str(exc))
        return _build_jobs_redirect(error=str(exc))

    if review_instrument_count == 0:
        return _build_jobs_redirect(success="Mappings refreshed from REDCap. This job no longer needs manual review and is ready to process.")

    success_message = (
        f"Mappings refreshed from REDCap for {review_instrument_count} form"
        f"{'s' if review_instrument_count != 1 else ''}. Review the updated options below."
    )
    if str(return_to).strip().lower() == "mappings":
        return _build_mappings_redirect(job_id, success=success_message)
    return _build_jobs_redirect(success=success_message)


@router.post("/jobs/{job_id}/use-existing-mappings")
def continue_with_existing_mappings_from_ui(
    job_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    job = db.get(Job, job_id)
    if job is None or not _can_access_job(session.user, job):
        return RedirectResponse("/jobs", status_code=303)

    try:
        next_status = _continue_job_with_existing_mappings(job)
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="mappings.use_existing",
            object_type="job",
            object_id=str(job.id),
            request=request,
            metadata={"job_status_after_continue": next_status.value},
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _build_jobs_redirect(error=str(exc))

    if next_status == JobStatus.READY:
        return _build_jobs_redirect(success="Continuing with the saved project mappings. This job is ready to process.")
    return _build_jobs_redirect(
        success="Continuing with the saved project mappings. Review the remaining mapping options before execution."
    )


@router.post("/mappings/{job_id}/confirm")
async def confirm_mappings_from_ui(
    job_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    job = db.get(Job, job_id)
    if job is None or not _can_access_job(session.user, job):
        return RedirectResponse("/jobs", status_code=303)

    if not isinstance(job.validation_summary_json, dict) or not job.redcap_project_id:
        return _build_mappings_redirect(job_id, error="This job does not have a stored mapping review bundle.")

    instrument_sequence = job.validation_summary_json.get("instrument_sequence", [])
    instrument_reviews = job.validation_summary_json.get("instrument_reviews", {})
    mappings = {
        mapping.instrument_name: mapping
        for mapping in db.scalars(
            select(InstrumentMapping).where(
                InstrumentMapping.redcap_host_id == job.redcap_host_id,
                InstrumentMapping.redcap_project_id == job.redcap_project_id,
                InstrumentMapping.instrument_name.in_(instrument_sequence),
            )
        ).all()
    }
    alias_bank = get_mapping_label_aliases(db)
    submitted_form = await request.form()
    status_labels_to_save: list[str] = []
    date_labels_to_save: list[str] = []

    try:
        for instrument_name in instrument_sequence:
            review = instrument_reviews.get(instrument_name)
            mapping = mappings.get(instrument_name)
            if not isinstance(review, dict) or mapping is None:
                raise ValueError("One or more mapping rows could not be loaded for confirmation.")
            if not bool(review.get("requires_confirmation")):
                continue

            field_lookup = {field["field_name"]: field for field in review.get("field_catalog", [])}
            field_prefix = f"mapping_{mapping.id}"

            status_field_choice = str(submitted_form.get(f"{field_prefix}_status_field_name", MAPPING_NONE_OPTION))
            status_manual_field_name = _normalize_optional_form_value(
                str(submitted_form.get(f"{field_prefix}_status_manual_field_name", "")),
                label=f"manual status field for {instrument_name}",
                max_length=255,
            )
            status_label_variant = _normalize_optional_form_value(
                str(submitted_form.get(f"{field_prefix}_status_label_variant", "")),
                label=f"status label variant for {instrument_name}",
                max_length=255,
            )
            status_manual_lock_value = _normalize_optional_form_value(
                str(submitted_form.get(f"{field_prefix}_status_lock_value", "")),
                label=f"lock value for {instrument_name}",
                max_length=100,
            )

            selected_status_field_name = status_manual_field_name or (
                None if status_field_choice == MAPPING_NONE_OPTION else status_field_choice
            )
            status_configuration = None
            if selected_status_field_name:
                field_definition = field_lookup.get(selected_status_field_name)
                if field_definition is None:
                    raise ValueError(f"Status field {selected_status_field_name} was not found on {instrument_name}.")
                status_configuration = resolve_status_field_configuration(
                    field_definition,
                    alias_bank,
                    manual_lock_value=status_manual_lock_value,
                )

            date_field_choice = str(submitted_form.get(f"{field_prefix}_date_field_name", MAPPING_NONE_OPTION))
            date_manual_field_name = _normalize_optional_form_value(
                str(submitted_form.get(f"{field_prefix}_date_manual_field_name", "")),
                label=f"manual lock date field for {instrument_name}",
                max_length=255,
            )
            date_label_variant = _normalize_optional_form_value(
                str(submitted_form.get(f"{field_prefix}_date_label_variant", "")),
                label=f"date label variant for {instrument_name}",
                max_length=255,
            )
            date_format_override = str(submitted_form.get(f"{field_prefix}_date_format", MAPPING_AUTO_OPTION))
            selected_date_field_name = date_manual_field_name or (
                None if date_field_choice == MAPPING_NONE_OPTION else date_field_choice
            )
            date_configuration = None
            if selected_date_field_name:
                field_definition = field_lookup.get(selected_date_field_name)
                if field_definition is None:
                    raise ValueError(f"Lock date field {selected_date_field_name} was not found on {instrument_name}.")
                date_configuration = resolve_date_field_configuration(
                    field_definition,
                    override_format=None if date_format_override == MAPPING_AUTO_OPTION else date_format_override,
                )

            mapping.form_complete_field_name = _expected_form_complete_field_name(instrument_name)
            mapping.crf_status_field_name = selected_status_field_name
            mapping.lock_date_field_name = selected_date_field_name
            mapping.status = MappingStatus.CONFIRMED
            mapping.confidence = MappingConfidence.HIGH
            mapping.confirmed_by_user_id = session.user.id
            mapping.last_validated_at = utc_now()
            mapping.drift_detected_at = None
            mapping.coded_values_json = {
                "instrument_label": review.get("instrument_label"),
                "status_field": status_configuration or {"mode": "none"},
                "date_field": date_configuration or {"mode": "none"},
            }

            if status_label_variant:
                status_labels_to_save.append(status_label_variant)
            if date_label_variant:
                date_labels_to_save.append(date_label_variant)

        save_mapping_label_aliases(
            db,
            actor_user_id=session.user.id,
            status_labels=status_labels_to_save,
            date_labels=date_labels_to_save,
        )
        job.status = JobStatus.READY
        job.last_error_summary = None
        record_audit_event(
            db,
            actor_user_id=session.user.id,
            action="mappings.confirm",
            object_type="job",
            object_id=str(job.id),
            request=request,
            metadata={"instrument_count": len(instrument_sequence)},
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _build_mappings_redirect(job.id, error=str(exc))

    return _build_jobs_redirect(success="Mappings saved. The job no longer needs manual review.")


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    all_visible_jobs = _list_visible_jobs(db, current_user=session.user, limit=None)
    latest_jobs = all_visible_jobs[:RECENT_JOBS_LIMIT]
    older_jobs = all_visible_jobs[RECENT_JOBS_LIMIT:]
    _ensure_report_records_for_jobs(db, older_jobs)
    db.commit()
    report_rows = _build_report_rows(
        db,
        current_user=session.user,
        excluded_job_ids={job.id for job in latest_jobs},
    )

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "page_title": "Reports",
            "user": session.user,
            "session": session,
            "report_rows": report_rows,
            "recent_jobs_limit": RECENT_JOBS_LIMIT,
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
            **_build_sidebar_context(active_path="/reports", current_user=session.user),
        },
    )


@router.get("/reports/{report_id}/download")
def download_report(report_id: UUID, request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    report = db.get(Report, report_id)
    if report is None or not _can_access_job(session.user, report.job):
        return RedirectResponse("/reports", status_code=303)

    rows = _load_job_rows_for_report(db, job_id=report.job_id)
    report_bytes = _build_job_report_csv(report.job, rows)
    report.byte_size = len(report_bytes)
    report.checksum_sha256 = hashlib.sha256(report_bytes).hexdigest()
    report.file_name = report.file_name or _build_job_report_filename(report.job)
    report.content_type = report.content_type or "text/csv"

    record_audit_event(
        db,
        actor_user_id=session.user.id,
        action="reports.download",
        object_type="report",
        object_id=str(report.id),
        request=request,
        metadata={"job_id": str(report.job_id), "report_type": report.report_type.value},
    )
    db.commit()

    return Response(
        content=report_bytes,
        media_type=f"{report.content_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report.file_name}"'},
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    users = list_users_for_actor(db, current_user)
    user_rows = [
        {
            "user": user,
            "can_manage": can_manage_target(current_user, user),
            "can_change_role": current_user.role == Role.SUPER_ADMIN and can_manage_target(current_user, user),
        }
        for user in users
    ]

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "page_title": "Users",
            "user": current_user,
            "session": session,
            "Role": Role,
            "user_rows": user_rows,
            "allowed_roles": allowed_creatable_roles(current_user),
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
            "visible_admin_count": sum(1 for user in users if user.role == Role.ADMIN),
            "visible_user_count": sum(1 for user in users if user.role == Role.USER),
            "inactive_count": sum(1 for user in users if not user.is_active),
            **_build_sidebar_context(active_path="/users", current_user=current_user),
        },
    )


@router.post("/users/create")
def create_user_from_ui(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(default=""),
    password: str = Form(...),
    role: str = Form(default=Role.USER.value),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    if len(password) < 8:
        return _redirect_with_message("/users", error="Passwords must be at least 8 characters long.")

    try:
        created_user = create_managed_user(
            db,
            actor=current_user,
            email=email,
            password=password,
            full_name=full_name,
            role=Role(role),
        )
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.create",
            object_type="user",
            object_id=str(created_user.id),
            request=request,
            metadata={"email": created_user.email, "role": created_user.role.value},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))
    except ValueError:
        db.rollback()
        return _redirect_with_message("/users", error="Invalid role selected.")

    return _redirect_with_message("/users", success=f"Created account for {created_user.email}.")


@router.post("/users/{user_id}/status")
def update_user_status_from_ui(
    user_id: UUID,
    request: Request,
    is_active: str = Form(...),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        return _redirect_with_message("/users", error="User not found.")

    try:
        set_user_active_state(
            db,
            actor=current_user,
            target_user=target_user,
            is_active=is_active.lower() == "true",
        )
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.update_status",
            object_type="user",
            object_id=str(target_user.id),
            request=request,
            metadata={"is_active": target_user.is_active},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))

    status_label = "activated" if target_user.is_active else "deactivated"
    return _redirect_with_message("/users", success=f"{target_user.email} {status_label}.")


@router.post("/users/{user_id}/role")
def update_user_role_from_ui(
    user_id: UUID,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        return _redirect_with_message("/users", error="User not found.")

    try:
        set_user_role(db, actor=current_user, target_user=target_user, role=Role(role))
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.update_role",
            object_type="user",
            object_id=str(target_user.id),
            request=request,
            metadata={"role": target_user.role.value},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))
    except ValueError:
        db.rollback()
        return _redirect_with_message("/users", error="Invalid role selected.")

    return _redirect_with_message("/users", success=f"{target_user.email} is now {target_user.role.value}.")


@router.post("/users/{user_id}/password")
def reset_user_password_from_ui(
    user_id: UUID,
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    if len(password) < 8:
        return _redirect_with_message("/users", error="Passwords must be at least 8 characters long.")

    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        return _redirect_with_message("/users", error="User not found.")

    try:
        reset_user_password(db, actor=current_user, target_user=target_user, password=password)
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.reset_password",
            object_type="user",
            object_id=str(target_user.id),
            request=request,
            metadata={"password_reset": True},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))

    return _redirect_with_message("/users", success=f"Password reset for {target_user.email}.")
