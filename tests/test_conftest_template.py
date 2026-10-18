"""Tests for the owned root ``conftest.py`` that holds the shared Hypothesis profiles."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from series.config import SERIES_FILE
from series.render import TEMPLATES
from series.tomledit import PYRIGHT_MODE, RUFF_SELECT

pytest_plugins = ["pytester"]

TEMPLATE = TEMPLATES / "conftest.py"
CI_EXAMPLES = 100
THOROUGH_EXAMPLES = 2000
HUB_PYPROJECT = SERIES_FILE.parent / "pyproject.toml"


def run(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    """Run pytest on the scratch project in a subprocess.

    ``runpytest`` is in-process: the template's ``settings.load_profile`` and
    its ``--hypothesis-profile`` option would leak into the hub's own session.
    A subprocess keeps them out. The cache plugin is off so no ``.pytest_cache``
    is written.
    """
    return pytester.runpytest_subprocess("-p", "no:cacheprovider", *args)


def test_ci_profile_is_default(pytester: pytest.Pytester) -> None:
    """With no flag the deterministic, database-free ``ci`` profile is loaded."""
    pytester.makeconftest(TEMPLATE.read_text(encoding="utf-8"))
    pytester.makepyfile(f"""
        from hypothesis import settings

        def test_p():
            s = settings()
            assert (s.max_examples, s.deadline, s.derandomize, s.database) == (
                {CI_EXAMPLES}, None, True, None
            )
    """)
    run(pytester).assert_outcomes(passed=1)


def test_thorough_flag_overrides_ci(pytester: pytest.Pytester) -> None:
    """``--hypothesis-profile=thorough`` swaps in the long, randomised profile."""
    pytester.makeconftest(TEMPLATE.read_text(encoding="utf-8"))
    pytester.makepyfile(f"""
        from hypothesis import settings

        def test_p():
            s = settings()
            assert (s.max_examples, s.deadline, s.derandomize) == ({THOROUGH_EXAMPLES}, None, False)
    """)
    run(pytester, "--hypothesis-profile=thorough").assert_outcomes(passed=1)


def test_template_passes_the_standard(tmp_path: Path) -> None:
    """The owned file itself passes ruff with the 37 groups and pyright strict."""
    (tmp_path / "conftest.py").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    groups = ", ".join(f'"{group}"' for group in RUFF_SELECT)
    # The hub's own ignore list is the series' common one (line length, docstring
    # style clashes, formatter overlaps), so the template is held to what a synced
    # repo is held to rather than to a second list kept here.
    hub = tomllib.loads(HUB_PYPROJECT.read_text(encoding="utf-8"))
    ignore = ", ".join(f'"{rule}"' for rule in hub["tool"]["ruff"]["lint"]["ignore"])
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\ntarget-version = "py314"\n'
        f"[tool.ruff.lint]\nselect = [{groups}]\n"
        f"ignore = [{ignore}]\n"
        f'[tool.pyright]\ntypeCheckingMode = "{PYRIGHT_MODE}"\n'
        f'pythonVersion = "3.14"\npythonPlatform = "All"\nvenvPath = "{Path(sys.prefix).parent}"\n'
        f'venv = "{Path(sys.prefix).name}"\n',
        encoding="utf-8",
    )
    for tool in (["ruff", "check", "."], ["pyright", "."]):
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-m", *tool], cwd=tmp_path, capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
