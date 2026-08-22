"""Unit tests for nutrilog.models."""

from datetime import datetime, timedelta, timezone

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
from nutrition.units import WeightUnit


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
    assert meal.nutrient_grams(NutrientType.DIETARY_FIBER) == 9.0
    assert meal.calories_kcal == 580.0

    payload = meal.to_api_payload()
    assert "nutritionLog" in payload
    log = payload["nutritionLog"]
    assert log["foodDisplayName"] == "Tofu Soba Bowl"
    assert log["mealType"] == "LUNCH"
    assert log["energy"]["kcal"] == 580.0
    assert log["totalCarbohydrate"]["grams"] == 54.0
    assert log["totalFat"]["grams"] == 18.0
    assert log["serving"]["foodMeasurementUnitDisplayName"] == "bowl"
    assert "unit" not in log["serving"]

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
        interval=TimeInterval(
            startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"
        ),
        energy=Energy(kcal=400),
        totalCarbohydrate=GramsQuantity(grams=30),
        totalFat=GramsQuantity(grams=10),
        nutrients=[
            NutrientEntry(
                nutrient="PROTEIN", quantity=GramsQuantity(grams=25)
            ),
            NutrientEntry(
                nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=5)
            ),
        ],
    )
    meal2 = MealLog(
        foodDisplayName="Meal 2",
        interval=TimeInterval(
            startTime="2026-08-17T18:00:00Z", endTime="2026-08-17T18:00:00Z"
        ),
        energy=Energy(kcal=600),
        totalCarbohydrate=GramsQuantity(grams=50),
        totalFat=GramsQuantity(grams=20),
        nutrients=[
            NutrientEntry(
                nutrient="PROTEIN", quantity=GramsQuantity(grams=35)
            ),
            NutrientEntry(
                nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=4)
            ),
        ],
    )

    summary = MacroSummary.from_meals([meal1, meal2])
    assert summary.meal_count == 2
    assert summary.total_calories == 1000
    assert summary.total_protein == 60
    assert summary.total_carbs == 80
    assert summary.total_fat == 30
    assert summary.nutrient_totals == {"DIETARY_FIBER": 9.0}


# Authoritative Nutrient enum from the Google Health API v4 discovery doc
# (https://health.googleapis.com/$discovery/rest?version=v4), at
# schemas/NutrientQuantity/properties/nutrient. Other values yield 400.
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
    invalid = sorted(
        n.value for n in NutrientType if n.value not in V4_NUTRIENT_ENUM
    )
    assert invalid == []


def _fiber_meal(grams: float) -> MealLog:
    return MealLog(
        foodDisplayName="Test",
        interval=TimeInterval(
            startTime="2026-08-18T12:00:00Z", endTime="2026-08-18T12:01:00Z"
        ),
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
    assert nutrients == [
        {"nutrient": "DIETARY_FIBER", "quantity": {"grams": 1.9}}
    ]


def test_fiber_read_from_dietary_fiber_nutrient():
    payload = {
        "nutritionLog": {
            "foodDisplayName": "Test",
            "interval": {
                "startTime": "2026-08-18T12:00:00Z",
                "endTime": "2026-08-18T12:01:00Z",
            },
            "nutrients": [
                {"quantity": {"grams": 1.9}, "nutrient": "DIETARY_FIBER"}
            ],
        }
    }
    assert (
        MealLog.from_api_payload(payload).nutrient_grams(
            NutrientType.DIETARY_FIBER
        )
        == 1.9
    )


def test_carbs_fall_back_to_carbohydrates_nutrient():
    """Points from other clients may carry carbs only in the nutrients array."""
    payload = {
        "nutritionLog": {
            "foodDisplayName": "Test",
            "interval": {
                "startTime": "2026-08-18T12:00:00Z",
                "endTime": "2026-08-18T12:01:00Z",
            },
            "nutrients": [
                {"quantity": {"grams": 7.7}, "nutrient": "CARBOHYDRATES"}
            ],
        }
    }
    assert MealLog.from_api_payload(payload).carbs_g == 7.7


def test_meal_log_reads_sugar_saturated_fat_and_sodium():
    """Nutrient getters must read the values nutrilog writes."""
    meal = MealLog(
        foodDisplayName="Musashi bar",
        interval=TimeInterval(
            startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"
        ),
        energy=Energy(kcal=236),
        nutrients=[
            NutrientEntry(nutrient="SUGAR", quantity=GramsQuantity(grams=3.7)),
            NutrientEntry(
                nutrient="SATURATED_FAT", quantity=GramsQuantity(grams=4.4)
            ),
            NutrientEntry(
                nutrient="SODIUM", quantity=GramsQuantity(grams=0.242)
            ),
        ],
    )
    assert meal.nutrient_grams(NutrientType.SUGAR) == 3.7
    assert meal.nutrient_grams(NutrientType.SATURATED_FAT) == 4.4
    # Stored in grams, surfaced in milligrams to match how labels state sodium.
    assert meal.nutrient_grams(NutrientType.SODIUM) == 0.242


def test_meal_log_missing_nutrients_read_zero():
    meal = MealLog(
        foodDisplayName="Plain",
        interval=TimeInterval(
            startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:00:00Z"
        ),
        energy=Energy(kcal=10),
    )
    assert meal.nutrient_grams(NutrientType.SUGAR) == 0.0
    assert meal.nutrient_grams(NutrientType.SATURATED_FAT) == 0.0
    assert meal.nutrient_grams(NutrientType.SODIUM) == 0.0


def test_to_api_payload_does_not_duplicate_lowercase_protein():
    """A lowercase 'protein' nutrient must not yield two protein entries."""
    meal = MealLog(
        foodDisplayName="x",
        interval=TimeInterval(
            startTime="2026-08-17T12:00:00Z", endTime="2026-08-17T12:01:00Z"
        ),
        energy=Energy(kcal=100),
        nutrients=[
            NutrientEntry(nutrient="protein", quantity=GramsQuantity(grams=20))
        ],
    )
    sent = meal.to_api_payload()["nutritionLog"]["nutrients"]
    assert len([n for n in sent if n["nutrient"].upper() == "PROTEIN"]) == 1


def test_from_datetimes_records_utc_offset():
    """API ignores RFC3339 offset, so it must travel as explicit field."""
    dt = datetime(2026, 8, 19, 9, 30, 0, tzinfo=timezone(timedelta(hours=10)))

    interval = TimeInterval.from_datetimes(dt)

    assert interval.startUtcOffset == "36000s"
    assert interval.endUtcOffset == "36000s"


def test_from_datetimes_records_negative_utc_offset():
    dt = datetime(2026, 8, 19, 9, 30, 0, tzinfo=timezone(timedelta(hours=-7)))

    interval = TimeInterval.from_datetimes(dt)

    assert interval.startUtcOffset == "-25200s"


def test_from_datetimes_offsets_are_computed_per_endpoint():
    """An interval spanning a DST change has two different offsets."""
    start = datetime(
        2026, 8, 19, 9, 30, 0, tzinfo=timezone(timedelta(hours=10))
    )
    # 11:00 at +11:00 is 00:00Z, half an hour after the 23:30Z start.
    end = datetime(2026, 8, 19, 11, 0, 0, tzinfo=timezone(timedelta(hours=11)))

    interval = TimeInterval.from_datetimes(start, end)

    assert interval.startUtcOffset == "36000s"
    assert interval.endUtcOffset == "39600s"


def test_payload_sends_utc_offsets():
    """Without offsets, API stores 0s and meal shows on wrong day."""
    dt = datetime(2026, 8, 19, 9, 30, 0, tzinfo=timezone(timedelta(hours=10)))
    meal = MealLog(
        foodDisplayName="Oat Cortado", interval=TimeInterval.from_datetimes(dt)
    )

    interval = meal.to_api_payload()["nutritionLog"]["interval"]

    assert interval["startUtcOffset"] == "36000s"
    assert interval["endUtcOffset"] == "36000s"


def test_payload_omits_utc_offsets_when_unknown():
    """A naive interval must not claim a +00:00 offset it does not have."""
    meal = MealLog(
        foodDisplayName="Oat Cortado",
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z",
            endTime="2026-08-19T09:31:00Z",
        ),
    )

    interval = meal.to_api_payload()["nutritionLog"]["interval"]

    assert "startUtcOffset" not in interval
    assert "endUtcOffset" not in interval


def test_from_api_payload_round_trips_utc_offsets():
    dt = datetime(2026, 8, 19, 9, 30, 0, tzinfo=timezone(timedelta(hours=10)))
    meal = MealLog(
        foodDisplayName="Oat Cortado", interval=TimeInterval.from_datetimes(dt)
    )

    parsed = MealLog.from_api_payload(meal.to_api_payload())

    assert parsed.interval.startUtcOffset == "36000s"
    assert parsed.interval.endUtcOffset == "36000s"


def test_nutrient_type_covers_the_whole_api_enum():
    """Caffeine and the vitamins must be loggable without a code change."""
    for name in (
        "CAFFEINE",
        "MAGNESIUM",
        "VITAMIN_C",
        "TRANS_FAT",
        "ZINC",
        "FOLATE",
    ):
        assert name in NutrientType.__members__


def test_nutrient_type_from_string_ignores_separators_and_case():
    assert NutrientType.from_string("caffeine") == NutrientType.CAFFEINE
    assert NutrientType.from_string("Vitamin C") == NutrientType.VITAMIN_C
    assert NutrientType.from_string("vitamin-c") == NutrientType.VITAMIN_C
    assert (
        NutrientType.from_string("SATURATED_FAT") == NutrientType.SATURATED_FAT
    )


def test_nutrient_type_from_string_accepts_everyday_names():
    """Nobody writes DIETARY_FIBER on a food diary."""
    assert NutrientType.from_string("fiber") == NutrientType.DIETARY_FIBER
    assert NutrientType.from_string("fibre") == NutrientType.DIETARY_FIBER
    assert NutrientType.from_string("sugars") == NutrientType.SUGAR
    assert NutrientType.from_string("carbs") == NutrientType.CARBOHYDRATES


# Every alias nutrilog carried before its vocabulary moved to the shared
# library. A literal list, so a change over there cannot quietly narrow what
# a user is allowed to write here.
FORMER_ALIASES = {
    "FIBER": NutrientType.DIETARY_FIBER,
    "FIBERS": NutrientType.DIETARY_FIBER,
    "FIBRE": NutrientType.DIETARY_FIBER,
    "FIBRES": NutrientType.DIETARY_FIBER,
    "SUGARS": NutrientType.SUGAR,
    "CARB": NutrientType.CARBOHYDRATES,
    "CARBS": NutrientType.CARBOHYDRATES,
    "CARBOHYDRATE": NutrientType.CARBOHYDRATES,
}


@pytest.mark.parametrize("member", list(NutrientType))
def test_every_api_name_still_resolves_in_every_separator_style(member):
    """Sourcing the vocabulary elsewhere must not drop an API nutrient.

    UNSATURATED_FAT is the one the shared vocabulary does not carry, so this
    is what pins the fallback that keeps it loggable.
    """
    for written in (
        member.value,
        member.value.lower(),
        member.value.replace("_", " ").title(),
        member.value.replace("_", "-").lower(),
    ):
        assert NutrientType.from_string(written) == member, written


@pytest.mark.parametrize("alias,expected", sorted(FORMER_ALIASES.items()))
def test_every_alias_nutrilog_accepted_still_resolves(alias, expected):
    assert NutrientType.from_string(alias) == expected
    assert NutrientType.from_string(alias.lower()) == expected


def test_a_name_the_vocabulary_refuses_stays_refused():
    """The enum fallback must not resurrect a deliberate refusal.

    Looking a rejected name up against the enum is what keeps a member the
    shared vocabulary has yet to learn loggable, so it has to use the API's
    spelling rather than the vocabulary's normalisation -- the latter strips
    brackets, and salt is refused on purpose.
    """
    assert NutrientType.from_string("salt") is None
    assert NutrientType.from_string("salt equivalent") is None


def test_nutrient_type_from_string_rejects_aggregate_fat():
    """The vocabulary knows `fat`; the API keeps its total in its own field.

    So it resolves as a name and still is not loggable as a nutrient, which
    is why the enum has no member for it.
    """
    assert NutrientType.from_string("fat") is None
    assert NutrientType.from_string("total fat") is None


def test_nutrient_type_from_string_rejects_unknown_names():
    assert NutrientType.from_string("unobtainium") is None
    assert NutrientType.from_string("") is None


def test_nutrient_type_from_string_rejects_salt():
    """Salt is not sodium: 1g salt is ~400mg sodium, so equating is wrong."""
    assert NutrientType.from_string("salt") is None


def test_nutrient_grams_reads_any_nutrient():
    meal = MealLog(
        foodDisplayName="Oat Cortado",
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z", endTime="2026-08-19T09:31:00Z"
        ),
        nutrients=[
            NutrientEntry(
                nutrient="CAFFEINE", quantity=GramsQuantity(grams=0.095)
            ),
        ],
    )

    assert meal.nutrient_grams(NutrientType.CAFFEINE) == 0.095
    assert meal.nutrient_grams(NutrientType.ZINC) == 0.0


def test_payload_round_trips_arbitrary_nutrients_with_their_unit():
    meal = MealLog(
        foodDisplayName="Oat Cortado",
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z", endTime="2026-08-19T09:31:00Z"
        ),
        nutrients=[
            NutrientEntry(
                nutrient=NutrientType.CAFFEINE.value,
                quantity=GramsQuantity(
                    grams=0.095, userProvidedUnit=WeightUnit.MILLIGRAM
                ),
            ),
        ],
    )

    payload = meal.to_api_payload()
    entry = payload["nutritionLog"]["nutrients"][0]
    assert entry["nutrient"] == "CAFFEINE"
    assert entry["quantity"] == {
        "grams": 0.095,
        "userProvidedUnit": "MILLIGRAM",
    }

    parsed = MealLog.from_api_payload(payload)
    assert parsed.nutrient_grams(NutrientType.CAFFEINE) == 0.095
    assert (
        parsed.nutrients[0].quantity.userProvidedUnit == WeightUnit.MILLIGRAM
    )


def test_payload_omits_user_provided_unit_when_unknown():
    meal = MealLog(
        foodDisplayName="Oat Cortado",
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z", endTime="2026-08-19T09:31:00Z"
        ),
        nutrients=[
            NutrientEntry(
                nutrient="CAFFEINE", quantity=GramsQuantity(grams=0.095)
            ),
        ],
    )

    entry = meal.to_api_payload()["nutritionLog"]["nutrients"][0]
    assert entry["quantity"] == {"grams": 0.095}


def test_macro_summary_totals_arbitrary_nutrients():
    """A nutrient nutrilog has no dedicated field for still rolls up."""

    def meal(caffeine_g):
        return MealLog(
            foodDisplayName="Oat Cortado",
            interval=TimeInterval(
                startTime="2026-08-19T09:30:00Z",
                endTime="2026-08-19T09:31:00Z",
            ),
            nutrients=[
                NutrientEntry(
                    nutrient="CAFFEINE",
                    quantity=GramsQuantity(grams=caffeine_g),
                ),
            ],
        )

    summary = MacroSummary.from_meals([meal(0.095), meal(0.063)])

    assert summary.nutrient_totals["CAFFEINE"] == pytest.approx(0.158)


def test_macro_summary_excludes_protein_from_nutrient_totals():
    """Protein has its own total; repeating it would double-count in view."""
    meal = MealLog(
        foodDisplayName="Eggs",
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z", endTime="2026-08-19T09:31:00Z"
        ),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=25))
        ],
    )

    summary = MacroSummary.from_meals([meal])

    assert summary.total_protein == 25
    assert "PROTEIN" not in summary.nutrient_totals


def test_payload_keeps_microgram_precision():
    """2.4µg is 0.0000024g: rounding to 6 places would silently make it 2µg."""
    meal = MealLog(
        foodDisplayName="Supplement",
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z", endTime="2026-08-19T09:31:00Z"
        ),
        nutrients=[
            NutrientEntry(
                nutrient=NutrientType.VITAMIN_B12.value,
                quantity=GramsQuantity(
                    grams=0.0000024, userProvidedUnit=WeightUnit.MICROGRAM
                ),
            ),
        ],
    )

    entry = meal.to_api_payload()["nutritionLog"]["nutrients"][0]

    assert entry["quantity"]["grams"] == pytest.approx(0.0000024)


def test_serving_uses_the_api_field_name_in_both_directions():
    """The API names the unit foodMeasurementUnitDisplayName.

    Writing `unit` is rejected outright, and reading `unit` never matches, so
    a real serving silently lost its unit on the way in.
    """
    api_payload = {
        "nutritionLog": {
            "foodDisplayName": "Soft cheese",
            "mealType": "SNACK",
            "energy": {"kcal": 95.5},
            "totalCarbohydrate": {"grams": 0.5},
            "totalFat": {"grams": 7.0},
            "nutrients": [],
            "serving": {
                "amount": 50,
                "foodMeasurementUnitDisplayName": "gram",
            },
        }
    }

    parsed = MealLog.from_api_payload(api_payload)

    assert parsed.serving is not None
    assert parsed.serving.amount == 50
    assert parsed.serving.unit == "gram"

    # What goes back out must be what the API accepts.
    serving = parsed.to_api_payload()["nutritionLog"]["serving"]
    assert serving == {"amount": 50, "foodMeasurementUnitDisplayName": "gram"}


def test_a_serving_without_a_unit_does_not_invent_one():
    """An absent unit is absent, not the word "serving"."""
    api_payload = {
        "nutritionLog": {
            "foodDisplayName": "Soft cheese",
            "mealType": "SNACK",
            "energy": {"kcal": 95.5},
            "nutrients": [],
            "serving": {"amount": 2},
        }
    }

    parsed = MealLog.from_api_payload(api_payload)

    assert parsed.serving is not None
    assert parsed.serving.unit is None
    assert parsed.to_api_payload()["nutritionLog"]["serving"] == {"amount": 2}
