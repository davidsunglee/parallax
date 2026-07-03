# M7 — Bitemporal / Milestoning

`M7` is the signature capability: temporal entities whose rows are **milestones**
over `[from, to)` intervals, with as-of predicates **auto-injected** on read and
**milestone-chaining** writes that never mutate a value in place. Per the
dependency graph, `M7` depends on `M8` (writes happen inside a unit of work).
The temporal **algebra** (`asOf` / `asOfRange` / `history`) is M2; the **SQL
emission** is M3; the **infinity representation** is M0/M11. This module ties
them to observable behavior.

This module is authored in two slices. The **MVP scope** (DQ7) — **non-temporal**
(already covered by M1–M5) and **audit-only (processing-temporal)**, read **and**
write — is specified first, in the sections through "Milestone-chaining writes
(audit-only)". The **full bitemporal** model (the rectangle-split `*Until` trio
over two axes) and the **business-temporal-only** profile follow, in the
"Full bitemporal" and "Business-temporal-only" sections below; they **reuse** the
as-of read + write-sequence machinery defined for the MVP rather than introduce a
new mechanism.

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

### Affected-row conflict contract for closes

The close `UPDATE` **MUST** affect exactly **one** row. A close that affects
**zero** rows is an **error in any mode** — it **MUST NOT** silently succeed and
proceed to chain the replacement row (which would produce a duplicate or an
orphaned current row). The current-row predicate (`pk and out_z = infinity`) alone
is **not** a sufficient gate against a concurrent writer: a fully-committed
concurrent chain leaves a *new* current row that a stale close would silently
re-close — a lost update — so under optimistic mode the close carries an additional
`and <in_z> = ?` gate on the processing-from the unit of work **observed**:

```text
update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?
binds: [<txInstant>, <pk>, <infinity>, <observedInZ>]
```

The observed `in_z` is the optimistic-lock **version analogue** for a temporal
entity, which carries no version column (the `M10` composition, `M10 --> M7`). A
zero-row gated close is a **retriable conflict** (`updatedRows != 1`); a zero-row
*ungated* (locking-mode) close is a distinct **non-retriable** stale/consistency
error. On **success** the gate applies **per closed/inactivated current row** — one
gated `UPDATE` per such row, each binding *that row's* observed `in_z`, each
affecting exactly one row — while the chained replacement rows are plain ungated
`INSERT`s whose fresh `in_z = txInstant` is the advance a later stale writer then
misses. No version column exists or advances. Current rows of the same key
*outside* the written window keep their `in_z`: conflict granularity is the
milestone, not the primary key. The conflict/retry contract itself is `M10`.

## Full bitemporal

A **bitemporal** entity declares **two** `asOfAttribute` dimensions — one
`business` axis (`from_z`/`thru_z`, when a fact is *true in the world*) and one
`processing` axis (`in_z`/`out_z`, when the *system knew* it). A milestone is the
intersection of a business interval and a processing interval — a **rectangle** in
`(business × processing)` space. A row is **current** on an axis when its `to` on
that axis equals **infinity**; the **fully-current** row is current on *both*
(`thru_z = out_z = infinity`).

### Bitemporal as-of reads (both axes)

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

### Bitemporal writes — the rectangle split

The signature bitemporal write is the **rectangle split** (research §6). A value
is changed for a **bounded business window** `[businessFrom, businessTo)` while
the audit trail is preserved on the processing axis. This is the `updateUntil` /
`terminateUntil` contract; with `insertUntil` they form the **`*Until` trio**
(DQ11):

| Mutation | Observable SQL sequence |
|---|---|
| **insertUntil** | open one row whose **business** interval is the bounded window `[businessFrom, businessTo)` at processing `[txInstant, infinity)`; a single `insert` (no prior row to close) |
| **updateUntil** | **inactivate** the original current row by closing its **processing** axis (`out_z = txInstant`), then chain **three** new rows at fresh processing time `[txInstant, infinity)` — `head` business `[from_z, businessFrom)` (old value), `middle` business `[businessFrom, businessTo)` (new value), `tail` business `[businessTo, infinity)` (old value) |
| **terminateUntil** | inactivate the original (as above), then chain only **head** and **tail** — **no** `middle` — so the value is **absent** inside the window |

The split keeps the value unchanged before and after the window and changes it
**only inside** it (or, for `terminateUntil`, removes it only inside it). The
original survives as a row closed on the processing axis — the bitemporal audit
trail. Key invariants the suite pins down:

- The inactivation `UPDATE` is keyed by the **current-on-processing** predicate
  (`pk and out_z = infinity`), so only the open rectangle is inactivated; the
  three new rows are inserted **after** it.
- After an `updateUntil`, the observable current-on-processing state is exactly
  the `head` / `middle` / `tail` rectangles; the `middle` carries the new value.
- After a `terminateUntil`, the window `[businessFrom, businessTo)` is covered by
  **no** current-on-processing row.
- The inactivation `UPDATE` **MUST** affect exactly **one** row; a zero-row
  inactivation is an error in any mode (the affected-row conflict contract above).
  In optimistic mode the inactivation gates on the observed processing-from — and,
  when the key's current rows share an `in_z` (distinct business windows current at
  the same processing time), on the **business** discriminator too, to inactivate
  exactly the observed rectangle: `… and out_z = ? and from_z = ? and in_z = ?`.
  The observed `in_z` is the version analogue (`M10`, `M10 --> M7`); the chained
  `head` / `middle` / `tail` rows are ungated `INSERT`s at the fresh `in_z`.

This mirrors `GenericBiTemporalDirector.updateUntil` / `splitTailEnd`
(research §6, the bitemporal rectangle split).

### MAY-tier mutations

The remaining dated mutations Reladomo defines —
`insertWithIncrement` / `incrementUntil` (additive increment chaining),
`purge` (physically delete a milestone chain), and `inactivateForArchiving` —
are RFC-2119 **MAY**: an implementation **MAY** provide them, and the suite
**MAY** carry optional fixtures for them, but they are **not** part of the
required parity surface. They are deliberately excluded from the coverage gate
(the gate counts only MVP / fast-follow / definitely-do modules; the MAY-tier
exclusion lands with the gate itself).

## Business-temporal-only

A **business-temporal-only** (`unitemporal-business`) entity declares a single
`business` as-of dimension and **no** processing axis. Reads inject the same
single-axis predicate as the audit-only profile, but over `from_z`/`thru_z` (the
default is still **now** ⇒ `thru_z = infinity`). Writes are the **same
close-and-chain** shape as audit-only — close the open business row and chain a
new `[businessInstant, infinity)` row — but driven by the **business instant** the
change takes effect rather than the transaction instant, and with **no
processing-axis residual** (so no rectangle split). A business correction
therefore supersedes the prior value at the business date it becomes effective.

## How the harness verifies M7 (M12)

Two case shapes, both proven against real Postgres:

- **As-of read cases** carry an `operation` (defaulted `all`, explicit `asOf`,
  or `history`) and assert `expectedRows`. The defaulted-as-of case asserts the
  **injected** `out_z = ?` golden SQL + the expected current rows, so the
  default-injection rule is proven automatically. Native infinity actually
  executes (the current-row predicate binds `infinity` and the `history`
  projection reads back the open bound). A boundary as-of case pins a timestamp
  exactly equal to one row's upper bound and the next row's lower bound, proving
  the default half-open `[from, to)` rule (`from <= d and to > d`). A
  **bitemporal** read nests two `asOf` nodes and asserts the both-axis golden SQL
  and rows (each axis's predicate injected independently); a business-pinned-only
  bitemporal read proves the omitted processing axis defaults to now. A
  **business-only** read exercises the same rule over `from_z`/`thru_z`.
- **Write-sequence cases** carry a `writeSequence` (ordered mutations — `insert` /
  `update` / `terminate` for audit-only and business-only; the `insertUntil` /
  `updateUntil` / `terminateUntil` trio for full bitemporal) and
  `expectedTableState`. The harness **applies** the ordered DML golden SQL to a
  freshly-provisioned (empty) table, then asserts the resulting milestone rows
  equal `expectedTableState` — including the `out_z = infinity` current-row state
  and, for the rectangle split, the inactivated original + `head` / `middle` /
  `tail` rectangles. The DML statement count must equal the sum of the steps'
  declared statement counts and the case's `roundTrips`.

Rather than introspecting an implementation, the suite proves the *documented
golden SQL itself* produces the correct milestones — exactly the observable
contract an implementation must reproduce.
