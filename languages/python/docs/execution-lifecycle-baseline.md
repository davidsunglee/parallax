# Execution lifecycle overhead — recorded baseline

What observation costs in time, measured on one machine under stated conditions.
`docs/adr/0060-execution-observability-is-transient-and-provider-driven.md` asks
the first implementation to "establish a reproducible baseline" against three
initial targets and says it "may tighten these provisional ceilings". This is
that baseline.

Nothing here gates. `just python-report-lifecycle-overhead` is a `report`: it
passes no verdict and belongs to no aggregate, because no number in this
repository is enforced against elapsed time and every CI job runs the floating
`ubuntu-latest` label. The memory half of the same acceptance criteria *is*
gated, in `tests/unit/test_execution_lifecycle_allocation_shape.py` and
`tests/unit/test_execution_lifecycle_retention.py`, because references give a
definite answer and a wall clock does not.

## Conditions

| | |
|---|---|
| Recorded | 2026-08-19 |
| Machine | darwin/arm64, 10 cores, mains power, no competing load started for the run |
| Interpreter | CPython 3.12.13 |
| Command | `just python-report-lifecycle-overhead` |
| Samples | 3000 timed pairs per configuration, 200 discarded first |
| Workload | one standalone `find`, then one `transact` writing on both flush triggers with a participating read between them — 20 events and 4 statements |
| Port | in memory: one row from each read, one affected row from each write |

## What the numbers were

Microseconds of Parallax-owned dispatch per delivered event, and end-to-end
overhead against the same workload with no Provider installed. Cheapest
configuration first; the first three exist to decompose the last two.

| Configuration | dispatch p50 | dispatch p95 | overhead p50 | overhead p95 |
|---|---|---|---|---|
| One Handler that keeps nothing | 1.52 | 3.05 | 10.1% | 9.4% |
| Safe logging alone, discarding every record | 2.26 | 4.10 | 15.0% | 17.5% |
| Safe logging alone, at INFO | 3.33 | 5.32 | 21.8% | 25.8% |
| Fan-out of three, tracing one root in ten | 3.84 | 5.77 | 25.1% | 32.3% |
| Fan-out of three, tracing every root | 4.02 | 6.64 | 26.4% | 36.9% |

Against ADR 0060's provisional ceilings — 5 µs p95 dispatch, 5% p50 and 10% p95
end-to-end:

- **dispatch p50 passes in every configuration**, with 23% headroom in the
  production shape, and **p95 misses in both production shapes** — by 15% in the
  sampled one;
- **end-to-end overhead misses at p50 by a factor of five** against this port,
  and reaches the 5% ceiling once a statement costs roughly 200 µs.

Neither reading means anything without its method, which is the next two
sections.

## The overhead ratio is measured against the worst denominator there is

The port is in memory. A workload that issues four statements and waits for none
of them puts the whole cost of the operation in Python, so an overhead ratio
measured against it is the largest ratio that absolute cost can produce, and any
real deployment's denominator is strictly larger. The report prints the
arithmetic rather than the argument:

| Per-round-trip latency | p50 overhead, production fan-out |
|---|---|
| 0 µs (this measurement) | 25.3% |
| 50 µs — a fast local socket | 15.2% |
| 250 µs — a same-host container | 5.9% |
| 1 ms — a LAN round trip | 1.8% |
| 5 ms — a busy or remote database | 0.4% |

Four round trips are charged, which is what this workload issues. A real
transaction boundary adds a begin and a commit, so every row above understates
the denominator it would have.

## A p95 of a difference is an upper bound, not a measurement

Every tail here belongs to both arms — a scheduler preemption, a collection, a
frequency step — and subtracting one arm from the other combines their tails
rather than removing them. The configuration that does almost no work shows the
scale of it: one Handler that keeps nothing measures a p95 difference of 3.05 µs
against a p50 of 1.52, and that 1.5 µs gap is noise rather than dispatch.

Across repeated runs of the same code on the same machine, the p50 columns move
by a few percent and the p95 columns by up to 30%. Only the p50 is a measurement
of the work.

## Where the cost is

The configurations decompose the total, each line the difference from the one
above it:

- **1.52 µs/event is Parallax's own** — the descriptor, the opening call, the
  event, its sequence and activity assignment, the publisher's delivery, and the
  containment around calling a Handler.
- **+0.74 µs/event is the logging built-in describing what a level above DEBUG
  could still want**, which it does whether or not that level would keep it: five
  transitions per workload, two of them root summaries carrying ten counters
  each — the largest field set the Handler builds.
- **+1.07 µs/event is the standard library** doing what it was asked to: two
  records per workload survive the level filter at INFO, at roughly 10 µs each
  for `LogRecord` construction and the enqueue.
- **+0.52 µs/event is the fan-out, bounded metrics, and sampled tracing
  together** — three composed Providers, a composite Handler, and one traced root
  in ten.
- **+0.18 µs/event is tracing every root** instead of one in ten.

The runtime's own dispatch is 40% of the production total, and no remaining term
is waste: each one builds something a configured Handler asked for.

## What changed since the first reading

The first measurement of this workload found the logging built-in costing
2.29 µs/event on top of the runtime — more than the runtime it observes — with
**1.24 µs of that paid whether or not any record survived the Logger's level**,
because `_LoggingHandler.handle` built every event's field mapping before calling
`Logger.log`. That is fixed rather than recorded: the Handler asks
`Logger.isEnabledFor` first and describes nothing the Logger would drop.

The realized saving is **0.58 µs/event** on the production fan-out (4.42 → 3.84
p50), not the 1.24 the decomposition predicted, and the gap is the guard's shape
rather than a measurement error. The guard is deliberately conservative: instead
of computing each event's exact level, which would need a second exhaustive match
over the whole algebra, it admits the two shapes that can be worth more than
DEBUG — a root activity's own Finished, and a Transaction Attempt's. Five of this
workload's twenty transitions are therefore still described at any level, and
those five include both root summaries, which are the most expensive records the
Handler builds. Making the guard exact would recover part of that residue for a
second copy of the algebra's dispatch, which is not a trade this module should
make.

Nothing else moved: the runtime's own 1.52 µs/event is unchanged, which is the
control the comparison needed.

The change alters no record. Every level, message, and field of every record is
identical with and without the guard across 72 configurations — six Logger levels
including one below DEBUG, a Handler level above the Logger's, three settings of
the process-wide `logging.disable`, both details, and a child Logger inheriting
its level from a parent — because `Logger.log` asks the same question before it
does anything else, and a Handler's own level filters records the Logger has
already created.

## Rerunning it

```sh
just python-report-lifecycle-overhead
```

Read the p50 columns and the decomposition; treat a p95 difference as an upper
bound. Comparing against the table above needs the same conditions — the same
machine class, no competing load, the same interpreter — because the absolute
numbers are machine-relative even where the ratios are not.
