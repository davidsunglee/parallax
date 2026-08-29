"""What every Object Query oracle behavior group is driven with.

The oracle asks a database for exactly two things — its dialect and the rows a
statement returns — so a test supplies them directly and never a container.
``ScriptedReads`` is the one recorder all the groups share: five modules
re-deriving it would be the coupling pattern this package exists to reverse.

Cases come from the shipped corpus, so a group asserts against real authored SQL,
binds, and observables rather than a synthetic model that could drift from what
the corpus actually declares. A group that needs a case to be wrong damages a
deep copy, which :func:`reference_harness.case.discover_cases` documents as the
supported way to obtain a mutable one.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, load_case

COMPATIBILITY_ROOT = Path(__file__).resolve().parents[3] / "core" / "compatibility"


class ScriptedReads:
    """Ordered canned results for a ``ReadExecutor``, recording every call made.

    Each entry of *results* answers one ``query`` call in order. An entry that is
    an ``Exception`` is raised instead of returned, which is how a driver failure
    is scripted without a driver. Asking for a result the script does not carry is
    a bug in the test rather than a case failure, so it raises a plain
    ``AssertionError`` that no ``CaseFailure`` expectation can absorb.

    It is deliberately narrower than a provider: no provisioning, no transaction
    control, no session lifecycle.
    """

    def __init__(
        self,
        dialect: str = "postgres",
        results: Sequence[list[dict[str, Any]] | Exception] = (),
    ) -> None:
        self.dialect = dialect
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._results = list(results)

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.calls.append((sql, tuple(binds)))
        index = len(self.calls) - 1
        if index >= len(self._results):
            raise AssertionError(
                f"the script carries {len(self._results)} result(s); query {index} asked "
                f"for one more: {sql!r}"
            )
        result = self._results[index]
        if isinstance(result, Exception):
            raise result
        return [dict(row) for row in result]

    @property
    def statements(self) -> list[str]:
        """The SQL text of every call, in the order it was made."""
        return [sql for sql, _binds in self.calls]


@pytest.fixture(scope="session")
def corpus_case() -> Callable[[str], Case]:
    """Load one shipped case by file name, deeply frozen and shared."""

    def load(name: str) -> Case:
        return load_case(COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / name)

    return load


@pytest.fixture
def damaged_case(corpus_case: Callable[[str], Case]) -> Callable[[str], Case]:
    """A private, fully mutable copy of one shipped case, for a group to break."""

    def load(name: str) -> Case:
        return copy.deepcopy(corpus_case(name))

    return load
