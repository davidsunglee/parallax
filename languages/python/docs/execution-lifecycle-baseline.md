# Execution lifecycle overhead — recorded baseline

What observation costs in time, measured on one machine under stated conditions.
`docs/adr/0060-execution-observability-is-transient-and-provider-driven.md` asks
the first implementation to "establish a reproducible baseline" against three
initial targets and says it "may tighten these provisional ceilings". This is
that baseline.

Nothing here gates. `just python-report-lifecycle-overhead` is a `report`: it
passes no verdict and belongs to no aggregate, because no number in this
repository is enforced against elapsed time and every CI job runs the floating
`ubuntu-latest` label. The memory half of the same decision *is* gated, in
`tests/unit/test_execution_lifecycle_allocation_shape.py` and
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
| One Handler that keeps nothing | 1.55 | 3.45 | 10.3% | 9.1% |
| Safe logging alone, discarding every record | 2.81 | 4.90 | 18.7% | 19.5% |
| Safe logging alone, at INFO | 3.89 | 6.09 | 25.5% | 27.3% |
| Fan-out of three, tracing one root in ten | 4.34 | 5.34 | 28.3% | 19.4% |
| Fan-out of three, tracing every root | 4.68 | 7.53 | 30.3% | 38.6% |

Against ADR 0060's provisional ceilings — 5 µs p95 dispatch, 5% p50 and 10% p95
end-to-end:

- **dispatch p50 passes in every configuration**, with 13% headroom in the
  production shape, and **p95 misses in both production shapes** — by 7% in the
  sampled one;
- **end-to-end overhead misses at p50 by nearly a factor of six** against this
  port, and reaches the 5% ceiling once a statement costs roughly 360 µs.

Neither reading means anything without its method, which is the next two
sections.

## The overhead ratio is measured against the worst denominator there is

The port is in memory. A workload that issues four statements and waits for none
of them puts the whole cost of the operation in Python, so an overhead ratio
measured against it is the largest ratio this configuration's own cost can
produce, and any real deployment's denominator is strictly larger. A deployment
composing more Handlers than these three is a different numerator rather than a
case of this one. The report prints the arithmetic rather than the argument:

| Per-round-trip latency | p50 overhead, production fan-out |
|---|---|
| 0 µs (this measurement) | 28.4% |
| 50 µs — a fast local socket | 17.2% |
| 250 µs — a same-host container | 6.6% |
| 1 ms — a LAN round trip | 2.0% |
| 5 ms — a busy or remote database | 0.4% |

Four round trips are charged, which is what this workload issues. A real
transaction boundary adds a begin and a commit, so every row above understates
the denominator it would have.

## A p95 of a difference is not a measurement of the tail

Every tail here belongs to both arms — a scheduler preemption, a collection, a
frequency step — and subtracting one arm from the other combines their tails
rather than removing them. What that leaves is a percentile of the dispatch cost
plus whatever the two arms disagreed about, which bounds the dispatch tail in
neither direction: a preemption landing on the unobserved arm is subtracted out
of that pair's difference and understates it as surely as one landing on the
observed arm overstates it. The configuration that does almost no work shows the
scale of the disagreement: one Handler that keeps nothing measures a p95
difference of 3.45 µs against a p50 of 1.55, and that 1.9 µs gap is the two arms
disagreeing rather than dispatch.

Across repeated runs of the same code on the same machine, the p50 columns move
by a few percent and the p95 columns by up to 30%. Only the p50 is a measurement
of the work.

## Where the cost is

The configurations decompose the total, each line the difference from the one
above it:

- **1.55 µs/event is Parallax's own** — the descriptor, the opening call, the
  event, its sequence and activity assignment, the publisher's delivery, and the
  containment around calling a Handler.
- **+1.25 µs/event is the logging built-in describing every transition**, which
  it does whatever the Logger's level would keep: twenty field mappings per
  workload, two of them root summaries carrying ten counters each — the largest
  field set the Handler builds.
- **+1.08 µs/event is the standard library** doing what it was asked to: two
  records per workload survive the level filter at INFO, at roughly 11 µs each
  for `LogRecord` construction, the message rendering `QueueHandler.prepare`
  does, and the enqueue.
- **+0.45 µs/event is the fan-out, bounded metrics, and sampled tracing
  together** — three composed Providers, a composite Handler, and one traced root
  in ten.
- **+0.34 µs/event is tracing every root** instead of one in ten.

The runtime's own dispatch is 36% of the production total. Every other term is
work a Handler the configuration installed asked for: the built-in's field
mapping, the standard library's record, and the composed children's own.

## What the built-in pays for a record nobody keeps

The largest term after the runtime's own is the field mapping the logging
built-in builds for every transition, and the second configuration isolates it:
a CRITICAL Logger keeps none of the twenty records and the built-in still costs
1.25 µs/event, 29% of the production fan-out's dispatch. Which records survive
is the Logger's decision, asked once, by `Logger.log`, so the mapping is built at
every level.

That is what the numbers above describe, and nothing here is written as though
it were cheaper. `docs/deferred-ledger.md` D-79 carries the shape that recovers
the cost — a mapping materialized only if the standard library asks for it — and
why the short cut of asking the Logger's level first is not one.

## Rerunning it

```sh
just python-report-lifecycle-overhead
```

Read the p50 columns and the decomposition; read a p95 difference as the two
arms disagreeing rather than as dispatch. Comparing against the table above needs
the same conditions — the same machine class, no competing load, the same
interpreter — because the absolute numbers are machine-relative even where the
ratios are not.
