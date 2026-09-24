from __future__ import annotations

from typing import Final

from parallax.core.object_query import AsOfRange, History, ObjectQueryNode

__all__ = ["DeferredFeatureError", "deferred_features"]

_DEFERRED_EXECUTION_FEATURES: Final[frozenset[str]] = frozenset({"snapshot-history-includes"})


class DeferredFeatureError(RuntimeError):
    """A valid modeled read whose execution this implementation has deferred.

    Nothing about the query is wrong: it is well formed and legal against the
    connected model, and a later release executing the named
    Features runs it unchanged. That is why this is a ``RuntimeError`` rather
    than a definition or rejection error, and why it is disjoint from
    :class:`~parallax.snapshot.handle._errors.SnapshotConnectionError`, which
    refuses a connection that could never materialize any read.

    :data:`code` and :data:`features` are its whole public state; it retains
    neither the query, the model, nor the Database. ``features``
    is NONEMPTY and ascending, listing EVERY Feature the query matched, so a
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


def deferred_features(query: ObjectQueryNode) -> frozenset[str]:
    """Every Deferred Execution Feature ``query`` requires.

    Empty for every query this implementation executes, which is the ordinary
    answer; a nonempty result is the refusal's whole content.
    """
    return _required_features(query) & _DEFERRED_EXECUTION_FEATURES


def _required_features(query: ObjectQueryNode) -> frozenset[str]:
    """The Feature-tagged read capabilities ``query`` requires.

    Only the capabilities the inventory could name are computed. A query's full
    Feature profile is a compatibility-corpus concern; what this module needs is
    one side of an intersection.
    """
    return frozenset({"snapshot-history-includes"} if _includes_over_a_scan(query) else ())


def _includes_over_a_scan(query: ObjectQueryNode) -> bool:
    """Whether ``query`` eager-fetches over a SCANNED temporal dimension.

    A milestone-set read answers one root per milestone, and combining that
    with Includes is the ``snapshot-history-includes`` Feature. Both halves are
    clauses of one flat query, so this is two field reads rather than a walk: an
    Include Path names at least one relationship level by construction, and a
    scan is an ``asOfRange`` or ``history`` selection on any dimension.

    Reaching this answer costs no port, so this module stays clear of the
    Database Port its own read-preflight consumer must not touch.
    """
    return bool(query.includes) and any(
        isinstance(selection, (AsOfRange, History)) for selection in query.temporal.values()
    )
