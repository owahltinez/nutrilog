"""Click command-line interface for Nutrilog."""

import re
from datetime import datetime, time, timedelta, timezone, tzinfo
from pathlib import Path

import click
from agentcli import (
    JsonAwareGroup,
    RemoteError,
    UsageError,
    emit,
    json_option,
    skill_group,
)
from dateutil import parser as date_parser

from nutrilog import __version__, auth
from nutrilog.client import GoogleHealthClient, GoogleHealthError
from nutrilog.models import (
    GramsQuantity,
    MacroSummary,
    MealLog,
    MealType,
    NutrientEntry,
    NutrientType,
    TimeInterval,
)
from nutrilog.parser import (
    MACRO_NUTRIENTS as _MACRO_NUTRIENTS,
)
from nutrilog.parser import (
    ParsedMacros,
    ParseError,
    infer_meal_type,
    parse_shorthand,
    parse_time_str,
)
from nutrilog.storage import (
    get_config_dir,
    get_configured_timezone_name,
    get_machine_timezone,
    get_user_timezone,
    set_user_timezone,
)
from nutrilog.units import UnknownUnitError, format_grams, parse_weight


def date_parser_iso(s: str) -> datetime:
    """Parse an ISO date/time string into a datetime object."""
    return date_parser.parse(s)


def resolve_date_range(
    date_str: str | None = None,
    days: int | None = None,
    tz: tzinfo = timezone.utc,
) -> tuple[datetime, datetime, str]:
    """Resolve start/end datetime boundaries and title label for queries."""
    today = datetime.now(tz).date()
    if days is not None:
        days_count = max(1, days)
        start_date = today - timedelta(days=days_count - 1)
        start_dt = datetime.combine(start_date, time.min, tzinfo=tz)
        end_dt = datetime.combine(today, time.max, tzinfo=tz)
        title_label = f"Past {days_count} Days" if days_count > 1 else "Today"
        return start_dt, end_dt, title_label

    if date_str:
        s = date_str.strip().lower()
        if s in ("today", "t"):
            target_date = today
            title_label = "Today"
        elif s in ("yesterday", "y"):
            target_date = today - timedelta(days=1)
            title_label = "Yesterday"
        else:
            target_date = date_parser_iso(date_str).date()
            title_label = target_date.strftime("%a, %b %d")
        start_dt = datetime.combine(target_date, time.min, tzinfo=tz)
        end_dt = datetime.combine(target_date, time.max, tzinfo=tz)
        return start_dt, end_dt, title_label

    # Default: today
    start_dt = datetime.combine(today, time.min, tzinfo=tz)
    end_dt = datetime.combine(today, time.max, tzinfo=tz)
    return start_dt, end_dt, "Today"


# Splits "caffeine=95mg" into its name, number and unit.
_NUTRIENT_ARG = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 \-_]*?)\s*[=:]\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*(\S*)\s*$"
)


def parse_nutrient_args(
    values: list[str] | None,
) -> dict[NutrientType, GramsQuantity]:
    """Turn repeated --nutrient arguments into quantities.

    Anything unclear is rejected rather than guessed at.
    """
    parsed: dict[NutrientType, GramsQuantity] = {}
    for raw in values or []:
        match = _NUTRIENT_ARG.match(raw)
        if not match:
            raise ParseError(
                f"Could not read {raw!r}: write it as --nutrient caffeine=95mg."
            )

        name, amount, unit = match.groups()
        nutrient = NutrientType.from_string(name)
        if nutrient is None:
            raise ParseError(
                f"Unknown nutrient {name!r}. "
                "Run 'nutrilog nutrients' to list them."
            )

        try:
            grams, resolved = parse_weight(float(amount), unit)
        except UnknownUnitError as exc:
            raise ParseError(f"{name}: {exc}") from exc
        parsed[nutrient] = GramsQuantity(
            grams=grams, userProvidedUnit=resolved
        )
    return parsed


def _extra_nutrients(meal: MealLog) -> list[NutrientEntry]:
    """Recorded nutrients other than protein, which has its own field."""
    return [
        e
        for e in meal.nutrients
        if e.nutrient.upper() != NutrientType.PROTEIN.value
    ]


def _describe_nutrients(meal: MealLog) -> dict[str, str]:
    """Every recorded nutrient, rendered for a human in a legible unit."""
    return {
        e.nutrient.upper(): format_grams(
            e.quantity.grams, e.quantity.userProvidedUnit
        )
        for e in _extra_nutrients(meal)
    }


def _nutrient_grams(meal: MealLog) -> dict[str, float]:
    """Every recorded nutrient in grams, for JSON consumers.

    Grams rather than formatted strings so callers never have to parse
    "2.4µg", and so this matches the units used by the summary totals.
    """
    return {
        e.nutrient.upper(): e.quantity.grams for e in _extra_nutrients(meal)
    }


def _meal_time(meal: MealLog, tz: tzinfo) -> str:
    """The meal's start time written in `tz`, as an ISO 8601 instant.

    The stored string is whatever produced it: a freshly built meal carries
    the local offset it was parsed from, one read back from the API carries
    UTC. Normalising here is what keeps a payload to a single convention, so
    a reader can compare a meal against the window it sits inside without
    converting anything. The instant never changes -- only how it is written.
    """
    try:
        return (
            date_parser_iso(meal.interval.startTime).astimezone(tz).isoformat()
        )
    except (ValueError, TypeError):
        # An unparseable timestamp is passed through rather than dropped: a
        # wrong-looking time is debuggable, a missing one is not.
        return meal.interval.startTime


def _meal_json(meal: MealLog, tz: tzinfo | None = None) -> dict[str, object]:
    """Render one meal consistently for machine-readable output."""
    return {
        "id": meal.id,
        "time": _meal_time(meal, tz or get_user_timezone()),
        "meal_type": meal.mealType.value,
        "name": meal.foodDisplayName,
        "protein_g": meal.protein_g,
        "calories_kcal": meal.calories_kcal,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "nutrients": _nutrient_grams(meal),
    }


def _render_meal_panel(
    meal: MealLog,
    title: str = "Logged to Google Health",
    tz: tzinfo | None = None,
) -> None:
    active_tz = tz or get_user_timezone()
    try:
        dt_parsed = date_parser_iso(meal.interval.startTime).astimezone(
            active_tz
        )
        time_display = dt_parsed.strftime("%Y-%m-%d %I:%M %p")
    except Exception:
        time_display = meal.interval.startTime

    lines = [
        f"Food: {meal.foodDisplayName}",
        f"Meal: {meal.mealType.value.capitalize()}",
        f"Time: {time_display}",
        (
            f"Protein: {meal.protein_g:.1f}g    Calories: "
            f"{meal.calories_kcal:.0f} kcal    "
            f"Carbs: {meal.carbs_g:.1f}g    Fat: {meal.fat_g:.1f}g"
        ),
    ]
    extras = _describe_nutrients(meal)
    if extras:
        rendered = "  ".join(
            f"{name.replace('_', ' ').title()}: {value}"
            for name, value in sorted(extras.items())
        )
        lines.append(rendered)
    if meal.id:
        lines.append(f"Point ID: {meal.id}")

    click.echo(f"{title}\n" + "\n".join(lines))


def _log_meal_internal(
    text: str | None = None,
    protein: float | None = None,
    calories: float | None = None,
    carbs: float | None = None,
    fat: float | None = None,
    nutrients: dict[NutrientType, GramsQuantity] | None = None,
    name: str | None = None,
    meal_type_str: str | None = None,
    time_str: str | None = None,
    dry_run: bool = False,
    output_json: bool = False,
    tz_override: str | None = None,
) -> MealLog:
    """Core logic to construct, validate, and upload a MealLog."""
    active_tz = get_user_timezone()

    try:
        parsed = parse_shorthand(text or "", tz=active_tz)
    except ParseError as exc:
        raise UsageError(str(exc)) from exc

    meal_type = None
    if meal_type_str:
        meal_type = MealType.from_string(meal_type_str)

    meal_time = None
    if time_str:
        meal_time = parse_time_str(time_str, tz=active_tz)
    elif parsed.timestamp:
        meal_time = parsed.timestamp
    else:
        meal_time = datetime.now(active_tz)

    food_name = name or (
        parsed.name
        if parsed.name
        else (
            text if text and not any([protein, calories, carbs, fat]) else ""
        )
    )
    if not food_name and parsed.name:
        food_name = parsed.name

    final_protein = protein if protein is not None else parsed.protein
    final_fat = fat if fat is not None else parsed.fat
    final_carbs = carbs if carbs is not None else parsed.carbs
    # Flags win over shorthand for the same nutrient, matching macro behavior.
    final_nutrients = {**parsed.nutrients, **(nutrients or {})}
    final_calories = calories if calories is not None else parsed.calories

    if final_calories <= 0 and (
        final_protein > 0 or final_carbs > 0 or final_fat > 0
    ):
        final_calories = (
            (final_protein * 4.0) + (final_carbs * 4.0) + (final_fat * 9.0)
        )

    final_meal_type = (
        meal_type or parsed.meal_type or MealType.MEAL_TYPE_UNSPECIFIED
    )
    if final_meal_type == MealType.MEAL_TYPE_UNSPECIFIED:
        final_meal_type = infer_meal_type(meal_time, tz=active_tz)

    if not food_name:
        food_name = final_meal_type.value.capitalize()

    # Delegate to ParsedMacros to share nutrient-building logic.
    meal_log = ParsedMacros(
        name=food_name,
        protein=final_protein,
        fat=final_fat,
        carbs=final_carbs,
        calories=final_calories,
        nutrients=final_nutrients,
        meal_type=final_meal_type,
        timestamp=meal_time,
        tz=active_tz,
    ).to_meal_log()

    for warning in parsed.warnings:
        click.echo(f"Warning: {warning}", err=True)

    if dry_run:
        if output_json:
            emit(_meal_json(meal_log), json_output=True, human=lambda _: [])
        else:
            _render_meal_panel(
                meal_log, title="Dry Run (Not Sent to Google Health)"
            )
        return meal_log

    client = GoogleHealthClient()
    try:
        saved_meal = client.log_meal(meal_log)
        if output_json:
            emit(_meal_json(saved_meal), json_output=True, human=lambda _: [])
        else:
            _render_meal_panel(
                saved_meal, title="Successfully Logged to Google Health"
            )
        return saved_meal
    except GoogleHealthError as exc:
        raise RemoteError(f"Error logging meal: {exc}") from exc


@click.group(
    cls=JsonAwareGroup,
    invoke_without_command=True,
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "-v", "--version", prog_name="Nutrilog")
@click.pass_context
def app(ctx: click.Context) -> None:
    """Fast, privacy-first nutrition logging to Google Health."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@app.command("log")
@click.argument("name_or_shorthand", required=False)
@click.option("--protein", "-p", type=float, help="Protein in grams.")
@click.option("--calories", "-k", type=float, help="Calories in kcal.")
@click.option("--carbs", "-c", type=float, help="Carbohydrates in grams.")
@click.option("--fat", "-f", type=float, help="Total fat in grams.")
@click.option(
    "--nutrient",
    "-n",
    multiple=True,
    help="Another nutrient with a unit; repeatable (e.g. caffeine=95mg).",
)
@click.option(
    "--meal", "-m", help="Meal type (breakfast, lunch, dinner, snack)."
)
@click.option("--time", "time_str", "-t", help="Time of meal.")
@click.option("--dry-run", is_flag=True, help="Simulate without uploading.")
@json_option
def log_command(
    name_or_shorthand: str | None,
    protein: float | None,
    calories: float | None,
    carbs: float | None,
    fat: float | None,
    nutrient: tuple[str, ...],
    meal: str | None,
    time_str: str | None,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Log a meal with macros and calories to Google Health."""
    try:
        nutrients = parse_nutrient_args(list(nutrient))
    except ParseError as exc:
        raise UsageError(str(exc)) from exc

    _log_meal_internal(
        text=name_or_shorthand,
        protein=protein,
        calories=calories,
        carbs=carbs,
        fat=fat,
        nutrients=nutrients,
        meal_type_str=meal,
        time_str=time_str,
        dry_run=dry_run,
        output_json=json_output,
    )


@app.command("history")
@click.option(
    "--date",
    "-d",
    help="Target date: today, yesterday, or YYYY-MM-DD.",
)
@click.option("--days", "-n", type=click.IntRange(min=1))
@json_option
def history_command(
    date: str | None, days: int | None, json_output: bool
) -> None:
    """View meal history and macronutrient totals."""
    active_tz = get_user_timezone()
    client = GoogleHealthClient()
    try:
        start_dt, end_dt, title_label = resolve_date_range(
            date_str=date, days=days, tz=active_tz
        )
    except Exception as e:
        raise UsageError(f"Invalid date format: {e}") from e

    try:
        meals = client.list_meals(start_time=start_dt, end_time=end_dt)
    except GoogleHealthError as exc:
        raise RemoteError(f"Failed to fetch history: {exc}") from exc

    summary = MacroSummary.from_meals(meals)

    if json_output:
        payload = {
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "summary": {
                "total_protein": summary.total_protein,
                "total_calories": summary.total_calories,
                "total_carbs": summary.total_carbs,
                "total_fat": summary.total_fat,
                "nutrient_totals": summary.nutrient_totals,
                "meal_count": summary.meal_count,
            },
            "meals": [_meal_json(m, active_tz) for m in meals],
        }
        emit(payload, json_output=True, human=lambda _: [])
        return

    is_multi_day = (end_dt.date() - start_dt.date()).days > 0
    now_str = (
        datetime.now(active_tz).strftime("%a, %b %d")
        if title_label == "Today"
        else title_label
    )
    click.echo(f"Meal History ({now_str})")
    click.echo(
        "Time / Date | Meal Type | Food | Protein | Calories | "
        "Carbs | Fat | Point ID"
    )
    if not meals:
        click.echo(
            "- | - | No meals logged for this timeframe | "
            "0.0g | 0 kcal | 0.0g | 0.0g | -"
        )

    for meal in meals:
        try:
            parsed_time = date_parser_iso(meal.interval.startTime).astimezone(
                active_tz
            )
            rendered_time = (
                parsed_time.strftime("%b %d %I:%M %p")
                if is_multi_day
                else parsed_time.strftime("%I:%M %p")
            )
        except Exception:
            rendered_time = meal.interval.startTime[:16]
        click.echo(
            " | ".join(
                [
                    rendered_time,
                    meal.mealType.value.capitalize(),
                    meal.foodDisplayName,
                    f"{meal.protein_g:.1f}g",
                    f"{meal.calories_kcal:.0f} kcal",
                    f"{meal.carbs_g:.1f}g",
                    f"{meal.fat_g:.1f}g",
                    meal.id or "-",
                ]
            )
        )

    summary_line = (
        f"Total Consumed ({summary.meal_count} meals): "
        f"{summary.total_protein:.1f}g Protein | "
        f"{summary.total_calories:.0f} kcal | "
        f"{summary.total_carbs:.1f}g Carbs | "
        f"{summary.total_fat:.1f}g Fat"
    )
    for name, grams in sorted(summary.nutrient_totals.items()):
        if grams > 0:
            formatted = format_grams(grams, None)
            clean_name = name.replace("_", " ").title()
            summary_line += f" | {formatted} {clean_name}"
    click.echo(summary_line)


@app.command("copy")
@click.argument("point_id")
@click.option("--name", help="Override the copied meal name.")
@click.option(
    "--meal",
    "-m",
    help="Override meal type (breakfast, lunch, dinner, snack).",
)
@click.option("--time", "time_str", "-t", help="Time for the copy.")
@click.option("--dry-run", is_flag=True, help="Preview without copying.")
@json_option
def copy_command(
    point_id: str,
    name: str | None,
    meal: str | None,
    time_str: str | None,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Copy a logged meal into a new Google Health data point."""
    active_tz = get_user_timezone()
    try:
        copied_time = (
            parse_time_str(time_str, tz=active_tz)
            if time_str
            else datetime.now(active_tz)
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise UsageError(f"Invalid time: {exc}") from exc

    meal_type = None
    if meal:
        meal_type = MealType.from_string(meal)
        if meal_type == MealType.MEAL_TYPE_UNSPECIFIED:
            raise UsageError(f"Invalid meal type: {meal!r}")

    client = GoogleHealthClient()
    try:
        source = client.get_meal(point_id)
        copied = source.model_copy(
            deep=True,
            update={
                "id": None,
                "foodDisplayName": name or source.foodDisplayName,
                "mealType": meal_type or source.mealType,
                "interval": TimeInterval.from_datetimes(copied_time),
            },
        )

        if dry_run:
            if json_output:
                emit(_meal_json(copied), json_output=True, human=lambda _: [])
            else:
                _render_meal_panel(
                    copied,
                    title="Dry Run (Copy Not Sent to Google Health)",
                    tz=active_tz,
                )
            return

        saved = client.log_meal(copied)
        if json_output:
            emit(_meal_json(saved), json_output=True, human=lambda _: [])
        else:
            _render_meal_panel(
                saved,
                title="Successfully Copied to Google Health",
                tz=active_tz,
            )
    except GoogleHealthError as exc:
        raise RemoteError(f"Error copying meal: {exc}") from exc


@app.command("nutrients")
def nutrients_command() -> None:
    """List every nutrient that can be logged, and how to write it."""
    click.echo("Macros (unitless, in grams)")
    click.echo("Nutrient | Flag | Shorthand")
    for label, flag, shorthand in (
        ("Protein", "-p", "38p"),
        ("Calories", "-k", "580k"),
        ("Carbohydrates", "-c", "54c"),
        ("Fat", "-f", "18f"),
    ):
        click.echo(f"{label} | {flag} | {shorthand}")

    # Names, not flags: 39 nutrients cannot each have a single letter.
    names = sorted(
        n.value.replace("_", " ").lower()
        for n in NutrientType
        if n not in _MACRO_NUTRIENTS
    )
    click.echo("Other nutrients — write with a unit, e.g. -n caffeine=95mg")
    click.echo(
        "\n".join(", ".join(names[i : i + 4]) for i in range(0, len(names), 4))
    )


@app.command("delete")
@click.argument("point_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def delete_command(point_id: str, yes: bool) -> None:
    """Delete a logged meal by its Data Point ID."""
    if not yes:
        confirm = click.confirm(
            f"Are you sure you want to delete meal '{point_id}'?"
        )
        if not confirm:
            click.echo("Deletion cancelled.")
            return

    client = GoogleHealthClient()
    try:
        success = client.delete_meal(point_id)
        if success:
            click.echo(f"Successfully deleted meal ({point_id})")
        else:
            raise RemoteError(f"Could not delete meal ({point_id})")
    except GoogleHealthError as exc:
        raise RemoteError(f"Failed to delete meal: {exc}") from exc


@app.command("rm", hidden=True)
@click.argument("point_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def rm_command(point_id: str, yes: bool) -> None:
    """Alias for 'delete'."""
    delete_command.callback(point_id=point_id, yes=yes)


# Auth Subcommands
@click.group("auth")
def auth_app() -> None:
    """Manage OAuth 2.0 authentication and credentials."""


@auth_app.command("login")
@click.option(
    "--secrets",
    "-s",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to client_secrets.json.",
)
@click.option("--port", "-p", default=0, type=int)
@click.option("--no-browser", is_flag=True)
@click.option("--remote", "-r", "--manual", is_flag=True)
def auth_login_cmd(
    secrets: Path | None, port: int, no_browser: bool, remote: bool
) -> None:
    """Log in to Google Health via OAuth 2.0."""
    try:
        if remote or (no_browser and auth.is_headless_or_ssh()):
            click.echo(
                "Initiating OAuth 2.0 authorization (Remote SSH Mode)..."
            )
            auth.login_remote(client_config_path=secrets)
        else:
            click.echo("Initiating Google OAuth 2.0 authorization...")
            auth.login(
                client_config_path=secrets,
                port=port,
                open_browser=not no_browser,
            )
        click.echo("Successfully authenticated with Google Health!")
    except Exception as exc:
        raise RemoteError(f"Login failed: {exc}") from exc


@auth_app.command("status")
def auth_status_cmd() -> None:
    """Check current authentication status and configuration."""
    status = auth.get_auth_status()
    click.echo("Nutrilog Authentication Status")
    authenticated = "Yes" if status["authenticated"] else "No"
    click.echo(f"Authenticated | {authenticated}")
    click.echo(f"Config Directory | {get_config_dir()}")
    if status.get("using_default_credentials"):
        click.echo("OAuth Client | Built-in Desktop App (Default)")
    else:
        click.echo("OAuth Client | Custom (Environment Variables)")
    if status.get("expiry"):
        click.echo(f"Token Expiry | {status['expiry']}")


@auth_app.command("logout")
def auth_logout_cmd() -> None:
    """Sign out and discard local Google Health OAuth tokens."""
    if auth.logout():
        click.echo("Successfully signed out. Stored tokens cleared.")
    else:
        click.echo("No active session tokens to clear.")


# Config Subcommands
@click.group("config")
def config_app() -> None:
    """Manage user preferences such as the active timezone."""


@config_app.command("show")
def config_show_cmd() -> None:
    """Display current Nutrilog configuration."""
    cfg_tz = get_configured_timezone_name()
    machine_tz = str(get_machine_timezone())

    click.echo("Nutrilog Configuration")
    click.echo(f"Config Directory | {get_config_dir()}")
    if cfg_tz:
        click.echo(f"Timezone | {cfg_tz} (Configured)")
    else:
        click.echo(f"Timezone | {machine_tz} (System Machine Default)")


@config_app.command("set")
@click.option(
    "--timezone",
    "timezone_name",
    "-z",
    help="Timezone name, abbreviation, or auto for machine local.",
)
def config_set_cmd(
    timezone_name: str | None,
) -> None:
    """Set user configuration settings."""
    if timezone_name is None:
        click.echo("No settings provided. Use --help to view options.")
        return

    try:
        saved_tz = set_user_timezone(timezone_name)
        if saved_tz:
            click.echo(f"Configuration updated: Timezone set to '{saved_tz}'")
        else:
            click.echo(
                "Configuration updated: Timezone reset to machine system local"
            )
    except ValueError as exc:
        raise UsageError(f"Invalid timezone: {exc}") from exc


for command in (
    auth_app,
    config_app,
    skill_group(name="nutrilog", package="nutrilog"),
):
    app.add_command(command)
