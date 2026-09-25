"""Retrieval-augmented answers over immutable corpus releases.

Two halves share this package. The data pipeline (`corpus`, `chunking`,
`pipeline`) turns authored documents into an immutable release directory; the
runtime (`retriever`, `router`, `generator`, `grounding`, `service`) answers a
question from one loaded release. They meet only at `types`, `normalize`,
`embeddings` and `release`, so either half can change without the other.

Everything here is development-only until the scholarly, safeguarding, privacy
and legal gates in `doc/development-boundary.md` pass. See `doc/rag-system.md`.
"""
