"""Look up the knowledge graph (kg-v2) for review: what is linked to a prophet, an ayah, a hadith or a tafsir section.

    python scripts/graph_query.py prophet yusuf
    python scripts/graph_query.py ayah 12:4
    python scripts/graph_query.py hadith bukhari:3395
    python scripts/graph_query.py section ibn-kathir:12:4-6
    python scripts/graph_query.py section tabari:12:4          a Quranpedia book's section (<book>:<surah>:<ayat>)
    python scripts/graph_query.py ... --text      also print the text of each linked item (first 160 characters)

Reads corpus/graph/ (build it with scripts/build_graph.py) and, with --text, the local canonical files. The text is
printed to your terminal only; never paste it into tickets or chat logs (the sources are not cleared).
"""
from collections import defaultdict
import json
import sys

import _common  # noqa: F401
from _common import ROOT
from companion_api.corpusprep import ibn_kathir, quranpedia

CORPUS = ROOT / "corpus"
GRAPH = CORPUS / "graph"


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _texts() -> dict[str, str]:
    canonical = CORPUS / "canonical"
    texts = {f"quran:{r['surah']}:{r['ayah']}": r["text_uthmani"] for r in _jsonl(canonical / "quran/ayat.jsonl")}
    for path in sorted((canonical / "hadith").glob("*.jsonl")):
        texts.update({f"{r['collection']}:{r['number']}": r.get("arabic_text") or "" for r in _jsonl(path)})
    tafsir = canonical / "tafsir/ibn-kathir.jsonl"
    if tafsir.is_file():
        texts.update({r["section_id"]: ibn_kathir.display_text(r["text"]) for r in _jsonl(tafsir)})
    for book in quranpedia.TAFSIR_BOOKS:  # kg-v2: a section is a book's passages on one range, in order
        path = canonical / book.canonical_name
        if path.is_file():
            for record in _jsonl(path):
                if quranpedia.usable_record(record):
                    texts[record["section_id"]] = (texts.get(record["section_id"], "") + " " + record["text"]).strip()
    return texts


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    show_text = "--text" in args
    args = [arg for arg in args if arg != "--text"]
    if len(args) != 2 or args[0] not in ("prophet", "ayah", "hadith", "section"):
        print(__doc__)
        return 2
    if not (GRAPH / "edges.jsonl").is_file():
        print("no graph yet: run python scripts/build_graph.py", file=sys.stderr)
        return 1
    kind, value = args
    node = {"prophet": f"prophet:{value}", "ayah": f"quran:{value}", "hadith": value, "section": value}[kind]
    edges = _jsonl(GRAPH / "edges.jsonl")
    out, into = defaultdict(list), defaultdict(list)
    for edge in edges:
        if edge["source"] == node:
            out[edge["type"]].append(edge)
        if edge["target"] == node:
            into[edge["type"]].append(edge)
    if not out and not into:
        print(f"{node}: not in the graph")
        return 1
    texts = _texts() if show_text else {}
    attributes = next((row for row in _jsonl(GRAPH / "nodes.jsonl") if row["id"] == node), {})
    print(node + ("  [" + ", ".join(f"{k}={v}" for k, v in attributes.items() if k not in ("id", "type")) + "]"
                  if attributes else ""))
    for direction, groups, key in (("->", out, "target"), ("<-", into, "source")):
        for edge_type, items in sorted(groups.items()):
            print(f"  {direction} {edge_type} ({len(items)})")
            for edge in items[:40]:
                detail = ", ".join(f"{k}={v}" for k, v in edge.items() if k not in ("type", "source", "target"))
                print(f"     {edge[key]}  [{detail}]")
                if show_text and edge[key] in texts:
                    print(f"        {' '.join(texts[edge[key]].split())[:160]}")
            if len(items) > 40:
                print(f"     ... {len(items) - 40} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
