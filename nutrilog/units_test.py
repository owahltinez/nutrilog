"""Unit tests for nutrilog.units."""

import pytest
from nutrilog.units import WeightUnit, UnknownUnitError, parse_weight, format_grams


def test_parses_gram_units():
    assert parse_weight(12.5, "g") == (12.5, WeightUnit.GRAM)
    assert parse_weight(12.5, "grams") == (12.5, WeightUnit.GRAM)


def test_parses_milligram_units():
    assert parse_weight(450, "mg") == (0.45, WeightUnit.MILLIGRAM)
    assert parse_weight(450, "milligrams") == (0.45, WeightUnit.MILLIGRAM)


def test_parses_microgram_units_including_ascii_spellings():
    """Labels write micrograms as µg, ug or mcg; all three mean the same thing."""
    for spelling in ("µg", "ug", "mcg", "micrograms"):
        grams, unit = parse_weight(2.4, spelling)
        assert unit == WeightUnit.MICROGRAM
        assert grams == pytest.approx(0.0000024)


def test_unit_matching_ignores_case_and_surrounding_space():
    assert parse_weight(450, " MG ") == (0.45, WeightUnit.MILLIGRAM)


def test_missing_unit_is_rejected():
    """Guessing a unit risks a 1000x error, so an absent unit is the caller's problem."""
    with pytest.raises(UnknownUnitError):
        parse_weight(450, None)
    with pytest.raises(UnknownUnitError):
        parse_weight(450, "")


def test_unrecognised_unit_is_rejected_with_the_offending_text():
    with pytest.raises(UnknownUnitError) as excinfo:
        parse_weight(1, "spoons")
    assert "spoons" in str(excinfo.value)


def test_format_grams_uses_the_unit_the_value_was_given_in():
    assert format_grams(0.45, WeightUnit.MILLIGRAM) == "450mg"
    assert format_grams(12.5, WeightUnit.GRAM) == "12.5g"
    assert format_grams(0.0000024, WeightUnit.MICROGRAM) == "2.4µg"


def test_format_grams_scales_to_a_readable_unit_when_none_was_recorded():
    """Points written by other apps carry grams only, and totals mix units across meals."""
    assert format_grams(0.061, None) == "61mg"
    assert format_grams(0.0000024, None) == "2.4µg"
    assert format_grams(12.5, None) == "12.5g"


def test_format_grams_scaling_treats_zero_as_grams():
    assert format_grams(0.0, None) == "0g"


def test_format_grams_drops_trailing_zeros():
    assert format_grams(12.0, WeightUnit.GRAM) == "12g"
    assert format_grams(0.5, WeightUnit.MILLIGRAM) == "500mg"
