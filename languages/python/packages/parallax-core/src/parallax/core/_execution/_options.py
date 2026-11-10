from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.internal.auto_retry import RetryPolicy, retry_policy
from parallax.core.internal.concurrency import ConcurrencyPreference, concurrency_preference
from parallax.core.internal.db_port import IsolationLevel, isolation_level

__all__ = [
    "OMITTED",
    "Omitted",
    "ReadOnlyTxnOptions",
    "TxnOptions",
    "patch_options",
]


class Omitted:
    """The type of the one marker a transaction keyword defaults to when the
    caller says nothing.

    A typed class rather than ``None`` so the annotation on each keyword names
    exactly the values it admits: ``None`` is then an ordinary invalid value,
    refused by the field rule, rather than a second spelling of omission.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "OMITTED"


OMITTED: Final[Omitted] = Omitted()

_BUILT_IN_RETRY: Final = RetryPolicy()


@dataclass(frozen=True, slots=True)
class TxnOptions:
    """The three transaction options a Database Root configures as defaults, and
    the resolved record every outer invocation runs under.

    ``retry`` is the one Retry Policy an invocation's attempts run under.
    ``concurrency`` is the Concurrency Preference each Entity's Effective
    Concurrency Strategy is derived from. ``isolation`` is the portable level
    every physical attempt asks the port for; the built-in default is Read
    Committed, requested concretely rather than left to the database's
    configured default.

    Every field is validated at construction under the same rules an explicit
    ``db.transact`` keyword meets, and ``None`` is invalid for all three: only
    an omitted keyword inherits.
    """

    retry: RetryPolicy = _BUILT_IN_RETRY
    concurrency: ConcurrencyPreference = "optimistic"
    isolation: IsolationLevel = "read_committed"

    def __post_init__(self) -> None:
        retry_policy(self.retry)
        object.__setattr__(self, "concurrency", concurrency_preference(self.concurrency))
        object.__setattr__(self, "isolation", isolation_level(self.isolation))


@dataclass(frozen=True, slots=True)
class ReadOnlyTxnOptions:
    """The resolved options a read-only invocation runs under.

    Each field is the read-only call's explicit keyword, else the scope's
    default for it, validated under the rule :class:`TxnOptions` applies to the
    same field. A read-only transaction takes no participation lock, so it has
    no Concurrency Preference to resolve, whatever the scope's defaults name.
    """

    retry: RetryPolicy
    isolation: IsolationLevel

    def __post_init__(self) -> None:
        retry_policy(self.retry)
        object.__setattr__(self, "isolation", isolation_level(self.isolation))


def patch_options(
    options: TxnOptions,
    *,
    retry: RetryPolicy | Omitted = OMITTED,
    concurrency: ConcurrencyPreference | Omitted = OMITTED,
    isolation: IsolationLevel | Omitted = OMITTED,
) -> TxnOptions:
    """Apply one partial option patch, reusing ``options`` when unchanged."""
    policy = options.retry if isinstance(retry, Omitted) else retry_policy(retry)
    preference = (
        options.concurrency
        if isinstance(concurrency, Omitted)
        else concurrency_preference(concurrency)
    )
    level = options.isolation if isinstance(isolation, Omitted) else isolation_level(isolation)
    if policy == options.retry and preference == options.concurrency and level == options.isolation:
        return options
    return TxnOptions(retry=policy, concurrency=preference, isolation=level)
