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

## MAY-tier mutations

The remaining dated mutations Reladomo defines —
`insertWithIncrement` / `incrementUntil` (additive increment chaining),
`purge` (physically delete a milestone chain), and `inactivateForArchiving` —
are RFC-2119 **MAY**: an implementation **MAY** provide them, and the suite
**MAY** carry optional fixtures for them, but they are **not** part of the
required parity surface, and they are excluded from the coverage gate.

## How the harness verifies (`m-case-format`)

Write-sequence cases carry a `writeSequence` (the `insertUntil` / `updateUntil` /
`terminateUntil` trio) and `expectedTableState`. The harness **applies** the
ordered DML golden SQL to a freshly-provisioned (empty) table, then asserts the
resulting rows — the inactivated original (`out_z` finite) plus the `head` /
`middle` / `tail` rectangles current on processing (`out_z = infinity`). The DML
statement count must equal the sum of the steps' declared statement counts and the
case's `roundTrips`.
