"""Fetch every registered source, verify it by sha256 and build corpus/canonical/.

    python scripts/fetch_sources.py            verify cached files (download missing ones) and build
    python scripts/fetch_sources.py --record   first run: record sha256 + retrieved_at for new sources
    python scripts/fetch_sources.py --refresh  re-download everything and compare with the registry

Re-runnable: files already in corpus/raw/ that match the registry are not downloaded again.
Exit status: 0 ok, 1 verification failed, 2 a source changed or is not recorded.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from companion_api.corpusprep import build, fetch, registry as registry_module  # noqa: E402
from companion_api.corpusprep.quran import QuranError  # noqa: E402
from companion_api.corpusprep.quranpedia import QuranpediaError  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=ROOT / "corpus/sources/registry.yaml")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "corpus/raw")
    parser.add_argument("--canonical-dir", type=Path, default=ROOT / "corpus/canonical")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "corpus/reports")
    parser.add_argument("--record", action="store_true", help="record sha256 for sources that have none yet")
    parser.add_argument("--refresh", action="store_true", help="download again even when a verified copy exists")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per download")
    parser.add_argument("--no-build", action="store_true", help="only fetch and verify")
    args = parser.parse_args(argv)

    try:
        registry = registry_module.load(args.registry)
    except registry_module.RegistryError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"fetching {len(registry.sources)} sources", file=sys.stderr)
    changed, recorded = [], False
    for source in registry.sources:
        acquisition = source.get("acquisition", "download")
        if acquisition != "download":
            # Crawled or manually downloaded: never fetched from `url` here, only verified when present.
            target = fetch.raw_path(args.raw_dir, source)
            if not target.is_file() or source["sha256"] is None:
                print(f"  skipped  {source['source_id']}  ({acquisition}: not present or not recorded yet)",
                      file=sys.stderr)
                continue
            if fetch.digest(target) != source["sha256"]:
                changed.append(f"{source['source_id']}: local {acquisition} file does not match the registry")
                continue
            print(f"  cached   {source['source_id']}  {source['sha256']}", file=sys.stderr)
            continue
        try:
            _, action = fetch.ensure(source, args.raw_dir, record=args.record, refresh=args.refresh,
                                     timeout=args.timeout)
        except fetch.SourceChanged as error:
            changed.append(str(error))
            continue
        except Exception as error:  # network or HTTP failure: name the source, keep going, fail at the end
            changed.append(f"{source['source_id']}: download failed ({type(error).__name__}: {error})")
            continue
        recorded |= action == "recorded"
        print(f"  {action:<8} {source['source_id']}  {source['sha256']}", file=sys.stderr)
    if recorded:
        registry_module.save(registry)
        print("registry updated with new sha256 values; review and commit it", file=sys.stderr)
    if changed:
        print("\nFAILED:\n  " + "\n  ".join(changed), file=sys.stderr)
        return 2
    if args.no_build:
        return 0

    try:
        files, quran_info, tafsir_info = build.build_quran(registry, args.raw_dir, args.canonical_dir,
                                                           reports=args.reports_dir)
        # test/corpus-tasks: Quranpedia English translations and tafsir books (candidate sources).
        quranpedia_files, quranpedia_info = build.build_quranpedia(registry, args.raw_dir, args.canonical_dir)
    except (QuranError, QuranpediaError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    files.update(quranpedia_files)
    hadith_files, hadith_info, discrepancies = build.build_hadith(registry, args.raw_dir, args.canonical_dir)
    files.update(hadith_files)
    manifest = build.write_manifest(args.canonical_dir, registry, files, quran_info, tafsir_info, hadith_info,
                                    quranpedia_info)
    report = build.write_report(args.reports_dir, registry, hadith_info, discrepancies)
    build.write_mapping(args.reports_dir, registry, args.raw_dir, args.canonical_dir)

    print(f"\nquran: {quran_info['surahs']} surahs, {quran_info['ayat']} ayat "
          f"(per-surah counts match {', '.join(quran_info['per_surah_checked_against'])})")
    print(f"tafsir alquran-cloud-muyassar: {tafsir_info['records']} records, "
          f"{tafsir_info['missing_ayat']} ayat missing, {tafsir_info['empty']} empty")
    if "ibn_kathir" in tafsir_info:
        info = tafsir_info["ibn_kathir"]
        print(f"tafsir ibn-kathir: {info['ayat']} ayat in {info['sections']} sections, {info['missing_ayat']} missing, "
              f"{info['words']} words, {info['editor_notes']} editor notes")
    if "kfc_comparison" in quran_info:
        for name in ("uthmani", "simple"):
            item = quran_info["kfc_comparison"][name]
            print(f"quran {name} vs {item['reference']}: " + ", ".join(
                f"{status} {count}" for status, count in item["statuses"].items()))
        print(f"  details: {args.reports_dir / 'quran_text_comparison.md'}")
    for source_id, info in quranpedia_info.get("translations", {}).items():
        print(f"translation {source_id}: {info['ayat']} ayat, {info['missing_ayat']} missing, {info['words']} words, "
              f"{info['with_footnotes']} with footnotes, {len(info['label_mismatch'])} labelled for another ayah")
    for source_id, info in quranpedia_info.get("tafsir", {}).items():
        print(f"tafsir {source_id} ({info['package_rule']}{', layer 0' if info['layer0'] else ''}): "
              f"{info['usable_records']} passages in {info['sections']} sections, {info['ayat_covered']} ayat, "
              f"{info['words']} words, flags {info['flags']}")
    for info in hadith_info:
        print(f"hadith {info['collection']}: {info['records']} records, {info['primary_empty_text']} empty in "
              f"primary, statuses {info['statuses']}, eligible {info['eligible']}")
    print(f"manifest: {manifest.relative_to(ROOT) if manifest.is_relative_to(ROOT) else manifest}")
    print(f"report:   {report.relative_to(ROOT) if report.is_relative_to(ROOT) else report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
