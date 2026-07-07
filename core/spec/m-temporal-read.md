# m-temporal-read — As-Of Temporal Reads

`m-temporal-read` is the **as-of read model**: temporal entities whose rows are
**milestones** over `[from, to)` intervals, with as-of predicates
**auto-injected** on read. It covers **all flavors** — single-axis (audit-only /
business-only) and full bitemporal reads. Per the dependency graph,
`m-temporal-read` depends on `m-op-algebra`: as-of *reads* are algebra-level. The
temporal **algebra** (`asOf` / `asOfRange` / `history`) is `m-op-algebra`; the
**SQL emission** is `m-sql`; the **infinity representation** is `m-core` /
`m-dialect`. Milestone-chaining **writes** are `m-audit-write`, `m-bitemp-write`,
and `m-business-only`.

## The as-of interval model

A temporal entity declares one or two `asOfAttribute` dimensions (`m-descriptor`).
Each dimension is a query-time virtual attribute backed by a **pair of timestamp
columns** — a `fromColumn` and a `toColumn` — forming a half-open interval
`[from, to)` (when `toIsInclusive` is `false`, the default). A row is **current**
on that axis when its `to` equals the **infinity** sentinel; the open bound is
the **database-native infinity** (`m-core`: Postgres `'infinity'::timestamptz`),
owned by the `m-dialect` seam.

Two axes are defined:

- **`processing`** (audit-only) — when the *system knew* a fact (`in_z`/`out_z`).
  This is the most-used mode and the one exercised end-to-end in the MVP.
- **`business`** — when a fact is *true in the world* (`from_z`/`thru_z`).

An entity with one `asOfAttribute` is **unitemporal** (`unitemporal-processing`
or `unitemporal-business`); with two it is **bitemporal**. The `entity.temporal`
classification (`m-descriptor`) is derived from the dimensions declared.

## As-of read predicates (auto-injected)

The as-of predicate is **never written by the user** — it is derived from the
as-of model and injected into the query. For a single dimension pinned to an
instant `d`:

| Condition | Injected predicate | Binds |
|---|---|---|
| `d = infinity` (the current row) | `to = ?` | `[infinity]` |
| `d < infinity`, exclusive (`[from, to)`) | `from <= ? and to > ?` | `[d, d]` |
| `d < infinity`, inclusive (`[from, to]`) | `from <= ? and to >= ?` | `[d, d]` |

This mirrors Reladomo's `AsOfEqOperation` (research §6). The "current row" case
is a **single** equality against infinity (one bind), not a two-sided range — so
the common as-of-now read is the cheapest possible predicate.

### Default-injection rule

> **An omitted as-of dimension defaults to "as of now."**

If a query does not pin a dimension, the implementation **MUST** inject the
**current-row** predicate (`to = infinity`) for it. Leaving out `processingDate`
therefore yields exactly the as-of-now result — the most common read. A query
that pins the dimension explicitly (`asOf(…, now)`) lowers to the **identical**
injected predicate; the compatibility suite proves the defaulted and explicit
forms produce the same golden SQL and rows.

### Operations

| Operation | Meaning |
|---|---|
| `asOf(operand, asOfAttr, date)` | pin a dimension to a single instant; `date = now` ⇒ the current milestone (`to = infinity`); a past instant ⇒ the `[from, to)` containment predicate |
| `asOfRange(operand, asOfAttr, from, to)` | scan every milestone whose interval overlaps `[from, to)` (edge-point read, not a single pin) |
| `history(operand, asOfAttr)` | return the **full** milestone set on that axis — no as-of predicate is injected, so superseded and current rows are all returned (Reladomo's `equalsEdgePoint`, renamed) |

The injected as-of term composes with any non-temporal predicate via `and`; the
temporal term is appended **after** the user predicate (so binds read
left-to-right: user binds, then the as-of bind(s)).

These rules are entity-local: each injected predicate is derived only from the
entity being read, its declared `asOfAttribute` dimensions, and the explicit pin
or default selected for those dimensions.

## Bitemporal reads (both axes)

A **bitemporal** entity declares **two** `asOfAttribute` dimensions — one
`business` axis (`from_z`/`thru_z`) and one `processing` axis (`in_z`/`out_z`). A
row is **current** on an axis when its `to` on that axis equals **infinity**; the
**fully-current** row is current on *both* (`thru_z = out_z = infinity`).

Each axis injects its own as-of predicate independently, exactly as the
single-axis rule above (`= infinity` for the current row; the `[from, to)`
containment for a past instant). A read pins **both** axes by composing the two
`asOf` nodes — one per dimension — so the injected terms `and` together:

| Read | Injected predicate |
|---|---|
| business now, processing now | `thru_z = ? and out_z = ?` (binds `[infinity, infinity]`) |
| business past `b`, processing now | `from_z <= ? and thru_z > ? and out_z = ?` (binds `[b, b, infinity]`) |
| business now, processing past `p` | `thru_z = ? and in_z <= ? and out_z > ?` (binds `[infinity, p, p]`) |
| business past `b`, processing past `p` | `from_z <= ? and thru_z > ? and in_z <= ? and out_z > ?` (binds `[b, b, p, p]`) |

The last form is the signature bitemporal read: *as the system believed at
processing instant `p`, what was true in the world at business instant `b`?* — it
reconstructs a historical belief, returning a milestone that may since have been
superseded on the processing axis. An omitted dimension still defaults to **now**
on that axis (the default-injection rule applies per-axis), so a query that pins
only the business date is implicitly "as the system knows it now."

A **business-temporal-only** read injects the single-axis fragment over
`from_z`/`thru_z` (the default is still **now** ⇒ `thru_z = infinity`);
`m-business-only` owns that flavor's writes.

## How the harness verifies as-of reads (`m-case-format`)

As-of read cases carry a `when.operation` (defaulted `all`, explicit `asOf`, or
`history`) and assert `then.rows`. The defaulted-as-of case asserts the
**injected** `out_z = ?` golden SQL + the expected current rows, so the
default-injection rule is proven automatically. Native infinity actually executes
(the current-row predicate binds `infinity` and the `history` projection reads
back the open bound). A boundary as-of case pins a timestamp exactly equal to one
row's upper bound and the next row's lower bound, proving the default half-open
`[from, to)` rule (`from <= d and to > d`). A **bitemporal** read nests two `asOf`
nodes and asserts the both-axis golden SQL and rows (each axis's predicate injected
independently); a business-pinned-only bitemporal read proves the omitted
processing axis defaults to now. A **business-only** read exercises the same rule
over `from_z`/`thru_z`.
