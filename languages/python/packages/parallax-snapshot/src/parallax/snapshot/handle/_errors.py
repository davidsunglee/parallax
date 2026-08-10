"""``parallax.snapshot.handle._errors`` — the dependency-free refusal leaf.

The leaf exists for :class:`QueryTargetError`. The read-preflight seam
(:mod:`parallax.snapshot.handle._preflight`) and the write-lowering family leaf
(:mod:`parallax.snapshot.handle._family`) raise that one class from child
enforcement scopes whose ``spec/python.md`` §7 grants are disjoint, so either
importing the other would drag a scope the importer may not reach, and no scope
holding grants can define it for both. A module that reaches nothing at all is
the only place left, which is why this one imports nothing but the standard
library.

The other three are raised from the parent ``parallax.snapshot.handle`` scope
alone — :class:`SnapshotConnectionError` from ``_database`` and
``_transaction``, :class:`SnapshotMaterializationError` from ``_read``,
:class:`UnobservedWriteError` from ``_transaction`` — so nothing about their
raise sites compels this module, and their membership is a placement decision
rather than a structural one. Only the first of the three lacks a single home
of its own: class-backed capability is checked at both read doors, so either
module defining it would have the other import a sibling for a class neither
owns. The remaining two each have one raiser and one deciding surface — the
materialization boundary ``_read`` translates at, and the Observation-Key
dereference ``tx.write_neutral`` performs — and are here for one reason only,
which is that the scope's four developer-facing refusals are then read in one
place. Nothing structural rules on those two, and moving either beside its
surface would cost this module nothing.

The package's other developer-facing refusals are declared with the surface
that decides them: ``DeferredFeatureError`` by the Feature inventory it reports
(:mod:`parallax.snapshot.handle._features`), ``NoResultFound`` and
``TooManyResultsFound`` by ``Snapshot.result``
(:mod:`parallax.snapshot.handle._read`), ``TransactionOptionConflictError`` and
``TransactionOwnershipError`` by the demarcation rules they state
(:mod:`parallax.snapshot.handle._database`), ``KeyedWriteValueError`` and
``TransactionTimePinReadOnlyError`` by the write-input checks that run them
(:mod:`parallax.snapshot.handle._write_inputs`), and ``WriteLoweringError`` by
the lowering types (:mod:`parallax.snapshot.handle._write_types`).

The leaf's emptiness is load-bearing rather than incidental, so ``spec/python.md`` §7
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
