"""The unit-preserving chunker, `chunk-v1` (doc/rag-system.md §4).

A unit is a verse, a narration, a ruling with its qualification or a
paragraph, and cutting one would let an answer cite half of it out of context.
So the chunker only ever groups whole units: consecutive units of one section,
until the next would pass the word budget. A unit over the budget becomes its
own chunk instead of being cut, and a `keepWithNext` unit always travels with
the unit after it. The output depends only on the documents and the budget,
so chunk ids stay stable across rebuilds of the same corpus.
"""
from typing import Iterable

from . import normalize
from .corpus import DEFAULT_MAX_CHUNK_WORDS, Document, Unit, keep_groups, word_count
from .types import Chunk

VERSION = "chunk-v1"
_DOT, _DASH = " \u00b7 ", "\u2013"

__all__ = ["VERSION", "DEFAULT_MAX_CHUNK_WORDS", "chunk_document", "chunk_documents", "embedding_text",
           "source_label"]


def source_label(document: Document, references: tuple[str, ...]) -> str:
    """The work, a middle dot, then the first reference and, when it differs, an en dash and the last (§4).

    For example "Robert's guide · part 1" or "Robert's guide · part 1–part 3". The title stands in
    for a missing `source.work`, which only synthetic documents may leave out.
    """
    work = document.source.work or document.title
    if not references:
        return work
    span = references[0] if len(references) == 1 else references[0] + _DASH + references[-1]
    return work + _DOT + span


def _sections(units: Iterable[Unit]) -> list[list[Unit]]:
    runs: list[list[Unit]] = []
    for unit in units:
        if runs and runs[-1][-1].section == unit.section:
            runs[-1].append(unit)
        else:
            runs.append([unit])
    return runs


def _chunk(document: Document, number: int, *, text: str, search: str, references: tuple[str, ...] = (),
           unit_ids: tuple[str, ...] = (), questions: tuple[str, ...] = ()) -> Chunk:
    return Chunk(id=f"{document.id}#{number}", document_id=document.id, kind=document.kind, title=document.title,
                 language=document.language, age_bands=document.age_bands, content_type=document.content_type,
                 madhhab=document.madhhab, review_status=document.review.status, synthetic=document.synthetic,
                 text=text, search_text=search, references=references,
                 source_label=source_label(document, references), unit_ids=unit_ids, questions=questions)


def chunk_document(document: Document, max_chunk_words: int = DEFAULT_MAX_CHUNK_WORDS) -> list[Chunk]:
    """Chunks for one validated document, numbered from 1 in reading order."""
    if max_chunk_words < 1:
        raise ValueError("max_chunk_words must be at least 1")
    if document.kind == "answer":
        search = normalize.search_text("\n".join((*document.questions, document.answer)))
        return [_chunk(document, 1, text=document.answer, search=search, questions=document.questions)]
    packed: list[list[Unit]] = []
    for run in _sections(document.units):
        current: list[Unit] = []
        words = 0
        for group in keep_groups(run):
            size = sum(word_count(unit.text) for unit in group)
            if current and words + size > max_chunk_words:
                packed.append(current)
                current, words = [], 0
            current.extend(group)
            words += size
        if current:
            packed.append(current)
    chunks = []
    for number, units in enumerate(packed, 1):
        text = "\n\n".join(unit.text for unit in units)
        references = tuple(dict.fromkeys(unit.reference for unit in units if unit.reference))
        chunks.append(_chunk(document, number, text=text, search=normalize.search_text(text), references=references,
                             unit_ids=tuple(unit.id for unit in units)))
    return chunks


def chunk_documents(documents: Iterable[Document], max_chunk_words: int = DEFAULT_MAX_CHUNK_WORDS) -> list[Chunk]:
    """Every chunk of a corpus, ordered by document id so the release's vector order is reproducible."""
    return [chunk for document in sorted(documents, key=lambda document: document.id)
            for chunk in chunk_document(document, max_chunk_words)]


def embedding_text(chunk: Chunk) -> str:
    """What the embedder sees for a chunk: `"<title>\\n<text>"`, questions before the answer (§4)."""
    return "\n".join((chunk.title, *chunk.questions, chunk.text))
