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

### The corpus YAML schema

Every compatibility-corpus document — case, model descriptor, and fixture alike —
is read under the **YAML 1.2 core schema**. A plain scalar resolves to one of
exactly four implicit types — `null`, boolean, integer, float, in the core schema's
own spellings — and **every other plain scalar is a string**.

Naming the schema is load-bearing, because "a YAML document" alone selects none and
the readers do not agree by default. Under the YAML 1.1 types most host libraries
still resolve, `yes` / `no` / `on` / `off` are booleans, so the ISO country code
`NO` reads as `false`; `1_000` and the sexagesimal `1:30` are integers; and a bare
`2024-01-01` becomes a host *date object* rather than the ISO string
`m-document-codec` defines as that value's document spelling. Each is a different
document, so two implementations reading one corpus file through two host defaults
grade two different inputs — an `owner: on` at a `string` Attribute is a
`write-value-type-mismatch` for one reader and an accepted string for the other,
and neither is wrong about the file it was handed.

The corollary is that a corpus temporal, UUID, decimal, or `bytes` value is always
its **portable literal** (`m-document-codec`), read as text and decoded against the
declared type — never a value some loader happened to construct. Quoting such a
scalar remains optional and changes nothing; under this schema it is a string
either way.

A fixture document sits beside its model as `fixtures/<model-stem>.yaml` and maps
each row-owning Entity to its rows. Its top-level keys are **canonical Entity
spellings** (`m-metamodel`) — `parallax.compatibility.Grade`, not `Grade` — so a
fixture names its Entity by the same identity every other shipped document does,
and a model declaring one local name in two namespaces keys each twin's rows
without ambiguity. A loader **MAY** additionally accept an unambiguous bare local
name, matching the permissive input every reference position allows; shipped
fixtures do not rely on it.

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
  conflict's `write`); the **context** members (`uow`, `mutation`, `at`,
  `observedTxStart`, `observedValidStart`, `equivalentEncodings`) describe the
  unit-of-work mode, the written verb, transaction instant, observed milestone
  coordinate, and alternate surface encodings.
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
  resulting `then.tableState` (the temporal writes `m-txtime-write` /
  `m-bitemp-write`, the set-based `m-batch-write`,
  `m-cascade-delete`, and `m-detach` merge-backs).
- **`scenario`** — a `when.scenario` of ordered read, committed-write, *and*
  lifecycle-**action** steps, golden SQL per step (`m-unit-work` and the
  object-lifecycle modules — see *Lifecycle action steps*).
- **`conflict`** — an observation-requiring keyed write (`when.mutation`:
  `update`, the default, or `delete`; a temporal target's milestone close)
  asserted by `then.affectedRows` for a single attempt, or an ordered
  `when.attempts` retry sequence (`m-opt-lock`).
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
  `m-op-algebra` / `m-inheritance` / `m-storage-layout` / `m-unit-work` negative
  validation, carrying no golden SQL —
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

**A document-valued cell compares structurally, in every dialect.** Where a cell
holds a structured document — a Value Object column, or a Relational Document
Layout Structured Column — the comparison is by members and values, independent
of key order and insignificant whitespace (`m-document-codec`). The rule covers
both `then.tableState`, which asserts the document a write produced, and
`given.fixtures`, which supplies the document a read starts from.

This is normative here rather than left to each provider because the two engines
genuinely disagree: Postgres `jsonb` normalizes on storage and `=` is already
structural, while MariaDB `json` is a text alias whose `=` is key-order and
whitespace sensitive, so structural comparison needs `json_equals`
(`m-dialect`). Under Relational Document Layout most of an asserted row is one
document cell, so a case author must be able to write it in the order that reads
best and get the same verdict on both dialects.

**A document-valued bind is authored as the document, never as its rendered text.**
Wherever a `?` carries a **composite** structured document — an object or an array:
the atomic value-object write bind, a Relational Document Layout `INSERT`'s complete
document, a complete `many`-occurrence array replacement, and the MariaDB `json_contains`
candidate an element predicate binds (`m-sql`) — the `binds` entry is the document
itself, in the same style as a document cell, and the provider adapts it at bind time
(Postgres wraps it as `jsonb`, MariaDB serializes it to `json` text). A text spelling
would put a key order and a separator convention into the golden that no contract
fixes, and would compare two documents `m-document-codec` says are one value as two
different binds.

**A document-valued bind that is a JSON scalar is authored as its JSON text.** A
leaf assignment inside the document mutation expression (`m-dialect`) binds a JSON
string, number, boolean, or null, and no structural authoring form distinguishes one
from an ordinary scalar bind, so the two coexist under the same `?`: the dialect's
value expression — `cast(? as jsonb)` on Postgres, `json_extract(?, '$')` on MariaDB
— parses either form, and a scalar rides as the JSON text (`"Solveig"`, `42`,
`true`, `null`) that both parse. This costs the rule above nothing, because what it
protects is a composite's key order and separator convention and a JSON scalar has
neither. It is the same boundary the array guard's `cast(? as jsonb)` already draws:
that `?` takes the two characters `[]` because it is a text argument the dialect
spells (`m-dialect`), not a document the codec built.

The complementary rule is on the construction side, not here: binds are built in
canonical logical placement order so a golden document is deterministic to
author (`m-storage-layout`). Deterministic construction and order-insensitive
comparison are complementary — the first makes a golden bind stable, the second
keeps the assertion honest across engines.

#### Field table

| Field | Group | Required | Meaning |
|---|---|---|---|
| `model` | top-level | yes | path (relative to `core/compatibility/`) to the model descriptor |
| `tags` | top-level | yes | module/feature tags (e.g. `["m-op-algebra", "eq"]`); drive coverage + test selection |
| `lane` | top-level | no | which executor satisfies the case (default `harness`): `harness` — the harness runs it as today; `api-conformance` — schema-validated by the harness but satisfied by each language's API Conformance Suite (see *Case lanes*, below) |
| `shape` | top-level | yes | the explicit shape discriminator — one of the nine shapes above; the schema `oneOf` keys on this `const` |
| `given.fixtures` | `given` | no | load the model's fixtures BEFORE the action (default `false`), so a sequence can mutate pre-existing persisted rows |
| `given.apply` | `given` | no | an ordered list of out-of-band **naive statement entries** (`sql` a plain string) the harness applies verbatim after the case's own provisioning and before its lane's first golden statement or step; admitted on `conflict`, `writeSequence`, and `scenario` cases. What the entries stand for is the lane's: a concurrent transaction's stale-version mutation or row removal on a conflict case, and otherwise state no authored member of the model could produce |
| `given.fault` | `given` | boundary | an injected portable fault kind (`serialization-failure` / `deadlock` / `lock-wait-timeout` / `optimistic-lock-conflict`) driving the retry loop |
| `when.operation` | `when` | read | a canonical `m-op-algebra` node, validated against the operation schema (read cases) |
| `when.targetEntity` | `when` | read | the entity the read TARGETS — the queried position `when.operation` starts from (see *Read targeting*, below); REQUIRED on every read case and every scenario / coherence read step |
| `when.writeSequence` | `when` | writeSequence | an ordered list of mutations a write case realizes: `insert` / `update` / `terminate` (Transaction-Time-Only and Bitemporal; the plain Bitemporal writes are unbounded Valid-Time rectangle splits), `delete`, `cascadeDelete`, plus `insertUntil` / `updateUntil` / `terminateUntil` for bounded Bitemporal rectangle splits |
| `when.scenario` | `when` | scenario | an ordered list of read / committed-write / lifecycle-**action** steps (`action` + `on`, plus `set` / `path` and the per-step lifecycle observables `expectState` / `expectError` / `differentObjectFrom`), each carrying its own per-step golden `statements`; a `uow`-grouped write step MAY additionally carry `on`, naming the find it settles against (see *Settling against a grouped find*, below) |
| `when.coherence` | `when` | coherence | a two-node (A / B) operation sequence, each step carrying its node, kind, and per-step golden `statements` |
| `when.concurrency` | `when` | error / concurrencySuccess | a two-connection, barrier-separated `rounds` choreography; each node step carries per-step golden `statements` |
| `when.boundary` | `when` | boundary | an ordered list of portable unit-of-work actions (`read` / `create` / `update` / `terminate` / `delete`) |
| `when.attempts` | `when` | conflict | an ordered retry sequence of optimistic-lock `UPDATE` attempts, each carrying its own `statements` + `affectedRows` + `write` |
| `when.write` | `when` | conflict / rejected | the single-attempt neutral write input (①): the flat attribute-named row the versioned `UPDATE` / `DELETE` (or temporal close) operates on; on a `rejected` case, a write the validator MUST refuse pre-SQL — a row, a predicate-selected instruction, or a whole keyed instruction, dispatched on the members it carries (see *Rejected cases*) |
| `when.mutation` | `when` | conflict | the keyed verb `when.write` names — `update` (default) or `delete`; ignored for a temporal target, whose conflict write is always the milestone close |
| `when.model` | `when` | rejected | an inline model descriptor whose accepted-model formation is invalid — either a standalone/table-level defect or a cross-entity family invariant a model-aware validator MUST reject pre-SQL; kept inline so the shared `models/` registry stays loadable (see *Rejected cases*) |
| `when.uow` | `when` | no | unit-of-work configuration (`concurrency: locking \| optimistic`, `retries`, `retryOptimisticConflicts`) the action runs under; descriptive |
| `when.at` / `when.observedTxStart` | `when` | conflict | the harness-supplied Transaction-Time close instant (→ new `out_z`) and observed `txStart` / physical `in_z` the optimistic gate binds |
| `when.observedValidStart` | `when` | conflict | the observed milestone's `validStart` / physical `from_z` — with `when.observedTxStart` it is that milestone's own EDGE, naming the milestone the close observed instead of the close's address (see *Naming the observed milestone*, below) |
| `when.equivalentEncodings` | `when` | no | alternate surface encodings of `when.operation`; each MUST canonicalize to it |
| `then.statements` | `then` | yes* | the golden SQL an impl must emit — an ordered list of `{sql, binds}` statement entries (dialect-keyed map form), one per deep-fetch level or write-sequence DML step. *Absent for scenario / attempts cases, whose golden SQL lives per step; disallowed on a boundary case |
| `then.referenceSql` | `then` | conditional | an independent naive oracle (see below) — a plain string, OR a dialect-keyed map where the naive spelling is dialect-specific; for a deep fetch it is the naive single-statement oracle for the **root** row set |
| `then.rows` | `then` | read | the rows the query must return (single-statement / flat-result cases) |
| `then.graph` | `then` | read | the assembled object graph a deep fetch must produce (one of `then.rows` / `then.graph` / `then.graphs` is REQUIRED for a read case) |
| `then.graphs` | `then` | read | an ORDERED array of per-milestone edge-pinned graphs a `history` / `asOfRange` snapshot read materializes (see *Milestone-set graphs*, below) — each entry `{pin, graph}`; coexists with `then.graph` exactly as `then.rows` does |
| `then.identityChecks` | `then` | read | declared reference-identity expectations over graph node positions — each `{left, right, same}` with JSON-Pointer `left` / `right` and a boolean `same` — the same-node claim a back-reference cycle's PK-only stub cannot carry by value (see *Back-reference cycles*, below) |
| `then.tableState` | `then` | writeSequence | the resulting table state a writeSequence (or conflict) case asserts, keyed by table name (REQUIRED for a write case) |
| `then.affectedRows` | `then` | conflict | the number of rows the golden write must affect (`0` = the zero-row shortfall — a gated conflict or an ungated stale write, `1` = success) |
| `then.errorClass` | `then` | error | the neutral `m-db-error` category a triggered error must classify to (`uniqueViolation` / `deadlock` / `lockWaitTimeout`) |
| `then.nativeCode` | `then` | error | the per-dialect native code each driver must surface (Postgres SQLSTATE string, MariaDB vendor errno) |
| `then.outcome` | `then` | boundary | the portable expected outcome (`committed` / `aborted` / a surfaced error kind) |
| `then.rejectedRule` | `then` | rejected | the normative rule the input violates, from the closed vocabulary a model-aware pre-SQL validator MUST enforce (see *Rejected cases*) |
| `then.roundTrips` | `then` | no | declared statement count (default `1`); for a deep-fetch case it MUST equal the authored/executed `then.statements` count (child SQL is omitted after an empty parent-key level); for a write sequence it MUST equal the ordered DML statement count; for a scenario the SUM of per-step round trips |
| `then.tolerance` | `then` | no | absolute numeric comparison tolerance; omit for exact comparison (the default). Declare ONLY for inherently inexact results (stddev/variance, repeating-decimal avg) |

#### How a case spells an Entity

Every case field that ROUTES by model identity — `when.targetEntity` and a
scenario / coherence read step's `targetEntity`, a `writeSequence[].entity`, a
keyed or conflict write's `entity`, and a predicate write's `target.entity` —
carries an Entity spelling under `m-metamodel`'s identifier constraint and parse
rule: an Entity's local name begins capitalized and every namespace segment is
lowercase. Each admits the two spellings a reference position admits
(`m-op-algebra`) — the bare local name, legal wherever it names exactly one
declared Entity of the case's model, or the canonical `<namespace>.<Entity>` —
and resolves by the same rule.

This is addressing vocabulary. It is distinct from the *result* vocabulary a
case asserts — `then.graph` root keys, narrowed-view keys, and `familyVariant` —
which names what a read materialized rather than what it addressed, and keeps
its own ambiguity-sensitive rule stated with each.

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

This cross-check reads the case's declared `targetEntity` and is deliberately
weaker than the operation rule it guards: `m-op-algebra`'s positional rule asks
each reference of the **active position** — the queried position as re-narrowed by
every enclosing `narrow`, and, for an order key, the position the ordered rows
occupy — and classifies a violation as `subtype-attribute-outside-narrow-scope`
or `attribute-outside-active-position` (below). A read case whose references pass
this cross-check can still be refused by that rule, and MUST be authored so it is
not: a `rejected` case is the shape that pins the refusal.

An abstract-target read (an abstract `targetEntity`, or an abstract position
`narrow`ed with `m-op-algebra`'s `narrow` node) materializes complete concrete
instances. Every leaf — a `then.rows` entry or a `then.graph` node — carries a
**`familyVariant`** key — the concrete subtype's **family variant spelling**
(`Dog`, `Cat`, …; the canonical qualified Entity spelling when duplicate local
concrete names make a bare spelling ambiguous). `familyVariant` is **not projected as SQL**: under
`table-per-hierarchy` the golden SQL projects the **raw tag column** (`m-sql`,
resolved Q6) and the harness materializes `familyVariant` from the tag metadata
map (`tagValue` -> subtype name) — an independent, metadata-derived
recomputation like the as-of and PK-allocation oracles. A **concrete-target**
read carries no `familyVariant` (the caller already knows the variant) and
projects only that concrete instance's columns in either lane. A `narrow` node
inside `when.operation` is validated pre-SQL against the family's effective
concrete-subtype set (`m-op-algebra`); an invalid narrow is a `rejected` case
(see the narrow rules in *Rejected cases*).

**A "complete concrete instance" means something different in each result
form** (*Read result form*, below), so what ELSE a leaf carries beyond
`familyVariant` diverges by lane — independently of the Document-tier
projection split that section otherwise fixes:

- **Row-form** (`then.rows`) is the flat SQL projection observed unfiltered:
  every leaf carries the full non-Document **Position Layout** sequence in
  table-wide semantic tier order, with root-first ancestry, local declaration
  order, and canonical concrete order stable only within a tier. Non-applicable
  subtype contributors are `null` — the values lane reports the query's own
  fixed-superset `select` list exactly as it comes back (`m-sql` *Read
  projection*).
- **Instance-form**, at a **top-level read case's own `then.graph` leaves**
  (a `shape: read` case with no `deepFetch`), is the
  **per-variant node shape**: each node carries **only its own branch's
  members** — its inherited chain plus its own declared attributes — and
  **omits every sibling branch's column entirely**, with **no null sibling
  padding** — a materialized `Dog` node has no `indoor` key to be null, exactly
  as an ordinary (non-inheritance) instance never carries an undeclared member.
  This per-variant reduction is **materialization-time** narrowing, but result
  form still affects projection. The target position fixes the family, physical
  Table/branch shape, and non-Document Position Layout sequence. Instance-form
  then adds applicable `Document` slots, while row-form omits them (`m-sql`
  *Read projection*). The paired goldens named here are byte-identical only
  because their models have no applicable top-level Value Objects; in general,
  SQL differs by that Document-slot delta. Graph assembly — never branch shape
  or the non-Document sequence — narrows values to the variant's own declared
  shape. `m-inheritance-003`/`-013`/`-015`/`-052`
  (row-form) and their `then.graph` siblings `m-inheritance-106`/`-107`/
  `-108`/`-109` (instance-form) are this divergence's own result-form pair
  (like the supplier form-divergence witness, *Read result form*, below): the
  row-form original stays the values-lane witness, its sibling the
  instance-form (developer-surface) witness.

This per-variant node shape is scoped, for now, to a read case's own top-level
`then.graph` leaves — the shape a `db.find` on an abstract multi-concrete
position returns. A **deep-fetch or snapshot CHILD level**'s graph node shape
(`m-snapshot-read-012`'s narrowed-vs-broad diamond, for example) is a distinct,
already-established convention this decision does not touch; reconciling the
two — whether a child level's polymorphic relationship set should narrow the
same way — is left open for a follow-up.

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

Graph comparison distinguishes collection kinds. Root result sets and
relationship collections compare as multisets (relationship `orderBy` is graded
separately), while a Value Object occurrence with `multiplicity: many` compares
positionally because its document order is semantic. Duplicate Value Object
elements remain distinct.

#### Read result form (row-form vs instance-form)

**Every** read a case asserts carries a **result form** — the **object lane**
(**instance-form**) or the **values lane** (**row-form**) of `m-sql`'s *Read result form*
— and that form fixes the read's **default** Document-slot selection (`m-sql`, *Read
projection*: instance-form projects every applicable top-level Value Object
`Document` slot; row-form omits those slots). Exactly one internal read widens that
default without changing lane — the materialized-predicate-write resolving read
below, whose need is decided by the write it serves.
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
  - A value-object-bearing target therefore projects its whole `Document` slot at
    **every** instance-form step above, even though the channel is `expectRows` /
    `observeRows`.
  - The **internal materialized-predicate-write resolving read** — the "materializing
    find" a set-based versioned / temporal predicate write consumes to plan its per-row
    DML, resolving each matched row to its pk and gate values with **no instance
    constructed** (`m-sql`, ADR 0014) — is the **sole row-form** (values lane) step read.
    It projects only the `Document` slots the write it serves needs: a **temporal**
    target's resolve projects **every** declared one, because the per-row observation it
    records is a complete Predecessor Row (`m-unit-work`); a **versioned** target's
    resolve retains only the observed version, so it projects only the documents its own
    assignments compare against, and none at all for a `delete`. A reassigned document
    still comes from the write instruction, never from the read. A **`distinct` / grouped
    concurrency-witness read** is likewise a projection over the values lane (`m-sql`),
    constructing no instance.

Row-form is **not a developer surface** — the idiomatic find API is instance-form
(results always materialize). Row-form is the internal / conformance consumption lane
(predicate `read` cases, the materialized predicate-write read, and future aggregation
results — `m-agg`; a `distinct` / grouped concurrency-witness read is likewise a
projection over the values lane, `m-sql`). The form is **structural intent** an adapter's
`compile` MAY consume, exactly like `when.uow.concurrency`; it needs no schema field and
no case edit. The two forms' Document-slot divergence is witnessed at **case** level, by
the `then.rows` reads over `customer`, which omit `address`, against the `then.graph`
reads of that same model, which project it. Two scenario witnesses pin the step-level
pair, one per materializing target class. The `subscriber` witness pins the row-form
**default**: a versioned predicate `delete` retains only the observed version, so its
resolving read omits `address` while the managed find one step earlier — the same
canonical operation over the same row — projects it, the two goldens differing in that
one slot.
The `supplier` witness pins the **widening**: an audit-only close's resolving read
projects `address` even though the close copies no payload, because the observation it
records is a complete Predecessor Row.
The Document-slot delta is not the forms' only divergence overall: the
abstract-target per-variant materialization narrowing established above (*Read
targeting*, `then.graph`'s per-variant node shape vs `then.rows`'s concrete-superset
row) is the other — a graph-assembly-time shape difference over the same
non-Document Position Layout, not a Document projection difference. Neither witness is
the sole value-object-bearing step read either, now that the
lifecycle-action `load` / first-`access` witnesses carry value-object-bearing
instance-form step reads (each projecting its read entity's own `address` Document
slot). Every other entity read at a step (`balance`, `position`, `account`,
`order_item`, and the rest) declares no value object, so instance-form and row-form
project the same columns there: the classification pins the answer for the
value-object-bearing step reads and leaves every other golden untouched.

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
per declared dimension, keyed by `valid-time` or `transaction-time` — and its
**`graph`** is the plain-value graph materialized at that
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

A **path-root guard** (`m-op-algebra`'s `{ entity, to }` beside a path's
`segments`) participates in this layer twice, and both are declared rather than
inferred. Its level's authored `IN` binds must equal the keys gathered from the
**guarded** root objects alone, so a guard that a case declares but an
implementation ignores fails on the bind comparison rather than passing quietly.
And per-path statement counts follow the guard's **resolved source set**, so
`then.roundTrips` must be derived under the new shape rather than carried over:
two paths whose guards resolve to the same set are **one** hop, while every other
relation between two guards — disjoint, overlapping, or one containing the other
— is two, even where the second fetches nothing the first did not
(`m-deep-fetch`). Since a guard creates no view key, a case whose extra hop is
subsumed observes it in `roundTrips` and nowhere else: its `then.graph` is
identical to the covering path's alone, and a root object outside every guard
carries **no** entry for that path's relationship rather than an empty one.

For each deep-fetch level whose child entity is temporal, the harness derives the
**propagated as-of binds independently** (an oracle, parallel to the ordering
oracle): it reads the root pin from the operation's nested `asOf` nodes, matches
each axis to the child entity's as-of dimension, and computes the expected child
as-of binds (the `infinity` equality for latest, the `[D, D]` range for an
instant, Valid Time first and Transaction Time second). It then splits the authored child binds into the
IN-list slice and the as-of suffix, asserting the slice equals the gathered
parent keys and the suffix equals the computed expectation — so a dropped or
wrong propagated as-of fails the case automatically. A non-temporal child has an
empty suffix.

For a writeSequence case inserting into a `sequence`-strategy entity, the
harness derives the **PK-generation oracle** (`case_runner._assert_pk_allocation`):
it independently re-derives the allocated primary keys and the registry counter
from the declared `pkGeneration` config (`initialValue`/`incrementSize`/
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
case's `then.roundTrips`. A step on a **temporal** entity carries **exactly one**
neutral write input row (`m-unit-work`: each row closes its own milestone and
chains its own successors, and a temporal entity never collapses into a set-based
statement), so a chain per key is authored as a **step per key**. The model descriptor's serde round-trip (layer 4b) still
runs; there is no `when.operation` to serde (layer 4a) and no normalization
difference — the DML golden SQL is normalized to a fixed point exactly like read
SQL (layer 3).

A **value-object** column's neutral write input (①) value is **always** the literal
document (a JSON object, a JSON array, or `NULL`) — never a DB-computed write marker
(`{computed: "maxPlusOne"}` / `{increment: n}`), which is a **scalar-attribute-only**
form. A value object binds its whole document even when that document is *shaped*
like a marker; the two are disambiguated by the field's declared metamodel role
(resolved from the Entity Layout slot's contributor), not by the value's shape
(`m-value-object`, `m-storage-layout`).

A writeSequence case MAY set **`given.fixtures: true`** to load the model's
fixtures **before** the ordered DML (instead of starting empty) — so a sequence
can mutate a *pre-existing* persisted row. This is the `m-detach` detached-update
or detached-delete merge-back case, and the minimal dependent cascade-delete
witness: the original rows exist, the ordered DML mutates them, and the asserted
table state shows which rows changed or were removed.

### Conflict cases (`m-opt-lock`)

A **conflict** case proves optimistic-lock conflict detection by the **affected-
row count** a golden statement leaves behind. The harness loads the model's
fixtures (the versioned row exists), applies an OPTIONAL out-of-band
**`given.apply`** (naive statement entries simulating a concurrent transaction
that bumped the version or removed the row), runs the golden write (whose neutral
input is `when.write`), and asserts the affected-row count equals
**`then.affectedRows`** — `0` for the zero-row shortfall (the `updatedRows != 1`
signal) and `1` for success. When `then.tableState` is authored it is asserted
too, confirming a conflicting write did not apply. As with writeSequence cases,
only the descriptor serde round-trip and the golden-SQL normalization layers
apply (there is no `when.operation`).

The written verb is **`when.mutation`** — `update` (the default) or `delete` —
for a NON-temporal target; a temporal target's conflict write is always the
milestone close, so it ignores the field. The verb does not decide whether the
golden carries a gate: `when.uow.concurrency` does, uniformly across update,
delete, and close (`m-opt-lock`). A `delete` case therefore pins both halves of
that rule — the optimistic golden appends `and <version> = ?`, the locking golden
appends nothing — and a locking-mode zero-row outcome is the non-retriable stale
write rather than a retriable conflict.

A conflict case MAY instead carry a **`when.attempts`** retry sequence — an ordered
list of golden `UPDATE`s, each with its own `statements` + `affectedRows` + `write`
— proving the **`m-opt-lock` retry contract** end-to-end. After `given.apply`, the
harness applies each attempt in order and asserts its affected-row count: the first
(stale-version) attempt affects `0` rows (the conflict signal), then a retry that
re-reads the now-fresh version and re-applies affects `1`. The final
`then.tableState` confirms the retried write — not the concurrent writer's —
landed. (Golden SQL lives per attempt, so there is no top-level `then.statements`.)

#### Naming the observed milestone

A temporal close names its coordinates one of two ways, and never both.

The **address** form states them directly: the write row's `validEnd` is the
address's Valid-Time exclusive upper bound on a Bitemporal target, and
`when.observedTxStart` is the gate candidate. This is how a case tests a KNOWN
stale-or-fresh gate — a deliberately stale token names no current milestone at
all, so it can only be authored, never resolved.

The **observation** form states the milestone instead:
`when.observedValidStart` with `when.observedTxStart` is that milestone's own
**edge** — its guaranteed-selecting start instant per declared as-of axis
(`m-temporal-read`). The close's Valid-Time address bound and its gate are then
both **derived** from the one milestone the edge selects among those the case's
own state holds current. An implementation MUST refuse a close that carries an
observed edge alongside an authored `validEnd`: the two spell one fact from
opposite ends, so agreeing they prove nothing the derivation does not and
disagreeing one would have to silently win.

Both observation coordinates are entitled by the target and by the attempt, and
an implementation **MUST** refuse one rather than ignore it where it is not:

- A **non-temporal** target has no milestone at all, so it may author **neither**
  `observedValidStart` **nor** `observedTxStart`, on the single-attempt `when` or
  on any attempt. Its write gates on the row's own `observedVersion`, so a
  milestone coordinate beside it reaches nothing that could read it.
- `observedValidStart` names a Valid-Time start, so it is legal **only on a
  Bitemporal target**: a Transaction-Time-Only target's milestones have no
  Valid-Time start to name.
- The edge selects among the milestones the case's **own loaded fixtures** hold
  current, so `observedValidStart` is legal **only on the single-attempt `when`**.
  A retry attempt re-reads the state the concurrent `given.apply` writer left
  behind, which no fixture edge names and no lane performs a resolving read to
  discover, so a retry attempt states its **address** directly and gates on its
  own `observedTxStart`.
- A retry sequence's attempts each carry their own close, so a case authoring
  `when.attempts` may author **neither** coordinate on the root `when`: every
  attempt reads its own, and a root coordinate is consumed by no attempt. The two
  authoring locations are alternatives, never a default and an override.
- A **locking**-mode close renders no gate, so `observedTxStart` is entitled there
  only as the **edge**'s Transaction-Time half — that is, with `observedValidStart`
  beside it, where it selects the milestone whose Valid-Time end the address binds.
  An address-form locking close, which names its `validEnd` directly, may not
  author it: the close's every bind is then already spelled, and the coordinate
  would gate nothing.

Because an edge selects exactly one milestone, a case whose own state holds two
current milestones of one key carrying the **same** edge is unaddressable, and an
implementation MUST refuse that state rather than pick one of them.

The forms differ in what they can grade, not in what they emit. One key may hold
several disjoint Valid-Time rectangles current on Transaction Time at once
(`m-bitemp-write`), sharing the primary key, the open Transaction-Time bound,
and possibly the gate; only their edges tell them apart. An address-form case
therefore grades the rendering of an address it supplied, while an
observation-form case grades the **derivation** — an implementation that resolves
a close's address from the primary key alone has no single answer for such a key
and cannot render both siblings of an edge-named pair.

Neither form grades how an implementation **keys** the observations its own reads
record. A conflict case names the milestone its write observed, so the write
consumes one observation resolved once from state the case supplies, and nothing
here observes what a second read of one key does to the first read's evidence.
That is a limit of this shape, not of the format: a scenario `uow` group's write
MAY name the find step it settles against (*Settling against a grouped find*,
below), and that reference is where the corpus grades the keying.

The **gate**'s provenance stays outside both shapes, for two different reasons.
The requirement that address and gate both derive from the one observed milestone
is normative above; no conflict case can witness the gate half, because an
observed edge's Transaction-Time coordinate IS the milestone's Transaction-Time
start, which is exactly what the optimistic gate binds — so in any case that names
an edge the coordinate the case authored and the coordinate a derivation reads off
the resolution are the same instant, and an implementation that binds the gate
straight from `observedTxStart` renders every conforming golden. A conflict case
therefore grades the **address**'s derivation alone, and a header of one that
claims the gate's is claiming what no degradation of a conforming implementation
can falsify.

A grouped write naming its source find authors no coordinate at all, so there both
binds are read off the one resolved milestone and which of them a misresolution
moves depends on the target's **profile**. On a Bitemporal target a key's current
rectangles are disjoint on Valid Time, so two observations of one key differ in
their Valid-Time end and the misresolved **address** is what fails. On a
Transaction-Time-Only target there is no Valid-Time half at all: a close addresses
the key plus the invariant open Transaction-Time bound, so every observation of one
key carries the *same* address and differs only in the milestone's
Transaction-Time start — which is the **gate**. Two observations of one key are
what a group holds whenever it reads that key twice at different as-of
coordinates, on either profile; the profile decides only which bind states which
milestone was settled against. That is why this reference is legal against any
temporal target and why a Transaction-Time-Only witness grades the **gate**'s
derivation, the half a conflict case cannot reach.

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

A scenario case MAY carry an out-of-band **`given.apply`**, applied after the
model's fixtures load and **before the first step** — the same position the
conflict and writeSequence lanes apply it in. Here it is setup rather than a
concurrent writer: it is the only way to put state into a persisted row that no
authored member of the model can produce, such as a key inside a Structured
Column the model declares nowhere (`m-storage-layout`), which is what a newer
version of an application writing that table leaves behind for an older one to
read and carry forward. Carrying it makes the case `single-connection` run-only
like any other (see *Compile eligibility*).

#### Grouping steps into one unit of work (`uow`)

A read or write step MAY carry an OPTIONAL **`uow: <label>`** key — a
string grouping label (an action step MAY NOT: its lifecycle-object engine
path does not observe grouping). Steps sharing one label execute inside **one held
transaction** (one unit of work, one connection) instead of each step's own
default boundary; a step carrying no `uow` key keeps **exactly** today's
semantics (an ungrouped write step is its own commit/rollback boundary, an
ungrouped find runs on the autocommit connection). This is what lets a story
whose observing find, versioned write, and dependent find all belong to one
unit of work (`m-opt-lock`'s prior-observation rule) be authored as the SAME
unit of work the story runs, rather than three separate ones. Grouping is
opt-in: it changes the meaning of no existing (unlabeled) case.

Steps execute in **authored order**; a group's own steps need **not** be
contiguous — two groups MAY interleave, which is how a scenario represents the
classic optimistic-lock race as two competing units of work: one group's
observing find, then a second (concurrent) group's own observe-and-commit,
then back to the first group's doomed write. A group **commits** after its
LAST step, **unless** one of its write steps declares `rollback: true` — then
the WHOLE GROUP rolls back after its last step instead, exactly the
`m-unit-work` **abort contract** applied to the group rather than one step.
This is what lets a step later in the SAME doomed group (a find re-issued to
force-flush a pending write) observe the mid-transaction state the eventual
abort then erases, before any find outside the group re-resolves the restored,
pre-transaction rows. A **read step inside a group** reads THROUGH the group's
own transaction (read-your-own-writes): its `expectRows` are what THAT
connection observes mid-transaction, never the post-commit / post-rollback
state a later, ungrouped find would see.

#### Settling against a grouped find

A `uow`-grouped write step MAY carry **`on: <index>`**, naming the earlier find
step of its OWN group whose result it settles against. The reference spells one
thing the write row cannot: which of the group's reads handed over the value being
written. It reuses the action step's own `on` spelling, and takes only the single
index form — a keyed write settles against the one milestone its value came from,
so a set of sources would name none.

Everywhere else, a keyed write's observed row comes from **case state**: a
writeSequence entry and a conflict close alike consume a milestone the case's own
fixtures and earlier entries left current, because those shapes carry no read to
have observed one (*Naming the observed milestone*, above). This reference is the
one place that rule is displaced. Where it appears, an implementation **MUST**
resolve the write's observation from the **observation store this unit of work's
own reads filled** — the evidence the named find recorded when it ran, addressed
by the object and by the milestone that read observed — and **MUST NOT** substitute
a milestone derived from case state. Two obligations follow:

- The named find MUST have observed a row of the write's own key, and the write
  MUST settle against **that** row's milestone. A write whose named find observed
  no such row is refused; it names evidence that does not exist.
- The write MUST reach the store by the coordinate the value it was handed came
  from, never by primary key alone. A group whose finds read one key at as-of
  coordinates resolving to different milestones fills a distinct slot per
  milestone; an implementation keying by identity alone holds one slot, and a
  write naming the earlier find then settles against the later find's row.

The reference is legal only where every part of it is meaningful: on a step that
declares `uow` (evidence is transaction-scoped, and an ungrouped write shares a
unit of work with no find), whose `write` is the **buffered keyed** form (a legacy
string label carries no instruction and a predicate-selected write consumes no
single milestone, so neither has anything an observation could reach), naming an
EARLIER step of the SAME group that is a find, against a **temporal** target.

The target restriction is the one `m-unit-work` already draws between evidence
addressed by identity and evidence addressed by a milestone. A versioned
Non-Temporal target has exactly one row per primary key, so its grouped write
reaches its group's evidence by identity and the reference would name nothing the
resolution does not already have. A milestone chain holds several rows per key on
**either** temporal profile, so both are settled against by name. A Bitemporal key
may hold several disjoint rectangles current at once, and a
**Transaction-Time-Only** key, though only one of its milestones is ever current,
is read at as-of Transaction-Time coordinates that resolve to milestones of any
age: a group that reads such a key's current milestone and then reads the same key
as of an earlier instant holds two pieces of evidence, and the later read takes
nothing from the earlier. Naming the find is what says which of them the write was
handed — an implementation keying by identity alone settles the write against the
historical milestone while the current one its value came from is the one it can
close.

The profiles differ only in **which bind** a misresolution moves. A Bitemporal
close addresses the observed rectangle's Valid-Time exclusive upper bound, so
naming the wrong milestone changes the address. A Transaction-Time-Only close
addresses the key plus the invariant open Transaction-Time bound — an address every
observation of that key shares — so there the whole of the difference lands on the
optimistic **gate**, which binds the observed milestone's own Transaction-Time
start. Neither profile is the weaker witness; a Transaction-Time-Only one grades
the gate's derivation, which no conflict case can reach (*Naming the observed
milestone*, above).

A write settling against a find's result is **query-result-dependent**: the
milestone it addresses is read off a row no compile lane executes, so such a case
declares `compileEligibility: run-only` (see *Compile eligibility*).

#### Predicate-selected write instruction

A scenario write MAY retain the legacy string label, or use the canonical object
form below. This object is the language-neutral requested operation consumed by
`compile`, `run`, and API no-drift checks; golden SQL remains the independent
expected lowering, never the source from which an adapter deduces the write.

The canonical write-instruction vocabulary — this predicate-selected shape and
the keyed `writeSequence` shape — is **hosted in
[`write-instruction.schema.json`](../schemas/write-instruction.schema.json)**
(`m-unit-work`, the write-side analogue of `operation.schema.json`); this document
references that canonical shape rather than redefining it. `validFrom` is the
Valid-Time lower bound and `until` the bounded operation's exclusive Valid-Time
upper bound. `at` is harness/Clock-supplied Transaction-Time context, never an
instruction field or alias. The schema and corpus must adopt these final spellings
before COR-40 runtime work begins; no translation alias is conforming.

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
| `assignments` | only `update` / `updateUntil` | ordered `{attr, value}` data; nonempty and unique; `attr` names an assignable qualified top-level attribute or value object. An attribute takes a neutral scalar/null literal; a value object takes its complete object/array document or null according to its declared multiplicity/nullability. |
| `at` | temporal target | harness-supplied Transaction-Time instant for close/chain behavior; context, not an instruction member |
| `validFrom` | Bitemporal target | Valid-Time lower bound for the plain or bounded temporal operation |
| `until` | `updateUntil` / `terminateUntil` | bounded operation's exclusive upper bound |

Delete and terminate mutations carry **no** assignments. Assignment list order is
not SQL order: the target's Entity Layout order determines the emitted `set`
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
possible. A **temporal** target's resolve additionally includes every current
non-milestone scalar payload column and every top-level value-object document
column, on **every** verb it reaches — the close-only `terminate` that chains
nothing included — because the per-row observation it records is a complete
Predecessor Row (`m-unit-work`). That same observation is what a chained
successor, or a preserved Valid-Time head or tail, reads its carried-forward
values from. It does not project output generated by the framework — for example
a bumped version, fresh Transaction-Time instant/open bound, or inheritance
discriminator. A non-trivial scenario read MAY carry `referenceSql`,
with the same string-or-dialect-map shape
as `then.referenceSql`; it is self-contained (rather than reusing golden binds)
and must agree with its golden rows as the third oracle.

##### Buffered keyed write instructions (the ordered flush buffer)

A scenario write step MAY carry an **ordered keyed buffer** in place of a single
instruction: `/scenario/<n>/write` is then a list of **one or more keyed**
instructions a single unit of work accumulates and **flushes together**
(`m-unit-work` buffered, batched, ordered writes). Each entry is a **keyed**
instruction (`mutation` + `entity` + `rows`, the case-format analogue of
`write-instruction.schema.json`'s `keyedWriteInstruction`), **referencing** the
canonical write-instruction `$defs` rather than redefining them and layering only
the `at` / `validFrom` / `until` authoring surface. A **predicate**-selected
instruction is **not** admitted — the buffer is **keyed-only**, and
predicate-in-buffer stays **deferred** to the string-label→structured write
migration. The step's golden SQL (`statements`) is the **independent expected
lowering of that flush**, never the source an adapter deduces the writes from, so
the step encodes **every** requested mutation explicitly and an adapter exercises
the flush from the instructions themselves. Valid-Time bounds are `validFrom` and
`until`; the Transaction-Time instant rides as Clock-context `at`, never an
instruction field.

The buffer is **general**: it spans a **single** keyed write (a buffer of one), a
**mixed multi-object flush** — an `insert`, `update`, and `delete` of **different**
objects, foreign-key-ordered at flush — and the **same-object coalescing** case
alike. **Same-object folding at flush is the coalescing rule**, a runtime/planner
property rather than a structural one: when two buffered instructions name the
**same** entity and primary-key identity the flush combines them — insert-then-update
writes the **final** value in place (`roundTrips: 1`), insert-then-delete **cancels**
to **no** DML (`roundTrips: 0`, no `statements`). The two-keyed same-object
insert-then-update / insert-then-delete pair is that rule's **single-object special
case**, not a separate shape. The JSON Schema pins only the structural shape (one or
more keyed entries); it imposes **no** cross-entry same-object equality, and the
retained static checks are per-entry **member-name honesty** (each keyed row key
names a declared attribute / value object of its entity) and the **temporal
singleton** (`m-unit-work`: an entry on a temporal entity carries exactly one row,
since each row chains its own milestones — author several rows as several
entries). Both are model-aware, which is why neither is expressible in the JSON
Schema. Coalescing and
foreign-key-ordering correctness are proven where they always were — the step's
golden SQL executed verbatim, plus `tableState` / `expectRows`.

```yaml
- write:                                    # an ordered keyed buffer (here, the coalescing special case)
    - mutation: insert
      entity: Balance
      rows: [{ id: 9, acctNum: D, value: 100.00 }]
      at: "2024-06-01T00:00:00+00:00"       # Transaction-Time Clock context, not an instruction field
    - mutation: update
      entity: Balance
      rows: [{ id: 9, value: 150.00 }]
      at: "2024-06-01T00:00:00+00:00"
  roundTrips: 1                             # same-object fold ⇒ ONE final-value INSERT (value 150)
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
  - `transaction-time-pin-read-only` — a mutation through a finite
    Transaction-Time pinned view, which records what the system knew and is never rewritten
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

### Rejected cases (`m-value-object` / `m-op-algebra` / `m-inheritance` / `m-storage-layout` / `m-unit-work`)

A **rejected** case proves a **negative**: that a model-aware validator refuses an
invalid input **before any SQL is emitted** (resolved question 7). It carries the
invalid input under `when` — **exactly one** of an `operation` (a schema-valid
`m-op-algebra` node), a `write` (a neutral write row, ①), **or** a `model` (an
inline invalid model descriptor, below) — and a `then.rejectedRule` naming
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
The adapter-side answer for a rejected-case `run` is the `m-conformance-adapter`
`rejectedRule` observation; see `m-conformance-adapter`.
This is the portable analogue of Reladomo refusing a structurally-invalid
embedded-value use (an embedded value is not a relationship target and cannot be
reverse-navigated); Parallax pins the same "these operations are structurally
invalid" semantics as a language-neutral pre-SQL rejection.

A `when.write` is one of three inputs, and an implementation **MUST** dispatch on
the members the input itself carries — never on the case's tags, filename, or
named rule, which no adapter is obliged to read before validating. A `target`
names a **predicate-selected instruction**; a `rows` array names a whole **keyed
instruction**; anything else is the **bare neutral write row** (①). The three
differ in what supplies the entity handle, which is why the distinction is
load-bearing rather than cosmetic: the first two name their own target, so a
validator checks the payload against the entity the input authored, while a bare
row names none at all and is resolved against the model's default write root: the
inheritance-family root when the model declares exactly one family, else — when it
declares no family at all — its own first entity. A model declaring **several**
families names no single root and therefore has no default; a bare row against one
is a case-authoring failure, not a rule to grade, because resolving it to whichever
entity happens to be declared first would grade a rule against an entity the case
never named. The same default resolves a `when.operation`, which likewise names no
target.

All three are **objects**, and a rejected `when.write` that is not one is
**invalid**. The `when.write` vocabulary is shared with conflict cases, which also
spell the multi-key form as an **array** of rows; that form states the aggregate
affected-row count one collapsed statement owns, which a rejection asserted pre-SQL
has nothing to say about. An array carries no member to dispatch on, so admitting
one here would leave each implementation to invent an answer — the schema refuses
it, and both graders refuse it by shape before asking for a member.

`target` and `rows` are therefore **reserved** at this position: a bare write row
authors neither, exactly as it authors neither half of an observed milestone's own
edge coordinate. A row is a row only because nothing on it names an instruction,
so without the reservation the row form would admit every instruction, the two
instruction forms would decide nothing, and a legitimate row for an entity whose
model declares a `many` value object named `rows` would be re-read by every
dispatcher as a keyed instruction. Such a row is **refused** rather than
reclassified — a silent reclassification turns an authoring mistake into a case
that grades a rule it never meant to reach — and its entity is written through the
keyed form, which names its own handle. The reservation is positional: it holds
where a row and an instruction can stand in the same place, so the rows nested
inside a keyed instruction, a `writeSequence` step, or the multi-key array form
keep the full member vocabulary.

A keyed instruction is admissible **only** here: everywhere else
a keyed instruction reaches an implementation through `when.writeSequence` or a
`when.scenario` step's own buffer, where the golden SQL it lowers to is what
grades it. The rejected lane emits no SQL, so it is the one lane in which the
instruction itself — its verb, its target, and its row count together — is the
input under test rather than a row's contents.

`then.rejectedRule` is a **closed vocabulary**, each identifier naming a normative
MUST — the `m-op-algebra` predicate rules (bound ordering, and the
nested-predicate resolver), the `m-value-object` materialization/navigation and
write-validation contracts, and accepted-model formation rules. **Operation**
rules:

- `between-bounds-inverted` — a `between`'s `lower` bound is strictly greater than
  its `upper`, comparing same-kind literals only (both numbers, or both strings),
  so the range is empty by construction (`m-op-algebra` bound ordering).
- `nested-path-first-segment-not-value-object` — a nested path's first segment names
  no value object declared on the queried entity (`m-op-algebra`).
- `nested-path-unknown-member` — an intermediate segment names no declared nested
  value object, or the leaf names no declared attribute (`m-op-algebra`).
- `nested-literal-type-mismatch` — a nested comparison / range / membership
  literal's type differs from the leaf attribute's declared neutral type
  (`m-op-algebra` typed literals).
- `nested-string-predicate-non-string-member` — a nested string predicate
  (`nestedLike` / `nestedNotLike` / `nestedStartsWith` / `nestedEndsWith` /
  `nestedContains`, in either nested scope) resolves to a leaf whose declared neutral
  type is not `String` (`m-op-algebra` non-string-member rule). Checked **before**
  the typed-literal rule, so a `date` / `time` / `timestamp` / `uuid` / `bytes`
  member — which carries the portable `string` literal and so satisfies the
  typed-literal check — is named here rather than silently accepted.
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
- `subtype-attribute-outside-narrow-scope` — a predicate or order key references a
  concrete-subtype-declared attribute at a polymorphic position that is not
  `narrow`ed to that subtype, so the attribute is not available to every concrete
  in the effective set (`m-op-algebra` × `m-inheritance`). The reference and the
  position share an inheritance family, so narrowing is the remedy; when they do
  not, the rule is `attribute-outside-active-position` below.
- `attribute-outside-active-position` — a predicate or order key references an
  attribute of an Entity that shares **no** inheritance family with the active
  position, so the reference is applicable nowhere in the read and no `narrow`
  can make it so (`m-op-algebra` positional rule). An order key is asked of the
  position its ordered rows occupy, which a top-level `narrow` moves.
- `reference-ambiguous-entity-name` — a reference position names an Entity by a
  **bare local name** that two namespaces of the model declare, so it resolves to
  no single Entity and the reference resolves nowhere (`m-op-algebra` reference
  resolution). It is the resolution half of the two positional rules above, which
  presuppose a reference that resolved: they fire when a reference resolves to an
  Entity **outside** the position, this one when it resolves to **more than one**
  and therefore to none. The rule refuses the **reference**, never the
  declarations — each Entity stays declarable, materializable under its exact
  qualified identity, and readable through a position naming it unambiguously.
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
- `write-required-value-object-missing` — a required `one` value object is absent
  (or null) at any depth, or a `many` occurrence is present as an explicit null. An
  **absent** `many` is not a violation: `Missing` and the empty array are one
  logical zero state, so an unnamed `many` occurrence stores `[]`
  (`m-value-object`, `m-document-codec`).
- `write-value-type-mismatch` — a document field value's type differs from the
  attribute's declared neutral type.
- `predicate-write-readless-document-many-unsupported` — an unversioned,
  non-temporal predicate-selected update assigns a document-resident `many`.
  The predicate, target, and assignment are individually valid; their readless
  combination is refused before buffering or SQL (`m-batch-write`).

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

**Instruction** rules (`m-unit-work` — a schema-valid keyed instruction whose own
shape a model-aware validator MUST refuse pre-SQL, judged against the target's
temporal profile rather than against any row's contents):

- `temporal-keyed-write-multi-row` — a keyed instruction on a **temporal** target
  carries more than one row. Each row of a milestone chain closes its own current
  milestone, consumes its own Temporal Observation, and opens its own successors,
  and a temporal target never collapses into a set-based statement
  (`m-batch-write`), so several rows under one instruction denote several
  independent chains rather than one wider write (`m-unit-work` "A temporal keyed
  instruction carries exactly one row"). Refusing is the rule: settling the first
  row would silently discard the rest and invent an observation-to-row mapping the
  instruction cannot express. The row count a keyed instruction may carry depends
  on whether its target is temporal, which the schema cannot see, so the neutral
  schema states the general one-or-more bound and this decides it.

**Model** rules (accepted-model formation — foundational, Inheritance, and
Storage Layout invariants that per-entity schema validation cannot express,
carried inline under `when.model`):
`metamodel-index-identity-duplicate`: two Indices of one Entity bear one name,
counting the derived primary-key Index a frontend hands over
(see `m-metamodel`),
`inheritance-unknown-parent`, `inheritance-cycle`,
`inheritance-missing-root`,
`inheritance-concrete-without-abstract-root`,
`inheritance-missing-concrete-subtype`,
`inheritance-tph-root-table-required`,
`inheritance-tph-descendant-table-forbidden`,
`inheritance-tpcs-abstract-table-forbidden`,
`inheritance-tpcs-concrete-table-required`,
`inheritance-abstract-node-fixture-rows`,
`inheritance-strategy-redeclared`, `inheritance-missing-tag-value`,
`inheritance-duplicate-tag-value`,
`inheritance-tag-on-concrete-subtype-strategy`,
`inheritance-temporality-not-root-owned`,
`inheritance-optimistic-locking-not-root-owned`,
`inheritance-persistence-not-root-owned`,
`inheritance-layout-not-root-owned`,
`inheritance-materialization-key-collision` (see `m-inheritance`),
`storage-layout-table-mapping-collision`: a later independent mapping owner
claims a structural Table already claimed by the first canonical owner,
`storage-layout-column-collision`: within one uniquely owned Table, distinct
Attributes, top-level Value Objects, a TPH discriminator, or a shared Structured
Column claim one physical Column,
`storage-layout-document-member-column-override`: a document-resident Attribute
or top-level Value Object carries a Column Override its root-owned Relational
Document Layout contradicts,
`storage-layout-index-over-document-member`: an Index component names a
document-resident Attribute, which has no Column to index (see
`m-storage-layout` for each invariant).
A `when.model` case carries an **inline** model descriptor — an
instance of `metamodel.schema.json` with an accepted-model formation defect — kept inside the
case rather than in the shared `models/` registry, so an invalid model cannot
break the sibling cases that load real models. The inline descriptor is
**round-tripped through descriptor serde** (layer 4) like any other model before
semantic validation asserts the rejection; the case's top-level `model:` still
names a real, loadable descriptor (its identity/registry role is unchanged). A
model-aware validator (and every language implementation) MUST reject the inline
model pre-SQL with **exactly** the named rule.

Storage Layout validation is keyed by structural Table identity. A standalone
Entity is one mapping owner, a whole TPH family represented by its root is one
owner, and each TPCS concrete mapping is one owner; TPH participants do not
compete with their family. Owners are encountered in canonical Entity Identity
order. The first owner claims the Table, and every later independent owner is
rejected as `storage-layout-table-mapping-collision` at its Entity mapping
location with the first owner related. The same-Table witness uses non-overlapping
Columns so this ownership issue cannot be mistaken for a physical Column claim.

Within every uniquely owned Table, `storage-layout-column-collision` applies to
a standalone Entity's local contributors, one table-per-concrete-subtype
concrete's inherited contributor chain, or the full table-per-hierarchy shared-
table superset including its tag. Inline rejected models separately witness the
same-Table owner collision, an Attribute/Value Object Column collision, an
inherited table-per-concrete-subtype Column collision, sibling contributions to
one shared Table, and a member colliding with the shared-table tag. This keeps
invalid models out of the reusable model registry while making each boundary
executable.

Purely **regex-level** negatives — an empty path after the value-object name, a
bad-cased segment — are the operation schema's job (the `nestedRef` grammar) and
stay **schema-validation unit tests**, never `rejected` cases: a syntactically
malformed operation is refused at layer 1 (schema conformance) before a model-aware
resolver ever runs. Likewise, purely **schema-expressible per-entity** inheritance negatives (a
rejected `strategy` enum value or the retired `discriminator` vocabulary) are
refused at layer 1 and stay schema-validation unit tests; `when.model` cases pin all
schema-valid accepted-model formation defects, including standalone/table-level
collisions and cross-entity family invariants. Table legality is strategy-relative
and therefore belongs to whole-model formation: a TPH root owns the shared table,
whereas a TPCS concrete subtype owns its table.

#### What decides a bare write row

The three forms above close the **dispatch** question by construction: the schema
admits exactly those objects, their discriminators are mutually reserved, and the
array is refused outright, so every reader picks the same form for every admitted
input. Nothing in the schema closes the question that follows it — *which rule an
admitted bare row violates* — because the schema is model-blind: a row's members are
attribute and value-object names it cannot know, and its values are the unrestricted
`writeRowValue`. Two independent graders can agree there only if this specification
decides every position a row can occupy, so it is enumerated rather than left to
each implementation's reading of the three rules.

A bare row is resolved **member by member against the target's declared structure**,
in **declaration order** — every declared Attribute, then every declared Value
Object, each document depth-first. Declaration order is normative: it makes the rule
a row of two defects violates a property of the *model* rather than of the row's
authoring order, so two implementations classify one row identically. The row is
graded as a **full document** — it carries no mutation to make it sparse.

Every key it names must name a declared member. A key that names none resolves to no
position, so no rule of the closed vocabulary is *about* it, and grading the row
regardless would report whichever rule some other member happens to violate — the
case would pass while testing something it never claimed. Such a row is therefore a
**case-authoring failure**, refused before the walk and never classified as a
`rejectedRule`, exactly as the keyed instruction form's rows are. The one key that is
not a member is `observedVersion`, which the shared row vocabulary admits as
flush-time context. The refusal is asked **after** the Subtype-write rules below,
which own the family-specific names a row may not carry and classify them.

That ordering belongs to the **row**, not to the form carrying it: a keyed
instruction's rows are asked the Subtype-write rules and then the member-honesty
refusal, in that order, before the instruction's own shape is judged at all. A
keyed `update` of a concrete subtype carrying a sibling branch's attribute is
therefore `subtype-write-sibling-attribute` in both forms, and one neutral write
row is classified one way however it is authored.

That ordering only works because the two checks divide the names between them
rather than both claiming every name. The Subtype-write rules are about names the
**family declares**: the tag column and the `tag` / `tagValue` / `familyVariant`
handles are `subtype-write-metadata-field`, and a member declared on a sibling or
unrelated branch is `subtype-write-sibling-attribute`. A name the family declares
**nowhere** sits on no branch at all, so it is no part of the sibling comparison —
including it would make every candidate ancestry chain fail and report a sibling
attribute for a name that is simply not real. Restricted that way, a payload
carrying a globally undeclared key falls through to the member-honesty refusal
above, which is the judgement that key actually needs.

Each position is one of six declared kinds, and the value authored at it falls in
one of five classes. The cells are the complete enumeration:

| declared position | absent | explicit `null` | admitted value | out-of-space scalar | value the position cannot hold |
| --- | --- | --- | --- | --- | --- |
| Attribute, `nullable: false` | `write-required-attribute-missing` | `write-required-attribute-missing` | accepted — an in-space scalar literal | `write-value-type-mismatch` | `write-value-type-mismatch` |
| Attribute, `nullable: true` | accepted | accepted | accepted — an in-space scalar literal | `write-value-type-mismatch` | `write-value-type-mismatch` |
| Value Object `one`, `nullable: false` | `write-required-value-object-missing` | `write-required-value-object-missing` | accepted — a document | — | `write-value-type-mismatch` |
| Value Object `one`, `nullable: true` | accepted | accepted | accepted — a document | — | `write-value-type-mismatch` |
| Value Object `many` | accepted (the empty collection) | `write-required-value-object-missing` | accepted — a list of documents, `[]` included | — | `write-value-type-mismatch` |
| framework-owned Attribute | accepted | accepted | accepted | accepted | accepted |

Reading the columns:

- **Admitted value** is what the position holds: an in-space scalar literal at an
  Attribute, one document at a `one` occurrence, a list of documents at a `many` one.
  A present document is not a leaf verdict — each member inside it answers its own
  row of this table, which is how the three rules hold at any depth.
- **In-space** is membership of the declared neutral type's value space, asked of the
  **portable literal** the case authors: the literal is in space when it *decodes* to
  a member (`m-core`, `m-document-codec`). Decoding is **many-to-one** where the
  document encoding is one-to-one — a value is stored in exactly one canonical
  spelling, while every spelling the grammar below names that value with decodes to
  it — so a non-canonical but admitted literal is in space and stores as the
  canonical form.
- The **portable literal grammar** of each string-carried type is exactly the
  document spelling `m-document-codec` fixes, widened by these variations and no
  others. It is enumerated rather than left to a host parser: every mainstream
  language ships an ISO-8601, UUID, and decimal parser with its own incidental
  extensions, and adopting one implementation's would make the others reproduce
  *it* rather than this contract.

  | type | admitted spellings |
  | --- | --- |
  | `bytes` | hexadecimal in **either digit case**, two digits per octet, no prefix and no separator |
  | `uuid` | 32 hexadecimal digits in **either digit case**, grouped 8-4-4-4-12 or with **no hyphens at all** |
  | `date` | `YYYY-MM-DD`, and a valid calendar date |
  | `time` | `hh:mm:ss` with an optional `.` fraction, or with the **seconds omitted**; no offset |
  | `timestamp` | `YYYY-MM-DDThh:mm:ss` with an optional `.` fraction, closed by `Z` or by **any** `±hh:mm` offset |
  | `decimal(p,s)` | a JSON number, or the exact spelling: a `-` only below zero, integer digits with no leading zero, an optional `.` fraction |

  So a brace-wrapped or `urn:uuid:` UUID, a hyphen in any other position, a week or
  ordinal or basic-format date, a space or any other character where the `T`
  belongs, an offset carrying seconds, and a decimal carrying a digit separator, a
  leading `+`, surrounding whitespace, an exponent, or `nan` / `infinity` are each
  **out of space**, however readily some host parser takes them.
- A **number literal at a `float32` / `float64`** names the float of the declared
  width nearest it (`m-document-codec`), so the only such literal out of space is
  one whose magnitude the width cannot hold — `1e39` at a `float32`. The carrier a
  loader happens to put the number in decides nothing: `20`, `20.0`, `16777217`, and
  `16777217.0` are all in space at a `float32`, because `20` and `20.0` are one JSON
  number and so are `16777217` and `16777217.0`. This is deliberately **not** an
  exactness rule — the last two store as `16777216`, a different number than the case
  wrote — and a case that means to author a value the width holds exactly must
  therefore write one; the grader will not catch it. Exactness cannot be recovered by
  refusing inexact literals here, because a canonical `float32` spelling is routinely
  inexact (`1e30` is the one `m-document-codec` gives `1.0000000150474662e30`), so
  the refusing rule is "exact **or** canonical" and narrows the value space rather
  than the case format.
- **Out of space** is a literal that decodes to no member: an integer beyond its
  declared width; a number whose magnitude the declared float width cannot hold; a
  decimal the declared precision and scale cannot hold exactly; text with no UTF-8
  encoding; a temporal literal carrying non-zero sub-microsecond precision; and any
  spelling outside the grammar above.
- A **DB-computed marker** (`{computed: …}` / `{increment: …}`) is admitted at a
  scalar Attribute and is a value no other position can hold. The disambiguation is
  by the position's declared metamodel ROLE, never by the value's shape, so a
  marker-shaped value inside a value-object document is a document field like any
  other.
- **A value the position cannot hold** is the multiplicity and document rules: a
  non-document at a `one` occurrence, a non-list at a `many` one, a non-document
  element inside a `many` list, and a document or list at a scalar Attribute. It is a
  **type mismatch**, not an absence: the member was named, so no required-ness rule
  is what it violates.
- A **framework-owned** Attribute (the optimistic-lock version, an As-Of Axis
  endpoint, a table-per-hierarchy tag column) is outside the walk entirely: the
  framework supplies its value, so its absence is no caller omission. A payload that
  *carries* the tag column violates the concrete-subtype protocol above instead.

The kinds compose: a nested Attribute or Value Object inside a present document
answers to its own row of the table, so the three rules hold "at any depth" by
recursion rather than by a separate depth rule. Where the target participates in an
inheritance family, the **Subtype-write** rules above run **first**
and over the family-effective member set, so an inherited required member is
required of a subtype write.

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
- **Length follows content**: keep the header concise and focused on the
  contract, the semantic distinction, and the information a reader needs to
  trust the assertions. A longer header is appropriate when the YAML cannot
  clearly express an important mapping or edge-case rationale; a header that
  narrates several unrelated behaviors usually signals the case should be split.

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
  case**, with coverage enforced by the suite's own partition assertion. This
  keeps every clarified branch specified in
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
  insert folds the computation into its own SQL and stays eligible),
  framework-owned observed-version / `in_z` binds, or a close whose address is read
  off the milestone a find of its own unit of work observed (*Settling against a
  grouped find*, above). `given` fixtures are legitimate
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
