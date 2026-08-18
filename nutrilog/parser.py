"""Shorthand macro and timestamp parser for Nutrilog."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
import re
from typing import Optional
from dateutil import parser as date_parser

from nutrilog.models import (
    Energy,
    GramsQuantity,
    MealLog,
    MealType,
    NutrientEntry,
    NutrientType,
    TimeInterval,
)


def infer_meal_type(dt: datetime, tz: Optional[tzinfo] = None) -> MealType:
    """Infer meal type from a datetime's hour of the day."""
    if tz is not None and dt.tzinfo is not None:
        dt_local = dt.astimezone(tz)
    else:
        dt_local = dt
    hour = dt_local.hour
    if 5 <= hour < 11:
        return MealType.BREAKFAST
    elif 11 <= hour < 15:
        return MealType.LUNCH
    elif 15 <= hour < 18:
        return MealType.SNACK
    elif 18 <= hour < 21:
        return MealType.DINNER
    else:
        return MealType.SNACK


class ParsedMacros:
    def __init__(
        self,
        name: str = "",
        protein: float = 0.0,
        fat: float = 0.0,
        carbs: float = 0.0,
        calories: float = 0.0,
        fiber: float = 0.0,
        sugar: float = 0.0,
        sodium: float = 0.0,
        meal_type: Optional[MealType] = None,
        timestamp: Optional[datetime] = None,
        tz: Optional[tzinfo] = None,
    ):
        from nutrilog.storage import get_user_timezone

        self.active_tz = tz or get_user_timezone()
        self.name = name.strip()
        self.protein = protein
        self.fat = fat
        self.carbs = carbs
        self.calories = calories
        self.fiber = fiber
        self.sugar = sugar
        self.sodium = sodium
        self.meal_type = meal_type
        self.timestamp = timestamp or datetime.now(self.active_tz)

        # If calories not provided but macros are, estimate calories
        if self.calories <= 0 and (self.protein > 0 or self.carbs > 0 or self.fat > 0):
            self.calories = (self.protein * 4.0) + (self.carbs * 4.0) + (self.fat * 9.0)

    def to_meal_log(self) -> MealLog:
        """Convert parsed macros to a MealLog object."""
        dt = self.timestamp or datetime.now(self.active_tz)
        meal_type = self.meal_type or infer_meal_type(dt, tz=self.active_tz)
        name = self.name or meal_type.value.capitalize()

        nutrients: list[NutrientEntry] = []
        if self.protein > 0:
            nutrients.append(
                NutrientEntry(
                    nutrient=NutrientType.PROTEIN.value,
                    quantity=GramsQuantity(grams=self.protein),
                )
            )
        if self.fiber > 0:
            nutrients.append(
                NutrientEntry(
                    nutrient=NutrientType.FIBER.value,
                    quantity=GramsQuantity(grams=self.fiber),
                )
            )
        if self.sugar > 0:
            nutrients.append(
                NutrientEntry(
                    nutrient=NutrientType.SUGAR.value,
                    quantity=GramsQuantity(grams=self.sugar),
                )
            )
        if self.sodium > 0:
            nutrients.append(
                NutrientEntry(
                    nutrient=NutrientType.SODIUM.value,
                    quantity=GramsQuantity(grams=self.sodium),
                )
            )

        return MealLog(
            foodDisplayName=name,
            mealType=meal_type,
            interval=TimeInterval.from_datetimes(dt),
            energy=Energy(kcal=round(self.calories, 1)),
            totalCarbohydrate=GramsQuantity(grams=round(self.carbs, 2)),
            totalFat=GramsQuantity(grams=round(self.fat, 2)),
            nutrients=nutrients,
        )


def _classify_nutrient(tag: str) -> Optional[str]:
    t = tag.lower().strip()
    if t in ("p", "pro", "prot", "protein", "proteins"):
        return "protein"
    elif t in ("f", "fat", "fats", "total_fat"):
        return "fat"
    elif t in ("c", "carb", "carbs", "carbohydrate", "carbohydrates", "total_carb"):
        return "carbs"
    elif t in ("k", "cal", "cals", "kcal", "kcals", "calorie", "calories", "energy"):
        return "calories"
    elif t in ("fib", "fiber", "fibres"):
        return "fiber"
    elif t in ("sug", "sugar", "sugars"):
        return "sugar"
    elif t in ("sod", "sodium"):
        return "sodium"
    return None


def parse_shorthand(
    text: str,
    default_meal_type: Optional[MealType] = None,
    default_time: Optional[datetime] = None,
    tz: Optional[tzinfo] = None,
) -> ParsedMacros:
    """Parse shorthand nutrition strings like:
    - '38p 18f 54c 580k Tofu Edamame Soba Bowl'
    - 'Tofu Bowl 38g protein, 18g fat, 54g carbs, 580 kcal'
    - 'protein: 30, carbs: 40, fat: 10, calories: 350'
    - 'p38.5 f18 c54.2 580cal Protein Bowl'
    - '35p 600k'
    """
    from nutrilog.storage import get_user_timezone

    active_tz = tz or get_user_timezone()
    cleaned = text.strip()
    if not cleaned:
        return ParsedMacros(meal_type=default_meal_type, timestamp=default_time, tz=active_tz)

    protein = 0.0
    fat = 0.0
    carbs = 0.0
    calories = 0.0
    fiber = 0.0
    sugar = 0.0
    sodium = 0.0

    working_text = cleaned

    def apply_val(category: str, val: float):
        nonlocal protein, fat, carbs, calories, fiber, sugar, sodium
        if category == "protein":
            protein = val
        elif category == "fat":
            fat = val
        elif category == "carbs":
            carbs = val
        elif category == "calories":
            calories = val
        elif category == "fiber":
            fiber = val
        elif category == "sugar":
            sugar = val
        elif category == "sodium":
            sodium = val

    # 1. Match explicit key-value pairs like "protein: 35g", "calories = 580", "fat: 12"
    kv_pattern = re.compile(
        r"(?i)\b(protein|proteins|pro|prot|total_fat|fat|fats|total_carb|carbohydrates|carbohydrate|carbs|carb|calories|calorie|kcals|kcal|cals|cal|energy|fibres|fiber|fib|sugars|sugar|sug|sodium|sod)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:mg|g|kcal|cal|k)?\b"
    )

    def kv_sub(m: re.Match) -> str:
        tag, val_str = m.group(1), m.group(2)
        category = _classify_nutrient(tag)
        if category:
            apply_val(category, float(val_str))
        return " "

    working_text = kv_pattern.sub(kv_sub, working_text)

    # 2. Match "NUMBER g NUTRIENT" like "38g protein", "54g carbs", "500mg sodium"
    num_g_nutrient_pattern = re.compile(
        r"(?i)(?:^|(?<=\s))([0-9]+(?:\.[0-9]+)?)\s*(?:g|mg)\s+(protein|proteins|pro|prot|total_fat|fat|fats|total_carb|carbohydrates|carbohydrate|carbs|carb|fibres|fiber|fib|sugars|sugar|sug|sodium|sod)\b"
    )

    def num_g_sub(m: re.Match) -> str:
        val_str, tag = m.group(1), m.group(2)
        category = _classify_nutrient(tag)
        if category:
            apply_val(category, float(val_str))
        return " "

    working_text = num_g_nutrient_pattern.sub(num_g_sub, working_text)

    # 3. Match suffix tokens like "38p", "18f", "54c", "580k", "580kcal", "580cal", "9fib"
    suffix_pattern = re.compile(
        r"(?i)(?:^|(?<=\s))([0-9]+(?:\.[0-9]+)?)\s*(p|pro|f|fat|c|carb|carbs|k|cal|cals|kcal|kcals|calories|fib|fiber|sug|sugar|sod|sodium)\b"
    )

    def suffix_sub(m: re.Match) -> str:
        val_str, tag = m.group(1), m.group(2)
        category = _classify_nutrient(tag)
        if category:
            apply_val(category, float(val_str))
        return " "

    working_text = suffix_pattern.sub(suffix_sub, working_text)

    # 4. Match prefix tokens like "p38", "p38.5", "f18", "c54", "cal580"
    prefix_pattern = re.compile(
        r"(?i)(?:^|(?<=\s))(p|pro|f|c|cal|kcal)([0-9]+(?:\.[0-9]+)?)(?:g|mg|kcal|cal|k)?\b"
    )

    def prefix_sub(m: re.Match) -> str:
        tag, val_str = m.group(1), m.group(2)
        category = _classify_nutrient(tag)
        if category:
            apply_val(category, float(val_str))
        return " "

    working_text = prefix_pattern.sub(prefix_sub, working_text)

    # Clean up remaining food name text
    cleaned_name = re.sub(r"[,;:\-_|]+", " ", working_text)
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()

    return ParsedMacros(
        name=cleaned_name,
        protein=protein,
        fat=fat,
        carbs=carbs,
        calories=calories,
        fiber=fiber,
        sugar=sugar,
        sodium=sodium,
        meal_type=default_meal_type,
        timestamp=default_time,
        tz=active_tz,
    )


def parse_time_str(
    time_str: str,
    base_date: Optional[datetime] = None,
    tz: Optional[tzinfo] = None,
) -> datetime:
    """Parse time/date strings like '12:30', '1:00pm', '2026-08-17 12:30', 'today 12pm'."""
    from nutrilog.storage import get_user_timezone

    active_tz = tz or get_user_timezone()
    now = base_date or datetime.now(active_tz)
    parsed = date_parser.parse(time_str, default=now)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=active_tz)
    return parsed
