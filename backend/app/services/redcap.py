from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from html import unescape
import json
import re
import ssl
from threading import Lock
from time import monotonic, sleep
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.core.config import get_settings


REQUEST_TIMEOUT_SECONDS = 20
NETWORK_RETRY_ATTEMPTS = 3
NETWORK_RETRY_BACKOFF_SECONDS = 1.5
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DOCKER_HOST_ALIAS = "host.docker.internal"
RATE_LIMIT_WINDOW_SECONDS = 60.0
settings = get_settings()
_rate_limit_registry_lock = Lock()
_rate_limit_overrides_by_host: dict[str, int] = {}
_rate_limit_history_by_host: dict[str, deque[float]] = {}
_rate_limit_lock_by_host: dict[str, Lock] = {}
_rate_limit_callback_var: ContextVar[object | None] = ContextVar("redcap_rate_limit_callback", default=None)
_rate_limit_scope_key_var: ContextVar[str | None] = ContextVar("redcap_rate_limit_scope_key", default=None)


class RedcapServiceError(Exception):
    """Raised when REDCap preflight or request handling fails."""


@contextmanager
def redcap_rate_limit_notifications(callback):
    token = _rate_limit_callback_var.set(callback)
    try:
        yield
    finally:
        _rate_limit_callback_var.reset(token)


@contextmanager
def redcap_rate_limit_scope(api_url: str, project_id: str | None):
    token = _rate_limit_scope_key_var.set(build_redcap_rate_limit_scope_key(api_url, project_id))
    try:
        yield
    finally:
        _rate_limit_scope_key_var.reset(token)


def canonicalize_redcap_api_url(api_url: str) -> str:
    parts = urlsplit(api_url.strip())
    normalized_path = parts.path or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            normalized_path,
            parts.query,
            "",
        )
    )


def canonicalize_redcap_host_base_url(api_url: str) -> str:
    parts = urlsplit(api_url.strip())
    normalized_path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), normalized_path, "", ""))


def build_redcap_rate_limit_scope_key(api_url: str, project_id: str | None = None) -> str:
    host_key = canonicalize_redcap_host_base_url(api_url)
    normalized_project_id = str(project_id or "").strip()
    return f"{host_key}::project::{normalized_project_id or '__host__'}"


def set_redcap_rate_limit_for_scope(api_url: str, rate_limit_per_minute: int | None, project_id: str | None = None) -> int:
    host_key = build_redcap_rate_limit_scope_key(api_url, project_id)
    resolved_limit = rate_limit_per_minute or settings.redcap_rate_limit_per_minute_default
    resolved_limit = max(1, int(resolved_limit))

    with _rate_limit_registry_lock:
        _rate_limit_overrides_by_host[host_key] = resolved_limit
        _rate_limit_history_by_host.setdefault(host_key, deque())
        _rate_limit_lock_by_host.setdefault(host_key, Lock())

    return resolved_limit


def set_redcap_rate_limit_for_host(api_url: str, rate_limit_per_minute: int | None) -> int:
    return set_redcap_rate_limit_for_scope(api_url, rate_limit_per_minute, None)


def _resolve_redcap_rate_limit_for_host(api_url: str) -> tuple[str, int]:
    host_key = _rate_limit_scope_key_var.get() or build_redcap_rate_limit_scope_key(api_url, None)
    with _rate_limit_registry_lock:
        resolved_limit = _rate_limit_overrides_by_host.get(host_key, settings.redcap_rate_limit_per_minute_default)
        _rate_limit_history_by_host.setdefault(host_key, deque())
        _rate_limit_lock_by_host.setdefault(host_key, Lock())

    return host_key, max(1, int(resolved_limit))


def _wait_for_rate_limit_slot(api_url: str) -> None:
    host_key, resolved_limit = _resolve_redcap_rate_limit_for_host(api_url)
    host_lock = _rate_limit_lock_by_host[host_key]
    request_history = _rate_limit_history_by_host[host_key]
    callback = _rate_limit_callback_var.get()
    waiting_notified = False

    while True:
        wait_seconds = 0.0
        with host_lock:
            now = monotonic()
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            while request_history and request_history[0] <= cutoff:
                request_history.popleft()

            if len(request_history) < resolved_limit:
                request_history.append(now)
                if waiting_notified and callable(callback):
                    callback(
                        "resumed",
                        {
                            "host_base_url": host_key,
                            "rate_limit_per_minute": resolved_limit,
                        },
                    )
                return

            wait_seconds = max(0.05, RATE_LIMIT_WINDOW_SECONDS - (now - request_history[0]))

        if callable(callback):
            callback(
                "waiting",
                {
                    "host_base_url": host_key,
                    "rate_limit_per_minute": resolved_limit,
                    "wait_seconds": wait_seconds,
                },
            )
        waiting_notified = True
        sleep(wait_seconds)


def _build_docker_host_alias_url(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.hostname not in LOOPBACK_HOSTS:
        return None

    hostname = parts.hostname or ""
    replacement_netloc = parts.netloc.replace(hostname, DOCKER_HOST_ALIAS, 1)
    return urlunsplit((parts.scheme, replacement_netloc, parts.path, parts.query, parts.fragment))


def _build_ssl_context() -> ssl.SSLContext:
    if get_settings().redcap_ssl_verify:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _perform_form_post(url: str, payload: dict[str, Any]) -> tuple[int, str, str | None]:
    _wait_for_rate_limit_slot(url)
    encoded_payload = urlencode({key: value for key, value in payload.items() if value is not None}).encode("utf-8")
    fallback_url = _build_docker_host_alias_url(url)
    candidate_urls = [url]
    if fallback_url and fallback_url != url:
        candidate_urls.append(fallback_url)

    last_error: URLError | None = None
    for candidate_url in candidate_urls:
        for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
            request = Request(
                candidate_url,
                data=encoded_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )

            try:
                with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS, context=_build_ssl_context()) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    return response.getcode(), body, response.headers.get_content_type()
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                return exc.code, body, exc.headers.get_content_type()
            except URLError as exc:
                last_error = exc
                if attempt < NETWORK_RETRY_ATTEMPTS:
                    sleep(NETWORK_RETRY_BACKOFF_SECONDS * attempt)
                continue

    reason = "Unknown network error."
    if last_error is not None:
        raw_reason = getattr(last_error, "reason", None)
        reason = str(raw_reason or last_error).strip() or last_error.__class__.__name__

    raise RedcapServiceError(
        f"Could not connect to REDCap at {url}. Reason: {reason} after {NETWORK_RETRY_ATTEMPTS} attempts."
    ) from last_error


def _response_excerpt(body: str, limit: int = 240) -> str:
    excerpt = " ".join((body or "").strip().split())
    if len(excerpt) > limit:
        return f"{excerpt[: limit - 3]}..."
    return excerpt


def _extract_xml_error_text(body: str) -> str | None:
    match = re.search(r"<error>\s*(.*?)\s*</error>", body or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return unescape(re.sub(r"<[^>]+>", " ", match.group(1))).strip() or None


def _extract_missing_record_id(message: str) -> str | None:
    match = re.search(r"record\s+'([^']+)'\s+not found", message, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip() or None
    match = re.search(r"do not exist:\s*(.+)$", message, flags=re.IGNORECASE)
    if match:
        first_record = match.group(1).split(",")[0].strip()
        return first_record or None
    return None


def _humanize_locking_module_error(message: str, *, record_id: str | None = None) -> str:
    cleaned_message = " ".join((message or "").split())
    missing_record_id = record_id or _extract_missing_record_id(cleaned_message)
    normalized = cleaned_message.lower()
    if missing_record_id or "not found" in normalized or "do not exist" in normalized:
        record_label = f" '{missing_record_id}'" if missing_record_id else ""
        return (
            f"Record{record_label} is not visible to this API token. "
            "If the record exists, it likely belongs to a Data Access Group that this API user cannot access."
        )
    return cleaned_message


def _raise_module_error(*, context_label: str, http_status: int, body: str, record_id: str | None = None) -> NoReturn:
    xml_error = _extract_xml_error_text(body)
    if xml_error:
        raise RedcapServiceError(_humanize_locking_module_error(xml_error, record_id=record_id))

    excerpt = _response_excerpt(body)
    status_prefix = f"HTTP {http_status}: " if http_status >= 400 else ""
    if excerpt:
        raise RedcapServiceError(
            f"REDCap returned invalid JSON while fetching {context_label}. {status_prefix}{excerpt}"
        )
    raise RedcapServiceError(f"REDCap returned invalid JSON while fetching {context_label}.")


def _parse_json_response(*, context_label: str, http_status: int, body: str, record_id: str | None = None) -> Any:
    normalized_body = body.lstrip()
    if normalized_body.lower().startswith("<!doctype") or normalized_body.lower().startswith("<html"):
        raise RedcapServiceError(f"REDCap returned HTML instead of JSON while fetching {context_label}.")

    if http_status >= 500:
        raise RedcapServiceError(f"REDCap returned a server error while fetching {context_label}.")

    xml_error = _extract_xml_error_text(normalized_body)
    if xml_error:
        raise RedcapServiceError(_humanize_locking_module_error(xml_error, record_id=record_id))

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        _raise_module_error(context_label=context_label, http_status=http_status, body=body, record_id=record_id)


def _post_redcap_json(api_url: str, *, context_label: str, payload: dict[str, Any]) -> Any:
    http_status, body, _ = _perform_form_post(api_url, payload)
    data = _parse_json_response(context_label=context_label, http_status=http_status, body=body)

    if http_status >= 400:
        error_message = body.strip() or f"HTTP {http_status}"
        raise RedcapServiceError(f"REDCap rejected the {context_label} request: {error_message[:240]}")

    return data


def _extract_response_error(data: Any, fallback: str) -> str:
    if isinstance(data, dict):
        for key in ("error", "message", "error_message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return _extract_response_error(data[0], fallback)
    return fallback


def _is_no_repeating_definitions_error(message: str) -> bool:
    normalized_message = " ".join(message.lower().split())
    return (
        "cannot export repeating instruments and events" in normalized_message
        and "does not contain any repeating instruments and events" in normalized_message
    )


def _normalize_module_response(data: Any, *, context_label: str) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        return list(data)
    raise RedcapServiceError(f"Unexpected REDCap response shape while fetching {context_label}.")


def _select_locking_response_row(
    rows: list[dict[str, Any]],
    *,
    context_label: str,
    instrument_name: str | None,
    event_name: str | None,
    repeat_instance: int | None,
) -> dict[str, Any]:
    if not rows:
        raise RedcapServiceError(f"REDCap returned no rows while fetching {context_label}.")
    if len(rows) == 1:
        return rows[0]

    filtered_rows = rows
    requested_instrument = (instrument_name or "").strip().lower()
    if requested_instrument:
        instrument_matches = [
            row
            for row in filtered_rows
            if str(row.get("instrument") or row.get("form_name") or "").strip().lower() == requested_instrument
        ]
        if instrument_matches:
            filtered_rows = instrument_matches

    requested_event = (event_name or "").strip().lower()
    if requested_event:
        event_matches = [
            row
            for row in filtered_rows
            if str(row.get("redcap_event_name") or row.get("event_name") or "").strip().lower() == requested_event
        ]
        if event_matches:
            filtered_rows = event_matches

    if repeat_instance is not None:
        requested_instance = str(repeat_instance).strip()
        instance_matches = [
            row for row in filtered_rows if str(row.get("instance") or "").strip() == requested_instance
        ]
        if instance_matches:
            filtered_rows = instance_matches

    return filtered_rows[0]


def _post_locking_module_json(
    api_url: str,
    *,
    page: str,
    context_label: str,
    payload: dict[str, Any],
) -> tuple[int, list[dict[str, Any]]]:
    module_url = _build_locking_module_url(api_url, page)
    http_status, body, _ = _perform_form_post(module_url, payload)
    record_id = str(payload.get("record") or "").strip() or None
    data = _parse_json_response(
        context_label=context_label,
        http_status=http_status,
        body=body,
        record_id=record_id,
    )
    normalized = _normalize_module_response(data, context_label=context_label)

    if http_status >= 400:
        error_message = _extract_response_error(data, body.strip() or f"HTTP {http_status}")
        raise RedcapServiceError(_humanize_locking_module_error(error_message, record_id=record_id)[:240])

    for row in normalized:
        if "error" in row and isinstance(row["error"], str) and row["error"].strip():
            raise RedcapServiceError(_humanize_locking_module_error(row["error"].strip(), record_id=record_id)[:240])

    return http_status, normalized


def _as_object_list(data: Any, *, context_label: str) -> list[dict[str, Any]]:
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise RedcapServiceError(f"Unexpected REDCap response shape while fetching {context_label}.")


def _as_single_object(data: Any, *, context_label: str) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    raise RedcapServiceError(f"Unexpected REDCap response shape while fetching {context_label}.")


def _build_locking_module_url(api_url: str, page: str) -> str:
    parts = urlsplit(api_url)
    query_items = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    query_items.extend(
        [
            ("NOAUTH", ""),
            ("type", "module"),
            ("prefix", "locking_api"),
            ("page", page),
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), ""))


def probe_locking_api(api_url: str, token: str) -> dict[str, Any]:
    probe_url = _build_locking_module_url(api_url, "status")
    http_status, body, content_type = _perform_form_post(
        probe_url,
        {
            "token": token,
            "record": "__redcap_batch_lock_probe__",
            "returnFormat": "json",
        },
    )
    normalized_body = body.lstrip()
    lowered_body = normalized_body.lower()

    is_html = lowered_body.startswith("<!doctype") or lowered_body.startswith("<html")
    looks_like_json = lowered_body.startswith("{") or lowered_body.startswith("[")
    looks_like_locking_response = any(
        token_fragment in lowered_body
        for token_fragment in ("lock_status", "record required", "locking api", "instance value", "username", "timestamp")
    )
    available = not is_html and (looks_like_json or looks_like_locking_response or http_status < 400)

    if available:
        reason = "Locking module probe succeeded."
    elif is_html:
        reason = "Locking module probe returned HTML instead of API output."
    else:
        reason = "Locking module probe did not return a recognizable locking API response."

    return {
        "available": available,
        "http_status": http_status,
        "content_type": content_type,
        "reason": reason,
        "response_excerpt": normalized_body[:240],
    }


def fetch_redcap_preflight_bundle(api_url: str, token: str) -> dict[str, Any]:
    project_info = _as_single_object(
        _post_redcap_json(
            api_url,
            context_label="project information",
            payload={
                "token": token,
                "content": "project",
                "format": "json",
                "returnFormat": "json",
            },
        ),
        context_label="project information",
    )

    metadata = _as_object_list(
        _post_redcap_json(
            api_url,
            context_label="metadata",
            payload={
                "token": token,
                "content": "metadata",
                "format": "json",
                "returnFormat": "json",
            },
        ),
        context_label="metadata",
    )

    instruments = _as_object_list(
        _post_redcap_json(
            api_url,
            context_label="instrument definitions",
            payload={
                "token": token,
                "content": "instrument",
                "format": "json",
                "returnFormat": "json",
            },
        ),
        context_label="instrument definitions",
    )

    try:
        repeating_forms_events = _as_object_list(
            _post_redcap_json(
                api_url,
                context_label="repeating instrument definitions",
                payload={
                    "token": token,
                    "content": "repeatingFormsEvents",
                    "format": "json",
                    "returnFormat": "json",
                },
            ),
            context_label="repeating instrument definitions",
        )
    except RedcapServiceError as exc:
        if _is_no_repeating_definitions_error(str(exc)):
            repeating_forms_events = []
        else:
            raise

    export_field_names = _as_object_list(
        _post_redcap_json(
            api_url,
            context_label="export field names",
            payload={
                "token": token,
                "content": "exportFieldNames",
                "format": "json",
                "returnFormat": "json",
            },
        ),
        context_label="export field names",
    )

    locking_api_probe = probe_locking_api(api_url, token)
    external_modules = project_info.get("external_modules")
    locking_api_listed = "locking_api" in json.dumps(external_modules, default=str).lower()

    return {
        "project_info": project_info,
        "metadata": metadata,
        "instruments": instruments,
        "repeating_forms_events": repeating_forms_events,
        "export_field_names": export_field_names,
        "locking_api_probe": locking_api_probe,
        "locking_api_listed": locking_api_listed,
        "locking_api_available": locking_api_listed or locking_api_probe["available"],
    }


def fetch_locking_status(
    api_url: str,
    token: str,
    *,
    record_id: str,
    instrument_name: str,
    event_name: str | None = None,
    arm_name: str | None = None,
    repeat_instance: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "token": token,
        "record": record_id,
        "instrument": instrument_name,
        "returnFormat": "json",
    }
    if event_name:
        payload["event"] = event_name
    if arm_name:
        payload["arm"] = arm_name
    if repeat_instance is not None:
        payload["instance"] = repeat_instance

    http_status, response_rows = _post_locking_module_json(
        api_url,
        page="status",
        context_label="locking status",
        payload=payload,
    )
    response = _select_locking_response_row(
        response_rows,
        context_label="locking status",
        instrument_name=instrument_name,
        event_name=event_name,
        repeat_instance=repeat_instance,
    )
    lock_status = response.get("lock_status")
    if lock_status is None:
        lock_status = response.get("locked")
    return {
        "http_status": http_status,
        "lock_status": lock_status,
        "username": response.get("username"),
        "timestamp": response.get("timestamp"),
        "raw": response_rows,
        "selected_row": response,
    }


def apply_locking_action(
    api_url: str,
    token: str,
    *,
    action: str,
    record_id: str,
    instrument_name: str,
    event_name: str | None = None,
    arm_name: str | None = None,
    repeat_instance: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "token": token,
        "record": record_id,
        "instrument": instrument_name,
        "returnFormat": "json",
    }
    if event_name:
        payload["event"] = event_name
    if arm_name:
        payload["arm"] = arm_name
    if repeat_instance is not None:
        payload["instance"] = repeat_instance

    http_status, response_rows = _post_locking_module_json(
        api_url,
        page=action,
        context_label=f"{action} action",
        payload=payload,
    )
    response = _select_locking_response_row(
        response_rows,
        context_label=f"{action} action",
        instrument_name=instrument_name,
        event_name=event_name,
        repeat_instance=repeat_instance,
    )
    lock_status = response.get("lock_status")
    if lock_status is None:
        lock_status = response.get("locked")
    return {
        "http_status": http_status,
        "lock_status": lock_status,
        "username": response.get("username"),
        "timestamp": response.get("timestamp"),
        "raw": response_rows,
        "selected_row": response,
    }


def import_record_update(
    api_url: str,
    token: str,
    *,
    record: dict[str, Any],
    date_format: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "token": token,
        "content": "record",
        "action": "import",
        "format": "json",
        "type": "flat",
        "data": json.dumps([record]),
        "overwriteBehavior": "overwrite",
        "returnFormat": "json",
    }
    if date_format:
        payload["dateFormat"] = date_format

    response = _post_redcap_json(
        api_url,
        context_label="record import",
        payload=payload,
    )
    if isinstance(response, list):
        return {"items": response}
    if isinstance(response, dict):
        return response
    return {"raw": response}


def export_record_rows(
    api_url: str,
    token: str,
    *,
    record_id: str,
    field_names: list[str],
    form_name: str | None = None,
    event_name: str | None = None,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "token": token,
        "content": "record",
        "action": "export",
        "format": "json",
        "type": "flat",
        "records": record_id,
        "fields": ",".join(field_name for field_name in field_names if field_name),
        "returnFormat": "json",
    }
    if form_name:
        payload["forms"] = form_name
    if event_name:
        payload["events"] = event_name

    return _as_object_list(
        _post_redcap_json(
            api_url,
            context_label="record export",
            payload=payload,
        ),
        context_label="record export",
    )
