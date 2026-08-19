"""What one run put on the wire, observed at the Database Port.

`then.statements` and `then.roundTrips` are the corpus's SQL and count oracles,
and both are facts about what reached the driver. This observes them at the port
because the Execution Lifecycle publishes no Database Call for a write or a
transaction yet: until it does, the port is the only place both oracles are
answerable for every lane. It is a stand-in for a seam still being built, not a
second witness the corpus wants — once the lifecycle covers the write and
transaction lanes, both oracles come off the delivered event stream, which is the
one source they were read from before the Execution Log was retired.

The canonical `?`-placeholder form is what every emission this engine reports
carries, so a captured driver statement is round-tripped back through
:meth:`~parallax.core.dialect.Dialect.from_driver_sql` before it joins them.
That recovery is a cost of observing driver SQL rather than the canonical
statement a Database Call event already carries. Binds cross the port unchanged
and need no such recovery.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from parallax.core.base import DocumentReadOrdinals
from parallax.core.db_port import Bind, DbPort, Row, TransactionOutcome
from parallax.core.dialect import Dialect
from parallax.core.sql_gen import LoweredStatement

__all__ = ["ObservedCall", "StatementObservation"]


@dataclass(frozen=True, slots=True)
class ObservedCall:
    """One attempted round trip, in canonical form.

    ``kind`` is which port method ran it, which is the same read/write split the
    corpus charges a materializing pair's resolve and its per-row writes to
    separate pointers by.
    """

    statement: LoweredStatement
    kind: Literal["read", "write"]


class StatementObservation:
    """Every statement one run put on the wire, in execution order.

    One observation spans however many handles, transactions, and attempts a run
    drives: a failed attempt's statements are recorded exactly like a committed
    one's, because a round trip is charged for reaching the database rather than
    for surviving.
    """

    __slots__ = ("_boundaries", "_calls")

    def __init__(self) -> None:
        self._calls: list[ObservedCall] = []
        self._boundaries = 0

    def observing(self, port: DbPort, dialect: Dialect) -> DbPort:
        """``port`` wrapped so every statement it runs lands in this observation."""
        return _ObservingPort(port, dialect, self)

    @property
    def calls(self) -> tuple[ObservedCall, ...]:
        return tuple(self._calls)

    @property
    def statements(self) -> tuple[LoweredStatement, ...]:
        return tuple(call.statement for call in self._calls)

    @property
    def reads(self) -> tuple[LoweredStatement, ...]:
        return tuple(call.statement for call in self._calls if call.kind == "read")

    @property
    def writes(self) -> tuple[LoweredStatement, ...]:
        return tuple(call.statement for call in self._calls if call.kind == "write")

    def since(
        self, mark: int, kind: Literal["read", "write"] | None = None
    ) -> tuple[LoweredStatement, ...]:
        """Every statement of ``kind`` issued after ``mark`` round trips.

        A run driving many steps through one handle reads each step's own
        emissions by taking :attr:`round_trips` before it and asking for the
        difference after, so one observation serves a whole scenario without a
        second observation per step.

        ``kind`` matters because a participating read force-flushes: the DML a
        read triggers belongs to the write step that buffered it, which reports
        its own pure re-lowering, so asking a find step for its reads is what
        keeps one statement from being emitted under two pointers.
        """
        return tuple(
            call.statement for call in self._calls[mark:] if kind is None or call.kind == kind
        )

    @property
    def round_trips(self) -> int:
        """Every attempted call, failed ones included; begin, commit, and
        rollback count none (`m-db-port`)."""
        return len(self._calls)

    @property
    def boundaries(self) -> int:
        """How many transaction demarcations this run opened.

        One PHYSICAL transaction attempt is one ``transaction`` call on the port
        (`m-unit-work`), so a retry loop's attempt count is readable here without
        the loop reporting a second tally of its own. A joined invocation opens
        no demarcation and is therefore not counted, which is the same
        distinction the lifecycle draws.
        """
        return self._boundaries

    def record_boundary(self) -> None:
        """Note one transaction demarcation, opened by this module's own wrapper."""
        self._boundaries += 1

    def record(self, kind: Literal["read", "write"], sql: str, binds: Sequence[Bind]) -> None:
        """Note one issued statement, in canonical form.

        Called by this module's own port wrapper alone: the two are one seam
        split across two classes so that the recording end can be handed to a
        handle while the reading end stays with the run that built it.
        """
        self._calls.append(ObservedCall(LoweredStatement(sql, tuple(binds)), kind))


class _ObservingPort:
    """A pass-through port that records before delegating.

    Recording BEFORE the call is what makes a failed statement count its round
    trip: the call is charged for having been issued, and the failure then
    propagates untouched.

    ``transaction`` wraps the connection its body receives, because the work
    inside a transaction runs on that connection rather than on this port; both
    wrappers write into the same observation, so one run reads as one ordered
    list however many connections it crossed.
    """

    __slots__ = ("_dialect", "_inner", "_observation")

    def __init__(self, inner: DbPort, dialect: Dialect, observation: StatementObservation) -> None:
        self._inner = inner
        self._dialect = dialect
        self._observation = observation

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self._observation.record("read", self._dialect.from_driver_sql(sql), binds)
        return self._inner.execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self._observation.record("write", self._dialect.from_driver_sql(sql), binds)
        return self._inner.execute_write(sql, binds)

    def transaction[T](self, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
        self._observation.record_boundary()
        return self._inner.transaction(
            lambda conn: body(_ObservingPort(conn, self._dialect, self._observation))
        )
