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


def _replace_section(text: str, heading_pattern: str, block: str) -> str | None:
    """Replace the level-2 section whose heading matches, or return ``None``."""
    heading = re.search(
        rf"^## [^\n]*(?:{heading_pattern})[^\n]*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if heading is None:
        return None
    following = re.compile(r"^## ", flags=re.MULTILINE).search(text, heading.end())
    if following is None:
        return f"{text[: heading.start()]}{block}\n"
    return f"{text[: heading.start()]}{block}\n\n{text[following.start() :]}"


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


def upsert_section_block(
    text: str,
    *,
    heading_pattern: str,
    start: str,
    end: str,
    body: str,
    before_heading: str = DEFAULT_BEFORE_HEADING,
) -> str:
    """Put ``body`` between markers, creating the block if it does not exist yet.

    It tries three things in order: reuse existing markers, replace a level-2
    section whose heading matches ``heading_pattern`` (a case-insensitive
    regex), or insert a new block before ``before_heading`` (else at the end).
    """
    replaced = replace_block(text, start, end, body)
    if replaced is not None:
        return replaced
    block = f"{start}\n{body.strip(chr(10))}\n{end}"
    return _replace_section(text, heading_pattern, block) or _insert_block(
        text, block, before_heading
    )
