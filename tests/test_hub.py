"""Tests for keeping the hub itself (home page, README, mkdocs nav) in step with series.yml."""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import series.sync as sync_module
from series.config import SERIES_FILE, SeriesError, load_series
from series.sync import HUB_FILES, check_hub, main, render_home

SERIES = load_series()
ROOT = SERIES_FILE.parent
DRIFT = 1
FAILED = 2


def copy_hub(tmp_path: Path) -> Path:
    """Copy the hub's generated files into ``tmp_path`` and return it."""
    for name in HUB_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_committed_hub_matches_series_yml() -> None:
    """The committed home page, README blocks, CLAUDE.md standard and nav are fresh.

    If this fails, run ``uv run series hub`` and commit the result.
    """
    assert check_hub(ROOT, SERIES) == []


def test_hub_command_regenerates_stale_files(tmp_path: Path) -> None:
    """``series hub`` rewrites a stale index, README table and nav, and nothing else."""
    hub = copy_hub(tmp_path)
    (hub / "docs" / "index.md").write_text("# Old\n", encoding="utf-8")
    readme = (hub / "README.md").read_text(encoding="utf-8")
    (hub / "README.md").write_text(readme.replace("| PyKV |", "| PyKVOLD |"), encoding="utf-8")
    mkdocs = (hub / "mkdocs.yml").read_text(encoding="utf-8")
    (hub / "mkdocs.yml").write_text(mkdocs.replace("- PyKV:", "- Old:"), encoding="utf-8")
    assert sorted(check_hub(hub, SERIES)) == ["README.md", "docs/index.md", "mkdocs.yml"]
    assert main(["hub", "--root", str(hub)]) == 0
    assert check_hub(hub, SERIES) == []
    written = sorted(str(p.relative_to(hub)) for p in hub.rglob("*") if p.is_file())
    assert written == sorted(HUB_FILES)
    for name in HUB_FILES:
        assert (hub / name).read_text(encoding="utf-8") == (ROOT / name).read_text(encoding="utf-8")


def test_hub_check_reports_drift_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``series hub --check`` exits 1 on drift and leaves the files alone."""
    hub = copy_hub(tmp_path)
    (hub / "docs" / "index.md").write_text("# Old\n", encoding="utf-8")
    assert main(["hub", "--check", "--root", str(hub)]) == DRIFT
    assert "hub: drift in docs/index.md" in capsys.readouterr().out
    assert (hub / "docs" / "index.md").read_text(encoding="utf-8") == "# Old\n"
    shutil.copyfile(ROOT / "docs" / "index.md", hub / "docs" / "index.md")
    assert main(["hub", "--check", "--root", str(hub)]) == 0


def test_hub_blocks_have_no_current_project(tmp_path: Path) -> None:
    """The hub is not a project, so nothing is bold or marked "you are here"."""
    hub = copy_hub(tmp_path)
    main(["hub", "--root", str(hub)])
    readme = (hub / "README.md").read_text(encoding="utf-8")
    assert "| **" not in readme
    assert "You are here" not in (hub / "mkdocs.yml").read_text(encoding="utf-8")


def test_home_count_comes_from_series_yml() -> None:
    """The project count is worked out from series.yml, never a written-out number."""
    assert f"A series of {len(SERIES)} projects" in render_home(SERIES)
    assert "A series of 3 projects" in render_home(SERIES[:3])


def test_ungrouped_project_is_an_error() -> None:
    """A project missing from HOME_GROUPS is an error that says how to fix it."""
    newcomer = replace(SERIES[0], name="PyNew", repo="pynew", folder="pynew")
    with pytest.raises(SeriesError, match=r"pynew.*HOME_GROUPS"):
        render_home([*SERIES, newcomer])


def test_hub_command_reports_ungrouped_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``series hub`` exits 2 with the message instead of a traceback."""
    newcomer = replace(SERIES[0], name="PyNew", repo="pynew", folder="pynew")
    monkeypatch.setattr(sync_module, "load_series", lambda: [*SERIES, newcomer])
    assert main(["hub", "--root", str(copy_hub(tmp_path))]) == FAILED
    assert "pynew" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("CLAUDE.md", "# No markers\n", "standard:start"),
        ("mkdocs.yml", None, "needs both mkdocs.yml and CLAUDE.md"),
    ],
)
def test_hub_command_reports_a_broken_hub(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    content: str | None,
    message: str,
) -> None:
    """A hub file without its markers, or missing, is an error rather than a guess."""
    hub = copy_hub(tmp_path)
    if content is None:
        (hub / name).unlink()
    else:
        (hub / name).write_text(content, encoding="utf-8")
    assert main(["hub", "--root", str(hub)]) == FAILED
    assert message in capsys.readouterr().err


def test_hub_command_reports_up_to_date(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A fresh hub is left alone and says so."""
    hub = copy_hub(tmp_path)
    assert main(["hub", "--root", str(hub)]) == 0
    assert "hub: up to date" in capsys.readouterr().out
