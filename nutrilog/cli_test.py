"""Unit tests for nutrilog.cli."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner

from nutrilog import __version__
from nutrilog.cli import app
from nutrilog.models import (
    Energy,
    GramsQuantity,
    MealLog,
    MealType,
    NutrientEntry,
    TimeInterval,
)
from nutrilog.storage import ENV_CONFIG_DIR

runner = CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_dir = tmp_path / "nutrilog_cli_test"
    monkeypatch.setenv(ENV_CONFIG_DIR, str(custom_dir))
    return custom_dir


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Nutrilog" in result.stdout
    assert __version__ in result.stdout


def test_cli_no_args_shows_help(temp_config_dir: Path):
    result = runner.invoke(app, [])
    assert result.exit_code == 0 or result.exit_code == 2
    assert "Usage" in result.stdout or "help" in result.stdout.lower()


def test_cli_dry_run_explicit_log_command(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "38p 18f 54c 580k Tofu Soba Bowl", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.stdout
    assert "Tofu Soba Bowl" in result.stdout
    assert "38.0g" in result.stdout
    assert "580 kcal" in result.stdout


def test_cli_json_output(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "30p 400k Protein Shake", "--dry-run", "--json"])
    assert result.exit_code == 0
    parsed_json = json.loads(result.stdout)
    assert parsed_json["name"] == "Protein Shake"
    assert parsed_json["protein_g"] == 30.0
    assert parsed_json["calories_kcal"] == 400.0


def test_cli_explicit_flags(temp_config_dir: Path):
    result = runner.invoke(
        app,
        [
            "log",
            "Grilled Barramundi",
            "--protein",
            "36",
            "--calories",
            "480",
            "--fat",
            "14",
            "--carbs",
            "12",
            "--meal",
            "lunch",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Grilled Barramundi" in result.stdout
    assert "36.0g" in result.stdout
    assert "480 kcal" in result.stdout
    assert "Lunch" in result.stdout


def test_cli_history_default_today(temp_config_dir: Path):
    sample_meal = MealLog(
        id="meal-1",
        foodDisplayName="Chicken Rice",
        mealType=MealType.LUNCH,
        interval=TimeInterval(startTime="2026-08-18T12:30:00Z", endTime="2026-08-18T12:30:00Z"),
        energy=Energy(kcal=650),
        totalCarbohydrate=GramsQuantity(grams=70),
        totalFat=GramsQuantity(grams=15),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=45))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "Meal History" in result.stdout
        assert "Chicken" in result.stdout
        assert "Rice" in result.stdout
        assert "45.0g" in result.stdout
        assert "650 kcal" in result.stdout
        assert "meal-1" in result.stdout


def test_cli_history_yesterday(temp_config_dir: Path):
    sample_meal = MealLog(
        id="meal-2",
        foodDisplayName="Oats",
        mealType=MealType.BREAKFAST,
        interval=TimeInterval(startTime="2026-08-17T08:30:00Z", endTime="2026-08-17T08:30:00Z"),
        energy=Energy(kcal=350),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=20))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["history", "--date", "yesterday"])
        assert result.exit_code == 0
        assert "Meal History (Yesterday)" in result.stdout
        assert "Oats" in result.stdout
        assert "meal-2" in result.stdout


def test_cli_history_days(temp_config_dir: Path):
    sample_meal = MealLog(
        id="meal-3",
        foodDisplayName="Tofu",
        mealType=MealType.DINNER,
        interval=TimeInterval(startTime="2026-08-16T19:00:00Z", endTime="2026-08-16T19:00:00Z"),
        energy=Energy(kcal=400),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=30))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["history", "--days", "7"])
        assert result.exit_code == 0
        assert "Meal History (Past 7 Days)" in result.stdout
        assert "Tofu" in result.stdout


def test_cli_history_json(temp_config_dir: Path):
    sample_meal = MealLog(
        id="dp-999",
        foodDisplayName="Protein Shake",
        mealType=MealType.SNACK,
        interval=TimeInterval(startTime="2026-08-18T15:00:00Z", endTime="2026-08-18T15:00:00Z"),
        energy=Energy(kcal=200),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=30))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["history", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert "summary" in parsed
        assert "meals" in parsed
        assert parsed["summary"]["total_protein"] == 30.0
        assert parsed["summary"]["total_calories"] == 200.0
        assert len(parsed["meals"]) == 1
        assert parsed["meals"][0]["name"] == "Protein Shake"


def test_cli_delete_command(temp_config_dir: Path):
    with patch("nutrilog.cli.GoogleHealthClient.delete_meal", return_value=True) as mock_del:
        result = runner.invoke(app, ["delete", "dp-999", "--yes"])
        assert result.exit_code == 0
        assert "Successfully deleted meal" in result.stdout
        assert "dp-999" in result.stdout
        mock_del.assert_called_once_with("dp-999")


def test_cli_delete_cancelled(temp_config_dir: Path):
    with patch("nutrilog.cli.GoogleHealthClient.delete_meal") as mock_del:
        result = runner.invoke(app, ["delete", "dp-999"], input="n\n")
        assert result.exit_code == 0
        assert "cancelled" in result.stdout
        mock_del.assert_not_called()



def test_cli_auth_status_and_logout(temp_config_dir: Path):
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "Nutrilog Authentication Status" in result.stdout

    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert "signed out" in result.stdout or "No active session" in result.stdout


def test_cli_auth_login_remote(temp_config_dir: Path):
    with patch("nutrilog.auth.login_remote") as mock_login_remote:
        result = runner.invoke(app, ["auth", "login", "--remote"])
        assert result.exit_code == 0
        assert "Remote SSH Mode" in result.stdout
        mock_login_remote.assert_called_once()


def test_cli_config_commands(temp_config_dir: Path):
    result = runner.invoke(app, ["config", "set", "--timezone", "Australia/Sydney"])
    assert result.exit_code == 0
    stdout_clean = " ".join(result.stdout.split())
    assert "Timezone set to 'Australia/Sydney'" in stdout_clean

    result_show = runner.invoke(app, ["config", "show"])
    assert result_show.exit_code == 0
    show_clean = " ".join(result_show.stdout.split())
    assert "Australia/Sydney" in show_clean

    # Test reset to auto
    result_reset = runner.invoke(app, ["config", "set", "--timezone", "auto"])
    assert result_reset.exit_code == 0
    assert "reset to machine system local" in " ".join(result_reset.stdout.split())

    # Test invalid timezone error
    result_invalid = runner.invoke(app, ["config", "set", "--timezone", "Not/A/Valid/Timezone"])
    assert result_invalid.exit_code == 1
    assert "Invalid timezone" in result_invalid.output


def _fiber_meal(point_id: str) -> MealLog:
    return MealLog(
        id=point_id,
        foodDisplayName="Test",
        mealType=MealType.LUNCH,
        interval=TimeInterval(startTime="2026-08-18T12:00:00Z", endTime="2026-08-18T12:01:00Z"),
        energy=Energy(kcal=236),
        totalCarbohydrate=GramsQuantity(grams=7.7),
        totalFat=GramsQuantity(grams=8.3),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=20)),
            NutrientEntry(nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=1.9)),
        ],
    )


def test_cli_log_fiber_uses_dietary_fiber_enum(temp_config_dir: Path):
    """`--fiber` must serialize to the only fibre value the v4 API accepts."""
    with patch("nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m) as mock_log:
        result = runner.invoke(
            app,
            ["log", "Test", "-p", "20", "-k", "236", "-c", "7.7", "-f", "8.3", "--fiber", "1.9"],
        )
    assert result.exit_code == 0
    sent = mock_log.call_args.args[0].to_api_payload()["nutritionLog"]["nutrients"]
    assert {"nutrient": "DIETARY_FIBER", "quantity": {"grams": 1.9}} in sent


def test_cli_history_shows_fiber(temp_config_dir: Path):
    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[_fiber_meal("meal-fib")]):
        result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "Fiber" in result.stdout
        assert "1.9g" in result.stdout


def test_cli_history_json_includes_fiber(temp_config_dir: Path):
    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[_fiber_meal("meal-fib")]):
        result = runner.invoke(app, ["history", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["summary"]["total_fiber"] == 1.9
        assert parsed["meals"][0]["fiber_g"] == 1.9


def _sent_nutrients(mock_log) -> list[dict]:
    """Nutrients as serialized for the API by the last log_meal call."""
    return mock_log.call_args.args[0].to_api_payload()["nutritionLog"]["nutrients"]


def test_cli_log_sugar_saturated_fat_and_sodium_flags(temp_config_dir: Path):
    """Sugar, saturated fat and sodium must be loggable via flags."""
    with patch("nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m) as mock_log:
        result = runner.invoke(
            app,
            ["log", "Musashi bar", "-p", "20", "-k", "236", "-c", "7.7", "-f", "8.3",
             "--fiber", "1.9", "--sugar", "3.7", "--saturated-fat", "4.4", "--sodium", "242"],
        )
    assert result.exit_code == 0, result.output
    sent = _sent_nutrients(mock_log)
    assert {"nutrient": "SUGAR", "quantity": {"grams": 3.7}} in sent
    assert {"nutrient": "SATURATED_FAT", "quantity": {"grams": 4.4}} in sent
    # --sodium is milligrams (as labels state it); the API field is grams.
    assert {"nutrient": "SODIUM", "quantity": {"grams": 0.242}} in sent


def test_cli_log_shorthand_sugar_and_sodium_are_not_dropped(temp_config_dir: Path):
    """Regression: the CLI path used to discard shorthand-parsed sugar and sodium."""
    with patch("nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m) as mock_log:
        result = runner.invoke(app, ["log", "20p 236k 3.7sug 242sod Test bar"])
    assert result.exit_code == 0, result.output
    sent = _sent_nutrients(mock_log)
    assert {"nutrient": "SUGAR", "quantity": {"grams": 3.7}} in sent
    assert {"nutrient": "SODIUM", "quantity": {"grams": 0.242}} in sent


def test_cli_history_json_includes_new_nutrients(temp_config_dir: Path):
    """history --json must expose every nutrient nutrilog can record."""
    meal = MealLog(
        foodDisplayName="Musashi bar",
        mealType=MealType.SNACK,
        interval=TimeInterval.from_datetimes(__import__("datetime").datetime.now().astimezone()),
        energy=Energy(kcal=236),
        totalCarbohydrate=GramsQuantity(grams=7.7),
        totalFat=GramsQuantity(grams=8.3),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=20)),
            NutrientEntry(nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=1.9)),
            NutrientEntry(nutrient="SUGAR", quantity=GramsQuantity(grams=3.7)),
            NutrientEntry(nutrient="SATURATED_FAT", quantity=GramsQuantity(grams=4.4)),
            NutrientEntry(nutrient="SODIUM", quantity=GramsQuantity(grams=0.242)),
        ],
    )
    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[meal]):
        result = runner.invoke(app, ["history", "--json"])
    assert result.exit_code == 0, result.output
    entry = json.loads(result.stdout)["meals"][0]
    assert entry["fiber_g"] == 1.9
    assert entry["sugar_g"] == 3.7
    assert entry["saturated_fat_g"] == 4.4
    assert entry["sodium_mg"] == 242.0
