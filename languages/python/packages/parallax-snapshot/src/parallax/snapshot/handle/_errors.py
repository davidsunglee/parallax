from __future__ import annotations

from typing import Final

__all__ = [
    "SnapshotConnectionError",
    "SnapshotMaterializationError",
]


class SnapshotConnectionError(ValueError):
    """A modeled read was asked of a Database over a model that names no class.

    A Snapshot answers Entity Class instances, so serving one needs a
    class-backed :class:`~parallax.core.DomainModel` — one that composed Entity
    Classes and therefore holds the index deciding which class a returned row
    instantiates. Both connection doors refuse a value that is no Domain Model
    at all, before the adapter is touched; a descriptor-backed model connects
    and is refused here instead, at the read it cannot serve and still before
    any SQL.

    The refusal is about materialization capability and never about identity or
    ownership: any class-backed model serves, however many other Databases
    already serve it. :data:`code` and the message are its whole public state.
    """

    code: Final[str] = "snapshot-class-backed-model-required"


class SnapshotMaterializationError(RuntimeError):
    """Building the Entity graph failed after the read itself had succeeded.

    Raised exactly once, at the materialization boundary, for a graph-construction
    refusal, a lifecycle build failure, or a state-factory failure. The original
    exception is the ``__cause__`` and is also carried as :attr:`cause`, so the
    defect stays diagnosable while callers branch on one stable code.

    Everything upstream keeps its own classification: query, capability,
    transaction, adapter, SQL, and neutral-decoding failures are never re-wrapped
    here, because none of them is a failure to build a graph. No partial graph and
    no Snapshot is published when this raises.
    """

    code: Final[str] = "snapshot-materialization-failed"

    def __init__(self, message: str, *, cause: BaseException) -> None:
        super().__init__(message)
        self.cause = cause
