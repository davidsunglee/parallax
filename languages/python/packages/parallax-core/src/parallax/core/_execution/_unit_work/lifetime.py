from __future__ import annotations

from typing import Protocol

__all__ = ["AttemptLifetime"]


class AttemptLifetime(Protocol):
    """The lifetime of the transaction attempt a unit of work coordinates.

    The attempt owns it; the unit of work only asks it to admit work, which it
    refuses once the attempt ended or became rollback-only, and dooms it when a
    flush fails while executing.
    """

    def ensure_open(self) -> None: ...

    def doom(self, cause: BaseException, /) -> None: ...
