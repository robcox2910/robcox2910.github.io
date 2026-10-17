"""The ``series`` command: sync the standard into every project, and render the hub page.

``apply_to_tree`` brings one checked-out repo onto the standard and
``check_tree`` says what would change. ``main`` is the command line: it
clones each project into ``$SERIES_SCRATCH`` (never a local checkout), applies
the standard on a branch, and opens a pull request.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from series.blocks import upsert_section_block
from series.claude_md import split_claude_md
from series.config import SERIES_FILE, Project, load_series
from series.render import TEMPLATES, apply_mkdocs_blocks, render
from series.tomledit import apply_standard_toml

BRANCH = "chore/series-standard"
COMMIT_TITLE = "chore: series standard (LICENSE, docs site, tooling, CLAUDE.md)"
COMMIT_TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PR_TRAILER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
GITHUB_OWNER = "robcox2910"
SCRATCH_ENV = "SERIES_SCRATCH"
LOCAL_ROOT = Path("/Users/robcox/development/python")
SELECT_ARRAY = re.compile(r"^\s*select\s*=\s*\[(.*?)\]", re.DOTALL | re.MULTILINE)

HOME_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Start here", ("py-os", "pebble-lang")),
    ("Storage", ("pydb", "pykv", "pydoc-db", "pygraphdb", "pytsdb", "pyvecdb", "pycoldb")),
    ("Systems", ("pycrypt", "pynet", "pyweb", "pygit", "pysearch", "pymq", "pyllm")),
    ("Putting it together", ("pystack",)),
)


@dataclass
class SyncResult:
    """What an apply did: files changed, CLAUDE.md lines moved, and a ruff note."""

    changed: list[str] = field(default_factory=lambda: list[str]())
    moved_claude_lines: list[str] = field(default_factory=lambda: list[str]())
    dropped_select_comments: bool = False


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _select_had_comments(pyproject: str) -> bool:
    """Return whether the old ruff ``select`` array contained comments."""
    match = SELECT_ARRAY.search(pyproject)
    return match is not None and "#" in match.group(1)


def _plan(
    repo_root: Path, project: Project, series: list[Project]
) -> tuple[dict[str, str], SyncResult]:
    """Work out every file the standard would write, without writing anything."""
    rendered = render(project, series, repo_root)
    updates: dict[str, str] = dict(rendered.files)
    result = SyncResult()

    readme = _read(repo_root / "README.md")
    text = f"# {project.name}\n" if readme is None else readme
    for pattern, start, end, body in rendered.blocks.get("README.md", []):
        text = upsert_section_block(
            text, heading_pattern=pattern or "", start=start, end=end, body=body
        )
    updates["README.md"] = text

    mkdocs = _read(repo_root / "mkdocs.yml")
    if mkdocs is not None:
        updates["mkdocs.yml"] = apply_mkdocs_blocks(mkdocs, rendered)

    claude = _read(repo_root / "CLAUDE.md")
    standard = (TEMPLATES / "claude_standard.md").read_text(encoding="utf-8")
    updates["CLAUDE.md"], result.moved_claude_lines = split_claude_md(
        f"# {project.name}\n" if claude is None else claude, standard
    )

    pyproject = _read(repo_root / "pyproject.toml")
    if pyproject is not None:
        updates["pyproject.toml"] = apply_standard_toml(pyproject)
        result.dropped_select_comments = _select_had_comments(pyproject) and (
            updates["pyproject.toml"] != pyproject
        )

    drift = {path: new for path, new in updates.items() if _read(repo_root / path) != new}
    return drift, result


def check_tree(repo_root: Path, project: Project, series: list[Project]) -> list[str]:
    """Return the paths that ``apply_to_tree`` would change, writing nothing."""
    drift, _ = _plan(repo_root, project, series)
    return list(drift)


def apply_to_tree(repo_root: Path, project: Project, series: list[Project]) -> SyncResult:
    """Bring ``repo_root`` onto the standard, writing only the files that change.

    Steps: render the standard; collect the owned files, the README blocks, the
    mkdocs blocks, the standard CLAUDE.md (moving project-specific lines under
    ``## Project notes``) and the pyproject keys; then write each file whose
    content differs. A second run changes nothing.
    """
    drift, result = _plan(repo_root, project, series)
    for path, content in drift.items():
        target = repo_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    result.changed = list(drift)
    return result


def render_home(series: list[Project]) -> str:
    """Return the hub's ``docs/index.md``: a learning path with one card per project."""
    by_repo = {p.repo: p for p in series}
    grouped = {repo for _, repos in HOME_GROUPS for repo in repos}
    lines = [
        "# From scratch in Python",
        "",
        "Seventeen projects that build real systems from scratch, to teach how they work.",
        "",
    ]
    for title, repos in HOME_GROUPS:
        members = [by_repo[r] for r in repos if r in by_repo]
        if title == "Systems":
            members += [p for p in series if p.repo not in grouped]
        lines += [f"## {title}", "", '<div class="grid cards" markdown>', ""]
        for p in members:
            builds = f" Builds on {', '.join(p.builds_on)}." if p.builds_on else ""
            lines += [
                f"- **[{p.name}]({p.site_url})**",
                "",
                f"    {p.teaches}.{builds} [Source]({p.github_url})",
                "",
            ]
        lines += ["</div>", ""]
    return "\n".join(lines)


def _run(cmd: list[str], cwd: Path | None = None) -> str:  # pragma: no cover
    """Run a git or gh command and return its output; raise on failure."""
    done = subprocess.run(  # noqa: S603 - fixed argument lists, no shell
        cmd, cwd=cwd, check=True, capture_output=True, text=True
    )
    return done.stdout


def _pr_body(result: SyncResult) -> str:
    lines = ["Brings this repo onto the shared series standard.", "", "## Changed files", ""]
    lines += [f"- `{path}`" for path in result.changed]
    lines += ["", "## CLAUDE.md lines moved into `## Project notes`", ""]
    lines += [f"- `{line.strip()}`" for line in result.moved_claude_lines] or ["- none"]
    if result.dropped_select_comments:
        lines += [
            "",
            "## pyproject.toml",
            "",
            (
                "The old ruff `select` array contained comments; they were dropped "
                "because the new `select` is the series standard."
            ),
        ]
    return "\n".join([*lines, "", PR_TRAILER])


def _sync_one(  # pragma: no cover
    project: Project, series: list[Project], scratch: Path, *, check: bool
) -> bool:
    """Sync one project in a fresh clone; return whether it had drift."""
    clone = scratch / project.repo
    _run(
        [
            "gh", "repo", "clone", f"{GITHUB_OWNER}/{project.repo}", str(clone),
            "--", "--depth", "50",
        ]
    )  # fmt: skip
    if check:
        drift = check_tree(clone, project, series)
        for path in drift:
            print(f"{project.repo}: drift in {path}")  # noqa: T201
        if not drift:
            print(f"{project.repo}: clean")  # noqa: T201
        return bool(drift)
    _run(["git", "switch", "-c", BRANCH], clone)
    result = apply_to_tree(clone, project, series)
    if not result.changed:
        print(f"{project.repo}: already on the standard")  # noqa: T201
        return False
    _run(["git", "add", "-A"], clone)
    _run(["git", "commit", "-m", f"{COMMIT_TITLE}\n\n{COMMIT_TRAILER}"], clone)
    _run(["git", "push", "-u", "origin", BRANCH], clone)
    url = _run(["gh", "pr", "create", "--title", COMMIT_TITLE, "--body", _pr_body(result)], clone)
    print(f"{project.repo}: {url.strip()}")  # noqa: T201
    return False


def _is_local_checkout(scratch: Path, series: list[Project]) -> bool:
    """Return whether ``scratch`` is, or is inside, one of the projects' local folders."""
    resolved = scratch.resolve()
    return any(
        resolved.is_relative_to(LOCAL_ROOT / p.folder)
        or resolved.is_relative_to(LOCAL_ROOT / p.repo)
        for p in series
    )


def _cmd_sync(args: argparse.Namespace) -> int:
    scratch_env = os.environ.get(SCRATCH_ENV)
    if not scratch_env:
        print(f"error: {SCRATCH_ENV} must be set to a scratch folder", file=sys.stderr)  # noqa: T201
        return 2
    series = load_series()
    scratch = Path(scratch_env)
    if _is_local_checkout(scratch, series):
        print(f"error: {SCRATCH_ENV} must not be a local checkout", file=sys.stderr)  # noqa: T201
        return 2
    scratch.mkdir(parents=True, exist_ok=True)
    chosen = [p for p in series if args.repo in (None, p.repo)]
    if not chosen:
        print(f"error: no project with repo {args.repo!r}", file=sys.stderr)  # noqa: T201
        return 2
    drifted = [_sync_one(p, series, scratch, check=args.check) for p in chosen]
    return 1 if args.check and any(drifted) else 0


def _cmd_home(args: argparse.Namespace) -> int:
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_home(load_series()), encoding="utf-8")
    print(f"wrote {target}")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``series`` command line."""
    parser = argparse.ArgumentParser(prog="series")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="apply the standard to every project")
    sync.add_argument("--check", action="store_true", help="report drift, change nothing")
    sync.add_argument("--repo", help="only this GitHub repo name")
    sync.set_defaults(run=_cmd_sync)
    home = commands.add_parser("home", help="render the hub's docs/index.md")
    home.add_argument("--output", default=str(SERIES_FILE.parent / "docs" / "index.md"))
    home.set_defaults(run=_cmd_home)
    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
