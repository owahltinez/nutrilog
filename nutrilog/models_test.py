"""Unit tests for nutrilog.models."""

from datetime import datetime, timezone
import pytest
from nutrilog.models import (
    Energy,
    GramsQuantity,
    MacroSummary,
    MealLog,
    MealType,
    NutrientEntry,
    NutrientType,
    Serving,
    TimeInterval,
)


def test_meal_type_from_string():
    assert MealType.from_string("breakfast") == MealType.BREAKFAST
    assert MealType.from_string("B") == MealType.BREAKFAST
    assert MealType.from_string("lunch") == MealType.LUNCH
    assert MealType.from_string("L") == MealType.LUNCH
    assert MealType.from_string("dinner") == MealType.DINNER
    assert MealType.from_string("D") == MealType.DINNER
    assert MealType.from_string("snack") == MealType.SNACK
    assert MealType.from_string("S") == MealType.SNACK
    assert MealType.from_string("unknown") == MealType.MEAL_TYPE_UNSPECIFIED


def test_time_interval_from_datetimes():
    dt = datetime(2026, 8, 17, 12, 30, 0, tzinfo=timezone.utc)
    interval = TimeInterval.from_datetimes(dt)
    assert interval.startTime == "2026-08-17T12:30:00Z"
    assert interval.endTime == "2026-08-17T12:31:00Z"

    dt_end = datetime(2026, 8, 17, 13, 0, 0, tzinfo=timezone.utc)
    interval2 = TimeInterval.from_datetimes(dt, dt_end)
    assert interval2.startTime == "2026-08-17T12:30:00Z"
    assert interval2.endTime == "2026-08-17T13:00:00Z"


def test_meal_log_payload_serialization():
    meal = MealLog(
        foodDisplayName="Tofu Soba Bowl",
        mealType=MealType.LUNCH,
        interval=TimeInterval(
            startTime="2026-08-17T12:30:00Z",
            endTime="2026-08-17T13:00:00Z",
        ),
        energy=Energy(kcal=580.0),
        totalCarbohydrate=GramsQuantity(grams=54.0),
        totalFat=GramsQuantity(grams=18.0),
        nutrients=[
            NutrientEntry(
                nutrient=NutrientType.PROTEIN.value,
                quantity=GramsQuantity(grams=38.5),
            ),
            NutrientEntry(
                nutrient=NutrientType.DIETARY_FIBER.value,
                quantity=GramsQuantity(grams=9.0),
            ),
        ],
        serving=Serving(amount=1.0, unit="bowl"),
    )

    assert meal.protein_g == 38.5
    assert meal.fat_g == 18.0
    assert meal.carbs_g == 54.0
    assert meal.fiber_g == 9.0
    assert meal.calories_kcal == 580.0

    payload = meal.to_api_payload()
    assert "nutritionLog" in payload
    log = payload["nutritionLog"]
    assert log["foodDisplayName"] == "Tofu Soba Bowl"
    assert log["mealType"] == "LUNCH"
    assert log["energy"]["kcal"] == 580.0
    assert log["totalCarbohydrate"]["grams"] == 54.0
    assert log["totalFat"]["grams"] == 18.0
    assert log["serving"]["unit"] == "bowl"

    # Test round trip parsing
    parsed_meal = MealLog.from_api_payload(payload, point_id="point-123")
    assert parsed_meal.id == "point-123"
    assert parsed_meal.foodDisplayName == "Tofu Soba Bowl"
    assert parsed_meal.mealType == MealType.LUNCH
    assert parsed_meal.calories_kcal == 580.0
    assert parsed_meal.protein_g == 38.5
    assert parsed_meal.carbs_g == 54.0
    assert parsed_meal.fat_g == 18.0
    assert parsed_meal.serving is not None
    assert parsed_meal.serving.unit == "bowl"


def test_macro_summary():
    meal1 = MealLog(
        foodDisplayName="Meal 1",
        interval=TimeInterval(startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"),
        energy=Energy(kcal=400),
        totalCarbohydrate=GramsQuantity(grams=30),
        totalFat=GramsQuantity(grams=10),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=25)),
            NutrientEntry(nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=5)),
        ],
    )
    meal2 = MealLog(
        foodDisplayName="Meal 2",
        interval=TimeInterval(startTime="2026-08-17T18:00:00Z", endTime="2026-08-17T18:00:00Z"),
        energy=Energy(kcal=600),
        totalCarbohydrate=GramsQuantity(grams=50),
        totalFat=GramsQuantity(grams=20),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=35)),
            NutrientEntry(nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=4)),
        ],
    )

    summary = MacroSummary.from_meals([meal1, meal2])
    assert summary.meal_count == 2
    assert summary.total_calories == 1000
    assert summary.total_protein == 60
    assert summary.total_carbs == 80
    assert summary.total_fat == 30
    assert summary.total_fiber == 9


# Authoritative Nutrient enum from the Google Health API v4 discovery document
# (https://health.googleapis.com/$discovery/rest?version=v4), at
# schemas/NutrientQuantity/properties/nutrient. Sending any other value is a 400.
V4_NUTRIENT_ENUM = frozenset(
    {
        "NUTRIENT_UNSPECIFIED",
        "BIOTIN",
        "CAFFEINE",
        "CALCIUM",
        "CHLORIDE",
        "CARBOHYDRATES",
        "CHOLESTEROL",
        "CHROMIUM",
        "COPPER",
        "DIETARY_FIBER",
        "FOLATE",
        "FOLIC_ACID",
        "IODINE",
        "IRON",
        "MAGNESIUM",
        "MANGANESE",
        "MOLYBDENUM",
        "MONOUNSATURATED_FAT",
        "NIACIN",
        "PANTOTHENIC_ACID",
        "PHOSPHORUS",
        "POLYUNSATURATED_FAT",
        "POTASSIUM",
        "PROTEIN",
        "RIBOFLAVIN",
        "SATURATED_FAT",
        "SELENIUM",
        "SODIUM",
        "SUGAR",
        "THIAMIN",
        "TRANS_FAT",
        "UNSATURATED_FAT",
        "VITAMIN_A",
        "VITAMIN_B12",
        "VITAMIN_B6",
        "VITAMIN_C",
        "VITAMIN_D",
        "VITAMIN_E",
        "VITAMIN_K",
        "ZINC",
    }
)


def test_nutrient_type_values_exist_in_api_enum():
    invalid = sorted(n.value for n in NutrientType if n.value not in V4_NUTRIENT_ENUM)
    assert invalid == []


def _fiber_meal(grams: float) -> MealLog:
    return MealLog(
        foodDisplayName="Test",
        interval=TimeInterval(startTime="2026-08-18T12:00:00Z", endTime="2026-08-18T12:01:00Z"),
        energy=Energy(kcal=236),
        nutrients=[
            NutrientEntry(
                nutrient=NutrientType.DIETARY_FIBER.value,
                quantity=GramsQuantity(grams=grams),
            )
        ],
    )


def test_fiber_written_as_dietary_fiber():
    nutrients = _fiber_meal(1.9).to_api_payload()["nutritionLog"]["nutrients"]
    assert nutrients == [{"nutrient": "DIETARY_FIBER", "quantity": {"grams": 1.9}}]


def test_fiber_read_from_dietary_fiber_nutrient():
    payload = {
        "nutritionLog": {
            "foodDisplayName": "Test",
            "interval": {"startTime": "2026-08-18T12:00:00Z", "endTime": "2026-08-18T12:01:00Z"},
            "nutrients": [{"quantity": {"grams": 1.9}, "nutrient": "DIETARY_FIBER"}],
        }
    }
    assert MealLog.from_api_payload(payload).fiber_g == 1.9


def test_carbs_fall_back_to_carbohydrates_nutrient():
    """Points from other clients may carry carbs only in the nutrients array."""
    payload = {
        "nutritionLog": {
            "foodDisplayName": "Test",
            "interval": {"startTime": "2026-08-18T12:00:00Z", "endTime": "2026-08-18T12:01:00Z"},
            "nutrients": [{"quantity": {"grams": 7.7}, "nutrient": "CARBOHYDRATES"}],
        }
    }
    assert MealLog.from_api_payload(payload).carbs_g == 7.7


def test_meal_log_reads_sugar_saturated_fat_and_sodium():
    """Nutrient getters must read the values nutrilog writes."""
    meal = MealLog(
        foodDisplayName="Musashi bar",
        interval=TimeInterval(startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"),
        energy=Energy(kcal=236),
        nutrients=[
            NutrientEntry(nutrient="SUGAR", quantity=GramsQuantity(grams=3.7)),
            NutrientEntry(nutrient="SATURATED_FAT", quantity=GramsQuantity(grams=4.4)),
            NutrientEntry(nutrient="SODIUM", quantity=GramsQuantity(grams=0.242)),
        ],
    )
    assert meal.sugar_g == 3.7
    assert meal.saturated_fat_g == 4.4
    # Stored in grams, surfaced in milligrams to match how labels state sodium.
    assert meal.sodium_mg == 242.0


def test_meal_log_missing_nutrients_read_zero():
    meal = MealLog(
        foodDisplayName="Plain",
        interval=TimeInterval(startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"),
        energy=Energy(kcal=10),
    )
    assert meal.sugar_g == 0.0
    assert meal.saturated_fat_g == 0.0
    assert meal.sodium_mg == 0.0
