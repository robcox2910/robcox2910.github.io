"""Tests for what helps people find the series: descriptions, topics, analytics and About boxes."""

from pathlib import Path

import pytest

from series.config import (
    COMMON_TOPICS,
    HUB_DESCRIPTION,
    MAX_TOPICS,
    Project,
    SeriesError,
    load_series,
)
from series.render import OVERRIDES_MAIN, Rendered, apply_mkdocs_blocks, overrides_main, render
from series.sync import (
    HUB_FILES,
    HUB_REPO,
    ROBOTS_TXT,
    About,
    about_drift,
    about_settings,
    render_home,
    render_robots,
)

SERIES = load_series()
SEARCH_SNIPPET_LIMIT = 160
GOOD_ENTRY = """\
projects:
  - name: PyNew
    repo: pynew
    folder: pynew
    package: pynew
    teaches: Things
    property: A rule.
    builds_on: []
    topics: {topics}
"""


def _write(tmp_path: Path, topics: str) -> Path:
    """Write a one-project series file with the given topics and return its path."""
    path = tmp_path / "series.yml"
    path.write_text(GOOD_ENTRY.format(topics=topics), encoding="utf-8")
    return path


class TestDescriptionsAndTopics:
    """Every project carries a pitch and topics, and bad topics are rejected."""

    def test_every_project_has_a_short_description(self) -> None:
        """Each description exists and fits in a search-result snippet."""
        for project in SERIES:
            assert project.description, project.name
            assert len(project.description) <= SEARCH_SNIPPET_LIMIT, project.name

    def test_every_project_has_its_own_topics(self) -> None:
        """Each project adds topics of its own after the common ones."""
        for project in SERIES:
            assert project.topics, project.name
            assert project.all_topics[: len(COMMON_TOPICS)] == COMMON_TOPICS
            assert len(project.all_topics) <= MAX_TOPICS

    def test_all_topics_drops_repeats(self) -> None:
        """A project topic that is already common appears once."""
        project = Project("A", "a", "a", "a", "Things", "A rule.", (), topics=("python", "extra"))
        assert project.all_topics == (*COMMON_TOPICS, "extra")

    def test_missing_description_and_topics_are_allowed(self, tmp_path: Path) -> None:
        """Both fields are optional, so an older series file still loads."""
        (project,) = load_series(_write(tmp_path, "[]"))
        assert (project.description, project.topics) == ("", ())

    @pytest.mark.parametrize("topics", ["[Bad_Topic]", "[has space]", "[-leading]"])
    def test_invalid_topic_is_rejected(self, tmp_path: Path, topics: str) -> None:
        """GitHub topics are lowercase letters, digits and hyphens."""
        with pytest.raises(SeriesError, match="invalid topics"):
            load_series(_write(tmp_path, topics))

    def test_too_many_topics_is_rejected(self, tmp_path: Path) -> None:
        """GitHub allows 20 topics, counting the common ones."""
        many = ", ".join(f"t{n}" for n in range(MAX_TOPICS))
        with pytest.raises(SeriesError, match="more than"):
            load_series(_write(tmp_path, f"[{many}]"))


class TestAnalytics:
    """The theme override page carries GoatCounter only when a code is set."""

    def test_code_adds_the_script(self) -> None:
        """With a code, the analytics block loads GoatCounter for that site."""
        page = overrides_main("example")
        assert "https://example.goatcounter.com/count" in page
        assert "{% block analytics %}" in page
        assert "{{ super() }}" in page

    def test_no_code_only_extends_the_base(self) -> None:
        """With no code, the page changes nothing about the site."""
        assert overrides_main("") == '{% extends "base.html" %}\n'

    def test_every_project_gets_the_override_page(self, tmp_path: Path) -> None:
        """The override page is a synced file, because the theme's custom_dir needs it."""
        rendered = render(SERIES[0], SERIES, tmp_path)
        assert rendered.files[OVERRIDES_MAIN] == overrides_main()


class TestSiteDescription:
    """The sync owns the top-level site_description key."""

    BASE = "site_name: X\nsite_url: https://example.com/\nrepo_url: r\n"

    def _apply(self, text: str, description: str, root: Path) -> str:
        """Apply the series blocks, with ``description``, to ``text``."""
        (root / "mkdocs.yml").write_text(text, encoding="utf-8")
        rendered = render(SERIES[0], SERIES, root)
        rendered = Rendered(
            files=rendered.files,
            blocks=rendered.blocks,
            nav_fallback=rendered.nav_fallback,
            site_description=description,
        )
        return apply_mkdocs_blocks(text, rendered)

    def test_added_after_site_url(self, tmp_path: Path) -> None:
        """A missing description goes straight after site_url, quoted."""
        out = self._apply(self.BASE, "Build: things", tmp_path)
        lines = out.splitlines()
        assert lines[2] == 'site_description: "Build: things"'

    def test_existing_description_is_replaced_once(self, tmp_path: Path) -> None:
        """An old description is replaced, and a second apply changes nothing."""
        text = self.BASE + "site_description: old words\n"
        once = self._apply(text, "New words", tmp_path)
        assert "old words" not in once
        assert once.count("site_description:") == 1
        assert self._apply(once, "New words", tmp_path) == once

    def test_empty_description_leaves_the_file_alone(self, tmp_path: Path) -> None:
        """No description means the key is neither added nor removed."""
        text = self.BASE + "site_description: keep me\n"
        assert "keep me" in self._apply(text, "", tmp_path)

    def test_new_mkdocs_gets_the_description(self, tmp_path: Path) -> None:
        """A repo with no mkdocs.yml gets one that already has the description."""
        rendered = render(SERIES[0], SERIES, tmp_path)
        assert "site_description:" in rendered.files["mkdocs.yml"]


class TestHomePage:
    """The hub home page sells the series before it lists it."""

    def test_home_has_pitch_audience_and_description(self) -> None:
        """The page says what you build, who it is for, and carries a meta description."""
        home = render_home(SERIES)
        assert home.startswith("---\ndescription: ")
        assert HUB_DESCRIPTION in home
        assert "aged 12 and up" in home
        assert "## How to start" in home
        assert home.index("## How to start") < home.index("## Start here")


class TestRobots:
    """The hub's robots.txt lets every crawler in and names every sitemap."""

    def test_allows_everything_and_lists_every_sitemap(self) -> None:
        """One sitemap line for the hub, then one per project in series order."""
        lines = render_robots(SERIES).splitlines()
        assert lines[:2] == ["User-agent: *", "Allow: /"]
        sitemaps = [line.removeprefix("Sitemap: ") for line in lines if line.startswith("Sitemap:")]
        assert sitemaps == [
            "https://robcox2910.github.io/sitemap.xml",
            *(f"{p.site_url}sitemap.xml" for p in SERIES),
        ]

    def test_robots_is_a_hub_file(self) -> None:
        """``series hub`` writes it, so the hub's drift test covers it."""
        assert ROBOTS_TXT in HUB_FILES


class TestAbout:
    """``series about`` keeps every GitHub About box in step with series.yml."""

    def test_settings_cover_the_hub_and_every_project(self) -> None:
        """The hub comes first, then each project with its docs site as the website."""
        settings = about_settings(SERIES)
        assert settings[0] == About(
            HUB_REPO, HUB_DESCRIPTION, "https://robcox2910.github.io/", COMMON_TOPICS
        )
        assert [s.repo for s in settings[1:]] == [p.repo for p in SERIES]
        assert settings[1].homepage == SERIES[0].site_url

    def test_drift_names_each_differing_field(self) -> None:
        """Empty GitHub fields differ in all three; topic order does not matter."""
        want = About("r", "Pitch", "https://x/", ("b", "a"))
        empty: dict[str, object] = {"description": None, "homepage": None, "topics": []}
        assert about_drift(want, empty) == [
            "description",
            "homepage",
            "topics",
        ]
        same: dict[str, object] = {
            "description": "Pitch",
            "homepage": "https://x/",
            "topics": ["a", "b"],
        }
        assert about_drift(want, same) == []
