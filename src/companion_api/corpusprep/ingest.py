"""Structure-aware ingestion: canonical files -> schema v2 corpus documents for the existing pipeline.

The output is an ordinary `corpus/<id>/` folder (corpus.json + documents/*.json)
that `companion_api.rag.pipeline` validates, chunks (chunk-v2) and releases,
so there is one pipeline, not two. Text is copied from corpus/canonical as it
is; ids, headers and references are generated from metadata.

    Quran    one document per segment (1-8 ayat, from Tanzil rukus); units are ayat;
             chunk-v2 adds a child chunk per ayah (`children: units`)
    Tafsir   one document per segment, units are the tafsir of each ayah, `parentChunk`
             is the segment's chunk; the source is `candidate`, so it is development-only
    Hadith   one document per cluster primary (Bukhari/Muslim); a narration is one unit,
             never split; one over 80 words also gets verbatim `parts` (child chunks)
"""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import shutil

from .registry import Registry
from .segments import Segment

LONG_HADITH_WORDS = 80
PART_TARGET_WORDS = 45
AGE_BANDS = ["7-9", "10-11"]
CURRICULUM = "pending-architecture-18"  # the curriculum framework is an open decision (architecture §18)
COLLECTION_AR = {"bukhari": "صحيح البخاري", "muslim": "صحيح مسلم", "nawawi40": "الأربعون النووية"}
COLLECTION_WORK = {"bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim"}
_BOUNDARY = re.compile(r"[.؟!:]\s+|[،,]\s+")
_SENTENCE = re.compile(r"[.؟!:]\s+")


@dataclass
class Built:
    documents: list[dict] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _source(registry: Registry, source_id: str, work: str) -> dict:
    entry = registry.get(source_id)
    return {"work": work, "edition": entry["edition"][:200], "publisher": entry["publisher"][:200],
            "translator": None, "license": entry["license"], "checksum": entry["sha256"]}


def _document(doc_id: str, title: str, content_type: str, source: dict, units: list[dict], **v2) -> dict:
    data = {"schemaVersion": 2, "id": doc_id, "kind": "passage", "title": title, "language": "ar",
            "ageBands": AGE_BANDS, "contentType": content_type, "madhhab": [], "curriculumPolicy": CURRICULUM,
            "synthetic": False, "source": source, "grading": v2.pop("grading", None),
            "review": {"status": "draft", "reviewer": None, "approvedOn": None, "supersedes": None}}
    data.update({"tier": None, "contextHeader": None, "prophetId": None, "topics": [], "madhhabScope": None,
                 "clusterId": None, "clusterRefs": [], "sourceIds": [], "parentChunk": None, "children": None,
                 "generatedQuestions": []})
    data.update(v2)
    data["units"] = units
    return data


def _span(first: int, last: int) -> str:
    return f"{first}" if first == last else f"{first}–{last}"


def quran_documents(segments: list[Segment], ayat: dict, tafsir: dict, names: dict[int, str],
                    registry: Registry, prophets: dict[tuple[int, int], str]) -> Built:
    built = Built()
    quran_source = _source(registry, "tanzil-quran-uthmani", "Tanzil Quran Text (Uthmani)")
    tafsir_source = _source(registry, "alquran-cloud-muyassar", "Al-Tafsir al-Muyassar")
    for item in segments:
        keys = [(item.surah, ayah) for ayah in range(item.first, item.last + 1)]
        prophet = next((prophets[key] for key in keys if key in prophets), None)
        span = _span(item.first, item.last)
        header = f"القرآن الكريم — سورة {names[item.surah]} — الآيات {span}"
        if prophet:
            header = f"قصة {prophet['name']} عليه السلام — " + header
        units = [{"id": f"a{ayah}", "text": ayat[(s, ayah)]["text_uthmani"], "reference": f"quran:{s}:{ayah}",
                  "section": item.id, "keepWithNext": False, "sourceRefs": [f"quran:{s}:{ayah}"], "parts": []}
                 for s, ayah in keys]
        built.documents.append(_document(
            item.id, f"سورة {names[item.surah]} {item.surah}:{span}", "quran", quran_source, units, tier=0,
            contextHeader=header, prophetId=prophet["id"] if prophet else None,
            sourceIds=["tanzil-quran-uthmani"], children="units"))
        tafsir_units = []
        seen: dict[str, dict] = {}
        for s, ayah in keys:
            text = tafsir.get((s, ayah))
            if not text:
                built.skip("tafsir_missing_for_ayah")
                continue
            if text in seen:  # one explanation covering several ayat: keep it once, cite every ayah
                seen[text]["sourceRefs"].append(f"quran:{s}:{ayah}")
                continue
            unit = {"id": f"t{ayah}", "text": text, "reference": f"quran:{s}:{ayah}", "section": item.id,
                    "keepWithNext": False, "sourceRefs": [f"quran:{s}:{ayah}"], "parts": []}
            seen[text] = unit
            tafsir_units.append(unit)
        if tafsir_units:
            built.documents.append(_document(
                "tafsir-muyassar-" + item.id.removeprefix("quran-"), f"التفسير الميسر {item.surah}:{span}",
                "tafsir", tafsir_source, tafsir_units, tier=1,
                contextHeader=f"التفسير الميسر — سورة {names[item.surah]} — الآيات {span}",
                prophetId=prophet["id"] if prophet else None, sourceIds=["alquran-cloud-muyassar"],
                parentChunk=f"{item.id}#1"))
    return built


def ibn_kathir_documents(records: list[dict], names: dict[int, str], registry: Registry,
                         prophets: dict[tuple[int, int], dict]) -> Built:
    """Layer 0 tafsir documents from Tafsir Ibn Kathir (test/corpus-tasks), one per section.

    Units are the section's paragraphs without the editor's [[notes]]
    (`ibn_kathir.display_text`); every unit cites the whole range the section
    explains. Tier 1, scholarly explanation. The source is `candidate`, so a
    release never admits these documents; they are for reviewers and the graph.
    """
    from . import ibn_kathir
    built = Built()
    for record in records:
        s, first, last = record["surah"], record["from_ayah"], record["to_ayah"]
        span = _span(first, last)
        ref = f"quran:{s}:{first}" + (f"-{last}" if last != first else "")
        units = [{"id": f"p{number}", "text": text, "reference": ref, "section": record["section_id"],
                  "keepWithNext": False, "sourceRefs": [ref], "parts": []}
                 for number, text in enumerate(ibn_kathir.paragraphs(record["text"]), 1)]
        if not units:
            built.skip("ibn_kathir_section_without_text")
            continue
        prophet = next((prophets[(s, ayah)] for ayah in range(first, last + 1) if (s, ayah) in prophets), None)
        source_id = record["source_id"]
        built.documents.append(_document(
            f"tafsir-ibn-kathir-{s:03d}-{first:03d}-{last:03d}", f"تفسير ابن كثير {s}:{span}", "tafsir",
            _source(registry, source_id, "Tafsir Ibn Kathir (Tafsir al-Quran al-Azim)"), units, tier=1,
            contextHeader=f"تفسير ابن كثير — سورة {names[s]} — الآيات {span}",
            prophetId=prophet["id"] if prophet else None, sourceIds=[source_id]))
    return built


def verbatim_parts(text: str) -> list[str]:
    """Contiguous excerpts of `text` at sentence (then comma) boundaries, about 45 words each."""
    if len(text.split()) <= LONG_HADITH_WORDS:
        return []
    for pattern in (_SENTENCE, _BOUNDARY):
        cuts, start, words = [], 0, 0
        for match in pattern.finditer(text):
            words = len(text[start:match.end()].split())
            if words >= PART_TARGET_WORDS:
                cuts.append((start, match.end()))
                start = match.end()
        if len(text[start:].split()) < PART_TARGET_WORDS / 3 and cuts:
            cuts[-1] = (cuts[-1][0], len(text))
        elif text[start:].strip():
            cuts.append((start, len(text)))
        parts = [text[a:b].strip() for a, b in cuts if text[a:b].strip()]
        if len(parts) >= 2:
            return parts
    return []


def hadith_documents(rows: dict[str, dict], clusters: dict[str, dict], nawawi_links: dict[str, dict],
                     registry: Registry) -> Built:
    built = Built()
    nawawi_by_ref: dict[str, list[str]] = {}
    for number, link in nawawi_links.items():
        if link["status"] == "linked":
            nawawi_by_ref.setdefault(link["ref"], []).append(number)
    for ref, row in rows.items():
        info = clusters[ref]
        if info["primary"] != ref:
            built.skip("cluster_member_not_primary")
            continue
        collection, number = ref.split(":", 1)
        members = [member for member in info["members"] if member != ref]
        nawawi = [n for member in info["members"] for n in nawawi_by_ref.get(member, [])]
        header = f"{COLLECTION_AR[collection]} — حديث رقم {number}"
        if nawawi:
            header += " — الأربعون النووية " + "، ".join(nawawi)
        primary_id = row["source_ids"][0]
        source_ids = row["source_ids"] if row["crosscheck_status"] in ("match", "contained_in_secondary") \
            else [primary_id]
        unit = {"id": "h", "text": row["arabic_text"], "reference": ref, "section": None, "keepWithNext": False,
                "sourceRefs": [ref], "parts": verbatim_parts(row["arabic_text"])}
        built.documents.append(_document(
            f"hadith-{collection}-{number.replace('.', '-')}", f"{COLLECTION_AR[collection]} {number}", "hadith",
            _source(registry, primary_id, COLLECTION_WORK[collection]), [unit], tier=0,
            grading=f"{row['grading']} ({row['grader']})", contextHeader=header, clusterId=info["cluster_id"],
            clusterRefs=members + [f"nawawi40:{n}" for n in nawawi], sourceIds=source_ids))
    return built


def write_corpus(root: Path, corpus_id: str, title: str, description: str, documents: list[dict]) -> None:
    if root.exists():
        shutil.rmtree(root)
    (root / "documents").mkdir(parents=True)
    (root / "corpus.json").write_text(json.dumps({"schemaVersion": 1, "id": corpus_id, "title": title,
                                                  "description": description}, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
    for document in documents:
        (root / "documents" / f"{document['id']}.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
