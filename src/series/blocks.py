"""Edit marked blocks inside text files.

Imagine a sticker on a page that says "start here" and another that says
"stop here". Everything between the stickers belongs to the series tool and
may be rewritten. Everything outside the stickers belongs to the project and
is never touched, not even by a single space.
"""

import re

DEFAULT_BEFORE_HEADING = "## License"


class BlockError(Exception):
    """Raised when the markers in a file are broken (one missing, or repeated)."""


def replace_block(text: str, start: str, end: str, body: str) -> str | None:
    """Swap the text between ``start`` and ``end`` for ``body``, keeping the markers.

    Returns ``None`` when neither marker is present. Raises ``BlockError`` when
    only one marker is present, when a marker appears more than once, or when
    the end comes before the start.
    """
    starts = text.count(start)
    ends = text.count(end)
    if starts == 0 and ends == 0:
        return None
    if starts != 1 or ends != 1:
        msg = f"expected exactly one {start!r} and one {end!r}, found {starts} and {ends}"
        raise BlockError(msg)
    start_at = text.index(start)
    end_at = text.index(end)
    if end_at < start_at:
        msg = f"{end!r} comes before {start!r}"
        raise BlockError(msg)
    return f"{text[: start_at + len(start)]}\n{body.strip(chr(10))}\n{text[end_at:]}"


TABLE_OR_LIST = re.compile(r"^\s*(?:\||[-*+] |\d+[.)] )")
FENCE = ("```", "~~~")


def _paragraphs(lines: list[str]) -> list[tuple[int, int, str]]:
    """Split section lines into ``(start, stop, kind)`` paragraphs.

    ``kind`` is ``"table"`` (a table or list), ``"prose"``, or ``"stop"`` for a
    subheading or code fence: nothing from a stop onwards is ever replaced.
    """
    paragraphs: list[tuple[int, int, str]] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        start = index
        if lines[start].startswith("#") or lines[start].lstrip().startswith(FENCE):
            paragraphs.append((start, len(lines), "stop"))
            break
        while index < len(lines) and lines[index].strip():
            index += 1
        table = any(TABLE_OR_LIST.match(line) for line in lines[start:index])
        paragraphs.append((start, index, "table" if table else "prose"))
    return paragraphs


def _old_content_length(lines: list[str]) -> int:
    """Return how many leading section lines are the old series content.

    That is the intro and the first table or list, or with no table just the
    first paragraph. A subheading or code fence ends the search, and anything
    after the old content belongs to the repo.
    """
    usable = [p for p in _paragraphs(lines) if p[2] != "stop"]
    tables = [p for p in usable if p[2] == "table"]
    if tables:
        return tables[0][1]
    return usable[0][1] if usable else 0


def _replace_section(text: str, heading_pattern: str, block: str) -> tuple[str, list[str]] | None:
    """Replace the old content of the level-2 section whose heading matches.

    Only the heading and the old table (or intro paragraph) are replaced;
    later prose and ``###`` subsections are kept after the block. Returns the
    new text and the removed non-blank lines, or ``None`` when nothing matches.
    """
    heading = re.search(
        rf"^## [^\n]*(?:{heading_pattern})[^\n]*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if heading is None:
        return None
    following = re.compile(r"^## ", flags=re.MULTILINE).search(text, heading.end())
    section_end = len(text) if following is None else following.start()
    lines = text[heading.end() : section_end].split("\n")[1:]
    dropped = _old_content_length(lines)
    removed = [heading.group(0), *(line for line in lines[:dropped] if line.strip())]
    kept = "\n".join(lines[dropped:]).strip("\n")
    new = f"{text[: heading.start()]}{block}" + (f"\n\n{kept}" if kept else "")
    if following is None:
        return f"{new}\n", removed
    return f"{new}\n\n{text[following.start() :]}", removed


def remove_block(text: str, start: str, end: str) -> str:
    """Return ``text`` without the block from ``start`` to ``end`` (markers included).

    The blank lines around the block collapse to one. Text with no markers
    comes back unchanged; broken markers raise ``BlockError``.
    """
    if replace_block(text, start, end, "") is None:
        return text
    before = text[: text.index(start)].rstrip("\n")
    after = text[text.index(end) + len(end) :].lstrip("\n")
    if not before:
        return after
    if not after:
        return f"{before}\n"
    return f"{before}\n\n{after}"


def _insert_block(text: str, block: str, before_heading: str) -> str:
    """Add the block before ``before_heading``, or at the end of the text."""
    target = re.search(rf"^{re.escape(before_heading)}[ \t]*$", text, flags=re.MULTILINE)
    if target is None:
        if not text:
            return f"{block}\n"
        return f"{text.rstrip(chr(10))}\n\n{block}\n"
    prefix = text[: target.start()]
    if prefix and not prefix.endswith("\n\n"):
        prefix = prefix.rstrip("\n") + "\n\n"
    return f"{prefix}{block}\n\n{text[target.start() :]}"


def upsert_section_block_with_removed(
    text: str,
    *,
    heading_pattern: str,
    start: str,
    end: str,
    body: str,
    before_heading: str = DEFAULT_BEFORE_HEADING,
) -> tuple[str, list[str]]:
    """Put ``body`` between markers, and return the lines a first sync replaced.

    It tries three things in order: reuse existing markers, replace the old
    content of a level-2 section whose heading matches ``heading_pattern`` (a
    case-insensitive regex), or insert a new block before ``before_heading``
    (else at the end). Only the second step removes text: the section heading
    and its old table (or intro paragraph). Those lines come back as the list,
    so a pull request can show exactly what went; anything later in the
    section stays, after the end marker.
    """
    replaced = replace_block(text, start, end, body)
    if replaced is not None:
        return replaced, []
    block = f"{start}\n{body.strip(chr(10))}\n{end}"
    section = _replace_section(text, heading_pattern, block)
    if section is not None:
        return section
    return _insert_block(text, block, before_heading), []


def upsert_section_block(
    text: str,
    *,
    heading_pattern: str,
    start: str,
    end: str,
    body: str,
    before_heading: str = DEFAULT_BEFORE_HEADING,
) -> str:
    """Put ``body`` between markers (see ``upsert_section_block_with_removed``)."""
    return upsert_section_block_with_removed(
        text,
        heading_pattern=heading_pattern,
        start=start,
        end=end,
        body=body,
        before_heading=before_heading,
    )[0]
