"""Tests for the standard pyproject keys."""

import tomllib

from packaging.requirements import Requirement

from series.tomledit import HYPOTHESIS_FLOOR, PYRIGHT_MODE, RUFF_SELECT, apply_standard_toml

EXPECTED_GROUPS = 37


def test_select_has_37_groups() -> None:
    """The standard lists exactly 37 groups."""
    assert len(RUFF_SELECT) == EXPECTED_GROUPS


def test_select_replaced_and_comments_kept() -> None:
    """Select is replaced, other comments survive."""
    text = '# top comment\n[tool.ruff.lint]\nselect = ["E"]  # old\nfoo = 1 # keep me\n'
    out = apply_standard_toml(text)
    data = tomllib.loads(out)
    assert data["tool"]["ruff"]["lint"]["select"] == list(RUFF_SELECT)
    assert "# top comment" in out
    assert "# keep me" in out
    assert data["tool"]["pyright"]["typeCheckingMode"] == PYRIGHT_MODE


def test_ignore_and_per_file_ignores_untouched() -> None:
    """Repo-owned settings are not edited."""
    text = (
        '[tool.ruff.lint]\nignore = ["E501"]\n'
        '[tool.ruff.lint.per-file-ignores]\n"tests/**" = ["S101"]\n'
        '[tool.pyright]\ntypeCheckingMode = "basic"\n'
        '[[tool.pyright.executionEnvironments]]\nroot = "tests"\n'
        "[tool.coverage.report]\nfail_under = 85\n"
    )
    data = tomllib.loads(apply_standard_toml(text))
    assert data["tool"]["ruff"]["lint"]["ignore"] == ["E501"]
    assert data["tool"]["ruff"]["lint"]["per-file-ignores"] == {"tests/**": ["S101"]}
    assert data["tool"]["pyright"]["typeCheckingMode"] == "strict"
    assert data["tool"]["pyright"]["executionEnvironments"] == [{"root": "tests"}]
    assert data["tool"]["coverage"]["report"]["fail_under"] == 85  # noqa: PLR2004


def test_missing_tables_created() -> None:
    """Tables are created when absent, and the run is idempotent."""
    text = '[project]\nname = "x"\n'
    out = apply_standard_toml(text)
    data = tomllib.loads(out)
    assert data["project"]["name"] == "x"
    assert data["tool"]["ruff"]["lint"]["select"] == list(RUFF_SELECT)
    assert data["tool"]["pyright"]["typeCheckingMode"] == "strict"
    assert apply_standard_toml(out) == out


def _dev(text: str) -> list[str]:
    """Return the ``dev`` extra of ``text`` after applying the standard."""
    return tomllib.loads(apply_standard_toml(text))["project"]["optional-dependencies"]["dev"]


def test_floor_constant() -> None:
    """The floor is the one string every repo's dev extra carries."""
    assert HYPOTHESIS_FLOOR == "hypothesis>=6.170"


def test_floor_added_when_missing() -> None:
    """A dev extra without hypothesis gains the floor and keeps its other entries."""
    text = '[project]\nname = "x"\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n'
    assert _dev(text) == ["pytest>=8", HYPOTHESIS_FLOOR]


def test_lower_floor_raised() -> None:
    """A lower ``>=`` floor is raised to the standard one, in place."""
    text = '[project.optional-dependencies]\ndev = ["hypothesis>=6.100", "pytest>=8"]\n'
    assert _dev(text) == [HYPOTHESIS_FLOOR, "pytest>=8"]


def test_higher_floor_left_alone() -> None:
    """A floor above the standard one is the repo's choice and is kept."""
    text = '[project.optional-dependencies]\ndev = ["hypothesis>=7.0"]\n'
    assert _dev(text) == ["hypothesis>=7.0"]


def test_non_floor_pin_replaced() -> None:
    """An exact pin is not a floor, so it is replaced by the standard floor."""
    text = '[project.optional-dependencies]\ndev = ["hypothesis==6.0"]\n'
    assert _dev(text) == [HYPOTHESIS_FLOOR]


def test_dev_extra_created_when_absent() -> None:
    """Missing tables are created down to the dev extra."""
    assert _dev('[project]\nname = "x"\n') == [HYPOTHESIS_FLOOR]


def test_hypothesis_in_other_extra_untouched() -> None:
    """Only the ``dev`` extra is edited."""
    text = '[project.optional-dependencies]\npebble = ["hypothesis>=6.0"]\ndev = []\n'
    extras = tomllib.loads(apply_standard_toml(text))["project"]["optional-dependencies"]
    assert extras["pebble"] == ["hypothesis>=6.0"]
    assert extras["dev"] == [HYPOTHESIS_FLOOR]


def test_floor_is_idempotent() -> None:
    """A second run changes nothing."""
    once = apply_standard_toml('[project.optional-dependencies]\ndev = ["hypothesis>=6.1"]\n')
    assert apply_standard_toml(once) == once


def test_every_hypothesis_entry_is_enforced() -> None:
    """A second, lower hypothesis entry is raised too, not skipped."""
    text = '[project.optional-dependencies]\ndev = ["hypothesis>=7.0", "hypothesis>=6.0"]\n'
    assert _dev(text) == ["hypothesis>=7.0", HYPOTHESIS_FLOOR]


def test_extras_and_markers_survive_a_raise() -> None:
    """Raising the floor keeps the entry's extras and environment marker."""
    text = (
        "[project.optional-dependencies]\n"
        "dev = [\"hypothesis[cli,pytz]==6.0 ; python_version >= '3.12'\"]\n"
    )
    (entry,) = _dev(text)
    req = Requirement(entry)
    assert req.name == "hypothesis"
    assert req.extras == {"cli", "pytz"}
    assert str(req.specifier) == ">=6.170"
    assert req.marker is not None
    assert str(req.marker) == 'python_version >= "3.12"'
