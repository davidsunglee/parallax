"""``parallax.snapshot.handle._options`` — the Database Root's transaction option
record, the field rules it shares with an explicit ``db.transact`` request, and
the private marker that keeps an omitted keyword distinguishable from every
value a caller could pass.

:class:`DatabaseOptions` is the one record three surfaces share (spec §5): the
root defaults ``connect`` takes, the resolved options an outer invocation runs
under, and what ``Transaction.options`` answers. It holds concrete values only —
never the marker — so a record read anywhere is complete. The field rules live
beside it because construction and an explicit request are held to the same
contract: the two core vocabularies are validated by their owning modules, and
the two scalar fields by the rules here.

A leaf of the handle package: it imports the core vocabularies and nothing from
its siblings, and both the composition root and the transaction runner import
it. ``Omitted`` and ``OMITTED`` carry no leading underscore because they cross
module boundaries inside the package; neither is re-exported through the
package's frozen ``__all__``, so the omission marker stays out of the public
vocabulary.
"""

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
