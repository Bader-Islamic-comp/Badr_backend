"""The unit-preserving chunker, `chunk-v2` (doc/rag-system.md §4, §13).

A unit is a verse, a narration, a ruling with its qualification or a
paragraph, and cutting one would let an answer cite half of it out of context.
So the chunker only ever groups whole units: consecutive units of one section,
until the next would pass the word budget. A unit over the budget becomes its
own chunk instead of being cut, and a `keepWithNext` unit always travels with
the unit after it. The output depends only on the documents and the budget,
so chunk ids stay stable across rebuilds of the same corpus.

chunk-v2 keeps that packing unchanged and adds, for schema v2 documents: the
structure metadata (source_refs, cluster, tier, header...), and child chunks
for small-to-big retrieval: one per verbatim `part` of a unit, and one per unit
of a multi-unit chunk when the document sets `children: units`. Children are
numbered after the parent chunks and point at them with `parent_id`, so ids
keep the `<document>#<n>` form the API accepts. chunk-v1 releases still load.
"""
from hashlib import sha256
from typing import Iterable

from . import normalize
from .corpus import DEFAULT_MAX_CHUNK_WORDS, Document, Unit, keep_groups, word_count
from .types import Chunk

VERSION = "chunk-v2"
_DOT, _DASH = " \u00b7 ", "\u2013"

__all__ = ["VERSION", "DEFAULT_MAX_CHUNK_WORDS", "chunk_document", "chunk_documents", "embedding_text",
           "source_label"]


def _kind(reference: str) -> str:
    """`quran`, `bukhari`, `abu_dawud`…: what a reference points into ("" for a plain one such as "part 1")."""
    return reference.split(":", 1)[0] if ":" in reference else ""


def source_label(document: Document, references: tuple[str, ...]) -> str:
    """The work, a middle dot, then the references as runs of one kind (§4).

    A run is its first reference and, when it differs, an en dash and its last; runs are joined by "; ".
    For example "Robert's guide · part 1–part 3", or "… · abu_dawud:5082; quran:112:1-4–quran:114:1-6" for
    an item citing a hadith and three surahs: before 2026-10-05 the span ran from the first reference to the
    last whatever their kinds, and that item read "abu_dawud:5082–quran:114:1-6", naming none of 112 and 113.
    The title stands in for a missing `source.work`, which only synthetic documents may leave out.
    """
    work = document.source.work or document.title
    if not references:
        return work
    runs: list[list[str]] = []
    for reference in references:
        if runs and _kind(runs[-1][-1]) == _kind(reference):
            runs[-1].append(reference)
        else:
            runs.append([reference])
    return work + _DOT + "; ".join(run[0] if len(run) == 1 else run[0] + _DASH + run[-1] for run in runs)


def _sections(units: Iterable[Unit]) -> list[list[Unit]]:
    runs: list[list[Unit]] = []
    for unit in units:
        if runs and runs[-1][-1].section == unit.section:
            runs[-1].append(unit)
        else:
            runs.append([unit])
    return runs


def _chunk(document: Document, number: int, *, text: str, search: str, references: tuple[str, ...] = (),
           unit_ids: tuple[str, ...] = (), questions: tuple[str, ...] = (), source_refs: tuple[str, ...] = (),
           parent_id: str | None = None, header: str | None = None) -> Chunk:
    return Chunk(id=f"{document.id}#{number}", document_id=document.id, kind=document.kind, title=document.title,
                 language=document.language, age_bands=document.age_bands, content_type=document.content_type,
                 madhhab=document.madhhab, review_status=document.review.status, synthetic=document.synthetic,
                 text=text, search_text=search, references=references,
                 source_label=source_label(document, references), unit_ids=unit_ids, questions=questions,
                 source_refs=source_refs, parent_id=parent_id or document.parent_chunk,
                 cluster_id=document.cluster_id, cluster_refs=document.cluster_refs,
                 context_header=header if header is not None else (document.context_header or ""),
                 tier=document.tier, prophet_id=document.prophet_id, topics=document.topics,
                 madhhab_scope=document.madhhab_scope, grading=document.grading, reviewer=document.review.reviewer,
                 source_ids=document.source_ids,
                 generated_questions=document.generated_questions if parent_id is None else (),
                 checksum=sha256(text.encode("utf-8")).hexdigest())


def _refs(units) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ref for unit in units for ref in unit.source_refs))


def chunk_document(document: Document, max_chunk_words: int = DEFAULT_MAX_CHUNK_WORDS) -> list[Chunk]:
    """Chunks for one validated document, numbered from 1 in reading order."""
    if max_chunk_words < 1:
        raise ValueError("max_chunk_words must be at least 1")
    # norm-v3: the rasm map applies to Quran text only.
    quranic = document.content_type == "quran"
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
        chunks.append(_chunk(document, number, text=text, search=normalize.search_text(text, quranic=quranic),
                             references=references,
                             unit_ids=tuple(unit.id for unit in units), source_refs=_refs(units)))
    children = []
    for parent, units in zip(chunks, packed):
        for unit in units:
            pieces = unit.parts or ((unit.text,) if document.children == "units" and len(units) > 1 else ())
            for index, piece in enumerate(pieces, 1):
                header = document.context_header or document.title
                if unit.parts:
                    header += f" — part {index} of {len(unit.parts)}"
                children.append(_chunk(document, len(chunks) + len(children) + 1, text=piece,
                                       search=normalize.search_text(piece, quranic=quranic),
                                       references=(unit.reference,) if unit.reference else (),
                                       unit_ids=(unit.id,), source_refs=unit.source_refs, parent_id=parent.id,
                                       header=header))
    return chunks + children


def chunk_documents(documents: Iterable[Document], max_chunk_words: int = DEFAULT_MAX_CHUNK_WORDS) -> list[Chunk]:
    """Every chunk of a corpus, ordered by document id so the release's vector order is reproducible."""
    return [chunk for document in sorted(documents, key=lambda document: document.id)
            for chunk in chunk_document(document, max_chunk_words)]


def embedding_text(chunk: Chunk) -> str:
    """What the embedder sees: the context header (else the title), questions before the answer, the text (§4).

    A Quran chunk is embedded from its search text, the simple spelling (norm-v3), because questions are
    written in simple spelling and are never mapped; its displayed text keeps the Uthmani rasm.
    """
    body = chunk.search_text if chunk.content_type == "quran" else chunk.text
    return "\n".join((chunk.context_header or chunk.title, *chunk.questions, body))
