"""The Jamharah dictionary crawl (reference package task): parsing, exact matching and the crawl's budget.

The HTML below is synthetic: it copies the site's markup shape (studied 2026-10-02), not its text.
"""
import importlib.util
from pathlib import Path
import sys

import pytest

from companion_api.corpusprep import jamharah

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str):
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))  # the scripts import their shared _common module
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hit(entry_id: int, title: str, categories: list[tuple[int, str]]) -> str:
    links = " ، ".join(f'<a href="https://islamic-content.com/dictionary/term/{n}">{name}</a>' for n, name in categories)
    return (f'<a href="https://islamic-content.com/dictionary/word/{entry_id}"><div class="mb-20">'
            f'<h4><a href="https://islamic-content.com/dictionary/word/{entry_id}">{title}</a></h4>'
            f'<p class="font-medium text-muted"></p><p class="font-x-small text-muted">{links}</p>'
            f'<h6>المصطلحات</h6></div></a>\n')


SEARCH = ("<main><h1>معجم المصطلحات</h1>" + _hit(10, "حمى الكلمة", [(5, "باب")])
          + _hit(12, "الكَلِمَة", []) + _hit(11, "الْكَلِمَـة", [(5, "باب"), (6, "باب آخر")])
          + _hit(13, "كلمة أخرى", [(5, "باب")]) + "</main><footer>"
          + '<a href="https://islamic-content.com/dictionary/term/99">ليس من النتائج</a></footer>')


def _entry(title: str, sections: str, translations: str = "", language: str = "ar") -> str:
    style = ' style="direction:ltr;text-align:left;"' if language != "ar" else ' style=""'
    return ('<div class="breadcrumbs"><ol><li><a href="/">home</a></li>'
            '<li><a href="https://islamic-content.com/dictionary/term/5">باب</a></li></ol></div>'
            f'<article class="entry-wraper"><h1{style}>{title}</h1>{sections}'
            f'<section id="related">{translations}</section></article>')


SECTION_AR = ('<div><h5 class="text-left">من معجم المصطلحات</h5><div><p><p>تعريف أول.</p><hr>'
              '<div class="footnotes">انظر: مرجع.</div></p></div></div>'
              '<div><h5 class="text-left">من موسوعة المصطلحات</h5><div><p><h2>التعريف</h2><p>تعريف ثان.</p></p>'
              '</div></div>')
SECTION_EN = ('<div><h5 class="text-left">من موسوعة المصطلحات</h5><div><p><h2>المعنى</h2><p>A word.</p>'
              '<h2>الشرح</h2><p>Longer &amp; kinder.</p></p></div></div>')
EN_LINK = '<li><a href="https://islamic-content.com/dictionary/word/11/en">English</a></li>'


def test_fold_ignores_diacritics_tatweel_hamza_and_the_article():
    assert jamharah.fold("الْكَلِمَـة") == jamharah.fold("كلمه") == jamharah.fold("الكلمة")
    assert jamharah.fold("أركان") == jamharah.fold("اركان")
    assert jamharah.fold("كلمة أخرى") != jamharah.fold("كلمة")


def test_search_results_and_their_categories():
    hits = jamharah.parse_search(SEARCH)
    assert [hit.entry_id for hit in hits] == [10, 12, 11, 13]
    assert hits[1].categories == () and hits[2].categories == ("باب", "باب آخر")
    assert "ليس من النتائج" not in hits[3].categories


def test_only_an_exact_title_matches_and_a_categorised_entry_wins():
    chosen, others = jamharah.choose("الكلمة", jamharah.parse_search(SEARCH))
    assert chosen.entry_id == 11 and [hit.entry_id for hit in others] == [12]
    assert jamharah.choose("حمى", jamharah.parse_search(SEARCH)) == (None, [])


def test_arabic_entry_sections_and_references():
    entry = jamharah.parse_entry(_entry("الْكَلِمَـة", SECTION_AR, EN_LINK), 11)
    assert entry.title_ar == "الْكَلِمَـة" and entry.categories == ["باب"] and entry.translations == ["en"]
    assert [(s["heading"], s["text"]) for s in entry.sections] == [(None, "تعريف أول."), ("التعريف", "تعريف ثان.")]
    assert entry.sections[0]["references"] == ["انظر: مرجع."]


def test_english_heading_is_the_equivalent_and_may_be_empty():
    entry = jamharah.parse_entry(_entry("Word<br /> (الْكَلِمَـة)", SECTION_EN, language="en"), 11, "en")
    assert entry.title == "Word" and entry.title_ar == "الْكَلِمَـة"
    assert [s["text"] for s in entry.sections] == ["A word.", "Longer & kinder."]
    empty = jamharah.parse_entry(_entry("<br /> (الكلمة)", "", language="en"), 12, "en")
    assert empty.title is None and empty.sections == []
    with pytest.raises(ValueError):
        jamharah.parse_entry("<html>not an entry</html>", 1)


def test_lookup_terms_use_the_query_when_given():
    glossary = {"terms": [{"ar": "تاب", "query": "التوبة", "latin": ["x"], "sensitive": True},
                          {"ar": "جبل", "latin": ["x"]},
                          {"ar": "التوحيد", "origin": "package_page_7", "latin": ["x"]}]}
    assert jamharah.lookup_terms(glossary) == [
        {"term": "تاب", "query": "التوبة", "origin": "glossary", "sensitive": True},
        {"term": "جبل", "query": "جبل", "origin": "glossary", "sensitive": False},
        {"term": "التوحيد", "query": "التوحيد", "origin": "package_page_7", "sensitive": True}]


CRAWLER = _script("crawl_jamharah")


class FakeClient:
    def __init__(self, pages: dict, budget: int, blocked: str | None = None):
        self.pages, self.budget, self.blocked, self.urls = pages, budget, blocked, []

    def get(self, url):
        crawler = CRAWLER
        if url == self.blocked:
            raise crawler.Stopped(f"HTTP 429 at {url}")
        if len(self.urls) >= self.budget:
            raise crawler.Budget("request budget reached")
        self.urls.append(url)
        return (200, self.pages[url], "2026-10-02T00:00:00+00:00") if url in self.pages else (404, "", "t")


def _pages():
    return {jamharah.search_url("الكلمة"): SEARCH, jamharah.search_url("غائب"): "<main></main>",
            jamharah.entry_url(11, "en"): _entry("Word<br /> (الْكَلِمَـة)", SECTION_EN, language="en"),
            jamharah.entry_url(11): _entry("الْكَلِمَـة", SECTION_AR, EN_LINK)}


def test_crawl_matches_reads_english_then_arabic_and_lists_unmatched():
    crawler = CRAWLER
    terms = [{"term": "غائب", "query": "غائب", "origin": "glossary"},
             {"term": "كلمة", "query": "الكلمة", "origin": "package_page_7"}]
    client = FakeClient(_pages(), budget=10)
    rows, stopped, blocked = crawler.crawl(terms, client)
    assert stopped is None and not blocked
    assert rows[0]["status"] == "unmatched" and rows[0]["reason"]
    assert rows[1]["status"] == "matched" and rows[1]["entry_id"] == 11 and rows[1]["alternatives"] == [12]
    assert rows[1]["english"] == "Word" and rows[1]["definition_ar"][0]["text"] == "تعريف أول."
    assert client.urls[-2:] == [jamharah.entry_url(11, "en"), jamharah.entry_url(11)]


def test_sensitive_terms_are_read_before_other_words():
    pages = _pages()
    pages[jamharah.search_url("كلمه")] = SEARCH
    terms = [{"term": "كلمه", "query": "كلمه", "origin": "glossary", "sensitive": False},
             {"term": "الكلمة", "query": "الكلمة", "origin": "glossary", "sensitive": True}]
    client = FakeClient(pages, budget=3)
    rows, stopped, _ = CRAWLER.crawl(terms, client)
    assert "budget" in stopped
    assert rows[1].get("english") == "Word" and "pages_read" not in rows[0]


def test_crawl_stops_at_the_budget_and_on_a_refusal():
    crawler = CRAWLER
    terms = [{"term": "كلمة", "query": "الكلمة", "origin": "glossary"}]
    rows, stopped, blocked = crawler.crawl(terms, FakeClient(_pages(), budget=1))
    assert "budget" in stopped and not blocked and rows[0]["status"] == "matched" and "pages_read" not in rows[0]
    rows, stopped, blocked = crawler.crawl(terms, FakeClient(_pages(), budget=9,
                                                             blocked=jamharah.search_url("الكلمة")))
    assert blocked and "429" in stopped and rows[0]["status"] == "not_searched"


def test_the_crawler_obeys_robots_and_never_uses_the_api():
    crawler = CRAWLER
    from urllib.robotparser import RobotFileParser
    robots = RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /api/", "Disallow: /legacy-dictionary/"])
    for url in (jamharah.search_url("التوحيد"), jamharah.entry_url(3529), jamharah.entry_url(3529, "en")):
        assert robots.can_fetch(crawler.USER_AGENT, url)
    assert not robots.can_fetch(crawler.USER_AGENT, "https://islamic-content.com/api/search_words?query=x")
    assert crawler.MIN_DELAY >= 5 and crawler.USER_AGENT.startswith("badr-corpus-fetch/1")
