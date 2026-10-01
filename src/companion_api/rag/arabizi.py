"""Arabizi: Arabic written in Latin letters ("shu talab allah mn el malaeke lama 5ala2 adam?").

A child who writes Arabizi speaks Arabic, so the service treats the question as
Arabic (doc/rag-system.md §6.6): its fixed replies are Arabic, and it is
answered from the Arabic corpus. The corpus cannot be searched with Latin
letters, so `expand` rewrites the question into Arabic search terms: the
prophets it names (from `corpus/aliases.yaml`) and the story and hadith words
of the reviewed glossary (`corpus/glossary_cross_lingual.yaml`), both exported
to `data/query_aliases.json`. The named prophets also narrow retrieval to their
passages. Only the search query changes; the model reads the child's own words.

Detection is a heuristic: a word that mixes letters with the digits Arabizi
uses for Arabic sounds (2 ء, 3 ع, 5 خ, 6 ط, 7 ح, 8 ق, 9 ص), or two or more
common Arabizi words. An English question has neither.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re

from . import normalize

ALIASES_FILE = Path(__file__).with_name("data") / "query_aliases.json"
_DIGIT_WORD = re.compile(r"^(?=.*[a-z])(?=.*[2356789])[a-z2356789]+$")
_COMMON = frozenset({
    "shu", "sho", "shou", "esh", "eish", "ana", "enta", "inta", "inte", "kif", "kaif", "keef", "leish", "lesh",
    "leh", "mesh", "mish", "msh", "wala", "walla", "ya3ni", "bidi", "badi", "bade", "3ayez", "mn", "min", "el",
    "lama", "lamma", "ba3d", "2abl", "mafi", "wein", "wen", "fein", "feen", "kam", "2adesh", "2addeish", "kteer",
    "ktir", "shi", "eza", "iza", "law", "lesa", "ba2a", "tab", "yalla", "hayda", "hada", "hadi", "elli", "illi",
    "3an", "3ala", "ma3", "la2", "aywa", "akid", "shoo", "wesh", "ish", "laish", "laysh", "la", "w", "b", "bel",
    "bil", "howe", "hiye", "heye", "meno", "menno", "3and", "zghir", "kbir", "kaman", "kamaan"})
_ARABIC_LETTER = re.compile("[\u0600-\u06ff]")


def is_arabizi(text: str) -> bool:
    if _ARABIC_LETTER.search(text):
        return False
    tokens = normalize.search_text(text).split()
    if any(_DIGIT_WORD.match(token) for token in tokens):
        return True
    return sum(token in _COMMON for token in tokens) >= 2


@dataclass(frozen=True)
class Expansion:
    query: str                       # Arabic search terms, empty when nothing was recognised
    prophet_ids: tuple[str, ...]     # prophets the question names, to narrow retrieval


@lru_cache(maxsize=1)
def _aliases() -> dict:
    if not ALIASES_FILE.is_file():
        return {"prophets": [], "terms": []}
    return json.loads(ALIASES_FILE.read_text(encoding="utf-8"))


def _found(spelling: str, tokens: list[str], joined: str) -> bool:
    return f" {spelling} " in joined if " " in spelling else spelling in tokens


def expand(text: str) -> Expansion:
    """Arabic search terms and prophet ids for a Latin-script question."""
    tokens = normalize.search_text(text).split()
    joined = f" {' '.join(tokens)} "
    data = _aliases()
    names, prophets, terms = [], [], []
    for prophet in data["prophets"]:
        if any(_found(spelling, tokens, joined) for spelling in prophet["latin"]):
            prophets.append(prophet["id"])
            names.append(prophet["ar"])
    for term in data["terms"]:
        if any(_found(spelling, tokens, joined) for spelling in term["latin"]):
            terms.append(term["ar"])
    return Expansion(" ".join(dict.fromkeys(names + terms)), tuple(prophets))
