"""``parallax.conformance.concurrency_runner`` — the `when.concurrency` rounds
runner (m-read-lock behavioral matrix, COR-3 Phase 8 increment 6).

A `concurrencySuccess` / `error`-with-`when.concurrency` case proves a
GENUINELY two-session concurrency property — the shared read lock actually
blocks a writer, admits a second shared reader, or a projection's own
omission admits a writer — that a single-connection harness cannot provoke
(`m-case-format` "Error cases" / "concurrencySuccess"). This module hosts the
case-driven, TWO-SESSION choreography every such case shares:

- :func:`parse_rounds` parses a case's own `when.concurrency.rounds` into an
  ordered, per-node step plan (`ConcurrencyStep`) — the language-neutral
  golden statements + (`concurrencySuccess` only) each present step's
  `kind` / `expectRows`.
- :func:`run_rounds` drives it: each node (`A` / `B`) gets its OWN
  independent, non-autocommit session (the `Provisioner.peer` seam, threaded
  in EXPLICITLY as `peer_factory` — this module constructs no connections
  itself, m-db-port), tuned with a short session-scoped `lock_timeout` so a
  genuinely blocked lock wait fails fast rather than hanging the suite
  (`m-case-format` "Error cases": "the dialect's lock-contention tuning ...
  applied so a blocked lock fails fast"). Two persistent worker THREADS (one
  per node) execute the rounds in AUTHORED order, synchronized by a
  `threading.Barrier` at every round boundary, so a round where BOTH nodes
  act races genuinely (the deadlock shape) while a round where only one node
  acts still waits for its partner to finish theirs before the next round
  starts — the SAME thread/barrier choreography the provider-contract
  deadlock proof exercises by hand
  (`tests/provider/test_provider_contract.py`), generalized here to an
  arbitrary ordered round sequence rather than one hand-authored contention
  round.

Statements execute VERBATIM (`m-case-format`'s own case contract for this
shape — a `when.concurrency` round's `statements` ARE the golden, dialect-
keyed SQL, never lowered from a neutral instruction): a step with no
declared `kind` (the `error` shape never declares one) or `kind: "read"`
calls the port's `execute` (row-returning; harmless on DML too — psycopg
does not require a SELECT to read rows back, `cursor.description is None`
degrades to an empty list); `kind: "write"` calls `execute_write`. Grading
(the classified error for the `error` shape; `expectRows` per read step for
`concurrencySuccess`) is the CALLER's job (`tests/conformance/
test_run_sweep.py`) — this module reports only the raw per-step outcome
(observed rows, or the raised, already-classified `DatabaseError`), mirroring
the `boundary_runner` / `run_read_case` split between pure machinery and
test-side grading.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast, runtime_checkable

from parallax.conformance import case_format
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, Row
from parallax.core.dialect import Dialect

__all__ = [
    "ConcurrencyStep",
    "NodeOutcome",
    "PeerSession",
    "RoundsRun",
    "parse_rounds",
    "run_rounds",
]

# Postgres session-scoped lock-contention tuning (m-case-format "Error cases":
# the provider seam's `open_session` applies "the dialect's lock-contention
# tuning ... so a blocked lock fails fast"). Long enough that a genuinely
# admitted (non-blocking) statement never spuriously times out, short enough
# that a genuinely blocked one (m-read-lock-006's contended writer) fails
# fast rather than hanging the suite.
_LOCK_TIMEOUT: str = "2000ms"

_NODES: tuple[str, ...] = ("A", "B")


@runtime_checkable
class PeerSession(Protocol):
    """The two `m-db-port` verbs this runner drives (`execute` / `execute_write`
    — never `transaction`, since a peer session's own non-autocommit
    connection life IS its unit of work here, the SAME `Provisioner.peer`
    pattern the provider-contract deadlock proof drives by hand) PLUS its
    OWN connection lifecycle (`Provisioner.peer`): the rounds runner opens
    two independent, non-autocommit sessions and MUST close each itself once
    a case's choreography finishes (successfully or not) — releasing every
    lock the session held so the NEXT case's schema reset is never blocked
    behind a leaked open transaction. A narrower, purpose-built structural
    protocol rather than the full `~parallax.core.db_port.DbPort` (which
    declares `transaction` too, unused here, and no lifecycle method at all
    — a demarcated `Database` handle never closes its own port).
    """

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]: ...

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ConcurrencyStep:
    """One node's own step within one round (`m-case-format` `concurrencyStep`).

    ``kind`` is ``None`` for the `error` shape (whose only assertion is the
    classified error the contention round raises); `concurrencySuccess`
    declares it on every present step (`"read"` / `"write"`).
    """

    statements: tuple[tuple[str, tuple[Bind, ...]], ...]
    kind: str | None
    expect_rows: tuple[Mapping[str, object], ...] | None


def _statement_entries(raw: object, dialect_name: str) -> tuple[tuple[str, tuple[Bind, ...]], ...]:
    entries = cast("list[Mapping[str, object]]", raw)
    out: list[tuple[str, tuple[Bind, ...]]] = []
    for entry in entries:
        sql = entry["sql"]
        text = cast("Mapping[str, str]", sql)[dialect_name] if isinstance(sql, Mapping) else sql
        binds = tuple(cast("list[Bind]", entry.get("binds", [])))
        out.append((cast("str", text), binds))
    return tuple(out)


def _step(raw: Mapping[str, object], dialect_name: str) -> ConcurrencyStep:
    kind = raw.get("kind")
    expect_rows_raw = raw.get("expectRows")
    expect_rows = (
        tuple(cast("list[Mapping[str, object]]", expect_rows_raw))
        if isinstance(expect_rows_raw, list)
        else None
    )
    return ConcurrencyStep(
        statements=_statement_entries(raw["statements"], dialect_name),
        kind=cast("str | None", kind) if isinstance(kind, str) else None,
        expect_rows=expect_rows,
    )


def parse_rounds(
    case: case_format.Case, dialect_name: str
) -> tuple[dict[str, ConcurrencyStep], ...]:
    """A case's own `when.concurrency.rounds`, in authored order — each round a
    dict keyed by the PRESENT node labels only (`m-case-format`: "a node
    absent from a round is idle")."""
    when = cast("Mapping[str, object]", case.document["when"])
    concurrency = cast("Mapping[str, object]", when["concurrency"])
    raw_rounds = cast("list[Mapping[str, object]]", concurrency["rounds"])
    rounds: list[dict[str, ConcurrencyStep]] = []
    for raw_round in raw_rounds:
        round_steps: dict[str, ConcurrencyStep] = {}
        for node in _NODES:
            raw_step = raw_round.get(node)
            if raw_step is not None:
                round_steps[node] = _step(cast("Mapping[str, object]", raw_step), dialect_name)
        rounds.append(round_steps)
    return tuple(rounds)


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    """One node's own outcome for one round: the rows its statements returned
    (empty for a pure-DML step, or a step that never ran because the case
    declared none this round), XOR the `DatabaseError` its LAST statement
    raised — never both."""

    rows: tuple[Row, ...] = ()
    error: DatabaseError | None = None


@dataclass(frozen=True, slots=True)
class RoundsRun:
    """The rounds runner's own raw report: one :class:`NodeOutcome` per
    PRESENT (round, node) pair, keyed exactly as :func:`parse_rounds`'s own
    round dicts are — grading (error classification / `expectRows`) is the
    caller's job."""

    rounds: tuple[dict[str, NodeOutcome], ...]


def _execute_step(session: PeerSession, dialect: Dialect, step: ConcurrencyStep) -> tuple[Row, ...]:
    """Run one step's statements VERBATIM on ``session`` (`m-case-format`'s
    own case contract for this shape), returning the LAST statement's rows.

    Each canonical `?`-placeholder golden statement is translated to the
    dialect's own driver form (`Dialect.to_driver_sql`) immediately before
    execution — the SAME translation site every other run lane uses
    (`engine.run_error_case`), never baked in at parse time, so
    :func:`parse_rounds`'s own report stays the canonical golden text.
    `kind: "write"` calls `execute_write` (the DML verb, m-db-port); every
    other step (a `kind: "read"` step, or a `kind`-less `error`-shape step —
    a SELECT observing a held lock, or the contention round's own trigger
    DML) calls `execute`: `PostgresAdapter.execute` degrades to an empty
    list when the statement returns no rows (`cursor.description is None`),
    so it is a safe, verb-blind way to run either a read OR the case's
    authored DML without SQL-verb sniffing (`m-case-format`'s own `kind`
    discriminator is what exists to replace that, for the ONE shape —
    `concurrencySuccess` — whose grading needs the distinction at all).
    """
    rows: tuple[Row, ...] = ()
    for sql, binds in step.statements:
        driver_sql = dialect.to_driver_sql(sql)
        if step.kind == "write":
            session.execute_write(driver_sql, binds)
        else:
            rows = tuple(session.execute(driver_sql, binds))
    return rows


def _empty_outcomes() -> dict[int, NodeOutcome]:
    return {}


@dataclass(slots=True)
class _WorkerResult:
    outcomes: dict[int, NodeOutcome] = field(default_factory=_empty_outcomes)
    failure: BaseException | None = None


def run_rounds(
    rounds: Sequence[Mapping[str, ConcurrencyStep]],
    dialect: Dialect,
    peer_factory: Callable[[], PeerSession],
) -> RoundsRun:
    """Drive ``rounds`` over two independently-held peer sessions (m-read-lock
    behavioral matrix; `m-case-format` "Error cases" / "concurrencySuccess").

    Opens exactly two sessions via ``peer_factory`` (never constructs a
    connection itself), applies the session-scoped lock-contention tuning to
    each, then runs one persistent worker thread per node: each thread walks
    every round in order, executing its own node's step (when present) and
    synchronizing with its partner at a `threading.Barrier(2)` BEFORE and
    AFTER each round — so a round with only one active node still waits for
    its idle partner to reach the SAME boundary (no round starts before the
    previous one is fully finished on BOTH sides), while a round where BOTH
    nodes act races them genuinely (the classic two-session contention
    shape). A raised `DatabaseError` is CAUGHT and recorded as that node's
    own outcome for the round (never re-raised across the thread boundary,
    and never aborting the choreography — the whole point of the error
    shape is to observe exactly which node's statement raised, then finish
    the round cleanly); any OTHER exception aborts the barrier for the
    partner thread and re-raises here, loudly, as a genuine harness defect.
    Both sessions are closed unconditionally before returning (releasing
    every lock so the caller's NEXT case can reset the schema).
    """
    sessions: dict[str, PeerSession] = {node: peer_factory() for node in _NODES}
    for session in sessions.values():
        session.execute(f"set lock_timeout = '{_LOCK_TIMEOUT}'", [])

    barrier = threading.Barrier(len(_NODES))
    results: dict[str, _WorkerResult] = {node: _WorkerResult() for node in _NODES}

    def worker(node: str) -> None:
        result = results[node]
        session = sessions[node]
        try:
            for index, round_steps in enumerate(rounds):
                barrier.wait()
                step = round_steps.get(node)
                if step is not None:
                    try:
                        rows = _execute_step(session, dialect, step)
                        result.outcomes[index] = NodeOutcome(rows=rows)
                    except DatabaseError as exc:
                        result.outcomes[index] = NodeOutcome(error=exc)
                barrier.wait()
        except BaseException as exc:
            result.failure = exc
            barrier.abort()

    threads = [
        threading.Thread(target=worker, args=(node,), name=f"concurrency-{node}") for node in _NODES
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        for session in sessions.values():
            session.close()

    for node in _NODES:
        failure = results[node].failure
        if failure is not None:
            raise failure

    return RoundsRun(
        rounds=tuple(
            {
                node: results[node].outcomes[index]
                for node in _NODES
                if index in results[node].outcomes
            }
            for index in range(len(rounds))
        )
    )
