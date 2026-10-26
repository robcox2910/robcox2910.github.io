"""Tests for publishing the series to PyPI: one name pattern, one release workflow, one source of truth."""

from pathlib import Path

import tomlkit
import yaml

from series.config import Project, load_series
from series.render import (
    DOCS_START,
    RELEASE_WORKFLOW,
    SERIES_START,
    TEMPLATES,
    Block,
    render,
    render_hub,
)
from series.sync import apply_to_tree, render_home
from series.tomledit import apply_standard_toml

SERIES = load_series()
PREFIX = "fromscratch-"
PYPROJECT = """\
[project]
name = "old-name"
dynamic = ["version"]
dependencies = []

[tool.ruff]
line-length = 99
"""


def _project(name: str) -> Project:
    """Return the series project called ``name``."""
    return next(p for p in SERIES if p.name == name)


class TestNames:
    """Every project publishes under one clear, free name pattern."""

    def test_every_package_is_fromscratch_prefixed_and_unique(self) -> None:
        """Each distribution name starts with the prefix, and no two are the same."""
        packages = [p.package for p in SERIES]
        assert all(name.startswith(PREFIX) for name in packages)
        assert len(set(packages)) == len(packages)

    def test_pyscheduler_joins_before_pystack(self) -> None:
        """PyScheduler is in the series, after what it uses and before PyStack, which uses it."""
        names = [p.name for p in SERIES]
        assert names.index("PyScheduler") == names.index("PyStack") - 1
        assert set(_project("PyScheduler").builds_on) == {"PyNet", "PyWeb", "PyDB", "PyMQ"}
        assert "PyScheduler" in _project("PyStack").builds_on


class TestProjectName:
    """The sync makes each repo's ``[project] name`` match ``series.yml``."""

    def test_name_is_set_and_the_rest_left_alone(self) -> None:
        """Only the name changes; other keys and tables stay exactly as written."""
        out = apply_standard_toml(PYPROJECT, package="fromscratch-demo")
        doc = tomlkit.parse(out)
        assert doc["project"]["name"] == "fromscratch-demo"  # type: ignore[index]
        assert doc["project"]["dynamic"] == ["version"]  # type: ignore[index]
        assert doc["tool"]["ruff"]["line-length"] == 99  # type: ignore[index]  # noqa: PLR2004

    def test_setting_the_name_twice_changes_nothing(self) -> None:
        """Applying the standard to its own output is a no-op."""
        once = apply_standard_toml(PYPROJECT, package="fromscratch-demo")
        assert apply_standard_toml(once, package="fromscratch-demo") == once

    def test_no_package_leaves_the_name(self) -> None:
        """Without a package the name is not touched (the hub has no distribution)."""
        assert 'name = "old-name"' in apply_standard_toml(PYPROJECT)

    def test_sync_renames_the_distribution(self, tmp_path: Path) -> None:
        """A sync writes the series name into the repo's pyproject."""
        (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
        project = _project("PyDB")
        apply_to_tree(tmp_path, project, SERIES)
        doc = tomlkit.parse((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
        assert doc["project"]["name"] == project.package  # type: ignore[index]


class TestReleaseWorkflow:
    """Every project gets the same tag-triggered release that publishes to PyPI."""

    def test_release_runs_on_version_tags_and_publishes(self, tmp_path: Path) -> None:
        """A ``vX.Y.Z`` tag builds, attaches files to a GitHub release and publishes to PyPI."""
        project = _project("PyDB")
        workflow = yaml.safe_load(render(project, SERIES, tmp_path).files[RELEASE_WORKFLOW])
        assert workflow[True]["push"]["tags"] == ["v*.*.*"]  # `on` loads as True
        build, publish = workflow["jobs"]["build"], workflow["jobs"]["publish"]
        assert any(step.get("run") == "uv build" for step in build["steps"])
        assert publish["needs"] == "build"
        assert publish["permissions"] == {"id-token": "write"}
        assert any(
            step.get("uses", "").startswith("pypa/gh-action-pypi-publish")
            for step in publish["steps"]
        )

    def test_publish_environment_names_pypi_and_links_the_package(self, tmp_path: Path) -> None:
        """The ``pypi`` environment (what PyPI's trusted publisher expects) links the project page."""
        project = _project("PyLLM")
        workflow = yaml.safe_load(render(project, SERIES, tmp_path).files[RELEASE_WORKFLOW])
        env = workflow["jobs"]["publish"]["environment"]
        assert env == {"name": "pypi", "url": f"https://pypi.org/project/{project.package}/"}


def _block_body(rendered_blocks: list[Block], start: str) -> str:
    """Return the body of the block that opens with ``start``."""
    return next(body for _, s, _, body in rendered_blocks if s == start)


class TestInstallDocs:
    """Every README and the home page tell readers how to ``pip install`` the series."""

    def test_project_docs_block_shows_its_pip_install_and_badge(self, tmp_path: Path) -> None:
        """A project's docs block gives its own ``pip install`` line and a PyPI badge."""
        project = _project("PyDB")
        body = _block_body(render(project, SERIES, tmp_path).blocks["README.md"], DOCS_START)
        assert f"pip install {project.package}" in body
        assert f"https://img.shields.io/pypi/v/{project.package}" in body
        assert f"https://pypi.org/project/{project.package}/" in body

    def test_hub_docs_block_installs_the_whole_series(self) -> None:
        """The hub has no package of its own, so it points at PyStack, which pulls in the rest."""
        body = _block_body(render_hub(SERIES).blocks["README.md"], DOCS_START)
        assert f"pip install {_project('PyStack').package}" in body

    def test_series_table_links_every_package_on_pypi(self, tmp_path: Path) -> None:
        """The related-projects table has a PyPI column linking each package."""
        body = _block_body(
            render(_project("PyDB"), SERIES, tmp_path).blocks["README.md"], SERIES_START
        )
        assert "| Project | What it teaches | Repository | Docs | PyPI |" in body
        for p in SERIES:
            assert f"[{p.package}](https://pypi.org/project/{p.package}/)" in body

    def test_home_page_says_how_to_install(self) -> None:
        """The series home shows the one-line install for everything."""
        assert f"pip install {_project('PyStack').package}" in render_home(SERIES)

    def test_claude_standard_says_siblings_come_from_pypi(self) -> None:
        """The shared CLAUDE.md rule names PyPI releases, not git-tag sources."""
        standard = (TEMPLATES / "claude_standard.md").read_text(encoding="utf-8")
        assert "fromscratch-" in standard
        assert "(git + tag)" not in standard
