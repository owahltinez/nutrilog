"""Unit tests for nutrilog.cli."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import click
from click.testing import CliRunner

from nutrilog import __version__
from nutrilog.client import GoogleHealthError
from nutrilog.cli import app
from nutrilog.models import (
    Energy,
    GramsQuantity,
    MealLog,
    MealType,
    NutrientEntry,
    Serving,
    TimeInterval,
)
from nutrilog.storage import ENV_CONFIG_DIR

runner = CliRunner()


def json_data(result):
    """Return data from agentcli's successful JSON envelope."""
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    return payload["data"]


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


def test_cli_is_click_and_uses_agentcli_error_contract():
    assert isinstance(app, click.Group)

    result = runner.invoke(app, ["log", "Snack", "--unknown", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": {"message": "No such option '--unknown'."},
    }


def test_cli_no_args_shows_help(temp_config_dir: Path):
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout or "help" in result.stdout.lower()


def test_cli_dry_run_explicit_log_command(temp_config_dir: Path):
    result = runner.invoke(
        app, ["log", "38p 18f 54c 580k Tofu Soba Bowl", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "Dry Run" in result.stdout
    assert "Tofu Soba Bowl" in result.stdout
    assert "38.0g" in result.stdout
    assert "580 kcal" in result.stdout


def test_cli_json_output(temp_config_dir: Path):
    result = runner.invoke(
        app, ["log", "30p 400k Protein Shake", "--dry-run", "--json"]
    )
    assert result.exit_code == 0
    parsed_json = json_data(result)
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
        interval=TimeInterval(
            startTime="2026-08-18T12:30:00Z", endTime="2026-08-18T12:30:00Z"
        ),
        energy=Energy(kcal=650),
        totalCarbohydrate=GramsQuantity(grams=70),
        totalFat=GramsQuantity(grams=15),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=45))
        ],
    )

    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[sample_meal],
    ):
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
        interval=TimeInterval(
            startTime="2026-08-17T08:30:00Z", endTime="2026-08-17T08:30:00Z"
        ),
        energy=Energy(kcal=350),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=20))
        ],
    )

    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[sample_meal],
    ):
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
        interval=TimeInterval(
            startTime="2026-08-16T19:00:00Z", endTime="2026-08-16T19:00:00Z"
        ),
        energy=Energy(kcal=400),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=30))
        ],
    )

    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[sample_meal],
    ):
        result = runner.invoke(app, ["history", "--days", "7"])
        assert result.exit_code == 0
        assert "Meal History (Past 7 Days)" in result.stdout
        assert "Tofu" in result.stdout


def test_cli_history_json(temp_config_dir: Path):
    sample_meal = MealLog(
        id="dp-999",
        foodDisplayName="Protein Shake",
        mealType=MealType.SNACK,
        interval=TimeInterval(
            startTime="2026-08-18T15:00:00Z", endTime="2026-08-18T15:00:00Z"
        ),
        energy=Energy(kcal=200),
        nutrients=[
            NutrientEntry(nutrient="PROTEIN", quantity=GramsQuantity(grams=30))
        ],
    )

    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[sample_meal],
    ):
        result = runner.invoke(app, ["history", "--json"])
        assert result.exit_code == 0
        parsed = json_data(result)
        assert "summary" in parsed
        assert "meals" in parsed
        assert parsed["summary"]["total_protein"] == 30.0
        assert parsed["summary"]["total_calories"] == 200.0
        assert len(parsed["meals"]) == 1
        assert parsed["meals"][0]["name"] == "Protein Shake"


def test_cli_history_json_reports_remote_error(temp_config_dir: Path):
    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        side_effect=GoogleHealthError("service unavailable"),
    ):
        result = runner.invoke(app, ["history", "--json"])

    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": {"message": "Failed to fetch history: service unavailable"},
    }


def _copy_source() -> MealLog:
    return MealLog(
        id="source-123",
        foodDisplayName="Pasta Dinner",
        mealType=MealType.DINNER,
        interval=TimeInterval(
            startTime="2026-08-18T19:00:00+10:00",
            endTime="2026-08-18T19:01:00+10:00",
            startUtcOffset="36000s",
            endUtcOffset="36000s",
        ),
        energy=Energy(kcal=700),
        totalCarbohydrate=GramsQuantity(grams=65),
        totalFat=GramsQuantity(grams=21),
        nutrients=[
            NutrientEntry(
                nutrient="PROTEIN", quantity=GramsQuantity(grams=42)
            ),
            NutrientEntry(
                nutrient="DIETARY_FIBER",
                quantity=GramsQuantity(grams=8.5, userProvidedUnit="GRAM"),
            ),
            NutrientEntry(
                nutrient="SODIUM",
                quantity=GramsQuantity(
                    grams=0.72, userProvidedUnit="MILLIGRAM"
                ),
            ),
        ],
        serving=Serving(amount=1, unit="meal"),
    )


def test_cli_copy_preserves_source_and_all_nutrition(temp_config_dir: Path):
    source = _copy_source()
    source_before = source.model_dump()
    saved = None

    def save_copy(meal: MealLog) -> MealLog:
        nonlocal saved
        saved = meal
        return meal.model_copy(update={"id": "copy-456"})

    with (
        patch(
            "nutrilog.cli.GoogleHealthClient.get_meal",
            return_value=source,
        ) as mock_get,
        patch(
            "nutrilog.cli.GoogleHealthClient.log_meal",
            side_effect=save_copy,
        ) as mock_log,
    ):
        result = runner.invoke(
            app,
            [
                "copy",
                "source-123",
                "--time",
                "2026-08-19T20:15:00+10:00",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Successfully Copied" in result.stdout
    assert "copy-456" in result.stdout
    mock_get.assert_called_once_with("source-123")
    mock_log.assert_called_once()
    assert saved is not None
    assert saved.id is None
    assert saved.interval.startTime == "2026-08-19T20:15:00+10:00"
    assert saved.model_dump(exclude={"id", "interval"}) == source.model_dump(
        exclude={"id", "interval"}
    )
    assert source.model_dump() == source_before


def test_cli_copy_defaults_to_now_and_supports_overrides(
    temp_config_dir: Path,
):
    source = _copy_source()
    current_time = datetime(
        2026, 8, 19, 21, 30, tzinfo=timezone(timedelta(hours=10))
    )

    with (
        patch(
            "nutrilog.cli.GoogleHealthClient.get_meal",
            return_value=source,
        ),
        patch("nutrilog.cli.GoogleHealthClient.log_meal") as mock_log,
        patch("nutrilog.cli.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = current_time
        mock_log.side_effect = lambda meal: meal
        result = runner.invoke(
            app,
            [
                "copy",
                "source-123",
                "--name",
                "Late Pasta",
                "--meal",
                "snack",
            ],
        )

    assert result.exit_code == 0, result.output
    copied = mock_log.call_args.args[0]
    assert copied.foodDisplayName == "Late Pasta"
    assert copied.mealType == MealType.SNACK
    assert copied.interval.startTime == "2026-08-19T21:30:00+10:00"


def test_cli_copy_dry_run_does_not_create_a_point(temp_config_dir: Path):
    source = _copy_source()

    with (
        patch(
            "nutrilog.cli.GoogleHealthClient.get_meal",
            return_value=source,
        ),
        patch("nutrilog.cli.GoogleHealthClient.log_meal") as mock_log,
    ):
        result = runner.invoke(
            app,
            [
                "copy",
                "source-123",
                "--time",
                "2026-08-19T20:15:00+10:00",
                "--dry-run",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    copied = json_data(result)
    assert copied["id"] is None
    assert copied["time"] == "2026-08-19T20:15:00+10:00"
    assert copied["name"] == "Pasta Dinner"
    assert copied["nutrients"] == {
        "DIETARY_FIBER": 8.5,
        "SODIUM": 0.72,
    }
    mock_log.assert_not_called()


def test_cli_delete_command(temp_config_dir: Path):
    with patch(
        "nutrilog.cli.GoogleHealthClient.delete_meal", return_value=True
    ) as mock_del:
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


def test_cli_rm_alias(temp_config_dir: Path):
    with patch(
        "nutrilog.cli.GoogleHealthClient.delete_meal", return_value=True
    ) as mock_delete:
        result = runner.invoke(app, ["rm", "dp-999", "--yes"])

    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once_with("dp-999")


def test_cli_auth_status_and_logout(temp_config_dir: Path):
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "Nutrilog Authentication Status" in result.stdout

    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert (
        "signed out" in result.stdout or "No active session" in result.stdout
    )


def test_cli_auth_login_remote(temp_config_dir: Path):
    with patch("nutrilog.auth.login_remote") as mock_login_remote:
        result = runner.invoke(app, ["auth", "login", "--remote"])
        assert result.exit_code == 0
        assert "Remote SSH Mode" in result.stdout
        mock_login_remote.assert_called_once()


def test_cli_config_commands(temp_config_dir: Path):
    result = runner.invoke(
        app, ["config", "set", "--timezone", "Australia/Sydney"]
    )
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
    assert "reset to machine system local" in " ".join(
        result_reset.stdout.split()
    )

    # Test invalid timezone error
    result_invalid = runner.invoke(
        app, ["config", "set", "--timezone", "Not/A/Valid/Timezone"]
    )
    assert result_invalid.exit_code == 1
    assert "Invalid timezone" in result_invalid.output


def _fiber_meal(point_id: str) -> MealLog:
    return MealLog(
        id=point_id,
        foodDisplayName="Test",
        mealType=MealType.LUNCH,
        interval=TimeInterval(
            startTime="2026-08-18T12:00:00Z", endTime="2026-08-18T12:01:00Z"
        ),
        energy=Energy(kcal=236),
        totalCarbohydrate=GramsQuantity(grams=7.7),
        totalFat=GramsQuantity(grams=8.3),
        nutrients=[
            NutrientEntry(
                nutrient="PROTEIN", quantity=GramsQuantity(grams=20)
            ),
            NutrientEntry(
                nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=1.9)
            ),
        ],
    )


def test_cli_log_fiber_uses_dietary_fiber_enum(temp_config_dir: Path):
    """Everyday "fiber" must become the only fibre value v4 accepts."""
    with patch(
        "nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m
    ) as mock_log:
        result = runner.invoke(
            app,
            [
                "log",
                "Test",
                "-p",
                "20",
                "-k",
                "236",
                "-c",
                "7.7",
                "-f",
                "8.3",
                "-n",
                "fiber=1.9g",
            ],
        )
    assert result.exit_code == 0, result.output
    sent = mock_log.call_args.args[0].to_api_payload()["nutritionLog"][
        "nutrients"
    ]
    assert {
        "nutrient": "DIETARY_FIBER",
        "quantity": {"grams": 1.9, "userProvidedUnit": "GRAM"},
    } in sent


def test_cli_history_totals_show_nutrients_beyond_the_macros(
    temp_config_dir: Path,
):
    """The table keeps 4 macro columns; tail is summarised underneath."""
    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[_fiber_meal("meal-fib")],
    ):
        result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "Fiber" in result.stdout
        assert "1.9g" in result.stdout


def test_cli_history_json_includes_fiber(temp_config_dir: Path):
    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[_fiber_meal("meal-fib")],
    ):
        result = runner.invoke(app, ["history", "--json"])
        assert result.exit_code == 0
        parsed = json_data(result)
        assert parsed["summary"]["nutrient_totals"]["DIETARY_FIBER"] == 1.9
        assert parsed["meals"][0]["nutrients"]["DIETARY_FIBER"] == 1.9


def _sent_nutrients(mock_log) -> list[dict]:
    """Nutrients as serialized for the API by the last log_meal call."""
    return mock_log.call_args.args[0].to_api_payload()["nutritionLog"][
        "nutrients"
    ]


def test_cli_log_several_nutrients_via_flags(temp_config_dir: Path):
    """One repeatable flag covers what four dedicated ones used to."""
    with patch(
        "nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m
    ) as mock_log:
        result = runner.invoke(
            app,
            [
                "log",
                "Musashi bar",
                "-p",
                "20",
                "-k",
                "236",
                "-c",
                "7.7",
                "-f",
                "8.3",
                "-n",
                "fiber=1.9g",
                "-n",
                "sugar=3.7g",
                "-n",
                "saturated fat=4.4g",
                "-n",
                "sodium=242mg",
            ],
        )
    assert result.exit_code == 0, result.output
    sent = {
        e["nutrient"]: e["quantity"]["grams"]
        for e in _sent_nutrients(mock_log)
    }
    assert sent["SUGAR"] == 3.7
    assert sent["SATURATED_FAT"] == 4.4
    # Sodium is written in milligrams; the API field is grams.
    assert sent["SODIUM"] == 0.242


def test_cli_log_shorthand_nutrients_are_not_dropped(temp_config_dir: Path):
    """Regression: the CLI path used to discard shorthand-parsed nutrients."""
    with patch(
        "nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m
    ) as mock_log:
        result = runner.invoke(
            app, ["log", "20p 236k sugar: 3.7g sodium: 242mg Test bar"]
        )
    assert result.exit_code == 0, result.output
    sent = {
        e["nutrient"]: e["quantity"]["grams"]
        for e in _sent_nutrients(mock_log)
    }
    assert sent["SUGAR"] == 3.7
    assert sent["SODIUM"] == 0.242


def test_cli_history_json_includes_new_nutrients(temp_config_dir: Path):
    """history --json must expose every nutrient nutrilog can record."""
    meal = MealLog(
        foodDisplayName="Musashi bar",
        mealType=MealType.SNACK,
        interval=TimeInterval.from_datetimes(
            __import__("datetime").datetime.now().astimezone()
        ),
        energy=Energy(kcal=236),
        totalCarbohydrate=GramsQuantity(grams=7.7),
        totalFat=GramsQuantity(grams=8.3),
        nutrients=[
            NutrientEntry(
                nutrient="PROTEIN", quantity=GramsQuantity(grams=20)
            ),
            NutrientEntry(
                nutrient="DIETARY_FIBER", quantity=GramsQuantity(grams=1.9)
            ),
            NutrientEntry(nutrient="SUGAR", quantity=GramsQuantity(grams=3.7)),
            NutrientEntry(
                nutrient="SATURATED_FAT", quantity=GramsQuantity(grams=4.4)
            ),
            NutrientEntry(
                nutrient="SODIUM", quantity=GramsQuantity(grams=0.242)
            ),
        ],
    )
    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals", return_value=[meal]
    ):
        result = runner.invoke(app, ["history", "--json"])
    assert result.exit_code == 0, result.output
    entry = json_data(result)["meals"][0]
    assert entry["nutrients"] == {
        "DIETARY_FIBER": 1.9,
        "SUGAR": 3.7,
        "SATURATED_FAT": 4.4,
        "SODIUM": 0.242,
    }


def test_cli_log_arbitrary_nutrient_flag(temp_config_dir: Path):
    """Caffeine is loggable without a dedicated flag."""
    with patch(
        "nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m
    ) as mock_log:
        result = runner.invoke(
            app, ["log", "Oat Cortado", "-n", "caffeine=95mg"]
        )

    assert result.exit_code == 0, result.output
    assert {
        "nutrient": "CAFFEINE",
        "quantity": {"grams": 0.095, "userProvidedUnit": "MILLIGRAM"},
    } in _sent_nutrients(mock_log)


def test_cli_nutrient_flag_is_repeatable(temp_config_dir: Path):
    with patch(
        "nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m
    ) as mock_log:
        result = runner.invoke(
            app,
            [
                "log",
                "Supplement",
                "-n",
                "magnesium=60mg",
                "-n",
                "vitamin b12=2.4µg",
            ],
        )

    assert result.exit_code == 0, result.output
    sent = {e["nutrient"] for e in _sent_nutrients(mock_log)}
    assert {"MAGNESIUM", "VITAMIN_B12"} <= sent


def test_cli_nutrient_flag_rejects_unknown_nutrient(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "Snack", "-n", "unobtainium=5g"])

    assert result.exit_code == 1
    assert "unobtainium" in result.output


def test_cli_nutrient_flag_rejects_missing_unit(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "Snack", "-n", "caffeine=95"])

    assert result.exit_code == 1
    assert "unit" in result.output.lower()


def test_cli_nutrient_flag_rejects_malformed_pair(temp_config_dir: Path):
    result = runner.invoke(app, ["log", "Snack", "-n", "caffeine"])

    assert result.exit_code == 1
    assert "caffeine" in result.output


def test_cli_per_nutrient_flags_are_gone(temp_config_dir: Path):
    """Replaced by -n; a stale flag must fail loudly rather than be ignored."""
    for flag in ("--sodium", "--sugar", "--saturated-fat", "--fiber"):
        result = runner.invoke(app, ["log", "Snack", flag, "5"])
        assert result.exit_code != 0, f"{flag} still accepted"


def test_cli_log_reports_shorthand_unit_errors(temp_config_dir: Path):
    """A nutrient without a unit stops the log instead of guessing."""
    result = runner.invoke(app, ["log", "Eggs sodium: 450"])

    assert result.exit_code == 1
    assert "unit" in result.output.lower()


def test_cli_log_warns_about_unclaimed_weights(temp_config_dir: Path):
    with patch(
        "nutrilog.cli.GoogleHealthClient.log_meal", side_effect=lambda m: m
    ):
        result = runner.invoke(app, ["log", "Eggs 450mg"])

    assert result.exit_code == 0, result.output
    assert "450mg" in result.output


def test_cli_json_output_lists_nutrients_generically(temp_config_dir: Path):
    result = runner.invoke(
        app,
        ["log", "Oat Cortado", "-n", "caffeine=95mg", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json_data(result)
    assert payload["nutrients"]["CAFFEINE"] == 0.095


def test_cli_history_json_totals_nutrients_generically(temp_config_dir: Path):
    meal = MealLog(
        foodDisplayName="Oat Cortado",
        mealType=MealType.BREAKFAST,
        interval=TimeInterval(
            startTime="2026-08-19T09:30:00Z", endTime="2026-08-19T09:31:00Z"
        ),
        energy=Energy(kcal=35),
        nutrients=[
            NutrientEntry(
                nutrient="CAFFEINE", quantity=GramsQuantity(grams=0.095)
            ),
        ],
    )
    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals", return_value=[meal]
    ):
        result = runner.invoke(app, ["history", "--json"])

    assert result.exit_code == 0, result.output
    payload = json_data(result)
    assert payload["summary"]["nutrient_totals"]["CAFFEINE"] == 0.095
    assert payload["meals"][0]["nutrients"]["CAFFEINE"] == 0.095


def test_cli_nutrients_command_lists_loggable_names(temp_config_dir: Path):
    """With names replacing flags, the list must be discoverable."""
    result = runner.invoke(app, ["nutrients"])

    assert result.exit_code == 0, result.output
    assert "caffeine" in result.output.lower()
    assert "vitamin b12" in result.output.lower()


def test_cli_nutrients_command_shows_the_macro_shorthand(
    temp_config_dir: Path,
):
    result = runner.invoke(app, ["nutrients"])

    assert "protein" in result.output.lower()
    assert "-p" in result.output


def _late_evening_meal() -> MealLog:
    """A meal at 10pm Sydney, which is the *previous* day in UTC.

    12:00Z on the 20th is 22:00+10:00 on the 20th. Any renderer that leaks
    UTC into a local-day view puts this meal on the wrong calendar day.
    """
    return MealLog(
        id="dp-tz",
        foodDisplayName="Orange Juice",
        mealType=MealType.SNACK,
        interval=TimeInterval(
            startTime="2026-08-20T12:00:00Z", endTime="2026-08-20T12:00:00Z"
        ),
        energy=Energy(kcal=45),
    )


def test_history_json_reports_meal_times_in_the_configured_zone(
    temp_config_dir: Path,
) -> None:
    """One payload, one convention: meals must match start_time and end_time.

    Emitting the window in local time and the meals in UTC invites a reader
    to compare them directly and land on the wrong day.
    """
    runner.invoke(app, ["config", "set", "--timezone", "Australia/Sydney"])

    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[_late_evening_meal()],
    ):
        parsed = json_data(runner.invoke(app, ["history", "--json"]))

    time = parsed["meals"][0]["time"]
    assert time == "2026-08-20T22:00:00+10:00"
    # The instant is unchanged; only how it is written.
    assert datetime.fromisoformat(time) == datetime.fromisoformat(
        "2026-08-20T12:00:00+00:00"
    )
    # Same offset as the window it sits inside.
    assert time[-6:] == parsed["start_time"][-6:]


def test_log_and_history_agree_on_timestamp_format(
    temp_config_dir: Path,
) -> None:
    """A meal must not change shape between being logged and being read."""
    runner.invoke(app, ["config", "set", "--timezone", "Australia/Sydney"])

    logged = json_data(
        runner.invoke(
            app,
            ["log", "probe", "-k", "1", "-t", "10pm", "--dry-run", "--json"],
        )
    )
    with patch(
        "nutrilog.cli.GoogleHealthClient.list_meals",
        return_value=[_late_evening_meal()],
    ):
        read = json_data(runner.invoke(app, ["history", "--json"]))

    assert logged["time"][-6:] == read["meals"][0]["time"][-6:]
