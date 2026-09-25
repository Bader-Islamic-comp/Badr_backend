"""Operator console: `python -m companion_api.rag.ask --release DIR [--include-drafts] [--check]`.

For adults trying a release with synthetic questions. It reads one question per
line from stdin and prints what the API would release: the answer type, the
text and its sources, plus the outcome code. Nothing is stored or logged
beyond the service's usual provenance line.

`--check` verifies the release checksums, that the configured embedder matches
the release and answers, that the generation endpoint is private and serves an
allowlisted model, then exits (0 when all pass).

Settings come from the server's environment variables (doc/rag-system.md
section 9); only the release directory is given here.
"""
import argparse
import sys

from ..config import Settings
from .embeddings import EmbeddingError
from .generator import GenerationError
from .service import AnswerService, assemble

BANNER = ("Robert operator console. Adult-operated, synthetic text only: do not type real children's questions "
          "or anyone's personal data.\nOne question per line; end with Ctrl-Z then Enter (Windows) or Ctrl-D.")
MAX_QUESTION = 2000  # the API's TurnRequest bound


def check(service: AnswerService, settings: Settings) -> int:
    failures = 0
    manifest = service.retriever.release.manifest
    identity = service.retriever.embedder.identity
    print(f"ok    release {manifest.release_id}: {manifest.chunk_count} chunks, checksums verified, "
          f"channel {manifest.channel}")
    print(f"ok    embedder {identity.name}/{identity.model} ({identity.dimensions} dimensions) matches the release")
    try:
        service.retriever.embedder.embed_query("synthetic operator check")
        print("ok    embedder answers" + (" (offline hashing embedder, no endpoint)" if identity.name == "hashing"
                                           else f" at {settings.embedding_endpoint}"))
    except EmbeddingError as exception:
        failures += 1
        print(f"FAIL  {exception}")
    print(f"ok    model {service.generator.model} is allowlisted; {settings.llm_base_url} is a private endpoint")
    try:
        service.generator.check()
        print(f"ok    generation endpoint serves {service.generator.model}")
    except GenerationError as exception:
        failures += 1
        print(f"FAIL  {exception}")
    return 1 if failures else 0


def show(service: AnswerService, question: str):
    result = service.answer(question)
    print(f"[{result.answer_type}] {result.text}")
    for number, source in enumerate(result.sources, start=1):
        print(f"    [{number}] {source.id}  {source.title}  ({source.reference})")
    print(f"    outcome: {result.reason}")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="python -m companion_api.rag.ask", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", required=True, help="release directory to answer from")
    parser.add_argument("--include-drafts", action="store_true", help="also retrieve draft chunks (operators only)")
    parser.add_argument("--check", action="store_true", help="verify release, embedder and model endpoint, then exit")
    args = parser.parse_args(argv)
    settings = Settings.from_environment()
    try:
        service = assemble(settings, args.release, include_drafts=args.include_drafts)
    except RuntimeError as exception:
        print(f"FAIL  {exception}", file=sys.stderr)
        return 1
    if args.check:
        return check(service, settings)

    print(BANNER, file=sys.stderr)
    if args.include_drafts:
        print("Drafts are included: answers may use unreviewed text that the API never serves.", file=sys.stderr)
    interactive = sys.stdin.isatty()
    while True:
        if interactive:
            print("> ", end="", file=sys.stderr, flush=True)
        line = sys.stdin.readline()
        if not line:
            return 0
        question = line.strip()
        if not question:
            continue
        if len(question) > MAX_QUESTION:
            print(f"(questions are limited to {MAX_QUESTION} characters, as in the API)")
            continue
        show(service, question)


if __name__ == "__main__":
    raise SystemExit(main())
