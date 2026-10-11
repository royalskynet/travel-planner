"""Persistent V2 trip revisions."""

from .sqlite import RevisionRecord, SQLiteTripRepository

__all__ = ["RevisionRecord", "SQLiteTripRepository"]
