"""Move a project's CLAUDE.md onto the shared standard, once.

The first sync swaps the generic sections (style, linting, testing, commits,
dependencies) for one marked standard block. Lines in those sections that the
standard does not already say are not thrown away: they move under
``## Project notes`` so the project keeps its own rules.
"""

from series.blocks import replace_block

START = "<!-- standard:start -->"
END = "<!-- standard:end -->"
GENERIC_SECTIONS = frozenset({"code style", "linting", "testing", "commits", "dependencies"})
NOTES_HEADING = "## Project notes"


def _remove_generic(lines: list[str]) -> tuple[list[str], list[str]]:
    """Drop the generic level-2 sections; return the kept lines and the moved lines."""
    kept: list[str] = []
    moved: list[str] = []
    in_generic = False
    for line in lines:
        if line.startswith("## "):
            in_generic = line[3:].strip().lower() in GENERIC_SECTIONS
            if in_generic:
                continue
        if in_generic:
            moved.append(line)
        else:
            kept.append(line)
    return kept, moved


def _add_notes(lines: list[str], moved: list[str]) -> list[str]:
    """Append ``moved`` to the Project notes section, creating it when missing."""
    if not moved:
        return lines
    heading_at = next(
        (i for i, line in enumerate(lines) if line.strip().lower() == NOTES_HEADING.lower()),
        None,
    )
    if heading_at is None:
        return [*lines, "", NOTES_HEADING, "", *moved]
    end = next(
        (i for i in range(heading_at + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    while end > heading_at + 1 and not lines[end - 1].strip():
        end -= 1
    tail = lines[end:]
    if tail and tail[0].strip():
        tail = ["", *tail]
    return [*lines[:end], *moved, *tail]


def split_claude_md(text: str, standard: str) -> tuple[str, list[str]]:
    """Put the standard block into ``text``; return the new text and any moved lines."""
    replaced = replace_block(text, START, END, standard)
    if replaced is not None:
        return replaced, []
    kept, removed = _remove_generic(text.split("\n"))
    known = {line.strip() for line in standard.split("\n")}
    moved = [line for line in removed if line.strip() and line.strip() not in known]
    block = [START, *standard.strip("\n").split("\n"), END]
    title_at = next((i for i, line in enumerate(kept) if line.startswith("# ")), None)
    at = 0 if title_at is None else title_at + 1
    rest = kept[at:]
    while rest and not rest[0].strip():
        rest.pop(0)
    head = kept[:at]
    lines = [*head, *([""] if head else []), *block, *([""] if rest else []), *rest]
    lines = _add_notes(lines, moved)
    out = "\n".join(lines)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out.rstrip("\n") + "\n", moved
