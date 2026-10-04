# m-bitemp-write — Bitemporal Rectangle-Split Writes

`m-bitemp-write` specifies the **Bitemporal write**: the *rectangle split* that
bounds a value change to a Valid-Time window while preserving the audit trail
on the Transaction-Time axis. Per the dependency graph, `m-bitemp-write` depends on
`m-txtime-write` — it reuses the close-and-chain machinery, extended to two axes.
The SQL emission is `m-sql`; the conflict/retry contract is `m-opt-lock`.

A milestone is the intersection of a Valid-Time interval and a Transaction-Time
interval — a **rectangle** in `(Valid Time × Transaction Time)` space. A row is current on an
axis when its `to` on that axis equals **infinity**; the **fully-current** row is
current on *both* (`thru_z = out_z = infinity`).

## The rectangle split

The signature bitemporal write is the **rectangle split** (research §6). A value
is changed for a **bounded Valid-Time window** `[validFrom, until)` while the
audit trail is preserved on the Transaction-Time axis. This is the `updateUntil` /
`terminateUntil` contract; with `insertUntil` they form the **`*Until` trio**
(DQ11):

| Mutation | Observable SQL sequence |
|---|---|
| **insertUntil** | open one row whose Valid-Time interval is `[validFrom, until)` at Transaction Time `[txInstant, infinity)`; a single `insert` (no prior row to close) |
| **updateUntil** | **inactivate** the original current row by closing Transaction Time (`out_z = txInstant`), then chain **three** new rows at fresh Transaction Time `[txInstant, infinity)` — `head` Valid Time `[from_z, validFrom)` (old value), `middle` Valid Time `[validFrom, until)` (new value), `tail` Valid Time `[until, infinity)` (old value) |
| **terminateUntil** | inactivate the original (as above), then chain only **head** and **tail** — **no** `middle` — so the value is **absent** inside the window |

The split keeps the value unchanged before and after the window and changes it
**only inside** it (or, for `terminateUntil`, removes it only inside it). The
original survives as a row closed on Transaction Time — the bitemporal audit
trail. Key invariants the suite pins down:

- The inactivation `UPDATE` addresses the **one current rectangle** it means to
  close: the primary key plus one exclusive upper bound per As-Of Axis
  (`pk and thru_z = ? and out_z = ?`, binding the observed rectangle's own
  Valid-Time end and the invariant Transaction-Time infinity). The key together
  with `out_z = infinity` alone would be ambiguous, because several disjoint
  Valid-Time rectangles of one key may be current on Transaction Time. The three
  new rows are inserted **after** it.
- After an `updateUntil`, the observable current-on-Transaction-Time state is exactly
  the `head` / `middle` / `tail` rectangles; the `middle` carries the new value.
- After a `terminateUntil`, the window `[validFrom, until)` is covered by **no**
  current-on-Transaction-Time row.
- The inactivation `UPDATE` **MUST** affect exactly **one** row; a zero-row
  inactivation is an error under either strategy (the affected-row conflict contract,
  `m-txtime-write`). Under Optimistic the inactivation additionally gates on the
  observed `txStart`, appended **after** the address:
  `… and thru_z = ? and out_z = ? and in_z = ?`. The observed `in_z` is the
  version analogue (`m-opt-lock`, `m-opt-lock --> m-temporal-read`); the chained
  `head` / `middle` / `tail` rows are ungated `INSERT`s at the fresh `in_z`. On a
  table-per-hierarchy concrete subtype the tag guard joins the identity
  predicates immediately after the primary key, before the per-axis upper bounds,
  exactly as it does for a Transaction-Time-Only close (`m-txtime-write` "Composed predicate
  order under Optimistic") — the observed-`in_z` gate still binds last.

This mirrors `GenericBiTemporalDirector.updateUntil` / `splitTailEnd`
(research §6, the bitemporal rectangle split). The same multi-row physical primary
key (domain key plus each axis's end column, `m-descriptor`) makes the chained
rectangles admissible.

## Plain (unbounded) bitemporal writes

Alongside the bounded `*Until` trio, the Bitemporal surface provides the
three **plain (unbounded) writes** — `insert`, `update`, `terminate` — that govern
a value from a **Valid-Time instant** `V` **through infinity** rather than
inside a bounded window. Each is the degenerate rectangle split obtained by letting
the window's Valid-Time upper bound go to infinity: where an `*Until` mutation carries
an explicit `until`, a plain mutation has none, so it never chains a `tail` back to
the old value beyond the window. Plain `insert` / `update` / `terminate` are all
**required** behavior (ADR 0021). `V` is the mutation input's `validFrom`, and the
window it governs is `[V, infinity)`.

| Mutation | Observable SQL sequence |
|---|---|
| **insert** (plain) | open one row whose Valid-Time interval is `[V, infinity)` at Transaction Time `[txInstant, infinity)`; a single `insert` with no prior row to close, so the row is fully current (`thru_z = out_z = infinity`) |
| **update** (plain) | inactivate the original by closing Transaction Time (`out_z = txInstant`), then chain two rows at fresh Transaction Time `[txInstant, infinity)` — `head` Valid Time `[from_z, V)` (old value) and a new `tail` Valid Time `[V, infinity)` (new value) |
| **terminate** (plain) | inactivate the original, then chain only a `head` over Valid Time `[from_z, V)`; `[V, infinity)` is covered by no current-on-Transaction-Time row |

The three form a natural progression. Plain `insert` establishes the fully-current
rectangle with no close; plain `update` and plain `terminate` share the same
inactivate + `head` prefix that preserves the prior value on Valid Time `[from_z, V)`,
and differ only in the tail — `update` chains a new `tail` carrying the new value on
`[V, infinity)`, whereas `terminate` chains no tail, so the value is **absent** from
`V` onward. Key invariants the suite pins down:

- Plain `insert` is a **single** `INSERT` of a fully-current row; there is no
  inactivation and no prior row to close, so the optimistic inactivation gate below
  does **not** apply to it. It is the unbounded degenerate of `insertUntil` and
  shares that mutation's canonical `INSERT` shape.
- For plain `update` and plain `terminate`, the inactivation `UPDATE` addresses the
  one current rectangle exactly as the `*Until` inactivation does
  (`pk and thru_z = ? and out_z = ?`), so only that rectangle is inactivated; the
  chained rows are inserted **after** it. Under Optimistic the inactivation gains
  the observed-`txStart` gate after the address, again exactly as the `*Until`
  inactivation does; the chained `head` / new `tail` are ungated `INSERT`s at the
  fresh `in_z`.
- The inactivation `UPDATE` **MUST** affect exactly **one** row; a zero-row
  inactivation is an error under either strategy (the affected-row conflict contract,
  `m-txtime-write`).
- After a plain `update`, Valid Time `[from_z, V)` is current on Transaction Time
  through the `head` (old value) and `[V, infinity)` through the new `tail` (new
  value). After a plain `terminate`, Valid Time `[from_z, V)` remains current
  through the `head` and `[V, infinity)` is covered by no current-on-Transaction-Time row.
- For `update` and `terminate`, the original survives as a row closed on the
  Transaction-Time axis — the bitemporal audit trail — so both prior Valid-Time
  history and Transaction-Time history stay observable to as-of reads. (Plain `insert`
  opens fresh history; there is no prior milestone to preserve.)

Plain `terminate` is a **temporal terminate, not a physical purge** (ADR 0021): no
milestone is deleted, only closed and chained; physically deleting a milestone chain
is the separate MAY-tier `purge`. The plain writes mirror `GenericBiTemporalDirector`'s
unbounded `insert` / `update` / `terminate` (research §6), the open-window / tailless
companions of the `*Until` trio.

## Observed writes span their requested extent

The tables above describe one current rectangle covering the whole window. A
keyed `update`, `updateUntil`, `terminate`, or `terminateUntil` written from a
source a read published is not confined to that rectangle. Its `validFrom` is
the source's own finite Valid-Time pin — the coordinate the read stood at, not
the observed rectangle's start — or, for a source an insertion of the same
attempt authored, that insertion's `validFrom`, its anchor (`m-unit-work`
*Insertion authority*). A source read at Valid-Time `latest` names no instant
and is refused, as is a source neither anchors. Its **requested extent** is
`[validFrom, until)`, through infinity when unbounded, and the write applies to
every current-on-Transaction-Time rectangle of the object that overlaps it:

- each overlapping rectangle is inactivated once, and its nonempty pieces are
  opened in Valid-Time order: a part outside the extent carries the
  rectangle's own values, and a part inside carries the assigned members over
  the rectangle's own unassigned values — or is not opened, for termination;
- a gap in coverage stays a gap: nothing is opened where no current rectangle
  exists, and the write continues to the coverage beyond it;
- a rectangle outside the extent is untouched, and adjacent pieces are never
  merged across two rectangles;
- every rectangle's inactivation precedes every opening (`m-sql`).

The observed rectangle is addressed and gated as an inactivation always is. A
rectangle no read of the write observed is read inside the flush that writes it
— the object's current rows over the part of the extent the observations do
not cover, read with the shared lock under Locking (`m-read-lock`) — and is
inactivated under its own observed `in_z` like any observed rectangle
(`m-unit-work` *deferred range unit*). Where observed writes of one object
compose (`m-unit-work` *Observed-State Coalescing*), the composition's segments
are applied the same way: each segment over each rectangle it overlaps, the
later-authored value winning where windows overlap. An assignment equal to a
rectangle's stored value is still assigned and still chains.

A write an insertion of the same attempt authorized observed no rectangle, so
the coverage it reaches is read from its anchor inside the flush that writes it,
and it requires a current rectangle containing that anchor. While the insertion
is still pending, its opening is the coverage: an edit bounded inside the
opening splits it, and nothing extends it beyond its own window (`m-unit-work`
*Same-transaction write coalescing*).

## Caller-addressed writes span their requested extent

A caller-addressed patch or replacement (`m-unit-work` *Caller-addressed
writes*) states its own `validFrom`, any instant inside a current rectangle, and
its requested extent is `[validFrom, until)`, through infinity when unbounded.
It requires a current rectangle containing `validFrom` whose `in_z` is the
caller's stated `ifTxStart`. That point condition describes the starting
rectangle alone, not the earlier state of every rectangle the extent reaches:
later rectangles are read inside the flush that writes them, including any
changed since the caller's query, and each is inactivated under its own `in_z`.

| Mutation | Inside its requested extent |
|---|---|
| Patch | Each overlapping rectangle takes the assigned members over its own unassigned values, exactly as an observed write's does; a gap and the coverage after a scheduled termination stay absent. |
| Replacement | Each overlapping rectangle takes the complete stated state, and every part of the extent no current rectangle covers — a gap, or the coverage after a scheduled termination — is opened with that state too, once. |

Every inactivation precedes every opening, the starting rectangle's first; a
replacement's opened gaps follow the pieces of the rectangles it inactivates.
Where the flush's read shows no rectangle containing `validFrom`, or one at
another `in_z`, the write is the caller's failed precondition before any
statement executes; where it shows more than one containing `validFrom`, the
write fails sooner, as Cardinality Corruption (`m-unit-work`). Under Optimistic the starting rectangle's inactivation gates
on the stated `ifTxStart`, and its shortfall is that failed precondition; every
later rectangle's gates on its own `in_z`, and its shortfall is an ordinary
conflict. Under Locking the starting rectangle was read under the shared lock
at submission and every rectangle the flush reads is read under it again, so no
inactivation is gated (`m-read-lock`).

A caller-addressed write composes with observed writes of one window and one
starting state (`m-unit-work` *Observed-State Coalescing*): a replacement's
extent survives an assignment composed after it and ends at a destruction,
which opens no gap only to destroy it.

Writes of one object over **disjoint** windows — adjacent ones included — are
separate operations, each with its own condition: a caller's `ifTxStart` at its
own `validFrom`, or the rectangle an observed source read. Both starts may lie
inside one stored rectangle. Pending together, they execute as one range that
inactivates each rectangle once and opens each operation's pieces inside its own
window; every rectangle holding a caller's start is inactivated first, in the
order the callers stated them, and one guard serves every start one rectangle
holds. A replacement fills gaps of its own window only, and a termination
destroys only its own.

```text
Stored: [January, infinity) at T0
Patch [February, April) from T0, then patch [June, August) from T0
Final:  [January, February) | [February, April) first patch
        | [April, June) | [June, August) second patch | [August, infinity)
```

When an ordering barrier separates such operations (`m-unit-work`
*Buffered, batched, ordered writes*), each executes on its own side. The later
one reads the coverage its window reaches when its turn comes, and finds the
rectangles the earlier one opened at the attempt's own `txInstant`: its
condition on the original they derive from was proven by the earlier
operation's guarded inactivation or held shared lock, and holds while every
rectangle derived from that original inside its window stands as it was opened.
It then revises or removes those rectangles like any the attempt opened, so the
attempt adds no history of its own.

**Concurrent creation in gaps is not coordinated.** The existing-row guards and
shared locks above protect rows that exist when the flush reads them. A
concurrent transaction may still open coverage inside a gap a replacement fills,
or a gap a patch passes over, and both commits can leave overlapping current
coverage; no isolation level is raised to prevent it.

**Untracked same-token changes are a configuration constraint.** A supported
deployment introduces no trigger or cascade that replaces or changes a tracked
current row outside the framework's own writes while leaving its address and
`in_z` as they were. Nothing here detects such a change; audit-only side effects
and effects on unrelated data are unaffected.

## Rectangles the attempt opened

The splits above inactivate a rectangle that existed before the attempt. A later
write of the **same** attempt whose observed rectangle the attempt's own earlier
flush opened has no history to preserve: closing it at the attempt's one
`txInstant` would leave an empty Transaction-Time interval whose physical key
collides with the rectangle that flush closed. Such a rectangle is therefore
**revised in place or removed** (`m-unit-work` *Rows the attempt opened*).
Whatever the predecessor, only **nonempty** successors are opened — a `head`
whose window starts where the rectangle starts covers no Valid Time and is not
opened.

When exactly one nonempty successor keeps the rectangle's complete physical
address — the key and its Valid-Time end, with Transaction-Time `infinity` — the
rectangle is updated in place into that successor, moving its `from_z` where the
successor starts later, and the other successors are inserted. Otherwise the
rectangle is deleted and every successor inserted. Both address the rectangle
exactly as an inactivation does, with the same observed-`in_z` gate under
Optimistic, and every resulting row keeps `in_z = txInstant`:

| Mutation of a rectangle `[s, e)` the attempt opened | Effect |
|---|---|
| **update** at `V` with `s < V` | update the rectangle into the changed tail `[V, e)`; insert the `head` `[s, V)` |
| **update** at `V = s` | update the rectangle's value in place |
| **updateUntil** `[V, U)` with `s < V < U < e` | update the rectangle into the carried tail `[U, e)`; insert `head` and `middle` |
| **terminateUntil** `[V, U)` with `s < V < U < e` | update the rectangle into the carried tail `[U, e)`; insert the `head` |
| **terminate** at `V` with `s < V` | delete the rectangle; insert the `head` `[s, V)` |
| **terminate** at `V = s` | delete the rectangle |

No end coordinate is moved to make a successor match, and ownership is never
inferred from `in_z = txInstant`. A rectangle that existed before the attempt is
inactivated exactly as above, so its Transaction-Time history stays immutable.

## What this module contributes to planning

Like `m-txtime-write`, this module does not emit its own statements: it describes
one authored mutation's **topology** to `m-unit-work`'s Write Planner, extended
to two axes. The description carries the same three parts:

- the **Close Cause** — `Superseded` for `update` / `updateUntil`, `Terminated`
  for `terminate` / `terminateUntil`;
- the **gate basis** — the observed `txStart` an optimistic inactivation binds;
  and
- the **successors** — the chained rectangles with their Insert Origins.

Origin is per successor, and the rectangle split is exactly where that matters.
A bounded `updateUntil` yields three successors: the `head` and the `tail` carry
the predecessor's represented state and are therefore `CarriedFrom` it, while the
`middle` carries the new value and is `ChangedFrom` it. A plain `update` yields a
`CarriedFrom` head and a `ChangedFrom` tail. A `terminate` or `terminateUntil`
yields only carried survivors: the **cause** records the absence, so a surviving
head or tail remains `CarriedFrom` and is never itself marked terminated. A plain
`insert` / `insertUntil` has no predecessor and its single row is `NewLineage`.

The description is neutral and names no SQL, dialect, or physical column, and it
is scoped to **one authored mutation** rather than to one resolved row — a
predicate-selected mutation resolving many rows yields one description the
planner applies across the resolved group. An implementation **MUST NOT** expose
a milestone plan, milestone step, or per-row expansion value on any cross-module
interface. The planner expands the description in place at the mutation's
already-decided position (ADR 0045) into the predecessor's effect — one Planned
Close, or for a rectangle the attempt opened a Planned Temporal Revision or
Removal — followed immediately by its Planned Insert successors in the facet's
canonical order — `head`, `middle`, `tail` where each exists and is nonempty —
with no unrelated step interleaved and no surviving group or identifier.

### Address and gate are separate

The rectangle an inactivation means to close and the concurrency condition that
detects a lost update are **separate** facts (ADR 0046). The **Milestone Target**
(`m-unit-work`) is the address: the primary key together with one write-required
exclusive upper bound **per As-Of Axis** — the observed predecessor's Valid-Time
end, and the invariant Transaction-Time `Infinity` that keeps an operational close
on the **current** rectangle. It carries no axis **start**, no Write Observation,
no gate, and no Effective Concurrency Strategy, and the planner derives it
**identically under both strategies**. Two axes are exactly why the Valid-Time end is required: a key
plus the current Transaction-Time bound may still select several disjoint current
rectangles.

The two ends are not interchangeable. The Transaction-Time end is invariantly
`Infinity`, but the Valid-Time end is whatever the observed predecessor carries —
`Infinity` for the rectangle running to the open Valid-Time bound, and a **finite**
instant for a bounded one, such as the `head` a prior split left behind. Binding a
constant `Infinity` on both axes would therefore address the open rectangle and
silently miss every bounded sibling.

The observed `in_z` rides the **gate**, never the address. That is why an
optimistic write based on a **stale** observation — one that named a current
rectangle when it was read and that another transaction has since superseded —
still addresses the current slot rather than copying a finite historical end into
it: closed history is never mutated, and the stale gate reports the conflict
instead (`m-txtime-write`). An observation of a rectangle the Transaction-Time
past holds never reaches planning at all, under either strategy: it could only come from
a view pinned at a finite Transaction-Time instant, which is read-only
(`m-identity-map`).

## Composition with inheritance

A rectangle-split write on an inheritance participant (a concrete subtype of a family
whose bitemporal axes are declared on the abstract root, `m-inheritance`) is the
**same** inactivate-and-chain sequence — the plain `terminate` and the windowed
`terminateUntil`, and their `update` / `*Until` siblings, are unchanged. Routing and
tag guards are physical, owned by `m-inheritance` / `m-sql`, not restated here; the
composed milestone shapes stay identical to the standalone witnesses, differing only
in table / tag routing. The corpus pins both strategies
(`m-inheritance-094` / `-095` terminate, `-096` / `-097` `terminateUntil`).

## MAY-tier mutations

The remaining dated mutations Reladomo defines —
`insertWithIncrement` / `incrementUntil` (additive increment chaining),
`insertForRecovery` (writing a milestone with **verbatim** Transaction-Time/Valid-Time
bounds rather than the transaction instant, to rebuild or backfill history without
the normal close-and-chain), `purge` (physically delete a milestone chain), and
`inactivateForArchiving` — are RFC-2119 **MAY**: an implementation **MAY** provide
them, and the suite **MAY** carry optional fixtures for them, but they are **not**
part of the required parity surface, and they are excluded from the coverage gate.

## How the harness verifies (`m-case-format`)

Write-sequence cases carry a `when.writeSequence` (the `insertUntil` /
`updateUntil` / `terminateUntil` trio, plus the plain unbounded `insert` /
`update` / `terminate` on a two-axis entity) and `then.tableState`. The harness
**applies** the ordered DML golden SQL (`then.statements`) to a freshly-provisioned
(empty) table, then asserts the resulting rows — the inactivated original (`out_z`
finite) plus the `head` / `middle` / `tail` rectangles current on Transaction Time
(`out_z = infinity`); a plain `update` asserts the inactivated original plus a
`head` and a new `tail`; a plain `terminate` asserts the inactivated original plus a
lone `head`, with `[V, infinity)` covered by no current-on-Transaction-Time row; a plain
`insert` asserts a single fully-current rectangle (`thru_z = out_z = infinity`) with
no inactivation. The DML statement count must equal the sum of the steps' declared
statement counts and the case's `then.roundTrips` (a plain `insert` step is 1
statement; a plain `terminate` step is 2 statements — inactivate + `head`; a plain
`update` step is 3 — inactivate + `head` + new `tail`). The standalone witnesses are
`m-bitemp-write-009-plain-insert`, `m-bitemp-write-006-plain-update-split`, and
`m-bitemp-write-007-plain-terminate`.
