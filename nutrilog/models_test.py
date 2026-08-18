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
                nutrient=NutrientType.FIBER.value,
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
            NutrientEntry(nutrient="FIBER", quantity=GramsQuantity(grams=5)),
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
            NutrientEntry(nutrient="FIBER", quantity=GramsQuantity(grams=4)),
        ],
    )

    summary = MacroSummary.from_meals([meal1, meal2])
    assert summary.meal_count == 2
    assert summary.total_calories == 1000
    assert summary.total_protein == 60
    assert summary.total_carbs == 80
    assert summary.total_fat == 30
    assert summary.total_fiber == 9
