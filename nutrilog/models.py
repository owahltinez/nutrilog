"""Data models for Nutrilog and Google Health API v4 payloads."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, List, Optional

from dateutil.parser import isoparse
from pydantic import BaseModel, Field

from nutrilog.units import WeightUnit


class MealType(str, Enum):
    """Meal category enum recognized by the Google Health API."""

    MEAL_TYPE_UNSPECIFIED = "MEAL_TYPE_UNSPECIFIED"
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    SNACK = "SNACK"

    @classmethod
    def from_string(cls, val: str) -> MealType:
        """Resolve a written string or alias to a MealType enum value."""
        v = val.strip().upper()
        if v in cls.__members__:
            return cls[v]
        mapping = {
            "B": cls.BREAKFAST,
            "BREAKFAST": cls.BREAKFAST,
            "MORNING": cls.BREAKFAST,
            "L": cls.LUNCH,
            "LUNCH": cls.LUNCH,
            "NOON": cls.LUNCH,
            "D": cls.DINNER,
            "DINNER": cls.DINNER,
            "EVENING": cls.DINNER,
            "NIGHT": cls.DINNER,
            "S": cls.SNACK,
            "SNACK": cls.SNACK,
            "TEA": cls.SNACK,
        }
        return mapping.get(v, cls.MEAL_TYPE_UNSPECIFIED)


class NutrientType(str, Enum):
    """The Google Health API v4 `Nutrient` enum.

    Complete rather than a curated subset: the API treats every nutrient
    identically (a name plus a weight in grams), so listing them all means
    logging caffeine or a vitamin needs no new code. Values must match the
    API exactly or it returns a 400. Aggregate fat and carbohydrate are
    absent by design: those totals live in the dedicated
    `nutritionLog.totalFat` / `nutritionLog.totalCarbohydrate` fields.
    """

    BIOTIN = "BIOTIN"
    CAFFEINE = "CAFFEINE"
    CALCIUM = "CALCIUM"
    CARBOHYDRATES = "CARBOHYDRATES"
    CHLORIDE = "CHLORIDE"
    CHOLESTEROL = "CHOLESTEROL"
    CHROMIUM = "CHROMIUM"
    COPPER = "COPPER"
    DIETARY_FIBER = "DIETARY_FIBER"
    FOLATE = "FOLATE"
    FOLIC_ACID = "FOLIC_ACID"
    IODINE = "IODINE"
    IRON = "IRON"
    MAGNESIUM = "MAGNESIUM"
    MANGANESE = "MANGANESE"
    MOLYBDENUM = "MOLYBDENUM"
    MONOUNSATURATED_FAT = "MONOUNSATURATED_FAT"
    NIACIN = "NIACIN"
    PANTOTHENIC_ACID = "PANTOTHENIC_ACID"
    PHOSPHORUS = "PHOSPHORUS"
    POLYUNSATURATED_FAT = "POLYUNSATURATED_FAT"
    POTASSIUM = "POTASSIUM"
    PROTEIN = "PROTEIN"
    RIBOFLAVIN = "RIBOFLAVIN"
    SATURATED_FAT = "SATURATED_FAT"
    SELENIUM = "SELENIUM"
    SODIUM = "SODIUM"
    SUGAR = "SUGAR"
    THIAMIN = "THIAMIN"
    TRANS_FAT = "TRANS_FAT"
    UNSATURATED_FAT = "UNSATURATED_FAT"
    VITAMIN_A = "VITAMIN_A"
    VITAMIN_B12 = "VITAMIN_B12"
    VITAMIN_B6 = "VITAMIN_B6"
    VITAMIN_C = "VITAMIN_C"
    VITAMIN_D = "VITAMIN_D"
    VITAMIN_E = "VITAMIN_E"
    VITAMIN_K = "VITAMIN_K"
    ZINC = "ZINC"

    @classmethod
    def from_string(cls, val: str) -> Optional[NutrientType]:
        """Resolve a written nutrient name, or None if unknown."""
        normalised = re.sub(r"[\s\-]+", "_", val.strip().upper())
        if normalised in cls.__members__:
            return cls[normalised]
        return NUTRIENT_ALIASES.get(normalised)


# Aliases for names whose API spelling nobody writes by hand. Excludes "salt".
NUTRIENT_ALIASES = {
    "FIBER": NutrientType.DIETARY_FIBER,
    "FIBERS": NutrientType.DIETARY_FIBER,
    "FIBRE": NutrientType.DIETARY_FIBER,
    "FIBRES": NutrientType.DIETARY_FIBER,
    "SUGARS": NutrientType.SUGAR,
    "CARB": NutrientType.CARBOHYDRATES,
    "CARBS": NutrientType.CARBOHYDRATES,
    "CARBOHYDRATE": NutrientType.CARBOHYDRATES,
}


class GramsQuantity(BaseModel):
    """A nutrient quantity measured in grams with an optional user unit."""

    grams: float = 0.0
    # The API echoes this back so clients can show "95mg" instead of "0.095g".
    userProvidedUnit: Optional[WeightUnit] = None  # noqa: N815


class Energy(BaseModel):
    """Energy quantity in kilocalories (kcal)."""

    kcal: float = 0.0


class Serving(BaseModel):
    """Serving size information."""

    amount: float = 1.0
    unit: str = "serving"


class NutrientEntry(BaseModel):
    """A single nutrient entry pairing an API nutrient name with quantity."""

    nutrient: str
    quantity: GramsQuantity


def _utc_offset_seconds(dt: datetime) -> Optional[str]:
    """The datetime's UTC offset as an API Duration, or None if naive."""
    offset = dt.utcoffset()
    if offset is None:
        return None
    return f"{int(offset.total_seconds())}s"


class TimeInterval(BaseModel):
    """Time interval representing when a meal was consumed."""

    startTime: str  # noqa: N815
    endTime: str  # noqa: N815
    # The API ignores the offset inside startTime and stores 0s unless sent.
    startUtcOffset: Optional[str] = None  # noqa: N815
    endUtcOffset: Optional[str] = None  # noqa: N815

    @property
    def start_datetime(self) -> datetime:
        """Parse startTime into a timezone-aware datetime object."""
        return isoparse(self.startTime)

    @property
    def end_datetime(self) -> datetime:
        """Parse endTime into a timezone-aware datetime object."""
        return isoparse(self.endTime)

    @classmethod
    def from_datetimes(
        cls,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> TimeInterval:
        """Create a TimeInterval from start and optional end datetimes."""
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end is None:
            end = start + timedelta(minutes=1)
        elif end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        if end <= start:
            end = start + timedelta(minutes=1)

        return cls(
            startTime=start.isoformat().replace("+00:00", "Z"),
            endTime=end.isoformat().replace("+00:00", "Z"),
            startUtcOffset=_utc_offset_seconds(start),
            endUtcOffset=_utc_offset_seconds(end),
        )


class MealLog(BaseModel):
    """A complete meal log entry matching the Google Health API schema."""

    id: Optional[str] = None
    foodDisplayName: str = "Meal"  # noqa: N815
    mealType: MealType = MealType.MEAL_TYPE_UNSPECIFIED  # noqa: N815
    interval: TimeInterval
    energy: Energy = Field(default_factory=Energy)
    totalCarbohydrate: GramsQuantity = Field(default_factory=GramsQuantity)  # noqa: N815
    totalFat: GramsQuantity = Field(default_factory=GramsQuantity)  # noqa: N815
    nutrients: List[NutrientEntry] = Field(default_factory=list)
    serving: Optional[Serving] = None

    @property
    def calories_kcal(self) -> float:
        """Return total calories in kcal."""
        return self.energy.kcal

    @property
    def protein_g(self) -> float:
        """Return total protein in grams."""
        return self.nutrient_grams(NutrientType.PROTEIN)

    def nutrient_grams(self, nutrient: NutrientType) -> float:
        """Grams recorded for a nutrient, or 0.0 when it was never logged."""
        for n in self.nutrients:
            if n.nutrient.upper() == nutrient.value:
                return n.quantity.grams
        return 0.0

    @property
    def carbs_g(self) -> float:
        """Return total carbohydrates in grams."""
        if self.totalCarbohydrate.grams:
            return self.totalCarbohydrate.grams
        return self.nutrient_grams(NutrientType.CARBOHYDRATES)

    @property
    def fat_g(self) -> float:
        """Return total fat in grams."""
        return self.totalFat.grams

    def to_api_payload(self) -> dict[str, Any]:
        """Convert to Google Health API v4 nutritionLog dataPoint format."""
        nutrients_list = []
        for n in self.nutrients:
            # 9dp preserves microgram precision (e.g. 2.4µg = 0.0000024g).
            quantity: dict[str, Any] = {"grams": round(n.quantity.grams, 9)}
            if n.quantity.userProvidedUnit is not None:
                quantity["userProvidedUnit"] = n.quantity.userProvidedUnit.value
            nutrients_list.append(
                {"nutrient": n.nutrient, "quantity": quantity}
            )

        # Ensure protein is recorded in nutrients list
        has_protein = any(
            n.nutrient.upper() == NutrientType.PROTEIN.value
            for n in self.nutrients
        )
        if not has_protein and self.protein_g > 0:
            nutrients_list.append(
                {
                    "nutrient": NutrientType.PROTEIN.value,
                    "quantity": {"grams": round(self.protein_g, 2)},
                }
            )

        interval_payload: dict[str, Any] = {
            "startTime": self.interval.startTime,
            "endTime": self.interval.endTime,
        }

        # Omitted rather than defaulted: naive interval has no offset to claim.
        if self.interval.startUtcOffset is not None:
            interval_payload["startUtcOffset"] = self.interval.startUtcOffset
        if self.interval.endUtcOffset is not None:
            interval_payload["endUtcOffset"] = self.interval.endUtcOffset

        payload: dict[str, Any] = {
            "nutritionLog": {
                "foodDisplayName": self.foodDisplayName,
                "mealType": self.mealType.value,
                "interval": interval_payload,
                "energy": {"kcal": round(self.energy.kcal, 1)},
                "totalCarbohydrate": {"grams": round(self.carbs_g, 2)},
                "totalFat": {"grams": round(self.fat_g, 2)},
                "nutrients": nutrients_list,
            }
        }
        if self.serving:
            payload["nutritionLog"]["serving"] = {
                "amount": self.serving.amount,
                "unit": self.serving.unit,
            }
        return payload

    @classmethod
    def from_api_payload(
        cls, data: dict[str, Any], point_id: Optional[str] = None
    ) -> MealLog:
        """Parse Google Health API v4 response payload into MealLog."""
        if "response" in data and isinstance(data["response"], dict):
            data = data["response"]

        if not point_id:
            name = data.get("name", "")
            if name:
                point_id = name.split("/")[-1]
            else:
                point_id = data.get("id") or data.get("dataPointId")

        log_data = data.get("nutritionLog", data)
        interval_data = log_data.get("interval", {})
        start_time = interval_data.get(
            "startTime", datetime.now(timezone.utc).isoformat()
        )
        end_time = interval_data.get("endTime", start_time)

        energy_data = log_data.get("energy", {})
        kcal = float(energy_data.get("kcal", 0.0))

        carbs_data = log_data.get("totalCarbohydrate", {})
        carbs_g = float(carbs_data.get("grams", 0.0))

        fat_data = log_data.get("totalFat", {})
        fat_g = float(fat_data.get("grams", 0.0))

        raw_nutrients = log_data.get("nutrients", [])
        nutrients = []
        for n in raw_nutrients:
            quantity_data = n.get("quantity", {})
            nutrients.append(
                NutrientEntry(
                    nutrient=n.get("nutrient", ""),
                    quantity=GramsQuantity(
                        grams=float(quantity_data.get("grams", 0.0)),
                        userProvidedUnit=quantity_data.get("userProvidedUnit"),
                    ),
                )
            )

        serving_data = log_data.get("serving")
        serving = None
        if serving_data:
            serving = Serving(
                amount=float(serving_data.get("amount", 1.0)),
                unit=str(serving_data.get("unit", "serving")),
            )

        raw_meal_type = log_data.get(
            "mealType", MealType.MEAL_TYPE_UNSPECIFIED.value
        )
        meal_type = MealType.from_string(raw_meal_type)

        return cls(
            id=point_id or data.get("id") or data.get("dataPointId"),
            foodDisplayName=log_data.get("foodDisplayName", "Meal"),
            mealType=meal_type,
            interval=TimeInterval(
                startTime=start_time,
                endTime=end_time,
                startUtcOffset=interval_data.get("startUtcOffset"),
                endUtcOffset=interval_data.get("endUtcOffset"),
            ),
            energy=Energy(kcal=kcal),
            totalCarbohydrate=GramsQuantity(grams=carbs_g),
            totalFat=GramsQuantity(grams=fat_g),
            nutrients=nutrients,
            serving=serving,
        )


class MacroSummary(BaseModel):
    """Rollup summary of daily macros and nutrients across multiple meals."""

    total_calories: float = 0.0
    total_protein: float = 0.0
    total_carbs: float = 0.0
    total_fat: float = 0.0
    # Grams per nutrient name, for everything without a dedicated total above.
    nutrient_totals: dict[str, float] = Field(default_factory=dict)
    meals: List[MealLog] = Field(default_factory=list)

    @property
    def meal_count(self) -> int:
        """Return the number of meals included in the summary."""
        return len(self.meals)

    def add_meal(self, meal: MealLog) -> None:
        """Add a meal and aggregate its macronutrients and nutrients."""
        self.meals.append(meal)
        self.total_calories += meal.calories_kcal
        self.total_protein += meal.protein_g
        self.total_carbs += meal.carbs_g
        self.total_fat += meal.fat_g

        # Protein and carbohydrates are excluded: already totalled above.
        for entry in meal.nutrients:
            name = entry.nutrient.upper()
            if name in (
                NutrientType.PROTEIN.value,
                NutrientType.CARBOHYDRATES.value,
            ):
                continue
            self.nutrient_totals[name] = (
                self.nutrient_totals.get(name, 0.0) + entry.quantity.grams
            )

    @classmethod
    def from_meals(cls, meals: List[MealLog]) -> MacroSummary:
        """Construct a MacroSummary rollup from a list of MealLog objects."""
        summary = cls()
        for meal in meals:
            summary.add_meal(meal)
        return summary
