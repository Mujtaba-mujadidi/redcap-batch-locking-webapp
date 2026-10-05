"""Form-complete checks for lock decisions, including repeating instruments.

Oxford REDCap only returns redcap_repeat_instrument / redcap_repeat_instance
when the record ID field is included in the export `fields` list. Matching must
then require both instrument and instance — never fall back to the first row.
"""

from __future__ import annotations

from app.models.job import JobRow
from app.models.mapping import InstrumentMapping
from app.services.redcap import export_record_rows


def expected_form_complete_field_name(instrument_name: str) -> str:
    return f"{instrument_name}_complete"


def normalize_export_instance_token(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if not text:
        return ""
    try:
        return str(int(text))
    except ValueError:
        return text


def is_form_marked_complete(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) == 2
    normalized_value = str(value or "").strip().lower()
    return normalized_value in {"2", "complete", "completed"}


def row_uses_repeat_context(
    row: JobRow,
    *,
    repeating_forms_events: list[dict[str, object]],
) -> bool:
    """True when this job row should be treated as a repeating form/event instance."""
    if row.repeat_instance is None:
        return False

    if not repeating_forms_events:
        return row.repeat_instance > 1

    requested_event = (row.event_name or "").strip().lower()
    requested_instrument = (row.target_instrument or "").strip().lower()
    for repeat_row in repeating_forms_events:
        repeat_instrument = str(
            repeat_row.get("form_name")
            or repeat_row.get("instrument_name")
            or repeat_row.get("redcap_repeat_instrument")
            or ""
        ).strip().lower()
        repeat_event = str(
            repeat_row.get("unique_event_name")
            or repeat_row.get("event_name")
            or repeat_row.get("redcap_event_name")
            or ""
        ).strip().lower()

        same_instrument = repeat_instrument == requested_instrument if repeat_instrument else False
        same_event = repeat_event == requested_event if repeat_event and requested_event else False
        is_repeating_event = not repeat_instrument and same_event
        if same_instrument or is_repeating_event:
            return True

    return row.repeat_instance > 1


def select_exported_record_row(
    export_rows: list[dict[str, object]],
    *,
    record_id_field_name: str,
    row: JobRow,
    require_repeat_match: bool,
) -> dict[str, object] | None:
    """Pick the export row that belongs to this job row.

    When require_repeat_match is True, both redcap_repeat_instrument and
    redcap_repeat_instance must match exactly. Returns None instead of guessing.
    """
    if not export_rows:
        return None

    filtered_rows = [
        export_row
        for export_row in export_rows
        if str(export_row.get(record_id_field_name) or "").strip() == row.record_id
    ]
    if not filtered_rows:
        # Record-scoped exports sometimes omit the ID field; keep rows only when none include it.
        if any(record_id_field_name in export_row for export_row in export_rows):
            return None
        filtered_rows = list(export_rows)

    if row.event_name:
        event_matches = [
            export_row
            for export_row in filtered_rows
            if str(export_row.get("redcap_event_name") or "").strip().lower() == row.event_name.strip().lower()
        ]
        if event_matches:
            filtered_rows = event_matches
        elif any(str(export_row.get("redcap_event_name") or "").strip() for export_row in filtered_rows):
            return None

    requested_instrument = (row.target_instrument or "").strip().lower()
    requested_instance = (
        normalize_export_instance_token(row.repeat_instance) if row.repeat_instance is not None else "1"
    )

    repeating_for_instrument = [
        export_row
        for export_row in filtered_rows
        if str(export_row.get("redcap_repeat_instrument") or "").strip().lower() == requested_instrument
    ]
    # Repeating exports include a blank parent row with an empty complete status.
    # If this instrument's instances are present, never use that parent row.
    if require_repeat_match or repeating_for_instrument:
        if not requested_instrument or not requested_instance:
            return None
        matches = [
            export_row
            for export_row in repeating_for_instrument
            if normalize_export_instance_token(export_row.get("redcap_repeat_instance")) == requested_instance
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    non_repeat_rows = [
        export_row
        for export_row in filtered_rows
        if not str(export_row.get("redcap_repeat_instrument") or "").strip()
        and not normalize_export_instance_token(export_row.get("redcap_repeat_instance"))
    ]
    if non_repeat_rows:
        return non_repeat_rows[0]

    return filtered_rows[0] if len(filtered_rows) == 1 else None


def fetch_form_complete_snapshot(
    *,
    api_url: str,
    api_key: str,
    row: JobRow,
    mapping: InstrumentMapping,
    record_id_field_name: str,
    repeating_forms_events: list[dict[str, object]],
) -> tuple[str, object, dict[str, object] | None, list[dict[str, object]]]:
    form_complete_field_name = mapping.form_complete_field_name or expected_form_complete_field_name(
        row.target_instrument
    )
    require_repeat_match = row_uses_repeat_context(row, repeating_forms_events=repeating_forms_events)

    # Including the record ID field forces this REDCap host to return
    # redcap_repeat_instrument / redcap_repeat_instance. Do not list those
    # system fields in `fields` — this host rejects them with HTTP 400.
    export_field_names = [record_id_field_name, form_complete_field_name]

    export_rows = export_record_rows(
        api_url,
        api_key,
        record_id=row.record_id,
        field_names=export_field_names,
        form_name=row.target_instrument,
        event_name=row.event_name,
    )
    selected_row = select_exported_record_row(
        export_rows,
        record_id_field_name=record_id_field_name,
        row=row,
        require_repeat_match=require_repeat_match,
    )
    if selected_row is None:
        return form_complete_field_name, None, None, export_rows
    return form_complete_field_name, selected_row.get(form_complete_field_name), selected_row, export_rows
