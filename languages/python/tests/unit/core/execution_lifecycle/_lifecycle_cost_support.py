"""The seam values the lifecycle cost suites drive.

`core/spec/m-execution-lifecycle.md` states cost as a contract twice over: what
an operation nobody observes may allocate, and what an observed one may still
hold once it has finished. The first is graded in
``test_execution_lifecycle_allocation_shape.py`` and the second in
``test_execution_lifecycle_retention.py``, both through the seam a real
operation drives rather than through a whole query — the read AROUND the seam
allocates the driver SQL, the binds, the rows, and the graph, which end to end
swamps the seam's own cost by three orders of magnitude.

What that seam is driven WITH is here; what it is measured with is generic and
lives in ``memory_instruments``, which the two suites import beside this module.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore — the same convention the private
`parallax.snapshot._handle` modules follow. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core.db_port import (
    CanonicalWriteStatement,
    OrderedWriteResult,
    OrderedWriteResultComplete,
)
from parallax.core.metamodel import EntityIdentity
from parallax.core.sql_gen import LoweredStatement

__all__ = [
    "AFFECTED",
    "ORDERED",
    "STATEMENT",
    "TARGET",
    "present",
    "rows",
]

TARGET: Final = EntityIdentity("parallax.compatibility", "Account")
"""A namespaced Entity whose canonical spelling has to be BUILT, which is what
makes a seam that spells its target measure as an allocation."""

STATEMENT: Final = LoweredStatement("select id from account where id = $1", (7,))

AFFECTED: Final = 5_000
"""A driver's affected-row count, past the interpreter's small-integer cache."""


def rows(count: int) -> list[dict[str, object]]:
    """``count`` rows shaped as a driver hands them back."""
    return [{"id": index} for index in range(count)]


class _Untouchable:
    """Statements an ordered invocation presents, refusing every inspection:
    an unobserved invocation hands them to its transport and reads none."""

    __slots__ = ()

    def __len__(self) -> int:
        raise AssertionError("an unobserved ordered invocation counts no statement")

    def __getitem__(self, index: int, /) -> LoweredStatement:
        raise AssertionError("an unobserved ordered invocation reads no statement")

    def target(self, index: int, /) -> EntityIdentity:
        raise AssertionError("an unobserved ordered invocation spells no target")


ORDERED: Final = _Untouchable()

_COMPLETED: Final = OrderedWriteResultComplete((AFFECTED,))


def present(statements: Sequence[CanonicalWriteStatement] | _Untouchable) -> OrderedWriteResult:
    """An ordered transport answering one completed count, whatever it is handed."""
    del statements
    return _COMPLETED
