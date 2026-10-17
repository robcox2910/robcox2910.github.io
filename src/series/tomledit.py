"""Set the shared standard keys in a ``pyproject.toml`` without disturbing the rest.

Only two keys belong to the series standard: the ruff rule groups and the
pyright mode. Everything else (ignores, per-file ignores, coverage floors,
comments, ordering) is left exactly as the project wrote it.
"""

from typing import Any, cast

import tomlkit
from tomlkit.items import Table

RUFF_SELECT: tuple[str, ...] = (
    "E", "W", "F", "I", "N", "UP", "B", "C4", "C90", "PTH", "SIM",
    "TID", "S", "PERF", "FURB", "PIE", "T10", "T20", "ERA", "PL",
    "RET", "ARG", "FBT", "DTZ", "ICN", "PT", "D", "RUF", "A", "BLE",
    "EM", "FLY", "ISC", "PGH", "RSE", "SLF", "TRY",
)  # fmt: skip
PYRIGHT_MODE = "strict"


def _table(parent: Any, key: str) -> Any:
    """Return ``parent[key]``, creating an empty table first if it is missing."""
    if key not in parent:
        parent[key] = tomlkit.table(is_super_table=True)
    return parent[key]


def apply_standard_toml(text: str) -> str:
    """Return ``text`` with the standard ruff ``select`` and pyright mode set."""
    doc = tomlkit.parse(text)
    tool = _table(doc, "tool")
    ruff = _table(tool, "ruff")
    lint = _table(ruff, "lint")
    select = tomlkit.array(str(list(RUFF_SELECT)).replace("'", '"'))
    select.multiline(True)
    lint["select"] = select
    pyright = _table(tool, "pyright")
    pyright["typeCheckingMode"] = PYRIGHT_MODE
    return tomlkit.dumps(cast("Table", doc))
