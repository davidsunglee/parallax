# M12 — Compatibility Harness & Test-Double Integration

`M12` is the **compatibility-case contract** and the no-mock, real-database
harness that proves it. It is **tooling, not an ORM**: it **never compiles
operations to SQL** — that is exactly what a real implementation must do and
prove against the golden SQL. The harness only proves the *suite itself* is
internally consistent and that the golden SQL is correct for the data, across
every database behind the provider seam. `M12` depends on `M2`, `M3`, `M4`,
`M7`, `M8`, `M9`, and `M10`.

The canonical reference implementation is `reference-harness/` (Python + uv +
sqlglot). Its *contract* is language-neutral; another ecosystem can re-implement
the runner.

**The harness is not an input to a language implementation.** The reference
harness is an executable oracle for the compatibility corpus, not a reference
architecture. Its internals — the SQL normalization strategy, the provider
seam, the assertion layering, and the module layout — are non-normative and
MUST NOT be used as design input for a language implementation. The binding
inputs are the spec modules, `core/schemas/`, the compatibility corpus, and the
conformance-adapter contract.

## The compatibility case

A case is a YAML document under `core/compatibility/cases/`, validated against
[`core/schemas/compatibility-case.schema.json`](../schemas/compatibility-case.schema.json).
Its fields:

A case is one of seven shapes: a **read case** (carries an `operation`), a
**writeSequence case** (carries a `writeSequence`, Phase 5 / M7), a **scenario
case** (carries a `scenario` of ordered read *and* committed-write steps, Phase
6 / M8), a **conflict case** (carries `expectedAffectedRows` for a single
attempt, or an `attempts` retry sequence, Phase 7 / M10), a **coherence
case** (carries a `coherence` two-node sequence, Phase 11 / cross-process
coherence), an **error case** (carries `errorClass` and
`expectedNativeCode`, Phase 12 / M11 error-code classification), or a **boundary
case** (carries `boundary` + `expect`, M8/M10 bounded automatic retry — an
`api-conformance`-lane case the harness schema-validates but does not execute).
The fields:

| Field | Required | Meaning |
|---|---|---|
| `model` | yes | path (relative to `core/compatibility/`) to the model descriptor |
| `tags` | yes | module/feature tags (e.g. `["m2", "eq"]`); drive coverage + test selection |
| `lane` | no | which executor satisfies the case (default `harness`): `harness` — the M12 harness runs it as today; `api-conformance` — schema-validated by the harness but satisfied by each language's API Conformance Suite (see *Case lanes*, below) |
| `operation` | read | a canonical M2 algebra node, validated against the operation schema (read cases) |
| `writeSequence` | write | an ordered list of mutations a write case realizes: `insert` / `update` / `terminate` (audit-only + business-only), `delete` (non-temporal delete / detached-delete merge-back), `cascadeDelete` (the minimal dependent-delete witness), plus the `insertUntil` / `updateUntil` / `terminateUntil` `*Until` trio for the full-bitemporal rectangle split |
| `equivalentEncodings` | no | alternate surface encodings of `operation` (e.g. a prefix vs a fluent spelling); each MUST canonicalize to `operation` |
| `goldenSql` | yes | **keyed by dialect** (`postgres: …`); the optimized SQL an impl must emit — a single statement, or an **ordered list** of statements (one per deep-fetch level, or one per write-sequence DML step) |
| `binds` | no | bind values for the `?` placeholders (default `[]`): a flat list for a single statement, or a list-of-lists for a multi-statement case. A deep-fetch level's `IN`-list binds are an **unordered set** — authored sorted for readability, but compared order-insensitively (see the fifth assertion layer); an implementation MAY emit them in any order and MUST NOT sort at runtime to match the fixture |
| `referenceSql` | conditional | an independent naive oracle (see below); for a deep fetch it is the naive single-statement oracle for the **root** row set |
| `expectedRows` | read | the rows the query must return (single-statement / flat-result cases) |
| `expectedGraph` | read | the assembled object graph a deep fetch must produce (one of `expectedRows` / `expectedGraph` is REQUIRED for a read case) |
| `expectedTableState` | write | the resulting table state a writeSequence case asserts, keyed by table name (REQUIRED for a write case) |
| `roundTrips` | no | declared statement count (default `1`); for a deep-fetch case it MUST equal the authored/executed goldenSql statement count (child SQL is omitted after an empty parent-key level); for a write sequence it MUST equal the ordered DML statement count |
| `tolerance` | no | absolute numeric comparison tolerance; omit for exact comparison (the default). Declare ONLY for inherently inexact results (stddev/variance, repeating-decimal avg) |

### goldenSql, referenceSql, expectedRows (the oracle question)

Each case carries **three independent things**, and the harness cross-checks all
three:

- **`goldenSql`** — the *optimized* SQL an implementation is **expected to
  emit**. This is the normative, per-dialect SQL contract a real ORM is graded
  against.
- **`expectedRows`** — the result the query must return, authored against the
  small fixture dataset.
- **`referenceSql`** — a deliberately *naive, obviously-correct* second
  formulation of the same query (e.g. a plain `IN (subquery)` instead of an
  optimized `EXISTS` join). An **independent oracle**.

Why the oracle matters: if a human hand-authors `goldenSql` and `expectedRows`,
both can be wrong *in the same way*, and a harness that only runs `goldenSql` and
compares to `expectedRows` would still pass — self-consistent but incorrect. The
independent `referenceSql`, written naively, is unlikely to share the bug; if
both return identical rows against real data, we have high confidence the golden
SQL is correct. (This is Reladomo's own `validateMithraResult(op, rawSql)`
discipline, made portable.)

**Policy.** `referenceSql` is **REQUIRED for non-trivial cases** (joins, deep
fetch, aggregation, temporal predicates) and **OPTIONAL for trivial single-table
predicate cases** where `expectedRows` is obviously verifiable by eye.

## The layered assertion model

Per case, against a freshly-provisioned database selected via the provider seam,
the harness asserts:

1. **Schema conformance** — the model descriptor validates against the metamodel
   schema; the `operation` against the operation schema; the case against the
   compatibility-case schema.
2. **Triple equivalence** — load the database from the descriptor + fixture data,
   then assert `exec(goldenSql[dialect]) == exec(referenceSql) == expectedRows`
   (the `referenceSql` term is included only when present). Row comparison is
   order-insensitive, and **numerics compare exactly in decimal space** (never
   through binary `float`), so a `decimal(p,s)` money column matches to the cent
   and a value's type never depends on whether it is whole. A case whose result
   is inherently inexact (stddev/variance, a repeating-decimal avg) — and so
   cannot be authored exactly and differs in scale across dialects — MAY declare
   a `tolerance`, making the numeric comparison `abs(actual - expected) <=
   tolerance`. Booleans compare only to booleans (`true` is never `1`).
3. **Normalization determinism** — `normalize(goldenSql[dialect]) ==
   goldenSql[dialect]` via sqlglot, per the M3 rules (alias scheme `t0,t1,…`,
   sorted binds, whitespace-collapsed, deterministic clause order).
4. **Serde round-trip** — `serialize(deserialize(x)) == x` for **both** the
   `operation` encoding *and* the model descriptor (the descriptor **is** the
   serialized metamodel), in **both** JSON and YAML. When a case declares
   `equivalentEncodings`, each alternate encoding MUST canonicalize (via the same
   serde seam) to the case's `operation` — a dialect-agnostic check that proves
   precedence / serialization fidelity (a prefix and a fluent surface of the same
   grouped predicate denote one canonical node) in the fixture itself.

A fifth layer — **round-trip-count consistency** — applies to relationship /
deep-fetch cases: the number of authored/executed golden SQL statements equals
the declared `roundTrips`, each non-empty child level executes keyed by the
distinct parent keys gathered from the previous level (an **unordered set** — the
`IN`-list bind order is *not* part of the contract, since it never changes which
children match, and child result order is fixed by the level's own `orderBy`; the
harness therefore compares each level's binds order-insensitively, consistent with
the order-insensitive row comparison of layer 2, and an implementation MUST NOT
sort these keys at runtime to match the fixture), empty parent-key levels execute
no child SQL, and the in-memory-assembled object graph equals the case's
`expectedGraph`. This is what proves N+1 elimination automatically (a 1 → N → N
deep fetch with non-empty levels must run in exactly 3 statements, not 1 + N +
N; a deep fetch whose root is empty runs only the root statement). For these
cases a dialect's `goldenSql` is an **ordered list** of statements (root plus
the child levels that execute) rather than a single string, and `expectedGraph`
replaces (or accompanies) `expectedRows`.

For each deep-fetch level whose child entity is temporal, the harness derives the
**propagated as-of binds independently** (an oracle, parallel to the ordering
oracle): it reads the root pin from the operation's nested `asOf` nodes, matches
each axis to the child entity's as-of dimension, and computes the expected child
as-of binds (the `infinity` equality for latest, the `[D, D]` range for an
instant, business axis first). It then splits the authored child binds into the
IN-list slice and the as-of suffix, asserting the slice equals the gathered
parent keys and the suffix equals the computed expectation — so a dropped or
wrong propagated as-of fails the case automatically. A non-temporal child has an
empty suffix.

For a writeSequence case inserting into a `sequence`-strategy entity, the
harness derives the **PK-generation oracle** (`case_runner._assert_pk_allocation`):
it independently re-derives the allocated primary keys and the registry counter
from the declared `pkGenerator` config (`initialValue`/`incrementSize`/
`batchSize`) and asserts both against the post-write DB state — proving the
golden's hand-authored ids actually follow the declared strategy (block
reservation, gap-on-unused, stride). `max` is pinned by its self-describing
`coalesce(max(...),0)+1` golden and needs no oracle.

### Write-sequence cases (M7 / M8 / M9 / M5)

A **writeSequence** case proves a write contract by *application*, not
introspection. The harness provisions a table, **applies the ordered DML golden
SQL in order** (with each statement's binds), then asserts the resulting rows
equal `expectedTableState`. This covers milestone-chaining temporal writes
(`insert` / `update` / `terminate` and the bitemporal `*Until` trio), batched
non-temporal writes, ordinary `delete`, and the minimal `cascadeDelete` witness
over dependent relationships. The DML statement count MUST equal the sum of the
`writeSequence` steps' declared statement counts and the case's `roundTrips`.
The model descriptor's serde round-trip (layer 4b) still runs; there is no
`operation` to serde (layer 4a) and no normalization difference — the DML golden
SQL is normalized to a fixed point exactly like read SQL (layer 3).

A writeSequence case MAY set **`loadFixtures: true`** to load the model's
fixtures **before** the ordered DML (instead of starting empty) — so a sequence
can mutate a *pre-existing* persisted row. This is the M9 detached-update
or detached-delete merge-back case, and the minimal dependent cascade-delete
witness: the original rows exist, the ordered DML mutates them, and the asserted
table state shows which rows changed or were removed.

### Conflict cases (M10)

A **conflict** case proves optimistic-lock conflict detection by the **affected-
row count** a golden `UPDATE` leaves behind. The harness loads the model's
fixtures (the versioned row exists), applies an OPTIONAL out-of-band
**`precondition`** (a naive SQL statement simulating a concurrent transaction
that bumped the version), runs the golden `UPDATE` (which gates on the version
the caller read earlier), and asserts the affected-row count equals
**`expectedAffectedRows`** — `0` for a stale version (conflict; the
`updatedRows != 1` signal) and `1` for a fresh version (success). When
`expectedTableState` is authored it is asserted too, confirming a conflicting
write did not apply. As with writeSequence cases, only the descriptor serde
round-trip and the golden-SQL normalization layers apply (there is no
`operation`).

A conflict case MAY instead carry an **`attempts`** retry sequence — an ordered
list of golden `UPDATE`s, each with its own `expectedAffectedRows` — proving the
**M10 retry contract** end-to-end. After the `precondition`, the harness applies
each attempt in order and asserts its affected-row count: the first (stale-
version) attempt affects `0` rows (the conflict signal), then a retry that re-
reads the now-fresh version and re-applies affects `1`. The final
`expectedTableState` confirms the retried write — not the concurrent writer's —
landed. (Golden SQL lives per attempt, so there is no top-level `goldenSql`.)

### Scenario cases (M8)

A **scenario** case proves the unit-of-work / identity / query-cache contract as
an ordered list of steps over one provisioned database. A **read step** issues a
`find` with a declared round-trip count (a cache hit declares `0` and lists no
golden SQL); a **write step** (`write`) **commits** golden DML between finds. The
write step is what makes **read-your-own-writes** and **query-cache
invalidation** expressible: a dependent find after a committed write must observe
it (and cannot be modeled as a cache hit, since reusing the stale pre-write rows
would fail the post-write `expectRows`). A write step defaults to **committing**
its DML; with **`rollback: true`** the harness applies the DML then **rolls it
back** (through the provider's manual-commit session seam) — the observable form
of the M8 **abort contract**: a later find MUST re-resolve and observe the
ORIGINAL rows, never the aborted write. A write step with **`roundTrips: 0`** and
no golden SQL is a **no-op** write — a versioned `UPDATE` whose `set` changes no
attribute issues no DML (`M10`) — and executes nothing, exactly like a cache-hit
read step. The rolled-back DML still executes, so it counts its statements as
round trips exactly as a committed write does. The harness asserts per-step
round-trip / golden-SQL count consistency, executes each step, and checks
`sameObjectAs` identity assertions; it never compiles an operation to SQL.

A case MAY carry a top-level **`uow`** block (`{ concurrency: locking |
optimistic }`) declaring the unit-of-work strategy its golden SQL runs under (`M8`
strategy selection). The block is **descriptive**: the harness executes the
authored golden SQL either way — the block records which mode produced it, so an
optimistic conflict case's gated `UPDATE` and a locking-mode case's ungated
version-advancing `UPDATE` are self-describing. Its default is `locking`.

### Coherence cases (M14 cross-process coherence)

A **coherence** case proves the cross-process cache-coherence contract (one node
observes another's committed write) by running a two-node operation sequence over
**two connections to one database**. The harness provisions one database (node A
= the provider's own connection, with the model's fixtures loaded so the seed read
sees a row), opens a second independent connection via the provider's **two-node
seam** (`open_peer`, below), and runs each `coherence` step on its declared node:
a `write` step **commits** DML on its node; a `read` step queries. The final
node-B re-fetch carries **`observeRows`** — node A's committed **post-write**
state, which node B **MUST** observe (never the stale pre-write rows). Each step's
golden SQL is normalized (layer 3), and the read steps' operations and the
descriptor survive serde (layer 4). The harness contains no cache and no
notification bus; it proves the suite's post-write golden SQL is correct against
real, committed, cross-connection data — the observable contract any conforming
invalidation mechanism (full-cache re-fetch or partial-cache mark-dirty) must
satisfy. See [`m14-cross-process-coherence.md`](m14-cross-process-coherence.md).

A read step MAY additionally declare `sameObjectAs` (with an optional
`identityAttr`): the harness asserts its observed rows carry the same primary-key
identity as an earlier same-node read, exercising M14's identity-preservation
contract (the refresh updates the interned object in place rather than forking a
new one for the same primary key).

### Error cases (M11 error-code classification)

- **error** (M11 error-code classification) — triggers a *real* database error and
  asserts the neutral category it classifies to (`errorClass`) plus the per-dialect
  native code (`expectedNativeCode`). `uniqueViolation` cases trigger
  single-connection: ordered golden DML whose final statement raises (a duplicate
  insert / a colliding update). `deadlock` and `lockWaitTimeout` cases trigger
  two-connection: a `concurrency` choreography of barrier-separated rounds, each
  naming the statements nodes A and B run that round. The harness runs each node on
  its own **non-autocommit session** (the provider seam's `open_session`, with the
  dialect's lock-contention tuning — Postgres `deadlock_timeout`/`lock_timeout`,
  MariaDB `innodb_lock_wait_timeout` — applied so a blocked lock fails fast), drives
  them on threads synchronized by a barrier, and classifies the error raised in the
  contention round via the provider's `classify_error`. The classifier is a thin
  per-dialect extraction (Postgres SQLSTATE, MariaDB errno) over the shared,
  DB-free category map + call-site predicates; the runner asserts the predicate
  partition, so the harness exercises the interface the language implementations
  build, not a harness-only shortcut.

### Boundary cases (M8 / M10 bounded automatic retry)

A **boundary** case proves the unit-of-work **bounded automatic retry** contract
(`M8` *Bounded automatic retry*, `M10` *Retry contract*): a loop-mechanics branch
whose observable — a retriable failure auto-retried away, a conflict surfaced
without the opt-in, a disabled loop (`retries: 0`), an exhausted bound, a callback
value withheld on abort — a **single-connection** harness cannot provoke, because
it needs an **injected transient failure** and a re-executed closure. It carries a
portable `boundary` (the ordered unit-of-work actions), an OPTIONAL `inject` (a
portable fault kind — `serialization-failure` / `deadlock` / `lock-wait-timeout` /
`optimistic-lock-conflict`, aligned with the `M11` `errorClass` vocabulary), an
`expect` (the portable outcome — `committed`, or a surfaced error kind), and its
retry configuration under `uow` (`retries` / `retryOptimisticConflicts`). It
carries **no** golden SQL — the concrete DML and error types stay per-language.
Every boundary case is on the `api-conformance` lane.

## Case lanes

Every case declares a **lane** (`lane`, default `harness`) naming which executor
satisfies it:

- **`harness`** — the M12 harness executes the case as today: it runs the golden
  SQL / data observables against a provisioned database.
- **`api-conformance`** — the harness **schema-validates** the case (layer 1) but
  does **not** execute it: its observable is a runtime-loop or read-lock-matrix
  branch (an injected transient, retry counting, error surfacing, the emitted
  read-lock proof) that a single-connection harness cannot provoke. **Each
  language's API Conformance Suite MUST satisfy every `api-conformance`-lane
  case**, with coverage enforced the way the suite's own partition assertion
  (`covered.ts`) self-asserts today. This keeps every clarified branch specified in
  core and executably covered, even the ones the harness itself cannot run. Every
  `boundary`-shape case is `api-conformance`; the read-lock matrix reads (object
  find locks, projection omits the lock, deep fetch locks every level, optimistic
  reads omit the lock) are `read`-shape `api-conformance` cases.

## Provisioning ↔ runner seam (DQ15)

The harness splits into two clearly-separated sub-parts joined by an explicit
seam so provisioning can be swapped without touching the assertion layer:

- **Provisioning — the `DatabaseProvider` seam.** Each provider yields a clean,
  migrated, isolated database for a single dialect, exposing `reset`,
  `apply_ddl`, `load`, `query`, `execute` (DML, for write sequences), and a
  `dialect` identifier. **Testcontainers** is the default mechanism, pinned at
  the latest stable Postgres major; a language **MAY** substitute an embedded
  binary that satisfies the same reset/isolation contract. An **optional**
  `open_peer` capability (Phase 11) yields a second, independent connection to the
  **same** database — modeling a peer application server (node B) for coherence
  cases; a provider that omits it simply cannot run coherence cases.
- **Runner + assertions.** The case runner applies the four (later five) layers
  above against whatever provider it is handed.

This seam is also the **database-provider seam** that grows the matrix: adding a
dialect is a new provider behind the same protocol, and the
**compatibility-matrix report** (implementations × databases) is produced by
running the suite across every available provider.

## Test-double integration

Per DQ8, most tests **SHOULD** live at this compatibility-suite level — the suite
is the primary behavioral surface across all languages — rather than buried in
per-language unit tests. Each per-language spec specifies how its test runner
(pytest / JUnit / `cargo test`) wires to the database provider.

## Language implementation conformance adapter

The reference harness proves the corpus itself is coherent. A concrete language
implementation proves conformance through the M12-adjacent adapter contract in
[`conformance-adapter-contract.md`](conformance-adapter-contract.md).

That adapter is the external seam between a corpus runner and a language
implementation. It exposes a small command surface (`describe`, `compile`,
`run`, and `benchmark`) and emits JSON documents validated by
[`../schemas/conformance-adapter.schema.json`](../schemas/conformance-adapter.schema.json).
It MUST accept compatibility corpus files as input and MUST report SQL
emissions or runtime observations without exposing implementation internals.
