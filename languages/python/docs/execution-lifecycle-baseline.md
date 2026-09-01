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
| Recorded | 2026-09-01 |
| Machine | darwin/arm64 (macOS 26.5.2) |
| Interpreter | CPython 3.14.7 |
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
| One Handler that keeps nothing | 1.59 | 2.45 | 9.7% | 12.8% |
| Safe logging alone, discarding every record | 2.49 | 3.30 | 15.3% | 16.3% |
| Safe logging alone, at INFO | 3.78 | 4.82 | 23.1% | 25.2% |
| Fan-out of three, tracing one root in ten | 4.29 | 5.37 | 26.2% | 27.5% |
| Fan-out of three, tracing every root | 4.49 | 5.27 | 27.4% | 24.1% |

Against ADR 0060's provisional ceilings — 5 µs p95 dispatch, 5% p50 and 10% p95
end-to-end:

- **dispatch p50 passes in every configuration**, with 14% headroom in the
  production shape, and **p95 misses in both production shapes** — by 7% in the
  sampled one and 5% in the other;
- **end-to-end overhead misses at p50 by more than a factor of five** against
  this port, and reaches the 5% ceiling once a statement costs roughly 350 µs.

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
| 0 µs (this measurement) | 26.1% |
| 50 µs — a fast local socket | 16.2% |
| 250 µs — a same-host container | 6.5% |
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
difference of 2.45 µs against a p50 of 1.59, and that 0.9 µs gap is the two arms
disagreeing rather than dispatch.

Across repeated runs of the same code on the same machine, the p50 columns move
by a few percent and the p95 columns by up to 30%. Only the p50 is a measurement
of the work.

## Where the cost is

The configurations decompose the total, each line the difference from the one
above it:

- **1.59 µs/event is Parallax's own** — the descriptor, the opening call, the
  event, its sequence and activity assignment, the publisher's delivery, and the
  containment around calling a Handler.
- **+0.90 µs/event is the logging built-in on a transition nobody keeps** —
  counting it, projecting the level and transition name its record would carry,
  and asking the Logger about that level. This configuration's Logger keeps none
  of the twenty records, so no field mapping is built for any of them and no
  record is made.
- **+1.28 µs/event is the two records INFO keeps and everything they cost** —
  the field mappings the built-in builds for them alone, one of them a root
  summary carrying ten counters, plus `LogRecord` construction, the message
  rendering `QueueHandler.prepare` does, and the enqueue: roughly 13 µs per
  surviving record.
- **+0.52 µs/event is the fan-out, bounded metrics, and sampled tracing
  together** — three composed Providers, a composite Handler, and one traced root
  in ten.
- **+0.20 µs/event is tracing every root** instead of one in ten.

The runtime's own dispatch is 37% of the production total. Every other term is
work a Handler the configuration installed asked for: the built-in's counting and
projection, the records a level kept, and the composed children's own. Each term
is a difference between two independently measured configurations, so a term can
move by the run-to-run spread of either of them — around 0.1 µs/event here —
without anything having changed.

## What changed since the eager reading

The reading this table replaces, taken 2026-08-19, charged the logging built-in
**+1.25 µs/event for describing every transition**, paid whatever the Logger's
level would keep: `_LoggingHandler.handle` built each event's field mapping and
handed it to `Logger.log`, which was then the only thing deciding whether a
record existed. Twenty mappings per workload, two records kept at INFO.

That is fixed rather than recorded. `handle` takes each event's exact level from
the one exhaustive match that already names its transition, asks
`Logger.isEnabledFor` about that level, and returns without describing anything
the Logger would drop. Counting stays eager, so a root summary's totals still
count the transitions nobody logged. No surviving record moved: same level,
message, key set, and values, and `extra=` is still a plain `dict`.

**Old → new on the p50, one machine and one interpreter.** What measures this
change is a before/after pair taken in one session on this machine and on
CPython 3.14.7: the "after" is the table above, and the "before" was taken on the
parent commit with the built-in still eager. Dispatch per event, p50:

| Configuration | before | after | change |
|---|---|---|---|
| One Handler that keeps nothing | 1.58 | 1.59 | +0.01 |
| Safe logging alone, discarding every record | 3.05 | 2.49 | −0.55 |
| Safe logging alone, at INFO | 4.22 | 3.78 | −0.44 |
| Fan-out of three, tracing one root in ten | 4.74 | 4.29 | −0.45 |
| Fan-out of three, tracing every root | 5.01 | 4.49 | −0.51 |

The first row is the control: it installs no logging Provider, so the change
cannot reach it, and its 0.01 µs move is well inside the 0.13 µs/event spread two
adjacent runs of the same code showed on this machine. It is the line that makes
the other four a measurement rather than a difference between two afternoons.

Nothing here compares against the 2026-08-19 table, and nothing should. The
interpreter moved from CPython 3.12.13 to 3.14.7 between the two recordings, so
every row of the table above moved for two reasons and only the paired
before/after separates them.

**Realized against predicted.** The term that was paid at every level is
configuration 2's dispatch minus configuration 1's — what the built-in costs when
its Logger keeps nothing — and on this interpreter it was 1.47 µs/event before
and is 0.90 after: 0.55 recovered, 38% of it. The residue is what stays eager by
design, and the second configuration isolates it at 21% of the production
fan-out's dispatch, against 29% before: counting every event so a root summary's
totals are true, the one match that answers the level, and the question to the
Logger. The design that authorized the work predicted about 0.58 µs/event, from
the measured recovery of an earlier, coarser guard on the production fan-out;
realized there is 0.45. This reading does not decompose the gap, and neither
does the arithmetic above — but the two guards are not the same trade. The
earlier one asked before matching, so an event it skipped cost it nothing else;
this one computes and allocates its projection for every event before asking. It
skips more events, eighteen of twenty rather than fifteen, and recovers less on
each.

**This document has narrated a guard's saving once before.** The 2026-08-19
reading recorded one, and a re-record later the same day withdrew it. What was
withdrawn could not compute an event's exact level: it asked whether a record
could be worth more than DEBUG, and carried a detector deciding whether a given
Logger was standard enough to be short-cut safely. Three Logger shapes an
application can legitimately configure each lost a record, and each was found by
narrowing the previous one. What is different now is the question rather than the
answer to it — the level asked about is the level `Logger.log` is given, from the
same match that names the transition, so there is no approximation to bound and
no detector to narrow. What is the same is the
exposure the standard idiom carries anywhere: a Logger whose `isEnabledFor` and
`log` disagree loses a record here as it would with any library that guards.
`spec/python.md` states the guard and that exposure; it is not a premise these
numbers rest on.

## Rerunning it

```sh
just python-report-lifecycle-overhead
```

Read the p50 columns and the decomposition; read a p95 difference as the two
arms disagreeing rather than as dispatch. Comparing against the table above needs
the same machine class and the same interpreter, on a machine doing nothing else,
because the absolute numbers are machine-relative even where the ratios are not.
