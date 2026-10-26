"""Tests for rendering the standard for one project."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from series.blocks import upsert_section_block
from series.config import Project, load_series
from series.render import TEMPLATES, Rendered, apply_mkdocs_blocks, render


class _MkdocsLoader(yaml.SafeLoader):
    """A safe loader that reads mkdocs tags (``!ENV``, ``!!python/name:``) as plain values."""


def _plain(loader: yaml.SafeLoader, _suffix: str, node: yaml.Node) -> object:
    """Read a tagged node as the value it would have without the tag."""
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return loader.construct_scalar(node)  # type: ignore[arg-type]


_MkdocsLoader.add_multi_constructor("!", _plain)  # pyright: ignore[reportUnknownMemberType]
_MkdocsLoader.add_multi_constructor(  # pyright: ignore[reportUnknownMemberType]
    "tag:yaml.org,2002:python/", _plain
)


def load_mkdocs(text: str) -> Any:
    """Parse an mkdocs.yml text, keeping tagged values as plain data."""
    return yaml.load(text, Loader=_MkdocsLoader)  # noqa: S506 - SafeLoader subclass


SERIES = load_series()
SERIES_COUNT = 18
PEBBLE = SERIES[1]
PYDB = SERIES[2]
SERIES_START = "<!-- series:start -->"
SERIES_END = "<!-- series:end -->"
DOCS_START = "<!-- docs:start -->"
DOCS_END = "<!-- docs:end -->"
ROOT = Path(__file__).resolve().parent.parent


def make_repo(
    tmp_path: Path, files: dict[str, str] | None = None, project: Project = PYDB
) -> tuple[Rendered, Path]:
    """Create a fake repo with ``files`` and render ``project`` for it."""
    for name, content in (files or {}).items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return render(project, SERIES, tmp_path), tmp_path


def block(rendered: Rendered, path: str, start: str) -> tuple[str | None, str, str, str]:
    """Return the block entry for ``path`` whose start marker is ``start``."""
    return next(entry for entry in rendered.blocks[path] if entry[1] == start)


def test_series_table_lists_all_18_in_order_and_bolds_current(tmp_path: Path) -> None:
    """The table has one row per project, in order, with the current one bold."""
    rendered, _ = make_repo(tmp_path)
    pattern, _, _, body = block(rendered, "README.md", SERIES_START)
    assert pattern is not None
    assert body.startswith("## Related Projects")
    assert "| Project | What it teaches | Repository | Docs |" in body
    rows = [line for line in body.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert len(rows) == len(SERIES) == SERIES_COUNT
    for row, project in zip(rows, SERIES, strict=True):
        assert project.name in row
        assert project.github_url in row
        assert project.site_url in row
        assert row.startswith(f"| **{project.name}**") == (project is PYDB)


@pytest.mark.parametrize(
    "heading",
    ['## Related projects — "from scratch in Python"', "## Related Projects"],
)
def test_series_pattern_replaces_existing_heading(tmp_path: Path, heading: str) -> None:
    """The anchored heading pattern finds the old section and replaces it whole."""
    rendered, _ = make_repo(tmp_path)
    pattern, start, end, body = block(rendered, "README.md", SERIES_START)
    assert pattern is not None
    text = f"# T\n\n## Intro\n\nhi\n\n{heading}\n\nold list\n\n## License\n\nMIT\n"
    out = upsert_section_block(text, heading_pattern=pattern, start=start, end=end, body=body)
    assert "old list" not in out
    assert out.count("## Related Projects") == 1
    assert "## Intro\n\nhi" in out
    assert out.endswith("## License\n\nMIT\n")


def test_series_pattern_is_anchored(tmp_path: Path) -> None:
    """A heading that merely mentions related projects is not replaced."""
    rendered, _ = make_repo(tmp_path)
    pattern, start, end, body = block(rendered, "README.md", SERIES_START)
    assert pattern is not None
    text = "# T\n\n## See also related projects\n\nkeep me\n\n## License\n\nMIT\n"
    out = upsert_section_block(text, heading_pattern=pattern, start=start, end=end, body=body)
    assert "keep me" in out


def test_docs_block_links_site_url(tmp_path: Path) -> None:
    """The docs block starts with its heading and links to the site."""
    rendered, _ = make_repo(tmp_path)
    pattern, _, _, body = block(rendered, "README.md", DOCS_START)
    assert pattern is not None
    assert body.startswith("## Documentation")
    assert f"Full docs (with kid-friendly explanations of every idea): {PYDB.site_url}" in body
    text = "# T\n\n## Documentation\n\nold\n\n## License\n"
    out = upsert_section_block(
        text, heading_pattern=pattern, start=DOCS_START, end=DOCS_END, body=body
    )
    assert "old" not in out


def test_license_has_2026_rob_cox(tmp_path: Path) -> None:
    """The LICENSE is the series one, byte for byte."""
    rendered, _ = make_repo(tmp_path)
    assert "Copyright (c) 2026 Rob Cox" in rendered.files["LICENSE"]
    assert rendered.files["LICENSE"] == (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_render_owns_root_conftest(tmp_path: Path) -> None:
    """The root ``conftest.py`` is an owned file, copied verbatim from the template."""
    rendered, _ = make_repo(tmp_path)
    template = TEMPLATES / "conftest.py"
    assert rendered.files["conftest.py"] == template.read_text(encoding="utf-8")


def test_ci_caller_uses_v1(tmp_path: Path) -> None:
    """The CI caller points at the shared workflow at v1."""
    rendered, _ = make_repo(tmp_path)
    assert "python-ci.yml@v1" in rendered.files[".github/workflows/ci.yml"]
    assert "docs.yml@v1" in rendered.files[".github/workflows/docs.yml"]


def test_coverage_report_false_by_default(tmp_path: Path) -> None:
    """With no existing docs workflow there is no coverage report."""
    rendered, _ = make_repo(tmp_path)
    docs = yaml.safe_load(rendered.files[".github/workflows/docs.yml"])
    assert docs["jobs"]["docs"]["with"]["coverage-report"] is False


def test_coverage_report_true_when_existing_docs_workflow_uses_html(tmp_path: Path) -> None:
    """An existing docs workflow with an HTML coverage run turns the report on."""
    workflow = "steps:\n  - run: uv run pytest --cov-report=html:docs/coverage\n"
    rendered, _ = make_repo(tmp_path, {".github/workflows/docs.yml": workflow})
    docs = yaml.safe_load(rendered.files[".github/workflows/docs.yml"])
    assert docs["jobs"]["docs"]["with"]["coverage-report"] is True


def test_coverage_report_false_when_existing_docs_workflow_lacks_html(tmp_path: Path) -> None:
    """A docs workflow that only builds docs does not get a coverage report."""
    workflow = "steps:\n  - run: uv run mkdocs build --strict\n"
    rendered, _ = make_repo(tmp_path, {".github/workflows/docs.yml": workflow})
    docs = yaml.safe_load(rendered.files[".github/workflows/docs.yml"])
    assert docs["jobs"]["docs"]["with"]["coverage-report"] is False


def test_pre_commit_replaces_pip_audit_with_local_hook(tmp_path: Path) -> None:
    """pip-audit runs as a local hook through uvx on a temporary file."""
    rendered, _ = make_repo(tmp_path)
    text = rendered.files[".pre-commit-config.yaml"]
    config = yaml.safe_load(text)
    repos = [entry["repo"] for entry in config["repos"]]
    assert "https://github.com/pypa/pip-audit" not in repos
    assert "local" in repos
    local = next(entry for entry in config["repos"] if entry["repo"] == "local")
    hook = local["hooks"][0]
    assert hook["language"] == "system"
    assert hook["pass_filenames"] is False
    assert hook["files"] == r"^(pyproject\.toml|uv\.lock)$"
    assert "uv export --frozen --no-emit-project --all-extras --no-hashes" in hook["entry"]
    assert "uvx pip-audit==2.10.0 -r" in hook["entry"]
    assert "--disable-pip --no-deps" in hook["entry"]
    assert "mktemp" in hook["entry"]
    assert "rm -f" in hook["entry"]


def test_pre_commit_commitizen_only_with_dev_dep(tmp_path: Path) -> None:
    """Commitizen stays only when pyproject lists it as a dev dependency."""
    without, _ = make_repo(tmp_path / "a", {"pyproject.toml": "[project]\nname='x'\n"})
    assert "commitizen" not in without.files[".pre-commit-config.yaml"]
    pyproject = '[dependency-groups]\ndev = ["pytest", "commitizen>=4"]\n'
    with_it, _ = make_repo(tmp_path / "b", {"pyproject.toml": pyproject})
    assert "commitizen-tools/commitizen" in with_it.files[".pre-commit-config.yaml"]
    yaml.safe_load(with_it.files[".pre-commit-config.yaml"])


def test_claude_standard_block(tmp_path: Path) -> None:
    """The CLAUDE.md block holds the generic sections and calls per-file-ignores repo-owned."""
    rendered, _ = make_repo(tmp_path)
    pattern, start, end, body = block(rendered, "CLAUDE.md", "<!-- standard:start -->")
    assert pattern is None
    assert end == "<!-- standard:end -->"
    for heading in ("Code Style", "Linting", "Testing", "Commits", "Dependencies", "Releasing"):
        assert f"## {heading}" in body
    assert "per-file-ignores" in body
    assert start == "<!-- standard:start -->"


def test_new_mkdocs_for_repo_without_docs_index(tmp_path: Path) -> None:
    """A repo with no docs gets a fresh mkdocs.yml and a docs/index.md from the README."""
    readme = "# PyDB\n\nSee [the guide](docs/guide.md) and [site](https://x.dev) [top](#a).\n"
    rendered, _ = make_repo(tmp_path, {"README.md": readme})
    assert "mkdocs.yml" not in rendered.blocks
    config = load_mkdocs(rendered.files["mkdocs.yml"])
    assert config["site_name"] == "PyDB"
    assert config["site_url"] == PYDB.site_url
    assert config["repo_url"] == PYDB.github_url
    assert config["nav"][0] == {"Home": "index.md"}
    assert "superpowers/" in config["exclude_docs"]
    assert "# theme:start" in rendered.files["mkdocs.yml"]
    assert "# series-nav:end" in rendered.files["mkdocs.yml"]
    assert "The series" in config["nav"][-1]
    index = rendered.files["docs/index.md"]
    assert f"({PYDB.github_url}/blob/main/docs/guide.md)" in index
    assert "(https://x.dev)" in index
    assert "(#a)" in index


def test_new_mkdocs_lists_docs_pages_sorted(tmp_path: Path) -> None:
    """A new nav lists the docs pages in sorted order after the index."""
    files = {
        "README.md": "# X\n",
        "docs/b.md": "# Bee\n",
        "docs/a/page.md": "no heading\n",
    }
    rendered, _ = make_repo(tmp_path, files)
    config = load_mkdocs(rendered.files["mkdocs.yml"])
    pages = [next(iter(item.values())) for item in config["nav"][:-1]]
    assert pages == ["index.md", "a/page.md", "b.md"]


def test_superpowers_docs_never_in_nav(tmp_path: Path) -> None:
    """Planning notes under docs/superpowers never reach the nav."""
    files = {
        "README.md": "# X\n",
        "docs/index.md": "# X\n",
        "docs/concepts.md": "# C\n",
        "docs/superpowers/plan.md": "# Plan\n",
    }
    rendered, _ = make_repo(tmp_path, files)
    assert "superpowers/plan.md" not in rendered.files["mkdocs.yml"]
    assert "concepts.md" in rendered.files["mkdocs.yml"]
    assert "docs/index.md" not in rendered.files


def test_existing_mkdocs_gets_blocks_not_file(tmp_path: Path) -> None:
    """An existing mkdocs.yml is never rewritten whole, only given blocks."""
    mkdocs = "site_name: X\nnav:\n  - Home: index.md\n"
    rendered, _ = make_repo(tmp_path, {"mkdocs.yml": mkdocs, "docs/index.md": "# X\n"})
    assert "mkdocs.yml" not in rendered.files
    starts = [entry[1] for entry in rendered.blocks["mkdocs.yml"]]
    assert starts == ["# theme:start", "# series-nav:start"]
    assert all(entry[0] is None for entry in rendered.blocks["mkdocs.yml"])


def test_missing_docs_index_is_added_for_existing_mkdocs(tmp_path: Path) -> None:
    """A repo with mkdocs.yml but no docs/index.md gets one from the README."""
    rendered, _ = make_repo(tmp_path, {"mkdocs.yml": "site_name: X\n", "README.md": "# X\n"})
    assert rendered.files["docs/index.md"].startswith("# X")


MKDOCS = """site_name: PyDB
repo_name: robcox2910/pydb

theme:
  name: material
  palette:
    primary: red

markdown_extensions:
  - tables

nav:
  - Home: index.md
  - Guide:
      - A: a.md

plugins:
  - search
"""


def applied(tmp_path: Path, text: str) -> tuple[str, dict[str, object]]:
    """Render for a repo with mkdocs ``text`` and return the applied text and its YAML."""
    rendered, _ = make_repo(tmp_path, {"mkdocs.yml": text, "docs/index.md": "# X\n"})
    out = apply_mkdocs_blocks(text, rendered)
    return out, load_mkdocs(out)


def test_apply_replaces_top_level_theme_and_appends_nav(tmp_path: Path) -> None:
    """The old theme mapping is replaced and the series nav ends the nav list."""
    out, config = applied(tmp_path, MKDOCS)
    assert "primary: red" not in out
    assert out.count("# theme:start") == 1
    assert config["theme"]["name"] == "material"  # type: ignore[index]
    nav = config["nav"]
    assert isinstance(nav, list)
    assert "The series" in nav[-1]  # type: ignore[operator]
    assert nav[1] == {"Guide": [{"A": "a.md"}]}  # type: ignore[index]
    assert "markdown_extensions" in config
    assert config["plugins"] == ["search"]
    assert "superpowers/" in str(config["exclude_docs"])


def test_apply_is_idempotent(tmp_path: Path) -> None:
    """Applying twice gives the same text as applying once."""
    once, _ = applied(tmp_path / "a", MKDOCS)
    rendered, _ = make_repo(tmp_path / "b", {"mkdocs.yml": once, "docs/index.md": "# X\n"})
    assert apply_mkdocs_blocks(once, rendered) == once


def test_apply_inserts_theme_after_repo_name_when_no_theme(tmp_path: Path) -> None:
    """With no theme, the block goes right after repo_name."""
    text = "site_name: X\nrepo_name: a/b\nnav:\n  - Home: index.md\n"
    out, config = applied(tmp_path, text)
    assert out.index("repo_name") < out.index("# theme:start") < out.index("nav:")
    assert config["theme"]["name"] == "material"  # type: ignore[index]


def test_apply_inserts_theme_at_end_when_no_theme_or_repo_name(tmp_path: Path) -> None:
    """With neither theme nor repo_name, the theme block is appended."""
    out, config = applied(tmp_path, "site_name: X\n")
    assert "theme" in config
    assert out.index("# theme:start") > out.index("site_name")


def test_apply_builds_nav_when_missing(tmp_path: Path) -> None:
    """With no nav, a fresh one lists the index and pages and ends with the series nav."""
    rendered, _ = make_repo(
        tmp_path,
        {"mkdocs.yml": "site_name: X\n", "docs/index.md": "# X\n", "docs/b.md": "# B\n"},
    )
    out = apply_mkdocs_blocks("site_name: X\n", rendered)
    config = load_mkdocs(out)
    assert config["nav"][0] == {"Home": "index.md"}
    assert config["nav"][1] == {"B": "b.md"}
    assert "The series" in config["nav"][-1]


def test_apply_reuses_indented_markers(tmp_path: Path) -> None:
    """Existing markers are reused and the body follows the marker's indent."""
    first, _ = applied(tmp_path / "a", MKDOCS)
    stale = first.replace("Series home", "Old home")
    rendered, _ = make_repo(tmp_path / "b", {"mkdocs.yml": stale, "docs/index.md": "# X\n"})
    out = apply_mkdocs_blocks(stale, rendered)
    assert out == first


def test_apply_appends_to_exclude_docs_without_superpowers(tmp_path: Path) -> None:
    """An existing exclude_docs block scalar gains superpowers/."""
    out, config = applied(tmp_path, MKDOCS + "exclude_docs: |\n  drafts/\n")
    assert "drafts/" in str(config["exclude_docs"])
    assert "superpowers/" in str(config["exclude_docs"])
    assert out.count("exclude_docs") == 1


def test_coverage_report_survives_a_second_render(tmp_path: Path) -> None:
    """Rendering over an already-synced repo keeps the coverage report on."""
    workflow = "steps:\n  - run: uv run pytest --cov-report=html:docs/coverage\n"
    first, _ = make_repo(tmp_path, {".github/workflows/docs.yml": workflow})
    (tmp_path / ".github/workflows/docs.yml").write_text(
        first.files[".github/workflows/docs.yml"], encoding="utf-8"
    )
    second = render(PYDB, SERIES, tmp_path)
    docs = yaml.safe_load(second.files[".github/workflows/docs.yml"])
    assert docs["jobs"]["docs"]["with"]["coverage-report"] is True
    assert second.files == first.files | {
        name: content for name, content in second.files.items() if name not in first.files
    }


def test_docs_pattern_matches_the_whole_heading(tmp_path: Path) -> None:
    """``## Documentation style guide`` is the repo's own section and is not replaced."""
    rendered, _ = make_repo(tmp_path)
    pattern, start, end, body = block(rendered, "README.md", DOCS_START)
    assert pattern is not None
    guide = "## Documentation style guide\n\nWrite short sentences."
    text = f"# T\n\n{guide}\n\n## License\n\nMIT\n"
    out = upsert_section_block(text, heading_pattern=pattern, start=start, end=end, body=body)
    assert guide in out
    assert out.index(DOCS_START) > out.index(guide)


def test_series_pattern_keeps_subsection(tmp_path: Path) -> None:
    """The rendered series pattern keeps a ``###`` subsection of the old section."""
    rendered, _ = make_repo(tmp_path)
    pattern, start, end, body = block(rendered, "README.md", SERIES_START)
    assert pattern is not None
    sub = "### How PyFoo fits in\n\nIt sits on PyDB."
    text = f"# T\n\n## Related projects\n\n- PyDB\n- PyKV\n\n{sub}\n\n## License\n\nMIT\n"
    out = upsert_section_block(text, heading_pattern=pattern, start=start, end=end, body=body)
    assert f"{SERIES_END}\n\n{sub}\n\n## License" in out
    assert "- PyKV" not in out


@pytest.mark.parametrize(
    "readme",
    [
        "# PyDB\n\nHello.\n\n## Related projects\n\n- [PyKV](x)\n\n## License\n\nMIT\n",
        (
            f"# PyDB\n\nHello.\n\n{SERIES_START}\n## Related Projects\n\n| old |\n{SERIES_END}\n\n"
            f"{DOCS_START}\n## Documentation\n\nold\n{DOCS_END}\n\n## License\n\nMIT\n"
        ),
    ],
)
def test_generated_index_has_no_series_or_docs_block(tmp_path: Path, readme: str) -> None:
    """A docs/index.md made from the README leaves out the series and docs blocks."""
    rendered, _ = make_repo(tmp_path, {"README.md": readme})
    index = rendered.files["docs/index.md"]
    for marker in (SERIES_START, SERIES_END, DOCS_START, DOCS_END):
        assert marker not in index
    assert "Related" not in index
    assert "## Documentation" not in index
    assert "PyKV" not in index
    assert index == "# PyDB\n\nHello.\n\n## License\n\nMIT\n"


def test_pre_commit_spares_pasted_output_in_property_page(tmp_path: Path) -> None:
    """The property page pastes real pytest output, so whitespace hooks skip it."""
    rendered, _ = make_repo(tmp_path)
    config = yaml.safe_load(rendered.files[".pre-commit-config.yaml"])
    hooks = {h["id"]: h for entry in config["repos"] for h in entry["hooks"]}
    for hook_id in ("trailing-whitespace", "end-of-file-fixer"):
        pattern = re.compile(hooks[hook_id]["exclude"])
        assert pattern.search("docs/property-testing.md")
        assert not pattern.search("docs/index.md")


def test_pre_commit_runs_python_hooks_on_python_314(tmp_path: Path) -> None:
    """Hooks parse 3.14 syntax such as `type X = ...`, so they need a 3.14 interpreter."""
    rendered, _ = make_repo(tmp_path)
    config = yaml.safe_load(rendered.files[".pre-commit-config.yaml"])
    assert config["default_language_version"] == {"python": "python3.14"}
