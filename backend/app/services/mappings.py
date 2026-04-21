from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import SystemSetting


MAPPING_LABEL_ALIAS_SETTING_KEY = "mapping_label_aliases"
DEFAULT_STATUS_ALIASES = [
    "lock status",
    "locking status",
    "locked",
    "form locked",
    "record locked",
    "lock indicator",
]
DEFAULT_DATE_ALIASES = [
    "lock date",
    "locking date",
    "locked date",
    "date locked",
    "locked on",
    "date of lock",
]
DATE_FORMAT_OPTIONS = {"YMD", "DMY", "MDY"}
AMBIGUITY_SCORE_MARGIN = 5
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_alias(value: str) -> str:
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


def get_mapping_label_aliases(db: Session) -> dict[str, list[str]]:
    defaults = {
        "status": DEFAULT_STATUS_ALIASES.copy(),
        "date": DEFAULT_DATE_ALIASES.copy(),
    }
    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == MAPPING_LABEL_ALIAS_SETTING_KEY))
    if setting is None or not isinstance(setting.value_json, dict):
        return defaults

    merged: dict[str, list[str]] = {}
    for key, fallback in defaults.items():
        merged_values: dict[str, str] = {normalize_alias(item): item for item in fallback}
        for item in setting.value_json.get(key, []):
            if isinstance(item, str):
                normalized = normalize_alias(item)
                if normalized:
                    merged_values.setdefault(normalized, item.strip())
        merged[key] = list(merged_values.values())
    return merged


def save_mapping_label_aliases(
    db: Session,
    *,
    actor_user_id,
    status_labels: list[str],
    date_labels: list[str],
) -> None:
    cleaned_status_labels = [label.strip() for label in status_labels if label and label.strip()]
    cleaned_date_labels = [label.strip() for label in date_labels if label and label.strip()]
    if not cleaned_status_labels and not cleaned_date_labels:
        return

    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == MAPPING_LABEL_ALIAS_SETTING_KEY))
    if setting is None:
        setting = SystemSetting(
            key=MAPPING_LABEL_ALIAS_SETTING_KEY,
            description="Learned label variants for REDCap lock status and lock date mapping detection.",
            value_json={"status": [], "date": []},
            updated_by_user_id=actor_user_id,
        )
        db.add(setting)

    current_value = setting.value_json if isinstance(setting.value_json, dict) else {"status": [], "date": []}
    for group_name, additions in (("status", cleaned_status_labels), ("date", cleaned_date_labels)):
        current_group = [item for item in current_value.get(group_name, []) if isinstance(item, str)]
        by_normalized = {normalize_alias(item): item for item in current_group}
        for item in additions:
            normalized = normalize_alias(item)
            if normalized:
                by_normalized.setdefault(normalized, item)
        current_value[group_name] = list(by_normalized.values())

    setting.value_json = current_value
    setting.updated_by_user_id = actor_user_id


def build_mapping_review_bundle(
    *,
    instrument_rows: list[dict[str, Any]],
    metadata_rows: list[dict[str, Any]],
    export_field_name_rows: list[dict[str, Any]],
    target_instruments: list[str],
    alias_bank: dict[str, list[str]],
) -> dict[str, Any]:
    instrument_label_lookup = {
        str(row.get("instrument_name") or ""): str(row.get("instrument_label") or row.get("instrument_name") or "")
        for row in instrument_rows
        if row.get("instrument_name")
    }
    export_lookup = _build_export_field_lookup(export_field_name_rows)
    metadata_by_form: dict[str, list[dict[str, Any]]] = {}
    for metadata_row in metadata_rows:
        form_name = str(metadata_row.get("form_name") or "").strip()
        if not form_name:
            continue
        metadata_by_form.setdefault(form_name, []).append(metadata_row)

    instrument_sequence = []
    instrument_reviews: dict[str, dict[str, Any]] = {}
    for instrument_name in target_instruments:
        instrument_sequence.append(instrument_name)
        form_rows = metadata_by_form.get(instrument_name, [])
        field_catalog = _build_field_catalog(form_rows, export_lookup)
        form_complete_field = _detect_form_complete_field(field_catalog, instrument_name)
        complete_index = _field_index(field_catalog, form_complete_field)
        status_candidates = _score_status_candidates(field_catalog, complete_index, alias_bank)
        date_candidates = _score_date_candidates(field_catalog, complete_index, alias_bank)

        selected_status = status_candidates[0] if status_candidates else None
        selected_date = date_candidates[0] if date_candidates else None
        status_requires_confirmation = _requires_manual_confirmation(status_candidates, value_key="lock_value")
        date_requires_confirmation = _requires_manual_confirmation(date_candidates, value_key="date_format")
        confidence = _determine_confidence(
            status_candidate=selected_status,
            date_candidate=selected_date,
            status_requires_confirmation=status_requires_confirmation,
            date_requires_confirmation=date_requires_confirmation,
        )

        notes: list[str] = []
        if status_requires_confirmation and not status_candidates:
            notes.append("No strong lock status field candidate was found.")
        elif status_requires_confirmation and selected_status and not selected_status.get("lock_value"):
            notes.append("A lock status field was detected, but its lock value needs confirmation.")
        elif status_requires_confirmation:
            notes.append("More than one lock status field looks plausible. Confirm which field to use.")
        if date_requires_confirmation and not date_candidates:
            notes.append("No strong lock date field candidate was found.")
        elif date_requires_confirmation and selected_date and not selected_date.get("date_format"):
            notes.append("A lock date field was detected, but its date format needs confirmation.")
        elif date_requires_confirmation:
            notes.append("More than one lock date field looks plausible. Confirm which field to use.")

        instrument_reviews[instrument_name] = {
            "instrument_name": instrument_name,
            "instrument_label": instrument_label_lookup.get(instrument_name) or instrument_name,
            "form_complete_field_name": form_complete_field["field_name"] if form_complete_field else None,
            "form_complete_field_label": form_complete_field["field_label"] if form_complete_field else None,
            "field_catalog": field_catalog,
            "status_candidates": status_candidates,
            "date_candidates": date_candidates,
            "selected_status_candidate": selected_status,
            "selected_date_candidate": selected_date,
            "confidence": confidence,
            "status_requires_confirmation": status_requires_confirmation,
            "date_requires_confirmation": date_requires_confirmation,
            "requires_confirmation": status_requires_confirmation or date_requires_confirmation,
            "notes": notes,
        }

    return {
        "instrument_sequence": instrument_sequence,
        "instrument_reviews": instrument_reviews,
    }


def resolve_status_field_configuration(
    field_definition: dict[str, Any],
    alias_bank: dict[str, list[str]],
    *,
    manual_lock_value: str | None = None,
) -> dict[str, Any]:
    field_type = str(field_definition.get("field_type") or "").lower()
    configuration = {
        "field_name": field_definition.get("field_name"),
        "field_label": field_definition.get("field_label"),
        "field_type": field_type,
    }

    if field_type in {"yesno", "truefalse"}:
        configuration.update(
            {
                "mode": field_type,
                "lock_value": "1",
                "unlock_value": "",
            }
        )
        return configuration

    if field_type == "checkbox":
        export_field_names = field_definition.get("export_field_names") or []
        if not export_field_names:
            raise ValueError("Checkbox fields require an export field name to be writable.")

        if manual_lock_value:
            matching_export = next(
                (
                    item
                    for item in export_field_names
                    if str(item.get("choice_value") or "") == manual_lock_value
                    or str(item.get("export_field_name") or "") == manual_lock_value
                ),
                None,
            )
            if matching_export is None:
                raise ValueError("Manual checkbox lock value did not match any checkbox choice.")
        elif len(export_field_names) == 1:
            matching_export = export_field_names[0]
        else:
            positive_choice = _detect_positive_choice(
                field_definition.get("choices") or [],
                alias_bank["status"],
            )
            matching_export = next(
                (
                    item
                    for item in export_field_names
                    if str(item.get("choice_value") or "") == str(positive_choice or "")
                ),
                None,
            )
            if matching_export is None:
                raise ValueError("Select a checkbox lock value manually for this field.")

        configuration.update(
            {
                "mode": "checkbox",
                "lock_value": "1",
                "unlock_value": "0",
                "choice_value": str(matching_export.get("choice_value") or ""),
                "export_field_name": matching_export.get("export_field_name"),
            }
        )
        return configuration

    if field_type in {"radio", "dropdown"}:
        lock_value = manual_lock_value or _detect_positive_choice(field_definition.get("choices") or [], alias_bank["status"])
        if not lock_value:
            raise ValueError("Select or enter the lock value for this status field.")

        configuration.update(
            {
                "mode": field_type,
                "lock_value": str(lock_value),
                "unlock_value": "",
            }
        )
        return configuration

    raise ValueError("Selected status field type is not supported for lock updates.")


def resolve_date_field_configuration(
    field_definition: dict[str, Any],
    *,
    override_format: str | None = None,
) -> dict[str, Any]:
    field_type = str(field_definition.get("field_type") or "").lower()
    validation_type = str(field_definition.get("validation_type") or "").lower()
    if field_type != "text":
        raise ValueError("Selected lock date field must be a text field with a REDCap date or datetime validation.")

    value_strategy = "current_date"
    inferred_format = None
    if validation_type.startswith("datetime"):
        value_strategy = "current_datetime"

    if "_mdy" in validation_type:
        inferred_format = "MDY"
    elif "_dmy" in validation_type:
        inferred_format = "DMY"
    elif "date" in validation_type or "datetime" in validation_type:
        inferred_format = "YMD"

    chosen_format = override_format or inferred_format
    if chosen_format is not None and chosen_format not in DATE_FORMAT_OPTIONS:
        raise ValueError("Unsupported date format override.")

    if chosen_format is None:
        raise ValueError("Choose the date format for this lock date field.")

    return {
        "mode": "date_text",
        "field_name": field_definition.get("field_name"),
        "field_label": field_definition.get("field_label"),
        "field_type": field_type,
        "validation_type": validation_type,
        "value_strategy": value_strategy,
        "date_format": chosen_format,
        "unlock_value": "",
    }


def _build_export_field_lookup(export_field_name_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = {}
    for row in export_field_name_rows:
        original_field_name = str(row.get("original_field_name") or "").strip()
        if not original_field_name:
            continue
        lookup.setdefault(original_field_name, []).append(
            {
                "choice_value": str(row.get("choice_value") or "").strip(),
                "export_field_name": str(row.get("export_field_name") or "").strip(),
            }
        )
    return lookup


def _build_field_catalog(
    form_rows: list[dict[str, Any]],
    export_lookup: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    field_catalog: list[dict[str, Any]] = []
    for position, row in enumerate(form_rows):
        field_name = str(row.get("field_name") or "").strip()
        field_catalog.append(
            {
                "field_name": field_name,
                "field_label": str(row.get("field_label") or "").strip(),
                "field_type": str(row.get("field_type") or "").strip().lower(),
                "validation_type": str(row.get("text_validation_type_or_show_slider_number") or "").strip().lower(),
                "choices": _parse_choices(str(row.get("select_choices_or_calculations") or "")),
                "export_field_names": export_lookup.get(field_name, []),
                "position": position,
            }
        )
    return field_catalog


def _parse_choices(raw_value: str) -> list[dict[str, str]]:
    if not raw_value.strip():
        return []

    choices: list[dict[str, str]] = []
    for part in raw_value.split("|"):
        code, _, label = part.partition(",")
        if code.strip():
            choices.append({"code": code.strip(), "label": label.strip()})
    return choices


def _detect_form_complete_field(field_catalog: list[dict[str, Any]], instrument_name: str) -> dict[str, Any] | None:
    exact_name = f"{instrument_name}_complete"
    for field_definition in field_catalog:
        if field_definition["field_name"] == exact_name:
            return field_definition
    return {
        "field_name": exact_name,
        "field_label": "",
        "field_type": "form_complete",
        "validation_type": "",
        "choices": [],
        "export_field_names": [],
        "position": len(field_catalog),
    }


def _field_index(field_catalog: list[dict[str, Any]], field_definition: dict[str, Any] | None) -> int | None:
    if field_definition is None:
        return None
    return int(field_definition["position"])


def _score_status_candidates(
    field_catalog: list[dict[str, Any]],
    complete_index: int | None,
    alias_bank: dict[str, list[str]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field_definition in field_catalog:
        field_type = field_definition["field_type"]
        if field_type not in {"yesno", "truefalse", "checkbox", "radio", "dropdown"}:
            continue

        alias_score = _alias_score(field_definition, alias_bank["status"])
        if alias_score <= 0:
            continue

        score = alias_score + _proximity_score(field_definition, complete_index)
        if field_type in {"yesno", "truefalse"}:
            score += 28
        elif field_type == "checkbox":
            score += 24 if len(field_definition["export_field_names"]) == 1 else 16
        else:
            score += 18

        lock_value = None
        try:
            lock_value = resolve_status_field_configuration(field_definition, alias_bank)["lock_value"]
        except ValueError:
            pass

        candidate = {
            "field_name": field_definition["field_name"],
            "field_label": field_definition["field_label"],
            "field_type": field_type,
            "score": score,
            "lock_value": lock_value,
        }
        if lock_value is None:
            candidate["note"] = "Lock value needs manual confirmation."

        candidates.append(candidate)

    return sorted(candidates, key=lambda item: (-item["score"], item["field_name"]))[:5]


def _score_date_candidates(
    field_catalog: list[dict[str, Any]],
    complete_index: int | None,
    alias_bank: dict[str, list[str]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field_definition in field_catalog:
        field_type = field_definition["field_type"]
        validation_type = field_definition["validation_type"]
        if field_type != "text":
            continue

        alias_score = _alias_score(field_definition, alias_bank["date"])
        if alias_score <= 0:
            continue

        score = alias_score + _proximity_score(field_definition, complete_index)
        if validation_type.startswith("date") or validation_type.startswith("datetime"):
            score += 26
        elif score >= 28:
            score += 6
        else:
            continue

        candidate = {
            "field_name": field_definition["field_name"],
            "field_label": field_definition["field_label"],
            "field_type": field_type,
            "validation_type": validation_type,
            "score": score,
            "date_format": _infer_date_format(validation_type),
        }
        candidates.append(candidate)

    return sorted(candidates, key=lambda item: (-item["score"], item["field_name"]))[:5]


def _alias_score(field_definition: dict[str, Any], aliases: list[str]) -> int:
    haystack_parts = [
        normalize_alias(field_definition.get("field_name") or ""),
        normalize_alias(field_definition.get("field_label") or ""),
    ]
    haystack_parts.extend(normalize_alias(choice.get("label") or "") for choice in field_definition.get("choices", []))
    haystack = " ".join(part for part in haystack_parts if part)

    best_score = 0
    for alias in aliases:
        normalized_alias = normalize_alias(alias)
        if not normalized_alias:
            continue
        if normalized_alias in haystack:
            best_score = max(best_score, 18 + 4 * len(normalized_alias.split()))
    return best_score


def _proximity_score(field_definition: dict[str, Any], complete_index: int | None) -> int:
    if complete_index is None:
        return 0

    distance = complete_index - int(field_definition["position"])
    if distance <= 0:
        return 0
    if distance == 1:
        return 30
    if distance == 2:
        return 24
    if distance == 3:
        return 18
    if distance <= 6:
        return 10
    return 0


def _determine_confidence(
    *,
    status_candidate: dict[str, Any] | None,
    date_candidate: dict[str, Any] | None,
    status_requires_confirmation: bool,
    date_requires_confirmation: bool,
) -> str:
    if (
        status_candidate
        and date_candidate
        and not status_requires_confirmation
        and not date_requires_confirmation
    ):
        return "high"
    if status_candidate or date_candidate:
        return "confirm"
    return "not_found"


def _requires_manual_confirmation(candidates: list[dict[str, Any]], *, value_key: str) -> bool:
    if not candidates:
        return True

    lead_candidate = candidates[0]
    if not lead_candidate.get(value_key):
        return True

    if len(candidates) == 1:
        return False

    lead_score = int(lead_candidate.get("score") or 0)
    next_score = int(candidates[1].get("score") or 0)
    return lead_score - next_score <= AMBIGUITY_SCORE_MARGIN


def _detect_positive_choice(choices: list[dict[str, str]], aliases: list[str]) -> str | None:
    positive_codes: list[str] = []
    alias_values = [normalize_alias(alias) for alias in aliases]
    for choice in choices:
        normalized_label = normalize_alias(choice.get("label") or "")
        if not normalized_label:
            continue
        if normalized_label in {"yes", "true", "locked", "lock"}:
            positive_codes.append(choice["code"])
            continue
        if normalized_label in {"no", "false", "unlocked", "unlock", "not locked"}:
            continue
        if any(alias and alias in normalized_label for alias in alias_values):
            positive_codes.append(choice["code"])

    unique_codes = []
    for code in positive_codes:
        if code not in unique_codes:
            unique_codes.append(code)
    if len(unique_codes) == 1:
        return unique_codes[0]
    return None


def _infer_date_format(validation_type: str) -> str | None:
    lowered_value = (validation_type or "").lower()
    if "_mdy" in lowered_value:
        return "MDY"
    if "_dmy" in lowered_value:
        return "DMY"
    if "date" in lowered_value or "datetime" in lowered_value:
        return "YMD"
    return None
