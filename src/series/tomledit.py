"""Set the shared standard keys in a ``pyproject.toml`` without disturbing the rest.

Three things belong to the series standard: the ruff rule groups, the pyright
mode and the Hypothesis floor in the ``dev`` extra. Everything else (ignores, per-file ignores, coverage floors,
comments, ordering) is left exactly as the project wrote it.
"""

from typing import Any, cast

import tomlkit
from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import Version
from tomlkit import TOMLDocument
from tomlkit.items import Table

RUFF_SELECT: tuple[str, ...] = (
    "E", "W", "F", "I", "N", "UP", "B", "C4", "C90", "PTH", "SIM",
    "TID", "S", "PERF", "FURB", "PIE", "T10", "T20", "ERA", "PL",
    "RET", "ARG", "FBT", "DTZ", "ICN", "PT", "D", "RUF", "A", "BLE",
    "EM", "FLY", "ISC", "PGH", "RSE", "SLF", "TRY",
)  # fmt: skip
PYRIGHT_MODE = "strict"
HYPOTHESIS_FLOOR = "hypothesis>=6.170"
_FLOOR_VERSION = Version(HYPOTHESIS_FLOOR.removeprefix("hypothesis>="))


def _table(parent: Any, key: str) -> Any:
    """Return ``parent[key]``, creating an empty table first if it is missing."""
    if key not in parent:
        parent[key] = tomlkit.table(is_super_table=True)
    return parent[key]


def _is_hypothesis(entry: str) -> bool:
    """Return whether the requirement string ``entry`` names Hypothesis."""
    try:
        return Requirement(entry).name.lower() == "hypothesis"
    except InvalidRequirement:
        return False


def _meets_floor(entry: str) -> bool:
    """Return whether ``entry`` has a ``>=`` specifier at or above the standard floor."""
    return any(
        spec.operator == ">=" and Version(spec.version) >= _FLOOR_VERSION
        for spec in Requirement(entry).specifier
    )


def ensure_dev_floor(doc: TOMLDocument) -> None:
    """Make ``[project.optional-dependencies] dev`` require Hypothesis at the floor or above.

    A Hypothesis entry that already has a higher ``>=`` floor is the repo's choice
    and stays. Any other entry (a lower floor, an exact pin) is replaced in place;
    if there is none the floor is appended. Missing tables are created. Other
    extras are never touched.
    """
    project = _table(doc, "project")
    extras = _table(project, "optional-dependencies")
    if "dev" not in extras:
        extras["dev"] = tomlkit.array()
    dev = extras["dev"]
    for index, entry in enumerate(dev):
        if _is_hypothesis(str(entry)):
            if not _meets_floor(str(entry)):
                dev[index] = HYPOTHESIS_FLOOR
            return
    dev.append(HYPOTHESIS_FLOOR)


def apply_standard_toml(text: str) -> str:
    """Return ``text`` with the standard ruff ``select``, pyright mode and Hypothesis floor set."""
    doc = tomlkit.parse(text)
    tool = _table(doc, "tool")
    ruff = _table(tool, "ruff")
    lint = _table(ruff, "lint")
    select = tomlkit.array(str(list(RUFF_SELECT)).replace("'", '"'))
    select.multiline(True)
    lint["select"] = select
    pyright = _table(tool, "pyright")
    pyright["typeCheckingMode"] = PYRIGHT_MODE
    ensure_dev_floor(doc)
    return tomlkit.dumps(cast("Table", doc))
