"""Integration tests for Nutrilog's shared agentcli skill commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from nutrilog.cli import app

SKILL_NAME = "nutrilog"
SHARED_DIR = Path(".agents") / "skills"

runner = CliRunner()


@pytest.fixture
def mock_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def test_packaged_skill_exists():
    path = Path(__file__).resolve().parents[1] / "SKILL.md"
    assert path.exists()
    assert path.is_file()
    assert "name: nutrilog" in path.read_text(encoding="utf-8")


def test_packaged_skill_guides_entry_granularity():
    content = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Choosing Entry Granularity" in content
    assert "Prefer the fewest entries" in content
    assert "Do not split a recipe into every ingredient" in content


def test_cli_skill_install_dry_run(mock_home: Path):
    dest = mock_home / "agent_skills"
    result = runner.invoke(
        app, ["skill", "install", "--to", str(dest), "--dry-run"]
    )
    assert result.exit_code == 0
    assert "would install" in result.stdout
    assert not dest.exists()


def test_cli_skill_install_and_status(mock_home: Path):
    dest = mock_home / "agent_skills"
    result = runner.invoke(app, ["skill", "install", "--to", str(dest)])
    assert result.exit_code == 0
    assert "copied" in result.stdout or "linked" in result.stdout
    assert (dest / SKILL_NAME / "SKILL.md").exists()

    status_result = runner.invoke(app, ["skill", "status"])
    assert status_result.exit_code == 0
    assert "Shared (.agents)" in status_result.stdout


def test_cli_skill_uninstall(mock_home: Path):
    dest = mock_home / "agent_skills"
    # Install first
    runner.invoke(app, ["skill", "install", "--to", str(dest)])
    assert (dest / SKILL_NAME).exists()

    # Uninstall
    result = runner.invoke(app, ["skill", "uninstall", "--to", str(dest)])
    assert result.exit_code == 0
    assert "removed" in result.stdout
    assert not (dest / SKILL_NAME).exists()


def test_single_skill_manifest_in_source_tree():
    """One manifest only; a second copy silently drifts from the real one.

    A duplicate under nutrilog/skills/ shipped stale docs for two releases
    because it had to be updated by hand alongside the root manifest. The
    wheel build maps the root file into place instead.
    """
    root = Path(__file__).resolve().parents[1]
    skipped = {
        ".venv",
        ".git",
        "dist",
        "build",
        ".pytest_cache",
        ".ruff_cache",
    }
    found = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("SKILL.md")
        if not skipped & set(p.parts)
    )

    assert found == ["SKILL.md"], f"duplicate manifests drift: {found}"
