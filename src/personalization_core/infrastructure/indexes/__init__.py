"""In-process retrieval index adapters."""

from .full_text import SimpleFullTextIndex
from .in_memory import InMemoryVectorIndex
from .null_index import NullVectorIndex

__all__ = ["InMemoryVectorIndex", "NullVectorIndex", "SimpleFullTextIndex"]
