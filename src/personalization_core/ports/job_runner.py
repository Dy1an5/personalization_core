from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

Job = Callable[[], Awaitable[None]]


@runtime_checkable
class JobRunner(Protocol):
    async def submit(self, name: str, job: Job) -> None:
        raise NotImplementedError
