from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nutrilog.models import MealType, NutrientType
from nutrilog.parser import (
    ParseError,
    infer_meal_type,
    parse_shorthand,
    parse_time_str,
)
from nutrilog.storage import ENV_CONFIG_DIR
from nutrilog.units import WeightUnit


@pytest.fixture(autouse=True)
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_dir = tmp_path / "nutrilog_test_config"
    monkeypatch.setenv(ENV_CONFIG_DIR, str(custom_dir))
    return custom_dir


def test_infer_meal_type():
    assert infer_meal_type(datetime(2026, 8, 17, 8, 30)) == MealType.BREAKFAST
    assert infer_meal_type(datetime(2026, 8, 17, 12, 30)) == MealType.LUNCH
    assert infer_meal_type(datetime(2026, 8, 17, 16, 0)) == MealType.SNACK
    assert infer_meal_type(datetime(2026, 8, 17, 19, 0)) == MealType.DINNER
    assert infer_meal_type(datetime(2026, 8, 17, 23, 0)) == MealType.SNACK
    assert infer_meal_type(datetime(2026, 8, 17, 2, 0)) == MealType.SNACK


def test_parse_shorthand_standard():
    input_str = "38p 18f 54c 580k Tofu Edamame Soba Bowl"
    result = parse_shorthand(input_str)

    assert result.protein == 38.0
    assert result.fat == 18.0
    assert result.carbs == 54.0
    assert result.calories == 580.0
    assert result.name == "Tofu Edamame Soba Bowl"


def test_parse_shorthand_prefix_syntax():
    input_str = "p38.5 f18 c54.2 580cal Protein Bowl"
    result = parse_shorthand(input_str)

    assert result.protein == 38.5
    assert result.fat == 18.0
    assert result.carbs == 54.2
    assert result.calories == 580.0
    assert result.name == "Protein Bowl"


def test_parse_shorthand_explicit_labels():
    input_str = (
        "Grilled Salmon protein: 35g, fat: 12g, carbs: 5g, calories: 280, "
        "fiber: 2g, sodium: 300mg"
    )
    result = parse_shorthand(input_str)

    assert result.protein == 35.0
    assert result.fat == 12.0
    assert result.carbs == 5.0
    assert result.calories == 280.0
    assert _grams(result, NutrientType.DIETARY_FIBER) == 2.0
    assert _grams(result, NutrientType.SODIUM) == pytest.approx(0.3)
    assert result.name == "Grilled Salmon"


def test_parse_shorthand_calorie_estimation():
    # If calories omitted: 30*4 + 40*4 + 10*9 = 120 + 160 + 90 = 370 kcal
    input_str = "30p 40c 10f Oatmeal"
    result = parse_shorthand(input_str)

    assert result.protein == 30.0
    assert result.carbs == 40.0
    assert result.fat == 10.0
    assert result.calories == 370.0
    assert result.name == "Oatmeal"


def test_parse_shorthand_no_name():
    input_str = "25p 180k"
    fixed_time = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    # Pin the zone too: meal type is inferred in local time, so a bare UTC
    # timestamp makes the expected meal type depend on the machine's timezone.
    result = parse_shorthand(
        input_str, default_time=fixed_time, tz=timezone.utc
    )

    assert result.protein == 25.0
    assert result.calories == 180.0
    assert result.name == ""

    meal_log = result.to_meal_log()
    assert meal_log.foodDisplayName == "Lunch"
    assert meal_log.mealType == MealType.LUNCH
    assert meal_log.protein_g == 25.0
    assert meal_log.calories_kcal == 180.0


def test_parse_shorthand_empty():
    result = parse_shorthand("")
    assert result.protein == 0.0
    assert result.calories == 0.0
    assert result.name == ""


def test_parse_shorthand_with_custom_meal_type():
    result = parse_shorthand(
        "30p 400k Protein Shake", default_meal_type=MealType.SNACK
    )
    meal_log = result.to_meal_log()
    assert meal_log.mealType == MealType.SNACK
    assert meal_log.foodDisplayName == "Protein Shake"


def test_parse_time_str():
    base = datetime(2026, 8, 17, 0, 0, 0, tzinfo=timezone.utc)
    parsed = parse_time_str("12:30", base_date=base)
    assert parsed.hour == 12
    assert parsed.minute == 30
    assert parsed.tzinfo is not None

    parsed_full = parse_time_str("2026-08-17 19:45")
    assert parsed_full.year == 2026
    assert parsed_full.month == 8
    assert parsed_full.day == 17
    assert parsed_full.hour == 19
    assert parsed_full.minute == 45


def test_parse_time_str_with_timezone():
    aest = timezone(timedelta(hours=10))
    base = datetime(2026, 8, 18, 0, 0, 0, tzinfo=aest)
    parsed = parse_time_str("09:30", base_date=base, tz=aest)
    assert parsed.hour == 9
    assert parsed.minute == 30
    assert parsed.tzinfo == aest


def test_parse_shorthand_saturated_fat_and_sodium():
    result = parse_shorthand(
        "20p 8.3f saturated fat: 4.4g sodium: 242mg Bar", tz=timezone.utc
    )

    nutrients = {
        n.nutrient: n.quantity.grams for n in result.to_meal_log().nutrients
    }
    assert nutrients["SATURATED_FAT"] == 4.4
    assert nutrients["SODIUM"] == pytest.approx(0.242)
    assert result.name == "Bar"


def test_parse_shorthand_accepts_british_fibre_spelling():
    result = parse_shorthand("fibre: 2g Oatmeal", tz=timezone.utc)
    assert _grams(result, NutrientType.DIETARY_FIBER) == 2.0
    assert result.name == "Oatmeal"


def test_parse_shorthand_sodium_honours_gram_unit():
    """'0.5g sodium' and '500mg sodium' represent the same half gram."""
    for text in (
        "sodium: 0.5g Test",
        "0.5g sodium Test",
        "sodium: 500mg Test",
        "500mg sodium Test",
    ):
        result = parse_shorthand(text, tz=timezone.utc)
        assert _grams(result, NutrientType.SODIUM) == pytest.approx(0.5), text


def _grams(result, nutrient: NutrientType) -> float:
    return result.nutrients[nutrient].grams


def test_parses_any_api_nutrient_by_name():
    """Caffeine needs no dedicated flag, field or shorthand."""
    result = parse_shorthand("Oat Cortado caffeine: 95mg")

    assert _grams(result, NutrientType.CAFFEINE) == pytest.approx(0.095)
    assert result.name == "Oat Cortado"


def test_parses_nutrients_in_every_labelled_form():
    for text in (
        "Eggs sodium: 450mg",
        "Eggs sodium = 450mg",
        "Eggs sodium 450mg",
        "Eggs 450mg sodium",
    ):
        result = parse_shorthand(text)
        assert _grams(result, NutrientType.SODIUM) == pytest.approx(0.45), text
        assert result.name == "Eggs", text


def test_records_the_unit_the_value_was_written_in():
    """Stored so the Health app can show 95mg rather than 0.095g."""
    result = parse_shorthand("Oat Cortado caffeine: 95mg")

    assert (
        result.nutrients[NutrientType.CAFFEINE].userProvidedUnit
        == WeightUnit.MILLIGRAM
    )


def test_parses_microgram_nutrients():
    result = parse_shorthand("Supplement vitamin b12: 2.4µg")

    assert _grams(result, NutrientType.VITAMIN_B12) == pytest.approx(0.0000024)


def test_nutrient_without_a_unit_is_an_error():
    """Assuming a unit would risk a 1000x error, so the user is told instead."""
    with pytest.raises(ParseError) as excinfo:
        parse_shorthand("Eggs sodium: 450")

    assert "sodium" in str(excinfo.value).lower()


def test_nutrient_with_an_unrecognised_unit_is_an_error():
    with pytest.raises(ParseError):
        parse_shorthand("Eggs sodium: 450 spoons")


def test_macros_stay_unitless_shorthand():
    """The four macros keep single letters; only long tail needs names."""
    result = parse_shorthand("38p 18f 54c 580k Tofu Bowl")

    assert (result.protein, result.fat, result.carbs, result.calories) == (
        38.0,
        18.0,
        54.0,
        580.0,
    )
    assert result.name == "Tofu Bowl"


def test_food_names_containing_nutrient_words_survive():
    """A bare nutrient word with no number and unit is part of the food name."""
    for text in ("Musashi Protein Crisp", "Iron Bru", "Low Fat Greek Yogurt"):
        assert parse_shorthand(text).name == text


def test_unclaimed_weight_tokens_are_reported():
    """A dropped macro used to be indistinguishable from one never typed."""
    result = parse_shorthand("Eggs 450mg")

    assert result.nutrients == {}
    assert any("450mg" in w for w in result.warnings)


def test_nutrient_names_ignore_separators_and_case():
    result = parse_shorthand("Juice Vitamin-C: 60mg, saturated fat: 2g")

    assert _grams(result, NutrientType.VITAMIN_C) == pytest.approx(0.06)
    assert _grams(result, NutrientType.SATURATED_FAT) == pytest.approx(2.0)


def test_grams_written_for_a_milligram_nutrient_are_kept_as_written():
    """0.45g of sodium is 450mg; unit is kept and grams are not rescaled."""
    result = parse_shorthand("Eggs sodium: 0.45g")

    assert _grams(result, NutrientType.SODIUM) == pytest.approx(0.45)
    assert (
        result.nutrients[NutrientType.SODIUM].userProvidedUnit
        == WeightUnit.GRAM
    )


def test_parsed_nutrients_reach_the_meal_log():
    meal = parse_shorthand("Oat Cortado 0.8p caffeine: 95mg").to_meal_log()

    assert meal.nutrient_grams(NutrientType.CAFFEINE) == pytest.approx(0.095)
    assert meal.nutrient_grams(NutrientType.PROTEIN) == pytest.approx(0.8)


def test_unclaimed_weight_stays_in_the_food_name():
    """A stray weight is never deleted.

    "(Berry Ripe, 35g)" is a serving size in the name, not a nutrient the user
    forgot to label. Whether it also warns is covered separately below.
    """
    result = parse_shorthand("Snack Proud Protein Bar (Berry Ripe, 35g)")

    assert result.name == "Snack Proud Protein Bar (Berry Ripe, 35g)"


def test_weight_in_a_name_does_not_become_a_nutrient():
    result = parse_shorthand("Chickpeas (100g)")

    assert result.name == "Chickpeas (100g)"
    assert result.nutrients == {}


def test_serving_size_in_parentheses_does_not_warn():
    """A parenthesised weight is a serving size; warning each time is noise."""
    for text in ("Chickpeas (100g)", "Protein Bar (Berry Ripe, 35g)"):
        result = parse_shorthand(text)
        assert result.name == text, text
        assert result.warnings == [], text


def test_unlabelled_weight_outside_parentheses_still_warns():
    result = parse_shorthand("Eggs 450mg")

    assert any("450mg" in w for w in result.warnings)
