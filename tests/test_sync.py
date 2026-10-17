"""Tests for the sync command, on fake repos in a temporary folder."""

import hashlib
from pathlib import Path

import pytest

from series.config import load_series
from series.sync import SyncResult, _pr_body, apply_to_tree, check_tree, main, render_home

GROUPS = 4
SERIES = load_series()
PYDB = SERIES[2]
OLD_CLAUDE = """# Claude Code Instructions

## Overview

PyDB is a database.

## Linting

- Ruff enforces a comprehensive rule set
- Never mutate the catalog outside a transaction

## Testing

- Minimum 80% coverage enforced by pytest-cov
"""
OLD_PYPROJECT = """[project]
name = "pydb"

[tool.ruff.lint]
select = [
    "E",  # pycodestyle
    "F",
]
"""
EXTRA = b"print('mine')\n\xff\x00"


def make_repo(tmp_path: Path) -> Path:
    """Build a small fake repo with an unowned extra file."""
    (tmp_path / "pyproject.toml").write_text(OLD_PYPROJECT, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(OLD_CLAUDE, encoding="utf-8")
    (tmp_path / "README.md").write_text("# PyDB\n\nHello.\n\n## License\n\nMIT\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "extra.py").write_bytes(EXTRA)
    return tmp_path


def snapshot(root: Path) -> dict[str, str]:
    """Hash every file under ``root``."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_apply_twice_is_idempotent(tmp_path: Path) -> None:
    """A second apply changes nothing."""
    repo = make_repo(tmp_path)
    first = apply_to_tree(repo, PYDB, SERIES)
    assert first.changed
    after_first = snapshot(repo)
    second = apply_to_tree(repo, PYDB, SERIES)
    assert second.changed == []
    assert second.moved_claude_lines == []
    assert snapshot(repo) == after_first


def test_check_reports_drift_then_clean_after_apply(tmp_path: Path) -> None:
    """Check lists paths without writing, and is empty once applied."""
    repo = make_repo(tmp_path)
    before = snapshot(repo)
    drift = check_tree(repo, PYDB, SERIES)
    assert "LICENSE" in drift
    assert "CLAUDE.md" in drift
    assert "pyproject.toml" in drift
    assert snapshot(repo) == before
    apply_to_tree(repo, PYDB, SERIES)
    assert check_tree(repo, PYDB, SERIES) == []


def test_unowned_files_untouched(tmp_path: Path) -> None:
    """Files the sync does not own keep their exact bytes."""
    repo = make_repo(tmp_path)
    apply_to_tree(repo, PYDB, SERIES)
    assert (repo / "src" / "extra.py").read_bytes() == EXTRA


def test_moved_lines_reported(tmp_path: Path) -> None:
    """Project-specific CLAUDE.md lines are reported, and ruff comments are flagged."""
    repo = make_repo(tmp_path)
    result = apply_to_tree(repo, PYDB, SERIES)
    assert "- Never mutate the catalog outside a transaction" in result.moved_claude_lines
    assert result.dropped_select_comments is True
    assert "Never mutate the catalog" in (repo / "CLAUDE.md").read_text(encoding="utf-8")


def test_missing_claude_md_is_created(tmp_path: Path) -> None:
    """A repo with no CLAUDE.md gets an H1 plus the block."""
    apply_to_tree(tmp_path, PYDB, SERIES)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# PyDB")
    assert "<!-- standard:start -->" in text


def test_cli_refuses_without_scratch_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sync exits non-zero with a clear message when SERIES_SCRATCH is unset."""
    monkeypatch.delenv("SERIES_SCRATCH", raising=False)
    assert main(["sync", "--check"]) != 0
    assert "SERIES_SCRATCH" in capsys.readouterr().err


def test_home_page_shape() -> None:
    """The hub page groups the projects and has one card per project."""
    text = render_home(SERIES)
    for heading in ("Start here", "Storage", "Systems", "Putting it together"):
        assert f"## {heading}" in text
    assert text.count('<div class="grid cards"') == GROUPS
    for project in SERIES:
        assert project.site_url in text


def test_pr_body_lists_files_moves_and_dropped_comments() -> None:
    """The PR body names changed files, moved lines and the dropped ruff comments."""
    body = _pr_body(SyncResult(["LICENSE"], ["- a rule"], dropped_select_comments=True))
    assert "`LICENSE`" in body
    assert "`- a rule`" in body
    assert "comments" in body


def test_cli_refuses_local_checkout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scratch folder inside a project's local folder is refused."""
    monkeypatch.setenv("SERIES_SCRATCH", "/Users/robcox/development/python/pydb/scratch")
    assert main(["sync", "--check"]) != 0
    assert "local checkout" in capsys.readouterr().err


def test_cli_unknown_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown --repo exits non-zero before cloning anything."""
    monkeypatch.setenv("SERIES_SCRATCH", str(tmp_path))
    assert main(["sync", "--repo", "nope"]) != 0
    assert "no project" in capsys.readouterr().err


def test_home_command_writes_file(tmp_path: Path) -> None:
    """``series home --output`` writes the rendered page."""
    out = tmp_path / "docs" / "index.md"
    assert main(["home", "--output", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == render_home(SERIES)
