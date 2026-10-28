"""The port's own portable vocabularies (m-db-port). Docker-free.

For isolation: what the closed set is, that a name outside it is refused as the
caller's mistake rather than carried on to a database that would refuse it
later, and what an accepted name comes back as. For acquisition failure: which
reasons a caller can be given at all. For read intent: that it is absent unless
a caller asserts it, and that every port standing in for another forwards it.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import get_args

import pytest

from parallax.conformance._mechanism.transaction_control import write_connection
from parallax.conformance.boundary_runner import FaultInjectingPort
from parallax.core.db_port import (
    ISOLATION_LEVELS,
    AcquisitionReason,
    ConnectionContext,
    ConnectionContextSource,
    DatabaseConnection,
    DocumentReadOrdinals,
    InvalidAuthorizationError,
    PipelineStatement,
    Row,
    TransactionOutcome,
    isolation_level,
)
from parallax.core.dialect import POSTGRES, Dialect
from tests._support.db_port import ConnectsAsItself, body_outcome
from tests._support.temporal_write_transport import CountingConnection, PortTally


class UnhashableName(str):
    """A ``str`` subclass no set can be asked about.

    It passes every type check a level name passes, so it is what separates
    validating by membership (which hashes, and would raise ``TypeError``) from
    validating by comparison.
    """

    __hash__ = None  # type: ignore[assignment]


def test_the_vocabulary_is_exactly_three_levels() -> None:
    assert set(ISOLATION_LEVELS) == {"read_committed", "repeatable_read", "serializable"}


@pytest.mark.parametrize("level", sorted(ISOLATION_LEVELS))
def test_every_level_of_the_vocabulary_is_returned_unchanged(level: str) -> None:
    assert isolation_level(level) == level


@pytest.mark.parametrize(
    "value",
    [
        "read uncommitted",  # a real level, deliberately outside the vocabulary
        "repeatable read",  # a database's own spelling rather than the portable one
        "REPEATABLE_READ",  # the vocabulary is exact, not case-folded
        "",
        None,
        3,
        [],  # unhashable: a set membership test alone would raise TypeError here
        {"level": "serializable"},
        UnhashableName("bogus"),  # unhashable AND a str: it clears an isinstance guard
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"isolation must be one of \['read_committed', "):
        isolation_level(value)


def test_an_accepted_level_comes_back_as_a_plain_hashable_str() -> None:
    level = isolation_level(UnhashableName("serializable"))

    assert level == "serializable"
    assert {level: "an adapter's per-level spelling"}


def test_a_connection_context_source_declares_resource_free_context_creation() -> None:
    class _Source:
        def new_context(self) -> ConnectionContext:
            raise AssertionError("the structural check must perform no I/O")

    assert isinstance(_Source(), ConnectionContextSource)


def test_invalid_authorization_is_a_caller_value_error() -> None:
    assert issubclass(InvalidAuthorizationError, ValueError)


def test_an_acquisition_names_one_of_six_reasons_for_granting_nothing() -> None:
    # Read back off the alias rather than off a table that projects it, so a
    # member added on one side and not the other is caught here rather than as
    # a lookup that raises on the one acquisition that failed that way.
    assert set(get_args(AcquisitionReason.__value__)) == {
        "timeout",
        "queue_rejected",
        "closed",
        "preparation_failed",
        "authorization_failed",
        "credentials_refused",
    }


@pytest.mark.parametrize(
    "method", [DatabaseConnection.execute, DatabaseConnection.execute_pipeline]
)
def test_read_intent_is_a_keyword_absent_unless_a_caller_asserts_it(
    method: Callable[..., object],
) -> None:
    parameter = inspect.signature(method).parameters["read_only"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is False


class _IntentRecordingPort(ConnectsAsItself):
    """A port recording which operation each submission reached and its read intent."""

    dialect: Dialect = POSTGRES

    def __init__(self) -> None:
        self.received: list[tuple[str, bool]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        del sql, binds, document_reads
        self.received.append(("execute", read_only))
        return []

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        self.received.append(("pipeline", read_only))
        return [[] for _ in statements]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        del sql, binds
        raise AssertionError("no write is submitted here")

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        del isolation, access_mode
        return body_outcome(self, body)


_DECORATORS: dict[str, Callable[[DatabaseConnection], DatabaseConnection]] = {
    "fault-injecting": lambda inner: FaultInjectingPort(inner, fault=None, persistent=False),
    "aborting": lambda inner: write_connection(inner, rollback=True),
    "counting": lambda inner: CountingConnection(inner, PortTally()),
}


_EACH_SUBMISSION = [
    ("execute", False),
    ("execute", True),
    ("pipeline", False),
    ("pipeline", True),
]


def _submit_each(port: DatabaseConnection) -> None:
    port.execute("select 1", ())
    port.execute("select 1", (), read_only=True)
    port.execute_pipeline((PipelineStatement("select 1"),))
    port.execute_pipeline((PipelineStatement("select 1"),), read_only=True)


@pytest.mark.parametrize("decorate", _DECORATORS.values(), ids=_DECORATORS.keys())
def test_a_decorating_port_forwards_each_submissions_read_intent_unchanged(
    decorate: Callable[[DatabaseConnection], DatabaseConnection],
) -> None:
    inner = _IntentRecordingPort()

    _submit_each(decorate(inner))

    assert inner.received == _EACH_SUBMISSION


@pytest.mark.parametrize("decorate", _DECORATORS.values(), ids=_DECORATORS.keys())
def test_the_port_a_decorated_boundary_hands_its_body_forwards_read_intent_unchanged(
    decorate: Callable[[DatabaseConnection], DatabaseConnection],
) -> None:
    inner = _IntentRecordingPort()

    decorate(inner).transaction(_submit_each)

    assert inner.received == _EACH_SUBMISSION


def test_a_pipeline_answered_statement_by_statement_keeps_the_batchs_read_intent() -> None:
    class _StatementPort(_IntentRecordingPort):
        execute_pipeline = ConnectsAsItself.execute_pipeline

    port = _StatementPort()

    port.execute_pipeline((PipelineStatement("a"), PipelineStatement("b")), read_only=True)
    port.execute_pipeline((PipelineStatement("c"),))

    assert port.received == [("execute", True), ("execute", True), ("execute", False)]
