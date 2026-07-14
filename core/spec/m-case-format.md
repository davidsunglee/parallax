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
  `referenceSql`, the observed data (`rows` / `graph` / the per-milestone `graphs` /
  `tableState`), the counts and codes (`affectedRows` / `errorClass` / `nativeCode` /
  `roundTrips`), the reference-identity `identityChecks`, the portable boundary
  `outcome`, and the numeric-comparison `tolerance`.

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
- **`scenario`** — a `when.scenario` of ordered read, committed-write, *and*
  lifecycle-**action** steps, golden SQL per step (`m-unit-work` and the
  object-lifecycle modules — see *Lifecycle action steps*).
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
- **`rejected`** — a schema-valid `when.operation`, a `when.write`, **or** an
  inline `when.model` a model-aware validator MUST refuse **before any SQL**,
  naming the violated normative rule in `then.rejectedRule` (`m-value-object` /
  `m-op-algebra` / `m-inheritance` negative validation, carrying no golden SQL —
  see *Rejected cases*, below).

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
        postgres: select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0 where t0.id in (?, ?, ?)
        mariadb: select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0 where t0.id in (?, ?, ?)   # optional
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
        postgres: select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on from order_item t0
    - sql:
        postgres: select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0 where t0.id in (?, ?, ?)
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
| `when.scenario` | `when` | scenario | an ordered list of read / committed-write / lifecycle-**action** steps (`action` + `on`, plus `set` / `path` and the per-step lifecycle observables `expectState` / `expectError` / `differentObjectFrom`), each carrying its own per-step golden `statements` |
| `when.coherence` | `when` | coherence | a two-node (A / B) operation sequence, each step carrying its node, kind, and per-step golden `statements` |
| `when.concurrency` | `when` | error / concurrencySuccess | a two-connection, barrier-separated `rounds` choreography; each node step carries per-step golden `statements` |
| `when.boundary` | `when` | boundary | an ordered list of portable unit-of-work actions (`read` / `create` / `update` / `terminate` / `delete`) |
| `when.attempts` | `when` | conflict | an ordered retry sequence of optimistic-lock `UPDATE` attempts, each carrying its own `statements` + `affectedRows` + `write` |
| `when.write` | `when` | conflict / rejected | the single-attempt neutral write input (①): the flat attribute-named row the versioned `UPDATE` (or temporal close) operates on; on a `rejected` case, a value-object write the validator MUST refuse pre-SQL |
| `when.model` | `when` | rejected | an inline model descriptor (`m-inheritance`) whose *family* is invalid — the cross-entity closed-tree invariant a model-aware validator MUST reject pre-SQL; kept inline so the shared `models/` registry stays loadable (see *Rejected cases*) |
| `when.uow` | `when` | no | unit-of-work configuration (`concurrency: locking \| optimistic`, `retries`, `retryOptimisticConflicts`) the action runs under; descriptive |
| `when.at` / `when.observedInZ` | `when` | conflict | a temporal-close conflict's close instant (→ new `out_z`) and observed processing-from (`in_z`) the optimistic gate binds |
| `when.equivalentEncodings` | `when` | no | alternate surface encodings of `when.operation`; each MUST canonicalize to it |
| `then.statements` | `then` | yes* | the golden SQL an impl must emit — an ordered list of `{sql, binds}` statement entries (dialect-keyed map form), one per deep-fetch level or write-sequence DML step. *Absent for scenario / attempts cases, whose golden SQL lives per step; disallowed on a boundary case |
| `then.referenceSql` | `then` | conditional | an independent naive oracle (see below) — a plain string, OR a dialect-keyed map where the naive spelling is dialect-specific; for a deep fetch it is the naive single-statement oracle for the **root** row set |
| `then.rows` | `then` | read | the rows the query must return (single-statement / flat-result cases) |
| `then.graph` | `then` | read | the assembled object graph a deep fetch must produce (one of `then.rows` / `then.graph` / `then.graphs` is REQUIRED for a read case) |
| `then.graphs` | `then` | read | an ORDERED array of per-milestone edge-pinned graphs a `history` / `asOfRange` snapshot read materializes (see *Milestone-set graphs*, below) — each entry `{pin, graph}`; coexists with `then.graph` exactly as `then.rows` does |
| `then.identityChecks` | `then` | read | declared reference-identity expectations over graph node positions — each `{left, right, same}` with JSON-Pointer `left` / `right` and a boolean `same` — the same-node claim a back-reference cycle's PK-only stub cannot carry by value (see *Back-reference cycles*, below) |
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
entity participates in an inheritance family (`m-inheritance`), that position may
be abstract: an abstract **root** targets the whole family (its **effective
concrete set**), an abstract **subtype** targets its concrete descendants, and a
concrete subtype targets itself. A non-inheritance entity's effective concrete set
is the entity itself.

`targetEntity` is a first-class, machine-checkable field, not documentation: a
model-aware harness cross-checks it against every queried-entity `Class.attribute`
/ `Class.relationship` reference in the operation (the class part of each top-level
predicate, order-by key, nested-value-object path, navigation relationship, and
deep-fetch root hop MUST be **consistent** with `targetEntity`; a navigation's
inner operation resolves against the *related* entity and is not cross-checked). The
cross-check is **family-aware**: a reference class `C` is consistent with the
target `T` when `C`'s effective concrete set is a **subset** of `T`'s — a subtype
of an abstract target is consistent, a sibling or a broader position is not. For a
non-inheritance entity the effective set is the entity itself, so "subset" reduces
to the pre-inheritance "equal".

An abstract-target read (an abstract `targetEntity`, or an abstract position
`narrow`ed with `m-op-algebra`'s `narrow` node) materializes complete concrete
instances. Its `then.rows` / `then.graph` leaves carry a **`familyVariant`** key —
the **concrete subtype name** of each row (`Dog`, `Cat`, …). `familyVariant` is
**not projected as SQL**: under `table-per-hierarchy` the golden SQL projects the
**raw tag column** (`m-sql`, resolved Q6) and the harness materializes
`familyVariant` from the tag metadata map (`tagValue` -> subtype name) — an
independent, metadata-derived recomputation like the as-of and PK-allocation
oracles. The row also carries the full **concrete-superset** columns (inherited
first, then each concrete subtype's own columns), with non-applicable subtype
columns `null`. A **concrete-target** read carries no `familyVariant` (the caller
already knows the variant) and projects only that concrete instance's columns. A
`narrow` node inside `when.operation` is validated pre-SQL against the family's
effective concrete-subtype set (`m-op-algebra`); an invalid narrow is a `rejected`
case (see the narrow rules in *Rejected cases*).

A **deep-fetch `then.graph`** keys each eager-fetched related set under the
**relationship name** — or, for a **narrowed polymorphic hop** (`m-deep-fetch`,
`m-inheritance`), under the **derived narrowed view key** `<rel>[<Concrete>,
<Concrete>]` (the local relationship name, the effective concrete-subtype set in
canonical alphabetical order by entity name, no spaces). Equivalent authored
narrowings (`to: [Pet]` vs `[Cat, Dog]`) key the same view; a broad and a narrowed hop over one relationship
key **different** views. A polymorphic narrowed view's child objects carry
`familyVariant` just as a flat abstract read's rows do (a single-concrete narrowed
view carries none). A `narrow` escaping the relationship target's effective set is a
`rejected` case (`narrow-outside-relationship-target`).

#### Read result form (row-form vs instance-form)

**Every** read a case asserts carries a **result form** — the **object lane**
(**instance-form**) or the **values lane** (**row-form**) of `m-sql`'s *Read result form*
— and that form fixes the read's projection (`m-sql`, *Read projection*, slot 4:
instance-form projects every declared value-object document column; row-form omits them).
The form follows the read's **nature**, and a case expresses that nature in one of two
ways, keyed on **where** the read is asserted — never on a bare member name alone:

- **A top-level read case** expresses the form through **which result member it asserts**
  (the member names the nature):
  - **`then.rows`** — the **row-form** / **values lane**: a flat value observation of the
    scalar columns only. It omits every value-object document column.
  - **`then.graph`** / **`then.graphs`** — the **instance-form** / **object lane**: the
    result materializes into instances (a snapshot graph, per-milestone graphs, or a
    deep-fetch tree), so the projection additionally carries every declared value-object
    document column (`m-value-object`).
- **A scenario / coherence / concurrency step** asserts its read with a step-level
  **`expectRows`** / **`observeRows`** — a uniform observation channel that does *not*
  name the form — so the form follows the **step's read semantics** (`m-sql`: "any find
  whose rows become objects"). **Every** SQL-producing read step is classified below, so
  no read-bearing step location is left without a form:
  - A **managed-object find or refresh step** — a developer-facing find whose rows become
    managed instances: an identity-map coordinate / refresh read, a coherence re-fetch, a
    scenario observation find, or a **concurrency full-scalar shared read** that observes
    the object (`m-read-lock`) — is **instance-form** (object lane), exactly like a
    `then.graph` read.
  - A relationship **`action: load` step** and the **first `action: access` step** of a
    relationship or operation-backed list (`m-op-list`) — the SQL-producing read that
    first **materializes** the loaded / accessed related objects (a deferred deep fetch,
    or an operation-list first resolution) — is likewise **instance-form** (object lane):
    it projects the read entity's own instance-form list (its scalars plus any
    value-object document column it declares), exactly as a deep-fetch / snapshot **child
    level** does (`m-sql`, *Read result form*). A **subsequent** `action: access` of an
    already-materialized relationship or list issues **no read** (a cache hit,
    `roundTrips: 0`) — there is no projection to classify.
  - A value-object-bearing target therefore projects its whole document (slot 4) at
    **every** instance-form step above, even though the channel is `expectRows` /
    `observeRows`.
  - The **internal materialized-predicate-write resolving read** — the "materializing
    find" a set-based versioned / temporal predicate write consumes to plan its per-row
    DML, resolving each matched row to its pk and gate values with **no instance
    constructed** (`m-sql`, ADR 0014) — is the **sole row-form** (values lane) step read;
    it omits slot 4 (a reassigned value-object document comes from the write instruction,
    not the read). A **`distinct` / grouped concurrency-witness read** is likewise a
    projection over the values lane (`m-sql`), constructing no instance.

Row-form is **not a developer surface** — the idiomatic find API is instance-form
(results always materialize). Row-form is the internal / conformance consumption lane
(predicate `read` cases, the materialized predicate-write read, and future aggregation
results — `m-agg`; a `distinct` / grouped concurrency-witness read is likewise a
projection over the values lane, `m-sql`). The form is **structural intent** an adapter's
`compile` MAY consume, exactly like `when.uow.concurrency`; it needs no schema field and
no case edit. The supplier result-form witness is the **sole** place the two result
FORMS **diverge** — a scenario whose managed find projects the `address` document
(instance-form) while its predicate-write resolving read omits it (row-form). It is **no
longer the sole value-object-bearing step read**, now that the lifecycle-action
`load` / first-`access` witnesses carry value-object-bearing instance-form step reads
(each projecting its read entity's own `address` document at slot 4). Every other entity
read at a step (`balance`, `position`, `account`, `order_item`, and the rest) declares no
value object, so instance-form and row-form project the same columns there: the
classification changes no existing golden and pins the answer for the value-object-bearing
step reads.

#### Milestone-set graphs (`then.graphs`)

A single-instant read materializes **one** snapshot graph, asserted by
`then.graph`. A **milestone-set** read — `history` (the full milestone set) or
`asOfRange` (every milestone overlapping the window) — materializes **one graph
per milestone**, asserted by **`then.graphs`**: an ordered array of `{pin, graph}`
entries. `then.graphs` coexists with `then.graph` exactly as `then.rows` does — a
single-instant read carries `graph`, a milestone-set read carries `graphs` — and a
read case satisfies its `then` requirement with any one of `rows` / `graph` /
`graphs`.

Each entry's **`pin`** is the milestone's OWN edge coordinate — its from-instant
per as-of axis, keyed by the as-of attribute name (`processingDate` /
`businessDate`) — and its **`graph`** is the plain-value graph materialized at that
pin, the same root-class-keyed shape as `then.graph`. The pins are **edge pins,
not a shared root pin**: `history` returns each milestone edge-pinned to its own
from-instant, and `asOfRange` returns every overlapping milestone independently
edge-pinned to its own from-instant (never to the window bounds) — the
`m-temporal-read` edge-point read, now observed as a graph per milestone. The
single root query returns the whole milestone set in one round trip; the harness
partitions those rows by edge pin (matching each pin's per-axis from-instant to the
row's from-column) and asserts each partition equals its declared graph. The pins
are **pairwise disjoint** — every milestone belongs to **exactly one** declared
graph, so an overlapping or duplicated pin (two graphs claiming the same milestone)
is a loud failure, as is a milestone matched by no pin. (A v1
milestone-set graph carries **no** deep-fetch includes — history-with-includes
(`snapshot-history-includes`) is staged and claimed by neither object-lifecycle
slice — so each graph is rooted at the read's `targetEntity`.)

#### Back-reference cycles and `then.identityChecks`

A snapshot graph is a plain-value tree, but an included **back-reference** can
reach a node already on the current path — `[items, items.order]` navigates
`Order → items → order`, and `items[0].order` is the ROOT `Order`. This is a legal
in-memory cycle (`m-snapshot-read`). To keep the graph JSON a finite value tree,
recursion stops at a **true cycle** (a relationship reaching an **ancestor node on
the current path**) and the cycle point carries a **PK-only stub** — ONLY the
referenced node's primary-key attribute(s), no other scalars, no relationships:

```yaml
then:
  graph:
    Order:
      - id: 1
        name: Ada
        items:
          - { id: 11, order_id: 1, sku: A-100, order: { id: 1 } }   # PK-only stub — recursion stops
```

The stub is scoped to **true cycles only**. A **diamond-shared** node at a
NON-cyclic position (two include paths reaching the same row that is not an
ancestor, as in `m-snapshot-read-001`) keeps its full-value representation — it is
not re-goldened to a stub.

The PK-only stub proves nothing about sameness by itself (a lookalike copy carrying
the same primary key would serialize identically). The cycle's real claim —
`items[0].order` is the **same node** as the root, not a copy — rides
**`then.identityChecks`**, an array of `{left, right, same}` entries mirroring the
`m-conformance-adapter` `identityCheck`: `left` and `right` are JSON Pointers into
the case naming the two node positions, and `same` is the asserted reference
verdict:

```yaml
then:
  identityChecks:
    - { left: /then/graph/Order/0, right: /then/graph/Order/0/items/0/order, same: true }
```

Reference identity is not wire-observable, so `then.identityChecks` is an
**adapter-delegated** observable: the harness validates it is well-formed and
skips grading it, and each language's API Conformance Suite returns and verifies it
against the `m-conformance-adapter` `identityChecks` observation — exactly as it
grades a scenario step's `differentObjectFrom`.

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

#### Predicate-selected write instruction

A scenario write MAY retain the legacy string label, or use the canonical object
form below. This object is the language-neutral requested operation consumed by
`compile`, `run`, and API no-drift checks; golden SQL remains the independent
expected lowering, never the source from which an adapter deduces the write.

The canonical write-instruction vocabulary — this predicate-selected shape and the
keyed `writeSequence` shape — is **hosted in
[`write-instruction.schema.json`](../schemas/write-instruction.schema.json)**
(`m-unit-work`, the write-side analogue of `operation.schema.json`); this document
references that canonical shape rather than redefining it. The case format carries
the same shapes with `at` / `businessAt` / `until` kept as **authoring aliases** of
the axis-explicit canonical spellings (`businessFrom` / `businessTo`; the processing
instant is harness / Clock-supplied context, never an instruction field). The
corpus-wide re-authoring to the canonical spellings is deferred.

```yaml
- write:
    mutation: update                    # update | delete | terminate | updateUntil | terminateUntil
    target:
      entity: Account
      predicate:
        lessThan: { attr: Account.balance, value: 200.00 }
    assignments:
      - { attr: Account.balance, value: 100.00 }
  roundTrips: 1
```

The canonical case pointer for this input is **`/scenario/<n>/write`**. Its fields
are deliberately small and structural:

| Field | Required | Rule |
|---|---|---|
| `mutation` | yes | one of `update`, `delete`, `terminate`, `updateUntil`, `terminateUntil` |
| `target.entity` | yes | exact concrete descriptor entity where the operation starts |
| `target.predicate` | yes | one schema-valid `m-op-algebra` operation; it is a bare write predicate, never a result modifier |
| `assignments` | only `update` / `updateUntil` | ordered `{attr, value}` data; nonempty and unique; `attr` names an assignable qualified top-level attribute or value object. An attribute takes a neutral scalar/null literal; a value object takes its complete object/array document or null according to its declared cardinality/nullability. |
| `at` | processing-temporal target | transaction instant for temporal close/chain behavior |
| `businessFrom` | business-temporal target | lower bound for the plain or bounded temporal operation |
| `until` | `updateUntil` / `terminateUntil` | bounded operation's exclusive upper bound |

Delete and terminate mutations carry **no** assignments. Assignment list order is
not SQL order: descriptor declared column order determines the emitted `set`
columns and assignment binds. The model-aware validator validates the predicate
against `operation.schema.json`, checks entity scope and bare-predicate rules,
rejects duplicate or framework-owned/unassignable assignments, and requires only
the temporal coordinates the target profile uses. It rejects a predicate-selected
inheritance-family write before SQL, as `m-inheritance` requires.

Materializing cases make the observation explicit: a preceding scenario read
resolves the same target predicate and exposes the matched rows or observed
versions; the following write instruction independently states what the caller
requested. For every versioned or temporal target, model-aware validation MUST
require that prior find to use the same concrete `targetEntity` and canonical
operation. It is a real resolving read, not a cache hit: it declares exactly one
round trip and one authored golden read statement, plus `expectRows`. An empty
`expectRows` is valid only as that real zero-match resolution (`1 + 0`); a
zero-round-trip/no-SQL step cannot materialize a predicate write. An unversioned,
non-temporal `update` or `delete` is the sole readless exception. The read is not
inferred from its SQL and the write is not inferred from the read.

For every resolved materialized row, the projection is descriptor-derived rather
than inferred from golden SQL. It MUST include identity, an explicit observed
optimistic version when present, and every current temporal axis boundary. An
assignment-bearing update also includes the current scalar or whole value-object
document of every assigned field, so per-row equality/no-op elimination is
possible. A temporal mutation that chains a successor or preserves a business
head/tail includes every current non-milestone scalar payload column and every
top-level value-object document column that those rows carry forward. It does not
project output generated by the framework — for example a bumped version, fresh
processing instant/open bound, or inheritance discriminator. A non-trivial
scenario read MAY carry `referenceSql`, with the same string-or-dialect-map shape
as `then.referenceSql`; it is self-contained (rather than reusing golden binds)
and must agree with its golden rows as the third oracle.

##### Buffered write instructions (same-transaction coalescing)

A scenario write step MAY carry the **coalescing pair** in place of a single
instruction: `/scenario/<n>/write` is then an ordered list of **exactly two
keyed** instructions a single unit of work buffers before a **coalescing flush**
(`m-unit-work` same-transaction coalescing). **Entry 0** is a keyed `insert` of a
new object; **entry 1** is the keyed `update` or `delete` of **that same object** —
the same entity and the same primary-key identity. Each entry is a **keyed**
instruction (`mutation` + `entity` + `rows`, the case-format analogue of
`write-instruction.schema.json`'s `keyedWriteInstruction`), **referencing** the
canonical write-instruction `$defs` rather than redefining them and layering only
the `at` / `businessFrom` / `until` authoring surface. The step's golden SQL
(`statements`) is the **independent expected lowering of the coalesced flush**: one
final-value write for insert-then-update (`roundTrips: 1`), or **no** DML for
insert-then-delete (`roundTrips: 0`, no `statements`). The step therefore encodes
**both** requested mutations explicitly, so an adapter exercises the coalescing
rule from the instructions themselves, never from the golden SQL or a prose note.
Business bounds are the axis-explicit canonical `businessFrom` / `businessTo`; the
processing instant rides as the Clock-context `at`, never an instruction field.

The form is **scoped** to that pair — it is **not** a general N-instruction ordered
buffer, and a **predicate**-selected instruction is **not** admitted (both
generalities belong to the deferred string-label→structured write migration, kept
separate). The JSON Schema pins the structural shape (exactly two keyed entries,
entry 0 `insert`, entry 1 `update` / `delete`); the same-entity and
same-primary-key equalities it cannot express are enforced by the harness
validator.

```yaml
- write:                                    # an ordered buffer, coalesced at flush
    - mutation: insert
      entity: Balance
      rows: [{ id: 9, acctNum: D, value: 100.00 }]
      at: "2024-06-01T00:00:00+00:00"       # processing (Clock) instant, not an instruction field
    - mutation: update
      entity: Balance
      rows: [{ id: 9, value: 150.00 }]
      at: "2024-06-01T00:00:00+00:00"
  roundTrips: 1                             # coalesces to ONE final-value INSERT (value 150)
```

A case MAY carry a **`when.uow`** block (`{ concurrency: locking |
optimistic }`) declaring the unit-of-work strategy its golden SQL runs under
(`m-unit-work` strategy selection). The block is **descriptive**: the harness
executes the authored golden SQL either way — the block records which mode produced
it, so an optimistic conflict case's gated `UPDATE` and a locking-mode case's
ungated version-advancing `UPDATE` are self-describing. Its default is `locking`.

#### Lifecycle action steps

Beyond read and write steps, a scenario carries a third step kind — the **action
step** — that names a managed-object lifecycle verb the client performs against
an earlier step's result. This is the vocabulary the object-lifecycle modules
(`m-identity-map`, `m-detach`, `m-deep-fetch`, `m-op-list`) need but the
SQL-oriented read/write steps cannot express. An action step carries an
**`action`** verb, an **`on`** source (the earlier step's index, or an array of
indices when the verb spans sources at different lowered coordinates), its own
per-step golden `statements` and `roundTrips`, and the same per-step observables
as a read step. The **Targets** column below states whether the verb acts on a
prior step's result (so `on` is REQUIRED) or on the unit of work as a whole (so
`on` is inapplicable and MAY be omitted):

| Verb | Meaning | Targets | Module |
|---|---|---|---|
| `mutate` | assign the attributes in `set` in memory (no SQL for a snapshot / detached object) | prior object (`on` required) | `m-snapshot-read` / `m-detach` |
| `detachCopy` | take a detached deep copy of the target | prior object (`on` required) | `m-detach` |
| `load` | explicitly trigger a deferred relationship load (the portable, mandatory load trigger) | prior object(s) (`on` required) | `m-deep-fetch` |
| `access` | read an already-loaded relationship / operation-backed list (no SQL when already populated) | prior object (`on` required) | `m-op-list` |
| `flush` | emit the unit of work's buffered DML | unit of work (`on` optional) | `m-unit-work` |
| `mergeBack` | reconcile a detached copy with the store | prior object (`on` required) | `m-detach` |
| `commit` / `abort` | end the unit of work, committing or discarding it | unit of work (`on` optional) | `m-unit-work` / `m-detach` |

**`on` is REQUIRED for the object-targeting verbs** (`mutate`, `detachCopy`,
`load`, `access`, `mergeBack`) — each acts on the object(s) a prior step
resolved, so it MUST name that source, and the store enforces this per-verb in
the schema (an object-targeting action missing `on` is rejected). The
**boundary / unit-of-work verbs** (`flush`, `commit`, `abort`) operate on the
whole unit of work rather than one specific prior object, so `on` is
**inapplicable and MAY be omitted** (a `flush` MAY still carry `on` to document
the buffered write it materializes). Every `on` index — single or in the array
form — MUST name an **earlier** step, and the array form's indices MUST be
**unique** (a source is referenced at most once); a forward / self / out-of-range
or duplicated index is a loud harness failure.

`set` is legal **only** on a `mutate` action; `path` (the navigated relationship,
e.g. `items` or `items.statuses`) only on `load` / `access`. Because golden SQL
still lives per step, a scenario with action steps carries no top-level
`then.statements`, and the harness executes a load / access as a relationship
query, a flush / mergeBack / commit as committed DML, and counts each step's round
trips against its listed statements exactly as for read / write steps. A deferred
`load` over several source objects emits **one child statement per non-empty level**
(never one per object), and one statement **per lowered coordinate group** when the
sources are pinned at different as-of coordinates — the deep-fetch batching contract,
proven by the load step's golden SQL and binds.

#### Per-step lifecycle observables

Read and action steps carry lifecycle observables that grade what the wire golden
SQL cannot see. Two — `sameObjectAs` (reference sameness) and `expectRows` — are
graded by the harness. The rest are **adapter-delegated**: the harness validates
they are well-formed and skips grading them, exactly as it skips a whole
`api-conformance`-lane case; each language's API Conformance Suite returns and
verifies them (`m-conformance-adapter`, `m-api-conformance`):

- **`sameObjectAs`** / **`differentObjectFrom`** — a zero-based earlier-step index
  this step's result denotes the **same** object as, or a **distinct** object from.
  `differentObjectFrom` is the reference-inequality counterpart of `sameObjectAs`:
  it proves two results are different objects even when their **row values are
  identical** (two finite coordinates in one milestone, `m-identity-map`), which
  value equality alone cannot distinguish. A single step declares at most one of the
  two.
- **`expectState`** — the lifecycle state the target object is in after the step,
  from the `m-detach` five-state machine (`in-memory` / `persisted` / `deleted` /
  `detached` / `detached-deleted`).
- **`expectError`** — a neutral **application-lifecycle** error the step's verb
  raises. It is a closed vocabulary, defined normatively where each error is
  defined and **distinct from the `m-db-error` DB-error taxonomy** (which pairs
  `errorClass` with a `nativeCode` an application error has no analogue for):
  - `detached-relationship-load` — a deferred relationship load on a **detached**
    object, which has no live unit of work to resolve through (`m-detach`).
  - `processing-pin-read-only` — a mutation through a **finite processing-axis**
    pinned view, which records what the system knew and is never rewritten
    (`m-identity-map`).

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

### Rejected cases (`m-value-object` / `m-op-algebra` / `m-inheritance`)

A **rejected** case proves a **negative**: that a model-aware validator refuses an
invalid input **before any SQL is emitted** (resolved question 7). It carries the
invalid input under `when` — **exactly one** of an `operation` (a schema-valid
`m-op-algebra` node), a `write` (a neutral write row, ①), **or** a `model` (an
inline invalid inheritance descriptor, below) — and a `then.rejectedRule` naming
the violated normative rule. A rejected case pins a **single** invalid input:
carrying **more than one** of `operation` / `write` / `model`, or **none**, is
invalid — enforced by the schema `oneOf` (paired with the `propertyNames` enum
that forbids other keys) and mirrored by a harness guard, so the "exactly one
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
- `narrow-outside-position` — a `narrow` node's resolved effective concrete-subtype
  set is not a **subset** of the **active** polymorphic position: the position
  threaded into the node (the read's `targetEntity`, or the enclosing `narrow`'s
  resolved set) intersected with — **clamped to** — the position the node's `entity`
  names, so a nested `narrow`, or one whose `entity` is broader than the threaded
  position, cannot broaden back out (`m-op-algebra` × `m-inheritance`).
- `narrow-empty-effective-set` — a `narrow`'s authored `to` list resolves to the
  **empty** concrete-subtype set (`m-op-algebra` × `m-inheritance`).
- `subtype-attribute-outside-narrow-scope` — a predicate references a
  concrete-subtype-declared attribute at a polymorphic position that is not
  `narrow`ed to that subtype, so the attribute is not available to every concrete
  in the effective set (`m-op-algebra` × `m-inheritance`).
- `narrow-outside-relationship-target` — a `narrow` in a navigation filter's `op`,
  or a deep-fetch path segment's `narrow`, that **either** names an `entity` which is
  not the **relationship target** exactly (a relationship-scope narrow MUST set
  `entity` to the target and reach subtypes via `to`, never by naming a broader or
  other position), **or** resolves its `to` set to a concrete-subtype set that is
  **not a subset** of the relationship target's effective concrete set — narrowing a
  polymorphic relationship to a concrete outside its reachable set, even a **sibling**
  sharing the family root (`m-navigate` / `m-deep-fetch` × `m-inheritance`,
  resolved Q10).

**Write** rules (`m-value-object` write validation — a value object is written
atomically as one whole document):

- `write-required-attribute-missing` — a required (`nullable: false`) attribute is
  absent (or null) at any depth.
- `write-required-value-object-missing` — a required nested value object is absent
  (or null), or a required `many` array is absent (an **empty** array is fine —
  emptiness is not a nullability violation).
- `write-value-type-mismatch` — a document field value's type differs from the
  attribute's declared neutral type.

**Subtype-write** rules (`m-inheritance` concrete-subtype write protocol — a
schema-valid neutral write input a model-aware validator MUST refuse pre-SQL,
checked payload-shape-first then target-validity):

- `subtype-write-set-based-unsupported` — a **keyless** / predicate-driven write to
  an inheritance family (a payload carrying no primary-key attribute): a per-object
  concrete-subtype write is keyed (the tag guard rides with the identity predicates,
  `m-sql`), so a keyless write is an unsupported **set-based** inheritance write.
- `subtype-write-metadata-field` — a payload carries **framework-owned metadata**:
  the tag column, `tag`, `tagValue`, or `familyVariant`. A concrete-subtype write
  derives the tag from the subtype's `tagValue` and never accepts it (or the
  read-time `familyVariant`) as input.
- `subtype-write-sibling-attribute` — a payload carries an attribute declared on a
  **sibling** / unrelated concrete branch, so no single concrete subtype in the
  target's effective set accepts every field. The accepted fields are exactly the
  target's ancestry chain (root + abstract ancestors + own).
- `abstract-write-target` — a create / update / delete / terminate handle aimed at
  an **abstract** root or abstract subtype. Writes are concrete-subtype only.

**Model** rules (`m-inheritance` closed-tree family invariants — the cross-entity
invariants per-entity schema validation cannot express, carried inline under
`when.model`): `inheritance-unknown-parent`, `inheritance-cycle`,
`inheritance-missing-root`, `inheritance-multiple-roots`,
`inheritance-concrete-without-abstract-root`,
`inheritance-abstract-node-with-table`, `inheritance-abstract-node-fixture-rows`,
`inheritance-strategy-redeclared`, `inheritance-missing-tag-value`,
`inheritance-duplicate-tag-value`, `inheritance-inconsistent-hierarchy-table`, and
`inheritance-tag-on-concrete-subtype-strategy` (see `m-inheritance` for each
invariant). A `when.model` case carries an **inline** model descriptor — an
instance of `metamodel.schema.json` whose *family* is invalid — kept inside the
case rather than in the shared `models/` registry, so an invalid family cannot
break the sibling cases that load real models. The inline descriptor is
**round-tripped through descriptor serde** (layer 4) like any other model before
semantic validation asserts the rejection; the case's top-level `model:` still
names a real, loadable descriptor (its identity/registry role is unchanged). A
model-aware validator (and every language implementation) MUST reject the inline
family pre-SQL with **exactly** the named rule.

Purely **regex-level** negatives — an empty path after the value-object name, a
bad-cased segment — are the operation schema's job (the `nestedRef` grammar) and
stay **schema-validation unit tests**, never `rejected` cases: a syntactically
malformed operation is refused at layer 1 (schema conformance) before a model-aware
resolver ever runs. Likewise, purely **per-entity** inheritance negatives (a
rejected `strategy` enum value, the retired `discriminator` vocabulary, an abstract
role declaring a `table`) are refused at layer 1 and stay schema-validation unit
tests; `when.model` cases pin the **cross-entity** family invariants only.

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

## Compile eligibility

Beyond the `lane` routing above, a case declares whether an adapter's **`compile`**
command can derive its emissions statically. By default a case is
**compile-eligible**: `compile` emits its SQL without executing anything. A case is
declared **run-only** — via a top-level **`compileEligibility`** block
(`{ mode: run-only, reason, note? }`) — when its emissions cannot be a pure function
of `when` + `given`, so only `run` grades it. Two criteria make a case run-only:

- **`single-connection`** — the case intends to exercise database **concurrency or
  locking** behavior: a `conflict` / `concurrencySuccess` / `boundary` shape, a
  `when.concurrency` choreography, or a `given.apply` / `given.fault`. Such a case is
  run-only **regardless** of whether its emissions happen to be statically derivable,
  because its point is a runtime interaction a single `compile` cannot represent.
- **`query-result-dependent`** — the emissions depend on a **query result**:
  deep-fetch fan-out binds, materialized predicate writes, `sequence`-strategy PK
  allocations (whose following `INSERT` binds registry-read values — a `max`-strategy
  insert folds the computation into its own SQL and stays eligible), or
  framework-owned observed-version / `in_z` binds. `given` fixtures are legitimate
  inputs; `then` expectations are never fed back.

Eligibility is an **authored, reviewed** declaration — intent is a human judgment.
The harness **mechanically backstops** the detectable `single-connection` cases: a
case carrying a `given.apply` / `given.fault`, a `when.concurrency`, or a `conflict`
/ `concurrencySuccess` / `boundary` shape **MUST** carry the run-only declaration with
reason `single-connection`, and leaving it eligible (or mis-reasoning it) is a loud
failure. The `query-result-dependent` criterion is **not** mechanically detectable;
each language's **refusing compile port** enforces it structurally at runtime — a
`compile` that requests a row proves the case was mis-declared eligible
(`m-conformance-adapter`).

The adapter's answer for a claimed-but-run-only case under `compile` is a defined
`status: run-only` with a `compile-run-only` diagnostic, **not** `unsupported`
(which is invalid for a claimed case command); see `m-conformance-adapter`.

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
