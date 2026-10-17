"""Tests for editing marked blocks inside text files."""

import pytest

from series.blocks import BlockError, replace_block, upsert_section_block

START = "<!-- series:start -->"
END = "<!-- series:end -->"
HEADING_PATTERN = "related projects"
BODY = "| PyDB | a database |\n| PyKV | a store |"
BEFORE = "# Title\n\nIntro text.\n\n"
AFTER = "\n\n## License\n\nMIT\n"
VARIANT_HEADING = '## Related projects — "from scratch in Python"'
OLD_TABLE = "| Old | table |\n|-----|-------|\n| a | b |"


def _upsert(text: str) -> str:
    return upsert_section_block(
        text,
        heading_pattern=HEADING_PATTERN,
        start=START,
        end=END,
        body=BODY,
    )


class TestReplaceBlock:
    """Tests for ``replace_block``."""

    def test_replace_between_markers_only(self) -> None:
        """Check that replace between markers only."""
        text = f"{BEFORE}{START}\nold\n{END}{AFTER}"
        result = replace_block(text, START, END, "new")
        assert result == f"{BEFORE}{START}\nnew\n{END}{AFTER}"

    def test_text_outside_blocks_untouched(self) -> None:
        """Check that text outside blocks untouched."""
        before = "  odd \t whitespace\r\n\né trailing   \n"
        after = "\n\n\n  end without newline"
        text = f"{before}{START}\nold\n{END}{after}"
        result = replace_block(text, START, END, "new")
        assert result is not None
        assert result.startswith(before + START)
        assert result.endswith(END + after)

    def test_missing_markers_returns_none(self) -> None:
        """Check that missing markers returns none."""
        assert replace_block("no markers here", START, END, "new") is None

    def test_single_marker_raises(self) -> None:
        """Check that single marker raises."""
        with pytest.raises(BlockError):
            replace_block(f"{START}\nonly the start", START, END, "new")

    def test_only_end_marker_raises(self) -> None:
        """Check that only end marker raises."""
        with pytest.raises(BlockError):
            replace_block(f"only the end\n{END}", START, END, "new")

    def test_two_pairs_raises(self) -> None:
        """Check that two pairs raises."""
        text = f"{START}\na\n{END}\n{START}\nb\n{END}"
        with pytest.raises(BlockError):
            replace_block(text, START, END, "new")

    def test_end_before_start_raises(self) -> None:
        """Check that end before start raises."""
        with pytest.raises(BlockError):
            replace_block(f"{END}\nx\n{START}", START, END, "new")


class TestUpsertSectionBlock:
    """Tests for ``upsert_section_block``."""

    def test_existing_markers_are_replaced(self) -> None:
        """Check that existing markers are replaced."""
        text = f"{BEFORE}## Related projects\n\n{START}\nold\n{END}{AFTER}"
        result = _upsert(text)
        assert result == f"{BEFORE}## Related projects\n\n{START}\n{BODY}\n{END}{AFTER}"

    def test_first_sync_replaces_variant_heading(self) -> None:
        """Check that first sync replaces variant heading."""
        text = f"{BEFORE}{VARIANT_HEADING}\n\n{OLD_TABLE}{AFTER}"
        result = _upsert(text)
        assert result == f"{BEFORE}{START}\n{BODY}\n{END}{AFTER}"
        assert "Old" not in result

    def test_section_at_end_of_file_is_replaced(self) -> None:
        """Check that section at end of file is replaced."""
        text = f"{BEFORE}{VARIANT_HEADING}\n\n{OLD_TABLE}\n"
        assert _upsert(text) == f"{BEFORE}{START}\n{BODY}\n{END}\n"

    def test_heading_match_ignores_case(self) -> None:
        """Check that heading match ignores case."""
        text = f"{BEFORE}## RELATED PROJECTS\n\nstuff{AFTER}"
        assert START in _upsert(text)

    def test_missing_section_inserted_before_license(self) -> None:
        """Check that missing section inserted before license."""
        text = f"{BEFORE.rstrip()}{AFTER}"
        result = _upsert(text)
        assert result == f"# Title\n\nIntro text.\n\n{START}\n{BODY}\n{END}\n\n## License\n\nMIT\n"

    def test_missing_section_appended_when_no_license(self) -> None:
        """Check that missing section appended when no license."""
        result = _upsert("# Title\n\nIntro text.\n")
        assert result == f"# Title\n\nIntro text.\n\n{START}\n{BODY}\n{END}\n"

    def test_append_adds_newline_when_missing(self) -> None:
        """Check that append adds newline when missing."""
        result = _upsert("# Title")
        assert result == f"# Title\n\n{START}\n{BODY}\n{END}\n"

    def test_empty_text_gets_just_the_block(self) -> None:
        """Check that empty text gets just the block."""
        assert _upsert("") == f"{START}\n{BODY}\n{END}\n"

    def test_license_without_blank_line_gets_one(self) -> None:
        """Check that license without blank line gets one."""
        result = _upsert("# Title\n## License\nMIT\n")
        assert result == f"# Title\n\n{START}\n{BODY}\n{END}\n\n## License\nMIT\n"

    def test_custom_before_heading(self) -> None:
        """Check that custom before heading."""
        text = "# T\n\n## Docs\n\nx\n\n## License\n\nMIT\n"
        result = upsert_section_block(
            text,
            heading_pattern="nothing matches",
            start=START,
            end=END,
            body=BODY,
            before_heading="## Docs",
        )
        assert result.index(START) < result.index("## Docs")

    @pytest.mark.parametrize(
        "text",
        [
            f"{BEFORE}{VARIANT_HEADING}\n\n{OLD_TABLE}{AFTER}",
            f"{BEFORE.rstrip()}{AFTER}",
            "# Title\n\nIntro text.\n",
            f"{BEFORE}{START}\nold\n{END}{AFTER}",
        ],
    )
    def test_upsert_is_idempotent(self, text: str) -> None:
        """Check that upsert is idempotent."""
        once = _upsert(text)
        assert _upsert(once) == once
