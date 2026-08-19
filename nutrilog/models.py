"""Data models for Nutrilog and Google Health API v4 payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class MealType(str, Enum):
    MEAL_TYPE_UNSPECIFIED = "MEAL_TYPE_UNSPECIFIED"
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    SNACK = "SNACK"

    @classmethod
    def from_string(cls, val: str) -> MealType:
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
    """Subset of the Google Health API v4 `Nutrient` enum that Nutrilog records.

    Values must match the API enum exactly; anything else is rejected with a 400.
    Note the API has no aggregate fat or carbohydrate nutrient: those totals live in
    the dedicated `nutritionLog.totalFat` / `nutritionLog.totalCarbohydrate` fields.
    """

    PROTEIN = "PROTEIN"
    CARBOHYDRATES = "CARBOHYDRATES"
    DIETARY_FIBER = "DIETARY_FIBER"
    SUGAR = "SUGAR"
    SODIUM = "SODIUM"
    POTASSIUM = "POTASSIUM"
    CALCIUM = "CALCIUM"
    IRON = "IRON"
    SATURATED_FAT = "SATURATED_FAT"
    CHOLESTEROL = "CHOLESTEROL"


class GramsQuantity(BaseModel):
    grams: float = 0.0


class Energy(BaseModel):
    kcal: float = 0.0


class Serving(BaseModel):
    amount: float = 1.0
    unit: str = "serving"


class NutrientEntry(BaseModel):
    nutrient: str
    quantity: GramsQuantity


def _utc_offset_seconds(dt: datetime) -> Optional[str]:
    """The datetime's UTC offset as an API Duration string, or None if naive."""
    offset = dt.utcoffset()
    if offset is None:
        return None
    return f"{int(offset.total_seconds())}s"


class TimeInterval(BaseModel):
    startTime: str
    endTime: str
    # The API ignores the offset inside startTime and stores 0s unless these are sent, which
    # makes the Health app file a meal on the UTC day instead of the local one.
    startUtcOffset: Optional[str] = None
    endUtcOffset: Optional[str] = None

    @property
    def start_datetime(self) -> datetime:
        from dateutil.parser import isoparse
        return isoparse(self.startTime)

    @property
    def end_datetime(self) -> datetime:
        from dateutil.parser import isoparse
        return isoparse(self.endTime)

    @classmethod
    def from_datetimes(
        cls,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> TimeInterval:
        from datetime import timedelta

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
    id: Optional[str] = None
    foodDisplayName: str = "Meal"
    mealType: MealType = MealType.MEAL_TYPE_UNSPECIFIED
    interval: TimeInterval
    energy: Energy = Field(default_factory=Energy)
    totalCarbohydrate: GramsQuantity = Field(default_factory=GramsQuantity)
    totalFat: GramsQuantity = Field(default_factory=GramsQuantity)
    nutrients: List[NutrientEntry] = Field(default_factory=list)
    serving: Optional[Serving] = None

    @property
    def calories_kcal(self) -> float:
        return self.energy.kcal

    @property
    def protein_g(self) -> float:
        return self._nutrient_grams(NutrientType.PROTEIN)

    def _nutrient_grams(self, nutrient: NutrientType) -> float:
        """Grams recorded for a nutrient, or 0.0 when it was never logged."""
        for n in self.nutrients:
            if n.nutrient.upper() == nutrient.value:
                return n.quantity.grams
        return 0.0

    @property
    def carbs_g(self) -> float:
        if self.totalCarbohydrate.grams:
            return self.totalCarbohydrate.grams
        return self._nutrient_grams(NutrientType.CARBOHYDRATES)

    @property
    def fat_g(self) -> float:
        # No fallback: the API has no aggregate fat nutrient, so totalFat is the only source.
        return self.totalFat.grams

    @property
    def fiber_g(self) -> float:
        return self._nutrient_grams(NutrientType.DIETARY_FIBER)

    @property
    def sugar_g(self) -> float:
        return self._nutrient_grams(NutrientType.SUGAR)

    @property
    def saturated_fat_g(self) -> float:
        return self._nutrient_grams(NutrientType.SATURATED_FAT)

    @property
    def sodium_mg(self) -> float:
        # The API stores sodium in grams; labels state it in milligrams.
        return round(self._nutrient_grams(NutrientType.SODIUM) * 1000.0, 3)

    def to_api_payload(self) -> dict[str, Any]:
        """Convert to Google Health API v4 nutritionLog dataPoint format."""
        nutrients_list = []
        for n in self.nutrients:
            nutrients_list.append(
                {
                    "nutrient": n.nutrient,
                    # 4dp, not 2: sodium is sub-gram, so 2dp would quantize 242mg to 240mg.
                    "quantity": {"grams": round(n.quantity.grams, 4)},
                }
            )

        # Ensure protein is recorded in nutrients list
        has_protein = any(n.nutrient.upper() == NutrientType.PROTEIN.value for n in self.nutrients)
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

        # Omitted rather than defaulted: a naive interval has no offset to claim.
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
    def from_api_payload(cls, data: dict[str, Any], point_id: Optional[str] = None) -> MealLog:
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
        start_time = interval_data.get("startTime", datetime.now(timezone.utc).isoformat())
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
            nutrients.append(
                NutrientEntry(
                    nutrient=n.get("nutrient", ""),
                    quantity=GramsQuantity(grams=float(n.get("quantity", {}).get("grams", 0.0))),
                )
            )

        serving_data = log_data.get("serving")
        serving = None
        if serving_data:
            serving = Serving(
                amount=float(serving_data.get("amount", 1.0)),
                unit=str(serving_data.get("unit", "serving")),
            )

        raw_meal_type = log_data.get("mealType", MealType.MEAL_TYPE_UNSPECIFIED.value)
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
    total_calories: float = 0.0
    total_protein: float = 0.0
    total_carbs: float = 0.0
    total_fat: float = 0.0
    total_fiber: float = 0.0
    meals: List[MealLog] = Field(default_factory=list)

    @property
    def meal_count(self) -> int:
        return len(self.meals)

    def add_meal(self, meal: MealLog) -> None:
        self.meals.append(meal)
        self.total_calories += meal.calories_kcal
        self.total_protein += meal.protein_g
        self.total_carbs += meal.carbs_g
        self.total_fat += meal.fat_g
        self.total_fiber += meal.fiber_g

    @classmethod
    def from_meals(cls, meals: List[MealLog]) -> MacroSummary:
        summary = cls()
        for meal in meals:
            summary.add_meal(meal)
        return summary
