from html.parser import HTMLParser

import pytest

import build_site
import generate as gen


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(build_site, "OUT", tmp_path / "_site")
    (tmp_path / "devlog").mkdir()
    (tmp_path / "devlog" / "2026-10-06-hello.md").write_text(
        "# Hello <b>devlog</b>\n\nSome **bold** text.\n", encoding="utf-8")
    build_site.build(gen.fetch_mock())
    return tmp_path / "_site"


def test_builds_index_and_post_pages(site):
    assert (site / "index.html").exists()
    assert (site / "posts" / "2026-10-06-hello.html").exists()
    assert (site / ".nojekyll").exists()


def test_index_lists_projects_and_post(site):
    index = (site / "index.html").read_text(encoding="utf-8")
    for repo in gen.own_repos(gen.fetch_mock()):
        assert repo["name"] in index
    assert 'href="posts/2026-10-06-hello.html"' in index


def test_text_from_data_is_escaped(site):
    index = (site / "index.html").read_text(encoding="utf-8")
    assert "<streaming>" not in index            # from a mock commit message
    assert "<b>devlog</b>" not in index          # post title is plain text on the index


def test_post_body_is_rendered_markdown(site):
    post = (site / "posts" / "2026-10-06-hello.html").read_text(encoding="utf-8")
    assert "<strong>bold</strong>" in post      # posts are yours, so their HTML is kept


def test_html_is_well_formed(site):
    class Parser(HTMLParser):
        void = {"meta", "img", "br", "hr", "link", "input"}

        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            if tag not in self.void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack and self.stack.pop() == tag, f"unbalanced </{tag}>"

    for page in [site / "index.html", *(site / "posts").glob("*.html")]:
        p = Parser()
        p.feed(page.read_text(encoding="utf-8"))
        assert p.stack == [], f"unclosed tags in {page.name}: {p.stack}"
