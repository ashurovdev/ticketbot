"""Validated invitation data and adaptive full-name layout rules."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from itertools import combinations, pairwise
from typing import Final, Literal

MAX_FULL_NAME_LENGTH: Final = 90
MAX_LEAD_ID_LENGTH: Final = 20
MAX_EVENT_DATE_LENGTH: Final = 36

NAME_BOX_WIDTH_PX: Final = 500
REFERENCE_NAME_FONT_SIZE_PX: Final = 46
COMPACT_NAME_MIN_FONT_SIZE_PX: Final = 34
WRAPPED_NAME_MAX_FONT_SIZE_PX: Final = 40
WRAPPED_NAME_MIN_FONT_SIZE_PX: Final = 28

_LEAD_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9_-]+\Z")
_START_TIME_PATTERN: Final = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")
_NAME_PUNCTUATION: Final = frozenset(
    "-'"
    "\N{RIGHT SINGLE QUOTATION MARK}"
    "\N{LEFT SINGLE QUOTATION MARK}"
    "\N{MODIFIER LETTER TURNED COMMA}"
    "\N{MODIFIER LETTER APOSTROPHE}"
    "\N{HYPHEN}"
    "\N{NON-BREAKING HYPHEN}"
)

NameLayoutVariant = Literal[
    "single_line",
    "single_line_compact",
    "two_line",
    "three_line",
]


class ValidationError(ValueError):
    """A validation failure tied to one invitation field."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True, slots=True)
class NameLayout:
    """Rendering guidance for the variable full-name block."""

    variant: NameLayoutVariant
    lines: tuple[str, ...]
    font_size_px: int
    line_height_px: int
    break_after_word_indices: tuple[int, ...]

    @property
    def line_count(self) -> int:
        return len(self.lines)


@dataclass(frozen=True, slots=True)
class InvitationData:
    """Normalized, immutable values used to render one invitation."""

    full_name: str
    lead_id: str
    start_time: str
    event_date: str

    def __post_init__(self) -> None:
        # Normalizing here keeps the frozen model safe even if a caller uses the
        # constructor directly. ``from_raw`` remains the explicit public entrypoint.
        full_name = _validate_full_name(self.full_name)
        # Reject a value during data collection if no legible layout can contain it.
        select_name_layout(full_name)
        object.__setattr__(self, "full_name", full_name)
        object.__setattr__(self, "lead_id", _validate_lead_id(self.lead_id))
        object.__setattr__(self, "start_time", _validate_start_time(self.start_time))
        object.__setattr__(self, "event_date", _validate_event_date(self.event_date))

    @classmethod
    def from_raw(
        cls,
        full_name: str,
        lead_id: str,
        start_time: str,
        event_date: str,
    ) -> InvitationData:
        """Validate and normalize values collected from Telegram messages."""

        return cls(
            full_name=full_name,
            lead_id=lead_id,
            start_time=start_time,
            event_date=event_date,
        )

    @property
    def name_layout(self) -> NameLayout:
        return select_name_layout(self.full_name)


def balanced_name_split(full_name: str, line_count: int) -> tuple[str, ...]:
    """Split a name at word boundaries while minimizing the widest line.

    The order and spelling of every word are preserved. If fewer words than the
    requested number of lines are supplied, one word is returned per line.
    """

    normalized_name = _validate_full_name(full_name)
    words = normalized_name.split(" ")
    effective_line_count = min(max(line_count, 1), len(words))
    if effective_line_count == 1:
        return (normalized_name,)

    best_lines: tuple[str, ...] | None = None
    best_score: tuple[float, float, float] | None = None

    for cuts in combinations(range(1, len(words)), effective_line_count - 1):
        boundaries = (0, *cuts, len(words))
        lines = tuple(
            " ".join(words[start:end])
            for start, end in pairwise(boundaries)
        )
        widths = tuple(_estimated_text_width_units(line) for line in lines)
        widest = max(widths)
        narrowest = min(widths)
        mean = sum(widths) / len(widths)
        imbalance = sum(abs(width - mean) for width in widths)
        score = (widest, widest - narrowest, imbalance)
        if best_score is None or score < best_score:
            best_score = score
            best_lines = lines

    if best_lines is None:  # Defensive; combinations always yields here.
        return (normalized_name,)
    return best_lines


def select_name_layout(full_name: str) -> NameLayout:
    """Choose a readable one-, two-, or three-line reference-compatible layout."""

    normalized_name = _validate_full_name(full_name)
    one_line = (normalized_name,)
    one_line_size = _largest_fitting_font_size(one_line, REFERENCE_NAME_FONT_SIZE_PX)

    if one_line_size >= REFERENCE_NAME_FONT_SIZE_PX:
        return _make_layout("single_line", one_line, REFERENCE_NAME_FONT_SIZE_PX)
    if one_line_size >= COMPACT_NAME_MIN_FONT_SIZE_PX:
        return _make_layout("single_line_compact", one_line, one_line_size)

    words = normalized_name.split(" ")
    if len(words) >= 2:
        two_lines = balanced_name_split(normalized_name, 2)
        two_line_size = _largest_fitting_font_size(
            two_lines,
            WRAPPED_NAME_MAX_FONT_SIZE_PX,
        )
        if two_line_size >= WRAPPED_NAME_MIN_FONT_SIZE_PX:
            return _make_layout("two_line", two_lines, two_line_size)

    if len(words) >= 3:
        three_lines = balanced_name_split(normalized_name, 3)
        three_line_size = _largest_fitting_font_size(
            three_lines,
            WRAPPED_NAME_MAX_FONT_SIZE_PX,
        )
        if three_line_size >= WRAPPED_NAME_MIN_FONT_SIZE_PX:
            return _make_layout("three_line", three_lines, three_line_size)

    raise ValidationError(
        "full_name",
        "is too wide to render legibly without cropping or distorting it",
    )


def _make_layout(
    variant: NameLayoutVariant,
    lines: tuple[str, ...],
    font_size_px: int,
) -> NameLayout:
    cumulative_word_count = 0
    break_indices: list[int] = []
    for line in lines[:-1]:
        cumulative_word_count += len(line.split(" "))
        break_indices.append(cumulative_word_count)

    return NameLayout(
        variant=variant,
        lines=lines,
        font_size_px=font_size_px,
        line_height_px=math.ceil(font_size_px * 1.16),
        break_after_word_indices=tuple(break_indices),
    )


def _largest_fitting_font_size(lines: tuple[str, ...], maximum: int) -> int:
    widest_units = max(_estimated_text_width_units(line) for line in lines)
    if widest_units <= 0:
        return maximum
    available_width = NAME_BOX_WIDTH_PX - 8
    return min(maximum, math.floor(available_width / widest_units))


def _estimated_text_width_units(text: str) -> float:
    """Estimate Poppins ExtraBold width in em without requiring font binaries."""

    width = 0.0
    for character in text:
        if character == " ":
            width += 0.30
        elif character in (
            "ilIjtfr1'"
            "\N{RIGHT SINGLE QUOTATION MARK}"
            "\N{MODIFIER LETTER TURNED COMMA}"
            "\N{MODIFIER LETTER APOSTROPHE}"
        ):
            width += 0.34
        elif character in "MWmwQO\N{CYRILLIC CAPITAL LETTER SHA}\N{CYRILLIC SMALL LETTER SHA}":
            width += 0.88
        elif character.isupper():
            width += 0.69
        elif character.isdigit():
            width += 0.62
        elif unicodedata.category(character).startswith("M"):
            # Combining marks do not advance the cursor in a normal font.
            continue
        else:
            width += 0.59
    return width


def _validate_full_name(raw_value: str) -> str:
    value = _normalize_display_text(raw_value, "full_name")
    if len(value) < 2:
        raise ValidationError("full_name", "must contain at least two characters")
    if len(value) > MAX_FULL_NAME_LENGTH:
        raise ValidationError(
            "full_name",
            f"must be at most {MAX_FULL_NAME_LENGTH} characters",
        )

    for character in value:
        category = unicodedata.category(character)
        if character == " " or character in _NAME_PUNCTUATION:
            continue
        if category.startswith(("L", "M")):
            continue
        raise ValidationError(
            "full_name",
            "may contain only letters, spaces, apostrophes, and hyphens",
        )

    if not any(unicodedata.category(character).startswith("L") for character in value):
        raise ValidationError("full_name", "must contain letters")

    for index, character in enumerate(value):
        if character not in _NAME_PUNCTUATION:
            continue
        if index == 0 or index == len(value) - 1:
            raise ValidationError("full_name", "punctuation must be between letters")
        before = value[index - 1]
        after = value[index + 1]
        if not _is_name_letter(before) or not _is_name_letter(after):
            raise ValidationError("full_name", "punctuation must be between letters")

    return value


def _validate_lead_id(raw_value: str) -> str:
    value = _normalize_scalar(raw_value, "lead_id")
    if not value:
        raise ValidationError("lead_id", "is required")
    if len(value) > MAX_LEAD_ID_LENGTH:
        raise ValidationError(
            "lead_id",
            f"must be at most {MAX_LEAD_ID_LENGTH} characters",
        )
    if _LEAD_ID_PATTERN.fullmatch(value) is None:
        raise ValidationError(
            "lead_id",
            "may contain only Latin letters, digits, hyphens, and underscores",
        )
    return value


def _validate_start_time(raw_value: str) -> str:
    value = _normalize_scalar(raw_value, "start_time")
    if _START_TIME_PATTERN.fullmatch(value) is None:
        raise ValidationError("start_time", "must use 24-hour HH:MM format")
    return value


def _validate_event_date(raw_value: str) -> str:
    value = _normalize_display_text(raw_value, "event_date")
    if len(value) < 3:
        raise ValidationError("event_date", "must contain at least three characters")
    if len(value) > MAX_EVENT_DATE_LENGTH:
        raise ValidationError(
            "event_date",
            f"must be at most {MAX_EVENT_DATE_LENGTH} characters",
        )

    for character in value:
        category = unicodedata.category(character)
        if character == " " or category.startswith(("L", "M", "N", "P")):
            continue
        raise ValidationError(
            "event_date",
            "may contain only letters, numbers, spaces, and punctuation",
        )
    return value


def _normalize_display_text(raw_value: str, field: str) -> str:
    value = _require_string(raw_value, field)
    value = unicodedata.normalize("NFC", value)
    _reject_control_characters(value, field)
    value = "".join(" " if unicodedata.category(char) == "Zs" else char for char in value)
    return " ".join(value.strip().split())


def _normalize_scalar(raw_value: str, field: str) -> str:
    value = _require_string(raw_value, field)
    value = unicodedata.normalize("NFC", value)
    _reject_control_characters(value, field)
    return value.strip()


def _require_string(raw_value: str, field: str) -> str:
    if not isinstance(raw_value, str):
        raise ValidationError(field, "must be text")
    return raw_value


def _reject_control_characters(value: str, field: str) -> None:
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValidationError(field, "must not contain control characters or new lines")
    if any(character in "\r\n\t" for character in value):
        raise ValidationError(field, "must not contain control characters or new lines")


def _is_name_letter(character: str) -> bool:
    return unicodedata.category(character).startswith(("L", "M"))


__all__ = [
    "InvitationData",
    "NameLayout",
    "NameLayoutVariant",
    "ValidationError",
    "balanced_name_split",
    "select_name_layout",
]
