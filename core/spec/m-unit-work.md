# m-unit-work — Transactions & Unit of Work

`m-unit-work` is the transaction scope: the unit of work that **buffers, orders,
and flushes** writes, and the automatic read-correctness rules that make
in-transaction reads safe. It is expressed entirely in terms of **operations and
object state** (`m-op-algebra`): it depends on `m-op-algebra` and on the execution
port `m-db-port`, but **not** on `m-sql`. The dialect-specific SQL the unit of work
executes (the read-lock suffix, the batched forms) is produced by `m-sql` and run
through the `m-db-port` execution seam at the composition root, so `m-unit-work`
takes no direct edge to SQL generation. (`m-op-list` and `m-navigate` in turn
depend on `m-unit-work`, because a list is an operation-backed view resolved within
a unit of work.)

Layered on the unit of work are four modules: the automatic shared read lock
(`m-read-lock`), bounded automatic retry (`m-auto-retry`), the transaction-scoped
identity map (`m-identity-map`), and the process-wide identity + query caches
(`m-process-cache`, deferred).

## The unit of work

A **unit of work** (transaction) is the scope within which object reads and
writes are coherent. Within one unit of work:

- Writes are **buffered** as pending operations, not flushed eagerly. At the
  unit-of-work boundary they are **combined, batched, and ordered** to respect
  foreign-key constraints, then flushed in one pass.
- A read that depends on a not-yet-flushed write **MUST** observe that write: the
  unit of work flushes pending writes before serving a dependent read
  (read-your-own-writes), so a query never returns stale in-transaction state.

> **The transaction boundary is user-specified, per-language.** How a unit of
> work is opened and committed — a closure, a context manager, a decorator, an
> explicit `begin`/`commit` pair — is an idiomatic, per-language concern and is
> pinned down in the per-language spec, **never** in raw SQL terms in core. Core
> mandates the *observable effects within and at* the boundary, not its syntax.

### No identity promise

`m-unit-work` is expressed purely in **operations** — it promises nothing about
*object identity*. Without a claimed identity module, two reads of one row
within a unit of work MAY yield distinct managed instances, and mutating both
buffers conflicting updates whose interleaving is unspecified — a **named
hazard**, not a contract. The guarantee that one database identity resolves to
one managed object within the unit of work is `m-identity-map`; a plain-value
read surface (`m-snapshot-read`) has no managed instances to promise identity
for. This silence is deliberate in **both** directions: nothing here mandates
that two reads yield the *same* instance, and nothing may mandate they yield
*distinct* instances.

## Abort

A unit of work either **commits** or **aborts** (rolls back). A commit makes its
writes durable and observable; an **abort discards them entirely**. The
observable contract:

- A write performed inside a unit of work that aborts **MUST NOT** be observable
  after the abort — whether it was still **buffered**, had been **force-flushed**
  to serve a dependent read (read-your-own-writes), or had populated a cache. A
  find issued after the abort **MUST** re-resolve and observe the
  **pre-transaction** state.
- The transaction callback's return value is **withheld on abort**: if the unit
  of work rolls back — or its commit fails — the operation **fails** rather than
  returning the callback value as though it were durable (promoting ADR 0006 into
  normative text).

This reconciles the abort contract with the **read-your-own-writes forced flush**.
The forced flush is safe precisely *because* it lands **inside the still-open
atomic scope** the abort discards: the unit of work may push a buffered write to
the database mid-transaction so a dependent read observes it, yet an abort still
erases that write — the flush never escapes the transaction it belongs to. An
implementation **MUST NOT** satisfy read-your-own-writes with a flush that survives
the abort.

The suite proves this with a **rollback scenario**: a find, a write step whose
golden DML is applied and then **rolled back**, and the *same* find re-issued —
which **MUST** re-resolve and observe the **original** rows, never the aborted
write.

## Buffered, batched, ordered writes

At the unit-of-work boundary the buffered writes are flushed as **set-based** SQL
wherever possible:

- Multiple inserts or same-column updates of one entity collapse into set-based
  SQL — a single multi-row `INSERT`, a batched `UPDATE`. The canonical golden
  forms and their proof are `m-batch-write`.
- Operations are **ordered** so that a parent row is inserted before a child
  that references it (and deleted after), honoring foreign-key constraints.

## Write instruction vocabulary

Every write a unit of work buffers — from any frontend, keyed or predicate-selected
— is a neutral **write instruction**, the write-side analogue of the operation
algebra. The canonical, language-neutral shapes are hosted in
[`write-instruction.schema.json`](../schemas/write-instruction.schema.json), mirroring
how `m-op-algebra` hosts `operation.schema.json`; `m-case-format` and
`m-conformance-adapter` reference that shape rather than redefining it. There are two:

- a **keyed** instruction — a `mutation` on one `entity` carrying the flat
  attribute-named neutral write input (`rows`);
- a **predicate-selected** instruction — a `mutation` on every row of a `target`
  (`entity` plus a bare `m-op-algebra` predicate) matching that predicate, with
  `assignments` on the update forms.

The embedded predicate is a canonical `m-op-algebra` node, legal vocabulary here
because `m-unit-work` already depends on `m-op-algebra` (the dependency-graph edge);
the write instruction is the sole place the write side reaches the algebra. Two
structural rules keep the instruction framework-honest:

- **The instant surface is axis-explicit.** A temporal write's authored **business
  bounds** are named uniformly `businessFrom` / `businessTo`. The **processing
  instant** is *not* an instruction field — it is supplied at flush from the Clock
  Strategy (ADR 0010), so no caller-facing shape can smuggle one in. (The corpus's
  `at` / `businessAt` / `until` spellings are authoring aliases of these canonical
  names; the corpus-wide re-authoring is deferred.)
- **The transaction observation is not an instruction field.** The framework-owned
  optimistic version / observed `in_z` a gated write binds (`m-opt-lock`) is attached
  **per materialized row at flush**, never carried on the durable instruction: the
  reserved `observedVersion` / `observedInZ` control keys are explicitly **forbidden**
  on a `write-instruction.schema.json` write row, so an observation cannot round-trip
  as instruction state — the structural guarantee that versions stay framework-owned
  (ADR 0013). They are flush-time context on the case format's materialization row.

A conforming implementation **MUST** round-trip every instruction through the
canonical form losslessly (`serialize(deserialize(x)) == x`), the write-side of the
`m-op-algebra` serde contract.

## Same-transaction write coalescing

Buffered writes of the **same object within one unit of work** combine before flush —
they annihilate or merge rather than each producing durable SQL, because a state a
transaction never durably exposed to any other reader is never separately recorded.
This follows Reladomo's transaction write queue (`TxOperations` /
`GenericBiTemporalDirector` same-transaction handling): a same-transaction
insert-then-update writes the final value in place, and a delete cancels a matching
pending insert.

- **Insert-then-update coalesces in place.** A row inserted and then updated in the
  same unit of work flushes as a **single** write carrying the **final** value; no
  intermediate milestone is fabricated. A **non-temporal** insert-then-update emits
  one `INSERT` with the post-update values (never `INSERT` + `UPDATE`); an
  **audit-only** insert-then-update opens a single current milestone with the final
  value — no close-and-chain, in contrast to the cross-transaction chaining of
  `m-audit-write`; a **bitemporal** insert-then-update opens a single fully-current
  rectangle with the final value — no inactivation / head-tail split, in contrast to
  the cross-transaction rectangle split of `m-bitemp-write`.
- **Insert-then-delete cancels.** A row inserted and then deleted in the same unit of
  work **cancels**: the two buffered writes annihilate and the flush emits **no** DML
  for that object — the net-zero effective-change-set elision, extended across two
  verbs.

Coalescing is a property of **one** unit of work; across two committed transactions
the milestone modules chain and split as usual. The rule is centralized here because
it is a buffering decision, not a per-verb one — the milestone modules
(`m-audit-write`, `m-bitemp-write`) describe the durable cross-transaction shapes and
defer the same-transaction combination to this scope.

A coalescing witness encodes **both** buffered mutations explicitly by authoring
the write step as an ordered **buffer-and-flush** scenario: `/scenario/<n>/write`
carries the ordered buffer of write instructions (the keyed `insert` of the new
object, then the keyed `update` / `delete` of that same object), and the step's
golden SQL is the independent expected lowering of the coalesced flush — one
final-value write, or no DML at all. The buffered form and its authoring surface are
the case format's (`m-case-format`); the instructions themselves are the canonical
`write-instruction.schema.json` shapes, so an adapter exercises coalescing from the
requested operations, never from the golden SQL.

## Strategy selection — the per-unit-of-work participation mode

A unit of work selects, per transaction, **how** its read-then-writes are made
correct — mirroring Reladomo's `TxParticipationMode`. Two strategies:

- **`locking`** (the **default**) — the automatic in-transaction shared read lock
  (`m-read-lock`). Reads take a row lock; writes need no version gate.
- **`optimistic`** — the alternative (`m-opt-lock`): reads take **no** lock (so
  readers never block writers), and every keyed write gates on the version the
  unit of work observed. Selected explicitly on the unit of work
  (`concurrency: optimistic`).

The mode is a property of the **unit of work**, not of the entity: the same
versioned entity is written under the shared lock in one workflow and under the
version gate in another. The metamodel only *names* the version column
(`m-descriptor`); opting into optimistic mode is what drops the read locks and
emits the gate.

## What the suite pins down

`m-unit-work`'s observable rules are expressed as **scenario** cases — ordered
operation steps, each with a declared round-trip count — and plain write cases:

| Case | What it proves |
|---|---|
| read-your-own-writes scenario | a buffered write is flushed before a dependent find observes it |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |
| fk-ordering / flush cases | buffered writes flush ordered by foreign-key dependency |
| insert-then-update coalescing (`m-unit-work-008`, `m-audit-write-008`, `m-bitemp-write-014`) | a same-transaction insert-then-update flushes as one write with the final value — no intermediate milestone (non-temporal / audit-only / bitemporal) |
| insert-then-delete cancellation (`m-unit-work-010`) | a same-transaction insert-then-delete cancels — the flush emits no DML for that object |

A scenario's declared round-trip counts **MUST** be internally consistent with
the golden SQL it lists: each step's `roundTrips` equals the number of golden SQL
statements that step emits. The harness asserts this consistency without ever
compiling an operation to SQL — proving the round-trip contract from the fixture
itself — and executes the listed golden SQL against the real database to confirm
result-correctness.
