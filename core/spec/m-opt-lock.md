# m-opt-lock — Optimistic Locking

`m-opt-lock` is the **optimistic concurrency** strategy: instead of an object find
holding a row lock for the duration of a read-then-write (`m-read-lock`'s automatic
shared-row lock), an entity carries a **version column** that a write **advances**
and, under the Optimistic strategy, **gates on**. A concurrent write that changed the version
first makes the stale-version write match **no** row, and that *missing* row is the
conflict signal.

`m-opt-lock` depends on `m-unit-work` (the unit of work whose flush issues the
versioned `UPDATE`) and `m-temporal-read` (the milestoning read model a temporal
entity's derived key rides on). The version a reader observed is held by the
identity cache (`m-process-cache`). The version-check SQL is fixed by `m-sql`;
`m-opt-lock` mandates the **observable** conflict-detection rule.

Its model-formation contribution consumes `m-metamodel`, the Inheritance Facet,
and the Temporal Facet through `m-model-formation`. The Rule Set owns exactly
`opt-lock-multiple-attributes` (a declaring position names more than one explicit
version Attribute) and `opt-lock-temporal-explicit-attribute` (a declaring
position with a Transaction-Time As-Of Axis also declares an explicit version
Attribute). Its Model Compiler produces the
immutable Optimistic Lock Facet ("The Optimistic Lock Facet", below),
identifying each Entity's effective explicit or Transaction-Time-derived
optimistic key without copying Attribute Metadata.

Optimistic locking is an **Effective Concurrency Strategy** derived for one
Entity inside a Unit Work, not one uniform mode imposed on every Entity in the
transaction. The Unit Work's `optimistic` Concurrency Preference — also the
default — selects this strategy for an Entity whose Optimistic Lock Facet carries
an explicit version or Transaction-Time-derived key. Its participating object
find takes **no** shared lock and correctness is recovered at write time by the
gate. An explicit `locking` preference instead gives that same Entity the
`m-read-lock` shared read lock and omits the gate. An unversioned Non-Temporal
Entity cannot use this strategy and falls back to Locking even under the
`optimistic` preference (`m-unit-work`). The metamodel names the capability
(`optimisticLocking: true` or the Transaction-Time start); the preference and
Facet together decide whether a particular Entity uses it.
The Optimistic strategy suits read-mostly workloads and detached edits (`m-detach`), where
holding a lock across the edit is undesirable or impossible.

## The Optimistic Lock Facet

The Model Compiler consumes the Inheritance and Temporal Facets and produces
the immutable `OptimisticLockFacet` under `FacetKey(m-opt-lock)`; typed access
is this module's `view(model) -> OptimisticLockFacet` function.

```text
OptimisticLockFacet
  key(EntityIdentity) -> OptimisticKey | absent

OptimisticKey =
    Unversioned
  | ExplicitVersion(attribute: AttributeIdentity)
  | TransactionTimeDerived(start_attribute: AttributeIdentity)
```

`key` is total, nonthrowing, and expected amortized O(1); it returns absent
only for an identity outside the accepted Metamodel. It is family-uniform:
every position in one inheritance family returns the same value, derived from
the family root, and a standalone Entity is its own root.

- `ExplicitVersion` carries the declaring Attribute Identity of the effective
  `optimisticLocking: true` Attribute — the root's identity on every
  descendant view, preserved rather than copied.
- `TransactionTimeDerived` applies to every Entity whose Temporal Facet shape
  declares Transaction Time and carries that axis's start Attribute Identity —
  the observed `txStart` (physical `in_z`) version analogue below. The two
  keyed variants are mutually exclusive because a temporal Entity with an
  explicit version Attribute is rejected
  (`opt-lock-temporal-explicit-attribute`), and no supported temporal shape
  lacks Transaction Time.
- `Unversioned` is the remaining case: a non-temporal Entity with no effective
  version Attribute. Its writes emit no gate and advance no version.

The facet copies no Attribute Metadata; both keyed variants carry identities
that resolve through the Metamodel's local lookup.

## The version column

An entity names its version column by marking exactly one attribute
`optimisticLocking: true` (`m-descriptor`). For an inheritance participant
(`m-inheritance`), the version column is **family-level metadata declared only
by the root**: every abstract and concrete descendant inherits it unchanged, and
a descendant declaring its own `optimisticLocking` attribute is rejected
pre-SQL regardless of whether the root itself is versioned
(`inheritance-optimistic-locking-not-root-owned`) — a family is versioned
together or not at all. That attribute is the **version**: an
integer an implementation **MUST**:

- **project** alongside the row on every read of a versioned entity (the reader
  observes the current version — the versioned-read golden SELECTs the version
  column);
- **advance** in the `set` of **every `UPDATE` statement** issued against the
  entity, under **both** strategies (so every successful write moves the version forward);
- **gate** under the **Optimistic strategy only** — include `and <version> = ?` in the
  `where` clause binding the version the unit of work *observed* for that row. In
  the Locking strategy the shared read lock makes the write correct, so no gate is
  emitted (the `UPDATE` still advances the version — the `m-detach-002` /
  locking-mode shape).

### Effective Concurrency Strategy determines the gate uniformly

Whether a write carries its observation-bound gate predicate is decided by the
target Entity's **Effective Concurrency Strategy alone**, never by the mutation
kind. The Unit Work derives that strategy from its Concurrency Preference and the
Entity's Optimistic Lock Facet before considering the verb. Optimistic emits a
gate on **every** observation-requiring write — a versioned keyed `UPDATE`, a
versioned keyed `DELETE`, and a temporal milestone close alike. Locking
emits **none** of them, because the shared read lock the required prior
observation took is what makes the write correct. The requirement to *hold* an
observation is unaffected: it is mandatory under **both** strategies for all three
shapes, and only what the statement *renders* differs.

An implementation **MUST NOT** make gate presence depend on the verb. A keyed
`DELETE` that retained its observed-version predicate under Locking would give
the gate two different meanings under one strategy and let a Locking shortfall
surface as an optimistic conflict.

The canonical effective-Locking goldens are therefore uniform in shape:

```text
update account set balance = ?, version = ? where id = ?
delete from account where id = ?
```

and their effective-Optimistic counterparts each append `and version = ?`, binding
the observed version last.

### A gate carries only its equality predicate

The gate decision is settled **during planning**, and what survives onto the
planned write is only what the statement still has to render (`m-unit-work`'s
Write Gate):

```text
VersionGate(attribute: AttributeIdentity, observed_version: PositiveInt)
TemporalGate(start_attribute: AttributeIdentity, observed_start: Instant)
Ungated
```

- The **advanced** version (`observed + 1`) and the close's Transaction-Time end
  are **assignments**, not gate members. A gate answers "which extra equality
  must hold", never "what does this write set".
- A gate repeats **neither** the full Write Observation **nor** the transaction's
  Concurrency Preference or the Entity's Effective Concurrency Strategy. Those
  are consumed while planning: the effective strategy selects
  `VersionGate` / `TemporalGate` or `Ungated`, and the observation supplies the
  bound value. Neither survives into the plan, so nothing downstream can
  re-derive a gate or reach a different answer than the planner did.
- `Ungated` is an **explicit** effective-Locking decision, not a null gate. Gate
  applicability is therefore structural rather than a nullable field every
  consumer must re-check.
- A Version Gate applies to exactly **one** row: it binds that row's observed
  version, so it is legal only on a single-key target. This is the same fact that
  forbids a versioned readless predicate template.

### What licenses a write under Locking

An observation is mandatory for a gated *and* an ungated observation-requiring
write, and both strategies accept the same observation. The Locking strategy's
ungated write is licensed by the **shared read lock** the observing read took — and it holds
that lock on exactly the row it closes, because the two derive from one value:
the write's address is the milestone its own written value came from, and the
observation the address comes from is the record of the read that locked that
milestone (`m-unit-work`, Write Observation). There is no separate license to
check. Under Locking, a write whose value names a milestone the current unit of
work never observed is already refused because no participating read proves the
lock is held; under Optimistic, an authentic standalone observation may supply
the gate instead. A write over a view pinned at a
finite Transaction-Time instant is already refused by the pin rule
(`m-identity-map`), under **both** strategies, before any planning.

The invariant is therefore a property of how the close is constructed rather
than a precondition validated on the input side. Nothing about the *read* that
produced an observation survives into it: two reads at different as-of
coordinates that resolve to one milestone produce one indistinguishable piece
of evidence, so no observation of a milestone can be less licensing than
another observation of that same milestone.

### Version values are framework-owned

The version an implementation binds in the gate **MUST** be one Parallax
authentically observed for that row. Under the Locking strategy it must come from
a current-transaction participating read, because that read is what acquired the
shared lock. Under the Optimistic strategy it may instead be retained by an
authentic Typed or Wire source produced by a standalone Parallax read; the
database gate remains the concurrency authority. A detached copy carries the
authentic observation made at detachment (`m-detach`). An implementation **MUST
NOT** accept a caller-authored or reconstructed version value as the gate or as
the new version; the new version is always runtime-computed (`observed + 1`).
"Caller-driven" refers to conflict *handling* only, never to the version *value*.
A keyed `UPDATE` or `DELETE` with no authentic observation is a
**read-before-write** error under either strategy: there is nothing from which to
advance the version and, when Optimistic, nothing to gate on. A `DELETE` writes no
version, but still requires the same evidence: current lock participation under
Locking or retained observed-version evidence under Optimistic.

### No-op updates issue no DML

The version advances on every `UPDATE` statement an implementation *issues*, but
an update whose `set` changes **no** attribute **MUST** issue **no DML** at all
(zero round trips). A no-domain-change write does not need to bump the version —
the concurrent editor that races it advances the version itself, so nothing slips
through.

### Predicate-selected writes materialize when observations are needed

A **predicate-selected write** starts from one concrete entity and one **bare**
`m-predicate` predicate. It is not a language method name and it is not inferred
from golden SQL. Query clauses (`orderBy`, `limit`, `includes`, `temporal`,
`asOfRange`, `history`, and `narrowTo`) are not write targets.
The canonical instruction and its assignment rules are `m-case-format`.

A keyed write of one versioned row gates under Optimistic and advances under
both strategies from the version observed for that row. A predicate-selected write to a
versioned entity has **no** single-statement versioned template: the gate binds a
*per-row* observed version. It **MUST** therefore **materialize** (ADR 0014):

1. resolve the predicate through a read, recording each matched row's observed
   version; under the Entity's effective Locking strategy this read takes the
   `m-read-lock` shared lock; then
2. issue one keyed per-object write for every row that the verb writes — gated
   under Optimistic and ungated-but-version-advancing under Locking.

For assignment-bearing mutations, no-op elimination is **per resolved row**: when
all assignments already equal that row's values, it issues no DML, advances no
version, and contributes no round trip. `delete` and temporal `terminate` process
**every** resolved row: they have no assignment equality to eliminate. The exact
cost is therefore **`1 + N`**, where `N` is the number of rows actually written,
not necessarily the number resolved. A per-object gate or temporal close that
matches zero rows is the `updatedRows != 1` conflict signal and **MUST** abort the
whole unit of work; a later row is never silently continued after that conflict.

This materialization rule also applies to Transaction-Time Entities. Their
observed `txStart` (`in_z`) is the per-row optimistic version analogue; the
temporal modules own close/chain and rectangle-split SQL, while this module owns
the conflict and abort rule. Reladomo is the prior art: transaction mode either
reads under a lock or gates on the observed optimistic version and treats
`updatedRows != 1` as a conflict; its temporal director closes `IN_Z` milestones
and splits rectangles. Parallax adopts those runtime semantics, not Reladomo's
Java API or implementation structure.

The one exception is an **unversioned, non-temporal** target. It remains readless
unless it assigns a document-resident `many`, which is refused before SQL as
`predicate-write-readless-document-many-unsupported` until that narrow shape can
materialize without changing the scalar and `one` route:
`update` emits exactly one `update <table> set <column> = ?, … where <predicate>`
and `delete` exactly one `delete from <table> where <predicate>`. The readless
update has no equality-elimination pass. Its `set` columns follow `m-sql`'s
target Entity Layout filtering, never authored assignment order; binds are
assignment values in that emitted order followed by predicate binds.
`m-batch-write` owns this readless vocabulary and witness; this module owns every
observed-version or Transaction-Time materialization rule.

### Temporal entities derive the version from Transaction Time

A Transaction-Time Entity (`m-temporal-read`) carries **no** version column, so
its optimistic key is **derived**: the observed `txStart` (`in_z`)
value **is** the version analogue (Reladomo's `IN_Z` rule). Under Optimistic the
milestone close/inactivate `UPDATE` the write already issues gains an
`and <in_z> = ?` gate bound to the `in_z` the unit of work observed for the current
milestone; a concurrent chain that superseded that milestone left a **fresh**
`in_z`, so the stale gate matches zero rows — the same `updatedRows != 1` conflict.
On **success** no version numbers exist to bump: the gate rides only on the
close(s) (one per closed/inactivated current row, each binding *that row's*
observed `in_z`, each **MUST** affect exactly one row), and the chained replacement
rows are plain ungated `INSERT`s whose fresh `in_z = txInstant` **is** the advance.
A **zero-row** close is an error under **either** strategy (never silent) — a
retriable conflict under Optimistic, a distinct non-retriable stale/consistency
error under Locking. The write shapes and the current-row-predicate-is-not-a-gate
rationale are `m-txtime-write` / `m-bitemp-write`; the conflict/retry contract is
this module (the `m-opt-lock --> m-temporal-read` composition edge). Combining an
explicit `optimisticLocking` attribute with a temporal `temporality`
profile is invalid
(`m-descriptor`). Every supported temporal formation contains Transaction Time;
Valid-Time-Only is unsupported, so no temporal formation lacks this derived key.

## Conflict detection

Under the **Optimistic strategy** the version turns a lost update into a **detectable**
event. The canonical golden `UPDATE` (`m-sql`) gates on the observed version:

```text
update account set balance = ?, version = ? where id = ? and version = ?
binds: [<new-balance>, <new-version>, <pk>, <observed-version>]
```

The effective-Locking golden for the same write drops the gate but still advances
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

Classification follows the **gate**, uniformly with the temporal close rule
above. A **gated** (optimistic) shortfall is the retriable conflict. An
**ungated** (effective-Locking) shortfall on a write that still required a prior
observation — a versioned keyed `UPDATE`, a versioned keyed `DELETE`, a
milestone close alike — is a categorically different, **non-retriable**
stale/consistency outcome: no gate could have caused it, so it is not a detected
lost update a re-read could resolve.

An implementation **MUST NOT** classify by verb here either. An effective-Locking
`UPDATE` whose shortfall surfaced as the retriable conflict would be retried
against an unchanged cause, since re-reading cannot supply a gate the strategy never
rendered.

## Retry contract

A detected conflict is **retriable**. On conflict an implementation **MUST**:

1. surface the conflict to the unit-of-work boundary (e.g. by raising a
   conflict / retriable exception, the per-language shape of which is an
   idiomatic concern);
2. invalidate the stale cached row so a re-read fetches the **current** version
   and values (`m-process-cache` freshness);
3. permit a **retry** that re-reads the fresh version and re-applies the
   intended change against it.

The unit-of-work boundary **MUST** offer **bounded automatic retry** as specified
in `m-auto-retry`: a configurable bound (default **10**; `0` disables the loop),
and on a retriable failure a rollback, a freshness invalidation, and a
re-execution of the closure against fresh state. A conflict is **not**
automatically retried by default — it surfaces to the caller — and joins the
retriable set only when the unit of work opts in (`retryOptimisticConflicts`,
Reladomo's `setRetryOnOptimisticLockFailure`, default off). Transient database
failures (deadlock / serialization failure) are always retriable regardless of
that flag. A retry that exhausts its bound surfaces the conflict to the caller.

The suite proves the retriable half observably with a conflict case's
**`when.attempts`** sequence (`m-case-format`): a stale-version `UPDATE` affects `0`
rows, then a retry that re-reads the fresh version and re-applies affects `1` — the
`0`-then-`1` transition, asserted against real data. The loop-mechanics branches a
single-connection harness cannot provoke (a conflict surfacing without the opt-in,
an injected transient auto-retried, `retries: 0`, bound exhaustion) are authored as
**boundary** cases on the `api-conformance` lane and satisfied by each language's
API Conformance Suite (`m-api-conformance`).

Optimistic locking composes with **detached merge-back** (`m-detach`): the version
a detached copy carries is the one read at detachment, so a merge-back `UPDATE`
gates on that version and detects a conflict if the original changed in the
interim — exactly the same `updatedRows != 1` rule.

Optimistic locking composes with **inheritance** (`m-inheritance` × `m-sql`)
without disturbing the gate-last invariant. A concrete-subtype `UPDATE` under
table-per-hierarchy carries a **tag guard** (`and <tag.column> = ?`) that joins the
**identity predicates** — canonically right after the primary-key equality
(resolved Q9) — so the version gate still **binds last**:
`update animal set name = ?, version = ? where id = ? and kind = ? and version = ?`,
binds `[…set values…, pk, tagValue, observed-version]`. There is **no** inheritance
exception to *the version gate binds last*: one absolute, human-memorable rule holds
across every statement family, and the tag guard rides with the identity predicates,
never after the gate. The zero-row `updatedRows != 1` conflict signal is unchanged.

## What the suite pins down

`m-opt-lock` is proven by a **conflict case** (`m-case-format`): the golden
`UPDATE` is applied to a loaded table and the **affected-row count** is asserted.
The case carries an optional out-of-band **`given.apply`** — naive statement
entries that simulate a concurrent transaction mutating the row — and a
**`then.affectedRows`** count:

| Case | Concurrency Preference | given.apply | Golden gate | Affected rows |
|---|---|---|---|---|
| optimistic-lock conflict | optimistic | bump the row's version out of band | the now-stale observed version | **0** (conflict detected) |
| optimistic-lock success | optimistic | none | the observed version | **1** (write applied) |
| versioned update, effective Locking | locking | none | none — no gate, version still advances | **1** (write applied) |
| versioned update, effective Locking | locking | remove the row out of band | none — no gate | **0** (non-retriable stale write) |
| versioned delete, effective Locking | locking | remove the row out of band | none — no gate | **0** (non-retriable stale write) |

A companion **scenario** case pins the no-op rule: a versioned update whose `set`
changes no attribute declares `roundTrips: 0` and lists no golden DML (no
statement issued). Predicate-selected witnesses use a materializing `find`, the
structured `write` instruction, and a verification `find`; non-trivial finds carry
their own naive `referenceSql` oracle.

| Witness | Target / Concurrency Preference | Observable rule |
|---|---|---|
| `m-opt-lock-003`, `-004` | `Account` update, optimistic / locking | materialize then per-object update; optimistic reads/gates are lock-free, locking reads carry `for share of t0` and writes omit the gate |
| `m-opt-lock-014` | `Account` update, locking | mixed equal/changed rows gives `1 + 1`, proving per-row no-op elimination and no spurious version bump |
| `m-opt-lock-015` | `Account` delete, optimistic | every matched row is deleted through a version-gated per-row write; the final find proves only the unmatched account remains |
| `m-txtime-write-007` | Transaction-Time `Balance` terminate, locking | every current matched milestone is closed; no equality-elimination applies |
| `m-bitemp-write-010`–`-013` | `Position` plain / bounded correction or termination | the materialized observed rectangle is closed and the required head/middle/tail chain is emitted |

Each scenario's write step lists its ordered per-object golden statements
(`roundTrips: N`); the declared total is the honest `1 + N` materialize cost plus
any explicit verification read. Optimistic corpus cases carry
`when.uow: { concurrency: optimistic }`; locking cases carry
`when.uow: { concurrency: locking }`.

The harness loads the model's fixtures (the row exists with its current
version), applies `given.apply` (a concurrent version bump, for the conflict
case), runs the golden `UPDATE`, and asserts the affected-row count equals
`then.affectedRows` — and, when authored, the resulting table state. This
proves conflict detection against **real data**: the stale-version `UPDATE`
provably touches zero rows, the fresh-version one provably touches exactly one,
so `updatedRows != 1` is verified as the conflict signal rather than merely
asserted in prose.
