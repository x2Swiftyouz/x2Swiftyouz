import datetime as dt
import re
import xml.etree.ElementTree as ET

import pytest

import generate as gen


@pytest.fixture
def user():
    return gen.fetch_mock()


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    """Rendering writes cards/ and anime SVGs; keep that out of the repo."""
    monkeypatch.setattr(gen, "ROOT", tmp_path)


def at(monkeypatch, when):
    monkeypatch.setenv("PROFILE_NOW", when)


# ---------------------------------------------------------------- festivals
@pytest.mark.parametrize("when, emoji", [
    ("2026-04-14T09:00", "💦"),
    ("2026-12-31T09:00", "🎆"),
    ("2027-01-02T09:00", "🎆"),        # range wraps the new year
    ("2026-10-31T09:00", "🎃"),
    ("2026-10-06T09:00", None),
])
def test_festival(monkeypatch, user, when, emoji):
    at(monkeypatch, when)
    fest = gen.festival(user)
    assert (fest or {}).get("emoji") == emoji


def test_github_anniversary(monkeypatch, user):
    at(monkeypatch, "2026-08-14T09:00")          # mock account created 2025-08-14
    assert gen.festival(user)["emoji"] == "🎂"


@pytest.mark.parametrize("hour, word", [(8, "morning"), (14, "afternoon"), (19, "evening"), (23, "night")])
def test_greeting_follows_local_time(monkeypatch, hour, word):
    at(monkeypatch, f"2026-10-06T{hour:02d}:00")
    assert word in gen.greeting()


# ---------------------------------------------------------------- data shaping
def test_top_languages_sum_to_100_and_hide_tiny(user):
    langs = gen.top_languages(user)
    assert abs(sum(p for _, p, _ in langs) - 100) < 0.01
    assert all(p >= 1 for _, p, _ in langs)


def test_profile_repo_is_not_a_project(user):
    assert gen.CFG["username"] not in [r["name"] for r in gen.own_repos(user)]


def test_commits_skip_merges_and_escape_html(user):
    md = gen.commits_markdown(user)
    assert "Merge pull request" not in md
    assert "<streaming>" not in md and "&lt;streaming&gt;" in md


def test_activity_is_newest_first_and_skips_profile_repo(user):
    lines = gen.activity_markdown(user).splitlines()
    assert not any(f"{gen.CFG['username']}/{gen.CFG['username']}" in ln for ln in lines)
    ages = [re.search(r"<sub>(\d+)(\w+) ago</sub>", ln).groups() for ln in lines]
    unit = {"m": 1, "h": 60, "d": 1440, "mo": 43200, "y": 525600}
    minutes = [int(n) * unit[u] for n, u in ages]
    assert minutes == sorted(minutes)


def test_readable_lightens_dark_colours_only_on_dark_theme():
    assert gen.readable("#012456", "dark") != "#012456"
    assert gen.readable("#012456", "light") == "#012456"
    assert gen.readable("#3572A5", "dark") == "#3572A5"


def test_wrap_respects_width_and_lines():
    lines = gen.wrap("word " * 50, 20, 2)
    assert len(lines) == 2 and all(len(ln) <= 20 for ln in lines)
    assert lines[-1].endswith("…")


def test_fill_section_replaces_only_inside_markers():
    text = "a\n<!--START_SECTION:x-->\nold\n<!--END_SECTION:x-->\nb"
    assert gen.fill_section(text, "x", "new") == "a\n<!--START_SECTION:x-->\nnew\n<!--END_SECTION:x-->\nb"


# ---------------------------------------------------------------- rendering
@pytest.mark.parametrize("theme", list(gen.THEMES))
def test_card_is_valid_svg(monkeypatch, user, theme):
    at(monkeypatch, "2026-04-14T09:00")          # festival path included
    ET.fromstring(gen.render(user, theme))


@pytest.mark.parametrize("theme", list(gen.THEMES))
def test_project_and_anime_cards_are_valid_svg(user, theme):
    ET.fromstring(gen.render_project(gen.own_repos(user)[0], theme, 0))
    ET.fromstring(gen.render_anime(gen.mock_anime(), theme))


def test_optional_sections_hidden_until_configured(monkeypatch):
    monkeypatch.setitem(gen.CFG, "discord_id", "")
    monkeypatch.setitem(gen.CFG, "anilist_user", "")
    assert gen.discord_section() == ""
    assert gen.anime_section(mock=True) == ""


def test_rel_time():
    now = dt.datetime.now(dt.timezone.utc)
    assert gen.rel_time((now - dt.timedelta(hours=3)).isoformat()) == "3h ago"


# ---------------------------------------------------------------- dev log / codewars
def test_devlog_newest_first_ignores_template(tmp_path):
    d = tmp_path / "devlog"
    d.mkdir()
    (d / "_template.md").write_text("# Template\n", encoding="utf-8")
    (d / "notes.md").write_text("# Misnamed\n", encoding="utf-8")
    (d / "2026-10-01-first.md").write_text("# First post\n", encoding="utf-8")
    (d / "2026-10-05-second.md").write_text("intro\n# Second *post*\n", encoding="utf-8")
    assert [p["title"] for p in gen.devlog_posts()] == ["Second *post*", "First post"]
    section = gen.devlog_section()
    assert section.startswith("### ✍️ Dev log")
    assert r"Second \*post\*" in section


def test_devlog_hidden_when_empty():
    assert gen.devlog_section() == ""


@pytest.mark.parametrize("name, shown", [("", False), ("x2swift", True), ("bad name<script>", False)])
def test_codewars_section(monkeypatch, name, shown):
    monkeypatch.setitem(gen.CFG, "codewars_user", name)
    assert bool(gen.codewars_section()) is shown
