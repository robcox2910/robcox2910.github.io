"""Set the shared standard keys in a ``pyproject.toml`` without disturbing the rest.

Three things belong to the series standard: the ruff rule groups, the pyright
mode and the Hypothesis floor in the ``dev`` extra. Everything else (ignores,
per-file ignores, coverage floors, comments, ordering) is left exactly as the
project wrote it.
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


def _raised(entry: str) -> str:
    """Return ``entry`` with its version specifier replaced by the floor, extras and marker kept."""
    req = Requirement(entry)
    extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    marker = f" ; {req.marker}" if req.marker is not None else ""
    return f"{HYPOTHESIS_FLOOR.replace('hypothesis', 'hypothesis' + extras, 1)}{marker}"


def ensure_dev_floor(doc: TOMLDocument) -> None:
    """Make ``[project.optional-dependencies] dev`` require Hypothesis at the floor or above.

    Every Hypothesis entry is checked. One that already has a higher ``>=`` floor
    is the repo's choice and stays. Any other (a lower floor, an exact pin) gets
    the floor in place, keeping its extras and environment marker; if there is
    no entry the floor is appended. Missing tables are created. Other
    extras are never touched.
    """
    project = _table(doc, "project")
    extras = _table(project, "optional-dependencies")
    if "dev" not in extras:
        extras["dev"] = tomlkit.array()
    dev = extras["dev"]
    found = False
    for index, entry in enumerate(dev):
        if _is_hypothesis(str(entry)):
            found = True
            if not _meets_floor(str(entry)):
                dev[index] = _raised(str(entry))
    if not found:
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
