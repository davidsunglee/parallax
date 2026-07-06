# m-audit-write — Processing-Axis (Audit-Only) Temporal Writes

`m-audit-write` specifies **milestone-chaining writes** on the **processing axis**:
a write chains milestone rows rather than mutating a value in place, producing the
audit trail. Per the dependency graph, `m-audit-write` depends on `m-temporal-read`
(it shares the interval/as-of model) and `m-unit-work` (writes happen inside a
unit of work). The SQL emission is `m-sql`; the conflict/retry contract is
`m-opt-lock`.

## Milestone-chaining writes (audit-only)

In **audit-only** mode the processing axis has no business-date residual, so the
chaining is the simple close-and-open form (the bitemporal *rectangle split* is
`m-bitemp-write`). The **MVP mutation surface** is `insert` / `update` /
`terminate` (DQ11); the `*Until` trio lands with full bitemporal.

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

## Affected-row conflict contract for closes

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
entity, which carries no version column (the `m-opt-lock` composition,
`m-opt-lock --> m-temporal-read`). A zero-row gated close is a **retriable
conflict** (`updatedRows != 1`); a zero-row *ungated* (locking-mode) close is a
distinct **non-retriable** stale/consistency error. On **success** the gate applies
**per closed/inactivated current row** — one gated `UPDATE` per such row, each
binding *that row's* observed `in_z`, each affecting exactly one row — while the
chained replacement rows are plain ungated `INSERT`s whose fresh `in_z = txInstant`
is the advance a later stale writer then misses. No version column exists or
advances. Current rows of the same key *outside* the written window keep their
`in_z`: conflict granularity is the milestone, not the primary key. The
conflict/retry contract itself is `m-opt-lock`.

## How the harness verifies (`m-case-format`)

Write-sequence cases carry a `writeSequence` (ordered `insert` / `update` /
`terminate`) and `expectedTableState`. The harness **applies** the ordered DML
golden SQL to a freshly-provisioned (empty) table, then asserts the resulting
milestone rows equal `expectedTableState` — including the `out_z = infinity`
current-row state. The DML statement count must equal the sum of the steps'
declared statement counts and the case's `roundTrips`. Rather than introspecting
an implementation, the suite proves the *documented golden SQL itself* produces
the correct milestones.
