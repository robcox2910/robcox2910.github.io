"""Tests for the standard pyproject keys."""

import tomllib

from series.tomledit import PYRIGHT_MODE, RUFF_SELECT, apply_standard_toml

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
