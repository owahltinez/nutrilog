"""Unit tests for nutrilog.skill."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nutrilog.cli import app
from nutrilog.skill import (
    SHARED_DIR,
    SKILL_NAME,
    _is_our_skill,
    _place,
    _primary_target,
    detected_tools,
    packaged_skill,
)

runner = CliRunner()


@pytest.fixture
def mock_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def test_packaged_skill_exists():
    path = packaged_skill()
    assert path.exists()
    assert path.is_file()
    assert "name: nutrilog" in path.read_text(encoding="utf-8")


def test_detected_tools_empty(mock_home: Path):
    assert detected_tools(mock_home) == {}


def test_detected_tools_present(mock_home: Path):
    (mock_home / ".gemini").mkdir()
    (mock_home / ".claude").mkdir()

    found = detected_tools(mock_home)
    assert "Gemini / Jetski" in found
    assert "Gemini CLI" in found
    assert "Claude Code" in found


def test_primary_target(mock_home: Path):
    target = _primary_target(None, mock_home)
    assert target == mock_home / SHARED_DIR / SKILL_NAME

    custom = mock_home / "custom_skills"
    assert _primary_target(custom, mock_home) == custom / SKILL_NAME


def test_place_and_is_our_skill(mock_home: Path):
    source = packaged_skill()
    target = mock_home / "test_skills" / SKILL_NAME

    assert not _is_our_skill(target)
    msg = _place(source, target, link=False, force=False)
    assert "Copied" in msg
    assert (target / "SKILL.md").is_file()
    assert _is_our_skill(target)

    # Refuse overwrite without --force
    with pytest.raises(ValueError, match="already exists"):
        _place(source, target, link=False, force=False)

    # Overwrite with force
    msg_force = _place(source, target, link=False, force=True)
    assert "Copied" in msg_force


def test_place_symlink(mock_home: Path):
    source = packaged_skill()
    target = mock_home / "linked_skills" / SKILL_NAME

    msg = _place(source, target, link=True, force=False)
    assert "Linked" in msg or "Copied" in msg
    assert _is_our_skill(target)


def test_cli_skill_install_dry_run(mock_home: Path):
    dest = mock_home / "agent_skills"
    result = runner.invoke(
        app, ["skill", "install", "--to", str(dest), "--dry-run"]
    )
    assert result.exit_code == 0
    assert "Would install" in result.stdout
    assert not dest.exists()


def test_cli_skill_install_and_status(mock_home: Path):
    dest = mock_home / "agent_skills"
    result = runner.invoke(app, ["skill", "install", "--to", str(dest)])
    assert result.exit_code == 0
    assert "Copied" in result.stdout or "Linked" in result.stdout
    assert (dest / SKILL_NAME / "SKILL.md").exists()

    status_result = runner.invoke(app, ["skill", "status"])
    assert status_result.exit_code == 0
    assert "Nutrilog Agent Skill Status" in status_result.stdout


def test_cli_skill_uninstall(mock_home: Path):
    dest = mock_home / "agent_skills"
    # Install first
    runner.invoke(app, ["skill", "install", "--to", str(dest)])
    assert (dest / SKILL_NAME).exists()

    # Uninstall
    result = runner.invoke(app, ["skill", "uninstall", "--to", str(dest)])
    assert result.exit_code == 0
    assert "Removed" in result.stdout
    assert not (dest / SKILL_NAME).exists()


def test_single_skill_manifest_in_source_tree():
    """One manifest only; a second copy silently drifts from the real one.

    A duplicate under nutrilog/skills/ shipped stale docs for two releases
    because it had to be updated by hand alongside the root manifest. The
    wheel build maps the root file into place instead.
    """
    root = Path(__file__).resolve().parents[1]
    skipped = {".venv", ".git", "dist", "build", ".pytest_cache", ".ruff_cache"}
    found = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("SKILL.md")
        if not skipped & set(p.parts)
    )

    assert found == ["SKILL.md"], f"duplicate manifests drift: {found}"
