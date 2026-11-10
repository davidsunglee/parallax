from __future__ import annotations

from typing import Final, cast, get_args

from parallax.core.internal.concurrency._compile import MODEL_COMPILER
from parallax.core.internal.concurrency._facet import (
    CONCURRENCY_MODULE,
    FACET_KEY,
    ConcurrencyFacet,
    ConcurrencyPreference,
    ConcurrencyStrategy,
    EvidenceKind,
    ExplicitVersion,
    TransactionTimeVersion,
    Unversioned,
    VersionSource,
    concurrency_facet_of,
)
from parallax.core.internal.concurrency._rules import ISSUE_CODES, RULE_SET

__all__ = [
    "CONCURRENCY_MODULE",
    "CONCURRENCY_PREFERENCES",
    "FACET_KEY",
    "INITIAL_VERSION",
    "ISSUE_CODES",
    "MODEL_COMPILER",
    "RULE_SET",
    "ConcurrencyFacet",
    "ConcurrencyPreference",
    "ConcurrencyStrategy",
    "EvidenceKind",
    "ExplicitVersion",
    "TransactionTimeVersion",
    "Unversioned",
    "VersionSource",
    "concurrency_facet_of",
    "concurrency_preference",
    "next_version",
]

CONCURRENCY_PREFERENCES: Final[frozenset[str]] = frozenset(get_args(ConcurrencyPreference))

INITIAL_VERSION: Final[int] = 1
"""The version every explicitly versioned insert opens at, ignoring any
row-carried value."""


def concurrency_preference(value: object) -> ConcurrencyPreference:
    """Return the vocabulary's own spelling of ``value``, or raise ``ValueError``.

    The candidate is compared to each preference rather than looked up in the
    set, since a value no set can be asked about (an unhashable ``str``
    subclass) would make membership alone raise ``TypeError``. What comes back
    is the matched preference itself, never the caller's own object.
    """
    known = sorted(CONCURRENCY_PREFERENCES)
    if isinstance(value, str):
        for preference in known:
            if value == preference:
                return cast("ConcurrencyPreference", preference)
    raise ValueError(f"concurrency must be one of {known}, got {value!r}")


def next_version(observed: int) -> int:
    """The version a successful write of a row observed at ``observed`` stores."""
    return observed + 1
