"""Render the series standard for one project.

``render`` turns the templates into the files and marked blocks a project
should have. It never writes anything: ``Rendered`` is a plan that the sync
step applies to a fresh clone.

The ``Rendered`` contract
-------------------------
``files`` maps a repo-relative path to the complete content of a file the
sync owns outright: ``LICENSE``, ``.pre-commit-config.yaml``,
``.github/workflows/ci.yml``, ``.github/workflows/docs.yml`` and
``overrides/main.html`` (the theme's ``custom_dir``, which carries the
analytics script). When the
repo has no ``mkdocs.yml`` it also holds a whole ``mkdocs.yml``, and when it
has no ``docs/index.md`` it holds one made from the README, minus the
series and docs blocks (the site's series nav already links the series).

``blocks`` maps a repo-relative path to a list of
``(heading_pattern | None, start, end, body)`` entries:

* ``README.md``: the series and docs blocks. Apply each with
  ``upsert_section_block(text, heading_pattern=..., start=..., end=..., body=...)``.
  Every body starts with its own heading, and each pattern replaces the old
  section whole (``Related projects ...`` and ``Documentation ...`` headings).
* ``CLAUDE.md``: one entry, pattern ``None``, holding the standard. Hand the
  body to ``split_claude_md(text, body)``.
* ``mkdocs.yml`` (only when the repo already has one): the theme and series
  nav entries, pattern ``None``. They cannot be applied with
  ``replace_block`` alone (the theme replaces a top-level mapping and the nav
  entry is indented), so apply them with ``apply_mkdocs_blocks(text, rendered)``.

``site_description`` is the project's one-line pitch; ``apply_mkdocs_blocks``
sets the top-level ``site_description`` key to it (after ``site_url``) unless
it is empty.

``nav_fallback`` is a ready-made ``nav:`` mapping that ``apply_mkdocs_blocks``
appends when an existing ``mkdocs.yml`` has no ``nav``.

The heading patterns use a look-behind, ``(?<=## )related projects``, because
``upsert_section_block`` places the pattern after ``## `` and any text, so a
plain ``^`` could never match. They are anchored to the whole heading:
``## Related projects ...`` (any suffix) and exactly ``## Documentation``, so
``## Documentation style guide`` is the repo's own section and is left alone.
"""

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from series.blocks import BlockError, remove_block, upsert_section_block
from series.claude_md import END as CLAUDE_END
from series.claude_md import START as CLAUDE_START
from series.config import GOATCOUNTER_CODE, HUB_DESCRIPTION, SITE_ROOT, Project

TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"
HOME_URL = f"{SITE_ROOT}/"

SERIES_START = "<!-- series:start -->"
SERIES_END = "<!-- series:end -->"
DOCS_START = "<!-- docs:start -->"
DOCS_END = "<!-- docs:end -->"
THEME_START = "# theme:start"
THEME_END = "# theme:end"
NAV_START = "# series-nav:start"
NAV_END = "# series-nav:end"
SERIES_PATTERN = r"(?<=## )related projects\b[^\n]*$"
DOCS_PATTERN = r"(?<=## )documentation[ \t]*$"

HIDDEN_DOCS_DIR = "superpowers"
DEFAULT_NAV_INDENT = 2
TOP_KEY = re.compile(r"^[A-Za-z_][\w-]*\s*:")
HTML_COVERAGE = re.compile(r"pytest[^\n]*--cov-report[= ]html|coverage-report:\s*true")
MARKDOWN_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)((?:\s+\"[^\"]*\")?)\)")
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
PLAIN_TITLE = re.compile(r"[\w .()&/-]+")
OVERRIDES_MAIN = "overrides/main.html"

Block = tuple[str | None, str, str, str]

_env = Environment(  # noqa: S701 - the output is YAML and Markdown, never HTML
    loader=FileSystemLoader(TEMPLATES),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass
class Rendered:
    """What the standard looks like for one project (see the module docstring)."""

    files: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    blocks: dict[str, list[Block]] = field(default_factory=lambda: dict[str, list[Block]]())
    nav_fallback: str = ""
    site_description: str = ""


def overrides_main(goatcounter: str = GOATCOUNTER_CODE) -> str:
    """Return the theme override page, with the GoatCounter script when a code is set.

    Material's ``analytics`` block is the hook for extra tracking scripts. With
    no code the page only extends the base, so the site looks exactly as before.
    """
    lines = ['{% extends "base.html" %}']
    if goatcounter:
        lines += [
            "",
            "{% block analytics %}",
            "  {{ super() }}",
            f'  <script data-goatcounter="https://{goatcounter}.goatcounter.com/count"',
            '          async src="https://gc.zgo.at/count.js"></script>',
            "{% endblock %}",
        ]
    return "\n".join(lines) + "\n"


def _template(name: str, **values: object) -> str:
    """Render one template to text."""
    return _env.get_template(name).render(**values)


def _has_commitizen(pyproject: Path) -> bool:
    """Return whether any dependency list in ``pyproject`` names commitizen."""
    if not pyproject.is_file():
        return False
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    lists: list[object] = list(
        cast("dict[str, object]", data.get("dependency-groups", {})).values()
    )
    project = cast("dict[str, Any]", data.get("project", {}))
    lists += list(cast("dict[str, object]", project.get("optional-dependencies", {})).values())
    lists.append(project.get("dependencies", []))
    return any(
        isinstance(item, str) and re.match(r"commitizen\b", item, flags=re.IGNORECASE)
        for group in lists
        for item in cast("list[object]", group)
    )


def _has_coverage_report(repo_root: Path) -> bool:
    """Return whether the existing docs workflow runs pytest with an HTML coverage report."""
    workflow = repo_root / ".github" / "workflows" / "docs.yml"
    return workflow.is_file() and bool(HTML_COVERAGE.search(workflow.read_text(encoding="utf-8")))


def _marked(start: str, end: str, body: str) -> str:
    """Wrap ``body`` in its two marker lines."""
    return f"{start}\n{body.strip(chr(10))}\n{end}"


def _page_title(path: Path) -> str:
    """Return a page's first ``# `` heading, or a title made from its file name."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _yaml_text(text: str) -> str:
    """Return ``text`` as a YAML scalar, quoted only when needed."""
    return text if PLAIN_TITLE.fullmatch(text) else json.dumps(text)


def _nav_pages(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``(title, path)`` for the index and every docs page outside ``superpowers/``."""
    docs = repo_root / "docs"
    pages = [("Home", "index.md")]
    if not docs.is_dir():
        return pages
    for page in sorted(docs.rglob("*.md")):
        relative = page.relative_to(docs)
        if relative.parts[0] == HIDDEN_DOCS_DIR or relative.as_posix() == "index.md":
            continue
        pages.append((_yaml_text(_page_title(page)), relative.as_posix()))
    return pages


def _absolute_links(readme: str, project: Project) -> str:
    """Rewrite the README's relative links to GitHub URLs so they work on the docs site."""

    def fix(match: re.Match[str]) -> str:
        bang, label, target, title = match.groups()
        if URL_SCHEME.match(target) or target.startswith(("#", "/")):
            return match.group(0)
        path = target.removeprefix("./")
        base = (
            f"https://raw.githubusercontent.com/robcox2910/{project.repo}/main"
            if bang
            else f"{project.github_url}/blob/main"
        )
        return f"{bang}[{label}]({base}/{path}{title})"

    return MARKDOWN_LINK.sub(fix, readme)


@dataclass(frozen=True)
class _Bodies:
    """The rendered text of each marked block, before markers are added."""

    series: str
    docs: str
    theme: str
    nav: str
    standard: str


def _bodies(values: dict[str, Any]) -> _Bodies:
    """Render the body of every marked block from the template ``values``."""
    return _Bodies(
        series=_template("readme_series.md.j2", **values).strip("\n"),
        docs=_template("readme_docs.md.j2", **values).strip("\n"),
        theme=(TEMPLATES / "mkdocs_theme.yml").read_text(encoding="utf-8").strip("\n"),
        nav=_template("mkdocs_series_nav.yml.j2", **values).strip("\n"),
        standard=(TEMPLATES / "claude_standard.md").read_text(encoding="utf-8").strip("\n"),
    )


def _readme_blocks(bodies: _Bodies) -> list[Block]:
    """Return the README series and docs block entries."""
    return [
        (SERIES_PATTERN, SERIES_START, SERIES_END, bodies.series),
        (DOCS_PATTERN, DOCS_START, DOCS_END, bodies.docs),
    ]


def _mkdocs_blocks(bodies: _Bodies) -> list[Block]:
    """Return the mkdocs.yml theme and series-nav block entries."""
    return [(None, THEME_START, THEME_END, bodies.theme), (None, NAV_START, NAV_END, bodies.nav)]


def render_hub(series: list[Project]) -> Rendered:
    """Render the blocks the hub itself carries: README, CLAUDE.md and mkdocs.yml.

    The hub is not a project, so no row is bold and no nav entry says "you are
    here"; its docs link is the home page. ``files`` is left empty: the hub
    keeps its own workflows and never gets the ``@v1`` caller files.
    """
    bodies = _bodies(
        {"current": None, "series": series, "home_url": HOME_URL, "site_url": HOME_URL}
    )
    nav_block = _indent(_marked(NAV_START, NAV_END, bodies.nav), DEFAULT_NAV_INDENT)
    return Rendered(
        blocks={
            "README.md": _readme_blocks(bodies),
            "CLAUDE.md": [(None, CLAUDE_START, CLAUDE_END, bodies.standard)],
            "mkdocs.yml": _mkdocs_blocks(bodies),
        },
        nav_fallback=f"nav:\n  - Home: index.md\n{nav_block}\n",
        site_description=HUB_DESCRIPTION,
    )


def render(project: Project, series: list[Project], repo_root: Path) -> Rendered:
    """Render the standard for ``project``; ``repo_root`` is only read, never written."""
    values: dict[str, Any] = {
        "project": project,
        "current": project,
        "series": series,
        "home_url": HOME_URL,
        "site_url": project.site_url,
    }
    bodies = _bodies(values)
    theme_body, nav_body = bodies.theme, bodies.nav

    coverage = "true" if _has_coverage_report(repo_root) else "false"
    rendered = Rendered(
        files={
            "LICENSE": (TEMPLATES / "LICENSE").read_text(encoding="utf-8"),
            "conftest.py": (TEMPLATES / "conftest.py").read_text(encoding="utf-8"),
            ".pre-commit-config.yaml": _template(
                "pre-commit-config.yaml.j2",
                commitizen=_has_commitizen(repo_root / "pyproject.toml"),
            ),
            ".github/workflows/ci.yml": _template("ci.yml"),
            ".github/workflows/docs.yml": _template("docs.yml", coverage_report=coverage),
            OVERRIDES_MAIN: overrides_main(),
        },
        blocks={
            "README.md": _readme_blocks(bodies),
            "CLAUDE.md": [(None, CLAUDE_START, CLAUDE_END, bodies.standard)],
        },
        site_description=project.description,
    )
    pages = _nav_pages(repo_root)
    nav_block = _marked(NAV_START, NAV_END, nav_body)
    if (repo_root / "mkdocs.yml").is_file():
        rendered.blocks["mkdocs.yml"] = _mkdocs_blocks(bodies)
        items = "".join(f"  - {title}: {path}\n" for title, path in pages)
        rendered.nav_fallback = f"nav:\n{items}{_indent(nav_block, DEFAULT_NAV_INDENT)}\n"
    else:
        rendered.files["mkdocs.yml"] = _template(
            "mkdocs_new.yml.j2",
            **values,
            theme_block=_marked(THEME_START, THEME_END, theme_body),
            nav_block=nav_block,
            pages=pages,
        )
    if not (repo_root / "docs" / "index.md").is_file():
        readme_path = repo_root / "README.md"
        readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
        readme = readme or f"# {project.name}\n"
        # Fill the blocks (which also swaps out an old unmarked series section),
        # then drop them: the site's series nav links the series, and a frozen
        # copy of the table in docs/index.md would go stale.
        for pattern, start, end, body in rendered.blocks["README.md"]:
            readme = upsert_section_block(
                readme, heading_pattern=pattern or "", start=start, end=end, body=body
            )
        for _, start, end, _ in rendered.blocks["README.md"]:
            readme = remove_block(readme, start, end)
        rendered.files["docs/index.md"] = _absolute_links(readme, project)
    return rendered


# --- applying the mkdocs.yml blocks -----------------------------------------


def _indent(text: str, width: int) -> str:
    """Indent every non-blank line of ``text`` by ``width`` spaces."""
    pad = " " * width
    return "\n".join(f"{pad}{line}" if line.strip() else line for line in text.split("\n"))


def _find_marker(lines: list[str], marker: str) -> list[int]:
    """Return the indexes of lines that are just ``marker`` (ignoring indentation)."""
    return [i for i, line in enumerate(lines) if line.strip() == marker]


def _replace_marked_lines(lines: list[str], start: str, end: str, body: str) -> bool:
    """Replace the lines between two markers in place; return whether markers were found."""
    starts, ends = _find_marker(lines, start), _find_marker(lines, end)
    if not starts and not ends:
        return False
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        msg = f"expected exactly one {start!r} followed by one {end!r}"
        raise BlockError(msg)
    first = lines[starts[0]]
    indent = first[: len(first) - len(first.lstrip())]
    inner = [f"{indent}{line}" if line.strip() else line for line in body.strip("\n").split("\n")]
    lines[starts[0] + 1 : ends[0]] = inner
    lines[starts[0] + 1 + len(inner)] = f"{indent}{end}"
    return True


def _key_region(lines: list[str], key: str) -> tuple[int, int] | None:
    """Return the line range of top-level ``key``, minus trailing blank and comment lines."""
    keys = [i for i, line in enumerate(lines) if TOP_KEY.match(line)]
    for position, begin in enumerate(keys):
        if lines[begin].partition(":")[0].strip() != key:
            continue
        stop = keys[position + 1] if position + 1 < len(keys) else len(lines)
        while stop > begin + 1 and (not lines[stop - 1].strip() or lines[stop - 1].startswith("#")):
            stop -= 1
        return begin, stop
    return None


def _insert(lines: list[str], at: int, new: list[str]) -> None:
    """Insert ``new`` lines at ``at``, keeping one blank line around them."""
    if at > 0 and lines[at - 1].strip():
        new = ["", *new]
    if at < len(lines) and lines[at].strip():
        new = [*new, ""]
    lines[at:at] = new


def _apply_theme(lines: list[str], body: str) -> None:
    """Put the theme block in: reuse markers, replace the theme mapping, or insert it."""
    if _replace_marked_lines(lines, THEME_START, THEME_END, body):
        return
    block = _marked(THEME_START, THEME_END, body).split("\n")
    region = _key_region(lines, "theme")
    if region is not None:
        lines[region[0] : region[1]] = block
        return
    after = _key_region(lines, "repo_name")
    _insert(lines, after[1] if after is not None else len(lines), block)


def _nav_indent(lines: list[str], region: tuple[int, int]) -> int:
    """Return the indent of the first nav item, or the default."""
    for line in lines[region[0] + 1 : region[1]]:
        match = re.match(r"^(\s+)- ", line)
        if match:
            return len(match.group(1))
    return DEFAULT_NAV_INDENT


def _apply_nav(lines: list[str], body: str, fallback: str) -> None:
    """Put the series nav in: reuse markers, end the nav list, or add a whole nav."""
    if _replace_marked_lines(lines, NAV_START, NAV_END, body):
        return
    region = _key_region(lines, "nav")
    if region is None:
        _insert(lines, len(lines), fallback.rstrip("\n").split("\n"))
        return
    block = _indent(_marked(NAV_START, NAV_END, body), _nav_indent(lines, region))
    lines[region[1] : region[1]] = block.split("\n")


def _apply_exclude_docs(lines: list[str]) -> None:
    """Make sure ``exclude_docs`` covers ``superpowers/``."""
    hidden = f"{HIDDEN_DOCS_DIR}/"
    region = _key_region(lines, "exclude_docs")
    if region is None:
        _insert(lines, len(lines), ["exclude_docs: |", f"  {hidden}"])
        return
    if any(hidden in line for line in lines[region[0] : region[1]]):
        return
    value = lines[region[0]].partition(":")[2].strip()
    if value.startswith(("|", ">")):
        lines[region[1] : region[1]] = [f"  {hidden}"]
    else:
        lines[region[0] : region[1]] = [
            "exclude_docs: |",
            *([f"  {value.strip(chr(34) + chr(39))}"] if value else []),
            f"  {hidden}",
        ]


def _apply_site_description(lines: list[str], description: str) -> None:
    """Set the top-level ``site_description``: replace it, or add it after ``site_url``."""
    if not description:
        return
    line = f"site_description: {json.dumps(description, ensure_ascii=False)}"
    region = _key_region(lines, "site_description")
    if region is not None:
        lines[region[0] : region[1]] = [line]
        return
    after = _key_region(lines, "site_url") or _key_region(lines, "site_name")
    lines.insert(after[1] if after is not None else 0, line)


def apply_mkdocs_blocks(text: str, rendered: Rendered) -> str:
    """Return ``text`` (an existing ``mkdocs.yml``) with the series blocks applied.

    Theme: reuse the markers if present, else replace the top-level ``theme:``
    mapping, else insert after ``repo_name:`` (or at the end). Nav: reuse the
    markers, else make the block the last item of the top-level ``nav:`` list,
    else append ``rendered.nav_fallback``. Also ensures ``exclude_docs``
    covers ``superpowers/`` and sets ``site_description`` when there is one. Applying twice changes nothing the second time.
    """
    entries = {entry[1]: entry[3] for entry in rendered.blocks.get("mkdocs.yml", [])}
    lines = text.rstrip("\n").split("\n") if text.strip() else []
    _apply_theme(lines, entries[THEME_START])
    _apply_nav(lines, entries[NAV_START], rendered.nav_fallback)
    _apply_exclude_docs(lines)
    _apply_site_description(lines, rendered.site_description)
    return "\n".join(lines) + "\n"
