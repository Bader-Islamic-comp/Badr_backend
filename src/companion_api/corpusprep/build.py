"""Builds `corpus/canonical/` and the cross-check report from verified raw files."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from ..rag import normalize
from . import hadith, ibn_kathir, quran, quran_compare, quranpedia, rasm
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


def build_quran(registry: Registry, raw_root: Path, canonical: Path,
                reports: Path | None = None) -> tuple[dict, dict, dict]:
    raw = lambda sid: raw_path(raw_root, registry.get(sid))
    uthmani, notice = quran.parse_tanzil(raw("tanzil-quran-uthmani"))
    simple, _ = quran.parse_tanzil(raw("tanzil-quran-simple"))
    references = {
        "tanzil-quran-metadata": quran.parse_tanzil_metadata(raw("tanzil-quran-metadata")),
        "qurancom-chapters": quran.parse_qurancom_chapters(raw("qurancom-chapters")),
    }
    mushafs = {}
    if quranpedia.available(registry, quranpedia.MUSHAF_IDS):
        # test/corpus-tasks: the King Fahd Complex texts on Quranpedia; their per-surah counts must match too.
        mushafs = {sid: quranpedia.parse_mushaf(raw(sid), number) for sid, number in quranpedia.MUSHAF_IDS.items()}
        references.update({sid: mushaf.per_surah for sid, mushaf in mushafs.items()})
    verification = quran.verify(uthmani, simple, references)
    table, rasm_info = rasm.derive(uthmani, simple)
    if rasm.write_if_changed(normalize._RASM_FILE, table):
        normalize.RASM.clear()
        normalize.RASM.update(table)
        print(f"  rasm map updated: {rasm_info}", file=sys.stderr)
    verification["rasm_map"] = rasm_info
    checks = {}
    if mushafs:
        comparison = compare_with_kfc(uthmani, simple, mushafs)
        verification["kfc_comparison"] = {
            "compare_version": quran_compare.VERSION,
            **{name: {"ours": item["ours"], "reference": item["reference"], "statuses": item["summary"]["statuses"],
                      "per_surah_counts_match": item["summary"]["per_surah_counts_match"]}
               for name, item in comparison.items()}}
        for name, field_name in (("uthmani", "kfc_check"), ("simple", "kfc_check_simple")):
            for key, result in comparison[name]["results"].items():
                checks.setdefault(key, {})[field_name] = result.status
        if reports is not None:
            write_quran_comparison(reports, comparison)
    files = {"quran/ayat.jsonl": _write_jsonl(canonical / "quran" / "ayat.jsonl", quran.ayat_records(
        uthmani, simple, "tanzil-quran-uthmani", "tanzil-quran-simple", checks))}
    # The Tanzil terms require their notice in derived files; it is copied from the download, not retyped.
    (canonical / "quran" / "NOTICE.txt").write_text("\n".join(notice) + "\n", encoding="utf-8", newline="\n")
    tafsir, tafsir_summary = quran.tafsir_records(quran.parse_alquran_cloud(raw("alquran-cloud-muyassar")),
                                                  uthmani.keys(), "alquran-cloud-muyassar")
    files["tafsir/alquran-cloud-muyassar.jsonl"] = _write_jsonl(
        canonical / "tafsir" / "alquran-cloud-muyassar.jsonl", tafsir)
    if ibn_kathir.available(registry):
        # test/corpus-tasks: Tafsir Ibn Kathir, one record per section (consecutive ayat sharing one explanation).
        texts = {}
        for surah in range(1, 115):
            texts.update(ibn_kathir.parse_surah(raw(ibn_kathir.source_id(surah)), surah))
        sections, ibn_kathir_summary = ibn_kathir.sections(texts, uthmani.keys())
        files["tafsir/ibn-kathir.jsonl"] = _write_jsonl(canonical / "tafsir" / "ibn-kathir.jsonl", sections)
        tafsir_summary = {**tafsir_summary, "ibn_kathir": ibn_kathir_summary}
    return files, verification, tafsir_summary


# test/corpus-tasks: the Quranpedia dumps of the reference package --------------------------------------------

def compare_with_kfc(uthmani: dict, simple: dict, mushafs: dict[str, "quranpedia.Mushaf"]) -> dict:
    """Tanzil Uthmani against the Complex's Uthmani text, Tanzil Simple against the print's standard spelling."""
    out = {}
    for name, ours_id, ours, reference_id in (
            ("uthmani", "tanzil-quran-uthmani", uthmani, quranpedia.MUSHAF_UTHMANI),
            ("simple", "tanzil-quran-simple", simple, quranpedia.MUSHAF_PRINT)):
        mushaf = mushafs[reference_id]
        results, summary = quran_compare.compare(ours, mushaf.texts)
        out[name] = {"ours": ours_id, "reference": reference_id, "reference_name": mushaf.name,
                     "reference_description": mushaf.description, "reference_version": mushaf.version,
                     "results": results, "summary": summary}
    return out


_DETAILS = "quran_text_comparison_details.jsonl"


def write_quran_comparison(reports: Path, comparison: dict) -> Path:
    """`quran_text_comparison.md` and `.json` (counts, references and word positions, no Quran text) and the
    details with the differing words, `quran_text_comparison_details.jsonl`, which stays out of git."""
    reports.mkdir(parents=True, exist_ok=True)
    ref = lambda key: f"quran:{key[0]}:{key[1]}"
    data = {"generated_by": "scripts/fetch_sources.py", "compare_version": quran_compare.VERSION,
            "note": "Counts, references and word positions only; the differing words are in "
                    f"corpus/reports/{_DETAILS} (not in git).", "comparisons": {}}
    details = []
    for name, item in comparison.items():
        results, summary = item["results"], item["summary"]
        by_status = {status: [key for key, result in results.items() if result.status == status]
                     for status in quran_compare.STATUSES}
        kinds = {}
        for result in results.values():
            for diff in result.diffs:
                kinds[diff["kind"]] = kinds.get(diff["kind"], 0) + 1
        data["comparisons"][name] = {
            "ours": item["ours"], "reference": item["reference"], "reference_name": item["reference_name"],
            "reference_version": item["reference_version"], "ayat_compared": summary["ayat_compared"],
            "statuses": summary["statuses"], "difference_kinds": dict(sorted(kinds.items())),
            "per_surah_counts_match": summary["per_surah_counts_match"],
            "per_surah_count_differences": summary["per_surah_count_differences"],
            "missing_in_reference": summary["missing_in_reference"], "missing_in_ours": summary["missing_in_ours"],
            "identical": [ref(key) for key in by_status["identical"]],
            "basmala_prefixed": [ref(key) for key in by_status["basmala_prefixed"]],
            "identical_except_hamza": {ref(key): results[key].public()["diffs"]
                                       for key in by_status["identical_except_hamza"]},
            "basmala_prefixed_with_hamza": {ref(key): results[key].public()["diffs"]
                                            for key in by_status["basmala_prefixed"] if len(results[key].diffs) > 1},
            "differs": {ref(key): results[key].public()["diffs"] for key in by_status["differs"]}}
        for key, result in results.items():
            if result.status not in ("identical", "identical_after_normalization"):
                details.append({"comparison": name, "ref": ref(key), "status": result.status,
                                "basmala_prefix": result.basmala_prefix, "diffs": result.diffs})
    (reports / "quran_text_comparison.json").write_text(_compact_json(data) + "\n", encoding="utf-8", newline="\n")
    (reports / _DETAILS).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in details),
                                    encoding="utf-8", newline="\n")
    path = reports / "quran_text_comparison.md"
    path.write_text(_comparison_markdown(data), encoding="utf-8", newline="\n")
    return path


def _compact_json(value, indent: int = 0, width: int = 110) -> str:
    """Indented JSON that keeps a short object or list on one line and packs long lists of plain values, so a
    report of several hundred references stays readable in a diff."""
    flat = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or len(flat) + indent <= width:
        return flat
    pad, end = " " * (indent + 1), "\n" + " " * indent
    if isinstance(value, dict):
        return "{\n" + ",\n".join(f"{pad}{json.dumps(key, ensure_ascii=False)}: {_compact_json(item, indent + 1)}"
                                  for key, item in value.items()) + end + "}"
    if any(isinstance(item, (dict, list)) for item in value):
        return "[\n" + ",\n".join(pad + _compact_json(item, indent + 1) for item in value) + end + "]"
    lines, line = [], ""
    for item in (json.dumps(item, ensure_ascii=False) for item in value):
        if line and len(pad) + len(line) + len(item) + 2 > width:
            lines.append(line + ",")
            line = ""
        line = f"{line}, {item}" if line else item
    return "[\n" + "\n".join(pad + part for part in lines + [line]) + end + "]"


def _refs(refs, limit: int = 400) -> str:
    refs = [r.removeprefix("quran:") for r in refs]
    return (", ".join(refs[:limit]) + (f" … and {len(refs) - limit} more" if len(refs) > limit else "")) or "none"


def _comparison_markdown(data: dict) -> str:
    uthmani, simple = data["comparisons"]["uthmani"], data["comparisons"]["simple"]
    lines = [
        "# Quran text comparison: Tanzil and the King Fahd Complex text on Quranpedia",
        "",
        "Generated by `scripts/fetch_sources.py`; do not edit by hand. The reference package asks for the Quranic",
        "text in its rasm as approved (the King Fahd Complex print, or quranpedia.net) and says to make sure the",
        "ayat are transmitted faithfully. This report holds counts, references and word positions only; the",
        f"differing words are in `corpus/reports/{_DETAILS}` (local, not in git).",
        "Nothing was changed in any text: the per-ayah result is stored as metadata (`kfc_check`,",
        "`kfc_check_simple`) in `corpus/canonical/quran/ayat.jsonl`.",
        "",
        "## Texts compared",
        "",
        "| Comparison | Ours (canonical) | Reference (Quranpedia) | Reference dump |",
        "| --- | --- | --- | --- |",
        f"| Uthmani rasm (`kfc_check`) | `{uthmani['ours']}` | `{uthmani['reference']}`: {uthmani['reference_name']}, "
        f"the Complex's Uthmani Hafs text (UthmanicHafs font) | {uthmani['reference_version']} |",
        f"| Standard spelling (`kfc_check_simple`) | `{simple['ours']}` | `{simple['reference']}`: "
        f"{simple['reference_name']}, the King Fahd Complex print (its `text` field is in standard spelling, its "
        f"pages are the print's) | {simple['reference_version']} |",
        "",
        "## Ayah counts per surah",
        "",
    ]
    for name, item in (("Uthmani", uthmani), ("Standard spelling", simple)):
        lines.append(f"- {name}: {item['ayat_compared']:,} ayat compared; per-surah counts "
                     + ("match for all 114 surahs" if item["per_surah_counts_match"] else
                        f"DIFFER for surahs {sorted(item['per_surah_count_differences'])}")
                     + f"; missing in the reference: {len(item['missing_in_reference'])}, missing in ours: "
                       f"{len(item['missing_in_ours'])}.")
    lines += [
        "",
        f"## Method (`{data['compare_version']}`)",
        "",
        "Each ayah is split into words on spaces and every word is folded the same way on both sides. The folded",
        "view is used for the comparison only (`corpusprep/quran_compare.py`).",
        "",
        "Level 1, writing conventions of the two digital editions:",
        "",
        "1. Unicode NFC (Quranpedia writes ي + hamza as two characters in places; Tanzil writes ئ).",
        "2. U+FEFF removed (a byte-order mark opens most ayat of mushafs-1).",
        "3. Tatweel U+0640 removed (Tanzil draws a superscript alef or a hamza on a tatweel).",
        "4. Removed: harakat; tanween in every form (Tanzil ً ٌ ٍ, the Complex's open tanween U+0656, U+0657,",
        "   U+065E); shadda; sukun in both forms (U+0652 and the Complex's U+06E1); maddah U+0653; the other",
        "   combining vowel signs U+0656-U+065E; superscript alef U+0670; the Quranic annotation signs",
        "   U+06D6-U+06ED (pause marks, small high letters, the small waw and ya of the silah, ۞, ۩, the small",
        "   meem of iqlab); open tanween U+08F0-U+08F3.",
        "5. Alef wasla ٱ to alef ا.",
        "6. Alef maksura ى to ya ي: Tanzil's Uthmani text encodes the print's undotted final ya as ى; the Complex",
        "   encodes ي and its font draws it undotted.",
        "7. A word left empty (a pause mark standing between spaces in Tanzil) is not a word.",
        "",
        "Level 2, the hamza (only when level 1 still differs): Unicode NFD, then ء and the hamza signs U+0654,",
        "U+0655, U+065F removed, so أ إ آ become ا, ؤ becomes و and ئ becomes ي. The letters around the hamza",
        "are still compared exactly.",
        "",
        "A first ayah that starts, in our text only, with the surah's opening basmala is `basmala_prefixed` when",
        "the rest agrees. Word positions count the words left after level 1 (a stand-alone pause mark is not a",
        "word), from 1, in each text as stored.",
        "",
        "## Results",
        "",
        "| Status | Uthmani | Standard spelling |",
        "| --- | ---: | ---: |",
    ]
    for status in quran_compare.STATUSES:
        lines.append(f"| {status} | {uthmani['statuses'][status]:,} | {simple['statuses'][status]:,} |")
    lines += ["", "Kinds of difference (one ayah can have several): "
              + "; ".join(f"Uthmani {kind} {count:,}" for kind, count in uthmani["difference_kinds"].items())
              + "; " + "; ".join(f"standard spelling {kind} {count:,}"
                                 for kind, count in simple["difference_kinds"].items()) + ".", ""]
    for title, item in (("Uthmani", uthmani), ("Standard spelling", simple)):
        lines += [f"### {title}: `{item['ours']}` against `{item['reference']}`", ""]
        lines.append(f"- `differs` ({len(item['differs'])}): " + ("none" if not item["differs"] else "; ".join(
            f"{r.removeprefix('quran:')} ours words {_positions(d['ours'])} / reference {_positions(d['theirs'])} "
            f"({d['kind']})" for r, diffs in item["differs"].items() for d in diffs if d["kind"] != "basmala")) + ".")
        lines.append(f"- `basmala_prefixed` ({len(item['basmala_prefixed'])}): every surah's ayah 1 except 1 and 9"
                     if len(item["basmala_prefixed"]) == 112 and not any(
                         r in item["basmala_prefixed"] for r in ("quran:1:1", "quran:9:1"))
                     else f"- `basmala_prefixed` ({len(item['basmala_prefixed'])}): {_refs(item['basmala_prefixed'])}")
        if item["basmala_prefixed_with_hamza"]:
            lines[-1] += ("; in " + _refs(list(item["basmala_prefixed_with_hamza"]))
                          + " a hamza is also written differently")
        lines[-1] += "."
        lines.append(f"- `identical_except_hamza` ({len(item['identical_except_hamza'])}): "
                     + _refs(list(item["identical_except_hamza"])) + ".")
        lines.append(f"- `identical` ({len(item['identical'])}): " + _refs(item["identical"]) + ".")
        lines.append("")
    letters = sum(1 for diffs in uthmani["differs"].values() for d in diffs if d["kind"] == "words")
    divided = [r for r, diffs in uthmani["differs"].items() if any(d["kind"] == "word_division" for d in diffs)]
    division = len(divided)
    same = uthmani["statuses"]["identical"] + uthmani["statuses"]["identical_after_normalization"]
    lines += [
        "## Verdict",
        "",
        f"**Tanzil's Uthmani text is not word-for-word identical to the King Fahd Complex text as stored.** "
        f"{same:,} of {uthmani['ayat_compared']:,} ayat have the same words once diacritics and annotation marks "
        "are removed and glyph variants folded; "
        f"{uthmani['statuses']['identical_except_hamza']:,} more differ only in how a hamza is written; "
        f"{uthmani['statuses']['basmala_prefixed']:,} first ayat carry, in Tanzil, the surah's opening basmala, "
        "which the print sets above the surah without a number (in Hafs it is an ayah of al-Fatiha only); and "
        f"{uthmani['statuses']['differs']:,} ayat differ: {division} by word division "
        f"(the same letters divided into words differently: {_refs(divided)}) and {letters} by an added, missing "
        "or different word. "
        + ("Apart from the hamza and the folds above, no ayah differs in its letters." if letters == 0 else
           "Some ayat differ in their words: see `differs` above."),
        "",
        "The standard-spelling texts (Tanzil Simple and mushafs-1) agree in the same way, apart from the opening "
        f"basmala and {simple['statuses']['differs']} ayat that write a word in another standard spelling (word "
        "division, or a final alef written ى in one and ا in the other).",
        "",
        "## Recommendation (not done here)",
        "",
        "- Switch the displayed (primary) Quran text to the Complex's Uthmani text, `quranpedia-mushaf-hafs-text`,",
        "  once governance clears it: it is the text the reference package names, and it does not put the opening",
        "  basmala inside ayah 1. Keep a standard-spelling text for search (Tanzil Simple, or mushafs-1) and",
        "  re-derive the rasm map (`corpusprep/rasm.py`) from the new pair.",
        "- Before switching, check how the app's Arabic font draws the Complex's encoding (sukun U+06E1, open",
        "  tanween U+0656, U+0657, U+065E): it is made for the Complex's UthmanicHafs font, whose licence also",
        "  needs checking. Quranpedia corrects its text continuously, so pin the dump version and diff each update.",
        "- Until then, Tanzil is safe for development (no letter differs apart from the hamza), but the opening",
        "  basmala should not be shown as part of ayah 1. Removing it changes the stored text, which Tanzil's terms",
        "  forbid, so it is a display rule for governance to decide, or a reason to switch.",
        f"- The word-division differences ({_refs(divided)}) and the hamza spellings need a reviewer with the",
        "  printed mushaf; neither text is changed here.",
        "",
    ]
    return "\n".join(lines)


def _positions(span: list[int]) -> str:
    if not span:
        return "(none)"
    return str(span[0]) if span[0] == span[1] else f"{span[0]}-{span[1]}"


def build_quranpedia(registry: Registry, raw_root: Path, canonical: Path) -> tuple[dict, dict]:
    """Canonical English translations (`translations/<source_id>.jsonl`, one record per ayah) and tafsir books
    (`tafsir/quranpedia-<slug>.jsonl`, one record per passage) for every registered Quranpedia source."""
    raw = lambda sid: raw_path(raw_root, registry.get(sid))
    ids = {source["source_id"] for source in registry.sources}
    uthmani, _ = quran.parse_tanzil(raw("tanzil-quran-uthmani"))
    per_surah = quran.per_surah(uthmani)
    books = quranpedia.parse_books_index(raw(quranpedia.BOOKS_INDEX)) if quranpedia.BOOKS_INDEX in ids else {}
    files, info = {}, {"translations": {}, "tafsir": {}}
    for translation in quranpedia.TRANSLATIONS:
        if translation.source_id not in ids:
            continue
        rule = registry.get(translation.source_id).get("package_rule")
        meta, entries = quranpedia.parse_translation(raw(translation.source_id), translation)
        records, summary = quranpedia.translation_records(entries, uthmani.keys(), translation, rule)
        name = f"translations/{translation.source_id}.jsonl"
        files[name] = _write_jsonl(canonical / name, records)
        info["translations"][translation.source_id] = {
            "package_rule": rule, "content_type": translation.content_type, "book_id": translation.book_id,
            "book": books.get(translation.book_id), "name": meta.get("name"), **summary}
    for book in quranpedia.TAFSIR_BOOKS:
        if book.source_id not in ids:
            continue
        rule = registry.get(book.source_id).get("package_rule")
        meta, passages = quranpedia.parse_tafsir(raw(book.source_id), book, per_surah)
        records, summary = quranpedia.tafsir_records(passages, book, rule)
        files[book.canonical_name] = _write_jsonl(canonical / book.canonical_name, records)
        info["tafsir"][book.source_id] = {
            "package_rule": rule, "layer0": rule in quranpedia.LAYER0_RULES, "book_id": book.book_id,
            "book": books.get(book.book_id), "dump_version": meta.get("version"), **summary}
    return files, info


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
                   hadith_info: list, quranpedia_info: dict | None = None) -> Path:
    manifest = {
        "schema_version": 1, "registry_sha256": registry.digest, "normalizer": normalize.VERSION,
        "sources": {source["source_id"]: source["sha256"] for source in registry.sources},
        "files": dict(sorted(files.items())), "quran": quran_info, "tafsir": tafsir_info,
        "hadith": [{key: value for key, value in info.items() if key != "primary_empty_numbers"}
                   for info in hadith_info],
    }
    if quranpedia_info:
        manifest["quranpedia"] = quranpedia_info
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
