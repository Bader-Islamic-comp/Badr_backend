"""Write corpus/reports/hadith_dorar_check.csv: a seeded, stratified sample of Bukhari and Muslim records for
people to verify by hand on dorar.net/hadith or an approved Shamela edition (reference package, hadith row).

    python scripts/sample_hadith_check.py [--seed 20261002] [--size 100]

Numbers only, never hadith text. Strata: collection x cross-check status. The agreeing statuses are sampled
less than their share and the unresolved ones (`text_differs`, `not_matched`) more, because those are where a
person's check matters most; a stratum smaller than its quota is taken whole and the rest goes to `match`.
The same seed and the same canonical files give the same sample. The verification columns are left empty for
the person who checks: the Dorar or Shamela reference they found, whether the text agrees, their name, the date.

Numbers are as in the primary edition (`numbering_system`, sunnah.com style); Dorar and Shamela editions may
number differently, Muslim especially (Abdul-Baqi numbering). When a number does not lead to the record, find
it by a distinctive phrase of its text in corpus/canonical/hadith/<collection>.jsonl (outside git).
"""
import argparse
import csv
import io
import json
from pathlib import Path
import random
import sys

import _common  # noqa: F401
from _common import ROOT

CANONICAL = ROOT / "corpus/canonical/hadith"
LAYER0 = ROOT / "corpus/layer0/documents"
OUT = ROOT / "corpus/reports/hadith_dorar_check.csv"
COLLECTIONS = ("bukhari", "muslim")
# Per collection, out of 50.
QUOTA = {"match": 20, "contained_in_secondary": 10, "text_differs": 10, "not_matched": 10}
COLUMNS = ("sample", "collection", "number", "numbering_system", "ref", "document_id", "crosscheck_status",
           "eligible", "second_source", "second_source_number", "dorar_or_shamela_reference", "text_agrees",
           "checked_by", "checked_on", "notes")


def _number_key(number: str):
    head, _, tail = number.partition(".")
    return int(head), int(tail or 0)


def document_id(collection: str, number: str) -> str:
    """The layer-0 document id of a record (scripts/build_corpus.py), whether or not it was built."""
    return f"hadith-{collection}-{number.replace('.', '-')}"


def sample(rows_by_collection: dict[str, list[dict]], seed: int, size: int) -> list[dict]:
    rng = random.Random(seed)
    per_collection = size // len(rows_by_collection)
    chosen = []
    for collection in sorted(rows_by_collection):
        strata: dict[str, list[dict]] = {}
        for row in rows_by_collection[collection]:
            strata.setdefault(row["crosscheck_status"], []).append(row)
        scale = per_collection / sum(QUOTA.values())
        quota = {status: round(count * scale) for status, count in QUOTA.items()}
        for status in ("not_matched", "text_differs", "contained_in_secondary"):
            quota[status] = min(quota[status], len(strata.get(status, [])))
        quota["match"] += per_collection - sum(quota.values())  # what small strata could not fill
        for status in QUOTA:
            pool = sorted(strata.get(status, []), key=lambda row: _number_key(row["number"]))
            picked = rng.sample(pool, min(quota[status], len(pool)))
            chosen += sorted(picked, key=lambda row: _number_key(row["number"]))
    return chosen


def render(rows: list[dict], layer0: set[str] | None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for position, row in enumerate(rows, 1):
        doc = document_id(row["collection"], row["number"])
        other = row.get("crosscheck") or {}
        writer.writerow([position, row["collection"], row["number"], row["numbering_system"],
                         f"{row['collection']}:{row['number']}",
                         doc if layer0 is None or doc in layer0 else "", row["crosscheck_status"],
                         "yes" if row["eligible"] else "no", other.get("source_id", ""), other.get("number", ""),
                         "", "", "", "", ""])
    return buffer.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    rows = {}
    for collection in COLLECTIONS:
        path = CANONICAL / f"{collection}.jsonl"
        if not path.is_file():
            print(f"{path} is missing: run python scripts/fetch_sources.py first", file=sys.stderr)
            return 1
        rows[collection] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    layer0 = {path.stem for path in LAYER0.glob("hadith-*.json")} if LAYER0.is_dir() else None
    picked = sample(rows, args.seed, args.size)
    args.out.write_text(render(picked, layer0), encoding="utf-8", newline="\n")
    counts: dict[tuple, int] = {}
    for row in picked:
        counts[(row["collection"], row["crosscheck_status"])] = counts.get((row["collection"],
                                                                             row["crosscheck_status"]), 0) + 1
    print(f"wrote {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}: {len(picked)} "
          f"records, seed {args.seed}" + ("" if layer0 is not None else " (corpus/layer0 not built: document_id "
                                          "is the id the record would have)"))
    for key in sorted(counts):
        print(f"  {key[0]:<8} {key[1]:<24} {counts[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
