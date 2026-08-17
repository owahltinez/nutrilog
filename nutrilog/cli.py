"""Typer and Rich command-line interface for Nutrilog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Optional
import typer
import typer.core
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
    get_daily_targets,
    load_config,
    save_config,
    save_credentials,
    set_daily_targets,
)


class NutrilogGroup(typer.core.TyperGroup):
    """Custom TyperGroup that routes unhandled positional arguments directly to 'log'."""

    def resolve_command(self, ctx, args):
        if not args:
            return super().resolve_command(ctx, args)
        cmd_name = args[0]
        cmd = self.get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd_name, cmd, args[1:]
        if cmd_name.startswith("-"):
            return super().resolve_command(ctx, args)
        log_cmd = self.get_command(ctx, "log")
        return "log", log_cmd, args


app = typer.Typer(
    cls=NutrilogGroup,
    name="nutrilog",
    help="Fast, privacy-first CLI tool for logging nutrition directly to Google Health.",
    invoke_without_command=True,
)
auth_app = typer.Typer(help="Manage OAuth 2.0 authentication and credentials.")
config_app = typer.Typer(help="Manage user preferences and daily macro targets.")

from nutrilog.skill import skill_app

app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(skill_app, name="skill")

console = Console()
err_console = Console(stderr=True)


def _render_meal_panel(meal: MealLog, title: str = "Logged to Google Health") -> None:
    lines = [
        f"[bold cyan]Food:[/bold cyan] {meal.foodDisplayName}",
        f"[bold cyan]Meal:[/bold cyan] {meal.mealType.value.capitalize()}",
        f"[bold cyan]Time:[/bold cyan] {meal.interval.startTime}",
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
) -> MealLog:
    # 1. Base time
    meal_time = parse_time_str(time_str) if time_str else datetime.now(timezone.utc)
    meal_type = MealType.from_string(meal_type_str) if meal_type_str else None

    # 2. Parse shorthand if provided
    parsed = parse_shorthand(text or "", default_meal_type=meal_type, default_time=meal_time)

    # 3. Apply explicit flag overrides
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

        final_meal_type = infer_meal_type(meal_time)

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

    if output_json:
        console.print_json(data=meal_log.to_api_payload())
        return meal_log

    if dry_run:
        _render_meal_panel(meal_log, title="Dry Run (Not Sent to Google Health)")
        return meal_log

    client = GoogleHealthClient()
    try:
        saved_meal = client.log_meal(meal_log)
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
        today_command()


@app.command("log")
def log_command(
    name_or_shorthand: Optional[str] = typer.Argument(
        None,
        help="Meal name or shorthand string (e.g. 'Grilled Salmon' or '35p 600k Grilled Salmon').",
    ),
    protein: Optional[float] = typer.Option(None, "--protein", "-p", help="Protein in grams."),
    calories: Optional[float] = typer.Option(None, "--calories", "-k", "--cal", help="Calories in kcal."),
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


@app.command("quick")
def quick_command(
    protein: float = typer.Option(..., "--protein", "-p", help="Protein in grams."),
    calories: Optional[float] = typer.Option(None, "--calories", "-k", help="Calories in kcal."),
    carbs: float = typer.Option(0.0, "--carbs", "-c", help="Carbs in grams."),
    fat: float = typer.Option(0.0, "--fat", "-f", help="Fat in grams."),
    name: str = typer.Option("Quick Log", "--name", "-n", help="Display name for this entry."),
    meal: Optional[str] = typer.Option(None, "--meal", "-m", help="Meal type."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without uploading."),
):
    """Quickly log protein and calories (e.g. protein shake, snack)."""
    _log_meal_internal(
        name=name,
        protein=protein,
        calories=calories,
        carbs=carbs,
        fat=fat,
        meal_type_str=meal,
        dry_run=dry_run,
    )


@app.command("today")
def today_command():
    """Display today's meals and macronutrient progress against targets."""
    client = GoogleHealthClient()
    try:
        meals = client.get_today_meals()
    except GoogleHealthError as e:
        err_console.print(f"[bold yellow]Could not fetch today's meals:[/bold yellow] {e}")
        return

    summary = MacroSummary.from_meals(meals)
    targets = get_daily_targets()

    now_str = datetime.now().strftime("%a, %b %d")
    table = Table(title=f"Today's Nutrition Summary ({now_str})", show_header=True, header_style="bold magenta")
    table.add_column("Time", style="dim", width=10)
    table.add_column("Meal Type", width=12)
    table.add_column("Food", style="bold", min_width=20)
    table.add_column("Protein", justify="right", style="green")
    table.add_column("Calories", justify="right", style="yellow")
    table.add_column("Carbs", justify="right", style="blue")
    table.add_column("Fat", justify="right", style="magenta")

    if not meals:
        table.add_row("-", "-", "No meals logged yet today", "0.0g", "0 kcal", "0.0g", "0.0g")
    else:
        for m in meals:
            try:
                t_dt = date_parser_iso(m.interval.startTime)
                t_str = t_dt.strftime("%I:%M %p")
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
            )

    console.print(table)

    # Progress rollups
    p_pct = (summary.total_protein / targets.protein * 100.0) if targets.protein > 0 else 0
    k_pct = (summary.total_calories / targets.calories * 100.0) if targets.calories > 0 else 0

    p_rem = max(0.0, targets.protein - summary.total_protein)
    k_rem = max(0.0, targets.calories - summary.total_calories)

    summary_panel = (
        f"[bold]Daily Total:[/bold] {summary.total_protein:.1f}g / {targets.protein:.0f}g Protein ([green]{p_pct:.0f}%[/green]) | "
        f"{summary.total_calories:.0f} / {targets.calories:.0f} kcal ([yellow]{k_pct:.0f}%[/yellow])\n"
        f"[bold]Remaining:[/bold]   {p_rem:.1f}g Protein | {k_rem:.0f} kcal"
    )
    console.print(Panel(summary_panel, border_style="cyan"))


def date_parser_iso(s: str) -> datetime:
    from dateutil import parser

    return parser.parse(s)


@app.command("history")
def history_command(
    days: int = typer.Option(7, "--days", "-d", help="Number of past days to query."),
    show_ids: bool = typer.Option(False, "--ids", help="Display Data Point IDs."),
):
    """View meal history across past days."""
    client = GoogleHealthClient()
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        meals = client.list_meals(start_time=start_dt)
    except GoogleHealthError as e:
        err_console.print(f"[bold red]Failed to fetch history:[/bold red] {e}")
        raise typer.Exit(code=1)

    table = Table(title=f"Meal History (Past {days} Days)", show_header=True)
    if show_ids:
        table.add_column("Point ID", style="dim", max_width=20)
    table.add_column("Date/Time", style="dim")
    table.add_column("Type")
    table.add_column("Food", style="bold")
    table.add_column("Protein", justify="right", style="green")
    table.add_column("Calories", justify="right", style="yellow")
    table.add_column("Carbs", justify="right", style="blue")
    table.add_column("Fat", justify="right", style="magenta")

    for m in meals:
        row = []
        if show_ids:
            row.append(m.id or "-")
        row.extend([
            m.interval.startTime[:16].replace("T", " "),
            m.mealType.value.capitalize(),
            m.foodDisplayName,
            f"{m.protein_g:.1f}g",
            f"{m.calories_kcal:.0f} kcal",
            f"{m.carbs_g:.1f}g",
            f"{m.fat_g:.1f}g",
        ])
        table.add_row(*row)
    console.print(table)


@app.command("list")
def list_command(
    days: int = typer.Option(1, "--days", "-d", help="Number of days to query (default 1)."),
    start: Optional[str] = typer.Option(None, "--start", help="Start time / date filter."),
    end: Optional[str] = typer.Option(None, "--end", help="End time / date filter."),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON array."),
):
    """List logged meals with IDs for inspection and deletion."""
    client = GoogleHealthClient()
    start_dt = parse_time_str(start) if start else (datetime.now(timezone.utc) - timedelta(days=days))
    end_dt = parse_time_str(end) if end else None

    try:
        meals = client.list_meals(start_time=start_dt, end_time=end_dt)
    except GoogleHealthError as e:
        err_console.print(f"[bold red]Failed to fetch meals:[/bold red] {e}")
        raise typer.Exit(code=1)

    if output_json:
        console.print_json(data=[m.to_api_payload() for m in meals])
        return

    table = Table(title=f"Logged Meals ({len(meals)} total)", show_header=True)
    table.add_column("Point ID", style="dim")
    table.add_column("Date/Time", style="cyan")
    table.add_column("Type", width=10)
    table.add_column("Food", style="bold", min_width=15)
    table.add_column("Protein", justify="right", style="green")
    table.add_column("Calories", justify="right", style="yellow")
    table.add_column("Carbs", justify="right", style="blue")
    table.add_column("Fat", justify="right", style="magenta")

    if not meals:
        table.add_row("-", "-", "-", "No meals found for this timeframe", "0.0g", "0 kcal", "0.0g", "0.0g")
    else:
        for m in meals:
            table.add_row(
                m.id or "-",
                m.interval.startTime[:16].replace("T", " "),
                m.mealType.value.capitalize(),
                m.foodDisplayName,
                f"{m.protein_g:.1f}g",
                f"{m.calories_kcal:.0f} kcal",
                f"{m.carbs_g:.1f}g",
                f"{m.fat_g:.1f}g",
            )
    console.print(table)


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
            console.print(f"[bold green]✓ Successfully deleted meal {point_id}[/bold green]")
        else:
            err_console.print(f"[bold red]Could not delete meal {point_id}[/bold red]")
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
    manual: bool = typer.Option(
        False,
        "--manual",
        "-m",
        help="Use copy-paste authorization flow (recommended for remote SSH sessions).",
    ),
):
    """Log in to Google Health via OAuth 2.0."""
    from nutrilog.auth import is_headless_or_ssh, login_manual

    try:
        if manual or (no_browser and is_headless_or_ssh()):
            console.print("[bold blue]Initiating OAuth 2.0 authorization (Remote / Manual Mode)...[/bold blue]")
            login_manual(client_config_path=secrets)
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
    table.add_row("Client Credentials Found", "Yes" if status["has_credentials_configured"] else "No")
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


@auth_app.command("setup")
def auth_setup_cmd(
    client_id: Optional[str] = typer.Option(None, "--client-id", help="OAuth 2.0 Desktop Client ID."),
    client_secret: Optional[str] = typer.Option(None, "--client-secret", help="OAuth 2.0 Client Secret."),
    secrets_file: Optional[Path] = typer.Option(None, "--file", "-f", help="Path to downloaded client_secrets.json."),
):
    """Save Google Cloud OAuth client credentials."""
    if secrets_file and secrets_file.exists():
        data = json.loads(secrets_file.read_text(encoding="utf-8"))
        save_credentials(data)
        console.print(f"[bold green]✓ Saved client credentials from {secrets_file}[/bold green]")
        return

    if client_id and client_secret:
        data = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        save_credentials(data)
        console.print("[bold green]✓ Saved client credentials successfully.[/bold green]")
        return

    console.print(
        "[yellow]Please provide either --file <path/to/client_secrets.json> or --client-id and --client-secret.[/yellow]"
    )


# Config Subcommands
@config_app.command("show")
def config_show_cmd():
    """Display current nutrition targets and configuration."""
    targets = get_daily_targets()
    table = Table(title="Daily Nutrition Targets", show_header=True)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Target", justify="right")

    table.add_row("Calories", f"{targets.calories:.0f} kcal")
    table.add_row("Protein", f"{targets.protein:.1f} g")
    table.add_row("Carbohydrates", f"{targets.carbs:.1f} g" if targets.carbs is not None else "Not set")
    table.add_row("Fat", f"{targets.fat:.1f} g" if targets.fat is not None else "Not set")

    console.print(table)


@config_app.command("set")
def config_set_cmd(
    calories: Optional[float] = typer.Option(None, "--calories", "-k", help="Daily calorie target (kcal)."),
    protein: Optional[float] = typer.Option(None, "--protein", "-p", help="Daily protein target (grams)."),
    carbs: Optional[float] = typer.Option(None, "--carbs", "-c", help="Daily carbohydrate target (grams)."),
    fat: Optional[float] = typer.Option(None, "--fat", "-f", help="Daily fat target (grams)."),
):
    """Set daily nutrition targets."""
    updated = set_daily_targets(calories=calories, protein=protein, carbs=carbs, fat=fat)
    console.print(
        f"[bold green]✓ Targets updated:[/bold green] {updated.calories:.0f} kcal, {updated.protein:.1f}g protein"
    )
