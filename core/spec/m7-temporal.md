# M7 — Bitemporal / Milestoning

`M7` is the signature capability: temporal entities whose rows are **milestones**
over `[from, to)` intervals, with as-of predicates **auto-injected** on read and
**milestone-chaining** writes that never mutate a value in place. Per the
dependency graph, `M7` depends on `M8` (writes happen inside a unit of work).
The temporal **algebra** (`asOf` / `asOfRange` / `history`) is M2; the **SQL
emission** is M3; the **infinity representation** is M0/M11. This module ties
them to observable behavior.

This phase specifies the **MVP scope** (DQ7): **non-temporal** (already covered
by M1–M5) and **audit-only (processing-temporal)**, read **and** write. Full
bitemporal (the rectangle-split `*Until` trio) and business-temporal-only mode
are later phases; they reuse the read + write-sequence machinery defined here.

## The as-of interval model

A temporal entity declares one or two `asOfAttribute` dimensions (M1). Each
dimension is a query-time virtual attribute backed by a **pair of timestamp
columns** — a `fromColumn` and a `toColumn` — forming a half-open interval
`[from, to)` (when `toIsInclusive` is `false`, the default). A row is **current**
on that axis when its `to` equals the **infinity** sentinel; the open bound is
the **database-native infinity** (M0: Postgres `'infinity'::timestamptz`), owned
by the M11 dialect seam.

Two axes are defined; the MVP uses one:

- **`processing`** (audit-only) — when the *system knew* a fact (`in_z`/`out_z`).
  This is the most-used mode and the one this phase exercises end-to-end.
- **`business`** — when a fact is *true in the world* (`from_z`/`thru_z`). Pinned
  here for completeness; its writes (the rectangle split) land with full
  bitemporal in a later phase.

An entity with one `asOfAttribute` is **unitemporal** (`unitemporal-processing`
or `unitemporal-business`); with two it is **bitemporal**. The `entity.temporal`
classification (M1) is derived from the dimensions declared.

## As-of read predicates (auto-injected)

The as-of predicate is **never written by the user** — it is derived from the
as-of model and injected into the query. For a single dimension pinned to an
instant `d`:

| Condition | Injected predicate | Binds |
|---|---|---|
| `d = infinity` (the current row) | `to = ?` | `[infinity]` |
| `d < infinity`, exclusive (`[from, to)`) | `from <= ? and to > ?` | `[d, d]` |
| `d < infinity`, inclusive (`[from, to]`) | `from < ? and to >= ?` | `[d, d]` |

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

## Milestone-chaining writes (audit-only)

A write to a temporal entity **chains milestone rows** rather than mutating in
place — this is what produces the audit trail. In **audit-only** mode the
processing axis has no business-date residual, so the chaining is the simple
close-and-open form (the bitemporal *rectangle split* is a later phase). The
**MVP mutation surface** is `insert` / `update` / `terminate` (DQ11); the
`*Until` trio lands with full bitemporal.

Let `txInstant` be the transaction's processing instant.

| Mutation | Observable SQL sequence |
|---|---|
| **insert** | open one current row: `insert … (in_z = txInstant, out_z = infinity)` |
| **update** | **close** the current row: `update … set out_z = ? where pk and out_z = ?` (`[txInstant, infinity]`), then **chain** a new current row: `insert … (in_z = txInstant, out_z = infinity)` with the new value |
| **terminate** | **close** the current row (as in update's first step) and **insert nothing** — the terminated state is the *absence* of any `out_z = infinity` row |

Key invariants the suite pins down:

- The close `UPDATE` is **keyed by the current-row predicate** (`pk and
  out_z = infinity`), never a blind in-place set — only the open milestone is
  closed.
- After an **update**, the prior value survives as a **closed** milestone
  (`out_z` finite); the new value is the current row (`out_z = infinity`). The
  observable state is **two** rows.
- After a **terminate**, **no** row has `out_z = infinity`.

This matches `AuditOnlyTemporalDirector` / `GenericBiTemporalDirector`'s
close-old-insert-new discipline (research §6), restricted to the processing axis.

## How the harness verifies M7 (M12)

Two case shapes, both proven against real Postgres:

- **As-of read cases** carry an `operation` (defaulted `all`, explicit `asOf`,
  or `history`) and assert `expectedRows`. The defaulted-as-of case asserts the
  **injected** `out_z = ?` golden SQL + the expected current rows, so the
  default-injection rule is proven automatically. Native infinity actually
  executes (the current-row predicate binds `infinity` and the `history`
  projection reads back the open bound).
- **Write-sequence cases** carry a `writeSequence` (ordered `insert` / `update` /
  `terminate` mutations) and `expectedTableState`. The harness **applies** the
  ordered DML golden SQL to a freshly-provisioned (empty) table, then asserts the
  resulting milestone rows equal `expectedTableState` — including the
  `out_z = infinity` current-row state. The DML statement count must equal the
  sum of the steps' declared statement counts and the case's `roundTrips`.

Rather than introspecting an implementation, the suite proves the *documented
golden SQL itself* produces the correct milestones — exactly the observable
contract an implementation must reproduce.
