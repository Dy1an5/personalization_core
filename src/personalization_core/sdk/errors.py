from __future__ import annotations


class SyncClientInAsyncContextError(RuntimeError):
    """Raised when the synchronous SDK wrapper is used inside an event loop."""
