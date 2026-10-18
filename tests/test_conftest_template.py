"""Tests for the owned root ``conftest.py`` that holds the shared Hypothesis profiles."""

import subprocess
import sys
from pathlib import Path

import pytest

from series.render import TEMPLATES
from series.tomledit import PYRIGHT_MODE, RUFF_SELECT

pytest_plugins = ["pytester"]

TEMPLATE = TEMPLATES / "conftest.py"
CI_EXAMPLES = 100
THOROUGH_EXAMPLES = 2000


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
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(passed=1)


def test_thorough_flag_overrides_ci(pytester: pytest.Pytester) -> None:
    """``--hypothesis-profile=thorough`` swaps in the long, randomised profile."""
    pytester.makeconftest(TEMPLATE.read_text(encoding="utf-8"))
    pytester.makepyfile(f"""
        from hypothesis import settings

        def test_p():
            s = settings()
            assert (s.max_examples, s.deadline, s.derandomize) == ({THOROUGH_EXAMPLES}, None, False)
    """)
    pytester.runpytest("--hypothesis-profile=thorough").assert_outcomes(passed=1)


def test_template_passes_the_standard(tmp_path: Path) -> None:
    """The owned file itself passes ruff with the 37 groups and pyright strict."""
    (tmp_path / "conftest.py").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    groups = ", ".join(f'"{group}"' for group in RUFF_SELECT)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\ntarget-version = "py314"\n'
        f"[tool.ruff.lint]\nselect = [{groups}]\n"
        'ignore = ["E501", "D203", "D213", "ISC001", "TRY003", "TRY300"]\n'
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
