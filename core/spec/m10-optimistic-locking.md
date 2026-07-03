# M10 — Optimistic Locking

`M10` is the **optimistic concurrency** strategy: instead of holding a row lock
for the duration of a read-then-write (`M8`'s automatic shared-row lock), an
entity carries a **version column** that a write **advances** and, in optimistic
mode, **gates on**. A concurrent write that changed the version first makes the
stale-version write match **no** row, and that *missing* row is the conflict
signal.

`M10` is a fast-follow module. It depends on `M8` (the unit of work whose flush
issues the versioned `UPDATE`, and the identity cache that holds the version a
reader observed) and on nothing below it. The version-check SQL is fixed by `M3`;
`M10` mandates the **observable** conflict-detection rule.

Optimistic locking is a **per-unit-of-work participation mode** the caller
selects (`M8` strategy selection — `concurrency: optimistic`), not a static entity
property. In optimistic mode a read takes **no** lock (so readers never block
writers), and correctness is recovered at write time by the version check; the
default `locking` mode instead takes `M8`'s implicit shared read lock. The same
versioned entity can be written under either mode in different workflows. The
metamodel only **names** the version column (`optimisticLocking: true`, `M1`);
whether the gate is emitted is the unit of work's choice. Optimistic mode suits
read-mostly workloads and detached edits (`M9`), where holding a lock across the
edit is undesirable or impossible.

## The version column

An entity names its version column by marking exactly one attribute
`optimisticLocking: true` (`M1`). That attribute is the **version**: an integer
an implementation **MUST**:

- **project** alongside the row on every read of a versioned entity (the reader
  observes the current version — the versioned-read golden SELECTs the version
  column);
- **advance** in the `set` of **every `UPDATE` statement** issued against the
  entity, in **both** modes (so every successful write moves the version forward);
- **gate** on **in optimistic mode only** — include `and <version> = ?` in the
  `where` clause binding the version the unit of work *observed* for that row. In
  `locking` mode the shared read lock makes the write correct, so no gate is
  emitted (the `UPDATE` still advances the version — the `0702` / locking-mode
  shape).

### Version values are framework-owned

The version an implementation binds in the gate **MUST** be the version the unit
of work *observed* for that row — the value a transaction-scoped read hydrated
into the identity cache (a detached copy carries the one read at detachment,
`M9`). An implementation **MUST NOT** accept a caller-authored version value as
the gate or as the new version; the new version is always runtime-computed
(`observed + 1`). "Caller-driven" refers to conflict *handling* only, never to the
version *value*. A keyed `UPDATE` of a versioned row the unit of work never
observed is a **read-before-write** error in **either** mode: the new version is
computed from the observed one (`observed + 1`), so with no observed version
there is nothing to advance from — and, in optimistic mode, nothing to gate on —
so the implementation **MUST** raise rather than write blindly. (Only optimistic
mode additionally emits the version *gate*; both modes require the observed
version to advance it.)

### No-op updates issue no DML

Replacing the older "write the version on every update even when no domain field
changed" rule: the version advances on every `UPDATE` statement an
implementation *issues*, but an update whose `set` changes **no** attribute
**MUST** issue **no DML** at all (zero round trips). A no-domain-change write does
not need to bump the version — the concurrent editor that races it advances the
version itself, so nothing slips through — and the removed always-write rule only
produced overhead writes and spurious conflicts.

### Set-based updates materialize

A keyed `UPDATE` of one versioned row gates on (optimistic) and advances (both
modes) the version the unit of work observed for that row. A **set-based** update
— one that selects rows by a predicate rather than a single primary key — has
**no** set-based versioned template: the gate binds a *per-row* observed version,
so a single `where <predicate>` statement cannot carry it. Such an update
**MUST** therefore **materialize** (ADR 0032): the implementation

1. **resolves the predicate to rows** through a read — a real round trip that
   records each matched row's observed version into the identity cache (and, in
   `locking` mode, takes `M8`'s shared read lock on them); then
2. issues **one keyed per-object `UPDATE` per resolved row** — the gated
   optimistic form or the ungated locking form above, each binding *that row's*
   observed version and advancing it.

Round-trip accounting is therefore **`1` read + `N` per-object updates**. A
per-object gate that matches zero rows is the same `updatedRows != 1` conflict
and **MUST** surface (a mid-batch conflict aborts the unit of work like any
other). This makes read-before-write **universal** for versioned entities: a
keyed update *requires* a prior observe (above), and a set-based update
*performs* it. For a **non-versioned** entity the readless batched forms stand
(`M3`, ADR 0011) — materialization applies only where a framework-owned version
must ride each write.

### Temporal entities derive the version from the processing axis

A processing-axis temporal entity (`M7`) carries **no** version column, so its
optimistic key is **derived**: the observed processing-from (`in_z`) value **is**
the version analogue (Reladomo's `IN_Z` rule). In optimistic mode the milestone
close/inactivate `UPDATE` the write already issues gains an `and <in_z> = ?` gate
bound to the `in_z` the unit of work observed for the current milestone; a
concurrent chain that superseded that milestone left a **fresh** `in_z`, so the
stale gate matches zero rows — the same `updatedRows != 1` conflict. On **success**
no version numbers exist to bump: the gate rides only on the close(s) (one per
closed/inactivated current row, each binding *that row's* observed `in_z`, each
**MUST** affect exactly one row), and the chained replacement rows are plain
ungated `INSERT`s whose fresh `in_z = txInstant` **is** the advance. A **zero-row**
close is an error in **any** mode (never silent) — a retriable conflict in
optimistic mode, a distinct non-retriable stale/consistency error in locking mode.
The write shapes and the current-row-predicate-is-not-a-gate rationale are `M7`;
the conflict/retry contract is this module (the `M10 --> M7` composition edge).
Combining an explicit `optimisticLocking` attribute with `asOfAttributes` is
invalid (`M1`), and a business-temporal-only entity cannot participate in
optimistic mode (no processing axis to derive the key from).

## Conflict detection

In **optimistic mode** the version turns a lost update into a **detectable**
event. The canonical golden `UPDATE` (`M3`) gates on the observed version:

```text
update account set balance = ?, version = ? where id = ? and version = ?
binds: [<new-balance>, <new-version>, <pk>, <observed-version>]
```

The `locking`-mode golden for the same write drops the gate but still advances
the version (`update account set balance = ?, version = ? where id = ?`) — the
shared read lock, not the version, is what makes it correct. Conflict detection
below applies to the gated optimistic form.

The detection rule is the **affected-row count**:

- The `UPDATE` affects **exactly one** row ⇒ **success**. No concurrent write
  intervened; the version advanced.
- The `UPDATE` affects **zero** rows ⇒ **conflict**. A concurrent transaction
  committed first and incremented the version, so the `where … and version = ?`
  gate matched no row. This is the `updatedRows != 1` signal.

An implementation **MUST** treat `updatedRows != 1` on a versioned `UPDATE` as a
conflict (a row that exists but no longer matches the expected version), and
**MUST NOT** silently succeed. The primary-key row still exists; only its version
moved, so the count — not an error from the database — is the conflict carrier.

## Retry contract

A detected conflict is **retriable**. On conflict an implementation **MUST**:

1. surface the conflict to the unit-of-work boundary (e.g. by raising a
   conflict / retriable exception, the per-language shape of which is an
   idiomatic concern);
2. invalidate the stale cached row so a re-read fetches the **current** version
   and values (`M8` cache freshness);
3. permit a **retry** that re-reads the fresh version and re-applies the
   intended change against it.

The unit-of-work boundary **MUST** offer **bounded automatic retry** as specified
in `M8` (*Bounded automatic retry*): a configurable bound (default **10**; `0`
disables the loop), and on a retriable failure a rollback, a freshness
invalidation, and a re-execution of the closure against fresh state. A conflict is
**not** automatically retried by default — it surfaces to the caller — and joins
the retriable set only when the unit of work opts in (`retryOptimisticConflicts`,
Reladomo's `setRetryOnOptimisticLockFailure`, default off). Transient database
failures (deadlock / serialization failure) are always retriable regardless of
that flag. A retry that exhausts its bound surfaces the conflict to the caller.

The suite proves the retriable half observably with a conflict case's
**`attempts`** sequence (M12): a stale-version `UPDATE` affects `0` rows, then a
retry that re-reads the fresh version and re-applies affects `1` — the `0`-then-
`1` transition, asserted against real data. The loop-mechanics branches a
single-connection harness cannot provoke (a conflict surfacing without the opt-in,
an injected transient auto-retried, `retries: 0`, bound exhaustion) are authored as
**boundary** cases on the `api-conformance` lane and satisfied by each language's
API Conformance Suite.

Optimistic locking composes with **detached merge-back** (`M9`): the version a
detached copy carries is the one read at detachment, so a merge-back `UPDATE`
gates on that version and detects a conflict if the original changed in the
interim — exactly the same `updatedRows != 1` rule.

## What the suite pins down

`M10` is proven by a **conflict case** (`M12`): the golden `UPDATE` is applied to
a loaded table and the **affected-row count** is asserted. The case carries an
optional out-of-band **`precondition`** — a naive SQL statement that simulates a
concurrent transaction mutating the row — and an **`expectedAffectedRows`** count:

| Case | Mode | Precondition | Golden UPDATE version | Affected rows |
|---|---|---|---|---|
| optimistic-lock conflict | optimistic | bump the row's version out of band | the now-stale observed version | **0** (conflict detected) |
| optimistic-lock success | optimistic | none | the observed version | **1** (write applied) |
| versioned update, locking mode | locking | none | none — no gate, version still advances | **1** (write applied) |

A companion **scenario** case pins the no-op rule: a versioned update whose `set`
changes no attribute declares `roundTrips: 0` and lists no golden DML (no
statement issued). A pair of **scenario** cases pins the set-based materialize (one
per mode): a `find` step (the materialize read, `roundTrips: 1`), a `write` step
listing the ordered **per-object** `UPDATE`s (`roundTrips: N`, its golden a list
and its binds a list-of-lists — the gated form in optimistic mode, the ungated
version-advancing form in locking mode), and a verify `find` re-resolving the
mutated rows — the declared `roundTrips` (`1 + N + 1`) is the honest materialize
cost. Optimistic corpus cases carry a `uow: { concurrency: optimistic }` block so
their gated goldens are self-describing; the locking-mode cases carry
`uow: { concurrency: locking }`.

The harness loads the model's fixtures (the row exists with its current
version), applies the precondition (a concurrent version bump, for the conflict
case), runs the golden `UPDATE`, and asserts the affected-row count equals
`expectedAffectedRows` — and, when authored, the resulting table state. This
proves conflict detection against **real data**: the stale-version `UPDATE`
provably touches zero rows, the fresh-version one provably touches exactly one,
so `updatedRows != 1` is verified as the conflict signal rather than merely
asserted in prose.
