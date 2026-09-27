"""Retrieval evaluation and offline dashboard (tasks 11 and 14).

    python scripts/eval_retrieval.py [--corpus corpus/wave1] [--ollama nomic-embed-text] [--no-dashboard]

Runs every available method on corpus/eval/gold.jsonl (310 synthetic questions) and the abstain
categories of harmful.jsonl, appends one run to reports/retrieval/history.jsonl and regenerates the
static page reports/retrieval/index.html (no network, no external scripts).
Methods: bm25; dense and hybrid RRF (k=60) for `hashing` and each --ollama model on a private endpoint.
Models that cannot run here are recorded as blocked with the reason.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import html
import json
from pathlib import Path
import shutil
import sys

import _common  # noqa: F401
from _common import ROOT
from companion_api.evaluation import retrieval
from companion_api.governance.releases import git_commit
from companion_api.rag import embeddings
from companion_api.rag.chunking import chunk_documents, embedding_text
from companion_api.rag.corpus import load_corpus

OUT = ROOT / "reports/retrieval"
CACHE = OUT / "cache"
# Known embedders on an OpenAI-compatible (Ollama) endpoint: dimensions and the prefixes the model expects.
OLLAMA_MODELS = {
    "nomic-embed-text": {"dims": 768, "doc": "search_document: ", "query": "search_query: ", "candidate": False},
    "qwen3-embedding:0.6b": {"dims": 1024, "doc": "", "query": None, "candidate": True},
}
# Hugging Face models: repo and encoder options. BGE-M3 runs here because Ollama's build returns NaN on this text.
HF_MODELS = {"multilingual-e5-large": ("intfloat/multilingual-e5-large", {}),
             "bge-m3": ("BAAI/bge-m3", {"doc_prefix": "", "query_prefix": "", "pooling": "cls"})}
RERANKER = "BAAI/bge-reranker-v2-m3"
REQUESTED = ("bge-m3", "multilingual-e5-large", "qwen3-embedding:0.6b", "bge-reranker-v2-m3")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _blocked(ran: set[str]) -> dict[str, str]:
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    return {name: f"not run in this invocation ({free_gb:.1f} GB free on disk); see the flags in --help"
            for name in REQUESTED if name not in ran}


def _embedder(name: str, base_url: str):
    if name in HF_MODELS:  # checked first: bge-m3 is served from Hugging Face
        from companion_api.evaluation.models import HFEmbedder
        repo, options = HF_MODELS[name]
        return HFEmbedder(repo, **options), True, (lambda e: e.embed_query)
    spec = OLLAMA_MODELS[name]
    embedder = embeddings.OpenAICompatibleEmbedder(
        base_url, name, dimensions=spec["dims"],
        query_instruction=embeddings.QWEN_QUERY_INSTRUCTION if spec["query"] is None else "", batch_size=32)
    prefix = spec["query"] or ""
    return embedder, spec["candidate"], (lambda e: (lambda q: e.embed_query(prefix + q)))


MAX_EMBED_WORDS = 350  # long narrations exceed model context; their verbatim part-chunks carry the rest


def _clip(text: str) -> str:
    words = text.split()
    return text if len(words) <= MAX_EMBED_WORDS else " ".join(words[:MAX_EMBED_WORDS])


def _robust(embedder):
    """Embeds in batches of 8, halving a batch the server refuses, with progress."""
    def embed(texts):
        out, step = [], 8
        for start in range(0, len(texts), step):
            out += _batch(embedder, texts[start:start + step])
            if start % 200 == 0:
                print(f"    ... embedded {start}/{len(texts)}", file=sys.stderr, flush=True)
        return out
    return embed


def _batch(embedder, texts):
    try:
        return embedder.embed_documents(texts)
    except embeddings.EmbeddingError:
        if len(texts) == 1:
            raise
        middle = len(texts) // 2
        return _batch(embedder, texts[:middle]) + _batch(embedder, texts[middle:])


def build_methods(chunks, models: list[str], base_url: str, reranker=None, questions: list[str] = ()):
    parents = {chunk.id: chunk for chunk in chunks if not chunk.is_child}
    plain, with_q = retrieval.entries(chunks, with_questions=False), retrieval.entries(chunks, with_questions=True)
    rerank = None
    if reranker is not None:
        texts = {pid: embedding_text(chunk) for pid, chunk in parents.items()}
        rerank = lambda question, ids: reranker.score(question, [texts[i] for i in ids])
    methods = []
    bm25 = {False: retrieval.bm25_index(plain), True: retrieval.bm25_index(with_q)}
    items = {False: plain, True: with_q}
    for q in (False, True):
        suffix = "+q" if q else ""
        methods.append((retrieval.Method(f"bm25{suffix}", items[q], bm25=bm25[q]), {"candidate": True}))
        if rerank:
            methods.append((retrieval.Method(f"bm25{suffix}+rerank", items[q], bm25=bm25[q], rerank=rerank),
                            {"candidate": True}))
    hashing = embeddings.HashingEmbedder()
    hv = hashing.embed_documents([item.text for item in plain])
    methods.append((retrieval.Method("hybrid:hashing", plain, bm25=bm25[False], vectors=hv,
                                     embed_query=hashing.embed_query), {"candidate": False}))
    ran = set()
    for name in models:
        embedder, candidate, query_fn = _embedder(name, base_url)
        print(f"embedding {len(with_q)} entries with {name} (cached after the first run)", file=sys.stderr, flush=True)
        prefix = OLLAMA_MODELS.get(name, {}).get("doc", "")
        vectors_q = retrieval.cached_vectors(CACHE, name.replace(":", "_").replace("/", "_"),
                                             [prefix + _clip(item.text) for item in with_q], _robust(embedder))
        vectors = {True: vectors_q, False: vectors_q[:len(plain)]}  # plain entries are the leading items
        embed_query = query_fn(embedder)
        print(f"embedding {len(questions)} questions with {name}", file=sys.stderr, flush=True)
        cached = retrieval.cached_vectors(CACHE, "q-" + name.replace(":", "_").replace("/", "_"),
                                          list(questions), lambda qs: [embed_query(q) for q in qs])
        table = dict(zip(questions, cached))
        query = (lambda q, table=table, fallback=embed_query: table.get(q) or fallback(q))
        # Free the model before loading the next one: this machine has little memory to spare.
        close = getattr(embedder, "close", None)
        if close:
            close()
        del embedder
        import gc
        gc.collect()
        for q in (False, True):
            suffix = "+q" if q else ""
            methods.append((retrieval.Method(f"dense:{name}{suffix}", items[q], vectors=vectors[q],
                                             embed_query=query), {"candidate": candidate}))
            methods.append((retrieval.Method(f"hybrid:{name}{suffix}", items[q], bm25=bm25[q], vectors=vectors[q],
                                             embed_query=query), {"candidate": candidate}))
            if rerank:
                methods.append((retrieval.Method(f"hybrid:{name}{suffix}+rerank", items[q], bm25=bm25[q],
                                                 vectors=vectors[q], embed_query=query, rerank=rerank),
                                {"candidate": candidate}))
        ran.add(name)
    if reranker is not None:
        ran.add("bge-reranker-v2-m3")
    return methods, ran


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus/wave1")
    parser.add_argument("--ollama", action="append", default=[], choices=sorted(OLLAMA_MODELS))
    parser.add_argument("--hf", action="append", default=[], choices=sorted(HF_MODELS))
    parser.add_argument("--rerank", action="store_true", help=f"also rerank with {RERANKER} (cross-encoder)")
    parser.add_argument("--base-url", default=embeddings.DEFAULT_BASE_URL)
    parser.add_argument("--no-dashboard", action="store_true")
    args = parser.parse_args(argv)
    corpus, report = load_corpus(args.corpus)
    if not report.ok:
        print(f"{args.corpus} does not validate", file=sys.stderr)
        return 1
    chunks = chunk_documents(corpus.documents)
    gold = _jsonl(ROOT / "corpus/eval/gold.jsonl")
    harmful = _jsonl(ROOT / "corpus/eval/harmful.jsonl")
    questions = [item["question"] for item in gold + harmful]
    reranker = None
    if args.rerank:
        from companion_api.evaluation.models import LazyReranker
        reranker = LazyReranker(RERANKER, CACHE / "rerank-scores.json")  # loads after the embedders are freed
    methods, ran = build_methods(chunks, args.ollama + args.hf, args.base_url, reranker, questions)
    results, worst = {}, {}
    for method, info in methods:
        print(f"evaluating {method.name}", file=sys.stderr, flush=True)
        result = retrieval.evaluate(method, gold, harmful)
        if reranker is not None:
            reranker.save()
        per_question = result.pop("per_question")
        results[method.name] = {**result, "candidate": info["candidate"]}
        worst[method.name] = sorted(per_question, key=lambda r: (r["rank"] is not None, -(r["rank"] or 0)))[:20]
    best = max(results, key=lambda name: (results[name]["overall"]["mrr"], name))
    run = {
        "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "git_commit": git_commit(ROOT),
        "corpus": corpus.id, "chunks": len(chunks),
        "corpus_digest": sha256("\n".join(c.id + c.checksum for c in chunks).encode()).hexdigest()[:16],
        "gold": len(gold), "gold_digest": sha256((ROOT / "corpus/eval/gold.jsonl").read_bytes()).hexdigest()[:16],
        "abstain_negatives": sum(i["category"] in retrieval.ABSTAIN_CATEGORIES for i in harmful),
        "methods": results, "best_by_mrr": best, "worst_20_best_method": worst[best],
        "blocked": _blocked(ran), "synthetic_questions": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run, ensure_ascii=False) + "\n")
    if not args.no_dashboard:
        history = _jsonl(OUT / "history.jsonl")
        questions = {item["id"]: item for item in gold}
        (OUT / "index.html").write_text(dashboard(history, questions), encoding="utf-8")
    for name, result in results.items():
        o, a = result["overall"], result["abstention"]
        print(f"{name:<28} R@1 {o['r1']:.3f}  R@5 {o['r5']:.3f}  R@10 {o['r10']:.3f}  MRR {o['mrr']:.3f}  "
              f"nDCG@10 {o['ndcg10']:.3f}  abstain(2-fold) {a.get('balanced_accuracy_2fold', 0):.3f}")
    print(f"best by MRR: {best}; blocked: {', '.join(run['blocked'])}")
    return 0


# --- dashboard ------------------------------------------------------------------------------------------

STYLE = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--surface-2:#f3f2ef;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#77766f;--rule:#dedcd6;--series-1:#2a78d6;--series-2:#eb6834;
--series-3:#1baf7a;--seq-lo:#cde2fb;--seq-hi:#2a78d6}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
--surface-1:#1a1a19;--surface-2:#242422;--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#9b9a92;
--rule:#383835;--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;--seq-lo:#184f95;--seq-hi:#3987e5}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#1a1a19;--surface-2:#242422;--text-primary:#fff;
--text-secondary:#c3c2b7;--text-muted:#9b9a92;--rule:#383835;--series-1:#3987e5;--series-2:#d95926;
--series-3:#199e70;--seq-lo:#184f95;--seq-hi:#3987e5}
body{margin:0;background:var(--surface-1)}
.viz-root{background:var(--surface-1);color:var(--text-primary);font:14px/1.45 system-ui,sans-serif;
padding:24px 16px;max-width:1100px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}
.muted{color:var(--text-secondary)}.note{color:var(--text-muted);font-size:13px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--rule);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--text-secondary);font-weight:600}
.tag{display:inline-block;font-size:12px;padding:1px 6px;border-radius:4px;background:var(--surface-2);
color:var(--text-secondary)}
.cell{position:relative}.cell span{position:relative}
svg{max-width:680px;display:block}svg text{fill:var(--text-secondary);font-size:12px}.legend{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0}
.key{display:inline-block;width:12px;height:3px;border-radius:2px;vertical-align:middle;margin-right:6px}
.q{white-space:normal;text-align:left;min-width:220px}
"""


def _esc(value) -> str:
    return html.escape(str(value))


def _bars(methods: dict) -> str:
    names = list(methods)
    width, row, left = 640, 28, 190
    height = row * len(names) + 30
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Recall at 5 by method">']
    scale = width - left - 60
    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        x = left + tick * scale
        parts.append(f'<line x1="{x}" x2="{x}" y1="0" y2="{height - 22}" stroke="var(--rule)" stroke-width="1"/>'
                     f'<text x="{x}" y="{height - 6}" text-anchor="middle">{tick:.2f}</text>')
    for index, name in enumerate(names):
        value = methods[name]["overall"]["r5"]
        y = index * row + 6
        w = max(value * scale, 1)
        parts.append(f'<g><title>{_esc(name)}: Recall@5 {value:.3f}</title>'
                     f'<text x="{left - 8}" y="{y + 14}" text-anchor="end">{_esc(name)}</text>'
                     f'<rect x="{left}" y="{y + 3}" width="{w:.1f}" height="16" rx="4" fill="var(--series-1)"/>'
                     f'<text x="{left + w + 6:.1f}" y="{y + 15}">{value:.3f}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def _trend(history: list[dict]) -> str:
    runs = history[-30:]
    tracked = ["bm25"]
    latest = runs[-1]["methods"]
    dense = [m for m in latest if m.startswith("dense:") and m != "dense:hashing"]
    hybrid = [m for m in latest if m.startswith("hybrid:") and m != "hybrid:hashing"]
    tracked += [max(dense, key=lambda m: latest[m]["overall"]["mrr"])] if dense else ["dense:hashing"]
    tracked += [max(hybrid, key=lambda m: latest[m]["overall"]["mrr"])] if hybrid else ["hybrid:hashing"]
    width, height, left, bottom = 640, 220, 40, 30
    span = max(len(runs) - 1, 1)
    xs = [left + i * (width - left - 20) / span for i in range(len(runs))]
    y = lambda v: 10 + (1 - v) * (height - bottom - 10)
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="MRR across runs">']
    for tick in (0, 0.5, 1.0):
        parts.append(f'<line x1="{left}" x2="{width - 20}" y1="{y(tick)}" y2="{y(tick)}" stroke="var(--rule)"/>'
                     f'<text x="{left - 6}" y="{y(tick) + 4}" text-anchor="end">{tick:.1f}</text>')
    legend = []
    for slot, name in enumerate(tracked, 1):
        points = [(x, run["methods"][name]["overall"]["mrr"]) for x, run in zip(xs, runs) if name in run["methods"]]
        if not points:
            continue
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y(v):.1f}" for i, (x, v) in enumerate(points))
        parts.append(f'<path d="{path}" fill="none" stroke="var(--series-{slot})" stroke-width="2"/>')
        for (x, v), run in zip(points, [r for r in runs if name in r["methods"]]):
            parts.append(f'<circle cx="{x:.1f}" cy="{y(v):.1f}" r="4" fill="var(--series-{slot})" '
                         f'stroke="var(--surface-1)" stroke-width="2"><title>{_esc(name)} · {_esc(run["run_at"])} · '
                         f'MRR {v:.3f}</title></circle>')
        legend.append(f'<span><span class="key" style="background:var(--series-{slot})"></span>{_esc(name)}</span>')
    parts.append("</svg>")
    return f'<div class="legend">{"".join(legend)}</div>' + "".join(parts)


def _shade(value: float) -> str:
    pct = round(max(0.0, min(1.0, value)) * 100)
    return (f' style="background:color-mix(in oklab, var(--seq-hi) {pct * 0.55:.0f}%, var(--surface-1))"')


def dashboard(history: list[dict], questions: dict) -> str:
    run = history[-1]
    methods = run["methods"]
    variants = sorted({v for m in methods.values() for v in m["by_variant"]})
    rows = []
    for name, m in methods.items():
        o, a = m["overall"], m["abstention"]
        tag = "" if m["candidate"] else ' <span class="tag">baseline, not a candidate</span>'
        rows.append(f"<tr><td>{_esc(name)}{tag}</td>" + "".join(f"<td>{o[k]:.3f}</td>" for k in
                    ("r1", "r5", "r10", "mrr", "ndcg10")) +
                    f"<td>{a.get('balanced_accuracy_2fold', 0):.3f}</td><td>{a.get('threshold_all_data', 0):.3f}</td></tr>")
    variant_rows = []
    for name, m in methods.items():
        cells = "".join(f'<td class="cell"{_shade(m["by_variant"][v]["r5"])}><span>{m["by_variant"][v]["r5"]:.3f}</span></td>'
                        if v in m["by_variant"] else "<td>—</td>" for v in variants)
        variant_rows.append(f"<tr><td>{_esc(name)}</td>{cells}</tr>")
    counts = "".join(f"<th>{_esc(v)}<br><span class=\"note\">n={methods[run['best_by_mrr']]['by_variant'][v]['n']}</span></th>"
                     for v in variants)
    worst_rows = "".join(
        f"<tr><td>{_esc(r['id'])}</td><td>{_esc(r['variant'])}</td><td>{r['rank'] or 'miss (>100)'}</td>"
        f"<td class=\"q\" dir=\"auto\">{_esc(questions.get(r['id'], {}).get('question', ''))}</td></tr>"
        for r in run["worst_20_best_method"])
    history_rows = "".join(
        f"<tr><td>{_esc(h['run_at'])}</td><td>{_esc(h['git_commit'][:12])}</td><td>{_esc(h['best_by_mrr'])}</td>"
        f"<td>{h['methods'][h['best_by_mrr']]['overall']['mrr']:.3f}</td>"
        f"<td>{h['methods'][h['best_by_mrr']]['overall']['r5']:.3f}</td><td>{len(h['methods'])}</td></tr>"
        for h in reversed(history[-30:]))
    blocked = "".join(f"<li><b>{_esc(k)}</b>: {_esc(v)}</li>" for k, v in run["blocked"].items())
    score_file = ROOT / "reports/progress/score.json"
    progress = ""
    if score_file.is_file():
        s = json.loads(score_file.read_text(encoding="utf-8"))
        progress = (f'<p><b>Corpus-task progress: {s["total"]} / 100</b> — automated {s["automated"]} '
                    f'(of {s["automated_possible"]} possible), human decisions {s["human"]} '
                    f'(of {s["human_possible"]}). Computed {_esc(s["computed_at"])} by scripts/progress_score.py.</p>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Retrieval quality</title>
<style>{STYLE}</style></head><body><main class="viz-root">
<h1>Retrieval quality</h1>
<p class="muted">Corpus <b>{_esc(run['corpus'])}</b> ({run['chunks']} chunks), {run['gold']} gold questions and
{run['abstain_negatives']} unanswerable ones. Run {_esc(run['run_at'])}, commit {_esc(run['git_commit'][:12])}.
<b>All questions are synthetic and pending approval</b>; the corpus is draft. Best by MRR:
<b>{_esc(run['best_by_mrr'])}</b>.</p>
{progress}
<h2>Metrics (latest run)</h2><div class="wrap"><table><thead><tr><th>method</th><th>R@1</th><th>R@5</th>
<th>R@10</th><th>MRR</th><th>nDCG@10</th><th>abstain acc. (2-fold)</th><th>threshold</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="note">Abstention: balanced accuracy of "answer when the top score clears the threshold", tuned on one half
of the questions and measured on the other. Hybrid methods use the dense branch's top cosine as their score.</p>
<h2>Recall@5 by method</h2>{_bars(methods)}
<h2>Recall@5 by variant</h2><div class="wrap"><table><thead><tr><th>method</th>{counts}</tr></thead>
<tbody>{''.join(variant_rows)}</tbody></table></div>
<p class="note">Cell shade grows with the value (one hue); the number is always printed.</p>
<h2>Worst 20 questions for {_esc(run['best_by_mrr'])}</h2><div class="wrap"><table><thead><tr><th>id</th>
<th>variant</th><th>rank of first expected chunk</th><th>question (synthetic)</th></tr></thead>
<tbody>{worst_rows}</tbody></table></div>
<h2>MRR across runs</h2>{_trend(history)}
<div class="wrap"><table><thead><tr><th>run</th><th>commit</th><th>best method</th><th>MRR</th><th>R@5</th>
<th>methods</th></tr></thead><tbody>{history_rows}</tbody></table></div>
<h2>Not run</h2><ul>{blocked or '<li>none</li>'}</ul>
</main></body></html>
"""


if __name__ == "__main__":
    sys.exit(main())
