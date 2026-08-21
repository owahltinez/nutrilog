"""Shorthand macro and timestamp parser for Nutrilog."""

import re
from datetime import datetime, tzinfo
from collections.abc import Iterable

from dateutil import parser as date_parser

from nutrilog.models import (
    NUTRIENT_ALIASES,
    Energy,
    GramsQuantity,
    MealLog,
    MealType,
    NutrientEntry,
    NutrientType,
    TimeInterval,
)
from nutrilog.storage import get_user_timezone
from nutrilog.units import UNIT_SPELLINGS, UnknownUnitError, parse_weight


class ParseError(ValueError):
    """The input names a nutrient but its quantity cannot be read."""


def infer_meal_type(dt: datetime, tz: tzinfo | None = None) -> MealType:
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


# The only nutrients with single-letter shorthand. Kept closed: API has 39
# nutrients and single letters do not scale.
_MACRO_ALIASES = {
    "protein": ("p", "pro", "prot", "protein", "proteins"),
    "fat": ("f", "fat", "fats", "total_fat"),
    "carbs": (
        "c",
        "carb",
        "carbs",
        "carbohydrate",
        "carbohydrates",
        "total_carb",
    ),
    "calories": (
        "k",
        "cal",
        "cals",
        "kcal",
        "kcals",
        "calorie",
        "calories",
        "energy",
    ),
}
_MACRO_BY_ALIAS = {
    alias: macro
    for macro, aliases in _MACRO_ALIASES.items()
    for alias in aliases
}


def _alternation(names: Iterable[str]) -> str:
    r"""A regex alternation, longest first so "sugars" wins over "sugar".

    re.escape turns a space into "\ ", which is what lets the caller swap
    it for a separator class covering spaces, underscores and hyphens.
    """
    return "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))


# Protein and carbohydrates are nutrients to the API but macros here: they own
# the "p" and "c" shorthand and their own fields, so macro rules claim them.
MACRO_NUTRIENTS = {NutrientType.PROTEIN, NutrientType.CARBOHYDRATES}

# Nutrient names accept spaces and hyphens where the API uses underscores.
_NUTRIENT_NAMES = [
    n.value.replace("_", " ") for n in NutrientType if n not in MACRO_NUTRIENTS
] + [
    alias.replace("_", " ")
    for alias, nutrient in NUTRIENT_ALIASES.items()
    if nutrient not in MACRO_NUTRIENTS
]
_NUTRIENT_PATTERN = _alternation(_NUTRIENT_NAMES).replace(r"\ ", r"[\s_-]+")
_UNIT_PATTERN = _alternation(UNIT_SPELLINGS)
_NUMBER = r"[0-9]+(?:\.[0-9]+)?"
_MACRO_PATTERN = _alternation(_MACRO_BY_ALIAS)

# Labelled nutrients require a separator or unit to keep food names intact.
_NUTRIENT_LABELLED = re.compile(
    rf"(?i)\b({_NUTRIENT_PATTERN})\s*(?::|=)\s*({_NUMBER})\s*([^\s,;]*)"
)
_NUTRIENT_LABEL_FIRST = re.compile(
    rf"(?i)\b({_NUTRIENT_PATTERN})\s+({_NUMBER})\s*({_UNIT_PATTERN})\b"
)
_NUTRIENT_VALUE_FIRST = re.compile(
    rf"(?i)(?:^|(?<=\s))({_NUMBER})\s*({_UNIT_PATTERN})\s+({_NUTRIENT_PATTERN})\b"
)

# Macros are unitless by convention: "38p", "p38", "protein: 38", "38g protein".
_MACRO_LABELLED = re.compile(
    rf"(?i)\b({_MACRO_PATTERN})\s*[:=]\s*({_NUMBER})\s*(?:g|mg|kcal|cal|k)?\b"
)
_MACRO_VALUE_FIRST = re.compile(
    rf"(?i)(?:^|(?<=\s))({_NUMBER})\s*(?:g|mg)?\s+({_MACRO_PATTERN})\b"
)
_MACRO_SUFFIX = re.compile(
    rf"(?i)(?:^|(?<=\s))({_NUMBER})\s*({_MACRO_PATTERN})\b"
)
_MACRO_PREFIX = re.compile(
    rf"(?i)(?:^|(?<=\s))(p|pro|f|c|cal|kcal)({_NUMBER})(?:g|mg|kcal|cal|k)?\b"
)

# Anything left that looks like a weight was probably meant as a nutrient.
_LEFTOVER_WEIGHT = re.compile(
    rf"(?i)(?:^|(?<=\s))({_NUMBER}\s*(?:{_UNIT_PATTERN}))\b"
)


class ParsedMacros:
    """Parsed macronutrient values and optional food metadata."""

    def __init__(
        self,
        name: str = "",
        protein: float = 0.0,
        fat: float = 0.0,
        carbs: float = 0.0,
        calories: float = 0.0,
        nutrients: dict[NutrientType, GramsQuantity] | None = None,
        meal_type: MealType | None = None,
        timestamp: datetime | None = None,
        tz: tzinfo | None = None,
        warnings: list[str] | None = None,
    ):
        """Initialize ParsedMacros instance."""
        self.active_tz = tz or get_user_timezone()
        self.name = name.strip()
        self.protein = protein
        self.fat = fat
        self.carbs = carbs
        self.calories = calories
        # Everything beyond the four macros, keyed by API nutrient.
        self.nutrients: dict[NutrientType, GramsQuantity] = nutrients or {}
        self.meal_type = meal_type
        self.timestamp = timestamp or datetime.now(self.active_tz)
        self.warnings = warnings or []

        # If calories not provided but macros are, estimate calories
        if self.calories <= 0 and (
            self.protein > 0 or self.carbs > 0 or self.fat > 0
        ):
            self.calories = (
                (self.protein * 4.0) + (self.carbs * 4.0) + (self.fat * 9.0)
            )

    def to_meal_log(self) -> MealLog:
        """Convert parsed macros to a MealLog object."""
        dt = self.timestamp or datetime.now(self.active_tz)
        meal_type = self.meal_type or infer_meal_type(dt, tz=self.active_tz)
        name = self.name or meal_type.value.capitalize()

        # Protein is kept in the nutrients array in the API schema.
        entries: list[NutrientEntry] = []
        if self.protein > 0:
            entries.append(
                NutrientEntry(
                    nutrient=NutrientType.PROTEIN.value,
                    quantity=GramsQuantity(grams=self.protein),
                )
            )
        for nutrient, quantity in self.nutrients.items():
            if nutrient == NutrientType.PROTEIN:
                continue
            entries.append(
                NutrientEntry(nutrient=nutrient.value, quantity=quantity)
            )

        return MealLog(
            foodDisplayName=name,
            mealType=meal_type,
            interval=TimeInterval.from_datetimes(dt),
            energy=Energy(kcal=round(self.calories, 1)),
            totalCarbohydrate=GramsQuantity(grams=round(self.carbs, 2)),
            totalFat=GramsQuantity(grams=round(self.fat, 2)),
            nutrients=entries,
        )


def _inside_parentheses(text: str, index: int) -> bool:
    """Whether index falls between an unclosed "(" and its ")"."""
    return "(" in text[:index] and text[:index].rfind("(") > text[
        :index
    ].rfind(")")


def _quantity(
    nutrient_name: str, value: str, unit: str | None
) -> GramsQuantity:
    """Build a quantity, refusing to guess a unit the user did not write."""
    try:
        grams, resolved = parse_weight(float(value), unit)
    except UnknownUnitError as exc:
        raise ParseError(f"{nutrient_name}: {exc}") from exc
    return GramsQuantity(grams=grams, userProvidedUnit=resolved)


def parse_shorthand(
    text: str,
    default_meal_type: MealType | None = None,
    default_time: datetime | None = None,
    tz: tzinfo | None = None,
) -> ParsedMacros:
    """Parse shorthand nutrition strings into structured macro data.

    Examples:
    - '38p 18f 54c 580k Tofu Edamame Soba Bowl'
    - 'Tofu Bowl 38g protein, 18g fat, 54g carbs, 580 kcal'
    - 'protein: 30, carbs: 40, fat: 10, calories: 350'
    - 'Oat Cortado caffeine: 95mg, magnesium: 7mg'

    The four macros are unitless; every other nutrient is written by name and
    needs an explicit unit. Raises ParseError when a named nutrient's unit
    is missing or unknown.
    """
    active_tz = tz or get_user_timezone()
    cleaned = text.strip()
    if not cleaned:
        return ParsedMacros(
            meal_type=default_meal_type, timestamp=default_time, tz=active_tz
        )

    macros = {"protein": 0.0, "fat": 0.0, "carbs": 0.0, "calories": 0.0}
    nutrients: dict[NutrientType, GramsQuantity] = {}
    working_text = cleaned

    def take_nutrient(name: str, value: str, unit: str | None) -> str:
        nutrient = NutrientType.from_string(name)
        if nutrient is None:
            return " "
        nutrients[nutrient] = _quantity(name, value, unit)
        return " "

    # Named nutrients first: unambiguous and prevents unit mistakes.
    working_text = _NUTRIENT_LABELLED.sub(
        lambda m: take_nutrient(m.group(1), m.group(2), m.group(3)),
        working_text,
    )
    working_text = _NUTRIENT_LABEL_FIRST.sub(
        lambda m: take_nutrient(m.group(1), m.group(2), m.group(3)),
        working_text,
    )
    working_text = _NUTRIENT_VALUE_FIRST.sub(
        lambda m: take_nutrient(m.group(3), m.group(1), m.group(2)),
        working_text,
    )

    def take_macro(alias: str, value: str) -> str:
        macro = _MACRO_BY_ALIAS.get(alias.lower())
        if macro:
            macros[macro] = float(value)
        return " "

    working_text = _MACRO_LABELLED.sub(
        lambda m: take_macro(m.group(1), m.group(2)), working_text
    )
    working_text = _MACRO_VALUE_FIRST.sub(
        lambda m: take_macro(m.group(2), m.group(1)), working_text
    )
    working_text = _MACRO_SUFFIX.sub(
        lambda m: take_macro(m.group(2), m.group(1)), working_text
    )
    working_text = _MACRO_PREFIX.sub(
        lambda m: take_macro(m.group(1), m.group(2)), working_text
    )

    # A leftover weight may be a nutrient whose name was missing or misspelt, so
    # it is flagged -- but left in place, since it is more often a serving size
    # and deleting it would corrupt the food name. Parenthesised ones are not
    # worth mentioning at all: "(35g)" is simply how serving sizes are written.
    warnings = [
        f"{m.group(1)!r} was read as part of the food name, not a nutrient."
        for m in _LEFTOVER_WEIGHT.finditer(working_text)
        if not _inside_parentheses(working_text, m.start())
    ]

    # Only punctuation orphaned by a consumed token is dropped: one preceded
    # by a word character belongs to the name, as in "(Berry Ripe, 35g)".
    cleaned_name = re.sub(r"(?:(?<=\s)|^)[,;:\-_|]+", " ", working_text)
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()

    return ParsedMacros(
        name=cleaned_name,
        protein=macros["protein"],
        fat=macros["fat"],
        carbs=macros["carbs"],
        calories=macros["calories"],
        nutrients=nutrients,
        meal_type=default_meal_type,
        timestamp=default_time,
        tz=active_tz,
        warnings=warnings,
    )


def parse_time_str(
    time_str: str,
    base_date: datetime | None = None,
    tz: tzinfo | None = None,
) -> datetime:
    """Parse '12:30', '1:00pm', '2026-08-17 12:30' or 'today 12pm'."""
    active_tz = tz or get_user_timezone()
    now = base_date or datetime.now(active_tz)
    default = now.replace(hour=0, minute=0, second=0, microsecond=0)
    parsed = date_parser.parse(time_str, default=default)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=active_tz)
    return parsed
