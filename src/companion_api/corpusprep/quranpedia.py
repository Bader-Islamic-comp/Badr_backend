"""Quranpedia dumps (test/corpus-tasks): the reference package's mushafs, English translations and tafsir books.

The files are the registered downloads in `corpus/raw/quranpedia-*/` (json or json.gz, sha256-pinned in the
registry). Every source is `candidate`: what is built from them stays out of every release.

    mushaf      {license, schema, data: {id, name, surahs: [{id, ayahs: [{surah, number, text, page_number..}]}]}}
                mushafs-1 "مصحف حفص" (the King Fahd Complex print, pages as printed; its `text` is in standard
                spelling), mushafs-2 "مصحف حفص نسخة نصية" (the Complex's Uthmani Hafs text, UthmanicHafs font)
    translation {id, name, language, ayahs: [{surah_number, ayah_number, page_number, translated_text}]}
    tafsir      {license, book: {id, name, author..}, ayahs: [{surah, ayah, content: [{text, part, page, ayahs}]}]}
                `content[].ayahs` lists the ayat a passage explains, as global ayah numbers (1-6236) in most
                books and as numbers within the surah in a few (Yahya ibn Sallam, Malik, al-Shafi'i)
    books index {license, data: [{id, name, author, edition, nasher, mohaqeq, translator..}]}

What the parsers change, and nothing else (mushaf text is returned exactly as in the file):

* `html_text` turns HTML markup into text. Tags are removed and the text inside them is kept: the Quran
  quotations `<span class="book-ayah">﴿…﴾</span>` (the brackets are part of the text), surah references,
  numbering, `<strong>`, and footnote markers `<a class="foot-note">(١)</a>`. A line ends at `<br>` and at the
  start and end of p, div, h1-h6, hr, table, tr, li, ul, ol and blockquote; table cells in one row are
  separated by a space. `<div class="foot-notes">` (the editor's footnotes) is moved out of the text into
  `footnotes`. Character references (`&amp;`, `&nbsp;`) are decoded. Carriage returns end a line; within a
  line every run of whitespace (including the no-break space U+00A0) becomes one space; lines are trimmed
  and empty lines dropped. So the only characters added are spaces and line breaks: letters, diacritics and
  punctuation are those of the file, in its order.
* Translations: the translator's footnotes after the "______" rule go to `footnotes`, and the ayah-number
  label at the start of the text ("(30) ", "30. ", "12-13. ") is removed when it names the record's ayah
  (kept in `number_label`). A label naming another ayah is kept in the text and flagged: the record then
  holds another ayah's text (al-Mukhtasar's English has such misplacements).
* Tafsir: one record per passage. A passage listed under several ayat (one explanation for a range) is
  kept once, with its range. Passages printed before the passage on the book's first ayah but filed under
  a later ayah are flagged `out_of_place`, not dropped: several books file their introductions under the
  last ayat of the Quran (al-Tabari, al-Sahih al-Masbur), and Tafsir Mujahid files its al-Fatiha under 12:51.
"""
from dataclasses import dataclass
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import re

DATASET = "quranpedia-dumps"
MUSHAF_PRINT = "quranpedia-mushaf-hafs"          # mushafs-1, the King Fahd Complex print (standard spelling text)
MUSHAF_UTHMANI = "quranpedia-mushaf-hafs-text"   # mushafs-2, the Complex's Uthmani Hafs text
MUSHAF_IDS = {MUSHAF_PRINT: 1, MUSHAF_UTHMANI: 2}
BOOKS_INDEX = "quranpedia-books-index"


@dataclass(frozen=True)
class Translation:
    source_id: str
    slug: str
    book_id: int
    name: str           # as the document titles say it
    translator: str
    content_type: str   # quran_translation, or tafsir_translation for a translated tafsir


TRANSLATIONS = (
    Translation("quranpedia-en-hilali-khan", "hilali-khan", 1948, "Hilali and Khan",
                "Muhammad Taqi-ud-Din al-Hilali and Muhammad Muhsin Khan", "quran_translation"),
    Translation("quranpedia-en-sahih-international", "sahih-international", 1947, "Saheeh International",
                "Saheeh International", "quran_translation"),
    Translation("quranpedia-en-ruwwad", "ruwwad", 27811, "Ruwwad Translation Center",
                "Ruwwad Translation Center (IslamHouse.com)", "quran_translation"),
    Translation("quranpedia-en-mukhtasar", "mukhtasar", 27824, "Tafsir Center for Quranic Studies",
                "Tafsir Center for Quranic Studies", "tafsir_translation"),
)


@dataclass(frozen=True)
class TafsirBook:
    source_id: str
    slug: str
    book_id: int
    title_ar: str   # the name readers know, for titles and headers
    author_ar: str
    era_ar: str     # when the author died (or the compilation date)

    @property
    def canonical_name(self) -> str:
        return f"tafsir/quranpedia-{self.slug}.jsonl"


TAFSIR_BOOKS = (
    TafsirBook("quranpedia-tafsir-mujahid", "mujahid", 269, "تفسير مجاهد", "مجاهد بن جبر", "ت 104 هـ"),
    TafsirBook("quranpedia-tafsir-sufyan-thawri", "sufyan-thawri", 27758, "تفسير سفيان الثوري", "سفيان الثوري",
               "ت 161 هـ"),
    TafsirBook("quranpedia-tafsir-yahya-ibn-sallam", "yahya-ibn-sallam", 27766, "تفسير يحيى بن سلام",
               "يحيى بن سلام", "ت 200 هـ"),
    TafsirBook("quranpedia-tafsir-malik", "malik", 27765, "تفسير الإمام مالك", "مالك بن أنس", "ت 179 هـ"),
    TafsirBook("quranpedia-tafsir-shafii", "shafii", 27767, "تفسير الشافعي", "محمد بن إدريس الشافعي", "ت 204 هـ"),
    TafsirBook("quranpedia-tafsir-farra-maani", "farra-maani", 351, "معاني القرآن للفراء", "يحيى بن زياد الفراء",
               "ت 207 هـ"),
    TafsirBook("quranpedia-tafsir-abu-ubayda-majaz", "abu-ubayda-majaz", 348, "مجاز القرآن",
               "أبو عبيدة معمر بن المثنى", "ت 209 هـ"),
    TafsirBook("quranpedia-tafsir-ibn-qutayba-gharib", "ibn-qutayba-gharib", 341, "غريب القرآن لابن قتيبة",
               "ابن قتيبة الدينوري", "ت 276 هـ"),
    TafsirBook("quranpedia-tafsir-tabari", "tabari", 4, "جامع البيان (تفسير الطبري)", "محمد بن جرير الطبري",
               "ت 310 هـ"),
    TafsirBook("quranpedia-tafsir-nasai", "nasai", 27759, "تفسير النسائي", "أحمد بن شعيب النسائي", "ت 303 هـ"),
    TafsirBook("quranpedia-tafsir-sahih-masbur", "sahih-masbur", 305, "الصحيح المسبور من التفسير بالمأثور",
               "حكمت بشير ياسين", "جمعه سنة 1420 هـ"),
    TafsirBook("quranpedia-tafsir-mukhtasar", "mukhtasar", 2003, "المختصر في تفسير القرآن الكريم",
               "مركز تفسير للدراسات القرآنية", "معاصر"),
    TafsirBook("quranpedia-tafsir-saadi", "saadi", 3, "تفسير السعدي (تيسير الكريم الرحمن)",
               "عبد الرحمن بن ناصر السعدي", "ت 1376 هـ"),
)
# Which package rules put a book into layer 0 (in_rule, borderline); outside_rule books stay canonical only.
LAYER0_RULES = ("in_rule", "borderline")


class QuranpediaError(ValueError):
    pass


def load(path: Path):
    """The JSON in `path`, gunzipped first when the file is gzip (by its magic bytes, not its name)."""
    data = Path(path).read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QuranpediaError(f"{path}: not UTF-8 JSON ({error})") from None


def available(registry, source_ids) -> bool:
    ids = {source["source_id"] for source in registry.sources}
    return all(source_id in ids for source_id in source_ids)


def ayah_numbers(per_surah: dict[int, int]) -> tuple[dict[tuple[int, int], int], dict[int, tuple[int, int]]]:
    """(surah, ayah) -> global ayah number (1-6236 in the Kufan count), and back."""
    to_global, from_global, number = {}, {}, 0
    for surah in sorted(per_surah):
        for ayah in range(1, per_surah[surah] + 1):
            number += 1
            to_global[(surah, ayah)] = number
            from_global[number] = (surah, ayah)
    return to_global, from_global


def span_id(surah: int, first: int, last: int) -> str:
    return f"{surah}:{first}" + (f"-{last}" if last != first else "")


# HTML -> text ------------------------------------------------------------------------------------------------

_BLOCK = frozenset({"br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "table", "tr", "li", "ul", "ol",
                    "blockquote"})
_CELLS = frozenset({"td", "th"})
_RULE = re.compile(r"^_{5,}$")


@dataclass(frozen=True)
class HtmlText:
    text: str
    footnotes: str
    quran_quotes: int  # <span class="book-ayah">: the book's own marking of a Quran quotation


class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.main: list[str] = []
        self.notes: list[str] = []
        self.note_depth = 0   # open divs inside <div class="foot-notes">
        self.cells = 0        # cells already opened in the current table row
        self.quotes = 0

    def _out(self) -> list[str]:
        return self.notes if self.note_depth else self.main

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div":
            if self.note_depth:
                self.note_depth += 1
            elif "foot-notes" in classes:
                self.note_depth = 1
                self.main.append("\n")
                return
        if tag == "span" and "book-ayah" in classes and not self.note_depth:
            self.quotes += 1
        if tag in _CELLS:
            if self.cells:
                self._out().append(" ")
            self.cells += 1
        elif tag == "tr":
            self.cells = 0
        if tag in _BLOCK:
            self._out().append("\n")

    def handle_startendtag(self, tag, attrs):  # <br />, <hr/>: a start tag only
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "div" and self.note_depth:
            self.note_depth -= 1
            (self.notes if self.note_depth else self.main).append("\n")
            return
        if tag == "tr":
            self.cells = 0
        if tag in _BLOCK:
            self._out().append("\n")

    def handle_data(self, data):
        self._out().append(data)


def _lines(parts: list[str]) -> str:
    text = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line for line in (" ".join(raw.split()) for raw in text.split("\n")) if line)


def html_text(html: str) -> HtmlText:
    """The text of a Quranpedia HTML fragment, its editor's footnotes apart (see the module docstring)."""
    parser = _Html()
    parser.feed(html or "")
    parser.close()
    return HtmlText(_lines(parser.main), _lines(parser.notes), parser.quotes)


# Mushafs -----------------------------------------------------------------------------------------------------

@dataclass
class Mushaf:
    id: int
    name: str
    description: str
    version: str | None
    texts: dict[tuple[int, int], str]
    pages: dict[tuple[int, int], int]

    @property
    def per_surah(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for surah, _ in self.texts:
            counts[surah] = counts.get(surah, 0) + 1
        return counts


def parse_mushaf(path: Path, mushaf_id: int) -> Mushaf:
    """One mushaf dump: (surah, ayah) -> text exactly as in the file; refuses a repeated or misfiled ayah."""
    raw = load(path)
    try:
        data = raw["data"]
        surahs = data["surahs"]
    except (KeyError, TypeError):
        raise QuranpediaError(f"{path}: expected {{data: {{surahs: [...]}}}}") from None
    if data.get("id") != mushaf_id:
        raise QuranpediaError(f"{path}: holds mushaf {data.get('id')}, expected {mushaf_id}")
    texts, pages = {}, {}
    for surah in surahs:
        for row in surah.get("ayahs") or []:
            try:
                key = (int(row["surah"]), int(row["number"]))
                text = row["text"]
            except (KeyError, TypeError, ValueError):
                raise QuranpediaError(f"{path}: an ayah lacks surah, number or text") from None
            if key[0] != int(surah["id"]):
                raise QuranpediaError(f"{path}: ayah {key[0]}:{key[1]} is filed under surah {surah['id']}")
            if key in texts:
                raise QuranpediaError(f"{path}: ayah {key[0]}:{key[1]} appears twice")
            if not isinstance(text, str) or not text.strip():
                raise QuranpediaError(f"{path}: ayah {key[0]}:{key[1]} has no text")
            if row.get("number_in_hafs") not in (None, [key[1]]):
                raise QuranpediaError(f"{path}: ayah {key[0]}:{key[1]} is numbered {row['number_in_hafs']} in Hafs")
            texts[key] = text
            pages[key] = row.get("page_number")
    return Mushaf(mushaf_id, data.get("name") or "", data.get("description") or "",
                  (raw.get("license") or {}).get("version"), texts, pages)


# Translations ------------------------------------------------------------------------------------------------

_LABEL = re.compile(r"^(?:\((\d{1,3})\)|(\d{1,3})(?:\s*-\s*(\d{1,3}))?\.+)\s*")


def split_translation(html: str, ayah: int) -> dict:
    """{text, footnotes, number_label, label_mismatch} for one translated ayah (see the module docstring)."""
    parsed = html_text(html)
    lines = parsed.text.split("\n") if parsed.text else []
    rule = next((index for index, line in enumerate(lines) if _RULE.match(line)), None)
    body = lines if rule is None else lines[:rule]
    notes = ([] if rule is None else lines[rule + 1:]) + ([parsed.footnotes] if parsed.footnotes else [])
    text = "\n".join(body)
    label, mismatch = None, False
    match = _LABEL.match(text)
    if match:
        first = int(match.group(1) or match.group(2))
        last = int(match.group(3) or first)
        if first <= ayah <= last:
            label, text = match.group(0).strip(), text[match.end():]
        else:
            mismatch = True
    return {"text": text, "footnotes": "\n".join(notes), "number_label": label, "label_mismatch": mismatch}


def parse_translation(path: Path, translation: Translation) -> tuple[dict, dict[tuple[int, int], dict]]:
    """(book metadata, (surah, ayah) -> split_translation fields)."""
    raw = load(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("ayahs"), list):
        raise QuranpediaError(f"{path}: expected a translation book with an `ayahs` list")
    if raw.get("id") != translation.book_id:
        raise QuranpediaError(f"{path}: holds translation book {raw.get('id')}, expected {translation.book_id}")
    out = {}
    for row in raw["ayahs"]:
        try:
            key = (int(row["surah_number"]), int(row["ayah_number"]))
            html = row["translated_text"]
        except (KeyError, TypeError, ValueError):
            raise QuranpediaError(f"{path}: a record lacks surah_number, ayah_number or translated_text") from None
        if key in out:
            raise QuranpediaError(f"{path}: ayah {key[0]}:{key[1]} appears twice")
        out[key] = split_translation(html if isinstance(html, str) else "", key[1])
    meta = {key: raw.get(key) for key in ("id", "name", "short_name", "description", "language", "locale_code")}
    return meta, out


def translation_records(entries: dict[tuple[int, int], dict], quran_keys, translation: Translation,
                        package_rule: str | None) -> tuple[list[dict], dict]:
    """Canonical records, one per ayah, and the coverage summary. Refuses ayat that do not exist."""
    quran_keys = set(quran_keys)
    extra = sorted(set(entries) - quran_keys)
    if extra:
        raise QuranpediaError(f"{translation.source_id} has ayat that do not exist, e.g. {extra[:3]}")
    records = []
    for surah, ayah in sorted(entries):
        entry = entries[(surah, ayah)]
        if not entry["text"].strip():
            continue
        records.append({"surah": surah, "ayah": ayah, "quran_ref": f"quran:{surah}:{ayah}", "text": entry["text"],
                        "footnotes": entry["footnotes"], "number_label": entry["number_label"],
                        "label_mismatch": entry["label_mismatch"], "source_id": translation.source_id,
                        "package_rule": package_rule, "content_type": translation.content_type,
                        "book_id": translation.book_id, "words": len(entry["text"].split())})
    summary = {"ayat": len(records), "missing_ayat": len(quran_keys - {(r["surah"], r["ayah"]) for r in records}),
               "words": sum(record["words"] for record in records),
               "with_footnotes": sum(1 for record in records if record["footnotes"]),
               "labels_removed": sum(1 for record in records if record["number_label"]),
               "label_mismatch": [record["quran_ref"] for record in records if record["label_mismatch"]]}
    return records, summary


# Tafsir books ------------------------------------------------------------------------------------------------

def _page(item: dict) -> tuple[int, int] | None:
    """(part, page) as printed; a part that is not a number ("المقدمة") comes before part 1."""
    part = str(item.get("part") or "").strip()
    try:
        return (int(part) if part.isdigit() else 0), int(item["page"])
    except (KeyError, TypeError, ValueError):
        return None


def parse_tafsir(path: Path, book: TafsirBook, per_surah: dict[int, int]) -> tuple[dict, list[dict]]:
    """(book metadata, passages in Quran order). A passage: surah, first, last, text, footnotes, quran_quotes,
    part, page, numbering (global / in_surah / record), flags. Repeats under several ayat are kept once."""
    raw = load(path)
    try:
        meta, rows = raw["book"], raw["ayahs"]
    except (KeyError, TypeError):
        raise QuranpediaError(f"{path}: expected {{book: {{...}}, ayahs: [...]}}") from None
    if meta.get("id") != book.book_id:
        raise QuranpediaError(f"{path}: holds book {meta.get('id')}, expected {book.book_id} ({book.slug})")
    to_global, from_global = ayah_numbers(per_surah)
    passages: dict[tuple, dict] = {}
    seen_keys = set()
    for row in rows:
        try:
            key = (int(row["surah"]), int(row["ayah"]))
            contents = row["content"]
        except (KeyError, TypeError, ValueError):
            raise QuranpediaError(f"{path}: a record lacks surah, ayah or content") from None
        if key not in to_global:
            raise QuranpediaError(f"{path}: a record for ayah {key[0]}:{key[1]}, which does not exist")
        if key in seen_keys:
            raise QuranpediaError(f"{path}: ayah {key[0]}:{key[1]} appears twice")
        seen_keys.add(key)
        for content in contents or []:
            numbers = [int(part) for part in str(content.get("ayahs") or "").split(",") if part.strip().isdigit()]
            if to_global[key] in numbers:
                numbering, keys = "global", [from_global.get(number) for number in numbers]
            elif key[1] in numbers:
                numbering, keys = "in_surah", [(key[0], number) for number in numbers]
            else:
                numbering, keys = "record", [key]
            if None in keys or any(other not in to_global for other in keys):
                raise QuranpediaError(f"{path}: a passage under {key[0]}:{key[1]} names ayat that do not exist")
            if {surah for surah, _ in keys} != {key[0]}:
                raise QuranpediaError(f"{path}: a passage under {key[0]}:{key[1]} spans two surahs")
            ayat = sorted({ayah for _, ayah in keys})
            text = content.get("text") if isinstance(content.get("text"), str) else ""
            identity = (text, key[0], ayat[0], ayat[-1])
            if identity in passages:
                continue
            parsed = html_text(text)
            passages[identity] = {
                "surah": key[0], "first": ayat[0], "last": ayat[-1], "text": parsed.text,
                "footnotes": parsed.footnotes, "quran_quotes": parsed.quran_quotes, "part": content.get("part"),
                "page": content.get("page"), "numbering": numbering, "order": len(passages),
                "flags": [] if ayat == list(range(ayat[0], ayat[-1] + 1)) else ["range_not_contiguous"]}
    ordered = sorted(passages.values(), key=lambda item: (item["surah"], item["first"], item["order"]))
    # A passage printed before the passage on the book's first ayah, but filed under a later ayah, is out of
    # place: introductions filed under the last ayat (al-Tabari, al-Sahih al-Masbur...) or a misfiled passage.
    start = _page(ordered[0]) if ordered else None
    for item in ordered:
        page = _page(item)
        if start and page and page < start and (item["surah"], item["first"]) != (ordered[0]["surah"],
                                                                                   ordered[0]["first"]):
            item["flags"].append("out_of_place")
        if not item["text"]:
            item["flags"].append("empty")
    info = {key: meta.get(key) for key in ("id", "name", "short_name", "edition", "nasher", "mohaqeq")}
    info["author"] = (meta.get("author") or {}).get("ar_name")
    info["version"] = (raw.get("license") or {}).get("version")
    return info, ordered


def tafsir_records(passages: list[dict], book: TafsirBook, package_rule: str | None) -> tuple[list[dict], dict]:
    """Canonical records (one per passage, numbered within its range) and the book's coverage summary."""
    records, ordinal = [], {}
    for item in passages:
        section = f"{book.slug}:{span_id(item['surah'], item['first'], item['last'])}"
        ordinal[section] = ordinal.get(section, 0) + 1
        records.append({
            "record_id": f"{section}/{ordinal[section]}", "section_id": section, "source_id": book.source_id,
            "package_rule": package_rule, "book_id": book.book_id, "surah": item["surah"],
            "from_ayah": item["first"], "to_ayah": item["last"],
            "quran_refs": [f"quran:{item['surah']}:{ayah}" for ayah in range(item["first"], item["last"] + 1)],
            "text": item["text"], "footnotes": item["footnotes"], "quran_quotes": item["quran_quotes"],
            "part": item["part"], "page": item["page"], "numbering": item["numbering"], "flags": item["flags"],
            "words": len(item["text"].split())})
    usable = [record for record in records if usable_record(record)]
    covered = {ref for record in usable for ref in record["quran_refs"]}
    summary = {"records": len(records), "usable_records": len(usable),
               "sections": len({record["section_id"] for record in usable}), "ayat_covered": len(covered),
               "surahs_covered": len({record["surah"] for record in usable}),
               "words": sum(record["words"] for record in usable),
               "multi_ayah_records": sum(1 for record in usable if record["to_ayah"] > record["from_ayah"]),
               "with_footnotes": sum(1 for record in usable if record["footnotes"]),
               "quran_quotes_marked": sum(record["quran_quotes"] for record in usable),
               "numbering_in_surah": sum(1 for record in records if record["numbering"] == "in_surah"),
               "numbering_from_record": sum(1 for record in records if record["numbering"] == "record"),
               "flags": _count_flags(records)}
    return records, summary


def usable_record(record: dict) -> bool:
    """A record that documents and the graph may use: it has text and is not stored out of place."""
    return bool(record["text"]) and not ({"empty", "out_of_place"} & set(record["flags"]))


def _count_flags(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for flag in record["flags"]:
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items()))


# Books index -------------------------------------------------------------------------------------------------

def parse_books_index(path: Path) -> dict[int, dict]:
    """book id -> {name, short_name, type, language, category, author, author_full, mohaqeq, translator,
    edition, publisher, publish_year, parts}; text fields as in the file (the HTML `about` is not kept)."""
    raw = load(path)
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise QuranpediaError(f"{path}: expected {{data: [...]}}")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            raise QuranpediaError(f"{path}: a book entry has no numeric id")
        if row["id"] in out:
            raise QuranpediaError(f"{path}: book {row['id']} appears twice")
        author = row.get("author") or {}
        out[row["id"]] = {"name": row.get("name"), "short_name": row.get("short_name"), "type": row.get("type"),
                          "language": (row.get("language") or {}).get("code"),
                          "category": (row.get("category") or {}).get("name"), "author": author.get("ar_name"),
                          "author_full": author.get("full_name"), "mohaqeq": row.get("mohaqeq"),
                          "translator": row.get("translator"), "edition": row.get("edition"),
                          "publisher": row.get("nasher"), "publish_year": row.get("publish_year"),
                          "parts": row.get("parts")}
    return out
