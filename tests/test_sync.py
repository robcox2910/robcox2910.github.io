"""Tests for the sync command, on fake repos in a temporary folder."""

import hashlib
from pathlib import Path

import pytest

import series.sync as sync_module
from series.blocks import BlockError
from series.config import Project, load_series
from series.render import TEMPLATES
from series.sync import (
    SyncError,
    SyncResult,
    _pr_body,
    apply_to_tree,
    check_tree,
    main,
    render_home,
)

GROUPS = 4
FAILED = 2
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


def test_sync_writes_conftest_and_leaves_tests_conftest_alone(tmp_path: Path) -> None:
    """The root conftest.py is owned; a repo's own tests/conftest.py never is."""
    repo = make_repo(tmp_path)
    own = repo / "tests" / "conftest.py"
    own.parent.mkdir()
    own.write_bytes(b"# mine\nimport pytest\n")
    apply_to_tree(repo, PYDB, SERIES)
    template = TEMPLATES / "conftest.py"
    assert (repo / "conftest.py").read_text(encoding="utf-8") == template.read_text(
        encoding="utf-8"
    )
    assert own.read_bytes() == b"# mine\nimport pytest\n"
    before = snapshot(repo)
    result = apply_to_tree(repo, PYDB, SERIES)
    assert snapshot(repo) == before
    assert result.changed == []


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


def _fake_run(calls: list[list[str]], failing_repo: str | None = None):
    """Return a stand-in for ``_run`` that makes empty clones and can fail one."""

    def run(cmd: list[str], cwd: Path | None = None) -> str:  # noqa: ARG001
        calls.append(cmd)
        if cmd[:3] == ["gh", "repo", "clone"]:
            if cmd[3].endswith(f"/{failing_repo}"):
                msg = "gh repo clone failed: boom"
                raise SyncError(msg)
            Path(cmd[4]).mkdir(parents=True)
        return ""

    return run


def test_failed_repo_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One repo failing is reported by name, the next still runs, and the exit code is 2."""
    calls: list[list[str]] = []
    monkeypatch.setenv("SERIES_SCRATCH", str(tmp_path))
    monkeypatch.setattr(sync_module, "load_series", lambda: [SERIES[1], SERIES[2]])
    monkeypatch.setattr(sync_module, "_run", _fake_run(calls, failing_repo="pebble-lang"))
    assert main(["sync", "--check"]) == FAILED
    out = capsys.readouterr()
    assert "pebble-lang: gh repo clone failed: boom" in out.err
    assert any(c[:3] == ["gh", "repo", "clone"] and c[3].endswith("/pydb") for c in calls)
    assert "pydb: drift in" in out.out


def test_existing_scratch_clone_is_reported_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A leftover clone folder is a failure for that repo and is left alone."""
    calls: list[list[str]] = []
    (tmp_path / "pydb").mkdir()
    (tmp_path / "pydb" / "keep.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("SERIES_SCRATCH", str(tmp_path))
    monkeypatch.setattr(sync_module, "_run", _fake_run(calls))
    assert main(["sync", "--check", "--repo", "pydb"]) == FAILED
    assert "pydb: scratch clone exists" in capsys.readouterr().err
    assert calls == []
    assert (tmp_path / "pydb" / "keep.txt").read_text(encoding="utf-8") == "x"


def test_pr_is_created_with_explicit_repo_base_and_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A single-branch clone has no tracking ref, so ``gh pr create`` must name everything."""
    calls: list[list[str]] = []

    def run(cmd: list[str], cwd: Path | None = None) -> str:  # noqa: ARG001
        calls.append(cmd)
        if cmd[:3] == ["gh", "repo", "clone"]:
            dest = Path(cmd[4])
            dest.mkdir()
            make_repo(dest)
        return "https://example.invalid/pr/1"

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(sync_module, "_run", run)
    sync_module._sync_one(PYDB, SERIES, scratch, check=False)
    (create,) = [c for c in calls if c[:3] == ["gh", "pr", "create"]]

    def flag(name: str) -> str:
        return create[create.index(name) + 1]

    assert flag("--repo") == f"robcox2910/{PYDB.repo}"
    assert flag("--base") == "main"
    assert flag("--head") == sync_module.BRANCH


def test_first_sync_reports_replaced_readme_lines(tmp_path: Path) -> None:
    """README lines replaced by the fallback are recorded and listed in the PR body."""
    repo = make_repo(tmp_path)
    readme = "# PyDB\n\n## Related projects\n\n- [PyKV](x)\n\nMy notes.\n\n## License\n\nMIT\n"
    (repo / "README.md").write_text(readme, encoding="utf-8")
    result = apply_to_tree(repo, PYDB, SERIES)
    assert result.replaced_readme_lines == ["## Related projects", "- [PyKV](x)"]
    assert "My notes." in (repo / "README.md").read_text(encoding="utf-8")
    body = _pr_body(result)
    assert "README lines replaced" in body
    assert "`- [PyKV](x)`" in body


DRIFT = 1


def test_unexpected_error_in_one_repo_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Any error in one repo (not just SyncError) is that repo's failure, and the run goes on."""
    monkeypatch.setenv("SERIES_SCRATCH", str(tmp_path))
    monkeypatch.setattr(sync_module, "load_series", lambda: [SERIES[1], SERIES[2]])
    monkeypatch.setattr(sync_module, "_run", _fake_run([]))
    real_check = sync_module.check_tree

    def check(repo_root: Path, project: Project, series: list[Project]) -> list[str]:
        if project.repo == "pebble-lang":
            msg = "expected exactly one marker"
            raise BlockError(msg)
        return real_check(repo_root, project, series)

    monkeypatch.setattr(sync_module, "check_tree", check)
    assert main(["sync", "--check"]) == FAILED
    out = capsys.readouterr()
    assert "pebble-lang: BlockError: expected exactly one marker" in out.err
    assert "pydb: drift in" in out.out


def test_check_with_drift_and_no_failures_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--check`` exits 1 when a repo drifts and nothing failed."""
    monkeypatch.setenv("SERIES_SCRATCH", str(tmp_path))
    monkeypatch.setattr(sync_module, "_run", _fake_run([]))
    assert main(["sync", "--check", "--repo", "pydb"]) == DRIFT
    assert "pydb: drift in" in capsys.readouterr().out


def _repo_runner(calls: list[list[str]], *, lock: bool = True):
    """Return a ``_run`` stand-in that clones a fake repo and records every call.

    ``uv lock`` writes a ``uv.lock`` in the clone (when ``lock``), as the real one would.
    """

    def run(cmd: list[str], cwd: Path | None = None) -> str:
        calls.append(cmd)
        if cmd[:3] == ["gh", "repo", "clone"]:
            dest = Path(cmd[4])
            dest.mkdir()
            make_repo(dest)
            (dest / "uv.lock").write_text("old lock\n", encoding="utf-8")
        elif cmd[:2] == ["uv", "lock"] and lock and cwd is not None:
            (cwd / "uv.lock").write_text("new lock\n", encoding="utf-8")
        return "https://example.invalid/pr/1"

    return run


def test_sync_relocks_when_pyproject_changes_and_commits_the_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``uv lock`` runs after the files are written and before ``git add``."""
    calls: list[list[str]] = []
    monkeypatch.setattr(sync_module, "_run", _repo_runner(calls))
    sync_module._sync_one(PYDB, SERIES, tmp_path, check=False)
    names = [c[0:2] for c in calls]
    assert ["uv", "lock"] in names
    assert names.index(["uv", "lock"]) < names.index(["git", "add"])
    assert (tmp_path / PYDB.repo / "uv.lock").read_text(encoding="utf-8") == "new lock\n"


def test_sync_does_not_relock_when_pyproject_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No pyproject change, no ``uv lock``."""
    calls: list[list[str]] = []
    clone = tmp_path / PYDB.repo
    clone.mkdir()
    make_repo(clone)
    apply_to_tree(clone, PYDB, SERIES)
    (clone / "README.md").write_text("# PyDB\n", encoding="utf-8")
    (clone / "uv.lock").write_text("old lock\n", encoding="utf-8")
    monkeypatch.setattr(sync_module, "_run", _repo_runner(calls))
    result = apply_to_tree(clone, PYDB, SERIES)
    assert "pyproject.toml" not in result.changed
    sync_module._refresh_lock(clone, result)
    assert not any(c[:2] == ["uv", "lock"] for c in calls)
    assert "uv.lock" not in result.changed


def _check_runner(monkeypatch: pytest.MonkeyPatch, *, on_standard: bool, stale: bool) -> None:
    """Fake a clone for ``--check``: optionally already on the standard, lock stale or not."""

    def run(cmd: list[str], cwd: Path | None = None) -> str:  # noqa: ARG001
        if cmd[:3] == ["gh", "repo", "clone"]:
            dest = Path(cmd[4])
            dest.mkdir()
            make_repo(dest)
            if on_standard:
                apply_to_tree(dest, PYDB, SERIES)
            (dest / "uv.lock").write_text("lock\n", encoding="utf-8")
        return ""

    monkeypatch.setattr(sync_module, "_run", run)

    def lock_is_stale(root: Path) -> bool:  # noqa: ARG001
        return stale

    monkeypatch.setattr(sync_module, "_lock_is_stale", lock_is_stale)


def test_check_reports_a_stale_lock_as_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With pyproject on the standard but ``uv.lock`` stale, ``--check`` names the lock."""
    _check_runner(monkeypatch, on_standard=True, stale=True)
    assert sync_module._sync_one(PYDB, SERIES, tmp_path, check=True) is True
    assert "pydb: drift in uv.lock" in capsys.readouterr().out


def test_check_is_clean_when_the_lock_is_fresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fresh lock on a repo already on the standard is clean."""
    _check_runner(monkeypatch, on_standard=True, stale=False)
    assert sync_module._sync_one(PYDB, SERIES, tmp_path, check=True) is False
    assert "pydb: clean" in capsys.readouterr().out


def test_check_flags_the_lock_when_pyproject_will_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pyproject that will change also means the lock will, whatever it says now."""
    _check_runner(monkeypatch, on_standard=False, stale=False)
    assert sync_module._sync_one(PYDB, SERIES, tmp_path, check=True) is True
    assert "pydb: drift in uv.lock" in capsys.readouterr().out


def test_unchanged_lock_is_not_listed_as_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If ``uv lock`` leaves ``uv.lock`` identical, it is not reported as changed."""
    clone = tmp_path / PYDB.repo
    clone.mkdir()
    make_repo(clone)
    (clone / "uv.lock").write_text("same\n", encoding="utf-8")
    result = apply_to_tree(clone, PYDB, SERIES)
    assert "pyproject.toml" in result.changed
    monkeypatch.setattr(sync_module, "_run", lambda cmd, cwd=None: "")  # noqa: ARG005
    sync_module._refresh_lock(clone, result)
    assert "uv.lock" not in result.changed
