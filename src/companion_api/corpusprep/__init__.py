"""Offline source preparation that runs before the RAG pipeline (doc/corpus-tasks.md).

Downloads registered sources, verifies them by sha256 and builds the canonical
Quran, tafsir and hadith files under `corpus/canonical/`. Sacred text is only
ever copied from a downloaded file, never written or corrected here.
"""
