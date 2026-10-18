"""The ``series`` command: sync the standard into every project, and keep the hub fresh.

``apply_to_tree`` brings one checked-out repo onto the standard and
``check_tree`` says what would change. ``main`` is the command line:
``series sync`` clones each project into ``$SERIES_SCRATCH`` (never a local
checkout), applies the standard on a branch, and opens a pull request;
``series hub`` regenerates the hub's own home page, README blocks, CLAUDE.md
standard, mkdocs nav and property-testing page from ``series.yml`` (``check_hub`` says what would change).
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from series.blocks import BlockError, replace_block, upsert_section_block_with_removed
from series.claude_md import split_claude_md
from series.config import SERIES_FILE, SITE_ROOT, Project, SeriesError, load_series
from series.render import TEMPLATES, Rendered, apply_mkdocs_blocks, render, render_hub
from series.tomledit import apply_standard_toml

BRANCH = "chore/series-standard"
COMMIT_TITLE = "chore: series standard (LICENSE, docs site, tooling, CLAUDE.md)"
COMMIT_TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PR_TRAILER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
GITHUB_OWNER = "robcox2910"
SCRATCH_ENV = "SERIES_SCRATCH"
LOCAL_ROOT = Path("/Users/robcox/development/python")
SELECT_ARRAY = re.compile(r"^\s*select\s*=\s*\[(.*?)\]", re.DOTALL | re.MULTILINE)

HUB_ROOT = SERIES_FILE.parent
HUB_FILES = ("README.md", "CLAUDE.md", "mkdocs.yml", "docs/index.md", "docs/property-testing.md")

# The home page's learning-path groups. Every project in series.yml must be in
# exactly one group: a new project goes here too, or `series hub` fails.
HOME_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Start here", ("py-os", "pebble-lang")),
    ("Storage", ("pydb", "pykv", "pydoc-db", "pygraphdb", "pytsdb", "pyvecdb", "pycoldb")),
    ("Systems", ("pycrypt", "pynet", "pyweb", "pygit", "pysearch", "pymq", "pyllm")),
    ("Putting it together", ("pystack",)),
)


class SyncError(Exception):
    """Raised when a step for one repo fails (a git or gh call, or a leftover clone)."""


@dataclass
class SyncResult:
    """What an apply did: files changed, lines moved or replaced, and a ruff note."""

    changed: list[str] = field(default_factory=lambda: list[str]())
    moved_claude_lines: list[str] = field(default_factory=lambda: list[str]())
    dropped_select_comments: bool = False
    replaced_readme_lines: list[str] = field(default_factory=lambda: list[str]())


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
        text, removed = upsert_section_block_with_removed(
            text, heading_pattern=pattern or "", start=start, end=end, body=body
        )
        result.replaced_readme_lines += removed
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
    """Return the hub's ``docs/index.md``: a learning path with one card per project.

    Raises ``SeriesError`` when a project is in no ``HOME_GROUPS`` group, so a
    new project can never land on the page in the wrong place by default.
    """
    by_repo = {p.repo: p for p in series}
    grouped = {repo for _, repos in HOME_GROUPS for repo in repos}
    ungrouped = [p.repo for p in series if p.repo not in grouped]
    if ungrouped:
        msg = (
            f"no home-page group for {', '.join(ungrouped)}: "
            "add each to HOME_GROUPS in src/series/sync.py"
        )
        raise SeriesError(msg)
    intro = (
        f"A series of {len(series)} projects that build real systems from scratch, "
        "to teach how they work."
    )
    lines = [
        "# From scratch in Python",
        "",
        intro,
        "",
    ]
    for title, repos in HOME_GROUPS:
        members = [by_repo[r] for r in repos if r in by_repo]
        if not members:
            continue
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


# The opening of the hub's property-testing page: the idea, explained once.
PROPERTY_INTRO = """\
# Property Testing

Every project in the series is checked with **property-based tests**. Here's
the idea, once, and then a list of where to see it in action.

## The idea

Imagine you've built a vending machine. The usual way to check it: put in
a pound, press B4, and see a packet of crisps drop out. That's an **example
test**. It's useful, but it only tells you about the one snack you thought
of.

Now imagine a mischievous tester. All night they press every button there is:
coins and no coins, two buttons at once, a snack that's sold out, the same
button forty times. For each go they check a single rule, such as:

> Whatever you press, the money you put in always equals the price of what
> came out plus the change you got back.

That rule is a **property**. It doesn't say which snack comes out. It says
something that must be true *every* time, whatever happens.

When the tester finds something that breaks the rule, they don't just write
"it went wrong after about a hundred presses". They play it again with less
and less -- fewer coins, fewer buttons, smaller numbers -- checking it still
goes wrong each time, until it's as simple as it can be. That boiling-down is
called **shrinking**, and it's the best part: the smallest failing input
usually points straight at the bug.

In Python, the tester is a library called
[Hypothesis](https://hypothesis.readthedocs.io/). Each project has a page
that walks through one of its properties, line by line.

## A property from every project

In learning order, each with the rule its page walks through:

"""


def render_property_page(series: list[Project]) -> str:
    """Return the hub's ``docs/property-testing.md``: the idea, then every project's page."""
    lines = [
        f"- **[{p.name}]({SITE_ROOT}/{p.repo}/property-testing/)**: {p.property}" for p in series
    ]
    return PROPERTY_INTRO + "\n".join(lines) + "\n"


def _plan_hub(root: Path, series: list[Project]) -> dict[str, str]:
    """Return every hub file whose content differs from what ``series.yml`` renders."""
    rendered = render_hub(series)
    updates = {
        "docs/index.md": render_home(series),
        "docs/property-testing.md": render_property_page(series),
    }
    readme = _read(root / "README.md") or "# Series home\n"
    for pattern, start, end, body in rendered.blocks["README.md"]:
        readme, _ = upsert_section_block_with_removed(
            readme, heading_pattern=pattern or "", start=start, end=end, body=body
        )
    updates["README.md"] = readme
    mkdocs, claude = _read(root / "mkdocs.yml"), _read(root / "CLAUDE.md")
    if mkdocs is None or claude is None:
        msg = f"the hub at {root} needs both mkdocs.yml and CLAUDE.md"
        raise SeriesError(msg)
    updates["mkdocs.yml"] = apply_mkdocs_blocks(mkdocs, rendered)
    updates["CLAUDE.md"] = _replace_standard(claude, rendered)
    return {path: new for path, new in updates.items() if _read(root / path) != new}


def _replace_standard(text: str, rendered: Rendered) -> str:
    """Refresh the hub's CLAUDE.md standard block, which must already be marked."""
    (_, start, end, body), *_ = rendered.blocks["CLAUDE.md"]
    replaced = replace_block(text, start, end, body)
    if replaced is None:
        msg = f"the hub's CLAUDE.md has no {start} / {end} markers"
        raise BlockError(msg)
    return replaced


def check_hub(root: Path, series: list[Project]) -> list[str]:
    """Return the hub files that ``series hub`` would change, writing nothing."""
    return list(_plan_hub(root, series))


def _run(cmd: list[str], cwd: Path | None = None) -> str:  # pragma: no cover
    """Run a git or gh command and return its output; raise ``SyncError`` on failure."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed argument lists, no shell
            cmd, cwd=cwd, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as exc:
        msg = f"`{' '.join(cmd[:3])}` failed: {exc.stderr.strip() or exc.stdout.strip()}"
        raise SyncError(msg) from exc
    return done.stdout


def _pr_body(result: SyncResult) -> str:
    lines = ["Brings this repo onto the shared series standard.", "", "## Changed files", ""]
    lines += [f"- `{path}`" for path in result.changed]
    lines += ["", "## CLAUDE.md lines moved into `## Project notes`", ""]
    lines += [f"- `{line.strip()}`" for line in result.moved_claude_lines] or ["- none"]
    lines += ["", "## README lines replaced by the series blocks", ""]
    lines += [f"- `{line.strip()}`" for line in result.replaced_readme_lines] or ["- none"]
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


def _sync_one(project: Project, series: list[Project], scratch: Path, *, check: bool) -> bool:
    """Sync one project in a fresh clone; return whether it had drift."""
    clone = scratch / project.repo
    if clone.exists():
        msg = f"scratch clone exists ({clone}); remove it to re-run"
        raise SyncError(msg)
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
    url = _run(
        [
            "gh", "pr", "create",
            "--repo", f"{GITHUB_OWNER}/{project.repo}",
            "--base", "main",
            "--head", BRANCH,
            "--title", COMMIT_TITLE,
            "--body", _pr_body(result),
        ],
        clone,
    )  # fmt: skip
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
    drifted: list[bool] = []
    failed = False
    for project in chosen:
        try:
            drifted.append(_sync_one(project, series, scratch, check=args.check))
        except SyncError as exc:
            failed = True
            print(f"{project.repo}: {exc}", file=sys.stderr)  # noqa: T201
        except Exception as exc:  # noqa: BLE001 - one broken repo must not stop the others
            failed = True
            print(f"{project.repo}: {type(exc).__name__}: {exc}", file=sys.stderr)  # noqa: T201
    if failed:
        return 2
    return 1 if args.check and any(drifted) else 0


def _cmd_hub(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        drift = _plan_hub(root, load_series())
    except (SeriesError, BlockError) as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        return 2
    for path, content in drift.items():
        if args.check:
            print(f"hub: drift in {path}")  # noqa: T201
            continue
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"wrote {target}")  # noqa: T201
    if not drift:
        print("hub: up to date")  # noqa: T201
    return 1 if args.check and drift else 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``series`` command line."""
    parser = argparse.ArgumentParser(prog="series")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="apply the standard to every project")
    sync.add_argument("--check", action="store_true", help="report drift, change nothing")
    sync.add_argument("--repo", help="only this GitHub repo name")
    sync.set_defaults(run=_cmd_sync)
    hub = commands.add_parser(
        "hub",
        aliases=["home"],
        help="regenerate the hub's home page, README blocks, CLAUDE.md standard and nav",
    )
    hub.add_argument("--check", action="store_true", help="report drift, change nothing")
    hub.add_argument("--root", default=str(HUB_ROOT), help="the hub checkout (default: this one)")
    hub.set_defaults(run=_cmd_hub)
    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
