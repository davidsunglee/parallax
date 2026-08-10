"""``parallax.snapshot.handle._errors`` — the dependency-free refusal leaf.

Holds the package's developer-facing refusals, so that WHERE a refusal is raised
places no constraint on which scopes can name it. It imports nothing but the
standard library, which is what lets the read-preflight seam
(:mod:`parallax.snapshot.handle._preflight`) and the write-lowering family leaf
(:mod:`parallax.snapshot.handle._family`) name the SAME failure: their
enforcement scopes grant disjoint dependencies, so either importing the other
would drag a scope the importer may not reach. A refusal with one raiser today
belongs here for that same reason rather than by a raiser count — the leaf is
what makes a second raiser, in any scope, a decision about behavior alone.

That emptiness is load-bearing rather than incidental, so ``spec/python.md`` §7
gives this module its own child scope with a grant row of ``(none)``. Two gates
hold it: the generated import-linter contract forbids every first-party scope
outside ``parallax.snapshot.handle`` AND every sibling child scope inside it,
and ``just python-check-scope-ownership`` fails on an import-free module written
beside this scope. A ``forbidden`` row is package-scoped, so the shared parent
package is the one name the row cannot state.

What makes the two consumers legal is their OWN rows rather than this one:
whatever this module reached, each consumer would acquire through it, and a
consumer's row forbids everything its grants do not reach — so a dependency
added here breaks the gate of any consumer not already granted it.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "QueryTargetError",
    "SnapshotConnectionError",
    "SnapshotMaterializationError",
    "UnobservedWriteError",
]


class SnapshotConnectionError(ValueError):
    """A modeled read was asked of a Database over a model that names no class.

    A Snapshot answers Entity Class instances, so serving one needs a
    class-backed :class:`~parallax.core.DomainModel` — one that composed Entity
    Classes and therefore holds the index deciding which class a returned row
    instantiates. :meth:`Database.connect` refuses a model that composed none
    before the adapter is touched; the first-party construction that admits a
    bare accepted Metamodel for neutral write work is refused here instead, at
    the read it cannot serve and still before any SQL.

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


class UnobservedWriteError(LookupError):
    """A neutral write named an Observation Key this unit of work never filed.

    An Observation Key is a REFERENCE into the transaction's own observation
    record, so ``tx.write_neutral`` dereferences it at the call rather than
    carrying it to planning: the defect is about what was read, and letting the
    write settle bare would surface it at flush as a licensing failure about what
    is being written — the wrong cause, one layer too late.

    A ``LookupError`` because that is what it is: the key resolved to nothing.
    Distinct from the `m-opt-lock` licensing refusals, which report that a
    settled write lacks evidence it structurally requires, rather than that a
    caller's reference missed. :data:`code` and the message are its whole public
    state; the key itself is not retained.
    """

    code: Final[str] = "write-observation-not-recorded"


class QueryTargetError(RuntimeError):
    """The connected model declares no Entity for a query's target.

    Raised before any SQL, connection acquisition, or adapter activity, and
    before a participating read force-flushes the unit of work, so a query the
    connected model cannot answer never becomes a side effect.

    The refusal reports that the CONNECTED MODEL, not the call's arguments, is
    what makes the query unanswerable — the identical query succeeds against a
    model declaring the Entity — which is why this is a ``RuntimeError``. It
    retains and exposes neither the query, the model, nor the Database:
    :data:`code` and the message are its whole public state.
    """

    code: Final[str] = "query-target-not-in-model"
