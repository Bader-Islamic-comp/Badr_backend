"""Generate doc/governance/rights-clearance.md from the registry (governance task 3).

Terms are quoted verbatim from the downloaded licence files (sha256-pinned in the registry), never
retyped. "Allowed" and "Unclear" are a draft reading for the rights owner, not legal advice. The
clearance status of every source is pending_legal until Mousa al-Rashdan decides.

    python scripts/rights_table.py
"""
from pathlib import Path
import sys

import _common  # noqa: F401
from _common import REGISTRY, ROOT
from companion_api.corpusprep import registry as registry_module
from companion_api.corpusprep.fetch import raw_path

OUT = ROOT / "doc/governance/rights-clearance.md"
RAW = ROOT / "corpus/raw"

# Draft reading per dataset: (licence text source or None, allowed, unclear, open question).
READING = {
    "tanzil-quran": ("tanzil-notice",
                     "Verbatim copying and distribution in an app, with the source named and a link to tanzil.net; "
                     "the notice kept with verbatim copies and derived files.",
                     "Whether a search-only normalized copy (`text_normalized`, `rasm_map.tsv`) counts as a "
                     "prohibited change. The metadata file has no terms of its own.",
                     "Legal question 1 (corpus-tasks.md, task 3)."),
    "qurancom-api": (None, "Nothing assumed; used only to check ayah counts, no text stored.",
                     "No terms were retrieved with the API response.", "Is a structural cross-check acceptable use?"),
    "alquran-cloud": (None, "Nothing assumed.",
                      "No licence or terms page (alquran.cloud/terms returned 404); the original publisher is the "
                      "King Fahd Complex.", "Legal question 3 (corpus-tasks.md, task 3)."),
    "spa5k-tafsir-api": ("spa5k-tafsir-license",
                         "The mirror's MIT licence covers its code only: nothing is assumed for the tafsir text.",
                         "No licence or terms are stated for the digitised text, on the mirror or on the QUL "
                         "resource page (qul.tarteel.ai/resources/tafsir/22, checked 2026-10-01). The work is "
                         "classical (Ibn Kathir, d. 774 AH); the digital edition's editor (the [[notes]] cite a "
                         "critical edition) and Tarteel may hold rights in it.",
                         "May the digitised text be used for a development index and a knowledge graph, and on "
                         "what terms for a release? (test/corpus-tasks)"),
    "fawazahmed0-hadith-api": ("fawazahmed0-license",
                               "Public-domain dedication of the repository: copy, modify and distribute for any purpose.",
                               "The repository does not name the upstream of its Arabic text, so the dedication may "
                               "not cover rights held upstream.", "Is the upstream of the Arabic text known and cleared?"),
    "mhashim6-open-hadith-data": ("mhashim6-license",
                                  "Use of the database under ODbL with attribution; individual contents under DbCL.",
                                  "Share-alike: whether the canonical files or the number mapping are a derived "
                                  "database that must be released under ODbL.", "Legal question 2 (corpus-tasks.md, task 3)."),
    "ahmedbaset-hadith-json": (None, "Nothing assumed.",
                               "No licence file in the repository; the data is described as scraped from sunnah.com, "
                               "whose terms were not retrieved.", "Legal question 4 (corpus-tasks.md, task 3)."),
    # Reference package datasets (test/corpus-tasks, 2026-10-02). The organizers' permission to use the package's
    # sources is reported, not yet in writing: it is not a clearance (doc/governance/reference-package.md).
    "quranpedia-dumps": ("quranpedia-license",
                         "Use inside apps, websites and research tools, with no attribution required; republishing "
                         "the data, in full or in part, as a downloadable dataset requires crediting Quranpedia.net "
                         "with a link and the dump's version. The organizers' permission to use the reference "
                         "package's sources was reported on 2026-10-02 (written confirmation pending).",
                         "The licence keeps translations and contemporary works the property of their authors and "
                         "publishers: the three English translations (Hilali and Khan, Saheeh International, "
                         "Ruwwad), al-Mukhtasar (Arabic and English), al-Sa'di and al-Sahih al-Masbur need their "
                         "publishers' terms or the organizers' confirmation that the permission covers them. It asks "
                         "every copy to be kept current, which a sha256-pinned release does not do by itself. Word "
                         "morphology (GPL) and i'rab (MIT) fields, where a file carries them, are under their own "
                         "licences.",
                         "Does the organizers' permission cover the translations and contemporary works, and may a "
                         "release pin one reviewed dump version? (reference package, open questions Q4 and Q5)"),
    "jamharah": (None,
                 "Nothing assumed beyond the organizers' reported permission. The site's footer says the right to "
                 "benefit from the content belongs to every Muslim; no licence or API terms were found.",
                 "Whether that statement and the permission cover keeping dictionary entries in an offline, "
                 "reviewed corpus. Only the entries for the glossary's terms are kept, outside git; the glossary "
                 "records entry ids, links and short English headings only.",
                 "May the dictionary's entries and English headings be used in a release, and with what credit? "
                 "(reference package, translation and terms row)"),
    "competition-ar": (None,
                       "The team's own wording (stories, lessons, notes, prayer summaries) is the project's to use. "
                       "It cites Quranpedia and dorar.net by reference and stores no file of theirs.",
                       "The short supplication wordings follow the cited hadith as dorar.net shows them, and the "
                       "ayat quoted in its documents come from quranpedia-mushaf-hafs (a candidate source); the "
                       "package's own rights records (corpus/competition-ar/approvals.json) await sign-off.",
                       "May the package's documents, with their Quranpedia ayat and dorar.net citations, be served "
                       "to children once reviewed? (corpus/competition-ar/README.md)"),
}


def _terms(key: str | None, registry) -> str:
    if key is None:
        return "_No licence text found at the source (see the registry `notes`)._"
    if key == "tanzil-notice":
        text = (ROOT / "corpus/canonical/quran/NOTICE.txt").read_text(encoding="utf-8")
        origin = "the notice block of the downloaded Tanzil file (`corpus/canonical/quran/NOTICE.txt`)"
    else:
        path = raw_path(RAW, registry.get(key))
        text = path.read_text(encoding="utf-8")
        origin = f"`{key}` (sha256 `{registry.get(key)['sha256'][:12]}…`)"
    return f"Quoted verbatim from {origin}:\n\n```text\n{text.strip()}\n```"


def _rules(sources: list[dict]) -> list[tuple[str, int]]:
    rules: dict[str, int] = {}
    for source in sources:
        rules[source.get("package_rule") or "none"] = rules.get(source.get("package_rule") or "none", 0) + 1
    return list(rules.items())


def main() -> int:
    registry = registry_module.load(REGISTRY)
    lines = ["# Rights clearance (draft)", "",
             "Owner: Mousa al-Rashdan. Generated by `python scripts/rights_table.py` from",
             "`corpus/sources/registry.yaml`; do not edit by hand. **Clearance status of every source: "
             "`pending_legal`.** The \"allowed\" and \"unclear\" columns are a draft reading to help the legal "
             "review, not legal advice. Registry `status` (`pending_legal` / `candidate`) says only whether "
             "terms were found. The package rule is the source's standing against the challenge's reference package "
             "(`doc/governance/reference-package.md`); the organizers' permission it reflects is reported, not yet in "
             "writing, and is not a clearance.", "", "## Summary", "",
             "| source | registry status | package rule | licence | clearance |", "| --- | --- | --- | --- | --- |"]
    for source in registry.sources:
        lines.append(f"| `{source['source_id']}` | {source['status']} | {source.get('package_rule') or '—'} | "
                     f"{source['license']} | pending_legal |")
    datasets: dict[str, list[dict]] = {}
    for source in registry.sources:
        datasets.setdefault(source["dataset"], []).append(source)
    for dataset, sources in datasets.items():
        key, allowed, unclear, question = READING[dataset]
        lines += ["", f"## {dataset}", "",
                  "Sources: " + ", ".join(f"`{s['source_id']}`" for s in sources) + ".", "",
                  f"- **Licence:** {sources[0]['license']} ({sources[0]['license_url'] or 'no licence URL'})",
                  "- **Package rule:** " + ", ".join(f"{rule} ({count})" for rule, count in _rules(sources)),
                  f"- **Allowed (draft reading):** {allowed}",
                  f"- **Unclear:** {unclear}",
                  f"- **Open legal question:** {question}",
                  "- **Clearance status:** pending_legal", "", "**Terms:**", "", _terms(key, registry)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(registry.sources)} sources, {len(datasets)} datasets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
