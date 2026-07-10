# m-bitemp-write — Bitemporal Rectangle-Split Writes

`m-bitemp-write` specifies the **full-bitemporal write**: the *rectangle split*
that bounds a value change to a business window while preserving the audit trail
on the processing axis. Per the dependency graph, `m-bitemp-write` depends on
`m-audit-write` — it reuses the close-and-chain machinery, extended to two axes.
The SQL emission is `m-sql`; the conflict/retry contract is `m-opt-lock`.

A milestone is the intersection of a business interval and a processing interval
— a **rectangle** in `(business × processing)` space. A row is **current** on an
axis when its `to` on that axis equals **infinity**; the **fully-current** row is
current on *both* (`thru_z = out_z = infinity`).

## The rectangle split

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
  inactivation is an error in any mode (the affected-row conflict contract,
  `m-audit-write`). In optimistic mode the inactivation gates on the observed
  processing-from — and, when the key's current rows share an `in_z` (distinct
  business windows current at the same processing time), on the **business**
  discriminator too, to inactivate exactly the observed rectangle:
  `… and out_z = ? and from_z = ? and in_z = ?`. The observed `in_z` is the
  version analogue (`m-opt-lock`, `m-opt-lock --> m-temporal-read`); the chained
  `head` / `middle` / `tail` rows are ungated `INSERT`s at the fresh `in_z`.

This mirrors `GenericBiTemporalDirector.updateUntil` / `splitTailEnd`
(research §6, the bitemporal rectangle split). The same multi-row physical primary
key (business key plus each axis's `fromColumn`, `m-descriptor`) makes the chained
rectangles admissible.

## Plain (unbounded) bitemporal writes

Alongside the bounded `*Until` trio, the full-bitemporal surface provides the
three **plain (unbounded) writes** — `insert`, `update`, `terminate` — that govern
a value from an **effective business date** `B` **through infinity** rather than
inside a bounded window. Each is the degenerate rectangle split obtained by letting
the window's upper business bound go to infinity: where an `*Until` mutation carries
an explicit `until`, a plain mutation has none, so it never chains a `tail` back to
the old value beyond the window. Plain `insert` / `update` / `terminate` are all
**required** behavior (ADR 0021). `B` is the mutation input's business instant (the
`businessFrom` of the step's neutral write input), and the window it governs is
`[B, infinity)`.

| Mutation | Observable SQL sequence |
|---|---|
| **insert** (plain) | open one row whose **business** interval is the unbounded window `[B, infinity)` at processing `[txInstant, infinity)`; a single `insert` — there is **no** prior row to close (the `businessTo = infinity` degenerate of `insertUntil`), so the row is **fully-current** (`thru_z = out_z = infinity`) |
| **update** (plain) | **inactivate** the original current row by closing its **processing** axis (`out_z = txInstant`), then chain **two** rows at fresh processing time `[txInstant, infinity)` — `head` business `[from_z, B)` (old value) and a new `tail` business `[B, infinity)` (new value); **no** `middle` and **no** old-`tail`, so the new value runs unbounded to infinity |
| **terminate** (plain) | inactivate the original (as above), then chain **only a `head`** — business `[from_z, B)` (the value before `B`) — with **no** `middle` and **no** `tail`, so `[B, infinity)` is left covered by no current-on-processing row |

The three form a natural progression. Plain `insert` establishes the fully-current
rectangle with no close; plain `update` and plain `terminate` share the same
inactivate + `head` prefix that preserves the prior value on business `[from_z, B)`,
and differ only in the tail — `update` chains a new `tail` carrying the new value on
`[B, infinity)`, whereas `terminate` chains no tail, so the value is **absent** from
`B` onward. Key invariants the suite pins down:

- Plain `insert` is a **single** `INSERT` of a fully-current row; there is no
  inactivation and no prior row to close, so the optimistic inactivation gate below
  does **not** apply to it. It is the unbounded degenerate of `insertUntil` and
  shares that mutation's canonical `INSERT` shape.
- For plain `update` and plain `terminate`, the inactivation `UPDATE` is keyed by
  the **current-on-processing** predicate (`pk and out_z = infinity`), so only the
  open rectangle is inactivated; the chained rows are inserted **after** it. In
  optimistic mode the inactivation gains the observed-processing-from gate (and,
  when the key's current rows share an `in_z`, the business discriminator too)
  exactly as the `*Until` inactivation does; the chained `head` / new `tail` are
  ungated `INSERT`s at the fresh `in_z`.
- The inactivation `UPDATE` **MUST** affect exactly **one** row; a zero-row
  inactivation is an error in any mode (the affected-row conflict contract,
  `m-audit-write`).
- After a plain `update`, business `[from_z, B)` is current-on-processing through
  the `head` (old value) and `[B, infinity)` through the new `tail` (new value).
  After a plain `terminate`, business `[from_z, B)` remains current through the
  `head` (the value before `B` is preserved) and `[B, infinity)` is covered by
  **no** current-on-processing row.
- For `update` and `terminate`, the original survives as a row closed on the
  processing axis — the bitemporal audit trail — so both the prior business history
  and the processing-axis history stay observable to as-of reads. (Plain `insert`
  opens fresh history; there is no prior milestone to preserve.)

Plain `terminate` is a **temporal terminate, not a physical purge** (ADR 0021): no
milestone is deleted, only closed and chained; physically deleting a milestone chain
is the separate MAY-tier `purge`. The plain writes mirror `GenericBiTemporalDirector`'s
unbounded `insert` / `update` / `terminate` (research §6), the open-window / tailless
companions of the `*Until` trio.

## MAY-tier mutations

The remaining dated mutations Reladomo defines —
`insertWithIncrement` / `incrementUntil` (additive increment chaining),
`purge` (physically delete a milestone chain), and `inactivateForArchiving` —
are RFC-2119 **MAY**: an implementation **MAY** provide them, and the suite
**MAY** carry optional fixtures for them, but they are **not** part of the
required parity surface, and they are excluded from the coverage gate.

## How the harness verifies (`m-case-format`)

Write-sequence cases carry a `when.writeSequence` (the `insertUntil` /
`updateUntil` / `terminateUntil` trio, plus the plain unbounded `insert` /
`update` / `terminate` on a two-axis entity) and `then.tableState`. The harness
**applies** the ordered DML golden SQL (`then.statements`) to a freshly-provisioned
(empty) table, then asserts the resulting rows — the inactivated original (`out_z`
finite) plus the `head` / `middle` / `tail` rectangles current on processing
(`out_z = infinity`); a plain `update` asserts the inactivated original plus a
`head` and a new `tail`; a plain `terminate` asserts the inactivated original plus a
lone `head`, with `[B, infinity)` covered by no current-on-processing row; a plain
`insert` asserts a single fully-current rectangle (`thru_z = out_z = infinity`) with
no inactivation. The DML statement count must equal the sum of the steps' declared
statement counts and the case's `then.roundTrips` (a plain `insert` step is 1
statement; a plain `terminate` step is 2 statements — inactivate + `head`; a plain
`update` step is 3 — inactivate + `head` + new `tail`). The standalone witnesses are
`m-bitemp-write-009-plain-insert`, `m-bitemp-write-006-plain-update-split`, and
`m-bitemp-write-007-plain-terminate`.
