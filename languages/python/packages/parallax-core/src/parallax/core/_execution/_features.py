from __future__ import annotations

from typing import Final

from parallax.core.base import UnsupportedError
from parallax.core.object_query import AsOfRange, History, QueryClauses

__all__ = ["EXECUTION_FEATURE_DEFERRED", "deferred_feature_refusal", "deferred_features"]

_DEFERRED_EXECUTION_FEATURES: Final[frozenset[str]] = frozenset({"snapshot-history-includes"})

EXECUTION_FEATURE_DEFERRED: Final = "execution-feature-deferred"
"""A valid modeled read whose execution this implementation has deferred.

Nothing about the query is wrong: it is well formed and legal against the
connected model, and a later release executing the named Features runs it
unchanged. The refusal names EVERY Feature the query matched, in ascending
order, so a caller reads the complete reason rather than whichever match was
found first.
"""


def deferred_feature_refusal(features: frozenset[str]) -> UnsupportedError:
    """The refusal of a read requiring the Deferred Execution ``features``."""
    return UnsupportedError(
        EXECUTION_FEATURE_DEFERRED,
        f"this Snapshot implementation has deferred {', '.join(sorted(features))} "
        "and cannot execute this query yet",
    )


def deferred_features(query: QueryClauses) -> frozenset[str]:
    """Every Deferred Execution Feature ``query`` requires.

    Empty for every query this implementation executes, which is the ordinary
    answer; a nonempty result is the refusal's whole content.
    """
    return _required_features(query) & _DEFERRED_EXECUTION_FEATURES


def _required_features(query: QueryClauses) -> frozenset[str]:
    """The Feature-tagged read capabilities ``query`` requires.

    Only the capabilities the inventory could name are computed. A query's full
    Feature profile is a compatibility-corpus concern; what this module needs is
    one side of an intersection.
    """
    return frozenset({"snapshot-history-includes"} if _includes_over_a_scan(query) else ())


def _includes_over_a_scan(query: QueryClauses) -> bool:
    """Whether ``query`` eager-fetches over a SCANNED temporal dimension.

    A milestone-set read answers one root per milestone, and combining that
    with Includes is the ``snapshot-history-includes`` Feature. Both halves are
    clauses of one flat query, so this is two field reads rather than a walk: an
    Include Path names at least one relationship level by construction, and a
    scan is an ``asOfRange`` or ``history`` selection on any dimension.

    Reaching this answer costs no port, so this module stays clear of the
    Database Port its own read-query resolution consumer must not touch.
    """
    return query.requests_includes and any(
        isinstance(selection, (AsOfRange, History)) for selection in query.temporal.values()
    )
