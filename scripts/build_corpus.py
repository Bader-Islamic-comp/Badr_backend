"""Structure-aware ingestion (corpus tasks Phase 2): canonical data -> checked candidates -> corpus folders.

    python scripts/build_corpus.py            check candidates, build corpus/layer0 and corpus/wave1,
                                              validate and chunk both with the existing pipeline

Writes status fields back into corpus/aliases.yaml, corpus/candidate/prophets/*_source_map.yaml and
corpus/candidate/hadith_selection.yaml (derived, deterministic), and a summary to corpus/reports/.
corpus/layer0 and corpus/wave1 hold third-party text and stay out of git; rebuild them with this script.
Exit status: 0 ok, 1 a check or validation failed.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from companion_api.corpusprep import age_band, candidates, cluster, competition, ingest, quran, quranpedia, registry as registry_module  # noqa: E402,E501
from companion_api.corpusprep.segments import load_metadata, load_transliterated_names, segment, verify_cover  # noqa: E402,E501
from companion_api.rag.chunking import VERSION as CHUNKER, chunk_documents  # noqa: E402
from companion_api.rag.corpus import load_corpus, word_count  # noqa: E402
from companion_api.rag import normalize  # noqa: E402


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _validate(root: Path) -> dict:
    started = time.time()
    corpus, report = load_corpus(root)
    if not report.ok:
        for issue in report.errors[:20]:
            _log(f"  {issue}")
        raise SystemExit(f"FAILED: {root} has {len(report.errors)} validation errors")
    chunks = chunk_documents(corpus.documents)
    parents = [chunk for chunk in chunks if not chunk.is_child]
    words = [word_count(chunk.text) for chunk in parents]
    return {
        "documents": len(corpus.documents), "chunks": len(chunks), "parent_chunks": len(parents),
        "child_chunks": len(chunks) - len(parents),
        "by_content_type": dict(Counter(chunk.content_type for chunk in chunks)),
        "warnings": len(report.warnings), "errors": 0,
        "parent_words": {"max": max(words), "median": sorted(words)[len(words) // 2]},
        "every_chunk_has_source_refs": all(chunk.source_refs for chunk in chunks),
        "every_chunk_has_header": all(chunk.context_header for chunk in chunks),
        "seconds": round(time.time() - started, 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-root", type=Path, default=ROOT / "corpus")
    args = parser.parse_args(argv)
    base = args.corpus_root
    registry = registry_module.load(base / "sources/registry.yaml")
    canonical = base / "canonical"

    _log("loading canonical data")
    ayat_rows = _jsonl(canonical / "quran/ayat.jsonl")
    ayat = {(row["surah"], row["ayah"]): row for row in ayat_rows}
    simple = {key: row["text_simple"] for key, row in ayat.items()}
    tafsir = {(row["surah"], row["ayah"]): row["text"] for row in _jsonl(canonical / "tafsir/alquran-cloud-muyassar.jsonl")}
    hadith_rows = {f"{row['collection']}:{row['number']}": row for collection in ("bukhari", "muslim")
                   for row in _jsonl(canonical / f"hadith/{collection}.jsonl")}
    nawawi_rows = _jsonl(canonical / "hadith/nawawi40.jsonl")

    _log("checking aliases and source maps")
    header, aliases = candidates.load_yaml(base / "aliases.yaml")
    aliases, alias_summary = candidates.check_aliases(aliases, simple)
    candidates.save_yaml(base / "aliases.yaml", header, aliases)
    names = {p["id"]: p["names_ar"][0]["alias"] for p in aliases["prophets"]}
    prophets_by_ayah, maps_summary, topics_by_ayah = {}, {}, {}
    for path in sorted((base / "candidate/prophets").glob("*_source_map.yaml")):
        header, data = candidates.load_yaml(path)
        data, summary = candidates.check_source_map(data, simple, aliases)
        candidates.save_yaml(path, header, data)
        maps_summary[data["prophet_id"]] = summary
        for item in data["ranges"]:
            if item["checks"]["exists"]:
                surah, first, last = candidates.parse_quran_ref(item["ref"])
                for ayah in range(first, last + 1):
                    prophets_by_ayah.setdefault((surah, ayah), {"id": data["prophet_id"],
                                                               "name": names[data["prophet_id"]]})
                    topics_by_ayah.setdefault((surah, ayah), item["topic"])

    _log("clustering hadith and linking Nawawi 40")
    records = [cluster.Record(row["collection"], row["number"], row["eligible"],
                              frozenset(cluster.grams(cluster.matn_tokens(row["arabic_text"]))))
               for row in hadith_rows.values()]
    clusters = cluster.cluster(records)
    links = cluster.link_nawawi([(row["number"], row["arabic_text"]) for row in nawawi_rows], records)
    sizes = Counter(len(info["members"]) for info in {info["cluster_id"]: info for info in clusters.values()}.values())

    _log("checking the hadith selection")
    header, selection = candidates.load_yaml(base / "candidate/hadith_selection.yaml")
    selection, selection_summary = candidates.check_selection(selection, hadith_rows, clusters, links)
    candidates.save_yaml(base / "candidate/hadith_selection.yaml", header, selection)

    _log("segmenting the Quran")
    metadata_path = next((base / "raw/tanzil-quran-metadata").glob("*.xml"))
    surah_names, rukus = load_metadata(metadata_path)
    counts = quran.per_surah(ayat)
    words = {key: len(row["text_uthmani"].split()) for key, row in ayat.items()}
    segments = segment(counts, rukus, words)
    verify_cover(segments, counts)

    _log("building corpus/layer0 (all of layer 0, development index)")
    built_quran = ingest.quran_documents(segments, ayat, tafsir, surah_names, registry, prophets_by_ayah)
    built_hadith = ingest.hadith_documents(hadith_rows, clusters, links, registry)
    layer0 = built_quran.documents + built_hadith.documents
    # test/corpus-tasks: Tafsir Ibn Kathir, when its sources were fetched (a candidate source: layer 0 only).
    ibn_kathir_path = canonical / "tafsir/ibn-kathir.jsonl"
    built_ibn_kathir = ingest.Built()
    if ibn_kathir_path.is_file():
        built_ibn_kathir = ingest.ibn_kathir_documents(_jsonl(ibn_kathir_path), surah_names, registry,
                                                       prophets_by_ayah)
        layer0 += built_ibn_kathir.documents
    # test/corpus-tasks: Quranpedia English translations and the tafsir books the package's rule admits or that
    # the organizers must rule on (in_rule, borderline); candidate sources, so layer 0 only, never wave 1.
    registered = {source["source_id"] for source in registry.sources}
    names_en = load_transliterated_names(metadata_path)
    latin = {entry["id"]: (entry.get("latin") or [entry["id"].title()])[0] for entry in aliases["prophets"]}
    prophets_en = {key: {**value, "latin": latin.get(value["id"])} for key, value in prophets_by_ayah.items()}
    quranpedia_docs, quranpedia_skipped = {}, {}
    for translation in quranpedia.TRANSLATIONS:
        path = canonical / f"translations/{translation.source_id}.jsonl"
        if translation.source_id in registered and path.is_file():
            _log(f"building English documents: {translation.source_id}")
            translated = {(row["surah"], row["ayah"]): row for row in _jsonl(path)}
            built = ingest.translation_documents(segments, translated, translation, names_en, registry, prophets_en)
            layer0 += built.documents
            quranpedia_docs[translation.source_id] = len(built.documents)
            quranpedia_skipped.update(built.skipped)
    for book in quranpedia.TAFSIR_BOOKS:
        path = canonical / book.canonical_name
        if book.source_id not in registered or not path.is_file():
            continue
        if registry.get(book.source_id).get("package_rule") not in quranpedia.LAYER0_RULES:
            continue  # outside the package's rule: canonical only, for comparison
        _log(f"building tafsir documents: {book.source_id}")
        built = ingest.quranpedia_tafsir_documents(segments, _jsonl(path), book, surah_names, registry,
                                                   prophets_by_ayah)
        layer0 += built.documents
        quranpedia_docs[book.source_id] = len(built.documents)
        quranpedia_skipped.update(built.skipped)
    # test/corpus-tasks-c2: the team's Arabic competition package (corpus/competition-ar), in layer 0 and wave 1.
    _log("building the competition package documents (corpus/competition-ar)")
    try:
        competition_docs = competition.build(base / "competition-ar/content.json", registry, base / "raw")
    except competition.CompetitionError as error:
        raise SystemExit(f"FAILED: competition package: {error}")
    layer0 += competition_docs
    _log("attaching generated retrieval questions (checked against sacred text)")
    generated = json.loads((base / "candidate/retrieval_questions.json").read_text(encoding="utf-8"))
    sacred = age_band.SacredIndex([row["text_simple"] for row in ayat_rows],
                                  [row["arabic_text"] for row in hadith_rows.values()] +
                                  [row["arabic_text"] for row in nawawi_rows])
    refused = [(doc_id, q) for doc_id, qs in generated["questions"].items() for q in qs if sacred.overlaps(q)]
    if refused:
        raise SystemExit(f"FAILED: {len(refused)} generated questions repeat sacred text, e.g. {refused[:3]}")
    questions_by_doc = generated["questions"]
    for doc in layer0:
        if doc["id"] in questions_by_doc:
            doc["generatedQuestions"] = questions_by_doc[doc["id"]]
    ingest.write_corpus(base / "layer0", "layer0", "Layer 0 reference text (development index)",
                        "Quran (Tanzil), Tafsir al-Muyassar and Tafsir Ibn Kathir (candidate licences), Sahih "
                        "al-Bukhari and Sahih Muslim cluster primaries, and from Quranpedia (candidate) English "
                        "translations of the meanings and the tafsir books of the reference package's rule "
                        "(in_rule and borderline), and the team's Arabic competition package. Draft, not reviewed, "
                        "not for children.",
                        layer0)

    _log("building corpus/wave1 (Wave 1 release candidate: 5 prophets + selected hadith, no tafsir)")
    wave_segments = {item.id for item in segments
                     if any((item.surah, ayah) in prophets_by_ayah for ayah in range(item.first, item.last + 1))}
    chosen = {entry["cluster_primary"] for entry in selection["hadith"] if not entry["needs_check"]}
    topics = {entry["cluster_primary"]: entry["topic"] for entry in selection["hadith"] if not entry["needs_check"]}
    wave1 = []
    for doc in built_quran.documents:
        if doc["contentType"] == "quran" and doc["id"] in wave_segments:
            labels = [topics_by_ayah[key] for unit in doc["units"]
                      if (key := tuple(int(x) for x in unit["reference"].split(":")[1:])) in topics_by_ayah]
            wave1.append({**doc, "topics": list(dict.fromkeys(labels))})
    wave1 += [{**doc, "topics": [topics[doc["units"][0]["reference"]]]}
              for doc in built_hadith.documents if doc["units"][0]["reference"] in chosen]
    wave1 += competition_docs
    ingest.write_corpus(base / "wave1", "wave1", "Wave 1 candidate corpus",
                        "Quran segments for Adam, Nuh, Ibrahim, Yusuf and Musa, the checked hadith selection and the "
                        "team's Arabic competition package. Draft, not reviewed, not for children.", wave1)

    _log("validating and chunking with the existing pipeline (chunk-v2)")
    summary = {
        "chunker": CHUNKER, "normalizer": normalize.VERSION,
        "segments": {"count": len(segments), "max_ayat": max(s.last - s.first + 1 for s in segments),
                     "source": "Tanzil rukus split to 1-8 ayat and <= 180 words"},
        "aliases": alias_summary, "source_maps": maps_summary,
        "clusters": {"records": len(records), "clusters": len({i["cluster_id"] for i in clusters.values()}),
                     "size_distribution": dict(sorted(sizes.items()))},
        "nawawi_links": {status: sum(1 for link in links.values() if link["status"] == status)
                         for status in ("linked", "needs_check", "not_linked")},
        "selection": selection_summary,
        "skipped": {**built_quran.skipped, **built_hadith.skipped, **built_ibn_kathir.skipped,
                    **quranpedia_skipped},
        "ibn_kathir_documents": len(built_ibn_kathir.documents),
        "quranpedia_documents": quranpedia_docs,
        "competition_documents": dict(Counter(doc["contentType"] for doc in competition_docs)),
        "long_hadith_with_parts": sum(1 for doc in built_hadith.documents if doc["units"][0]["parts"]),
        "wave1_prophet_segments": len(wave_segments), "wave1_hadith": len(chosen),
        "generated_questions": sum(len(doc["generatedQuestions"]) for doc in wave1),
    }
    summary["layer0"] = _validate(base / "layer0")
    summary["wave1"] = _validate(base / "wave1")
    reports = base / "reports"
    (reports / "ingest_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8", newline="\n")
    (reports / "nawawi_links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
