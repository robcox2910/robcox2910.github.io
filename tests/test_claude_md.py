"""Tests for the CLAUDE.md first-sync split."""

from pathlib import Path

from series.claude_md import END, START, split_claude_md

FIXTURE = Path(__file__).parent / "fixtures" / "pystack_CLAUDE.md"
STANDARD = """## Standard

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`
- Package manager: uv
- Run `uv run pytest` before committing
"""
PIN_LINES = [
    "- Sibling projects are pinned release tags in `[tool.uv.sources]` (git + tag); `uv.lock` records the commit",
    "- Never use `path` sources -- `tests/test_dependency_pins.py` enforces this",
]


def _fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_generic_sections_replaced_by_block() -> None:
    """Generic sections vanish and the marked block follows the title."""
    out, _ = split_claude_md(_fixture(), STANDARD)
    for heading in ("## Code Style", "## Linting", "## Testing", "## Commits", "## Dependencies"):
        assert heading not in out
    lines = out.split("\n")
    assert lines[0] == "# Claude Code Instructions"
    assert lines[2] == START
    assert out.count(START) == 1
    assert out.count(END) == 1
    assert "- Package manager: uv" in out.split(START)[1].split(END)[0]


def test_repo_specific_lines_move_to_project_notes() -> None:
    """Lines the standard lacks end up under Project notes."""
    out, moved = split_claude_md(_fixture(), STANDARD)
    for line in PIN_LINES:
        assert line in moved
        assert line in out.split("## Project notes")[1]
    assert "- Package manager: uv" not in moved
    assert all(line.strip() for line in moved)


def test_other_sections_untouched() -> None:
    """The Plugins section is kept verbatim."""
    original = _fixture()
    plugins = "## Plugins" + original.split("## Plugins")[1]
    out, _ = split_claude_md(original, STANDARD)
    assert plugins.rstrip("\n") in out


def test_second_split_is_idempotent() -> None:
    """A second split changes nothing and moves nothing."""
    once, _ = split_claude_md(_fixture(), STANDARD)
    twice, moved = split_claude_md(once, STANDARD)
    assert twice == once
    assert moved == []


def test_markers_present_replaces_only_block() -> None:
    """With markers present only the block changes."""
    text = f"# T\n\n{START}\nold\n{END}\n\n## Mine\n\n- keep\n"
    out, moved = split_claude_md(text, "new")
    assert out == f"# T\n\n{START}\nnew\n{END}\n\n## Mine\n\n- keep\n"
    assert moved == []


def test_existing_project_notes_extended_and_no_title() -> None:
    """Moved lines join an existing Project notes section; no H1 puts block on top."""
    text = "## Testing\n\n- odd rule\n\n## Project notes\n\n- mine\n\n## Other\n\n- x\n"
    out, moved = split_claude_md(text, "std")
    assert moved == ["- odd rule"]
    assert out.startswith(f"{START}\nstd\n{END}\n")
    assert "## Project notes\n\n- mine\n- odd rule\n\n## Other" in out


def test_nothing_to_move_creates_no_notes() -> None:
    """No leftover lines means no Project notes section."""
    out, moved = split_claude_md("# T\n\n## Linting\n\n- std line\n", "- std line")
    assert moved == []
    assert "Project notes" not in out
