"""What a run put on the wire, observed at the port (conformance support).

`then.statements` and `then.roundTrips` are facts about what reached the driver,
so the engine observes them at the Database Port rather than through the
lifecycle seam — which keeps both oracles answerable whether or not an Execution
Lifecycle Provider is installed, and keeps them from becoming one witness
wearing two names.

Three things have to hold for that observation to be usable as an emission: the
canonical `?`-placeholder spelling comes back and nothing else about the
statement moves, the read/write split is the port method that ran the statement,
and the work inside a transaction lands in the same ordered list as the work
outside one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from parallax.conformance._observed_port import StatementObservation
from parallax.core.db_port import Bind, DbPort, DocumentReadOrdinals, Row
from parallax.core.dialect import POSTGRES


class _Port:
    """A port that answers nothing and records the driver SQL it was handed."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, tuple[object, ...]]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        self.seen.append((sql, tuple(binds)))
        return []

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.seen.append((sql, tuple(binds)))
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(self)


def test_a_captured_statement_comes_back_in_canonical_form() -> None:
    inner = _Port()
    observation = StatementObservation()
    observing = observation.observing(inner, POSTGRES)

    observing.execute("select t0.id from account t0 where t0.id = %s", [7])

    (call,) = observation.calls
    # The driver saw its own placeholder spelling; the emission carries the
    # canonical one every other statement this engine reports is stated in.
    assert inner.seen == [("select t0.id from account t0 where t0.id = %s", (7,))]
    assert call.statement.sql == "select t0.id from account t0 where t0.id = ?"
    assert call.statement.binds == (7,)
    assert call.kind == "read"


def test_a_driver_placeholder_inside_a_quoted_identifier_stays_part_of_the_name() -> None:
    # A physical name is any non-empty string, so `rate%s` is an admissible
    # column and renders as a quoted identifier. Only the statement's own bind is
    # a placeholder: recovering the canonical spelling must leave the two names
    # standing, or a run would disagree with its golden over its own schema.
    observation = StatementObservation()
    observing = observation.observing(_Port(), POSTGRES)

    observing.execute('select t0."rate%s", t0."account%s" from t t0 where t0.id = %s', [7])

    (call,) = observation.calls
    assert call.statement.sql == 'select t0."rate%s", t0."account%s" from t t0 where t0.id = ?'


def test_the_canonical_spelling_survives_the_trip_out_to_the_driver_and_back() -> None:
    # The two translations are inverses over the WHOLE statement: a `?` inside a
    # quoted identifier or a string literal is that name's or that value's own
    # text, so the outbound direction may not turn it into a driver placeholder
    # and the inbound direction may not turn a name's `%s` into a bind.
    canonical = 'update "t%s" t0 set note = ? where t0."rate?" = ? and t0.tag = \'a?b\''
    observation = StatementObservation()
    observing = observation.observing(_Port(), POSTGRES)

    observing.execute_write(POSTGRES.to_driver_sql(canonical), ["x", 7])

    (call,) = observation.calls
    assert call.statement.sql == canonical


def test_the_split_is_the_port_method_that_ran_the_statement() -> None:
    observation = StatementObservation()
    observing = observation.observing(_Port(), POSTGRES)

    observing.execute("select 1 from t where c = %s", [1])
    observing.execute_write("update t set c = %s", [2])

    assert [call.kind for call in observation.calls] == ["read", "write"]
    assert [statement.sql for statement in observation.reads] == ["select 1 from t where c = ?"]
    assert [statement.sql for statement in observation.writes] == ["update t set c = ?"]
    assert observation.round_trips == 2
    assert [statement.sql for statement in observation.statements] == [
        "select 1 from t where c = ?",
        "update t set c = ?",
    ]


def test_work_inside_a_transaction_lands_in_the_same_ordered_list() -> None:
    # The work inside a demarcation runs on the connection the body receives
    # rather than on the port that opened it, so one run reads as one ordered
    # list however many connections it crossed.
    observation = StatementObservation()
    observing = observation.observing(_Port(), POSTGRES)

    observing.execute("select 1 from t", [])
    observing.transaction(lambda conn: conn.execute_write("insert into t values (%s)", [1]))

    assert [call.kind for call in observation.calls] == ["read", "write"]
    assert observation.boundaries == 1


def test_a_step_reads_its_own_statements_from_a_mark() -> None:
    observation = StatementObservation()
    observing = observation.observing(_Port(), POSTGRES)

    observing.execute("select 1 from a", [])
    mark = observation.round_trips
    observing.execute_write("update b set c = %s", [1])
    observing.execute("select 1 from b", [])

    assert [statement.sql for statement in observation.since(mark)] == [
        "update b set c = ?",
        "select 1 from b",
    ]
    # A find step asks for its READS: the DML a participating read force-flushed
    # belongs to the write step that buffered it, which reports its own
    # re-lowering, so one statement never lands under two pointers.
    assert [statement.sql for statement in observation.since(mark, "read")] == ["select 1 from b"]


def test_a_run_that_opened_no_transaction_counts_no_boundary() -> None:
    observation = StatementObservation()
    observation.observing(_Port(), POSTGRES).execute("select 1 from t", [])
    assert (observation.boundaries, observation.round_trips) == (0, 1)
