"""Backend unit tests for clinical-critical helpers.

Run from backend/:
  python -m pytest
"""

from types import SimpleNamespace

from app.services.form_complete import (
    is_form_marked_complete,
    select_exported_record_row,
)


def _job_row(**overrides):
    base = {
        "record_id": "385-25",
        "target_instrument": "concomitant_medications",
        "repeat_instance": 2,
        "event_name": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_select_exported_record_row_matches_instrument_and_instance():
    export_rows = [
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "",
            "redcap_repeat_instance": "",
            "concomitant_medications_complete": "",
        },
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "concomitant_medications",
            "redcap_repeat_instance": 1,
            "concomitant_medications_complete": "0",
            "med_name": "Creatine ",
        },
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "concomitant_medications",
            "redcap_repeat_instance": 2,
            "concomitant_medications_complete": "2",
            "med_name": "Ibuprofen",
        },
    ]

    selected = select_exported_record_row(
        export_rows,
        record_id_field_name="record_id",
        row=_job_row(repeat_instance=2),
        require_repeat_match=True,
    )

    assert selected is not None
    assert selected["med_name"] == "Ibuprofen"
    assert selected["concomitant_medications_complete"] == "2"


def test_select_exported_record_row_fails_closed_without_identity_fields():
    # This is the failure mode we hit in production before the record_id fix.
    export_rows = [
        {"med_name": "Creatine ", "concomitant_medications_complete": "0"},
        {"med_name": "Ibuprofen", "concomitant_medications_complete": "2"},
    ]

    selected = select_exported_record_row(
        export_rows,
        record_id_field_name="record_id",
        row=_job_row(repeat_instance=2),
        require_repeat_match=True,
    )

    assert selected is None


def test_select_exported_record_row_instance_one():
    export_rows = [
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "concomitant_medications",
            "redcap_repeat_instance": 1,
            "concomitant_medications_complete": "0",
        },
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "concomitant_medications",
            "redcap_repeat_instance": 2,
            "concomitant_medications_complete": "2",
        },
    ]

    selected = select_exported_record_row(
        export_rows,
        record_id_field_name="record_id",
        row=_job_row(repeat_instance=1),
        require_repeat_match=True,
    )

    assert selected is not None
    assert selected["concomitant_medications_complete"] == "0"


def test_is_form_marked_complete():
    assert is_form_marked_complete("2") is True
    assert is_form_marked_complete(2) is True
    assert is_form_marked_complete("complete") is True
    assert is_form_marked_complete("COMPLETED") is True
    assert is_form_marked_complete("0") is False
    assert is_form_marked_complete("1") is False
    assert is_form_marked_complete("") is False
    assert is_form_marked_complete(None) is False


def test_select_exported_record_row_ignores_blank_parent_for_instance_one():
    export_rows = [
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "",
            "redcap_repeat_instance": "",
            "concomitant_medications_complete": "",
        },
        {
            "record_id": "385-25",
            "redcap_repeat_instrument": "concomitant_medications",
            "redcap_repeat_instance": 1,
            "concomitant_medications_complete": "2",
        },
    ]

    selected = select_exported_record_row(
        export_rows,
        record_id_field_name="record_id",
        row=_job_row(repeat_instance=1),
        require_repeat_match=False,
    )

    assert selected is not None
    assert selected["concomitant_medications_complete"] == "2"
