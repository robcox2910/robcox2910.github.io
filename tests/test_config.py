"""Tests for loading the series list from series.yml."""

import tomllib
from pathlib import Path

import pytest

from series.config import SERIES_FILE, Project, SeriesError, load_series

EXPECTED_COUNT = 18
EXPECTED_NAMES = [
    "PyOS",
    "Pebble",
    "PyDB",
    "PyKV",
    "PyDocDB",
    "PyGraphDB",
    "PyTSDB",
    "PyVecDB",
    "PyColDB",
    "PyCrypt",
    "PyNet",
    "PyWeb",
    "PyGit",
    "PySearch",
    "PyMQ",
    "PyLLM",
    "PyScheduler",
    "PyStack",
]
VALID_ENTRY = """\
  - name: {name}
    repo: {name}
    folder: {name}
    package: {name}
    teaches: Things
    property: Things stay put
    builds_on: {builds_on}
"""


def _write(tmp_path: Path, text: str) -> Path:
    """Write ``text`` to a temporary series file and return its path."""
    path = tmp_path / "series.yml"
    path.write_text(text, encoding="utf-8")
    return path


class TestRealSeries:
    """Checks on the real series.yml shipped in this repo."""

    def test_series_has_all_18_projects_in_order(self) -> None:
        """All 18 projects appear, PyStack last."""
        names = [p.name for p in load_series()]
        assert len(names) == EXPECTED_COUNT
        assert names == EXPECTED_NAMES

    def test_folder_and_repo_differ_for_pyos_and_pydocdb(self) -> None:
        """PyOS and PyDocDB have checkout folders that differ from their repo names."""
        by_name = {p.name: p for p in load_series()}
        assert (by_name["PyOS"].folder, by_name["PyOS"].repo) == ("os_learning", "py-os")
        assert (by_name["PyDocDB"].folder, by_name["PyDocDB"].repo) == ("pydocdb", "pydoc-db")

    def test_builds_on_names_exist_and_come_earlier(self) -> None:
        """Every builds_on name is a project listed earlier in the series."""
        seen: set[str] = set()
        for project in load_series():
            assert set(project.builds_on) <= seen
            seen.add(project.name)

    def test_site_url(self) -> None:
        """PyDB's site lives under the shared GitHub Pages address."""
        by_name = {p.name: p for p in load_series()}
        assert by_name["PyDB"].site_url == "https://robcox2910.github.io/pydb/"

    def test_github_url(self) -> None:
        """PyDocDB's GitHub address uses its repo name, not its folder."""
        by_name = {p.name: p for p in load_series()}
        assert by_name["PyDocDB"].github_url == "https://github.com/robcox2910/pydoc-db"


class TestValidation:
    """Checks that bad series files are rejected with a clear error."""

    def test_missing_field_raises_series_error(self, tmp_path: Path) -> None:
        """A project without a teaches line is rejected."""
        path = _write(tmp_path, "projects:\n  - name: A\n    repo: a\n")
        with pytest.raises(SeriesError, match="missing"):
            load_series(path)

    def test_property_field_required(self, tmp_path: Path) -> None:
        """A project without a property line is rejected, and the error names the field."""
        text = "projects:\n" + VALID_ENTRY.format(name="A", builds_on="[]").replace(
            "    property: Things stay put\n", ""
        )
        with pytest.raises(SeriesError, match="missing: property"):
            load_series(_write(tmp_path, text))

    def test_duplicate_name_raises_series_error(self, tmp_path: Path) -> None:
        """Two projects with the same name are rejected."""
        text = "projects:\n" + VALID_ENTRY.format(name="A", builds_on="[]") * 2
        with pytest.raises(SeriesError, match="duplicate"):
            load_series(_write(tmp_path, text))

    def test_duplicate_repo_raises_series_error(self, tmp_path: Path) -> None:
        """Two projects with the same repo are rejected."""
        first = VALID_ENTRY.format(name="A", builds_on="[]")
        second = VALID_ENTRY.format(name="B", builds_on="[]").replace("repo: B", "repo: A")
        with pytest.raises(SeriesError, match="duplicate"):
            load_series(_write(tmp_path, "projects:\n" + first + second))

    def test_unknown_builds_on_raises_series_error(self, tmp_path: Path) -> None:
        """A builds_on name that is not in the series is rejected."""
        text = "projects:\n" + VALID_ENTRY.format(name="A", builds_on="[Nope]")
        with pytest.raises(SeriesError, match="unknown"):
            load_series(_write(tmp_path, text))

    def test_builds_on_later_project_raises_series_error(self, tmp_path: Path) -> None:
        """A builds_on name that is listed later is rejected."""
        text = (
            "projects:\n"
            + VALID_ENTRY.format(name="A", builds_on="[B]")
            + VALID_ENTRY.format(name="B", builds_on="[]")
        )
        with pytest.raises(SeriesError, match="later"):
            load_series(_write(tmp_path, text))

    def test_bad_shape_raises_series_error(self, tmp_path: Path) -> None:
        """A file without a projects list is rejected."""
        with pytest.raises(SeriesError, match="projects"):
            load_series(_write(tmp_path, "nothing: here\n"))

    def test_non_mapping_project_raises_series_error(self, tmp_path: Path) -> None:
        """A project entry that is not a mapping is rejected."""
        with pytest.raises(SeriesError, match="mapping"):
            load_series(_write(tmp_path, "projects:\n  - just a string\n"))

    def test_project_is_frozen(self) -> None:
        """Projects cannot be changed after loading."""
        project = load_series()[0]
        assert isinstance(project, Project)
        with pytest.raises(AttributeError):
            project.name = "Other"  # pyright: ignore[reportAttributeAccessIssue]


def test_hub_does_not_depend_on_pip_audit() -> None:
    """pip-audit runs through ``uvx``, so the hub, like every repo, never depends on it."""
    pyproject = tomllib.loads((SERIES_FILE.parent / "pyproject.toml").read_text(encoding="utf-8"))
    groups = [*pyproject["dependency-groups"].values(), pyproject["project"]["dependencies"]]
    assert not [dep for group in groups for dep in group if dep.startswith("pip-audit")]
