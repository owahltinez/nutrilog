from datetime import datetime, timezone
from pathlib import Path
import pytest

from nutrilog.models import MealType
from nutrilog.parser import infer_meal_type, parse_shorthand, parse_time_str
from nutrilog.storage import ENV_CONFIG_DIR


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
    input_str = "Grilled Salmon protein: 35g, fat: 12g, carbs: 5g, calories: 280, fiber: 2g, sodium: 300"
    result = parse_shorthand(input_str)

    assert result.protein == 35.0
    assert result.fat == 12.0
    assert result.carbs == 5.0
    assert result.calories == 280.0
    assert result.fiber == 2.0
    assert result.sodium_mg == 300.0  # 'sodium: 300' on a label means 300mg.
    assert result.name == "Grilled Salmon"


def test_parse_shorthand_calorie_estimation():
    # When calories are omitted, calculate: 30*4 + 40*4 + 10*9 = 120 + 160 + 90 = 370 kcal
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
    result = parse_shorthand(input_str, default_time=fixed_time, tz=timezone.utc)

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
    result = parse_shorthand("30p 400k Protein Shake", default_meal_type=MealType.SNACK)
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
    from datetime import timedelta, timezone
    aest = timezone(timedelta(hours=10))
    base = datetime(2026, 8, 18, 0, 0, 0, tzinfo=aest)
    parsed = parse_time_str("09:30", base_date=base, tz=aest)
    assert parsed.hour == 9
    assert parsed.minute == 30
    assert parsed.tzinfo == aest


def test_parse_shorthand_saturated_fat_and_sodium_in_mg():
    result = parse_shorthand("20p 8.3f 4.4sat 242sod Bar", tz=timezone.utc)

    assert result.saturated_fat == 4.4
    assert result.sodium_mg == 242.0

    nutrients = {n.nutrient: n.quantity.grams for n in result.to_meal_log().nutrients}
    assert nutrients["SATURATED_FAT"] == 4.4
    assert nutrients["SODIUM"] == 0.242


def test_parse_shorthand_accepts_british_fibre_spelling():
    result = parse_shorthand("fibre: 2g Oatmeal", tz=timezone.utc)
    assert result.fiber == 2.0
    assert result.name == "Oatmeal"


def test_parse_shorthand_sodium_honours_gram_unit():
    """'0.5g sodium' is 500mg; the unit must not be discarded."""
    assert parse_shorthand("sodium: 0.5g Test", tz=timezone.utc).sodium_mg == 500.0
    assert parse_shorthand("0.5g sodium Test", tz=timezone.utc).sodium_mg == 500.0
    assert parse_shorthand("sodium: 500mg Test", tz=timezone.utc).sodium_mg == 500.0
    assert parse_shorthand("500mg sodium Test", tz=timezone.utc).sodium_mg == 500.0
