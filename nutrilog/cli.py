"""Typer and Rich command-line interface for Nutrilog."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nutrilog import __version__
from nutrilog.auth import get_auth_status, login as auth_login, logout as auth_logout
from nutrilog.client import GoogleHealthClient, GoogleHealthError
from nutrilog.models import (
    Energy,
    GramsQuantity,
    MacroSummary,
    MealLog,
    MealType,
    NutrientEntry,
    NutrientType,
    TimeInterval,
)
from nutrilog.parser import parse_shorthand, parse_time_str
from nutrilog.storage import (
    get_config_dir,
    get_configured_timezone_name,
    get_machine_timezone,
    get_user_timezone,
    load_config,
    save_config,
    set_user_timezone,
)


app = typer.Typer(
    name="nutrilog",
    help="Fast, privacy-first CLI tool for logging nutrition directly to Google Health.",
    no_args_is_help=True,
)
auth_app = typer.Typer(help="Manage OAuth 2.0 authentication and credentials.")
config_app = typer.Typer(help="Manage user preferences and daily macro targets.")

from nutrilog.skill import skill_app

app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(skill_app, name="skill")

console = Console()
err_console = Console(stderr=True)


def date_parser_iso(s: str) -> datetime:
    from dateutil import parser

    return parser.parse(s)


def resolve_date_range(
    date_str: Optional[str] = None,
    days: Optional[int] = None,
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


def _render_meal_panel(meal: MealLog, title: str = "Logged to Google Health", tz: Optional[tzinfo] = None) -> None:
    active_tz = tz or get_user_timezone()
    try:
        dt_parsed = date_parser_iso(meal.interval.startTime).astimezone(active_tz)
        time_display = dt_parsed.strftime("%Y-%m-%d %I:%M %p")
    except Exception:
        time_display = meal.interval.startTime

    lines = [
        f"[bold cyan]Food:[/bold cyan] {meal.foodDisplayName}",
        f"[bold cyan]Meal:[/bold cyan] {meal.mealType.value.capitalize()}",
        f"[bold cyan]Time:[/bold cyan] {time_display}",
        f"[bold green]Protein:[/bold green] {meal.protein_g:.1f}g    "
        f"[bold yellow]Calories:[/bold yellow] {meal.calories_kcal:.0f} kcal    "
        f"[bold blue]Carbs:[/bold blue] {meal.carbs_g:.1f}g    "
        f"[bold magenta]Fat:[/bold magenta] {meal.fat_g:.1f}g",
    ]
    if meal.fiber_g > 0:
        lines.append(f"[bold dim]Fiber:[/bold dim] {meal.fiber_g:.1f}g")
    if meal.id:
        lines.append(f"[dim]Point ID: {meal.id}[/dim]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold green]✓ {title}[/bold green]",
            expand=False,
            border_style="green",
        )
    )


def _log_meal_internal(
    text: Optional[str] = None,
    protein: Optional[float] = None,
    calories: Optional[float] = None,
    carbs: Optional[float] = None,
    fat: Optional[float] = None,
    fiber: Optional[float] = None,
    name: Optional[str] = None,
    meal_type_str: Optional[str] = None,
    time_str: Optional[str] = None,
    dry_run: bool = False,
    output_json: bool = False,
    tz_override: Optional[str] = None,
) -> MealLog:
    """Core logic to construct, validate, and upload a MealLog."""
    active_tz = get_user_timezone()

    parsed = parse_shorthand(text or "", tz=active_tz)

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

    food_name = name or (parsed.name if parsed.name else (text if text and not any([protein, calories, carbs, fat]) else ""))
    if not food_name and parsed.name:
        food_name = parsed.name

    final_protein = protein if protein is not None else parsed.protein
    final_fat = fat if fat is not None else parsed.fat
    final_carbs = carbs if carbs is not None else parsed.carbs
    final_fiber = fiber if fiber is not None else parsed.fiber
    final_calories = calories if calories is not None else parsed.calories

    if final_calories <= 0 and (final_protein > 0 or final_carbs > 0 or final_fat > 0):
        final_calories = (final_protein * 4.0) + (final_carbs * 4.0) + (final_fat * 9.0)

    final_meal_type = meal_type or parsed.meal_type or MealType.MEAL_TYPE_UNSPECIFIED
    if final_meal_type == MealType.MEAL_TYPE_UNSPECIFIED:
        from nutrilog.parser import infer_meal_type

        final_meal_type = infer_meal_type(meal_time, tz=active_tz)

    if not food_name:
        food_name = final_meal_type.value.capitalize()

    nutrients = []
    if final_protein > 0:
        nutrients.append(
            NutrientEntry(
                nutrient=NutrientType.PROTEIN.value,
                quantity=GramsQuantity(grams=final_protein),
            )
        )
    if final_fiber > 0:
        nutrients.append(
            NutrientEntry(
                nutrient=NutrientType.FIBER.value,
                quantity=GramsQuantity(grams=final_fiber),
            )
        )

    meal_log = MealLog(
        foodDisplayName=food_name,
        mealType=final_meal_type,
        interval=TimeInterval.from_datetimes(meal_time),
        energy=Energy(kcal=round(final_calories, 1)),
        totalCarbohydrate=GramsQuantity(grams=round(final_carbs, 2)),
        totalFat=GramsQuantity(grams=round(final_fat, 2)),
        nutrients=nutrients,
    )

    if dry_run:
        if output_json:
            meal_dict = {
                "id": meal_log.id,
                "time": meal_log.interval.startTime,
                "meal_type": meal_log.mealType.value,
                "name": meal_log.foodDisplayName,
                "protein_g": meal_log.protein_g,
                "calories_kcal": meal_log.calories_kcal,
                "carbs_g": meal_log.carbs_g,
                "fat_g": meal_log.fat_g,
                "fiber_g": meal_log.fiber_g,
            }
            console.print_json(data=meal_dict)
        else:
            _render_meal_panel(meal_log, title="Dry Run (Not Sent to Google Health)")
        return meal_log

    client = GoogleHealthClient()
    try:
        saved_meal = client.log_meal(meal_log)
        if output_json:
            meal_dict = {
                "id": saved_meal.id,
                "time": saved_meal.interval.startTime,
                "meal_type": saved_meal.mealType.value,
                "name": saved_meal.foodDisplayName,
                "protein_g": saved_meal.protein_g,
                "calories_kcal": saved_meal.calories_kcal,
                "carbs_g": saved_meal.carbs_g,
                "fat_g": saved_meal.fat_g,
                "fiber_g": saved_meal.fiber_g,
            }
            console.print_json(data=meal_dict)
        else:
            _render_meal_panel(saved_meal, title="Successfully Logged to Google Health")
        return saved_meal
    except GoogleHealthError as e:
        err_console.print(f"[bold red]Error logging meal:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Display Nutrilog version."
    ),
):
    """Nutrilog - Fast terminal nutrition logging to Google Health."""
    if version:
        console.print(f"[bold green]Nutrilog[/bold green] v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@app.command("log")
def log_command(
    name_or_shorthand: Optional[str] = typer.Argument(
        None,
        help="Meal name or shorthand string (e.g. 'Grilled Salmon' or '35p 600k Grilled Salmon').",
    ),
    protein: Optional[float] = typer.Option(None, "--protein", "-p", help="Protein in grams."),
    calories: Optional[float] = typer.Option(None, "--calories", "-k", help="Calories in kcal."),
    carbs: Optional[float] = typer.Option(None, "--carbs", "-c", help="Carbohydrates in grams."),
    fat: Optional[float] = typer.Option(None, "--fat", "-f", help="Total fat in grams."),
    fiber: Optional[float] = typer.Option(None, "--fiber", help="Fiber in grams."),
    meal: Optional[str] = typer.Option(None, "--meal", "-m", help="Meal type (breakfast, lunch, dinner, snack)."),
    time_str: Optional[str] = typer.Option(None, "--time", "-t", help="Time of meal (e.g. '12:30', '1pm')."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without uploading to Google Health."),
    output_json: bool = typer.Option(False, "--json", help="Output payload as JSON."),
):
    """Log a meal with macros and calories to Google Health."""
    _log_meal_internal(
        text=name_or_shorthand,
        protein=protein,
        calories=calories,
        carbs=carbs,
        fat=fat,
        fiber=fiber,
        meal_type_str=meal,
        time_str=time_str,
        dry_run=dry_run,
        output_json=output_json,
    )


@app.command("history")
def history_command(
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Target date ('today', 'yesterday', 'YYYY-MM-DD'). Defaults to today.",
    ),
    days: Optional[int] = typer.Option(
        None,
        "--days",
        "-n",
        help="Query past N calendar days (e.g. --days 7).",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON array."),
):
    """View meal history and macronutrient totals."""
    active_tz = get_user_timezone()
    client = GoogleHealthClient()
    try:
        start_dt, end_dt, title_label = resolve_date_range(date_str=date, days=days, tz=active_tz)
    except Exception as e:
        err_console.print(f"[bold red]Invalid date format:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        meals = client.list_meals(start_time=start_dt, end_time=end_dt)
    except GoogleHealthError as e:
        err_console.print(f"[bold red]Failed to fetch history:[/bold red] {e}")
        raise typer.Exit(code=1)

    summary = MacroSummary.from_meals(meals)

    if output_json:
        payload = {
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "summary": {
                "total_protein": summary.total_protein,
                "total_calories": summary.total_calories,
                "total_carbs": summary.total_carbs,
                "total_fat": summary.total_fat,
                "meal_count": summary.meal_count,
            },
            "meals": [
                {
                    "id": m.id,
                    "time": m.interval.startTime,
                    "meal_type": m.mealType.value,
                    "name": m.foodDisplayName,
                    "protein_g": m.protein_g,
                    "calories_kcal": m.calories_kcal,
                    "carbs_g": m.carbs_g,
                    "fat_g": m.fat_g,
                }
                for m in meals
            ],
        }
        console.print_json(data=payload)
        return

    is_multi_day = (end_dt.date() - start_dt.date()).days > 0
    now_str = datetime.now(active_tz).strftime("%a, %b %d") if title_label == "Today" else title_label
    table = Table(title=f"Meal History ({now_str})", show_header=True, header_style="bold magenta")
    table.add_column("Time / Date", style="dim")
    table.add_column("Meal Type")
    table.add_column("Food", style="bold")
    table.add_column("Protein", justify="right", style="green")
    table.add_column("Calories", justify="right", style="yellow")
    table.add_column("Carbs", justify="right", style="blue")
    table.add_column("Fat", justify="right", style="magenta")
    table.add_column("Point ID", style="dim")

    if not meals:
        table.add_row("-", "-", "No meals logged for this timeframe", "0.0g", "0 kcal", "0.0g", "0.0g", "-")
    else:
        for m in meals:
            try:
                t_dt = date_parser_iso(m.interval.startTime).astimezone(active_tz)
                t_str = t_dt.strftime("%b %d %I:%M %p") if is_multi_day else t_dt.strftime("%I:%M %p")
            except Exception:
                t_str = m.interval.startTime[:16]
            table.add_row(
                t_str,
                m.mealType.value.capitalize(),
                m.foodDisplayName,
                f"{m.protein_g:.1f}g",
                f"{m.calories_kcal:.0f} kcal",
                f"{m.carbs_g:.1f}g",
                f"{m.fat_g:.1f}g",
                m.id or "-",
            )

    console.print(table)

    summary_panel = (
        f"[bold]Total Consumed ({summary.meal_count} meals):[/bold] "
        f"{summary.total_protein:.1f}g Protein | "
        f"{summary.total_calories:.0f} kcal | "
        f"{summary.total_carbs:.1f}g Carbs | "
        f"{summary.total_fat:.1f}g Fat"
    )
    console.print(Panel(summary_panel, border_style="cyan"))


@app.command("delete")
def delete_command(
    point_id: str = typer.Argument(..., help="The Data Point ID of the meal to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Delete a logged meal by its Data Point ID."""
    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete meal '{point_id}'?")
        if not confirm:
            console.print("[dim]Deletion cancelled.[/dim]")
            return

    client = GoogleHealthClient()
    try:
        success = client.delete_meal(point_id)
        if success:
            console.print(f"[bold green]✓ Successfully deleted meal[/bold green] [dim]({point_id})[/dim]")
        else:
            err_console.print(f"[bold red]Could not delete meal[/bold red] [dim]({point_id})[/dim]")
            raise typer.Exit(code=1)
    except GoogleHealthError as e:
        err_console.print(f"[bold red]Failed to delete meal:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command("rm", hidden=True)
def rm_command(
    point_id: str = typer.Argument(..., help="The Data Point ID of the meal to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Alias for 'delete'."""
    delete_command(point_id=point_id, yes=yes)


# Auth Subcommands
@auth_app.command("login")
def auth_login_cmd(
    secrets: Optional[Path] = typer.Option(None, "--secrets", "-s", help="Path to client_secrets.json."),
    port: int = typer.Option(0, "--port", "-p", help="Port for local loopback server (default random)."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not automatically launch a browser window."),
    remote: bool = typer.Option(
        False,
        "--remote",
        "-r",
        "--manual",
        help="Use copy-paste authorization flow (recommended for remote SSH sessions).",
    ),
):
    """Log in to Google Health via OAuth 2.0."""
    from nutrilog.auth import is_headless_or_ssh, login_remote

    try:
        if remote or (no_browser and is_headless_or_ssh()):
            console.print("[bold blue]Initiating OAuth 2.0 authorization (Remote SSH Mode)...[/bold blue]")
            login_remote(client_config_path=secrets)
        else:
            console.print("[bold blue]Initiating Google OAuth 2.0 authorization...[/bold blue]")
            auth_login(client_config_path=secrets, port=port, open_browser=not no_browser)
        console.print("[bold green]✓ Successfully authenticated with Google Health![/bold green]")
    except Exception as e:
        err_console.print(f"[bold red]Login failed:[/bold red] {e}")
        raise typer.Exit(code=1)


@auth_app.command("status")
def auth_status_cmd():
    """Check current authentication status and configuration."""
    status = get_auth_status()
    table = Table(title="Nutrilog Authentication Status", show_header=False)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")

    table.add_row("Authenticated", "[green]Yes[/green]" if status["authenticated"] else "[red]No[/red]")
    table.add_row("Config Directory", str(get_config_dir()))
    if status.get("using_default_credentials"):
        table.add_row("OAuth Client", "Built-in Desktop App (Default)")
    else:
        table.add_row("OAuth Client", "Custom (Environment Variables)")
    if status.get("expiry"):
        table.add_row("Token Expiry", str(status["expiry"]))

    console.print(table)


@auth_app.command("logout")
def auth_logout_cmd():
    """Sign out and discard local Google Health OAuth tokens."""
    if auth_logout():
        console.print("[bold green]✓ Successfully signed out. Stored tokens cleared.[/bold green]")
    else:
        console.print("[dim]No active session tokens to clear.[/dim]")


# Config Subcommands
@config_app.command("show")
def config_show_cmd():
    """Display current Nutrilog configuration."""
    cfg_tz = get_configured_timezone_name()
    machine_tz = str(get_machine_timezone())

    table = Table(title="Nutrilog Configuration", show_header=True)
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value", justify="right")

    table.add_row("Config Directory", str(get_config_dir()))
    if cfg_tz:
        table.add_row("Timezone", f"{cfg_tz} (Configured)")
    else:
        table.add_row("Timezone", f"{machine_tz} (System Machine Default)")

    console.print(table)


@config_app.command("set")
def config_set_cmd(
    timezone_name: Optional[str] = typer.Option(
        None,
        "--timezone",
        "-z",
        help="Timezone (e.g. 'Australia/Sydney', 'AEST', 'America/Los_Angeles', or 'auto' to use machine local).",
    ),
):
    """Set user configuration settings."""
    if timezone_name is None:
        console.print("[dim]No settings provided to update. Use --help to view available options.[/dim]")
        return

    try:
        saved_tz = set_user_timezone(timezone_name)
        if saved_tz:
            console.print(f"[bold green]✓ Configuration updated:[/bold green] Timezone set to '{saved_tz}'")
        else:
            console.print("[bold green]✓ Configuration updated:[/bold green] Timezone reset to machine system local")
    except ValueError as e:
        err_console.print(f"[bold red]Invalid timezone:[/bold red] {e}")
        raise typer.Exit(code=1)
