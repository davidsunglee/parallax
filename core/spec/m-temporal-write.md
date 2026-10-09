# m-temporal-write — Temporal Writes

`m-temporal-write` specifies writes to temporal Entities: Transaction-Time-Only
milestone chaining, the Bitemporal rectangle split, and the **temporal
expansion** that realizes both — one Coverage Transform of a written object's
existing coverage, applied by one Predecessor Expansion to each existing
milestone it reaches. A temporal write chains milestone rows rather than
mutating a value in place, which is what produces the audit trail. Per the
dependency graph it depends on `m-write-plan`, whose Planned Write algebra and
Predecessor Rows it settles into; on `m-temporal-read`, whose intervals and axes
it shares with as-of reads; on `m-inheritance`, `m-core`, and `m-metamodel` for
the family-effective state it carries; and on `m-document-codec` for effective
comparison. `m-unit-work`'s Write Planner drives the expansion, the SQL emission
is `m-sql`, and the conflict/retry contract is `m-opt-lock`.

## Transaction-Time-Only milestone-chaining writes

In Transaction-Time-Only mode there is no Valid-Time dimension, so the
chaining is the simple close-and-open form; the bitemporal *rectangle split*
follows below. The **MVP mutation surface** is `insert` / `amend` / `replace` /
`terminate` (DQ11); the `*Until` forms belong to Bitemporal writes. An amendment
and a replacement chain alike on this axis: a replacement's successor states the
complete writable state where an amendment's keeps every member it does not
assign.

Let `txInstant` be the transaction's finite Transaction-Time instant.

| Mutation | Observable SQL sequence |
|---|---|
| **insert** | open one current row: `insert … (in_z = txInstant, out_z = infinity)` |
| **amend** | **close** the current row: `update … set out_z = ? where pk and out_z = ?` (`[txInstant, infinity]`), then **chain** a new current row: `insert … (in_z = txInstant, out_z = infinity)` with the new value |
| **terminate** | **close** the current row (as in an amendment's first step) and **insert nothing** — the terminated state is the *absence* of any `out_z = infinity` row |

Key invariants the suite pins down:

- The close `UPDATE` is **keyed by the current-row predicate** (`pk and
  out_z = infinity`), never a blind in-place set — only the open milestone is
  closed.
- After an **amend**, the prior value survives as a **closed** milestone
  (`out_z` finite); the new value is the current row (`out_z = infinity`). The
  observable state is **two** rows.
- After a **terminate**, **no** row has `out_z = infinity`.
- A keyed **amend** assigns literally (`m-unit-work` *Comparing an assigned
  member with its persisted value*), and an amendment assigning no member writes
  nothing. An amendment or replacement every assigned value of which the current
  row already holds leaves that row **unchanged**, whether a read observed the row, an
  insertion authorized the write, or a caller's condition names the row
  (*Unchanged milestones*, below): under Optimistic, where the database's
  write count includes unchanged rows, one guard keeps it —
  `update … set in_z = in_z where pk and out_z = ? and in_z = ?`
  (`[infinity, observedTxStart]`) — closing and chaining nothing, so the
  observable state stays **one** row; under Locking, and for a row the attempt
  opened, nothing is written at all. Without that proof the row is closed and
  its equal successor chained, as for a changed value.

This matches `AuditOnlyTemporalDirector` / `GenericBiTemporalDirector`'s
close-old-insert-new discipline (research §6), restricted to Transaction Time.

### The Transaction-Time past is never rewritten

Across the required parity surface, Parallax never rewrites the Transaction-Time
past. Every write **MUST** reach the new state by appending — closing the current
milestone and chaining whatever successors the mutation defines (`terminate`
defines none) — never by editing or removing a milestone that is already
superseded. A write based on an observation of a *historical* milestone is no
exception: it still addresses `out_z = infinity` and never copies a finite
historical end into that address (*The close addresses a Milestone Target*,
below). So the Transaction-Time past records what the system knew, and a read of
it is stable under concurrent writing.

The invariant reaches every surface that authors these writes, which is what
makes a view pinned at a finite Transaction-Time instant **read-only** rather
than merely inadvisable: mutating one raises the neutral
`transaction-time-pin-read-only` error and emits no DML (`m-identity-map`).

The append is what the suite grades, so the cases grading it discharge the
invariant. `m-temporal-write-002` and `-005` assert the resulting milestone rows —
`-005` chains onto persisted history and carries the superseded prior through
`then.tableState` unchanged; `m-temporal-write-003` asserts that a `terminate`
leaves no current row while deleting nothing; `m-identity-map-010` and
`m-temporal-write-032` assert the refusal at the mutation surface.

A current row the **same attempt** opened is not yet part of that past: no
committed state records it, and closing it at the attempt's one instant would
leave an empty `[txInstant, txInstant)` milestone whose physical key collides
with the row the attempt's earlier flush closed. A later write of the attempt
therefore revises or removes such a row instead of closing it (*A row the
attempt opened*, below), and the milestone it superseded keeps its closed
history unchanged.

The administrative operations that would widen this invariant are
the MAY-tier `insertForRecovery`, `purge`, and
`inactivateForArchiving` (*MAY-tier mutations*, below) — they write verbatim milestone bounds or physically
delete a milestone chain, and they sit outside the required parity surface.
Naming them here is non-normative and licenses nothing: providing one widens the
invariant deliberately, wherever that operation is specified, rather than taking
an exception this invariant admits.

### A row the attempt opened

Within one attempt, a write whose observed current row was opened by that
attempt's own earlier flush — by an `insert` or as an amendment's chained row —
addresses the row by the same Milestone Target and keeps its
`in_z = txInstant` (*Ownership disposal*, below):

| Mutation of a row the attempt opened | Observable SQL sequence |
|---|---|
| **amend** | revise the row in place: `update … set <changed members> where pk and out_z = ?` (`[infinity]`), chaining nothing |
| **terminate** | remove the row: `delete from … where pk and out_z = ?` (`[infinity]`) |

Under Optimistic the address is followed by the observed-`in_z` gate exactly as
a close's is. An amendment every assigned value of which the row already holds
writes nothing. Ownership is the attempt's record of what it opened, never an
`in_z` that happens to equal `txInstant`: a row an earlier attempt committed at
the same instant is closed as usual. After the attempt, the Transaction-Time
history holds each pre-attempt milestone closed once and one current row per
key, with no empty interval.

A write the insertion itself authorized after its insert flushed observed no
row: the object's current row is read inside the flush that writes it, and is
revised or removed as above (`m-unit-work` *Insertion authority*).

### A caller-addressed write

A caller-addressed amendment or replacement (`m-unit-work` *Caller-addressed
writes*) observed no row either: it states the `in_z` of the current row its
caller last observed as `ifTxStart`, and takes no Valid-Time bound. The current
row is read inside the flush that writes it, and is closed and chained as an
`amend` is — an amendment's chained row keeps every member it does not assign, a
replacement's states the complete writable state — or kept unchanged where every
value it assigns is one the row already holds, exactly as a source-authorized
write's is
(*Unchanged milestones*): the caller's condition establishes the write's
authority, not a demand for new history. Where that read finds no
current row, or one at another `in_z`, the write is its caller's failed
precondition before any statement executes; where it finds more than one current
row, the write fails sooner, as Cardinality Corruption (`m-unit-work`). Under
Optimistic the close's gate — or the guard keeping an unchanged row — binds the
stated `ifTxStart` rather than an observation, and its zero-row shortfall is
that failed precondition, never a retriable conflict. Under Locking the current
row was read whole under the shared lock at submission, and the flush reuses it
unless an earlier unit of the attempt has since changed it, when it reads the
row again under the lock (`m-unit-work` *Retained starting rows*); the close is
ungated.

## The rectangle split

A milestone is the intersection of a Valid-Time interval and a Transaction-Time
interval — a **rectangle** in `(Valid Time × Transaction Time)` space. A row is current on an
axis when its `to` on that axis equals **infinity**; the **fully-current** row is
current on *both* (`thru_z = out_z = infinity`).

The signature bitemporal write is the **rectangle split** (research §6). A value
is changed for a **bounded Valid-Time window** `[validFrom, until)` while the
audit trail is preserved on the Transaction-Time axis. This is the `amendUntil` /
`terminateUntil` contract; with `insertUntil` they form the **`*Until` trio**
(DQ11):

| Mutation | Observable SQL sequence |
|---|---|
| **insertUntil** | open one row whose Valid-Time interval is `[validFrom, until)` at Transaction Time `[txInstant, infinity)`; a single `insert` (no prior row to close) |
| **amendUntil** | **inactivate** the original current row by closing Transaction Time (`out_z = txInstant`), then chain **three** new rows at fresh Transaction Time `[txInstant, infinity)` — `head` Valid Time `[from_z, validFrom)` (old value), `middle` Valid Time `[validFrom, until)` (new value), `tail` Valid Time `[until, infinity)` (old value) |
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
- After an `amendUntil`, the observable current-on-Transaction-Time state is exactly
  the `head` / `middle` / `tail` rectangles; the `middle` carries the new value.
- After a `terminateUntil`, the window `[validFrom, until)` is covered by **no**
  current-on-Transaction-Time row.
- The inactivation `UPDATE` **MUST** affect exactly **one** row; a zero-row
  inactivation is an error under either strategy (*Affected-row conflict contract for
  closes*, below). Under Optimistic the inactivation additionally gates on the
  observed `txStart`, appended **after** the address:
  `… and thru_z = ? and out_z = ? and in_z = ?`. The observed `in_z` is the
  version analogue (`m-opt-lock`, `m-opt-lock --> m-temporal-read`); the chained
  `head` / `middle` / `tail` rows are ungated `INSERT`s at the fresh `in_z`. On a
  table-per-hierarchy concrete subtype the tag guard joins the identity
  predicates immediately after the primary key, before the per-axis upper bounds,
  exactly as it does for a Transaction-Time-Only close (*Composition with
  inheritance*, below) — the observed-`in_z` gate still binds last.

This mirrors `GenericBiTemporalDirector.updateUntil` / `splitTailEnd`
(research §6, the bitemporal rectangle split). The same multi-row physical primary
key (domain key plus each axis's end column, `m-descriptor`) makes the chained
rectangles admissible.

## Plain (unbounded) bitemporal writes

Alongside the bounded `*Until` trio, the Bitemporal surface provides the
three **plain (unbounded) writes** — `insert`, `amend`, `terminate` — that govern
a value from a **Valid-Time instant** `V` **through infinity** rather than
inside a bounded window. Each is the degenerate rectangle split obtained by letting
the window's Valid-Time upper bound go to infinity: where an `*Until` mutation carries
an explicit `until`, a plain mutation has none, so it never chains a `tail` back to
the old value beyond the window. Plain `insert` / `amend` / `terminate` are all
**required** behavior (ADR 0021). `V` is the mutation input's `validFrom`, and the
window it governs is `[V, infinity)`.

| Mutation | Observable SQL sequence |
|---|---|
| **insert** (plain) | open one row whose Valid-Time interval is `[V, infinity)` at Transaction Time `[txInstant, infinity)`; a single `insert` with no prior row to close, so the row is fully current (`thru_z = out_z = infinity`) |
| **amend** (plain) | inactivate the original by closing Transaction Time (`out_z = txInstant`), then chain two rows at fresh Transaction Time `[txInstant, infinity)` — `head` Valid Time `[from_z, V)` (old value) and a new `tail` Valid Time `[V, infinity)` (new value) |
| **terminate** (plain) | inactivate the original, then chain only a `head` over Valid Time `[from_z, V)`; `[V, infinity)` is covered by no current-on-Transaction-Time row |

The three form a natural progression. Plain `insert` establishes the fully-current
rectangle with no close; plain `amend` and plain `terminate` share the same
inactivate + `head` prefix that preserves the prior value on Valid Time `[from_z, V)`,
and differ only in the tail — `amend` chains a new `tail` carrying the new value on
`[V, infinity)`, whereas `terminate` chains no tail, so the value is **absent** from
`V` onward. Key invariants the suite pins down:

- Plain `insert` is a **single** `INSERT` of a fully-current row; there is no
  inactivation and no prior row to close, so the optimistic inactivation gate below
  does **not** apply to it. It is the unbounded degenerate of `insertUntil` and
  shares that mutation's canonical `INSERT` shape.
- For plain `amend` and plain `terminate`, the inactivation `UPDATE` addresses the
  one current rectangle exactly as the `*Until` inactivation does
  (`pk and thru_z = ? and out_z = ?`), so only that rectangle is inactivated; the
  chained rows are inserted **after** it. Under Optimistic the inactivation gains
  the observed-`txStart` gate after the address, again exactly as the `*Until`
  inactivation does; the chained `head` / new `tail` are ungated `INSERT`s at the
  fresh `in_z`.
- The inactivation `UPDATE` **MUST** affect exactly **one** row; a zero-row
  inactivation is an error under either strategy (*Affected-row conflict
  contract for closes*, below).
- After a plain `amend`, Valid Time `[from_z, V)` is current on Transaction Time
  through the `head` (old value) and `[V, infinity)` through the new `tail` (new
  value). After a plain `terminate`, Valid Time `[from_z, V)` remains current
  through the `head` and `[V, infinity)` is covered by no current-on-Transaction-Time row.
- For `amend` and `terminate`, the original survives as a row closed on the
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
keyed `amend`, `amendUntil`, `replace`, `replaceUntil`, `terminate`, or
`terminateUntil` written from a source a read published is not confined to that
rectangle. Its `validFrom` is
the source's own finite Valid-Time pin — the coordinate the read stood at, not
the observed rectangle's start — or, for a source an insertion of the same
attempt authored, that insertion's `validFrom`, its anchor (`m-unit-work`
*Insertion authority*). A source read at Valid-Time `latest` names no instant
and is refused, as is a source neither anchors. Its **requested extent** is
`[validFrom, until)`, through infinity when unbounded, and the write applies to
every current-on-Transaction-Time rectangle of the object that overlaps it and
that the write holds or reads (*Concurrent creation in gaps is not
coordinated*):

- each overlapping rectangle is inactivated once, and its nonempty pieces are
  opened in Valid-Time order: a part outside the extent carries the
  rectangle's own values, and a part inside executes every assigned member over
  the rectangle's own unassigned values, an assigned value equal to the stored
  one included — a replacement's complete stated state, for a replacement — or
  is not opened, for termination;
- an amendment leaves a gap in coverage a gap: nothing is opened where no
  current rectangle exists, and the write continues to the coverage beyond it.
  A replacement opens its complete state over every part of its extent no
  current rectangle covers — a gap, or the coverage after a scheduled
  termination — once, after every inactivation, exactly as a caller-addressed
  replacement does (*Caller-addressed writes span their requested extent*).
  Its authority is its source's: a source whose evidence or insertion
  authority fails licenses no opening, so a replacement is never an upsert;
- a rectangle outside the extent is untouched; adjacent pieces the write opens
  merge where their stored state is identical (*Merging produced successors*),
  never with an untouched or unchanged rectangle;
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
rectangle's stored value is still assigned. A rectangle the composed effect
leaves exactly as it was — every part of it kept and every assigned member
already its value there — is **unchanged** (*Unchanged
milestones*, below) and keeps its milestone rather than being inactivated and reopened
in equal pieces: one guard on its own address and observed `in_z` proves it under
Optimistic where the database's write count includes unchanged rows (`m-sql`),
and nothing is written for it under Locking or when the attempt opened it. The
write's other rectangles are inactivated and reopened as above, so a range
assigning 100 over `[March, October)` to `[January, April) 100 | gap |
[May, August) 180 | [August, December) 100` keeps the first and last rectangles
as they were and rewrites only `[May, August)`. Without the guard's proof every
reached rectangle is inactivated, equal pieces included, and an unchanged
rectangle's equal pieces reopen as one row (*Merging produced successors*).

A write an insertion of the same attempt authorized observed no rectangle, so
the coverage it reaches is read from its anchor inside the flush that writes it,
and it requires a current rectangle containing that anchor. While the insertion
is still pending, its opening is the coverage: an edit bounded inside the
opening splits it, and an amendment never extends it beyond its own window
(`m-unit-work` *Same-transaction write coalescing*). A replacement reaching past
the opening establishes the same state there it would once the insertion had
executed, settled in the opening's own unit at the normal flush: no flush runs
at the call and no intermediate insertion is written. The stored coverage past
the opening's window is read inside the write batch, each rectangle the composed
writes reach is transformed under its own proof, the opening's surviving pieces
open as new lineages, and every remaining part of the replacement's extent opens
with its complete state; pieces of identical stored state among them open as one
row (*Merging produced successors*). The opening's own window is coverage, so a part of it an
earlier composed write destroyed is not reopened.

## Caller-addressed writes span their requested extent

A caller-addressed amendment or replacement (`m-unit-work` *Caller-addressed
writes*) states its own `validFrom`, any instant inside a current rectangle, and
its requested extent is `[validFrom, until)`, through infinity when unbounded.
It requires a current rectangle containing `validFrom` whose `in_z` is the
caller's stated `ifTxStart`. That point condition describes the starting
rectangle alone, not the earlier state of every rectangle the extent reaches:
later rectangles are read inside the flush that writes them, including any
changed since the caller's query, and each is inactivated under its own `in_z`.

| Mutation | Inside its requested extent |
|---|---|
| Amendment | Each overlapping rectangle the write holds or reads takes the assigned members over its own unassigned values, exactly as an observed write's does; a gap and the coverage after a scheduled termination stay absent. |
| Replacement | Each overlapping rectangle the write holds or reads takes the complete stated state, and every part of the extent no current rectangle covers — a gap, or the coverage after a scheduled termination — is opened with that state too, once. |

A rectangle the write leaves unchanged is kept rather than inactivated
(*Unchanged milestones*), the starting rectangle included: each rectangle is
judged by its own values over the part of it the extent reaches, so the starting
rectangle's equality keeps that rectangle alone, never a later one the write
changes or a gap a replacement opens.

Every inactivation precedes every opening, the starting rectangle's first; a
replacement's opened gaps follow the pieces of the rectangles it inactivates.
Where the flush's read shows no rectangle containing `validFrom`, or one at
another `in_z`, the write is the caller's failed precondition before any
statement executes; where it shows more than one containing `validFrom`, the
write fails sooner, as Cardinality Corruption (`m-unit-work`). Under Optimistic
the starting rectangle's inactivation, or the guard keeping it unchanged, gates
on the stated `ifTxStart`, and its shortfall is that failed precondition; every
later rectangle's gates on its own `in_z`, and its shortfall is an ordinary
conflict. Under Locking the starting rectangle was read whole under the shared
lock at submission, and the flush reuses it while no earlier unit of the attempt
has changed it and reads only the rectangles it does not cover, under the same
lock (`m-unit-work` *Retained starting rows*), so no inactivation is gated
(`m-read-lock`).

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
Amend [February, April) from T0, then amend [June, August) from T0
Final:  [January, February) | [February, April) first amendment
        | [April, June) | [June, August) second amendment | [August, infinity)
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
or a gap an amendment passes over, and both commits can leave overlapping current
coverage; no isolation level is raised to prevent it. A write binds to the rows
it already holds — the rectangles it observed, unless an ordering barrier
follows earlier writes of its object; the starting rectangles a Locking
acquisition retained that are still current; the starting rectangle a
predicate selected each object by; and a pending insertion's own window — and
reads only the coverage of its extent those leave. A rectangle
created concurrently inside a held row's Valid-Time interval is therefore not
reached: the write neither reads nor inactivates it, and it stays current
beside the write's own pieces.

**Untracked same-token changes are a configuration constraint.** A supported
deployment introduces no trigger or cascade that replaces or changes a tracked
current row outside the framework's own writes while leaving its address and
`in_z` as they were. Nothing here detects such a change; audit-only side effects
and effects on unrelated data are unaffected.

## Predicate-selected amendments span their requested extent

A Bitemporal `amend` or `amendUntil` a predicate selects (`m-unit-work`
*Materialized Write Groups*) has the requested extent `[validFrom, until)`,
through infinity when unbounded, and reaches each object its predicate matched
as an observed write reaches its object. Membership is decided once, at the
call, after the transaction's pending writes flush: an object is selected when
its rectangle current at `validFrom`, current on Transaction Time, matches the
predicate, and that rectangle is the object's starting rectangle, held as a
read holds it. The predicate never judges a later rectangle: one whose values
no longer match is amended like any other the extent reaches, and an object
whose only matching rectangle starts after `validFrom` is not selected. Where
the selection holds more than one rectangle of one object, the call fails as
Cardinality Corruption naming that object and the count, once the selection is
read and before anything of the write is buffered or executed — exactly as a
caller-addressed write whose read shows more than one rectangle containing its
`validFrom` does (*Caller-addressed writes span their requested extent*).

Each selected object's extent is applied as an observed write's is (*Observed
writes span their requested extent*). Under Optimistic the starting rectangle
gates on the `in_z` the selection observed, and a shortfall there is an ordinary
conflict; a later rectangle is read inside the flush that writes it — under the
shared lock under Locking (`m-read-lock`) — and gates on its own `in_z`. Gaps
stay gaps. Every rectangle is judged for itself (*Unchanged milestones*): a
starting rectangle already holding every assigned value keeps its milestone,
and the same amendment still writes the later coverage it changes.

```text
Stored:   [January, April) 100 | [April, July) 200
Amend where value = 100 from February until June, assigning 150
Selected: the object, by [January, April)
Final:    [January, February) 100 | [February, June) 150 | [June, July) 200
```

Both stored rectangles are inactivated under their own proofs; the parts the
window changes hold one state and so are one row (*Merging produced
successors*).

The objects settle in batches when the flush reaches the write (`m-unit-work`
*Materialized Write Groups*): a later rectangle is read when its object's batch
is reached, after earlier batches executed, so it reflects their effects and
whatever committed meanwhile, while the starting rectangle keeps the proof the
selection observed.

## Rectangles the attempt opened

The splits above inactivate a rectangle that existed before the attempt. A later
write of the **same** attempt whose observed rectangle the attempt's own earlier
flush opened has no history to preserve: closing it at the attempt's one
`txInstant` would leave an empty Transaction-Time interval whose physical key
collides with the rectangle that flush closed. Such a rectangle is therefore
**revised in place or removed** (*Ownership disposal*, below).
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
| **amend** at `V` with `s < V` | update the rectangle into the changed tail `[V, e)`; insert the `head` `[s, V)` |
| **amend** at `V = s` | update the rectangle's value in place |
| **amendUntil** `[V, U)` with `s < V < U < e` | update the rectangle into the carried tail `[U, e)`; insert `head` and `middle` |
| **terminateUntil** `[V, U)` with `s < V < U < e` | update the rectangle into the carried tail `[U, e)`; insert the `head` |
| **terminate** at `V` with `s < V` | delete the rectangle; insert the `head` `[s, V)` |
| **terminate** at `V = s` | delete the rectangle |

An amendment every assigned value of which the rectangle already holds over the
part it reaches — observed, insertion-authored, or caller-addressed — writes
nothing at all: the rectangle is unchanged and is neither split nor revised.
Ownership is never inferred from `in_z = txInstant`.

## Temporal expansion

A temporal write is finalized by `m-unit-work`'s Write Planner, which expands each
surviving temporal unit in place, at its already-decided position (ADR 0045).
Expansion is **neutral**: it names no SQL, dialect, physical column, or statement
and takes no dialect argument, which is what lets it live inside planning while
column participation and quoting stay in lowering. An implementation **MUST NOT**
expose a milestone plan, a milestone step, or a per-row expansion value on any
cross-module interface; only the Planned Writes it produces, and the effects
their success publishes, leave it.

### Coverage Transform

A **Coverage Transform** is what one object's composed writes do to its existing
coverage, decided before any coverage is known. It is an ordered sequence of
disjoint **Coverage Segments**, each a requested Valid-Time window — the whole
axis on a Transaction-Time-Only object — that either assigns members or destroys
coverage. Outside every segment an existing interval is carried unchanged; inside
one, it keeps its own unassigned members and takes the segment's assignments, or
is destroyed. A later write wins per member where windows overlap, and adjacent
segments left stating the same thing are one segment. A replacement's segment
states a complete state; a later assignment over it keeps it a replacement, and a
destruction ends it.

Applied to one existing milestone's coverage, the transform yields that
milestone's **Successors**: the nonempty intervals it becomes, in Valid-Time
order. A successor derives from exactly one predecessor — the existing milestone
it is part of — and is `CarriedFrom` it where no segment assigns there, or
`ChangedFrom` it, carrying the assigned members over the predecessor's own
unassigned ones. A row the unit opens may merge adjacent successors of several
predecessors and new lineages (*Merging produced successors*); each successor
still derives from its own predecessor alone, which keeps its own proof. A gap in coverage stays a gap, except inside a replacement's
extent, where each uncovered stretch is a **Coverage Gap**: a new lineage opened
with the complete stated state, never a successor of anything.

### Predecessor Expansion

A **Predecessor Expansion** applies one unit's transform to one existing milestone
— its **predecessor**, carried as the complete Predecessor Row its observation or
the flush's read produced (`m-write-plan`). It decides, from the unit's settled
facts and the attempt's ownership as it stands then:

- whether the transform reaches the predecessor at all; one it does not reach is
  left alone;
- whether the predecessor is **unchanged** (*Unchanged milestones*, below), and
  then how it is kept;
- otherwise the **Close Cause** — `Superseded` where some successor assigns,
  `Terminated` where none does, even when Bitemporal head or tail successors
  survive, so the cause records the absence and a surviving head or tail stays
  `CarriedFrom` the predecessor and is never itself marked terminated;
- the **gate**: under Optimistic the close binds the predecessor's observed
  Transaction-Time start, whatever the profile, and under Locking the explicit
  `Ungated` decision (`m-opt-lock`). A predecessor holding a caller's start fails
  its gate as that caller's precondition rather than as a conflict;
- the predecessor's own effect by ownership (*Ownership disposal*, below), and
  its nonempty successors.

For one authored mutation of a lone row this is the profile tables above: an
`amend` closes as `Superseded` and opens a `ChangedFrom` successor, plus
`CarriedFrom` heads and tails on Bitemporal data; a `terminate` closes as
`Terminated` and opens only carried survivors; `amendUntil` yields a carried
`head`, a changed `middle`, and a carried `tail`. Each successor is its own
Planned Insert, opened at the attempt's Transaction Instant over
`[txInstant, infinity)` on Transaction Time and over its own Valid-Time
coverage, which stamps the open bound as the managed `infinity`.

A unit's steps keep each predecessor's effect ahead of what it opens. A lone
write's or a group row's close is followed immediately by its successors in
Valid-Time order — `head`, `middle`, `tail` where each exists and is nonempty —
with no unrelated step interleaved and no surviving group or identifier. A range
over several predecessors runs every predecessor's effect before any opening:
predecessors holding a caller's start first, in the order the callers stated
them, then validated observations, then every other predecessor; its successors
follow, and a replacement's Coverage Gaps come last. A row merged from several
produced rows opens where the first of them would have. A predicate-selected
mutation is expanded once for the mutation, never once per resolved row, and
applied to each selected object in resolution order; a Bitemporal amendment's
object is a range over its rectangles, every effect before any opening.

A row a termination or a Transaction-Time-Only write selects is a predecessor
like any other, transformed over its own Valid-Time coverage alone. The rows
such a predicate selects are not confined to the mutation's window, so a
Bitemporal row can start inside it or beyond it. One starting after `validFrom`
has no `head`: its first successor starts where the row starts, never earlier,
and the row is disposed of by ownership as any reached predecessor is. One
starting at or after `until` is not reached and is left alone, with no
statement and no change to its state. A Bitemporal amendment instead selects
each object by the rectangle current at its `validFrom` and reaches the
object's later coverage too (*Predicate-selected amendments span their
requested extent*).

A row opening a **new lineage** — an `insert`'s, each surviving part of a pending
insert (`m-unit-work` *Same-transaction write coalescing*), and each Coverage
Gap — carries the authored state over its own coverage, stamped exactly as a
successor is, with a `NewLineage` origin. No predecessor is fabricated for it.

### Unchanged milestones

A temporal write is applied to each current milestone it reaches, and a
milestone it leaves exactly as it was is **unchanged**: the write's final
composed effect keeps every interval of it and assigns no member a value other
than the one it already holds there — compared by `m-document-codec`'s
effective-change classification over the assigned members alone, an amendment's
assignments or a replacement's complete stated writable state, never over a
source's earlier value or an intermediate edit. Authority takes no part in the
judgment: an observed, an insertion-authored, and a caller-addressed write alike
keep an unchanged milestone rather than closing it and chaining an equal
successor, wherever its unchanged state is proven without changing it:

- a milestone the attempt opened is invisible to every other transaction, so it
  needs no proof and no statement;
- under the effective Locking strategy the shared lock the attempt holds on every
  row the write reaches (`m-read-lock`) keeps the row as it was read, so it needs
  no statement either;
- under Optimistic a milestone that existed before the attempt is proven by a
  **Planned Temporal Guard**: a write that matches the milestone only at its
  observed address and Transaction-Time start, changes no value, and holds the
  row's write lock until the transaction ends. The guard on the milestone
  holding a caller-addressed write's start binds that caller's stated
  `ifTxStart`, and its shortfall is the caller's failed precondition; every
  other guard binds the milestone's own observed start, and its shortfall is the
  milestone's ordinary conflict. Matching is the proof, so a database whose
  write count reports only the rows an update changed cannot give it
  (`m-dialect` *Unchanged-row count*); there the milestone is closed and chained
  as a changed one is, its gate classified as the guard's would be, a choice
  made before anything executes. A guard that matches no row is never a reason
  to fall back.

Either way nothing is closed or opened, the milestone keeps its Transaction-Time
start and its history gains nothing, and the unit's other milestones transform
as usual. The unit still completes: it spends every source it composed, and it
changes no state of the kept milestone, so an observation of that state from
another source stays eligible, another transaction's revision token for it
still holds, and a caller's stated start still names it. A stale stated start is
still its caller's failed precondition. A guard is not zero work: it is a
database write that fires update triggers and keeps its lock through any later
dependent read until the transaction ends.

Judgment is by final effective state, not by the number of successors that
describe it: successors that together cover the whole milestone without a gap,
every one carrying or assigning only values it already holds, leave it
unchanged — a bounded equal assignment keeps its rectangle across a carried
head and tail. It is per milestone: a write equal to the milestone holding its
start keeps that milestone alone, and still changes a later one it reaches or a
gap a replacement opens. It is by declared value: a replacement whose complete
stated state a milestone already holds keeps that milestone whole, stored
content no member declares included, although executing the same replacement on
a changed milestone replaces that content where it assigns (`m-write-plan`
*Write Rows*). A kept milestone is not a successor the write produced. A row a
Transaction-Time-Only predicate-selected amendment selects is instead
eliminated before planning when every assigned member is restored
(`m-unit-work` *Comparing an assigned member with its persisted value*); every
milestone a Bitemporal one reaches is judged here.

### Ownership disposal

For each predecessor a unit transforms, expansion derives its **nonempty**
successors once and then:

```text
predecessor existed before the attempt -> close it once; open the successors
predecessor the attempt opened:
  exactly one successor keeps its complete physical address
      -> revise the row in place into that successor; open the others
  otherwise
      -> remove the row; open every successor
```

Ownership is the attempt's own record (`m-unit-work` *Rows the attempt
opened*): no axis end is moved to make a successor match, nor is a successor
matched against any predecessor but its own. A milestone that existed before the
attempt is never revised in place or removed, so its history stays immutable,
and a revised or reopened row keeps the attempt's Transaction Instant as its
Transaction-Time start. A revision assigns every executed assignment of the
successor it realizes (`m-write-plan` *Write Rows*), whatever value the row
already holds there, plus a moved Valid-Time start; it never assigns the key, an
axis end, or the Transaction-Time start. Closing, revising, or removing a
predecessor changes its observed state; a kept address whose successor executes
nothing and keeps its start leaves it as it was. Where successors merge, the row
that keeps an address is the merged one, so a revision or removal of an owned
predecessor is chosen only once they have (*Merging produced successors*).

### Merging produced successors

Once every predecessor of one object is decided, the rows the unit produces for
that object — its successors, a pending insertion's surviving pieces, and a
replacement's Coverage Gaps — merge before any of them is given an address. Two
of them are one row when, in Valid-Time order, one starts where the other ends,
both stand at the same Transaction-Time interval, and their complete stored
state outside their Valid-Time interval is identical: every directly stored
value, every final audit value, and every document they store, compared by
`m-write-payload`'s persisted equality, so unknown keys, presence, array order,
JSON kinds, and exact numeric meaning all count. A row whose state is not known
until the database writes it — a generated value, or a Column left to its
default — merges with nothing. Only rows one settled write produces for one
object merge: a kept unchanged milestone, an untouched neighbour, a validated
observation, another object, and a gap no replacement fills are never part of a
merge, and nothing is read, closed, or rewritten in order to merge. There is no
transaction-wide or later normalization of coverage.

```text
Stored:   P1 [January, April) 100 | P2 [April, July) 200, all else equal
Amend [February, June) assigning 150
Final:    [January, February) 100 | [February, June) 150 | [June, July) 200
History:  P1 and P2 each inactivated under its own proof
```

Had P1 and P2 differed in a member the amendment does not assign, the two
changed parts would differ too and four rows would stand. A replacement states
the same complete state over every part of its extent, so its pieces and gaps
merge wherever the rest of their stored state — undeclared document content
outside the replaced members, say — agrees.

Merging changes no proof and no effect order. Every predecessor is still
inactivated, guarded, revised, or removed under its own gate, in the order
*Predecessor Expansion* gives, before anything opens; fewer openings never drop
an original's condition. A merged row is opened once, where the first row it
merges would have opened. Where the attempt owns a predecessor whose own
successor ends a merged row where the predecessor ends, that row is revised in
place into the whole merged row — its own successor's assignments, with its
Valid-Time start moved to the merged row's — and every other owned predecessor
whose kept successor the merged row absorbed is removed. A revision whose
successor assigns nothing and whose start does not move expresses no merge, so
that predecessor is removed under its gate and the merged row opened. Equal
stored state does not make one predecessor's assignments stand for another's:
only the predecessor ending the merged row is revised, and only by its own.

Every original's part of a merged row is recorded with the unit's effects
(`m-unit-work` *Execution units complete before later work runs*): writes the
flush admitted before a barrier follow each original to the merged row over the
part it contributed, never over the rest, and an insertion keeps only the part
of the row its own coverage became.

### An overlapped observation is retired, not transformed

Two observations of one object whose coverage overlaps cannot both describe
current state (`m-opt-lock` *Composed temporal writes keep every source
condition*). The later-authored one is the predecessor the transform applies to;
the earlier is retired on its own address before anything is opened, as
`Terminated`, with no successor and under the same gate and ownership rules: a
milestone that existed before the attempt is closed, and one the attempt opened
is removed. Its successors never borrow the later observation's.

## The close addresses a Milestone Target

A close addresses `m-write-plan`'s **Milestone Target**: the primary key plus one
write-required **exclusive upper bound per As-Of Axis**. For Transaction-Time-Only
data that is the single `out_z = infinity` bound; for Bitemporal data it adds the
observed Valid-Time end (*Address and gate are separate*, below). The target carries no axis
start, no observation, no gate, and no Effective Concurrency Strategy, and it is
**identical under both strategies** (ADR 0046) — only the gate differs.

That separation is what makes a **stale** observation safe — one that named the
current milestone when it was read and that another transaction has since
superseded. Such a write still targets `out_z = infinity`; it never copies a
finite historical end into the target, so closed history is never mutated. Under
Optimistic the stale observed `in_z` rides the gate, matches zero rows against
the newer current milestone, and reports the conflict. Locking
renders no gate and needs none: its observing read holds a shared read lock on
the milestone the observation names, which is the same milestone the close
addresses, so no concurrent writer can have superseded it (`m-opt-lock`,
`m-read-lock`).

An observation of a milestone the Transaction-Time past holds is a different
thing and never reaches planning under either strategy: it could only come from a view
pinned at a finite Transaction-Time instant, and mutating one is refused at the
authoring surface by the read-only rule above.

### Address and gate are separate

The rectangle an inactivation means to close and the concurrency condition that
detects a lost update are **separate** facts (ADR 0046). The **Milestone Target**
(`m-write-plan`) is the address: the primary key together with one write-required
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
instead (*The close addresses a Milestone Target*, above). An observation of a rectangle the Transaction-Time
past holds never reaches planning at all, under either strategy: it could only come from
a view pinned at a finite Transaction-Time instant, which is read-only
(`m-identity-map`).

## Affected-row conflict contract for closes

The close `UPDATE` **MUST** affect exactly **one** row. A close that affects
**zero** rows is an **error under either strategy** — it **MUST NOT** silently succeed and
proceed to chain the replacement row (which would produce a duplicate or an
orphaned current row). The current-row predicate (`pk and out_z = infinity`) alone
is **not** a sufficient gate against a concurrent writer: a fully-committed
concurrent chain leaves a *new* current row that a stale close would silently
re-close — a lost update — so under Optimistic the close carries an additional
`and <in_z> = ?` gate on the `txStart` the unit of work **observed**:

```text
update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?
binds: [<txInstant>, <pk>, <infinity>, <observedTxStart>]
```

The observed `in_z` is the optimistic-lock **version analogue** for a temporal
entity, which carries no version column (the `m-opt-lock` composition,
`m-opt-lock --> m-temporal-read`). A zero-row gated close is a **retriable
conflict** (`updatedRows != 1`); a zero-row *ungated* (effective-Locking) close is a
distinct **non-retriable** stale/consistency error — a categorically different
outcome from the gated conflict, but not a new `m-db-error` category: `then`
carries no `errorClass` for either shape, since neither is a database error code.
A case grades the gated conflict as the Shortfall of the losing unit of work's
flush failure (`m-case-format` *Unit fates*); the ungated one is a
language-internal claim rather than a corpus observable (`m-case-format`
*Conflict cases*). On **success** the gate applies
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
resolved row": a `terminate` row contributes a lone close, an `amend` row a
close-then-chain pair. `m-temporal-write-007` (terminate) and `m-temporal-write-009`
(amend) are the corpus witnesses.

## Composition with inheritance

A milestone-chaining write on an inheritance participant (a concrete subtype of a
family whose Transaction-Time axis is declared on the abstract root, `m-inheritance`) is
the **same** close-and-open sequence — `insert` / `amend` / `terminate` are
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

A rectangle-split write on an inheritance participant (a concrete subtype of a family
whose bitemporal axes are declared on the abstract root, `m-inheritance`) is the
**same** inactivate-and-chain sequence — the plain `terminate` and the windowed
`terminateUntil`, and their `amend` / `*Until` siblings, are unchanged. Routing and
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

Write-sequence cases carry a `when.writeSequence` (ordered `insert` / `amend` /
`terminate`) and `then.tableState`. The harness **applies** the ordered DML
golden SQL (`then.statements`) to a freshly-provisioned (empty) table, then asserts
the resulting milestone rows equal `then.tableState` — including the
`out_z = infinity` current-row state. The DML statement count must equal the sum of
the steps' declared statement counts and the case's `then.roundTrips`. Rather than
introspecting
an implementation, the suite proves the *documented golden SQL itself* produces
the correct milestones.

On a two-axis entity the sequence carries the `insertUntil` / `amendUntil` /
`terminateUntil` trio beside the plain unbounded `insert` / `amend` /
`terminate`, and the harness asserts the resulting rows — the inactivated original (`out_z`
finite) plus the `head` / `middle` / `tail` rectangles current on Transaction Time
(`out_z = infinity`); a plain `amend` asserts the inactivated original plus a
`head` and a new `tail`; a plain `terminate` asserts the inactivated original plus a
lone `head`, with `[V, infinity)` covered by no current-on-Transaction-Time row; a plain
`insert` asserts a single fully-current rectangle (`thru_z = out_z = infinity`) with
no inactivation. The DML statement count must equal the sum of the steps' declared
statement counts and the case's `then.roundTrips` (a plain `insert` step is 1
statement; a plain `terminate` step is 2 statements — inactivate + `head`; a plain
`amend` step is 3 — inactivate + `head` + new `tail`). The standalone witnesses are
`m-temporal-write-025-plain-insert`, `m-temporal-write-022-plain-update-split`, and
`m-temporal-write-023-plain-terminate`.
