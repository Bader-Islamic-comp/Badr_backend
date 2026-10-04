"""The Jamharah dictionary (islamic-content.com/dictionary, Osool Center): parse its pages and match terms.

The reference package (corpus/sources/reference_package.yaml, row «الترجمة والمصطلحات») prefers this
dictionary over machine translation for sensitive Islamic terms. `scripts/crawl_jamharah.py` looks up the
terms of `corpus/glossary_cross_lingual.yaml` through the site's own search page and reads the matched
entries; this module holds the parsing and matching, so they can be tested offline.

Matching is exact and never guessed: a term matches an entry only when the two titles are equal once
diacritics, tatweel, hamza forms on alef, alef maqsura, ta marbuta, punctuation and a leading article are
folded. Several equal titles are all reported; the one listed under a dictionary category wins, then the
lowest id. Anything else is `unmatched`.

Site facts (studied 2026-10-02): the dictionary's own search box calls /api/search_words, which robots.txt
disallows, so the crawler uses the site search page instead (`/search?query=<term>&type=word`, 15 results
a page). An entry is `/dictionary/word/<id>` (Arabic) and `/dictionary/word/<id>/<lang>` per translation;
the English page's heading is the English equivalent, empty when the entry has no English translation.
"""
from dataclasses import dataclass, field
import html as html_lib
import re
from urllib.parse import quote

BASE = "https://islamic-content.com"
PARSER_VERSION = "jamharah-parse-v1"


def search_url(query: str) -> str:
    return f"{BASE}/search?query={quote(query)}&type=word"


def entry_url(entry_id: int, language: str | None = None) -> str:
    return f"{BASE}/dictionary/word/{entry_id}" + (f"/{language}" if language else "")


# --- folding for exact matching ---------------------------------------------------------------------------

# Arabic diacritics (fathatan..sukun and the extended marks up to U+065F), superscript alef, tatweel.
_DROP = dict.fromkeys([*range(0x064B, 0x0660), 0x0670, 0x0640])
_LETTERS = {ord("أ"): "ا", ord("إ"): "ا", ord("آ"): "ا", ord("ٱ"): "ا", ord("ى"): "ي", ord("ة"): "ه"}
_NOT_WORD = re.compile(r"[^\w\s]")
_ARTICLE = "ال"


def fold(text: str) -> str:
    """The comparison form of a title: never stored or shown."""
    text = html_lib.unescape(text).translate(_DROP).translate(_LETTERS)
    words = _NOT_WORD.sub(" ", text).split()
    if words and words[0].startswith(_ARTICLE) and len(words[0]) > len(_ARTICLE) + 1:
        words[0] = words[0][len(_ARTICLE):]
    return " ".join(words).casefold()


# --- page parsing ------------------------------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def text_of(fragment: str) -> str:
    return _SPACE.sub(" ", html_lib.unescape(_TAG.sub(" ", fragment))).strip()


@dataclass(frozen=True)
class Hit:
    entry_id: int
    title: str
    categories: tuple[str, ...] = ()


_HIT = re.compile(r'<h4>\s*<a href="(?:https?://islamic-content\.com)?/dictionary/word/(\d+)"\s*>(.*?)</a>\s*</h4>',
                  re.S)
_CATEGORY = re.compile(r'<a href="(?:https?://islamic-content\.com)?/dictionary/term/(\d+)"\s*>(.*?)</a>', re.S)


def parse_search(page: str) -> list[Hit]:
    """Dictionary entries on one search results page, in page order."""
    matches = list(_HIT.finditer(page))
    hits = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(page)
        tail = page[match.end():end]
        stop = tail.find("<h6")  # each result card ends with its type label; its categories come before
        block = tail if stop < 0 else tail[:stop]
        categories = tuple(text_of(name) for _, name in _CATEGORY.findall(block))
        hits.append(Hit(int(match.group(1)), text_of(match.group(2)), categories))
    return hits


def choose(query: str, hits: list[Hit]) -> tuple[Hit | None, list[Hit]]:
    """The exact match for `query` and the other exact matches, or (None, [])."""
    wanted = fold(query)
    exact = [hit for hit in hits if fold(hit.title) == wanted]
    exact.sort(key=lambda hit: (not hit.categories, hit.entry_id))
    return (exact[0], exact[1:]) if exact else (None, [])


@dataclass
class Entry:
    entry_id: int
    language: str               # "ar" for the Arabic page, else the translation's code
    title_ar: str
    title: str | None           # the heading in `language`; None when the page has no text in it
    categories: list[str] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)   # {"source", "heading", "text", "references"}
    translations: list[str] = field(default_factory=list)


_ARTICLE_BLOCK = re.compile(r"<article\b.*?</article>", re.S)
_H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S)
_BREADCRUMBS = re.compile(r'<div class="breadcrumbs">.*?</ol>', re.S)
_SOURCE = re.compile(r"<h5\b[^>]*>(.*?)</h5>", re.S)
_H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.S)
_FOOTNOTES = re.compile(r'<div class="footnotes">(.*?)</div>', re.S)
_TRANSLATION = re.compile(r'/dictionary/word/\d+/([a-z]{2,3})"')


def _sections(body: str) -> list[dict]:
    related = body.find('<section id="related"')
    body = body if related < 0 else body[:related]
    starts = list(_SOURCE.finditer(body))
    sections = []
    for position, start in enumerate(starts):
        end = starts[position + 1].start() if position + 1 < len(starts) else len(body)
        chunk = body[start.end():end]
        references = [text_of(note) for note in _FOOTNOTES.findall(chunk)]
        chunk = _FOOTNOTES.sub(" ", chunk)
        parts = _H2.split(chunk)  # [before, heading, text, heading, text, ...]
        if text_of(parts[0]):
            sections.append({"source": text_of(start.group(1)), "heading": None, "text": text_of(parts[0]),
                             "references": references})
            references = []
        for index in range(1, len(parts) - 1, 2):
            text = text_of(parts[index + 1])
            if text:
                sections.append({"source": text_of(start.group(1)), "heading": text_of(parts[index]),
                                 "text": text, "references": references})
                references = []
    return sections


def parse_entry(page: str, entry_id: int, language: str = "ar") -> Entry:
    """One dictionary entry page. Raises ValueError when the page is not an entry."""
    article = _ARTICLE_BLOCK.search(page)
    heading = _H1.search(article.group(0)) if article else None
    if heading is None:
        raise ValueError(f"dictionary/word/{entry_id}: no entry heading on the page")
    raw = heading.group(1)
    if language == "ar":
        title_ar, title = text_of(raw), text_of(raw)
    else:
        before, _, after = re.split(r"(<br\s*/?>)", raw, maxsplit=1) if re.search(r"<br\s*/?>", raw) else (raw, "", "")
        title = text_of(before) or None
        title_ar = text_of(after).strip("()[] ") if after else ""
    crumbs = _BREADCRUMBS.search(page)
    categories = [text_of(name) for _, name in _CATEGORY.findall(crumbs.group(0))] if crumbs else []
    related = page.find('<section id="related"')
    translations = sorted(set(_TRANSLATION.findall(page[related:]))) if related >= 0 else []
    return Entry(entry_id, language, title_ar, title, categories, _sections(article.group(0)), translations)


# --- the terms to look up ----------------------------------------------------------------------------------

def lookup_terms(glossary: dict) -> list[dict]:
    """Every glossary term to look up, in file order: the term, its query (the term unless the glossary gives a
    lookup form), its origin, and whether it is a sensitive Islamic term (read first; page-7 terms always are)."""
    terms = []
    for term in glossary["terms"]:
        origin = term.get("origin", "glossary")
        terms.append({"term": term["ar"], "query": term.get("query") or term["ar"], "origin": origin,
                      "sensitive": bool(term.get("sensitive")) or origin == "package_page_7"})
    return terms
