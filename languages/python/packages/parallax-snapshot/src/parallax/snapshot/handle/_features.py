"""``parallax.snapshot.handle._features`` — Deferred Execution Features.

The inventory of Conformance-Slice read Features whose operation shapes this
Snapshot implementation is expected to execute and has not implemented yet,
together with the recognizer deciding whether one canonical operation requires
any of them. The read-preflight seam consults it after target resolution and
operation validation and before any I/O, so such a query is refused BY NAME
rather than rejected as invalid: ``m-snapshot-read`` carries
``snapshot-history-includes`` on its own Feature tag and forbids any case
mandating its refusal, so the query is valid, the implementation is behind, and
the refusal says which of the two it is.

The inventory is FIXED for the installed package and describes Snapshot's own
execution completeness — never a database provider's capability, a Dialect
trait, an adapter or Database Port property, or anything an application,
environment, constructor argument, or hook can add to or remove from. There is
no capability protocol here for a provider to implement, because every Database
in one installation defers exactly the same set. Its expected end state is
empty, and every member is reviewable implementation debt.

A member is added only atomically with the core behavior and Feature tag that
defines it, the active Conformance Slice's explicit non-claim of that Feature,
the Python specification's deferred list, and zero-I/O refusal coverage —
``tests/compatibility`` proves the non-claim by walking the claimed corpus. A
Feature the active slice DOES claim is a defect when unimplemented and can never
be made permissible by listing it here. Removing a member is the same change in
reverse.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
The inventory itself is the exception — it keeps the leading underscore
``spec/python.md`` names it by, and nothing imports it, which is the property the
sentences above describe.
"""

from __future__ import annotations

from typing import Final

from parallax.core.op_algebra import (
    AsOf,
    AsOfRange,
    DeepFetch,
    Distinct,
    History,
    Limit,
    Narrow,
    Operation,
    OrderBy,
)
from parallax.core.temporal_read import scans_an_axis

__all__ = ["DeferredFeatureError", "deferred_features"]

_DEFERRED_EXECUTION_FEATURES: Final[frozenset[str]] = frozenset({"snapshot-history-includes"})


class DeferredFeatureError(RuntimeError):
    """A valid modeled read whose execution this implementation has deferred.

    Nothing about the query is wrong: the operation is well formed and legal
    against the connected model, and a later release executing the named
    Features runs it unchanged. That is why this is a ``RuntimeError`` rather
    than a definition or rejection error, and why it is disjoint from
    :class:`~parallax.snapshot.handle._errors.SnapshotConnectionError`, which
    refuses a connection that could never materialize any read.

    :data:`code` and :data:`features` are its whole public state; it retains
    neither the query, the operation, the model, nor the Database. ``features``
    is NONEMPTY and ascending, listing EVERY Feature the operation matched, so a
    caller reads the complete reason rather than whichever match was found
    first. The constructor enforces the nonemptiness: an empty match set is the
    ordinary answer for a query this implementation executes, so raising it
    would name no deferral at all, and this class is exported — a caller can
    reach the constructor directly.

    Raised before SQL generation, connection acquisition, Database Port access,
    and — on a participating read — before the unit of work's force-flush, so a
    deferred read never becomes a side effect.
    """

    code: Final[str] = "execution-feature-deferred"

    def __init__(self, features: frozenset[str]) -> None:
        if not features:
            raise ValueError(
                "a deferred-feature refusal names at least one Feature; an empty match "
                "set means the query is executable and nothing is refused"
            )
        ordered = tuple(sorted(features))
        super().__init__(
            f"{self.code}: this Snapshot implementation has deferred "
            f"{', '.join(ordered)} and cannot execute this query yet"
        )
        self.features: tuple[str, ...] = ordered


def deferred_features(operation: Operation) -> frozenset[str]:
    """Every Deferred Execution Feature ``operation`` requires.

    Empty for every operation this implementation executes, which is the
    ordinary answer; a nonempty result is the refusal's whole content.
    """
    return _required_features(operation) & _DEFERRED_EXECUTION_FEATURES


def _required_features(operation: Operation) -> frozenset[str]:
    """The Feature-tagged read capabilities ``operation`` requires.

    Only the capabilities the inventory could name are computed. An operation's
    full Feature profile is a compatibility-corpus concern; what this module
    needs is one side of an intersection.
    """
    return frozenset({"snapshot-history-includes"} if _includes_over_a_scan(operation) else ())


def _includes_over_a_scan(operation: Operation) -> bool:
    """Whether ``operation`` deep-fetches over a SCANNED temporal axis.

    A milestone-set read answers one graph per milestone, and combining that
    with includes is the ``snapshot-history-includes`` Feature. The deep fetch
    is not confined to the outermost node: ``m-op-algebra`` composes it freely
    with the nodes returning their operand's OWN rows — ``orderBy``, ``limit``,
    ``distinct``, ``narrow``, and the temporal ``asOf``, ``asOfRange``, and
    ``history`` — so the walk descends that closed spine until it reaches one,
    exactly as the read gate's own level check does. Reading the outer node
    alone would let a wrapper-carried deep fetch over a milestone set past this
    seam, which is the deferral evading its own refusal rather than a shape this
    implementation runs.

    A scan on EITHER side of the deep fetch is the same milestone set: the
    wrappers crossed on the way down are part of the read, and the operand below
    is the question ``~parallax.core.temporal_read.scans_an_axis`` owns — the
    same recognizer the read executors dispatch a milestone-set find on, and one
    that deliberately does not peel a deep fetch itself, leaving a composer of
    the two to hold that half. Reaching it costs no port: ``m-temporal-read`` is
    a pure operation-and-metadata scope, so this module stays clear of the
    Database Port its own read-preflight consumer must not touch.
    """
    node = operation
    scanned = False
    while True:
        match node:
            case DeepFetch(operand=operand):
                return scanned or scans_an_axis(operand)
            case AsOfRange(operand=operand) | History(operand=operand):
                scanned = True
                node = operand
            case (
                OrderBy(operand=operand)
                | Limit(operand=operand)
                | Distinct(operand=operand)
                | Narrow(operand=operand)
                | AsOf(operand=operand)
            ):
                node = operand
            case _:
                return False
