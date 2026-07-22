# m-txtime-write — Transaction-Time-Only Temporal Writes

`m-txtime-write` specifies milestone-chaining writes on Transaction Time:
a write chains milestone rows rather than mutating a value in place, producing the
audit trail. Per the dependency graph, `m-txtime-write` depends on `m-temporal-read`
(it shares the interval/as-of model) and `m-unit-work` (writes happen inside a
unit of work). The SQL emission is `m-sql`; the conflict/retry contract is
`m-opt-lock`.

## Transaction-Time-Only milestone-chaining writes

In Transaction-Time-Only mode there is no Valid-Time dimension, so the
chaining is the simple close-and-open form (the bitemporal *rectangle split* is
`m-bitemp-write`). The **MVP mutation surface** is `insert` / `update` /
`terminate` (DQ11); the `*Until` trio belongs to Bitemporal writes.

Let `txInstant` be the transaction's finite Transaction-Time instant.

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
close-old-insert-new discipline (research §6), restricted to Transaction Time.

### Composition with inheritance

A milestone-chaining write on an inheritance participant (a concrete subtype of a
family whose Transaction-Time axis is declared on the abstract root, `m-inheritance`) is
the **same** close-and-open sequence — `insert` / `update` / `terminate` are
unchanged. Routing and tag guards are physical, owned by `m-inheritance` / `m-sql`,
not restated here. The corpus proves Transaction-Time-Only terminate composed with both strategies
(`m-inheritance-090` / `-091`).

**Composed predicate order under optimistic mode.** A temporal close on a
table-per-hierarchy concrete subtype composes the tag guard with the observed-`in_z`
gate below, the direct extension of `m-opt-lock`'s gate-last invariant (*Optimistic
locking composes with inheritance*) to a milestone close: the tag guard rides the
**identity predicates** — immediately after the primary key, before the
current-row predicate — and the observed-`in_z` gate still binds **last**:

```text
update reading set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?
binds: [<txInstant>, <pk>, <tagValue>, <infinity>, <observedTxStart>]
```

There is no inheritance exception to *the gate binds last* for a temporal close
either — one absolute ordering holds whether the write is a keyed update or a
milestone close. The corpus pins this composed order (`m-inheritance-105`).

## Affected-row conflict contract for closes

The close `UPDATE` **MUST** affect exactly **one** row. A close that affects
**zero** rows is an **error in any mode** — it **MUST NOT** silently succeed and
proceed to chain the replacement row (which would produce a duplicate or an
orphaned current row). The current-row predicate (`pk and out_z = infinity`) alone
is **not** a sufficient gate against a concurrent writer: a fully-committed
concurrent chain leaves a *new* current row that a stale close would silently
re-close — a lost update — so under optimistic mode the close carries an additional
`and <in_z> = ?` gate on the `tx_start` the unit of work **observed**:

```text
update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?
binds: [<txInstant>, <pk>, <infinity>, <observedTxStart>]
```

The observed `in_z` is the optimistic-lock **version analogue** for a temporal
entity, which carries no version column (the `m-opt-lock` composition,
`m-opt-lock --> m-temporal-read`). A zero-row gated close is a **retriable
conflict** (`updatedRows != 1`); a zero-row *ungated* (locking-mode) close is a
distinct **non-retriable** stale/consistency error — a categorically different
outcome from the gated conflict, but not a new `m-db-error` category: `then`
carries no `errorClass` for either shape, since a conflict (gated or ungated) is
proven the same way every optimistic-lock conflict is, by the affected-row count
(`then.affectedRows`), never by a database error code. On **success** the gate applies
**per closed/inactivated current row** — one gated `UPDATE` per such row, each
binding *that row's* observed `in_z`, each affecting exactly one row — while the
chained replacement rows are plain ungated `INSERT`s whose fresh `in_z = txInstant`
is the advance a later stale writer then misses. No version column exists or
advances. Current rows of the same key *outside* the written window keep their
`in_z`: conflict granularity is the milestone, not the primary key. The
conflict/retry contract itself is `m-opt-lock`.

## Statement order when a set-based write materializes

A set-based (predicate-selected) Transaction-Time-Only write **materializes** to per-row
statements (`m-opt-lock`, ADR 0014; emission order is `m-sql`) — the set predicate
cannot collapse to one statement because each close is keyed by its own resolved
current-row (`pk and out_z = infinity`) and each chain carries that row's resolved
columns. The golden emits those statements in the resolving read's **resolved-row
order**, and each resolved row's **close-and-chain stays together as one adjacent
unit** — the row's close `UPDATE` immediately followed by its chain `INSERT` —
**never regrouped by statement kind** (all closes, then all inserts). This is the
multi-statement-per-row generalization of `m-sql`'s "one keyed per-object write per
resolved row": a `terminate` row contributes a lone close, an `update` row a
close-then-chain pair. `m-txtime-write-007` (terminate) and `m-txtime-write-009`
(update) are the corpus witnesses.

## How the harness verifies (`m-case-format`)

Write-sequence cases carry a `when.writeSequence` (ordered `insert` / `update` /
`terminate`) and `then.tableState`. The harness **applies** the ordered DML
golden SQL (`then.statements`) to a freshly-provisioned (empty) table, then asserts
the resulting milestone rows equal `then.tableState` — including the
`out_z = infinity` current-row state. The DML statement count must equal the sum of
the steps' declared statement counts and the case's `then.roundTrips`. Rather than
introspecting
an implementation, the suite proves the *documented golden SQL itself* produces
the correct milestones.
