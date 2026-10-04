"""The team's Arabic competition package (`corpus/competition-ar/content.json`) as schema-v2 corpus documents.

    stories          one `story` document per scene: the scene, then its lesson ("الدرس: ...")
    adhkar, duas     one `dua` document per dhikr or supplication: the wording (with how many times it is
                     said), a Quranic supplication's ayat as the Quranpedia mushaf has them, then the child note
    prayer_learning  one `lesson` document per section (preparation, wudu, steps, counts), a unit per step

Ids are `comp-<item id>`; tier 2 (child content); draft review status. Every document cites the registry source
`competition-ar-content`, whose sha256 is content.json's: an edited package fails the build until the registry
records the reviewed file. A document quoting ayat also cites the mushaf's registry source, so it follows that
source's status (a candidate source keeps it out of every release).

References: `quran:S:A[-B]` as they are; `hadith:<numbering>:N` becomes `<numbering>:N` with `_` for `-`
(`muslim-abdulbaqi:591` -> `muslim_abdulbaqi:591`, kept apart from the canonical `muslim:` numbering); a
`fiqh:` reference becomes `dorar_fiqh:<page>`, the dorar.net/feqhia page of the item's evidence URL, else of the
section in `prayer_learning.evidence_urls`, else of `prayer_learning.fiqh_source`.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

from . import fetch, quranpedia
from .ingest import _document
from .registry import Registry

SOURCE_ID = "competition-ar-content"
QURAN_SOURCE_ID = quranpedia.MUSHAF_PRINT
WORK = "حزمة بدر العربية للمسابقة"
DRAFT = "مسودة حزمة المسابقة"
OCCASIONS_AR = {
    "morning": "أذكار الصباح", "evening": "أذكار المساء", "after_obligatory_prayer": "بعد الصلاة المفروضة",
    "for_parents": "للوالدين", "learning": "عند التعلم", "general": "دعاء عام", "after_mistake": "بعد الخطأ",
    "for_family": "للأسرة", "before_difficult_task": "قبل المهمة الصعبة", "gratitude": "عند الشكر",
    "before_sleep": "قبل النوم", "after_waking": "بعد الاستيقاظ", "before_eating": "قبل الطعام",
    "before_bathroom": "قبل دخول الحمام", "entering_mosque": "عند دخول المسجد",
    "leaving_mosque": "عند الخروج من المسجد", "after_sneezing": "بعد العطاس", "seeking_guidance": "طلب الهداية",
}
GROUPS_AR = {"adhkar": "أذكار", "daily_duas": "أدعية يومية"}
# (content key, id suffix, Arabic title)
PRAYER_SECTIONS = (("preparation", "preparation", "الاستعداد للصلاة"), ("wudu", "wudu", "الوضوء"),
                   ("prayer_steps", "steps", "خطوات الصلاة"),
                   ("prayer_counts", "counts", "عدد ركعات الصلوات المفروضة"))
RAKAH_AR = {2: "ركعتان", 3: "ثلاث ركعات", 4: "أربع ركعات"}
BOM = chr(0xFEFF)  # opens most ayat of the mushafs-1 dump; a file artefact, not part of the text
_QURAN = re.compile(r"quran:(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?")
_HADITH = re.compile(r"hadith:([a-z-]+):(\d+)")
_FIQH = re.compile(r"fiqh:([a-z-]+):([a-z-]+)")
_FEQHIA_PAGE = re.compile(r"^https://dorar\.net/feqhia/(\d+)/?$")


class CompetitionError(ValueError):
    pass


def load_content(path: Path, registry: Registry) -> tuple[dict, dict]:
    """(content, registry entry); refuses a content.json whose sha256 is not the one the registry records."""
    raw = Path(path).read_bytes()
    entry = registry.get(SOURCE_ID)
    actual = sha256(raw).hexdigest()
    if actual != entry["sha256"]:
        raise CompetitionError(f"{path}: sha256 {actual} is not the one {SOURCE_ID} records in the registry "
                               f"({entry['sha256']}); after review, record the new digest and retrieved_at there")
    return json.loads(raw.decode("utf-8")), entry


def quran_text(registry: Registry, raw_root: Path) -> dict[tuple[int, int], str]:
    """(surah, ayah) -> text of the registry-pinned Quranpedia mushaf, verified by its registry sha256."""
    entry = registry.get(QURAN_SOURCE_ID)
    path = fetch.raw_path(raw_root, entry)
    if not path.is_file():
        raise CompetitionError(f"{path} is missing; run scripts/fetch_sources.py")
    if fetch.digest(path) != entry["sha256"]:
        raise CompetitionError(f"{path} does not match the registry's sha256 for {QURAN_SOURCE_ID}")
    return quranpedia.parse_mushaf(path, quranpedia.MUSHAF_IDS[QURAN_SOURCE_ID]).texts


def _feqhia_page(url) -> str | None:
    match = _FEQHIA_PAGE.match(url or "")
    return match[1] if match else None


def source_refs(item: dict, prayer: dict | None = None) -> list[str]:
    """The item's `refs` as corpus source references (module docstring), in order, without repeats."""
    prayer = prayer or {}
    out = []
    for ref in item["refs"]:
        if _QURAN.fullmatch(ref):
            out.append(ref)
        elif match := _HADITH.fullmatch(ref):
            out.append(f"{match[1].replace('-', '_')}:{match[2]}")
        elif match := _FIQH.fullmatch(ref):
            page = (_feqhia_page(item.get("evidence_url"))
                    or _feqhia_page((prayer.get("evidence_urls") or {}).get(f"{match[1]}_{match[2]}"))
                    or _feqhia_page(prayer.get("fiqh_source")))
            if page is None:
                raise CompetitionError(f"{item['id']}: {ref} has no dorar.net/feqhia page")
            out.append(f"dorar_fiqh:{page}")
        else:
            raise CompetitionError(f"{item['id']}: unknown reference {ref}")
    return list(dict.fromkeys(out))


def occasion_label(item: dict) -> str:
    """The item's occasions in Arabic, joined with «، »."""
    occasions = item.get("occasions") or [item["occasion"]]
    return "، ".join(OCCASIONS_AR.get(occasion, occasion) for occasion in occasions)


def _times(count: int) -> str:
    return "مرتين" if count == 2 else f"{count} مرات" if 3 <= count <= 10 else f"{count} مرة"


def ayat(ref: str, quran: dict[tuple[int, int], str]) -> str:
    """The ayat of `quran:S:A[-B]`, each between ﴿ ﴾ (without the dump's byte-order mark) and its number."""
    match = _QURAN.fullmatch(ref)
    surah, first, last = int(match[1]), int(match[2]), int(match[3] or match[2])
    try:
        return " ".join(f"﴿{quran[(surah, number)].strip(BOM)}﴾ ({number})" for number in range(first, last + 1))
    except KeyError as error:
        raise CompetitionError(f"{ref}: ayah {error.args[0]} is not in the mushaf") from None


def _unit(unit_id: str, text: str, section: str, refs: list[str], keep: bool) -> dict:
    return {"id": unit_id, "text": text, "reference": refs[0] if refs else None, "section": section,
            "keepWithNext": keep, "sourceRefs": refs, "parts": []}


def _chain(units: list[dict]) -> list[dict]:
    """Keeps a document's units in one chunk: every unit but the last is kept with the next."""
    for position, unit in enumerate(units):
        unit["keepWithNext"] = position < len(units) - 1
    return units


def _short(text: str, limit: int = 70) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def documents(content: dict, entry: dict, quran: dict[tuple[int, int], str]) -> list[dict]:
    """Schema-v2 documents for the package `content` (registry `entry` of competition-ar-content)."""
    source = {"work": WORK, "edition": content["package_id"], "publisher": entry["publisher"][:200],
              "translator": None, "license": entry["license"], "checksum": entry["sha256"]}

    def document(doc_id, title, content_type, header, units, **v2):
        return _document(doc_id, title, content_type, source, _chain(units), tier=2, contextHeader=header,
                         sourceIds=v2.pop("sourceIds", [SOURCE_ID]), **v2)

    docs = []
    for story in content["stories"]:
        prophet = story["id"].removeprefix("story-")
        for number, scene in enumerate(story["scenes"], 1):
            refs, doc_id = source_refs(scene), "comp-" + scene["id"]
            docs.append(document(
                doc_id, f"{story['title']} — المشهد {number}", "story",
                f"قصة — {story['title']} — المشهد {number} ({DRAFT})",
                [_unit("scene", scene["text"], doc_id, refs, True),
                 _unit("lesson", "الدرس: " + scene["lesson"], doc_id, refs, False)],
                prophetId=prophet, grading=scene.get("grading")))
    for group, name in GROUPS_AR.items():
        for item in content[group]:
            refs, doc_id = source_refs(item), "comp-" + item["id"]
            text = item["display"]
            if (item.get("repeat") or 1) > 1:
                text += f" — يُقال {_times(item['repeat'])}"
            units = [_unit("display", text, doc_id, refs, True)]
            quran_refs = [ref for ref in refs if ref.startswith("quran:")] \
                if item.get("kind") == "quran_recitation" else []
            units += [_unit(f"q{number}", ayat(ref, quran), doc_id, [ref], True)
                      for number, ref in enumerate(quran_refs, 1)]
            units.append(_unit("note", item["child_note"], doc_id, refs, False))
            docs.append(document(
                doc_id, f"{name}: {_short(item['display'])}", "dua", f"{name} — {occasion_label(item)} ({DRAFT})",
                units, grading=item.get("grading"),
                sourceIds=[SOURCE_ID, QURAN_SOURCE_ID] if quran_refs else [SOURCE_ID]))
    prayer = content["prayer_learning"]
    common = "common" if prayer.get("madhhab_applicability") == "shared_basics_only" else None
    for key, suffix, title in PRAYER_SECTIONS:
        doc_id = f"comp-prayer-{suffix}"
        units = []
        for step in prayer[key]:
            text = step.get("text") or \
                f"صلاة {step['prayer']}: {RAKAH_AR.get(step['rakah'], str(step['rakah']) + ' ركعات')} ({step['context']})"
            units.append(_unit(step["id"], text, doc_id, source_refs(step, prayer), True))
        gradings = list(dict.fromkeys(step["grading"] for step in prayer[key] if step.get("grading")))
        docs.append(document(
            doc_id, f"تعليم الصلاة: {title}", "lesson",
            f"تعليم الصلاة — {title} ({DRAFT}؛ الأساسيات المشتركة فقط)", units,
            grading="؛ ".join(gradings) or None, madhhabScope=common))
    return docs


def build(content_path: Path, registry: Registry, raw_root: Path) -> list[dict]:
    """The package's documents, after checking content.json and the mushaf against the registry."""
    content, entry = load_content(content_path, registry)
    return documents(content, entry, quran_text(registry, raw_root))
