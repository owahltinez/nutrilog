"""CLI commands and utilities for installing the packaged Agent Skill for Nutrilog."""

from __future__ import annotations

from importlib import resources
import os
from pathlib import Path
import shutil
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

SKILL_NAME = "nutrilog"

# The tool-agnostic cross-tool location
SHARED_DIR = Path(".agents") / "skills"

# Per-tool skills directories: {Tool Name: (Marker directory, Skills directory)}
TOOL_DIRS: dict[str, tuple[Path, Path]] = {
    "Gemini / Jetski": (Path(".gemini"), Path(".gemini") / "config" / "skills"),
    "Gemini CLI": (Path(".gemini"), Path(".gemini") / "skills"),
    "Claude Code": (Path(".claude"), Path(".claude") / "skills"),
    "Cursor": (Path(".cursor"), Path(".cursor") / "skills"),
}

console = Console()
err_console = Console(stderr=True)


def packaged_skill() -> Path:
    """Locate the packaged SKILL.md, whether installed in a wheel or run from source."""
    try:
        packaged = Path(str(resources.files("nutrilog") / "skills" / SKILL_NAME / "SKILL.md"))
        if packaged.is_file():
            return packaged
    except Exception:
        pass

    # Fallback to repository root
    checkout = Path(__file__).resolve().parents[1] / "SKILL.md"
    if checkout.is_file():
        return checkout

    raise RuntimeError(f"SKILL.md not found in package or repository checkout.")


def detected_tools(home: Optional[Path] = None) -> dict[str, Path]:
    """Return skills directories for agent tools present on this system."""
    h = home or Path.home()
    return {
        name: h / skills
        for name, (marker, skills) in TOOL_DIRS.items()
        if (h / marker).is_dir()
    }


def _primary_target(destination: Optional[Path], home: Path) -> Path:
    """Return the default target directory for skill installation."""
    if destination is not None:
        return destination / SKILL_NAME
    return home / SHARED_DIR / SKILL_NAME


def _is_our_skill(target: Path) -> bool:
    """Check if the target directory contains the nutrilog skill."""
    manifest = target / "SKILL.md"
    if manifest.is_symlink() and not manifest.exists():
        return True
    if not manifest.is_file():
        return False
    try:
        content = manifest.read_text(encoding="utf-8", errors="replace")
        return f"name: {SKILL_NAME}" in content
    except OSError:
        return False


def _remove(target: Path) -> None:
    """Remove installed skill directory or symlink."""
    if target.is_symlink() or target.is_file():
        target.unlink()
    else:
        shutil.rmtree(target)


def _place(
    source: Path,
    target: Path,
    *,
    link: bool = False,
    force: bool = False,
) -> str:
    """Place the skill manifest into target directory."""
    if target.exists() or target.is_symlink():
        if not _is_our_skill(target):
            raise ValueError(
                f"{target} exists and does not contain the '{SKILL_NAME}' skill. Refusing to overwrite."
            )
        if not force:
            raise ValueError(f"{target} already exists. Pass --force to replace it.")
        _remove(target)

    target.mkdir(parents=True, exist_ok=True)
    manifest = target / "SKILL.md"

    if link:
        try:
            manifest.symlink_to(source)
            return f"Linked   {manifest} -> {source}"
        except OSError as e:
            err_console.print(f"[yellow]# Symlink failed ({e}); copying instead[/yellow]")

    shutil.copy2(source, manifest)
    return f"Copied   {target}"


skill_app = typer.Typer(
    name="skill",
    help="Install or manage the packaged Agent Skill for AI coding agents.",
)


@skill_app.command("install")
def skill_install_cmd(
    destination: Optional[Path] = typer.Option(
        None,
        "--to",
        help=f"Specific skills directory to act on (e.g. ~/.gemini/config/skills).",
    ),
    every: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Install into every detected AI agent tool's skills directory.",
    ),
    link: bool = typer.Option(
        False,
        "--link",
        help="Symlink instead of copying (best for persistent installs).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Replace existing installation.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview actions without making filesystem changes.",
    ),
):
    """Install the Nutrilog Agent Skill so coding assistants can discover and use Nutrilog."""
    try:
        source = packaged_skill()
    except RuntimeError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    home = Path.home()
    targets = [_primary_target(destination, home)]

    found = detected_tools(home)
    if every:
        for directory in found.values():
            target_path = directory / SKILL_NAME
            if target_path not in targets:
                targets.append(target_path)

    for target in targets:
        if dry_run:
            if (target.exists() or target.is_symlink()) and not _is_our_skill(target):
                console.print(f"[bold red]Would REFUSE[/bold red]  {target}: not the {SKILL_NAME} skill")
            elif target.exists() and not force:
                console.print(f"[bold yellow]Would REFUSE[/bold yellow]  {target}: exists (needs --force)")
            else:
                console.print(f"[bold green]Would install[/bold green] {target}")
            continue

        try:
            msg = _place(source, target, link=link, force=force)
            console.print(f"[bold green]✓[/bold green] {msg}")
        except Exception as e:
            err_console.print(f"[bold red]Error installing to {target}:[/bold red] {e}")
            raise typer.Exit(code=1)

    if found and not every and destination is None:
        console.print("\n[dim]# Also found tool-specific skills directories:[/dim]")
        for name, directory in found.items():
            console.print(f"[dim]#   {name}: {directory / SKILL_NAME}[/dim]")
        console.print("[dim]# Install into all of them with: nutrilog skill install --all[/dim]")


@skill_app.command("uninstall")
def skill_uninstall_cmd(
    destination: Optional[Path] = typer.Option(
        None,
        "--to",
        help="Specific skills directory to remove from.",
    ),
    every: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Uninstall from all known agent skills locations.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview removals without touching filesystem.",
    ),
):
    """Uninstall the Nutrilog Agent Skill."""
    home = Path.home()
    targets = [_primary_target(destination, home)]

    if every:
        for marker, skills in TOOL_DIRS.values():
            target_path = home / skills / SKILL_NAME
            if target_path not in targets:
                targets.append(target_path)

    for target in targets:
        if not target.exists() and not target.is_symlink():
            continue

        if not _is_our_skill(target):
            console.print(f"[yellow]Skipping {target}: not our skill[/yellow]")
            continue

        if dry_run:
            console.print(f"[bold yellow]Would remove[/bold yellow]  {target}")
            continue

        try:
            _remove(target)
            console.print(f"[bold green]✓ Removed[/bold green] {target}")
        except Exception as e:
            err_console.print(f"[bold red]Error removing {target}:[/bold red] {e}")
            raise typer.Exit(code=1)


@skill_app.command("status")
def skill_status_cmd():
    """Show where the Nutrilog Agent Skill is installed."""
    home = Path.home()
    table = Table(title="Nutrilog Agent Skill Status", show_header=True)
    table.add_column("Location Type")
    table.add_column("Path", style="dim")
    table.add_column("Installed", justify="center")

    shared = home / SHARED_DIR / SKILL_NAME
    table.add_row(
        "Shared (.agents)",
        str(shared),
        "[green]Yes[/green]" if _is_our_skill(shared) else "[dim]No[/dim]",
    )

    for name, (marker, skills) in TOOL_DIRS.items():
        p = home / skills / SKILL_NAME
        present = _is_our_skill(p)
        table.add_row(
            name,
            str(p),
            "[green]Yes[/green]" if present else "[dim]No[/dim]",
        )

    console.print(table)
