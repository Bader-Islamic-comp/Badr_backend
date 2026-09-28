# Corpus pipeline setup

How to rebuild the religious corpus, its releases, the retrieval evaluation and the governance
checks from a fresh clone. For running the API server itself, see [`README.md`](../README.md#setup-and-run-powershell).

Every command below was run on 2026-09-28 on Linux (Python 3.11.8, 12-core i5-10500H, no GPU,
15 GB RAM) from a fresh `git clone` of branch `corpus-tasks` with a new virtual environment,
except the ones marked **(main copy)**, which ran in the working repository the same day because
they need several GB of models and hours of CPU. Run everything from the repository root.

## 1. Requirements

| | minimum | notes |
| --- | --- | --- |
| Python | 3.10+ | tested with 3.11.8 |
| Disk, core | ~0.5 GB | venv ~0.2 GB; `corpus/raw` 36 MB, `corpus/canonical` 33 MB, `corpus/layer0` 75 MB, `corpus/wave1` 1 MB, releases a few MB each |
| Disk, embedding evaluation | +~8 GB | Hugging Face models: BGE-M3 2.2 GB, multilingual-e5-large 2.2 GB, bge-reranker-v2-m3 2.2 GB; Ollama `qwen3-embedding:0.6b` 0.64 GB; PyTorch wheel on top |
| Memory | 1 GB core; **~4 GB free** per evaluation process | the corpus build peaks at ~0.5 GB; one float32 embedder or the reranker takes 3.3–3.5 GB |
| Network | only for `fetch_sources.py` and model downloads | nothing else calls out |
| Ollama | optional | only for `--ollama qwen3-embedding:0.6b` in the evaluation; tested with 0.22.1 |

## 2. Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]' -c constraints-dev.txt
.venv/bin/python -m pytest -q          # 634 passed, no corpus data needed
```

The examples below use `.venv/bin/python`; on Windows use `.venv/Scripts/python.exe`.

### Environment variables

`.env.example` lists them; nothing loads it automatically. The corpus scripts need none. The ones
that matter here:

| variable | used by | default |
| --- | --- | --- |
| `COMPANION_RAG_RELEASE` | the server: which release directory to serve (or `releases/current_release`) | empty |
| `COMPANION_EMBEDDING_MODEL` | the server and `due_for_review.py` | `qwen3-embedding:0.6b` |
| `COMPANION_EMBEDDING_BASE_URL` | the server | the LLM base URL (local Ollama) |
| `EVAL_DTYPE` | `evaluation/models.py`: `float32` (default) or `bfloat16` (halves memory, much slower on CPUs without bf16) | `float32` |
| `SUNNAH_API_KEY` | **not read by any script yet.** sunnah.com needs a key; Riyad as-Salihin and al-Adab al-Mufrad are single-source until one exists (`doc/decisions/01-licensing.md`) | — |

Never commit real keys or tokens.

## 3. Fetch the sources and build the corpus

The sacred and third-party text is **not in git** (every licence is `pending_legal`). Git keeps the
sha256 of every file in `corpus/sources/registry.yaml` and `corpus/canonical/manifest.json`, so the
download is verified byte for byte.

```bash
.venv/bin/python scripts/fetch_sources.py     # ~16 s: downloads corpus/raw, verifies sha256, builds corpus/canonical
.venv/bin/python scripts/build_corpus.py      # ~30 s: builds corpus/layer0 and corpus/wave1, validates and chunks them
```

`fetch_sources.py` exits 1 if a verification fails and 2 if a source changed upstream (never
silently accepted); `--refresh` re-downloads everything to check the sources, `--record` is only for
registering a new source. After a clean build, `git status` shows only the timing fields in
`corpus/reports/ingest_summary.json`; the canonical manifest is identical.

## 4. Releases and rollback

Releases are immutable, read-only directories under `releases/` (not in git) with an audit log.

```bash
.venv/bin/python scripts/build_release.py corpus/wave1 --release-id wave1-dev-1 \
    --actor "Momen Alhamza" --embedding-model hashing --promote
.venv/bin/python scripts/rollback.py --status
.venv/bin/python scripts/rollback.py --actor "Momen Alhamza" --reason "why"            # back to the previous release
.venv/bin/python scripts/rollback.py --promote wave1-dev-1 --actor "Momen Alhamza" --reason "why"
.venv/bin/python scripts/scan_index.py releases/current_release                       # no child content in the index
```

`--embedding-model hashing` needs no model server (development only). Without it the release is
embedded with `qwen3-embedding:0.6b` through local Ollama. Add `--quarantine` to a rollback to
mark the current release as never servable again. The `published` channel refuses any release
whose sources are not all `cleared`, which today means every release.

## 5. Retrieval evaluation and dashboard

```bash
.venv/bin/python scripts/eval_retrieval.py                 # bm25, bm25+q, hybrid:hashing — seconds
# then open reports/retrieval/index.html in a browser (static page, no network)
```

Each run appends to `reports/retrieval/history.jsonl` and regenerates `reports/retrieval/index.html`
(`--no-dashboard` skips the page). All questions are synthetic and pending review.

### With the real embedders (main copy)

Extra packages (the versions these runs used; not pinned in `pyproject.toml`): `torch` 2.12.0,
`transformers` 4.41.2, `huggingface_hub` 0.36.2.

```bash
ollama pull qwen3-embedding:0.6b
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('BAAI/bge-m3', allow_patterns=['*.json', 'sentencepiece.bpe.model', 'pytorch_model.bin'])
for repo in ('intfloat/multilingual-e5-large', 'BAAI/bge-reranker-v2-m3'):
    snapshot_download(repo, allow_patterns=['*.json', '*.safetensors', 'sentencepiece.bpe.model'])"

.venv/bin/python scripts/eval_retrieval.py --ollama qwen3-embedding:0.6b --hf bge-m3 --hf multilingual-e5-large
.venv/bin/python scripts/eval_retrieval.py --ollama qwen3-embedding:0.6b --hf bge-m3 --hf multilingual-e5-large \
    --rerank --rerank-k 10 --rerank-on hybrid:bge-m3 --rerank-on hybrid:bge-m3+q --rerank-on hybrid:qwen3-embedding:0.6b
```

Measured time on this CPU, first run: each Hugging Face embedder ~25–30 min for 1,658 entries plus
461 questions; the reranker ~1 pair/s, so the command above (~7,500 pairs) took ~1.5 h. Vectors and
rerank scores are cached in `reports/retrieval/cache/` (not in git) by model and text digest; a
repeat run with the same corpus takes a minute. Results and caveats: [ADR 0005](adr-0005-embedding-selection.md).

## 6. Governance tools

```bash
.venv/bin/python scripts/review.py list                   # age-band drafts by status
.venv/bin/python scripts/apply_decisions.py --check       # validate doc/decisions/decisions.yaml without applying
.venv/bin/python scripts/apply_decisions.py               # apply signed human decisions (the only way to approve)
.venv/bin/python scripts/verify_audit.py                  # verify both hash-chained audit logs
.venv/bin/python scripts/due_for_review.py releases/current_release
.venv/bin/python scripts/age_band.py check                # validate the age-band drafts
.venv/bin/python scripts/progress_score.py                # X / 100, automated and human parts, per task
.venv/bin/python scripts/check_progress.py                # doc/done.md against evidence, architecture, plan and tasks
.venv/bin/python scripts/build_decision_packages.py       # regenerate doc/decisions/*.md (04 stays out of git)
.venv/bin/python scripts/rights_table.py                  # regenerate doc/governance/rights-clearance.md
.venv/bin/python scripts/build_eval.py                    # regenerate corpus/eval/*.jsonl from the *_source.yaml files
```

The last three regenerate files and accept no `--help`; their output is deterministic.
`progress_score.py --write` also updates the progress section of `doc/done.md` and
`reports/progress/score.json`. Approvals never come from a script or an agent: only a signed entry in
`doc/decisions/decisions.yaml` applied by `apply_decisions.py` (see [`doc/decisions/README.md`](decisions/README.md)).

## 7. Tests

```bash
.venv/bin/python -m pytest -q                              # whole suite, ~6 s
.venv/bin/python -m pytest -q tests/test_no_child_content.py
```

## 8. Common problems

| symptom | cause and fix |
| --- | --- |
| `fetch_sources.py` exits 2 | a source changed upstream or is not recorded. Do not re-record blindly: compare, then decide (source policy). |
| a download fails once | network errors are retried 3 times; run the command again. |
| evaluation killed (`Killed`, exit 137) | out of memory. Close other programs; run one heavy command at a time. Finished models stay cached, so re-running continues where it stopped. |
| reranker seems stuck | it is slow on CPU (~1 pair/s at 384 tokens). Use `--rerank-k 10` and `--rerank-on` for a few methods; the full default (top 30 on every method) is ~7 h here. |
| a watch or tool call times out during the evaluation | run it in the background and read its log (`... > eval.log 2>&1 &`); do not start a second copy of the same run. |
| `OSError`/`AttributeError` loading BGE-M3 | the weights file was not downloaded: fetch `pytorch_model.bin` as above. |
| Ollama returns NaN or HTTP 500 for `bge-m3` | known on this text; BGE-M3 is evaluated through Hugging Face (`--hf bge-m3`) instead. |
| disk full | the models need ~8 GB; nothing outside the repository is deleted by these scripts. |
