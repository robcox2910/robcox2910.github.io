"""Load the list of series projects from ``series.yml``.

Think of ``series.yml`` as the table of contents of a book: it lists every
project in the order you should read them. This module reads it and checks
that nothing is missing, repeated or out of order.
"""

import builtins
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

SERIES_FILE = Path(__file__).resolve().parent.parent.parent / "series.yml"
SITE_ROOT = "https://robcox2910.github.io"
GITHUB_ROOT = "https://github.com/robcox2910"
REQUIRED_FIELDS = ("name", "repo", "folder", "package", "teaches", "property", "builds_on")

# Shown in search results and link previews for the series home page, and used
# as the hub repo's GitHub description.
HUB_DESCRIPTION = (
    "Build real systems from scratch in Python: an operating system, a compiler, "
    "databases, networking and a language model, explained for learners aged 12+."
)

# Every repo gets these GitHub topics before its own; GitHub allows 20 in all.
COMMON_TOPICS = (
    "python",
    "education",
    "from-scratch",
    "build-your-own-x",
    "learn-by-doing",
    "computer-science",
    "tdd",
)
MAX_TOPICS = 20
TOPIC = re.compile(r"[a-z0-9][a-z0-9-]{0,49}")

# The GoatCounter site code (the "code" in https://<code>.goatcounter.com).
# Empty means no analytics script; set it, then run `series hub` and `series sync`.
GOATCOUNTER_CODE = "robcox"


class SeriesError(Exception):
    """Raised when ``series.yml`` is not a valid list of projects."""


@dataclass(frozen=True)
class Project:
    """One project in the series.

    Attributes:
        name: Display name, such as ``PyDB``.
        repo: GitHub repository name.
        folder: Checkout directory name next to the other projects.
        package: Python distribution name.
        teaches: A short phrase saying what the project teaches.
        property: One line saying which property its property-testing page walks through.
        builds_on: Names of earlier projects this one uses.
        description: One sentence for search results, link previews and the
            GitHub "About" box. Empty means none is set.
        topics: The project's own GitHub topics, added after ``COMMON_TOPICS``.

    """

    name: str
    repo: str
    folder: str
    package: str
    teaches: str
    property: str
    builds_on: tuple[str, ...]
    description: str = ""
    topics: tuple[str, ...] = ()

    @builtins.property  # bare `property` is the field above
    def all_topics(self) -> tuple[str, ...]:
        """Return the common topics then the project's own, without repeats."""
        return tuple(dict.fromkeys((*COMMON_TOPICS, *self.topics)))

    @builtins.property  # bare `property` is the field above
    def site_url(self) -> str:
        """Return the address of the project's documentation site."""
        return f"{SITE_ROOT}/{self.repo}/"

    @builtins.property  # bare `property` is the field above
    def github_url(self) -> str:
        """Return the address of the project's GitHub repository."""
        return f"{GITHUB_ROOT}/{self.repo}"


def _parse_project(entry: object) -> Project:
    """Turn one YAML entry into a ``Project``, or raise ``SeriesError``."""
    if not isinstance(entry, dict):
        msg = f"each project must be a mapping, got {entry!r}"
        raise SeriesError(msg)
    fields = cast("dict[str, Any]", entry)
    label = str(fields.get("name", "?"))
    missing = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing:
        msg = f"project {label} is missing: {', '.join(missing)}"
        raise SeriesError(msg)
    topics = tuple(str(item) for item in fields.get("topics") or ())
    bad = [topic for topic in topics if not TOPIC.fullmatch(topic)]
    if bad:
        msg = f"project {label} has invalid topics (lowercase, digits, hyphens): {bad}"
        raise SeriesError(msg)
    if len({*COMMON_TOPICS, *topics}) > MAX_TOPICS:
        msg = f"project {label} has more than {MAX_TOPICS} topics with the common ones"
        raise SeriesError(msg)
    return Project(
        name=str(fields["name"]),
        repo=str(fields["repo"]),
        folder=str(fields["folder"]),
        package=str(fields["package"]),
        teaches=str(fields["teaches"]),
        property=str(fields["property"]),
        builds_on=tuple(str(item) for item in fields["builds_on"] or ()),
        description=str(fields.get("description") or "").strip(),
        topics=topics,
    )


def _check(projects: list[Project]) -> None:
    """Check for duplicates and bad ``builds_on`` entries, or raise ``SeriesError``."""
    seen: set[str] = set()
    repos: set[str] = set()
    all_names = {project.name for project in projects}
    for project in projects:
        if project.name in seen or project.repo in repos:
            msg = f"duplicate name or repo: {project.name} / {project.repo}"
            raise SeriesError(msg)
        for other in project.builds_on:
            if other not in all_names:
                msg = f"{project.name} builds on unknown project {other}"
                raise SeriesError(msg)
            if other not in seen:
                msg = f"{project.name} builds on {other}, which comes later"
                raise SeriesError(msg)
        seen.add(project.name)
        repos.add(project.repo)


def load_series(path: Path = SERIES_FILE) -> list[Project]:
    """Read and validate the series file, returning projects in learning order."""
    data: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = cast("dict[str, Any]", data).get("projects") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        msg = f"{path} must contain a 'projects' list"
        raise SeriesError(msg)
    projects = [_parse_project(entry) for entry in cast("list[object]", entries)]
    _check(projects)
    return projects
