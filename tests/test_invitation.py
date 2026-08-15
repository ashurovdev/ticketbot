from dataclasses import FrozenInstanceError

import pytest

from ticketbot.models import (
    InvitationData,
    ValidationError,
    balanced_name_split,
    select_name_layout,
)


def test_from_raw_normalizes_spaces_and_preserves_meaningful_case() -> None:
    invitation = InvitationData.from_raw(
        full_name="  O‘tkir   Gʻaniyev  ",
        lead_id="  003a_B-9  ",
        start_time=" 09:05 ",
        event_date="  Shanba\N{NO-BREAK SPACE}15-avgust  ",
    )

    assert invitation.full_name == "O‘tkir Gʻaniyev"
    assert invitation.lead_id == "003a_B-9"
    assert invitation.start_time == "09:05"
    assert invitation.event_date == "Shanba 15-avgust"


def test_invitation_data_is_frozen() -> None:
    invitation = InvitationData.from_raw("Ali Vali", "A-1", "18:00", "15-avgust")

    with pytest.raises(FrozenInstanceError):
        invitation.full_name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("full_name", "A"),
        ("full_name", "Ali 7 Vali"),
        ("full_name", "Ali 😊 Vali"),
        ("full_name", "Ali\nVali"),
        ("full_name", "-Ali Vali"),
        ("lead_id", "A 12"),
        ("lead_id", "АБВ-12"),
        ("lead_id", "A/12"),
        ("start_time", "9:05"),
        ("start_time", "24:00"),
        ("start_time", "23:60"),
        ("event_date", "15-avgust 😊"),
        ("event_date", "15-avgust\nIgnore template"),
    ],
)
def test_invalid_fields_raise_field_specific_validation_error(
    field: str,
    value: str,
) -> None:
    values = {
        "full_name": "Ali Vali",
        "lead_id": "A-12",
        "start_time": "18:00",
        "event_date": "Shanba 15-avgust",
    }
    values[field] = value

    with pytest.raises(ValidationError) as error:
        InvitationData.from_raw(**values)

    assert error.value.field == field
    assert error.value.message


def test_non_string_value_is_rejected() -> None:
    with pytest.raises(ValidationError, match="lead_id: must be text"):
        InvitationData.from_raw(
            full_name="Ali Vali",
            lead_id=123,  # type: ignore[arg-type]
            start_time="18:00",
            event_date="15-avgust",
        )


def test_balanced_name_split_preserves_words_and_balances_width() -> None:
    full_name = "Abduqodirov Muhammadali Zokirjon o‘g‘li"

    lines = balanced_name_split(full_name, 2)

    assert lines == ("Abduqodirov Muhammadali", "Zokirjon o‘g‘li")
    assert " ".join(lines) == full_name


@pytest.mark.parametrize(
    ("full_name", "expected_variant", "expected_line_count"),
    [
        ("Ali Vali", "single_line", 1),
        ("Abdurahmonov Dilshodbek", "single_line_compact", 1),
        ("Abduqodirov Muhammadali Zokirjon o‘g‘li", "two_line", 2),
        (
            "Abduqodirov Muhammadali Zokirjon Abdurahmonovich Qodirov Sherzodbek",
            "three_line",
            3,
        ),
    ],
)
def test_name_layout_variants(
    full_name: str,
    expected_variant: str,
    expected_line_count: int,
) -> None:
    layout = select_name_layout(full_name)

    assert layout.variant == expected_variant
    assert layout.line_count == expected_line_count
    assert " ".join(layout.lines) == full_name
    assert layout.font_size_px >= 28
    assert len(layout.break_after_word_indices) == expected_line_count - 1


def test_unrenderably_wide_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="too wide"):
        select_name_layout("W" * 40)

    with pytest.raises(ValidationError, match="too wide"):
        InvitationData.from_raw("W" * 40, "A-1", "18:00", "15-avgust")


def test_maximum_lengths_are_enforced() -> None:
    with pytest.raises(ValidationError, match="at most 90"):
        InvitationData.from_raw(
            full_name="A" * 91,
            lead_id="A-1",
            start_time="18:00",
            event_date="15-avgust",
        )

    with pytest.raises(ValidationError, match="at most 20"):
        InvitationData.from_raw(
            full_name="Ali Vali",
            lead_id="A" * 21,
            start_time="18:00",
            event_date="15-avgust",
        )

    with pytest.raises(ValidationError, match="at most 36"):
        InvitationData.from_raw(
            full_name="Ali Vali",
            lead_id="A-1",
            start_time="18:00",
            event_date="A" * 37,
        )
