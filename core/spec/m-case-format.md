# m-case-format — Compatibility Case Format & Harness

`m-case-format` is the **compatibility-case contract** and the no-mock,
real-database harness that proves it. It is **tooling, not an ORM**: it **never
compiles operations to SQL** — that is exactly what a real implementation must do
and prove against the golden SQL. The harness only proves the *suite itself* is
internally consistent and that the golden SQL is correct for the data, across
every database behind the provider seam. As a conformance-family module,
`m-case-format` declares only the structural edge `m-case-format --> m-core`; by
construction it harnesses (references) every behavioral module it grades.

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

A case's identity is its **filename**, `<module>-NNN-<slug>.yaml`: `<module>` is the
primary module slug the case chiefly proves (the first module tag in its `tags`),
`NNN` is a 3-digit sequence number unique **within that module** (not globally), and
`<slug>` is a short descriptive name. The case **ID** is the `<module>-NNN` prefix
(e.g. `m-batch-write-001`); a case carries no separate `id` field, and IDs need only
be unique per primary module — numbering is never coordinated across modules.

`m-` is a **reserved tag namespace**: a `tags` entry matching
`^m-[a-z0-9]+(-[a-z0-9]+)*$` names a module and is validated against the closed
catalog in [`modules.md`](modules.md); every other tag is a free-form feature tag. A
case ID (`m-pk-gen-001`) also matches that grammar — a harmless overlap, since module
identity is only ever resolved against the catalog, never inferred from a filename.

### Its fields — grouped `given` / `when` / `then`

A case reads top-to-bottom as a behavioral sentence — **given** an ambient
world-state, **when** an action is performed, **then** these things hold. Identity
and routing (`model`, `tags`, `lane`) plus the explicit `shape` discriminator stay
**top-level**; everything else buckets into three closed groups:

- **`given`** — the world-state established BEFORE the action: `fixtures` (whether
  the model's rows are pre-loaded), `apply` (out-of-band naive SQL run verbatim),
  and `fault` (an injected fault kind). Optional — a case that starts from the
  model's default fixtures and injects nothing omits `given` entirely.
- **`when`** — the action under test and how the client performs it. Exactly one
  **action** member per shape (`operation` | `writeSequence` | `scenario` |
  `coherence` | `concurrency` | `boundary` | `attempts`, plus the single-attempt
  conflict's `write`); the **context** members (`uow`, `at`, `observedInZ`,
  `equivalentEncodings`) describe the unit-of-work mode, transaction instant,
  observed version, and alternate surface encodings.
- **`then`** — everything the case asserts: the golden `statements`, the naive
  `referenceSql`, the observed data (`rows` / `graph` / `tableState`), the counts
  and codes (`affectedRows` / `errorClass` / `nativeCode` / `roundTrips`), the
  portable boundary `outcome`, and the numeric-comparison `tolerance`.

`model` / `tags` / `lane` stay top-level because they are routing/discovery fields
read by the coverage gate and the language gate; grouping them buys no readability.

#### Case shapes

A case is one of **nine shapes**, named by the required top-level `shape`:

- **`read`** — a queryable `when.operation` naming its `when.targetEntity`,
  asserting `then.rows` or a deep-fetch `then.graph`.
- **`writeSequence`** — ordered DML under `when.writeSequence`, asserting the
  resulting `then.tableState` (the temporal writes `m-audit-write` /
  `m-bitemp-write` / `m-business-only`, the set-based `m-batch-write`,
  `m-cascade-delete`, and `m-detach` merge-backs).
- **`scenario`** — a `when.scenario` of ordered read *and* committed-write steps,
  golden SQL per step (`m-unit-work`).
- **`conflict`** — an optimistic-lock `UPDATE` asserted by `then.affectedRows` for
  a single attempt, or an ordered `when.attempts` retry sequence (`m-opt-lock`).
- **`coherence`** — a `when.coherence` two-node sequence (`m-coherence`).
- **`error`** — asserts `then.errorClass` + `then.nativeCode` (`m-db-error`),
  triggered by top-level `then.statements` (single-connection `uniqueViolation`) or
  a `when.concurrency` deadlock / lock-wait choreography.
- **`concurrencySuccess`** — a `when.concurrency` choreography with **no**
  `then.errorClass` (`m-read-lock` behavioral read-lock — barrier-separated rounds
  on two held sessions that assert no error is raised; every present step declares
  an explicit `kind`, a `read` step's `expectRows` observed on its held session, a
  `write` step asserting only that it did not block/raise). Proves the shared read
  lock is compatible with a second reader and that an unlocked projection admits a
  writer.
- **`boundary`** — `when.boundary` ordered actions + `then.outcome`
  (`m-auto-retry` — an `api-conformance`-lane case the harness schema-validates but
  does not execute, carrying no golden SQL).
- **`rejected`** — a schema-valid `when.operation` **or** a `when.write` a
  model-aware validator MUST refuse **before any SQL**, naming the violated
  normative rule in `then.rejectedRule` (`m-value-object` / `m-op-algebra` negative
  validation, carrying no golden SQL — see *Rejected cases*, below).

#### The statement entry

Every SQL statement in a case — golden or naive — is a **statement entry**: a
closed `{sql, binds}` object carrying one logical statement together with its own
binds. This is the single most load-bearing structure in the format: one shared
vocabulary everywhere SQL appears (`then.statements`, every per-step `statements`
list, and `given.apply`), so there is **no positional pairing convention** to learn
— each statement's binds are attached to it structurally.

At **golden locations** (`then.statements`, the per-step `statements` lists in
scenario / coherence / attempts / concurrency) `sql` is a **dialect-keyed map**
(`postgres` / `mariadb`), the dialect texts side by side, and `binds` is authored
once (bind order is identical across dialects), defaulting to `[]`:

```yaml
then:
  statements:
    - sql:
        postgres: select t0.id, t0.name from orders t0 where t0.id in (?, ?, ?)
        mariadb: select t0.id, t0.name from orders t0 where t0.id in (?, ?, ?)   # optional
      binds: [1, 2, 42]
```

**`binds` follows the same scalar-or-dialect-keyed form as `sql`.** The flat array
above is the authored form wherever the bind holes are shared across dialects
(every ordinary case). Where the hole structure *diverges* — the structured-document
extraction, where Postgres carries one bind per JSON path segment while MariaDB
carries a single `'$.a.b'` path bind (`m-dialect`) — `binds` is a **dialect-keyed
map** whose keys **MUST** equal that statement's `sql` map's keys (harness-asserted):

```yaml
then:
  statements:
    - sql:
        postgres: select t0.id from customer t0 where jsonb_extract_path_text(t0.address, ?, ?) = ?
        mariadb: select t0.id from customer t0 where json_value(t0.address, ?) = ?
      binds:
        postgres: ['geo', 'country', 'US']
        mariadb: ['$.geo.country', 'US']
```

`then.referenceSql` is polymorphic the same way: a plain string wherever one naive
spelling runs verbatim on every dialect (the authored default), or a dialect-keyed
map — whose keys **MUST** equal the golden `sql` map's keys (harness-asserted, exactly
as for a `binds` map) — where the naive spelling itself is dialect-specific (Postgres
reads the JSON with the `->>` operator and a bare key, MariaDB — a **different**
function family from its `json_value` golden — with
`nullif(json_unquote(json_extract(col, '$.path')), 'null')`). The harness runs the entry
matching the executing dialect; a map that omits a dialect its golden `sql` declares is
a **loud failure**, never a silently skipped oracle (which would let that dialect's
golden SQL go unchecked by the independent oracle).

At the **naive location** (`given.apply`) `sql` is a plain, dialect-agnostic
**string** run verbatim on every dialect:

```yaml
given:
  apply:
    - sql: update account set balance = 999.00, version = 2 where id = 2
```

A multi-statement (deep fetch) golden is an ordered list of entries — one per
deep-fetch level or write-sequence DML step; each entry carries only its own
`binds`, and a statement with no binds omits the `binds` key entirely:

```yaml
then:
  statements:
    - sql:
        postgres: select t0.id, t0.order_id, t0.sku, t0.quantity from order_item t0
    - sql:
        postgres: select t0.id, t0.name from orders t0 where t0.id in (?, ?, ?)
      binds: [1, 2, 42]
```

A deep-fetch child level's `IN`-list binds are an **unordered set** — authored
sorted for readability, but compared order-insensitively (see the fifth assertion
layer); an implementation MAY emit them in any order and MUST NOT sort at runtime
to match the fixture.

#### Row and table-state style

An expected row (`then.rows`, `then.graph` leaves, a `then.tableState` row) is
authored as an **inline flow map** whenever the rendered line fits the file's
line-length norm (~120 characters), and as a **block map** otherwise. Result rows
are almost always inline (`- { order_id: 2, total_quantity: 4 }`); wide bitemporal
table-state rows, which do not fit, stay readable as block maps. Timestamp columns
in `then.tableState` are ISO-8601 UTC strings at core microsecond precision, with
the open-bound `infinity` as the literal string `infinity`.

#### Field table

| Field | Group | Required | Meaning |
|---|---|---|---|
| `model` | top-level | yes | path (relative to `core/compatibility/`) to the model descriptor |
| `tags` | top-level | yes | module/feature tags (e.g. `["m-op-algebra", "eq"]`); drive coverage + test selection |
| `lane` | top-level | no | which executor satisfies the case (default `harness`): `harness` — the harness runs it as today; `api-conformance` — schema-validated by the harness but satisfied by each language's API Conformance Suite (see *Case lanes*, below) |
| `shape` | top-level | yes | the explicit shape discriminator — one of the nine shapes above; the schema `oneOf` keys on this `const` |
| `given.fixtures` | `given` | no | load the model's fixtures BEFORE the action (default `false`), so a sequence can mutate pre-existing persisted rows |
| `given.apply` | `given` | conflict | an ordered list of out-of-band **naive statement entries** (`sql` a plain string) the harness applies verbatim after fixtures load and before the golden `UPDATE` — a concurrent transaction's stale-version mutation |
| `given.fault` | `given` | boundary | an injected portable fault kind (`serialization-failure` / `deadlock` / `lock-wait-timeout` / `optimistic-lock-conflict`) driving the retry loop |
| `when.operation` | `when` | read | a canonical `m-op-algebra` node, validated against the operation schema (read cases) |
| `when.targetEntity` | `when` | read | the entity the read TARGETS — the queried position `when.operation` starts from (see *Read targeting*, below); REQUIRED on every read case and every scenario / coherence read step |
| `when.writeSequence` | `when` | writeSequence | an ordered list of mutations a write case realizes: `insert` / `update` / `terminate` (audit-only, business-only, **and full-bitemporal** — the plain, unbounded bitemporal writes are all first-class degenerate rectangle splits with no `until`: plain `insert` is a single fully-current `INSERT`, plain `update` is inactivate + `head` + new `tail`, plain `terminate` is inactivate + `head` only), `delete` (non-temporal delete / detached-delete merge-back), `cascadeDelete` (the minimal dependent-delete witness), plus the `insertUntil` / `updateUntil` / `terminateUntil` `*Until` trio for the bounded full-bitemporal rectangle split |
| `when.scenario` | `when` | scenario | an ordered list of read / committed-write steps, each carrying its own per-step golden `statements` |
| `when.coherence` | `when` | coherence | a two-node (A / B) operation sequence, each step carrying its node, kind, and per-step golden `statements` |
| `when.concurrency` | `when` | error / concurrencySuccess | a two-connection, barrier-separated `rounds` choreography; each node step carries per-step golden `statements` |
| `when.boundary` | `when` | boundary | an ordered list of portable unit-of-work actions (`read` / `create` / `update` / `terminate` / `delete`) |
| `when.attempts` | `when` | conflict | an ordered retry sequence of optimistic-lock `UPDATE` attempts, each carrying its own `statements` + `affectedRows` + `write` |
| `when.write` | `when` | conflict | the single-attempt neutral write input (①): the flat attribute-named row the versioned `UPDATE` (or temporal close) operates on |
| `when.uow` | `when` | no | unit-of-work configuration (`concurrency: locking \| optimistic`, `retries`, `retryOptimisticConflicts`) the action runs under; descriptive |
| `when.at` / `when.observedInZ` | `when` | conflict | a temporal-close conflict's close instant (→ new `out_z`) and observed processing-from (`in_z`) the optimistic gate binds |
| `when.equivalentEncodings` | `when` | no | alternate surface encodings of `when.operation`; each MUST canonicalize to it |
| `then.statements` | `then` | yes* | the golden SQL an impl must emit — an ordered list of `{sql, binds}` statement entries (dialect-keyed map form), one per deep-fetch level or write-sequence DML step. *Absent for scenario / attempts cases, whose golden SQL lives per step; disallowed on a boundary case |
| `then.referenceSql` | `then` | conditional | an independent naive oracle (see below) — a plain string, OR a dialect-keyed map where the naive spelling is dialect-specific; for a deep fetch it is the naive single-statement oracle for the **root** row set |
| `then.rows` | `then` | read | the rows the query must return (single-statement / flat-result cases) |
| `then.graph` | `then` | read | the assembled object graph a deep fetch must produce (one of `then.rows` / `then.graph` is REQUIRED for a read case) |
| `then.tableState` | `then` | writeSequence | the resulting table state a writeSequence (or conflict) case asserts, keyed by table name (REQUIRED for a write case) |
| `then.affectedRows` | `then` | conflict | the number of rows the golden `UPDATE` must affect (`0` = stale-version conflict, `1` = success) |
| `then.errorClass` | `then` | error | the neutral `m-db-error` category a triggered error must classify to (`uniqueViolation` / `deadlock` / `lockWaitTimeout`) |
| `then.nativeCode` | `then` | error | the per-dialect native code each driver must surface (Postgres SQLSTATE string, MariaDB vendor errno) |
| `then.outcome` | `then` | boundary | the portable expected outcome (`committed` / `aborted` / a surfaced error kind) |
| `then.rejectedRule` | `then` | rejected | the normative rule the input violates, from the closed vocabulary a model-aware pre-SQL validator MUST enforce (see *Rejected cases*) |
| `then.roundTrips` | `then` | no | declared statement count (default `1`); for a deep-fetch case it MUST equal the authored/executed `then.statements` count (child SQL is omitted after an empty parent-key level); for a write sequence it MUST equal the ordered DML statement count; for a scenario the SUM of per-step round trips |
| `then.tolerance` | `then` | no | absolute numeric comparison tolerance; omit for exact comparison (the default). Declare ONLY for inherently inexact results (stddev/variance, repeating-decimal avg) |

#### Read targeting (`targetEntity`)

Every read names the entity it targets. A read case carries **`when.targetEntity`**
(a metamodel entity name) alongside `when.operation`, and every **read step** of a
scenario or coherence case carries a step-level `targetEntity` alongside its
`find`. This is REQUIRED — the read side reaches the same explicit-entity standard
the write side already meets with `writeSequence[].entity`, so an `all: {}` read no
longer names its subject only in a comment or in the golden SQL.

`targetEntity` names the **queried position** the operation starts from. When an
entity participates in an inheritance family, that position may be abstract: an
abstract **root** targets the whole family, an abstract **subtype** targets its
concrete descendants, and a concrete subtype targets itself. Today every entity is
concrete, so `targetEntity` names exactly the entity whose rows the read returns —
the forward-referencing abstract vocabulary changes nothing until inheritance
families exist.

`targetEntity` is a first-class, machine-checkable field, not documentation: a
model-aware harness cross-checks it against every queried-entity `Class.attribute`
/ `Class.relationship` reference in the operation (the class part of each top-level
predicate, order-by key, nested-value-object path, navigation relationship, and
deep-fetch root hop MUST name `targetEntity`; a navigation's inner operation
resolves against the *related* entity and is not cross-checked). Until inheritance
families exist, "consistent" means "equal".

### `then.statements`, `then.referenceSql`, `then.rows` (the oracle question)

Each case carries **three independent things**, and the harness cross-checks all
three:

- **`then.statements`** — the *optimized* golden SQL an implementation is
  **expected to emit** (the per-dialect `sql` inside each statement entry). This is
  the normative, per-dialect SQL contract a real ORM is graded against.
- **`then.rows`** — the result the query must return, authored against the small
  fixture dataset.
- **`then.referenceSql`** — a deliberately *naive, obviously-correct* second
  formulation of the same query (e.g. a plain `IN (subquery)` instead of an
  optimized `EXISTS` join). An **independent oracle**.

Why the oracle matters: if a human hand-authors the golden `then.statements` and
`then.rows`, both can be wrong *in the same way*, and a harness that only runs the
golden SQL and compares to `then.rows` would still pass — self-consistent but
incorrect. The independent `then.referenceSql`, written naively, is unlikely to
share the bug; if both return identical rows against real data, we have high
confidence the golden SQL is correct. (This is Reladomo's own
`validateMithraResult(op, rawSql)` discipline, made portable.)

**Policy.** `then.referenceSql` is **REQUIRED for non-trivial cases** (joins, deep
fetch, aggregation, temporal predicates) and **OPTIONAL for trivial single-table
predicate cases** where `then.rows` is obviously verifiable by eye.

## The layered assertion model

Per case, against a freshly-provisioned database selected via the provider seam,
the harness asserts:

1. **Schema conformance** — the model descriptor validates against the metamodel
   schema; the `operation` against the operation schema; the case against the
   compatibility-case schema.
2. **Triple equivalence** — load the database from the descriptor + fixture data,
   then assert `exec(then.statements[].sql[dialect]) == exec(then.referenceSql) ==
   then.rows` (the `then.referenceSql` term is included only when present). Row
   comparison is
   order-insensitive, and **numerics compare exactly in decimal space** (never
   through binary `float`), so a `decimal(p,s)` money column matches to the cent
   and a value's type never depends on whether it is whole. A case whose result
   is inherently inexact (stddev/variance, a repeating-decimal avg) — and so
   cannot be authored exactly and differs in scale across dialects — MAY declare
   a `tolerance`, making the numeric comparison `abs(actual - expected) <=
   tolerance`. Booleans compare only to booleans (`true` is never `1`).
3. **Normalization determinism** — `normalize(then.statements[].sql[dialect]) ==
   then.statements[].sql[dialect]` via sqlglot, per the `m-sql` rules (alias scheme `t0,t1,…`,
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
the declared `then.roundTrips`, each non-empty child level executes keyed by the
distinct parent keys gathered from the previous level (an **unordered set** — the
`IN`-list bind order is *not* part of the contract, since it never changes which
children match, and child result order is fixed by the level's own `orderBy`; the
harness therefore compares each level's binds order-insensitively, consistent with
the order-insensitive row comparison of layer 2, and an implementation MUST NOT
sort these keys at runtime to match the fixture), empty parent-key levels execute
no child SQL, and the in-memory-assembled object graph equals the case's
`then.graph`. This is what proves N+1 elimination automatically (a 1 → N → N
deep fetch with non-empty levels must run in exactly 3 statements, not 1 + N +
N; a deep fetch whose root is empty runs only the root statement). For these
cases `then.statements` is an **ordered list** of statement entries (root plus
the child levels that execute) rather than a single entry, and `then.graph`
replaces (or accompanies) `then.rows`.

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

### Write-sequence cases

A **writeSequence** case proves a write contract by *application*, not
introspection. The harness provisions a table, **applies the ordered DML golden
SQL in order** (each `then.statements` entry with its own `binds`), then asserts
the resulting rows equal `then.tableState`. This covers milestone-chaining
temporal writes (`insert` / `update` / `terminate` and the bitemporal `*Until`
trio), batched non-temporal writes, ordinary `delete`, and the minimal
`cascadeDelete` witness over dependent relationships. The DML statement count MUST
equal the sum of the `when.writeSequence` steps' declared statement counts and the
case's `then.roundTrips`. The model descriptor's serde round-trip (layer 4b) still
runs; there is no `when.operation` to serde (layer 4a) and no normalization
difference — the DML golden SQL is normalized to a fixed point exactly like read
SQL (layer 3).

A **value-object** column's neutral write input (①) value is **always** the literal
document (a JSON object, a JSON array, or `NULL`) — never a DB-computed write marker
(`{computed: "maxPlusOne"}` / `{increment: n}`), which is a **scalar-attribute-only**
form. A value object binds its whole document even when that document is *shaped*
like a marker; the two are disambiguated by the field's declared metamodel role
(resolved from `columnOrder(entity)`), not by the value's shape (`m-value-object`).

A writeSequence case MAY set **`given.fixtures: true`** to load the model's
fixtures **before** the ordered DML (instead of starting empty) — so a sequence
can mutate a *pre-existing* persisted row. This is the `m-detach` detached-update
or detached-delete merge-back case, and the minimal dependent cascade-delete
witness: the original rows exist, the ordered DML mutates them, and the asserted
table state shows which rows changed or were removed.

### Conflict cases (`m-opt-lock`)

A **conflict** case proves optimistic-lock conflict detection by the **affected-
row count** a golden `UPDATE` leaves behind. The harness loads the model's
fixtures (the versioned row exists), applies an OPTIONAL out-of-band
**`given.apply`** (naive statement entries simulating a concurrent transaction
that bumped the version), runs the golden `UPDATE` (which gates on the version
the caller read earlier, its neutral write input in `when.write`), and asserts the
affected-row count equals **`then.affectedRows`** — `0` for a stale version
(conflict; the `updatedRows != 1` signal) and `1` for a fresh version (success).
When `then.tableState` is authored it is asserted too, confirming a conflicting
write did not apply. As with writeSequence cases, only the descriptor serde
round-trip and the golden-SQL normalization layers apply (there is no
`when.operation`).

A conflict case MAY instead carry a **`when.attempts`** retry sequence — an ordered
list of golden `UPDATE`s, each with its own `statements` + `affectedRows` + `write`
— proving the **`m-opt-lock` retry contract** end-to-end. After `given.apply`, the
harness applies each attempt in order and asserts its affected-row count: the first
(stale-version) attempt affects `0` rows (the conflict signal), then a retry that
re-reads the now-fresh version and re-applies affects `1`. The final
`then.tableState` confirms the retried write — not the concurrent writer's —
landed. (Golden SQL lives per attempt, so there is no top-level `then.statements`.)

### Scenario cases (`m-unit-work`)

A **scenario** case proves the unit-of-work / identity / query-cache contract as
an ordered list of steps over one provisioned database. A **read step** issues a
`find` (naming its `targetEntity`, as a read case does) with a declared round-trip
count (a cache hit declares `0` and lists no golden SQL); a **write step**
(`write`) **commits** golden DML between finds. The
write step is what makes **read-your-own-writes** and **query-cache
invalidation** expressible: a dependent find after a committed write must observe
it (and cannot be modeled as a cache hit, since reusing the stale pre-write rows
would fail the post-write `expectRows`). A write step defaults to **committing**
its DML; with **`rollback: true`** the harness applies the DML then **rolls it
back** (through the provider's manual-commit session seam) — the observable form
of the `m-unit-work` **abort contract**: a later find MUST re-resolve and observe
the ORIGINAL rows, never the aborted write. A write step with **`roundTrips: 0`** and
no golden SQL is a **no-op** write — a versioned `UPDATE` whose `set` changes no
attribute issues no DML (`m-opt-lock`) — and executes nothing, exactly like a
cache-hit read step. The rolled-back DML still executes, so it counts its
statements as round trips exactly as a committed write does. The harness asserts
per-step round-trip / golden-SQL count consistency, executes each step, and checks
`sameObjectAs` identity assertions; it never compiles an operation to SQL.

A case MAY carry a **`when.uow`** block (`{ concurrency: locking |
optimistic }`) declaring the unit-of-work strategy its golden SQL runs under
(`m-unit-work` strategy selection). The block is **descriptive**: the harness
executes the authored golden SQL either way — the block records which mode produced
it, so an optimistic conflict case's gated `UPDATE` and a locking-mode case's
ungated version-advancing `UPDATE` are self-describing. Its default is `locking`.

### Coherence cases (`m-coherence`)

A **coherence** case proves the cross-process cache-coherence contract (one node
observes another's committed write) by running a two-node operation sequence over
**two connections to one database**. The harness provisions one database (node A
= the provider's own connection, with the model's fixtures loaded so the seed read
sees a row), opens a second independent connection via the provider's **two-node
seam** (`open_peer`, below), and runs each `coherence` step on its declared node:
a `write` step **commits** DML on its node; a `read` step queries (naming its
`targetEntity`, as a read case does). The final
node-B re-fetch carries **`observeRows`** — node A's committed **post-write**
state, which node B **MUST** observe (never the stale pre-write rows). Each step's
golden SQL is normalized (layer 3), and the read steps' operations and the
descriptor survive serde (layer 4). The harness contains no cache and no
notification bus; it proves the suite's post-write golden SQL is correct against
real, committed, cross-connection data — the observable contract any conforming
invalidation mechanism (full-cache re-fetch or partial-cache mark-dirty) must
satisfy. See [`m-coherence.md`](m-coherence.md).

A read step MAY additionally declare `sameObjectAs` (with an optional
`identityAttr`): the harness asserts its observed rows carry the same primary-key
identity as an earlier same-node read, exercising `m-coherence`'s
identity-preservation contract (the refresh updates the interned object in place
rather than forking a new one for the same primary key).

### Error cases (`m-db-error`)

- **error** (`m-db-error` error-code classification) — triggers a *real* database
  error and asserts the neutral category it classifies to (`then.errorClass`) plus
  the per-dialect native code (`then.nativeCode`). `uniqueViolation` cases trigger
  single-connection: ordered golden DML (top-level `then.statements`) whose final
  statement raises (a duplicate insert / a colliding update). `deadlock` and
  `lockWaitTimeout` cases trigger two-connection: a `when.concurrency` choreography
  of barrier-separated rounds, each naming the statements nodes A and B run that
  round. The harness runs each node on
  its own **non-autocommit session** (the provider seam's `open_session`, with the
  dialect's lock-contention tuning — Postgres `deadlock_timeout`/`lock_timeout`,
  MariaDB `innodb_lock_wait_timeout` — applied so a blocked lock fails fast), drives
  them on threads synchronized by a barrier, and classifies the error raised in the
  contention round via the provider's `classify_error`. The classifier is a thin
  per-dialect extraction (Postgres SQLSTATE, MariaDB errno) over the shared,
  DB-free category map + call-site predicates; the runner asserts the predicate
  partition, so the harness exercises the interface the language implementations
  build, not a harness-only shortcut.

### Boundary cases (`m-auto-retry`)

A **boundary** case proves the unit-of-work **bounded automatic retry** contract
(`m-auto-retry`, `m-opt-lock` *Retry contract*): a loop-mechanics branch
whose observable — a retriable failure auto-retried away, a conflict surfaced
without the opt-in, a disabled loop (`retries: 0`), an exhausted bound, a callback
value withheld on abort — a **single-connection** harness cannot provoke, because
it needs an **injected transient failure** and a re-executed closure. It carries a
portable `when.boundary` (the ordered unit-of-work actions), an OPTIONAL
`given.fault` (a portable fault kind — `serialization-failure` / `deadlock` /
`lock-wait-timeout` / `optimistic-lock-conflict`, aligned with the `m-db-error`
`errorClass` vocabulary), a `then.outcome` (the portable outcome — `committed`, or
a surfaced error kind), and its retry configuration under `when.uow` (`retries` /
`retryOptimisticConflicts`). It carries **no** golden SQL — the concrete DML and
error types stay per-language. Every boundary case is on the `api-conformance`
lane.

### Rejected cases (`m-value-object` / `m-op-algebra`)

A **rejected** case proves a **negative**: that a model-aware validator refuses an
invalid input **before any SQL is emitted** (resolved question 7). It carries the
invalid input under `when` — **exactly one** of an `operation` (a schema-valid
`m-op-algebra` node) **or** a `write` (a neutral write row, ①) — and a
`then.rejectedRule` naming the violated normative rule. A rejected case pins a
**single** invalid input: carrying **both** `operation` and `write`, or **neither**,
is invalid — enforced by the schema `oneOf` (paired with the `propertyNames` enum
that forbids other keys) and mirrored by a harness XOR guard, so the "exactly one
invalid input" rule holds even for a caller that reaches the runner without schema
validation. It carries **no** golden SQL (`then.statements` is disallowed): the
assertion is that the input never *reaches* SQL. The harness (and every language
implementation) resolves the input against the queried entity's **declared**
value-object structure and asserts the refusal happens pre-SQL with **exactly** the
named rule; a run that accepts the input, or rejects it with a different rule,
**fails**. Rejection is **dialect-agnostic** — no dialect,
provisioning, or execution — so a rejected case is checked once, with no database.
This is the portable analogue of Reladomo refusing a structurally-invalid
embedded-value use (an embedded value is not a relationship target and cannot be
reverse-navigated); Parallax pins the same "these operations are structurally
invalid" semantics as a language-neutral pre-SQL rejection.

`then.rejectedRule` is a **closed vocabulary**, each identifier naming a normative
MUST — the `m-op-algebra` nested-predicate resolver rules and the `m-value-object`
materialization/navigation and write-validation contracts. **Operation** rules:

- `nested-path-first-segment-not-value-object` — a nested path's first segment names
  no value object declared on the queried entity (`m-op-algebra`).
- `nested-path-unknown-member` — an intermediate segment names no declared nested
  value object, or the leaf names no declared attribute (`m-op-algebra`).
- `nested-literal-type-mismatch` — a nested comparison / membership literal's type
  differs from the leaf attribute's declared neutral type (`m-op-algebra` typed
  literals).
- `deep-fetch-value-object-segment` — a `deepFetch` path segment names a value
  object (`m-value-object` contract 4, `m-deep-fetch`).
- `navigate-value-object-target` — a `navigate` / `exists` / `notExists` targets a
  value object (`m-value-object` contract 4, `m-navigate`).
- `find-root-value-object` — a `find()` is rooted at a value object
  (`m-value-object` contract 5).

**Write** rules (`m-value-object` write validation — a value object is written
atomically as one whole document):

- `write-required-attribute-missing` — a required (`nullable: false`) attribute is
  absent (or null) at any depth.
- `write-required-value-object-missing` — a required nested value object is absent
  (or null), or a required `many` array is absent (an **empty** array is fine —
  emptiness is not a nullability violation).
- `write-value-type-mismatch` — a document field value's type differs from the
  attribute's declared neutral type.

Purely **regex-level** negatives — an empty path after the value-object name, a
bad-cased segment — are the operation schema's job (the `nestedRef` grammar) and
stay **schema-validation unit tests**, never `rejected` cases: a syntactically
malformed operation is refused at layer 1 (schema conformance) before a model-aware
resolver ever runs.

## Case-header house style

Every case opens with a **header comment** — the only comments a case carries.
Comments are **header-only**: no comment sits mid-document, because the grouped
`given` / `when` / `then` structure now shows what old comments used to narrate.
The header follows a fixed house style:

- **First line** states, in one sentence, **what the case proves** — the contract
  or behavior, not the mechanics. (`sum + groupBy + having — the canonical
  aggregate case (m-agg sub-area).`)
- **A short paragraph** gives the **why / mechanism** and the key numbers a reader
  needs to trust the assertions (the group totals, the version that goes stale, the
  distinct parent keys a deep-fetch level gathers).
- It uses the **new field names only** (`given.apply`, `then.affectedRows`,
  `then.statements`) — no legacy vocabulary, no "formerly known as" prose.
- It does **not narrate mechanics the structure now shows** — no describing
  positional binds, key-presence shape sniffing, or field pairings that no longer
  exist.
- It stays **roughly a dozen lines at most**; a case that needs more explanation
  than that is usually two cases.

```yaml
# Optimistic-lock conflict (m-opt-lock): a stale-version UPDATE affects ZERO rows.
#
# Account id 2 (Linus) is read at version 1. Before our UPDATE flushes, a
# concurrent transaction commits a change to the same row, bumping its version to
# 2 — modeled here by the out-of-band `given.apply` (a naive UPDATE the harness
# applies verbatim after loading the fixtures, simulating the other writer). Our
# golden UPDATE gates on the version we read EARLIER (1), so its `... and version =
# ?` predicate matches NO row: it affects ZERO rows — the `updatedRows != 1`
# conflict signal. The harness asserts `then.affectedRows` is 0, and the resulting
# `then.tableState` confirms our stale write never applied.
```

## Case lanes

Every case declares a **lane** (`lane`, default `harness`) naming which executor
satisfies it:

- **`harness`** — the harness executes the case as today: it runs the golden
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
  `open_peer` capability yields a second, independent connection to the
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
implementation proves conformance through the adjacent adapter contract in
[`m-conformance-adapter.md`](m-conformance-adapter.md).

That adapter is the external seam between a corpus runner and a language
implementation. It exposes a small command surface (`describe`, `compile`,
`run`, and `benchmark`) and emits JSON documents validated by
[`../schemas/conformance-adapter.schema.json`](../schemas/conformance-adapter.schema.json).
It MUST accept compatibility corpus files as input and MUST report SQL
emissions or runtime observations without exposing implementation internals.
