"""Unit tests for nutrilog.cli."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner

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
    assert "0.1.5" in result.stdout


def test_cli_dry_run_explicit_log_command(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "38p 18f 54c 580k Tofu Soba Bowl", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.stdout
    assert "Tofu Soba Bowl" in result.stdout
    assert "38.0g" in result.stdout
    assert "580 kcal" in result.stdout


def test_cli_dry_run_implicit_shorthand(temp_config_dir: Path):
    result = runner.invoke(app, ["38p 18f 54c 580k Tofu Soba Bowl", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry Run" in result.stdout
    assert "Tofu Soba Bowl" in result.stdout
    assert "38.0g" in result.stdout
    assert "580 kcal" in result.stdout


def test_cli_json_output(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "30p 400k Protein Shake", "--json"])
    assert result.exit_code == 0
    parsed_json = json.loads(result.stdout)
    assert "nutritionLog" in parsed_json
    log = parsed_json["nutritionLog"]
    assert log["foodDisplayName"] == "Protein Shake"
    assert log["energy"]["kcal"] == 400.0


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


def test_cli_quick_command(temp_config_dir: Path):
    result = runner.invoke(
        app,
        ["quick", "--protein", "25", "--calories", "180", "--name", "Post-Workout", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "Post-Workout" in result.stdout
    assert "25.0g" in result.stdout
    assert "180 kcal" in result.stdout


def test_cli_today_command(temp_config_dir: Path):
    sample_meal = MealLog(
        id="meal-1",
        foodDisplayName="Chicken Rice",
        mealType=MealType.LUNCH,
        interval=TimeInterval(startTime="2026-08-17T12:30:00Z", endTime="2026-08-17T12:30:00Z"),
        energy=Energy(kcal=650),
        totalCarbohydrate=GramsQuantity(grams=70),
        totalFat=GramsQuantity(grams=15),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=45))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.get_today_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["today"])
        assert result.exit_code == 0
        assert "Today's Nutrition Summary" in result.stdout
        assert "Chicken Rice" in result.stdout
        assert "45.0g" in result.stdout
        assert "650 kcal" in result.stdout


def test_cli_default_no_args_shows_today(temp_config_dir: Path):
    with patch("nutrilog.cli.GoogleHealthClient.get_today_meals", return_value=[]):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Today's Nutrition Summary" in result.stdout
        assert "No meals logged" in result.stdout


def test_cli_history_command(temp_config_dir: Path):
    sample_meal = MealLog(
        id="meal-2",
        foodDisplayName="Oats",
        mealType=MealType.BREAKFAST,
        interval=TimeInterval(startTime="2026-08-16T08:30:00Z", endTime="2026-08-16T08:30:00Z"),
        energy=Energy(kcal=350),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=20))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["history", "--days", "3", "--ids"])
        assert result.exit_code == 0
        assert "Meal History" in result.stdout
        assert "Oats" in result.stdout
        assert "meal-2" in result.stdout


def test_cli_list_command(temp_config_dir: Path):
    sample_meal = MealLog(
        id="dp-999",
        foodDisplayName="Protein Shake",
        mealType=MealType.SNACK,
        interval=TimeInterval(startTime="2026-08-17T15:00:00Z", endTime="2026-08-17T15:00:00Z"),
        energy=Energy(kcal=200),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=30))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["list", "--days", "2"])
        assert result.exit_code == 0
        assert "Logged Meals" in result.stdout
        assert "dp-999" in result.stdout
        assert "Protein" in result.stdout


def test_cli_list_json(temp_config_dir: Path):
    sample_meal = MealLog(
        id="dp-999",
        foodDisplayName="Protein Shake",
        mealType=MealType.SNACK,
        interval=TimeInterval(startTime="2026-08-17T15:00:00Z", endTime="2026-08-17T15:00:00Z"),
        energy=Energy(kcal=200),
        nutrients=[NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=30))],
    )

    with patch("nutrilog.cli.GoogleHealthClient.list_meals", return_value=[sample_meal]):
        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert len(parsed) == 1
        assert parsed[0]["nutritionLog"]["foodDisplayName"] == "Protein Shake"


def test_cli_delete_command(temp_config_dir: Path):
    with patch("nutrilog.cli.GoogleHealthClient.delete_meal", return_value=True) as mock_del:
        result = runner.invoke(app, ["delete", "dp-999", "--yes"])
        assert result.exit_code == 0
        assert "Successfully deleted meal dp-999" in result.stdout
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


def test_cli_auth_setup_with_flags(temp_config_dir: Path):
    result = runner.invoke(
        app,
        ["auth", "setup", "--client-id", "my-client-id", "--client-secret", "my-secret"],
    )
    assert result.exit_code == 0
    assert "Saved client credentials successfully" in result.stdout


def test_cli_auth_setup_with_file(temp_config_dir: Path, tmp_path: Path):
    creds_file = tmp_path / "client_secrets.json"
    creds_file.write_text(
        json.dumps({"installed": {"client_id": "file-id", "client_secret": "file-sec"}}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["auth", "setup", "--file", str(creds_file)])
    assert result.exit_code == 0
    assert "Saved client credentials from" in result.stdout


def test_cli_auth_login_remote(temp_config_dir: Path):
    with patch("nutrilog.auth.login_remote") as mock_login_remote:
        result = runner.invoke(app, ["auth", "login", "--remote"])
        assert result.exit_code == 0
        assert "Remote SSH Mode" in result.stdout
        mock_login_remote.assert_called_once()


def test_cli_config_commands(temp_config_dir: Path):
    result = runner.invoke(app, ["config", "set", "--calories", "2300", "--protein", "150"])
    assert result.exit_code == 0
    assert "2300 kcal" in result.stdout
    assert "150.0g protein" in result.stdout

    result_show = runner.invoke(app, ["config", "show"])
    assert result_show.exit_code == 0
    assert "2300 kcal" in result_show.stdout
    assert "150.0 g" in result_show.stdout
