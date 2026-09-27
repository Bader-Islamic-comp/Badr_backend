"""Builds `corpus/canonical/` and the cross-check report from verified raw files."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from ..rag import normalize
from . import hadith, quran, rasm
from .fetch import raw_path
from .registry import Registry

# (collection, primary source, secondary source or None, how to pair entries)
COLLECTIONS = (
    ("bukhari", "fawazahmed0-ara-bukhari", "mhashim6-bukhari", "text"),
    ("muslim", "fawazahmed0-ara-muslim", "mhashim6-muslim", "text"),
    ("nawawi40", "fawazahmed0-ara-nawawi", "ahmedbaset-nawawi40", "number"),
    ("riyadussalihin", "ahmedbaset-riyadussalihin", None, None),
    ("adab_mufrad", "ahmedbaset-adab-mufrad", None, None),
)
_PARSERS = {"fawazahmed0": hadith.parse_fawazahmed0, "ahmedbaset": hadith.parse_ahmedbaset,
            "mhashim6": hadith.parse_mhashim6}


def _write_jsonl(path: Path, rows: list[dict]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(data)
    return {"sha256": sha256(data).hexdigest(), "records": len(rows)}


def _parse(registry: Registry, raw_root: Path, source_id: str) -> hadith.Parsed:
    return _PARSERS[source_id.split("-", 1)[0]](raw_path(raw_root, registry.get(source_id)))


def build_quran(registry: Registry, raw_root: Path, canonical: Path) -> tuple[dict, dict, dict]:
    raw = lambda sid: raw_path(raw_root, registry.get(sid))
    uthmani, notice = quran.parse_tanzil(raw("tanzil-quran-uthmani"))
    simple, _ = quran.parse_tanzil(raw("tanzil-quran-simple"))
    verification = quran.verify(uthmani, simple, {
        "tanzil-quran-metadata": quran.parse_tanzil_metadata(raw("tanzil-quran-metadata")),
        "qurancom-chapters": quran.parse_qurancom_chapters(raw("qurancom-chapters")),
    })
    table, rasm_info = rasm.derive(uthmani, simple)
    if rasm.write_if_changed(normalize._RASM_FILE, table):
        normalize.RASM.clear()
        normalize.RASM.update(table)
        print(f"  rasm map updated: {rasm_info}", file=sys.stderr)
    verification["rasm_map"] = rasm_info
    files = {"quran/ayat.jsonl": _write_jsonl(canonical / "quran" / "ayat.jsonl", quran.ayat_records(
        uthmani, simple, "tanzil-quran-uthmani", "tanzil-quran-simple"))}
    # The Tanzil terms require their notice in derived files; it is copied from the download, not retyped.
    (canonical / "quran" / "NOTICE.txt").write_text("\n".join(notice) + "\n", encoding="utf-8", newline="\n")
    tafsir, tafsir_summary = quran.tafsir_records(quran.parse_alquran_cloud(raw("alquran-cloud-muyassar")),
                                                  uthmani.keys(), "alquran-cloud-muyassar")
    files["tafsir/alquran-cloud-muyassar.jsonl"] = _write_jsonl(
        canonical / "tafsir" / "alquran-cloud-muyassar.jsonl", tafsir)
    return files, verification, tafsir_summary


def build_hadith(registry: Registry, raw_root: Path, canonical: Path, out=sys.stderr) -> tuple[dict, list, list]:
    candidates = {source["source_id"] for source in registry.sources if source["status"] == "candidate"}
    files, summaries, discrepancies = {}, [], []
    for collection, primary_id, secondary_id, pairing in COLLECTIONS:
        print(f"  hadith: {collection}", file=out, flush=True)
        primary = _parse(registry, raw_root, primary_id)
        secondary = _parse(registry, raw_root, secondary_id) if secondary_id else None
        matches = None
        if pairing == "number":
            matches = hadith.crosscheck_by_number(primary.entries, secondary.entries)
        elif pairing == "text":
            matches = hadith.crosscheck_by_text(primary.entries, secondary.entries, progress=lambda done, total: print(
                f"    ... cross-checked {done}/{total}", file=out, flush=True))
        rows = hadith.records(collection, primary, primary_id, secondary_id, matches, candidates)
        files[f"hadith/{collection}.jsonl"] = _write_jsonl(canonical / "hadith" / f"{collection}.jsonl", rows)
        info = hadith.summary(collection, primary, secondary, rows)
        info.update(primary_source=primary_id, secondary_source=secondary_id, pairing=pairing)
        summaries.append(info)
        discrepancies += [{"collection": collection, "number": row["number"], "status": row["crosscheck_status"],
                           "crosscheck": row["crosscheck"]} for row in rows
                          if row["crosscheck_status"] in ("text_differs", "not_matched")]
    return files, summaries, discrepancies


def write_mapping(reports: Path, registry: Registry, raw_root: Path, canonical: Path) -> Path:
    """One CSV row per primary record paired by text: its number in each numbering system (numbers only)."""
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / "hadith_number_mapping.csv"
    lines = ["collection,primary_source,primary_number,primary_numbering,secondary_source,secondary_number,"
             "secondary_numbering,status,dice,containment"]
    for collection, primary_id, secondary_id, pairing in COLLECTIONS:
        if pairing != "text":
            continue
        numbering = hadith.NUMBERING[secondary_id.split("-", 1)[0]]
        for line in (canonical / "hadith" / f"{collection}.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            other = row["crosscheck"] or {}
            lines.append(",".join(str(value) for value in (
                collection, primary_id, row["number"], row["numbering_system"], secondary_id,
                other.get("number", ""), numbering, row["crosscheck_status"], other.get("similarity", ""),
                other.get("containment", ""))))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def write_manifest(canonical: Path, registry: Registry, files: dict, quran_info: dict, tafsir_info: dict,
                   hadith_info: list) -> Path:
    manifest = {
        "schema_version": 1, "registry_sha256": registry.digest, "normalizer": normalize.VERSION,
        "sources": {source["source_id"]: source["sha256"] for source in registry.sources},
        "files": dict(sorted(files.items())), "quran": quran_info, "tafsir": tafsir_info,
        "hadith": [{key: value for key, value in info.items() if key != "primary_empty_numbers"}
                   for info in hadith_info],
    }
    path = canonical / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def _statuses(info: dict) -> str:
    order = ("match", "contained_in_secondary", "text_differs", "not_matched", "single_source")
    return " / ".join(str(info["statuses"].get(key, 0)) for key in order)


def write_report(reports: Path, registry: Registry, hadith_info: list, discrepancies: list) -> Path:
    reports.mkdir(parents=True, exist_ok=True)
    details = reports / "hadith_crosscheck_details.jsonl"
    details.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in discrepancies),
                       encoding="utf-8", newline="\n")
    lines = [
        "# Hadith cross-check report",
        "",
        "Generated by `scripts/fetch_sources.py`. Nothing here is resolved automatically: every",
        "`text_differs` and `not_matched` record stays unresolved until a reviewer decides it, and no text",
        "is copied from one source into another. The report lists numbers and scores only, never hadith text.",
        "",
        "## Method",
        "",
        f"- Both texts are reduced to a comparison-only view, `{hadith.COMPARE_VERSION}`: `norm-v1` search text",
        "  (diacritics, tatweel, alef/ya/ta-marbuta folded, punctuation removed), a detached conjunction waw",
        "  joined to the next word, and alef dropped so classical spellings compare equal. This view is never",
        "  stored or shown; the canonical `arabic_text` is untouched.",
        "- Similarity is the Dice coefficient of word-trigram sets.",
        "- A primary entry split over consecutive second-source entries (up to 3 either side of its best",
        "  match) is compared with their union; the match is then a span such as `2729-2732`.",
        f"- `match`: Dice >= {hadith.MATCH}. `contained_in_secondary`: Dice lower, but >= {hadith.CONTAINED} of the",
        "  primary's trigrams are inside one longer second-source entry (islamware groups several narrations",
        "  under one number), so the wording agrees and only the granularity differs.",
        f"  `text_differs`: Dice or containment >= {hadith.DIFFERS}. Lower, or no candidate: `not_matched`. One source: `single_source`.",
        "- Same numbering system: the entry with the same number is compared. Different numbering",
        "  (sunnah.com vs islamware): each primary entry is compared with its most similar entries in the",
        "  second source. The number mapping between the two systems is `corpus/reports/hadith_number_mapping.csv`.",
        "- Grading: Bukhari and Muslim are `sahih` by collection rule. No other source gives a structured",
        "  grading with its grader, so those records have `grading: null` and are ineligible.",
        "",
        "## Summary",
        "",
        "| collection | primary | second source | pairing | records | empty in primary | match / contained / text_differs / not_matched / single_source | second-source entries never matched | eligible |",
        "| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for info in hadith_info:
        lines.append(f"| {info['collection']} | `{info['primary_source']}` | "
                     f"{'`' + info['secondary_source'] + '`' if info['secondary_source'] else '—'} | "
                     f"{info['pairing'] or '—'} | {info['records']} | {info['primary_empty_text']} | "
                     f"{_statuses(info)} | "
                     f"{info['secondary_unmatched'] if info['secondary_unmatched'] is not None else '—'} | "
                     f"{info['eligible']} |")
    lines += ["", "## Source status", "", "| source | status | licence |", "| --- | --- | --- |"]
    used = {info["primary_source"] for info in hadith_info} | {info["secondary_source"] for info in hadith_info}
    for source in registry.sources:
        if source["source_id"] in used:
            lines.append(f"| `{source['source_id']}` | {source['status']} | {source['license']} |")
    lines += ["", "## Notes", "",
              "- `nawawi40` is checked against `ahmedbaset-nawawi40`, which likely shares a sunnah.com upstream",
              "  with the primary, so agreement there is weaker evidence than for Bukhari and Muslim (islamware).",
              "- `riyadussalihin` and `adab_mufrad` have one source only (licence unclear) and no grading.",
              "- A second-source entry can be the best match of two primary entries (repeated hadith with",
              "  near-identical chains); see `secondary_matched_more_than_once` in `corpus/canonical/manifest.json`.",
              "", "## Empty entries in the primary source", ""]
    for info in hadith_info:
        if info["primary_empty_numbers"]:
            shown = ", ".join(info["primary_empty_numbers"][:60])
            more = len(info["primary_empty_numbers"]) - 60
            lines.append(f"- {info['collection']} ({len(info['primary_empty_numbers'])}): {shown}"
                         + (f" … and {more} more" if more > 0 else ""))
    lines += ["", "## Lowest-similarity records (up to 25 per collection)", "",
              "Full list: `corpus/reports/hadith_crosscheck_details.jsonl`.", ""]
    for info in hadith_info:
        rows = sorted((row for row in discrepancies if row["collection"] == info["collection"]),
                      key=lambda row: row["crosscheck"]["similarity"] if row["crosscheck"] else -1)
        if not rows:
            continue
        lines += [f"### {info['collection']} ({len(rows)} unresolved)", "",
                  "| number | status | best match in second source | Dice | containment |",
                  "| --- | --- | --- | ---: | ---: |"]
        for row in rows[:25]:
            other = row["crosscheck"]
            lines.append(f"| {row['number']} | {row['status']} | {other['number'] if other else '—'} | "
                         f"{other['similarity'] if other else '—'} | {other['containment'] if other else '—'} |")
        lines.append("")
    path = reports / "hadith_crosscheck.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path
