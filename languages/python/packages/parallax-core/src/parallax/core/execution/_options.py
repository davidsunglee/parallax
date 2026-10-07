from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.db_port import IsolationLevel, isolation_level
from parallax.core.unit_work import Concurrency, concurrency_preference

__all__ = [
    "OMITTED",
    "DatabaseOptions",
    "Omitted",
    "check_max_retries",
    "check_retry_optimistic_conflicts",
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


def check_max_retries(value: object) -> int:
    """``value`` as a retry bound, or ``ValueError``.

    A bound is a nonnegative built-in ``int``: ``bool`` is refused although it
    subclasses ``int``, because ``True`` reads as a flag rather than as the
    bound 1, and a fractional or otherwise non-integral value names no number of
    re-executions at all.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"max_retries must be a nonnegative int, got {value!r}")
    if value < 0:
        raise ValueError(f"max_retries must be >= 0, got {value}")
    return value


def check_retry_optimistic_conflicts(value: object) -> bool:
    """``value`` as the optimistic-conflict opt-in, or ``ValueError``.

    Strictly a ``bool``: the opt-in widens the retriable set, and a truthy value
    of another type would enable that silently.
    """
    if not isinstance(value, bool):
        raise ValueError(f"retry_optimistic_conflicts must be a bool, got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class DatabaseOptions:
    """The four transaction options a Database Root configures as defaults, and
    the resolved record every outer invocation runs under.

    ``max_retries`` bounds re-executions rather than attempts: ``0`` runs the
    callback once and ``N`` admits at most ``N + 1`` attempts. ``concurrency``
    is the Concurrency Preference each Entity's Effective Concurrency Strategy is
    derived from. ``retry_optimistic_conflicts`` adds an Optimistic Lock
    Conflict to the retriable set. ``isolation`` is the portable level every
    physical attempt asks the port for; the built-in default is Read Committed,
    requested concretely rather than left to the database's configured default.

    Every field is validated at construction under the same rules an explicit
    ``db.transact`` keyword meets, and ``None`` is invalid for all four: only an
    omitted keyword inherits.
    """

    max_retries: int = 10
    concurrency: Concurrency = "optimistic"
    retry_optimistic_conflicts: bool = False
    isolation: IsolationLevel = "read_committed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_retries", check_max_retries(self.max_retries))
        object.__setattr__(self, "concurrency", concurrency_preference(self.concurrency))
        object.__setattr__(
            self,
            "retry_optimistic_conflicts",
            check_retry_optimistic_conflicts(self.retry_optimistic_conflicts),
        )
        object.__setattr__(self, "isolation", isolation_level(self.isolation))


def patch_options(
    options: DatabaseOptions,
    *,
    max_retries: int | Omitted = OMITTED,
    concurrency: Concurrency | Omitted = OMITTED,
    retry_optimistic_conflicts: bool | Omitted = OMITTED,
    isolation: IsolationLevel | Omitted = OMITTED,
) -> DatabaseOptions:
    """Apply one partial option patch, reusing ``options`` when unchanged."""
    bound = (
        options.max_retries if isinstance(max_retries, Omitted) else check_max_retries(max_retries)
    )
    preference = (
        options.concurrency
        if isinstance(concurrency, Omitted)
        else concurrency_preference(concurrency)
    )
    opt_in = (
        options.retry_optimistic_conflicts
        if isinstance(retry_optimistic_conflicts, Omitted)
        else check_retry_optimistic_conflicts(retry_optimistic_conflicts)
    )
    level = options.isolation if isinstance(isolation, Omitted) else isolation_level(isolation)
    if (
        bound == options.max_retries
        and preference == options.concurrency
        and opt_in == options.retry_optimistic_conflicts
        and level == options.isolation
    ):
        return options
    return DatabaseOptions(
        max_retries=bound,
        concurrency=preference,
        retry_optimistic_conflicts=opt_in,
        isolation=level,
    )
