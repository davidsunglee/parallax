"""What observation costs in time, measured against the same workload unobserved.

`docs/adr/0060-execution-observability-is-transient-and-provider-driven.md` sets
three initial targets — p95 no more than 5 microseconds of Parallax-owned
dispatch per event for three lightweight Handlers, and p50/p95 end-to-end
overhead no more than 5/10 percent — and calls for a reproducible baseline. This
records that baseline. It is a `report`: it passes no verdict and joins no
aggregate, because no number in this repository is enforced against elapsed
time, every CI job runs the floating `ubuntu-latest` label, and a wall clock that
gates turns an unrelated slow machine into a failed merge.

**Two arms, interleaved.** The same workload runs with no Provider installed and
against the production shape the acceptance criteria name — one
:class:`~parallax.core.execution_lifecycle.FanoutLifecycleProvider` over Safe
logging at INFO into an application-owned bounded queue, bounded metrics, and
sampled tracing into a bounded exporter. The arms alternate rather than running
one after the other, and the order inside each pair alternates too, so frequency
scaling, thermal drift, and a noisy neighbour land on both arms and largely
cancel. Pairing is also what makes the per-event figure honest: it comes from one
pair's own difference rather than from two independently ranked distributions.

**What is inside the measurement.** Everything Parallax owns: the descriptor and
the opening call, event creation and correlation, the fan-out, every Handler
call, and the enqueue into the application's queue. Outside it: the queue's
drain, the exporter, and the formatter, none of which this runs at all — the
queue is emptied between timed windows and no listener is attached.

**What the ratio is sensitive to, stated rather than assumed.** The port here is
in memory, so the denominator carries no database latency and almost no
materialization — one row back from each read, one affected row from each write.
That is the most adversarial denominator a real deployment could have, so the
recorded ratio is an upper bound and any real round trip only lowers it. The
report says so in arithmetic rather than in prose, by projecting the measured
absolute overhead across a range of plausible per-round-trip latencies.

**Two readings of the overhead, because they answer differently.** The ratio of
the two arms' own percentiles is the reading the initial targets are worded in,
and it is the noisier one: the unobserved arm's tail inflates its own p95, which
DEFLATES a p95 stated as a ratio of two independently ranked distributions. The
paired reading — the percentile of each pair's own ratio — is immune to that,
because both halves of every ratio were measured microseconds apart. Both are
printed.

**What a p95 of a DIFFERENCE can and cannot say.** Every tail this measurement
has belongs to both arms — a scheduler preemption, a collection, a frequency
step — and subtracting one arm from the other does not remove either one's
tail, it combines them. The p95 of a paired difference is therefore an upper
bound on the dispatch tail rather than an estimate of it, and only the p50 is
a measurement of the work itself. The cheapest configuration is what shows the
scale of that: its own p95 difference is twice its p50 while it does barely any
work at all.

Run it through `just python-report-lifecycle-overhead`.
"""

from __future__ import annotations

import logging
import logging.handlers
import platform
import queue
import sys
import time
from collections import deque
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Final, NamedTuple

from parallax.conformance.story_models import ACCOUNT_MODEL, Account
from parallax.core.base import DocumentReadOrdinals
from parallax.core.db_port import (
    Bind,
    CallbackRaised,
    Committed,
    DbPort,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProvider,
    FanoutLifecycleProvider,
    LoggingLifecycleProvider,
    RootExecution,
)
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

PAIRS: Final = 3_000
"""Timed pairs per configuration. Each contributes one sample to each arm, so the
p95 is ranked over three thousand observations rather than over a handful."""

WARMUP_PAIRS: Final = 200
"""Pairs run and discarded first, so import, first-call, and cache-fill costs are
outside every window that is kept."""

QUEUE_CAPACITY: Final = 10_000
"""The application-owned bounded queue's depth. Bounded is the contract; deep
enough that one timed window never fills it is the measurement's own need, since
a full queue would measure the standard library's overflow path instead."""

TRACE_CAPACITY: Final = 1_000
"""The bounded exporter's depth: a ring the sampled tracer writes into and
nothing drains."""

TRACE_SAMPLE: Final = 10
"""One root in ten is traced, which is what "sampled tracing" costs — the
sampling decision on every root and the span work on a tenth of them."""

ROW: Final[Row] = {"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1}

LATENCY_PROJECTION_US: Final = (0, 50, 250, 1_000, 5_000)
"""Per-round-trip database latencies the measured absolute overhead is projected
across, in microseconds: an in-process fake, a fast local socket, a same-host
container, a LAN round trip, and a busy or remote database. Charged per statement
the workload issues; a real transaction boundary adds a begin and a commit on top
of those, so every projection here understates the denominator it would have."""

DISPATCH_CEILING_US: Final = 5.0
P50_OVERHEAD_CEILING: Final = 0.05
P95_OVERHEAD_CEILING: Final = 0.10


class _MemoryPort:
    """An in-memory `m-db-port` with no boundary of its own.

    It answers one row to every read and one affected row to every write, so the
    denominator is the smallest a real workload could have and the two arms
    differ by the lifecycle alone. ``statements`` is what the latency projection
    charges its round trips against.
    """

    def __init__(self) -> None:
        self.statements = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.statements += 1
        return [dict(ROW)]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.statements += 1
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
        try:
            return Committed(body(self))
        except BaseException as raised:
            return RolledBack(CallbackRaised(raised))


class _MetricsHandler:
    """Bounded metrics: one counter per transition type, and nothing per event.

    Fourteen keys is the whole of it, however long the root runs, because the
    event algebra is closed — which is what "bounded per-root state" looks like
    for a metrics exporter.
    """

    __slots__ = ("_counts",)

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def handle(self, event: ExecutionEvent, /) -> None:
        name = type(event).__name__
        self._counts[name] = self._counts.get(name, 0) + 1


class _MetricsProvider:
    """Shares one counter table across every root, as a real exporter would."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return _MetricsHandler(self.counts)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        return None


class _TracingHandler:
    """One sampled root's spans, appended to a bounded ring the exporter owns."""

    __slots__ = ("_execution_id", "_spans")

    def __init__(self, execution: RootExecution, spans: deque[tuple[str, str, int, int]]) -> None:
        self._execution_id = str(execution.id)
        self._spans = spans

    def handle(self, event: ExecutionEvent, /) -> None:
        self._spans.append(
            (self._execution_id, type(event).__name__, event.sequence, event.activity_id)
        )


class _TracingProvider:
    """Samples one root in ``sample``, declining the rest.

    Declining is the sampler's whole mechanism: an unsampled root costs the
    decision and the opening call, and no event of it is ever built for this
    child at all. A sample of one traces everything, which is the configuration
    that puts three Handlers on every root rather than an average of two and a
    tenth.
    """

    def __init__(self, sample: int) -> None:
        self.spans: deque[tuple[str, str, int, int]] = deque(maxlen=TRACE_CAPACITY)
        self._sample = sample
        self._seen = 0

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        self._seen += 1
        if self._seen % self._sample:
            return None
        return _TracingHandler(execution, self.spans)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        return None


class _NullHandler:
    """A Handler that receives every event and does nothing with it.

    The floor: what remains once no Handler is doing any work is what Parallax
    itself spent building and delivering the event.
    """

    def handle(self, event: ExecutionEvent, /) -> None:
        return None


class _NullProvider:
    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return _NullHandler()

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        return None


class _CountingHandler:
    """Counts the events one workload delivers, so the per-event figure has a
    denominator that was observed rather than assumed."""

    __slots__ = ("_total",)

    def __init__(self, total: list[int]) -> None:
        self._total = total

    def handle(self, event: ExecutionEvent, /) -> None:
        self._total[0] += 1


class _CountingProvider:
    def __init__(self) -> None:
        self.total = [0]

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return _CountingHandler(self.total)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        return None


def _bounded_logger(
    records: queue.Queue[logging.LogRecord], name: str, level: int
) -> logging.Logger:
    """A Logger writing into an application-owned bounded queue and nowhere else.

    No listener drains it and no formatter runs, which is the separation the
    measurement needs: enqueueing is Parallax's caller's cost and belongs inside
    the window, while everything the queue feeds is the application's and does
    not.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(logging.handlers.QueueHandler(records))
    logger.setLevel(level)
    logger.propagate = False
    return logger


def _workload(db: Database) -> None:
    """One unit of work: a standalone read, then a transaction that writes on
    both flush triggers with a participating read between them.

    Every emitting activity kind appears — a Read root, a Transaction Invocation
    root, its Attempt, both Write Batch triggers, and a Database Call under each
    — so the per-event figure averages the mix an application really delivers
    rather than the cheapest transition.
    """
    db.find(Account.where(Account.id == 7)).result()

    def body(tx: Transaction) -> None:
        tx.insert(Account(id=11, owner="Hopper", balance=Decimal("1.00")))
        tx.find(Account.where(Account.id == 7)).result()
        tx.insert(Account(id=12, owner="Lovelace", balance=Decimal("2.00")))

    db.transact(body)


def _percentile[T: (int, float)](samples: Sequence[T], fraction: float) -> T:
    """The nearest-rank percentile of ``samples``: the smallest observation at or
    above which ``fraction`` of them lie."""
    ordered = sorted(samples)
    rank = max(1, min(len(ordered), int(-(-len(ordered) * fraction // 1))))
    return ordered[rank - 1]


def _timed(work: Callable[[], None]) -> int:
    started = time.perf_counter_ns()
    work()
    return time.perf_counter_ns() - started


class _Measurement:
    """Both arms' samples, and each pair's own difference and ratio.

    The paired series are kept rather than derived afterwards because pairing is
    the point: a difference or a ratio is only meaningful between two runs a few
    microseconds apart, and two independently sorted lists have lost which sample
    ran beside which.
    """

    def __init__(self) -> None:
        self.plain: list[int] = []
        self.observed: list[int] = []
        self.difference: list[int] = []
        self.ratio: list[float] = []


def _measure(
    plain: Database, observed: Database, records: queue.Queue[logging.LogRecord]
) -> _Measurement:
    """Run both arms ``PAIRS`` times, alternating which of the two goes first.

    The queue is emptied between pairs and outside every timed window, so its
    depth never becomes the thing being measured and its drain never lands in a
    sample.
    """
    for index in range(WARMUP_PAIRS):
        _workload(plain if index % 2 else observed)
        _workload(observed if index % 2 else plain)
    _drain(records)

    measurement = _Measurement()
    for index in range(PAIRS):
        if index % 2:
            plain_ns = _timed(lambda: _workload(plain))
            observed_ns = _timed(lambda: _workload(observed))
        else:
            observed_ns = _timed(lambda: _workload(observed))
            plain_ns = _timed(lambda: _workload(plain))
        measurement.plain.append(plain_ns)
        measurement.observed.append(observed_ns)
        measurement.difference.append(observed_ns - plain_ns)
        measurement.ratio.append(observed_ns / plain_ns - 1)
        _drain(records)
    return measurement


def _drain(records: queue.Queue[logging.LogRecord]) -> None:
    while not records.empty():
        records.get_nowait()


class _Shape(NamedTuple):
    """One workload run's own numbers: what it delivers and what it issues.

    Both are observed rather than assumed — the event count is the per-event
    figure's denominator, and the statement count is what the latency projection
    charges a round trip against.
    """

    events: int
    statements: int


def _shape() -> _Shape:
    port = _MemoryPort()
    counting = _CountingProvider()
    _workload(connect(port, ACCOUNT_MODEL, lifecycle_provider=counting))
    return _Shape(counting.total[0], port.statements)


def _conditions(shape: _Shape) -> list[tuple[str, str]]:
    return [
        ("python", f"{platform.python_version()} ({platform.python_implementation()})"),
        ("platform", f"{platform.system().lower()}/{platform.machine()}"),
        ("processor", platform.processor() or "unknown"),
        ("pairs", f"{PAIRS} timed, {WARMUP_PAIRS} discarded, per configuration"),
        ("workload", f"{shape.events} events and {shape.statements} statements"),
    ]


def _section(label: str, measurement: _Measurement, shape: _Shape) -> list[str]:
    plain_p50 = _percentile(measurement.plain, 0.50)
    plain_p95 = _percentile(measurement.plain, 0.95)
    observed_p50 = _percentile(measurement.observed, 0.50)
    observed_p95 = _percentile(measurement.observed, 0.95)
    delta_p50 = _percentile(measurement.difference, 0.50)
    delta_p95 = _percentile(measurement.difference, 0.95)

    lines = [
        f"  {label}",
        "                              p50            p95",
        f"    no provider      {plain_p50 / 1_000:11.2f} us {plain_p95 / 1_000:11.2f} us",
        f"    observed         {observed_p50 / 1_000:11.2f} us {observed_p95 / 1_000:11.2f} us",
        f"    paired delta     {delta_p50 / 1_000:11.2f} us {delta_p95 / 1_000:11.2f} us",
        f"    dispatch/event   {delta_p50 / shape.events / 1_000:11.3f} us "
        f"{delta_p95 / shape.events / 1_000:11.3f} us"
        f"   (ceiling {DISPATCH_CEILING_US:.0f} us p95)",
        f"    overhead, ranked {observed_p50 / plain_p50 - 1:11.1%} "
        f"{observed_p95 / plain_p95 - 1:11.1%}"
        f"   (ceilings {P50_OVERHEAD_CEILING:.0%} p50, {P95_OVERHEAD_CEILING:.0%} p95)",
        f"    overhead, paired {_percentile(measurement.ratio, 0.50):11.1%} "
        f"{_percentile(measurement.ratio, 0.95):11.1%}",
        "",
        "    the same p50 overhead once a statement costs a round trip:",
    ]
    for latency in LATENCY_PROJECTION_US:
        denominator = plain_p50 + shape.statements * latency * 1_000
        lines.append(f"      + {latency:>5} us per round trip   {delta_p50 / denominator:6.1%}")
    lines.append("")
    return lines


def _fanout(logger: logging.Logger, sample: int) -> FanoutLifecycleProvider:
    return FanoutLifecycleProvider(
        [LoggingLifecycleProvider(logger), _MetricsProvider(), _TracingProvider(sample)]
    )


def _configurations(
    records: queue.Queue[logging.LogRecord],
) -> list[tuple[str, ExecutionLifecycleProvider]]:
    """What is measured, cheapest first.

    The first three are what make the last two readable, because a total nobody
    can decompose is a number rather than a finding. A Handler that keeps nothing
    isolates what PARALLAX costs — descriptor, opening, event, sequence, activity,
    delivery — from what any Handler does with the event. The logging built-in is
    the only composed Handler heavy enough to matter, and it is measured twice:
    once at a level that emits its root summaries, and once at a level that
    discards every record, which separates what the built-in renders for every
    event from what the standard library then does with the few that survive.

    The last two are the production shape, twice, because the two documents this
    answers to name different ones: the acceptance criteria say sampled tracing,
    which leaves two Handlers active on most roots, and the initial dispatch
    target is stated for three lightweight Handlers, which is what tracing every
    root gives.
    """
    emitting = _bounded_logger(records, "parallax.lifecycle.overhead", logging.INFO)
    silent = _bounded_logger(records, "parallax.lifecycle.overhead.silent", logging.CRITICAL)
    return [
        ("one Handler that keeps nothing", _NullProvider()),
        ("Safe logging alone, discarding every record", LoggingLifecycleProvider(silent)),
        ("Safe logging alone, at INFO", LoggingLifecycleProvider(emitting)),
        (
            f"fan-out of three, tracing one root in {TRACE_SAMPLE}",
            _fanout(emitting, TRACE_SAMPLE),
        ),
        ("fan-out of three, tracing every root", _fanout(emitting, 1)),
    ]


def main(argv: list[str]) -> int:
    """Measure and print; never judge.

    Exit codes: 0 — the measurement ran; 2 — usage error. There is no exit code
    for a number that is too large, deliberately.
    """
    if argv:
        print("usage: python tools/lifecycle_overhead.py", file=sys.stderr)
        return 2
    port = _MemoryPort()
    records: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=QUEUE_CAPACITY)
    shape = _shape()
    plain = connect(port, ACCOUNT_MODEL)
    lines = ["parallax execution lifecycle overhead", ""]
    lines += [f"  {name:<12}{value}" for name, value in _conditions(shape)]
    lines += [""]
    for label, provider in _configurations(records):
        observed = connect(port, ACCOUNT_MODEL, lifecycle_provider=provider)
        lines += _section(label, _measure(plain, observed, records), shape)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
