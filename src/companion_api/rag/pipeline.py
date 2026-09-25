"""The offline data pipeline: `python -m companion_api.rag.pipeline` (doc/rag-system.md §3-§5).

    validate <corpus-dir> [--json]
    build <corpus-dir> --out <releases-root> [--release-id ID] [--embedding-model M]
          [--embedding-base-url URL] [--max-chunk-words N] [--channel development|published]
    verify <release-dir>
    import-markdown <file-or-dir> <out-dir> [--overwrite]
    stats <release-dir>

Output is counts, ids and paths, never document text: build output ends up in
terminals, CI logs and tickets, and canonical text belongs only in the release.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from . import embeddings, normalize
from .chunking import VERSION as CHUNKER_VERSION, chunk_documents, embedding_text
from .corpus import DEFAULT_MAX_CHUNK_WORDS, Document, load_corpus, parse_document, word_count
from .endpoints import EndpointError
from .markdown import MarkdownError, parse as parse_markdown
from .release import ReleaseError, load_release, write_release
from .types import RELEASE_ID, EmbedderIdentity, ReleaseManifest


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _embedding_settings(model: str | None, base_url: str | None) -> tuple[str, str]:
    """Flags first, then the same environment the server reads (§9), so both embed alike."""
    model = model or os.environ.get("COMPANION_EMBEDDING_MODEL") or embeddings.DEFAULT_EMBEDDING_MODEL
    base_url = (base_url or os.environ.get("COMPANION_EMBEDDING_BASE_URL") or os.environ.get("COMPANION_LLM_BASE_URL")
                or embeddings.DEFAULT_BASE_URL)
    return model, base_url


def _describe(identity: EmbedderIdentity) -> str:
    return f"{identity.name} / {identity.model}, {identity.dimensions} dimensions"


def review_counts(documents) -> dict:
    return {"approved": sum(document.review.status == "approved" for document in documents),
            "draft": sum(document.review.status == "draft" for document in documents),
            "synthetic": sum(document.synthetic for document in documents)}


def _validate(args) -> int:
    corpus, report = load_corpus(args.corpus_dir, max_chunk_words=args.max_chunk_words)
    documents = corpus.documents if corpus else ()
    if args.json:
        print(json.dumps({"corpus": corpus.id if corpus else None, "documents": len(documents), **report.to_json()},
                         indent=2, ensure_ascii=False))
    else:
        if corpus:
            kinds = Counter(document.kind for document in documents)
            print(f"Corpus {corpus.id or '(unnamed)'}: {len(documents)} valid documents "
                  f"({kinds['passage']} passage, {kinds['answer']} answer)")
        print(report.format())
    return 0 if report.ok else 1


def _build(args) -> int:
    corpus, report = load_corpus(args.corpus_dir, max_chunk_words=args.max_chunk_words)
    if corpus is None or not report.ok:
        print(report.format())
        return _fail("Build refused: fix the errors above, then build again.")
    if report.warnings:
        print(report.format())
    documents = corpus.documents
    if args.channel == "published":
        blocked = [document.id for document in documents if document.synthetic or document.review.status != "approved"]
        if blocked:
            return _fail(f"Build refused: the published channel needs every document approved and non-synthetic; "
                         f"{len(blocked)} of {len(documents)} are not (for example {', '.join(blocked[:3])}).")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    release_id = args.release_id or f"{corpus.id}-{now:%Y%m%d%H%M%S}"
    if not RELEASE_ID.match(release_id):
        return _fail("Build refused: release ids are 3-64 characters of a-z, 0-9, '.', '_' or '-'.")
    out = Path(args.out)
    if (out / release_id).exists():
        return _fail(f"Build refused: release {release_id} already exists in {out}. Releases are immutable; "
                     "choose another --release-id.")
    chunks = chunk_documents(documents, args.max_chunk_words)
    model, base_url = _embedding_settings(args.embedding_model, args.embedding_base_url)
    offline_hint = ("Start Ollama (or another OpenAI-compatible server on this machine) with that model available, "
                    "or build offline for development with --embedding-model hashing.")
    try:
        embedder = embeddings.embedder_for(model, base_url)
    except EndpointError as error:
        return _fail(f"Build refused: {error} {offline_hint}")
    try:
        vectors = embedder.embed_documents([embedding_text(chunk) for chunk in chunks])
    except embeddings.EmbeddingError as error:
        return _fail(f"Could not embed with {model} at {base_url}: {error}. {offline_hint}")
    finally:
        close = getattr(embedder, "close", None)
        if close:
            close()
    manifest = ReleaseManifest(
        release_id=release_id, created_at=now.isoformat(), channel=args.channel, corpus_ids=(corpus.id,),
        document_count=len(documents), chunk_count=len(chunks), embedder=embedder.identity,
        pipeline={"normalizer": normalize.VERSION, "chunker": CHUNKER_VERSION, "maxChunkWords": args.max_chunk_words},
        review=review_counts(documents))
    try:
        path = write_release(out, manifest, chunks, vectors)
    except ReleaseError as error:
        return _fail(f"Build refused: {error}")
    kinds = Counter(chunk.kind for chunk in chunks)
    review = manifest.review
    print(f"Built release {release_id} ({args.channel})\n"
          f"  path:      {path}\n"
          f"  corpus:    {corpus.id}\n"
          f"  documents: {len(documents)} ({review['approved']} approved, {review['draft']} draft, "
          f"{review['synthetic']} synthetic)\n"
          f"  chunks:    {len(chunks)} ({kinds['passage']} passage, {kinds['answer']} answer; "
          f"budget {args.max_chunk_words} words)\n"
          f"  embedder:  {_describe(embedder.identity)}\n"
          f"  warnings:  {len(report.warnings)}")
    return 0


def _load(path: str):
    try:
        return load_release(Path(path))
    except ReleaseError as error:
        print(f"Release refused: {error}", file=sys.stderr)
        return None


def _verify(args) -> int:
    release = _load(args.release_dir)
    if release is None:
        return 1
    manifest = release.manifest
    pipeline, review = manifest.pipeline, manifest.review
    servable = sum(chunk.servable for chunk in release.chunks)
    print(f"Release {manifest.release_id} verified: checksums and counts match\n"
          f"  created:   {manifest.created_at}\n"
          f"  channel:   {manifest.channel}\n"
          f"  corpora:   {', '.join(manifest.corpus_ids)}\n"
          f"  documents: {manifest.document_count} ({review.get('approved', 0)} approved, "
          f"{review.get('draft', 0)} draft, {review.get('synthetic', 0)} synthetic)\n"
          f"  chunks:    {manifest.chunk_count} ({servable} servable)\n"
          f"  embedder:  {_describe(manifest.embedder)}\n"
          f"  pipeline:  {pipeline.get('normalizer')}, {pipeline.get('chunker')}, "
          f"{pipeline.get('maxChunkWords')} words per chunk")
    return 0


def _stats(args) -> int:
    release = _load(args.release_dir)
    if release is None:
        return 1
    chunks = release.chunks
    words = [word_count(chunk.text) for chunk in chunks]

    def counts(values) -> str:
        return ", ".join(f"{key} {count}" for key, count in sorted(Counter(values).items()))

    manifest = release.manifest
    print(f"Release {manifest.release_id}: {len(chunks)} chunks from {manifest.document_count} documents\n"
          f"  content type:  {counts(chunk.content_type for chunk in chunks)}\n"
          f"  language:      {counts(chunk.language for chunk in chunks)}\n"
          f"  review status: {counts(chunk.review_status for chunk in chunks)}\n"
          f"  kind:          {counts(chunk.kind for chunk in chunks)}\n"
          f"  synthetic:     {sum(chunk.synthetic for chunk in chunks)}\n"
          f"  words/chunk:   average {sum(words) / len(words):.1f}, max {max(words)}")
    return 0


def _import_markdown(args) -> int:
    source, out = Path(args.source), Path(args.out_dir)
    files = sorted(source.glob("*.md")) if source.is_dir() else [source]
    if not files or not all(file.is_file() for file in files):
        return _fail(f"No Markdown documents found at {source}.")
    converted: list[tuple[Path, Document]] = []
    failed = False
    for file in files:
        try:
            parsed = parse_markdown(file.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, MarkdownError) as error:
            messages = error.errors if isinstance(error, MarkdownError) else [(None, "is not saved as UTF-8 text")]
            for line, message in messages:
                print(f"error    {file.name}{f':{line}' if line else ''}: {message}")
            failed = True
            continue
        document, issues = parse_document(parsed.data, file.name, parsed.lines)
        for issue in issues:
            print(issue)
        if document is None:
            failed = True
        elif any(document.id == other.id for _, other in converted):
            print(f"error    {file.name}: id {document.id} is also used by another file in this import")
            failed = True
        elif (out / f"{document.id}.json").exists() and not args.overwrite:
            print(f"error    {file.name}: {out / f'{document.id}.json'} already exists; "
                  "pass --overwrite to replace it")
            failed = True
        else:
            converted.append((file, document))
    if failed:
        return _fail("Nothing was written: fix the errors above, then import again.")
    out.mkdir(parents=True, exist_ok=True)
    for file, document in converted:
        target = out / f"{document.id}.json"
        target.write_text(json.dumps(document.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                          newline="\n")
        print(f"wrote {target} from {file.name}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m companion_api.rag.pipeline",
                                     description="Validate a corpus and build, verify or inspect immutable releases.")
    commands = parser.add_subparsers(dest="command", required=True)

    def budget(command):
        command.add_argument("--max-chunk-words", type=int, default=DEFAULT_MAX_CHUNK_WORDS,
                             help=f"chunk word budget (default {DEFAULT_MAX_CHUNK_WORDS})")

    validate = commands.add_parser("validate", help="check a corpus folder and print the report")
    validate.add_argument("corpus_dir")
    validate.add_argument("--json", action="store_true", help="print the report as JSON")
    budget(validate)
    validate.set_defaults(handler=_validate)

    build = commands.add_parser("build", help="validate, chunk, embed and write a new release")
    build.add_argument("corpus_dir")
    build.add_argument("--out", required=True, help="folder that holds releases, for example releases")
    build.add_argument("--release-id", help="default: <corpus-id>-<UTC yyyymmddHHMMSS>")
    build.add_argument("--embedding-model", help="default: $COMPANION_EMBEDDING_MODEL or "
                                                 f"{embeddings.DEFAULT_EMBEDDING_MODEL}; 'hashing' works offline")
    build.add_argument("--embedding-base-url", help="default: $COMPANION_EMBEDDING_BASE_URL, "
                                                    f"$COMPANION_LLM_BASE_URL or {embeddings.DEFAULT_BASE_URL}")
    build.add_argument("--channel", choices=("development", "published"), default="development")
    budget(build)
    build.set_defaults(handler=_build)

    verify = commands.add_parser("verify", help="check a release's checksums and print its manifest")
    verify.add_argument("release_dir")
    verify.set_defaults(handler=_verify)

    importer = commands.add_parser("import-markdown", help="convert Markdown documents to canonical JSON")
    importer.add_argument("source", help="a .md file or a folder of them")
    importer.add_argument("out_dir")
    importer.add_argument("--overwrite", action="store_true", help="replace JSON files that already exist")
    importer.set_defaults(handler=_import_markdown)

    stats = commands.add_parser("stats", help="chunk counts and sizes of a release")
    stats.add_argument("release_dir")
    stats.set_defaults(handler=_stats)
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:  # a Windows console or pipe may not encode every character of a name or path
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    if getattr(args, "max_chunk_words", 1) < 1:
        return _fail("--max-chunk-words must be at least 1.")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
