"""What the Unit Work Scenario package's tests are driven with.

Every test here drives the package's one export against a provider double, and
asserts only what a caller can see: whether the call returned or raised, what it
asked the database for and in which order, and — for the phases that precede a
database entirely — that it asked for nothing at all.

Two doubles, because the package makes two kinds of promise. A
:class:`ScriptedProvider` stands in for Postgres and MariaDB at the seam they
already satisfy, so which sessions were opened, what ran on each, and when each
committed are behaviour *of* the export observed at that seam, not internals. A
:class:`RefusingProvider` raises on every method, so a path that reaches no
database is proven by the absence of that raise rather than by inspecting
anything.

Cases come from the shipped corpus wherever the corpus authors the shape;
:func:`damaged_case` is the supported way to obtain a mutable copy to break. A
few shapes the corpus does not carry are built here in Python over real corpus
models, so the golden SQL and observables under test are still authentic.
"""

from __future__ import annotations

import contextlib
import copy
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, discover_cases, load_case
from reference_harness.unit_work_scenario import assert_unit_work_scenario

COMPATIBILITY_ROOT = Path(__file__).resolve().parents[3] / "core" / "compatibility"


# --- the script a provider answers from -------------------------------------


@dataclass(frozen=True)
class Rows:
    """The rows the next ``query`` returns."""

    rows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Affected:
    """The row count the next ``execute`` reports."""

    count: int = 1


type ScriptEntry = Rows | Affected | Exception


# --- the ordered record of what a run asked the database for ----------------
#
# A session is named by the order it was opened in, and ``None`` names the
# provider's own autocommit connection — the two boundaries a Scenario step can
# run on, and the whole of what distinguishes them from outside.


@dataclass(frozen=True)
class Reset:
    pass


@dataclass(frozen=True)
class Ddl:
    statements: int


@dataclass(frozen=True)
class Fixtures:
    table: str


@dataclass(frozen=True)
class Opened:
    session: int


@dataclass(frozen=True)
class Queried:
    session: int | None
    sql: str
    binds: tuple[Any, ...] = ()


@dataclass(frozen=True)
class Executed:
    session: int | None
    sql: str
    binds: tuple[Any, ...] = ()


@dataclass(frozen=True)
class Committed:
    session: int


@dataclass(frozen=True)
class RolledBack:
    session: int


type Call = Reset | Ddl | Fixtures | Opened | Queried | Executed | Committed | RolledBack


class _ScriptedSession:
    """One held transaction, answering from the provider's own single script."""

    def __init__(self, provider: ScriptedProvider, ordinal: int) -> None:
        self._provider = provider
        self._ordinal = ordinal
        self.dialect = provider.dialect

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        return self._provider._execute(self._ordinal, sql, binds)

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return self._provider._query(self._ordinal, sql, binds)

    def commit(self) -> None:
        self._provider.chronology.append(Committed(self._ordinal))

    def rollback(self) -> None:
        self._provider.chronology.append(RolledBack(self._ordinal))


class ScriptedProvider:
    """A ``DatabaseProvider`` answering from one immutable positional script.

    Every call that returns a value — a ``query`` on the provider or on any held
    session, an ``execute`` on either — takes the next script entry, whichever
    connection issued it, so the script IS the run's expected chronology of
    answers. An entry of the wrong kind for the call that reached it, or a call
    the script does not carry, is a bug in the test rather than a case failure and
    raises a plain ``AssertionError`` no ``CaseFailure`` expectation can absorb.
    An ``Exception`` entry is raised instead of answered, which is how a driver
    failure is scripted without a driver.

    Used as a context manager it also refuses a script the run did not exhaust, so
    a test cannot silently stop describing what it claims to describe.
    """

    def __init__(self, script: Sequence[ScriptEntry] = (), dialect: str = "postgres") -> None:
        self.dialect = dialect
        self.chronology: list[Call] = []
        self._script = list(script)
        self._consumed = 0
        self._sessions = 0

    # --- provisioning ------------------------------------------------------

    def reset(self) -> None:
        self.chronology.append(Reset())

    def apply_ddl(self, statements: Sequence[str]) -> None:
        self.chronology.append(Ddl(len(list(statements))))

    def load(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self.chronology.append(Fixtures(table))

    # --- the autocommit connection -----------------------------------------

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return self._query(None, sql, binds)

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        return self._execute(None, sql, binds)

    @contextlib.contextmanager
    def open_session(self) -> Iterator[_ScriptedSession]:
        ordinal = self._sessions
        self._sessions += 1
        self.chronology.append(Opened(ordinal))
        yield _ScriptedSession(self, ordinal)

    # --- what a test reads back --------------------------------------------

    @property
    def sessions(self) -> int:
        """How many sessions the run opened."""
        return self._sessions

    def __enter__(self) -> ScriptedProvider:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None and self._consumed != len(self._script):
            raise AssertionError(
                f"the script carries {len(self._script)} entr(ies); the run consumed "
                f"{self._consumed}"
            )

    # --- the script ---------------------------------------------------------

    def _next(self, what: str, sql: str) -> ScriptEntry:
        if self._consumed >= len(self._script):
            raise AssertionError(
                f"the script carries {len(self._script)} entr(ies); {what} "
                f"{self._consumed} asked for one more: {sql!r}"
            )
        entry = self._script[self._consumed]
        self._consumed += 1
        if isinstance(entry, Exception):
            raise entry
        return entry

    def _query(self, session: int | None, sql: str, binds: Sequence[Any]) -> list[dict[str, Any]]:
        self.chronology.append(Queried(session, sql, tuple(binds)))
        entry = self._next("query", sql)
        assert isinstance(entry, Rows), f"query {sql!r} reached a scripted {entry!r}"
        return [dict(row) for row in entry.rows]

    def _execute(self, session: int | None, sql: str, binds: Sequence[Any]) -> int:
        self.chronology.append(Executed(session, sql, tuple(binds)))
        entry = self._next("execute", sql)
        assert isinstance(entry, Affected), f"execute {sql!r} reached a scripted {entry!r}"
        return entry.count


class DatabaseRefused(Exception):
    """Raised by :class:`RefusingProvider` on any database access at all.

    Not a ``CaseFailure``: it stands in for the native driver exception a caller
    is promised arrives unchanged, so a test that sees it knows the package got
    through every judgement without an authored failure and then asked for a
    database.
    """


class RefusingProvider:
    """A ``DatabaseProvider`` that refuses every call it is given."""

    def __init__(self, dialect: str = "postgres") -> None:
        self.dialect = dialect

    def reset(self) -> None:
        raise DatabaseRefused("reset")

    def apply_ddl(self, statements: Sequence[str]) -> None:
        raise DatabaseRefused("apply_ddl")

    def load(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        raise DatabaseRefused("load")

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        raise DatabaseRefused("query")

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        raise DatabaseRefused("execute")

    def open_session(self) -> Any:
        raise DatabaseRefused("open_session")


def assert_judged(case: Case, dialect: str = "postgres") -> None:
    """Drive every judgement the package makes before it asks for a database.

    A case whose document is clean reaches provisioning, which the refusing
    provider declines; an authored defect raises ``CaseFailure`` first, so a
    ``pytest.raises(CaseFailure)`` around this call proves both the refusal AND
    that it cost zero database calls.
    """
    with pytest.raises(DatabaseRefused):
        assert_unit_work_scenario(case, RefusingProvider(dialect))


# --- cases ------------------------------------------------------------------


@pytest.fixture(scope="session")
def scenario_cases() -> list[Case]:
    """Every shipped Unit Work Scenario case, deeply frozen and shared."""
    return [case for case in discover_cases(COMPATIBILITY_ROOT) if case.is_scenario]


@pytest.fixture(scope="session")
def corpus_case() -> Callable[[str], Case]:
    """Load one shipped case by file name, deeply frozen and shared."""

    def load(name: str) -> Case:
        return load_case(COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / name)

    return load


@pytest.fixture
def damaged_case(corpus_case: Callable[[str], Case]) -> Callable[[str], Case]:
    """A private, fully mutable copy of one shipped case, for a test to rewrite.

    A shipped case is the starting point rather than the invariant: a test breaks
    it to witness a refusal, or varies it into a legal shape the corpus does not
    carry, and either way may rewrite any part of the copy.
    """

    def load(name: str) -> Case:
        return copy.deepcopy(corpus_case(name))

    return load
