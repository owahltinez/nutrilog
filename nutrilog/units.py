"""Weight unit handling for nutrient quantities.

The Google Health API stores every nutrient in grams and records the unit
the user actually typed alongside it, so a 95mg caffeine entry can be
displayed as "95mg" rather than "0.095g".
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple


class UnknownUnitError(ValueError):
    """A quantity was written with a missing or unrecognised unit."""


class WeightUnit(str, Enum):
    """The subset of the API's `userProvidedUnit` enum that food labels use."""

    GRAM = "GRAM"
    MILLIGRAM = "MILLIGRAM"
    MICROGRAM = "MICROGRAM"


# Grams per unit, and the suffix used when displaying a value back to the user.
_GRAMS_PER_UNIT = {
    WeightUnit.GRAM: 1.0,
    WeightUnit.MILLIGRAM: 0.001,
    WeightUnit.MICROGRAM: 0.000001,
}
_DISPLAY_SUFFIX = {
    WeightUnit.GRAM: "g",
    WeightUnit.MILLIGRAM: "mg",
    WeightUnit.MICROGRAM: "µg",
}

# Micrograms arrive spelled every which way: the micro sign U+00B5, a Greek mu
# U+03BC that labels and copy-paste use interchangeably with it, and the ASCII
# fallbacks "ug" and "mcg".
_SPELLINGS = {
    WeightUnit.GRAM: ("g", "gram", "grams"),
    WeightUnit.MILLIGRAM: ("mg", "milligram", "milligrams"),
    WeightUnit.MICROGRAM: (
        "µg",
        "μg",
        "ug",
        "mcg",
        "microgram",
        "micrograms",
    ),
}
_UNIT_BY_SPELLING = {
    spelling: unit
    for unit, spellings in _SPELLINGS.items()
    for spelling in spellings
}

# Longest first, so a regex alternation prefers "grams" over "g".
UNIT_SPELLINGS = tuple(sorted(_UNIT_BY_SPELLING, key=len, reverse=True))


def resolve_unit(unit: Optional[str]) -> WeightUnit:
    """Map a written unit onto the API enum, rejecting anything unrecognised."""
    if not unit or not unit.strip():
        raise UnknownUnitError(
            "A unit is required: write 95mg or 0.095g, not a bare number."
        )

    resolved = _UNIT_BY_SPELLING.get(unit.strip().lower())
    if resolved is None:
        raise UnknownUnitError(
            f"Unrecognised unit {unit.strip()!r}: use g, mg or µg."
        )
    return resolved


def parse_weight(value: float, unit: Optional[str]) -> Tuple[float, WeightUnit]:
    """Convert a written quantity into grams, keeping the original unit."""
    resolved = resolve_unit(unit)
    return value * _GRAMS_PER_UNIT[resolved], resolved


def _readable_unit(grams: float) -> WeightUnit:
    """The unit that keeps a value legible: 0.061g reads better as 61mg."""
    magnitude = abs(grams)
    if magnitude == 0:
        return WeightUnit.GRAM
    if magnitude < 0.001:
        return WeightUnit.MICROGRAM
    if magnitude < 1:
        return WeightUnit.MILLIGRAM
    return WeightUnit.GRAM


def format_grams(grams: float, unit: Optional[WeightUnit]) -> str:
    """Render grams in original unit or the most legible one if unknown."""
    display_unit = unit or _readable_unit(grams)
    scaled = grams / _GRAMS_PER_UNIT[display_unit]

    # Round before trimming to handle float precision (e.g. 0.45mg).
    text = f"{round(scaled, 6):f}".rstrip("0").rstrip(".")
    return f"{text}{_DISPLAY_SUFFIX[display_unit]}"
