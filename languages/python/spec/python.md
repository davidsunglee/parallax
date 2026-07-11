# Parallax Python — Completed Language Spec

This is the completed per-language spec for the Python implementation of
Parallax, authored from [`core/spec/language-spec-template.md`](../../../core/spec/language-spec-template.md).
Nothing here contradicts the core specification, the canonical claim in
[`slices.md`](../../../core/spec/slices.md), or the normative module DAG and
artifact topology in [`modules.md`](../../../core/spec/modules.md).

Guiding decision: the Python target is **Python-first and SQLModel-inspired**.
Developers author Pydantic-based entity classes; the canonical YAML/JSON
descriptor is derived output (and direct input for the conformance adapter),
never something an application developer hand-writes.

## 1. Scope and exact claim

| Scope decision | Required record |
|---|---|
| Conformance Slice | `slice-snapshot-1` — tag `slice-snapshot-1`, plain-value **snapshot** lifecycle profile, defined in [`core/spec/slices.md`](../../../core/spec/slices.md). |
| Exact `describe` claim | The complete canonical `describeOk` envelope below; structurally equal to the canonical claim after JSON parsing, except for the `adapter` identity. |
| Claimed capability coverage | Copied verbatim from the canonical claim: the 23 `modules` below, `dialects: ["postgres"]`, the eight `caseShapes`, `caseTags.include: ["slice-snapshot-1"]`, `commands: ["describe", "compile", "run"]`, `provisioning: "self-managed"`. `modules` is the tagged-case union of the slice, **not** a dependency closure and not a packaging plan. |
| Unclaimed implementation prerequisites | `m-db-port` — reached via `m-unit-work` and `m-db-error`; abstract port supplied by the `parallax.core.db_port` scope, concrete adapter by `parallax-postgres`; contract-covered, never case-advertised. `m-op-list` — reached via `m-navigate` and `m-deep-fetch`; supplied by the internal, unexported `parallax.core.op_list` scope; the snapshot surface never exposes an operation-backed lazy list. |
| Deferred capabilities | MariaDB (dialect); `benchmark` command and `m-perf-bench`; `m-agg` / `m-sql-agg`; `m-business-only`; `m-process-cache` / `m-coherence`; `m-cascade-delete`; the `snapshot-history-includes` feature; the managed-object lifecycle (`m-identity-map`, `m-detach`, public operation-backed lists); an async developer surface; MAY-tier mutations (`insertWithIncrement`, `incrementUntil`, `purge`, `inactivateForArchiving`); template-database reset optimization; isolation-level configuration; handle-level default concurrency override; statement `where`-refinement chaining and `as_of` re-pinning. Deferral is roadmap intent; **unsupported classification** is the adapter's wire behavior for out-of-claim requests — the two are recorded separately and never conflated. |
| Supported dialects and commands | Postgres only; `describe`, `compile`, `run`. Exercised locally and in CI by `uv run pytest -m compile_sweep` (Docker-free compile of every claimed case) and `uv run pytest -m conformance` (the `pg-full` run profile), aggregated by `just python-static` and `just python-verify`. |

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "python", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-audit-write", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-dialect", "m-inheritance", "m-navigate", "m-op-algebra", "m-opt-lock", "m-pk-gen", "m-read-lock", "m-snapshot-read", "m-sql", "m-temporal-read", "m-unit-work", "m-value-object"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "error", "concurrencySuccess", "rejected"],
    "caseTags": { "include": ["slice-snapshot-1"] },
    "commands": ["describe", "compile", "run"],
    "provisioning": "self-managed"
  }
}
```

- **Unsupported classification.** The adapter returns `status: "unsupported"`
  with exit `10` for every case command outside the claim and never for an
  in-slice case. Classification order mirrors the adapter contract's filters:
  unclaimed command (`benchmark`) → `unsupported-command`; dialect other than
  `postgres` → `unsupported-dialect`; unclaimed case shape →
  `unsupported-case-shape`; any case module tag outside the claimed `modules` →
  `unsupported-module`; a case not carrying `slice-snapshot-1` →
  `unsupported-case-tag`. Each response carries a diagnostic naming the first
  failed filter.
- **Case-selection expression.** Verification selects
  `("slice-snapshot-1" ∈ case.tags) ∧ (dialect = postgres) ∧ (case.shape ∈ claimed caseShapes) ∧ (case module-tags ⊆ claimed modules)`;
  milestone-scoped runs intersect further with capability tags via
  `--parallax-tags <m-slug>[,…]`. Filename prefixes are never a conformance
  target.

## 2. Shared developer API and model surface

### Query and operation API

- **Finder/query entry point.** A free-standing, side-effect-free statement is
  built from classmethods on the entity class and executed by the Parallax
  Handle. Variadic `where(*predicates)` conjoins its arguments (the natural
  big-AND of filter criteria; zero arguments is find-all). A statement with
  predicates rejects a further `.where()` call (refinement chaining is a
  deferred additive extension).

  ```python
  op = Order.where(
      Order.order_id == 42,
      Order.items.any(OrderItem.sku.in_(["A", "B"])),
  )
  snapshot = db.find(op)
  ```

  Canonical `m-op-algebra` serialization of that statement:

  ```yaml
  targetEntity: Order
  operation:
    and:
      operands:
        - eq: { attr: Order.orderId, value: 42 }
        - exists:
            rel: Order.items
            op:
              in: { attr: OrderItem.sku, values: [A, B] }
  ```

  To-many predicate paths always carry an explicit quantifier (`.any(...)`);
  expression objects raise on `__bool__` (catching accidental `and`/`or`/`not`
  and chained comparisons, pointing at `&`/`|`/`~` and `.between()`), and
  reflected operators (`25 | expr`) raise with parenthesization guidance.
- **Single-object find.** Arity is negotiated on the materialized result:
  `snapshot.result()` raises `NoResultFound` on zero and `TooManyResultsFound`
  on more than one; `snapshot.result_or_none()` returns `T | None`, raising
  only on more than one; `snapshot.results()` returns a plain `list[T]`. No
  implicit `LIMIT` is injected; callers wanting one write `.limit(2)`
  explicitly.
- **`group` operator.** Spelled with native Python parentheses only — no public
  `group` constructor exists. Python's `&` binds tighter than `|`, matching the
  algebra's precedence; the serializer inserts a canonical `group` node exactly
  where an operand's combinator binds looser than its parent (an `or` directly
  under an `and`), and flattens same-combinator nesting (order-preserving) to
  the n-ary canonical form. Redundant `group` nodes are unrepresentable, so an
  idiomatic operation can never drift from canonical form over grouping. The
  internal group node type exists for serde/tooling and is not public API.
- **Deep-fetch/include spelling.** Chained attribute paths on the statement:
  `Order.where(...).include(Order.items.statuses, Order.tags)`. One path
  grammar shared with predicates; longer paths imply their intermediates
  (glossary Include Path). The first hop is statically typed via descriptor
  `__get__` overloads; deeper hops resolve dynamically and are validated
  against the metamodel at statement-build time — never at execution and never
  at the database. Subtype narrowing on a position or include path is spelled
  `.narrow(ConcreteOrAbstractSubtype, ...)` (e.g.
  `Animal.where(...).narrow(Dog)`, `Owner.pets.narrow(Dog)`) and serializes to
  the canonical `narrow` / `pathNarrow` nodes; the resolved set must stay
  within the position's effective concrete-subtype set, checked at build time.
- **Temporal-read spelling.** Statement-level and axis-keyed, with the two core
  axis kinds as the public vocabulary:

  ```python
  Balance.where(...).as_of(processing=d)
  Position.where(...).as_of(business=b, processing=p)
  Balance.where(...).history("processing")          # Literal-typed axis
  Balance.where(...).as_of_range(processing=(f, t))
  ```

  Timestamps are timezone-aware `datetime` values, normalized to UTC,
  microsecond precision; naive datetimes are rejected at statement build. An
  omitted axis defaults to **latest** per the core default-injection rule; the
  module-level `LATEST` sentinel spells the same pin explicitly and lowers to
  the identical injected predicate. `as_of` is single-shot: calling it on an
  already-pinned statement raises (derive from the unpinned base instead;
  re-pinning is a deferred additive extension). Rejected at build: pinning or
  scanning an axis the entity does not declare, temporal clauses on
  non-temporal entities, and conflicting double pins.

### Metadata and model input

- **Primary model-authoring format.** SQLModel-style decorated Pydantic
  classes. Developers define frozen entity classes extending the Parallax base
  with field/relationship metadata; the class frontend builds the in-memory
  **metamodel**, which is the single hub: it round-trips through canonical
  JSON and YAML serde, exports canonical descriptors, and is equally
  constructible by **direct ingestion** of canonical YAML (the conformance
  adapter's path — corpus cases never require Python classes). The API
  Conformance Suite closes the loop by authoring idiomatic classes for corpus
  models and asserting their exported descriptors are structurally equal to
  the corpus YAML (the no-drift guard).
  Naming: Python fields are snake_case; canonical identifiers are camelCase.
  A deterministic snake→camel conversion applies on export (drop underscore,
  capitalize the following character), with a class-definition-time collision
  check and an explicit `Field(name="...")` override for irregular cases.
  Ingested descriptors keep canonical names in the metamodel; the ambiguous
  camel→snake direction is never needed because classes are not generated.
  Reserved class-level names (`where`, other query-root classmethods, the
  `model_*` Pydantic space) may not be field names; collisions are rejected at
  class definition.
- **Runtime introspection API.** `parallax.core.meta(Order)` (or by name,
  `meta("Order")`) returns a frozen `EntityMeta` view over the metamodel:
  `name`, `table`, `temporal`, `attributes` (type, column, nullable,
  primary_key, pk generator, max length), `primary_key`, `as_of` (axis →
  from/to columns), `relationships` (cardinality, related entity, join,
  order-by, dependent), `value_objects`, `family` (inheritance root, strategy,
  tag/tagValue, subtypes; `None` outside a family), and `descriptor()` for the
  canonical dict/YAML/JSON export. Keys use canonical camelCase names. The
  same object is returned whether the metamodel came from classes or ingested
  YAML.
- **Neutral scalar type mapping.** No lossy coercions; validation at build
  time; the database never sees an invalid value.

  | Neutral | Python read type | Input policy | Bind/materialization |
  |---|---|---|---|
  | `boolean` | `bool` | `bool` only | driver bool |
  | `int32` / `int64` | `int` | `int`, range-validated (±2³¹ / ±2⁶³); `bool` rejected | driver int |
  | `float32` / `float64` | `float` | `float`; `int` accepted (lossless); NaN/inf rejected | driver float |
  | `string` | `str` | `str`; `maxLength` enforced at build | driver text |
  | `bytes` | `bytes` | `bytes` | driver bytea via dialect bind seam |
  | `decimal(p,s)` | `decimal.Decimal` | `Decimal` or `int`; `float` rejected; precision/scale validated | driver numeric → `Decimal` on read |
  | `date` / `time` | `datetime.date` / `datetime.time` | wall-clock; `time` with `tzinfo` rejected | driver date/time, no instant semantics |
  | `timestamp` | tz-aware `datetime` | naive rejected; normalized UTC; microseconds | `timestamptz`; aware UTC on read |
  | `uuid` | `uuid.UUID` | `UUID` or canonical string | driver uuid |
  | `json` (value object) | nested frozen value-object class | the VO class instance; never a raw dict | structured column per dialect |

- **Metamodel serde ownership.** Source owner `parallax.core.descriptor`
  (enforcement scope of the same name), shipped in the `parallax-core`
  artifact. JSON and YAML round-trip tests run in the unit lane
  (`uv run pytest -m unit`), and every corpus descriptor must parse,
  round-trip deterministically, and re-export equal to its canonical form.

### Code generation or runtime realization

- **Realization technique.** No code generation. The typed finder and object
  surface is realized at class-definition time by the Parallax metaclass and
  typed descriptors over user-authored Pydantic classes (class-level attribute
  access yields typed expression objects; instances are frozen plain values).
  Rationale: single source of truth in user code, no generated-file lifecycle,
  strict-Pyright-friendly via descriptor `__get__` overloads.
- **Drift prevention without codegen.** The API Conformance Suite's
  descriptor-equality guard (idiomatic class exports ≡ corpus descriptor) and
  the operation no-drift guard (idiomatic statement serialization ≡ corpus
  operation) are the drift gates; both run in CI.
- **Derivable typed artifacts.** None are generated. The spec deliberately
  promises no generated surface; everything typed is derived at runtime from
  the class declarations, which carry no information absent from the
  descriptor schema.

## 3. Object lifecycle profile

### Snapshot lifecycle

- **Public result and node types.** `db.find(op)` executes exactly once,
  materializes fully, and returns `Snapshot[T]` — the Python reification of a
  core Snapshot Graph. Nodes are **frozen instances of the user's own entity
  classes** (plain values: hashable, shareable, serializable). `Snapshot[T]`'s
  complete surface: `result()`, `result_or_none()`, `results()` (a fresh
  `list[T]` per call), `pin` (the lowered as-of coordinates), `execution`
  (per-statement `sql`, `binds`, informational `duration`, and `round_trips`,
  mirroring the adapter emission convention), and `__repr__`. Deliberately
  absent: iteration/len/truthiness/indexing on the container, refresh or
  write methods, and any lazy behavior. Accessors are pure in-memory reads.
- **Graph-local identity.** Within one materialized graph, one node per
  `(entity family, primary key, lowered as-of coordinates)` key: diamond paths
  share the same node object, cycles/back-references are hard pointers
  (constructed via an implementation-private setattr backdoor during
  materialization), and projections targeting the same key merge into one
  node. Value objects have no identity (fresh values per owner). Identity
  never escapes one graph: nodes from different `find` calls never coalesce.
- **Whole-graph temporal pinning.** The statement's `as_of` coordinates (with
  latest defaults per axis) pin the whole graph; the pin propagates per hop,
  matched by axis, to every temporal entity in the include tree — auto
  injected, never user-written. `history` / `as_of_range` return one root per
  milestone, each root **edge-pinned** at its milestone's from-instant;
  `snapshot.pin` reports only genuinely pinned axes (a scanned axis is absent,
  per the core rule that a scan is not a pin), and `parallax.core.pin_of(node)`
  reports each node's own coordinates. The `snapshot-history-includes` feature
  is **deferred, not invalid**: combining `.history()` with `.include()`
  raises `UnsupportedFeatureError` naming the deferral, distinct from
  validation errors.
- **Closed-world relationships.** An included to-one is the related node or
  `None` (loaded-null); an included to-many is a `list` (possibly empty —
  loaded-empty). A relationship outside the include set is **unloaded**:
  attribute access raises `UnloadedRelationshipError` naming the path and the
  include fix, and `parallax.core.is_loaded(node, "items")` answers without
  raising. Access never issues SQL — there is no lazy loading in this
  lifecycle.
- **Eager include execution.** One query per non-empty relationship level
  (semi-join against the parent level's keys); an empty level short-circuits
  its subtree; declared descriptor `orderBy` governs child ordering; narrowed
  relationship views load exactly the requested narrowed set keyed by
  relationship name and effective concrete-subtype set; the `1 + L` round-trip
  ceiling holds and is observable via `snapshot.execution.round_trips`.
- **Explicit writes.** All writes go through the Parallax Transaction
  (§5) — the handle has no write methods. Graph edits are impossible (nodes
  are frozen); the only mutation idiom is deriving an **edited copy**:
  the Parallax base class overrides `model_copy` so a copy of a node carries
  an accumulated changed-field record (copy-of-copy unions). Nodes carry no
  change tracking; the derived copy's change record is an explicit write
  input, and there is no merge-back (no re-association, no returned managed
  object). Write inputs are the entity classes themselves: full instances for
  `insert` (the Create Payload), edited copies or instances for the other
  verbs (§5). The stale-web-edit pattern (fetch `as_of` the original display
  instant inside an optimistic transaction, apply payload fields to a copy,
  update — a concurrent writer's chain fails the observed-`in_z` gate) is the
  documented idiom for offline-edit conflict detection and requires no
  detached objects.

## 4. Result collections and materialization

### Snapshot results

- **Eager materialized collections.** Query construction is side-effect-free;
  execution happens exactly at `db.find(op)` and returns a value. Roots are
  reached only through `Snapshot[T]`'s three accessors; `results()` returns a
  real built-in `list[T]` the caller owns (fresh copy per call). Included
  to-many relationships are plain `list` fields on frozen nodes. Nothing is an
  `m-op-list` operation-backed lazy list; iteration, indexing, and bulk
  operations are ordinary Python on ordinary lists.
- **Result-shape appearances.** Root-empty: `results() == []`, `result()`
  raises `NoResultFound`, `result_or_none()` is `None`. Relationship-empty:
  `[]`. Relationship-null (to-one): `None`. Unloaded: raising access as in §3.
  Ordered children: descriptor `orderBy` order. Shared prefixes: one query per
  level regardless of how many include paths share it. Graph-local shared
  identity: diamond paths yield the *same* node object (`is`-identical), which
  is also how identity expectations are observed by scenario cases.

## 5. Transactions and writes

- **Demarcation construct.** Callback-only:
  `db.transact(fn, *, retries=10, concurrency="locking", retry_optimistic_conflicts=False)`.
  The closure receives the Parallax Transaction (`def fn(tx): ...`),
  `tx.find(op)` reads inside the transaction (participating per the selected
  mode), and the callback's return value is returned **only after a durable
  commit** — on rollback, or on commit failure, the call raises instead of
  returning the value as though durable. A `with`-block demarcation is
  deliberately not offered: the core retry contract requires re-executing the
  closure, which a `with` block cannot do; a decorator form is a possible
  additive future. Bounded automatic retry follows core: deadlock-category
  failures retriable by default, bound default 10, `retries=0` disables the
  loop, exhaustion surfaces diagnosably with the attempt count;
  optimistic-lock conflicts join the retriable set only via
  `retry_optimistic_conflicts=True`.
- **Nesting, ownership, and participation mode.** Transactions do not nest:
  calling `db.transact` from inside a transaction body raises (re-entrancy is
  a deferred design question, not silent nesting). A transaction object is
  owned by its closure invocation and is not thread-safe; escaping references
  raise on use after the scope ends. The per-transaction participation mode is
  `locking` (default — in-transaction reads take the dialect's shared read
  lock) or `optimistic` (no read locks; keyed writes gate on the observed
  version analogue). Connections open at the database's default isolation
  (READ COMMITTED); no isolation knob is exposed.
- **Buffering, flush, and read-your-own-writes.** Writes buffer in the unit of
  work and flush at commit, combined and batched per `m-batch-write` (multi-row
  INSERT collapse, per-key UPDATE batching, IN-list DELETE collapse) and
  ordered to respect foreign keys (parents inserted before children, deleted
  after). A read that depends on a buffered write forces a flush inside the
  still-open atomic scope first (read-your-own-writes); aborts discard
  buffered, force-flushed, and cached effects alike. No public explicit
  `flush()` control is offered in v1.
- **Write verbs and temporal spellings.** Verb names: `insert`, `update`,
  `delete` (non-temporal), `terminate` (temporal), and the bitemporal
  `insert_until`, `update_until`, `terminate_until`. Inputs are entity
  instances and edited copies, lowering to the canonical row-shaped write
  inputs: `insert` takes a full instance; non-temporal `update` takes an
  edited copy and emits the sparse row (primary key + changed fields from the
  copy's change record; a provenance-less instance raises, and changing a PK
  field raises); temporal `update` takes an edited copy or instance and emits
  the full row (close-and-chain); `delete`/`terminate` take a node or
  instance and key off it. Bitemporal plain verbs require keyword-only
  `business_from`; the `*_until` trio additionally requires `until`, with
  `business_from < until`, both aware-UTC-microsecond datetimes, all validated
  at build. `delete` on a temporal entity and `terminate` on a non-temporal
  entity are rejected. Processing instants come from the handle-configured
  **Clock Strategy** (default system UTC; tests inject a fixed clock) — never
  from callers, with no per-operation overrides. Temporal `update`/`terminate`
  read-before-write inside the transaction, sourcing the chained row's
  unchanged values and, under optimistic mode, the observed `in_z` for the
  gated close (with the business discriminator when current rows share an
  `in_z`, per `m-bitemp-write`).

## 6. Database support and compatibility proof

### Database provider integration

- **Test runner and discovery.** pytest. A conformance-runner module loads
  `core/compatibility/cases/**`, applies the §1 case-selection expression
  (claim filters exactly as `m-conformance-adapter` defines them), and
  parametrizes pytest over the result; milestone runs intersect with
  `--parallax-tags`. Filename prefixes are never used for selection.
- **Provisioning.** testcontainers-python, `self-managed` per the claim. The
  Postgres image is pinned to an exact version **and** sha256 digest in one
  constants module; bumps are reviewed diffs. Testcontainers and all container
  tooling live in development-only dependency groups and are proven absent
  from production artifacts by the §8 clean-install checks.
- **Reset lifecycle.** One container per test session; per-case isolation via
  `DROP SCHEMA … CASCADE` + `CREATE SCHEMA`, then ordered DDL derived from the
  case's descriptor (`applyDdl`), then fixture rows in descriptor column order
  (`loadFixtures`). No snapshot/template-database optimization in v1 — the
  simple path is the only path (recorded as a deferred optimization), so no
  provider snapshot API or fallback needs naming.
- **Golden SQL selection.** The `postgres` key of each statement entry; every
  claimed case carries it (guaranteed by the claim's dialect filter). A
  missing key is a hard error, never a silent skip.
- **Docker-free dialect contract suite.** Table-driven pytest with one row per
  database (one row today: postgres) covering the `m-dialect` catalog:
  identifier quoting (reserved and non-simple), neutral NULL ordering per
  direction, row-limit rendering, shared read-lock application and omission,
  neutral-scalar column-type mapping (parametric decimals, bounded strings),
  bytes projection shape and projection-introduced binds, temporal-infinity
  bind representation, placeholder translation (canonical `?` → psycopg `%s`),
  typed bind normalization, precision-sensitive value parsing, and native
  error-code classification predicates. Runs in `uv run pytest -m dialect`
  with no Docker and no driver I/O.
- **Adapter smoke and provider contract suites.** The psycopg adapter smoke
  suite covers construction from documented connection configuration, a
  managed scalar read returning adapter-boundary values (e.g. `Decimal`),
  a transaction callback that commits and returns its value, a bytes write
  round trip through the dialect bind seam, affected-row semantics for matched
  and unmatched DML, and a **real transient classification proof** (two
  crossed-update connections via `peer` provoke a genuine `40P01` deadlock).
  The provider contract suite exercises `reset`, `applyDdl`, `loadFixtures`,
  `query`, `exec`, `execRolledBack`, and `peer` against the container.
- **Matrix profiles.** Two named profiles, both **full**: `pg-full` (every
  claimed case, `run`, postgres, expected count derived from the corpus at
  runtime — never hard-coded) and `compile-sweep` (every claimed case,
  `compile`, Docker-free, emissions and binds vs golden plus normalization).
  No partial profiles exist; MariaDB is a §1 deferral, not a profile
  exclusion.
- **Commands and skip reporting.** Markers: `unit`, `dialect`,
  `compile_sweep`, `adapter_smoke`, `provider_contract`, `conformance`,
  `api_conformance`, `artifact`, `clean_install`, `api_surface`; run via `uv`
  and aggregated by the `languages/python` justfile (`just python-static`,
  `just python-verify`). Database-backed markers skip only when Docker is
  unavailable; a session-scoped fixture prints a final summary naming every
  skipped database-backed check and its reason, and the CI database lane fails
  on any skip — silent skips are structurally impossible.
- **Database Error mapping.** At the port boundary every driver exception is
  re-raised as a Parallax Error carrying the neutral `m-db-error` category,
  the preserved native SQLSTATE, and the driver message; driver exception
  types never cross above the port. The SQLSTATE→category table (`40P01`,
  `40001` → deadlock; `55P03` → lock-wait timeout; `23505` → unique violation;
  …) lives in the pure dialect strategy where the Docker-free contract suite
  tests it.

### API Conformance Suite and Usage Guide

- **Framework and location.** pytest (`-m api_conformance`) under
  `languages/python/tests/api_conformance/`, executing idiomatic public-API
  code through the shipped `parallax-snapshot` extension and
  `parallax-postgres` adapter against the real Testcontainers Postgres.
- **Coverage partition and no-drift guards.** An assertion computes
  `exercised ∪ reasoned-skipped == active slice` from corpus data at runtime,
  failing on stale case IDs or empty skip reasons. Two no-drift guards run per
  example: the idiomatic statement's serialization equals the corpus
  operation, and idiomatic class descriptors equal corpus descriptors.
- **Usage Guide.** Generated from suite source (`uv run gen-usage-guide`) into
  `languages/python/docs/usage-guide.md`; CI runs `--check` and fails on
  drift. The guide and suite are additive to conformance-adapter proof, never
  substitutes.

## 7. Source-enforcement topology

Behavioral modules map one-to-one onto Python submodules (enforcement scopes)
inside the distributions of §8. import-linter enforces every DAG direction
between scopes; artifact co-location never legalizes a forbidden edge.

| Behavioral/support module | Source owner/path | Enforcement scope | Allowed direct dependencies | Enforcement rule/config |
|---|---|---|---|---|
| `m-core` | `parallax.core.base` | `parallax.core.base` | (none) | import-linter layers, `languages/python/pyproject.toml` |
| `m-descriptor` | `parallax.core.descriptor` | `parallax.core.descriptor` | `m-core` | import-linter layers |
| `m-pk-gen` | `parallax.core.pk_gen` | `parallax.core.pk_gen` | `m-descriptor` | import-linter layers |
| `m-inheritance` | `parallax.core.inheritance` | `parallax.core.inheritance` | `m-descriptor` | import-linter layers |
| `m-value-object` | `parallax.core.value_object` | `parallax.core.value_object` | `m-descriptor` | import-linter layers |
| `m-op-algebra` | `parallax.core.op_algebra` | `parallax.core.op_algebra` | `m-descriptor`, `m-inheritance` | import-linter layers |
| `m-sql` | `parallax.core.sql_gen` | `parallax.core.sql_gen` | `m-op-algebra`, `m-dialect` | import-linter layers |
| `m-dialect` | `parallax.core.dialect` (incl. driver-free `dialect.postgres`) | `parallax.core.dialect` | `m-core` | import-linter layers |
| `m-db-port` | `parallax.core.db_port` (abstract) | `parallax.core.db_port` | `m-core` | import-linter layers |
| `m-db-error` | `parallax.core.db_error` | `parallax.core.db_error` | `m-db-port`, `m-dialect` | import-linter layers |
| `m-unit-work` | `parallax.core.unit_work` | `parallax.core.unit_work` | `m-op-algebra`, `m-db-port` | import-linter layers |
| `m-read-lock` | `parallax.core.read_lock` | `parallax.core.read_lock` | `m-unit-work`, `m-dialect` | import-linter layers |
| `m-auto-retry` | `parallax.core.auto_retry` | `parallax.core.auto_retry` | `m-unit-work`, `m-db-error` | import-linter layers |
| `m-opt-lock` | `parallax.core.opt_lock` | `parallax.core.opt_lock` | `m-unit-work`, `m-temporal-read` | import-linter layers |
| `m-temporal-read` | `parallax.core.temporal_read` | `parallax.core.temporal_read` | `m-op-algebra` | import-linter layers |
| `m-audit-write` | `parallax.core.audit_write` | `parallax.core.audit_write` | `m-temporal-read`, `m-unit-work` | import-linter layers |
| `m-bitemp-write` | `parallax.core.bitemp_write` | `parallax.core.bitemp_write` | `m-audit-write` | import-linter layers |
| `m-batch-write` | `parallax.core.batch_write` | `parallax.core.batch_write` | `m-unit-work` | import-linter layers |
| `m-op-list` (unclaimed prerequisite, internal) | `parallax.core.op_list` (unexported) | `parallax.core.op_list` | `m-op-algebra`, `m-unit-work` | import-linter layers + private-module convention |
| `m-navigate` | `parallax.core.navigate` | `parallax.core.navigate` | `m-op-list`, `m-unit-work`, `m-temporal-read`, `m-inheritance` | import-linter layers |
| `m-deep-fetch` | `parallax.core.deep_fetch` | `parallax.core.deep_fetch` | `m-navigate`, `m-op-list` | import-linter layers |
| `m-snapshot-read` | `parallax.snapshot.materialize` + `parallax.snapshot.handle` | `parallax.snapshot` | `m-deep-fetch` (and transitively below) | import-linter cross-package contract |
| `m-case-format` | `parallax.conformance.case_format` (dev-only) | `parallax.conformance.case_format` | `m-core` | import-linter layers (dev tree) |
| `m-conformance-adapter` | `parallax.conformance.cli` (dev-only) | `parallax.conformance.cli` | `m-case-format` (harnesses any behavioral module) | import-linter layers (dev tree) |
| `m-api-conformance` | `languages/python/tests/api_conformance` (dev-only) | `tests.api_conformance` | `m-case-format` (harnesses the public surface) | pytest collection boundary |
| Entity and statement frontend (support) | `parallax.core.entity` | `parallax.core.entity` | `m-descriptor`, `m-op-algebra`, `m-temporal-read` | import-linter layers |
| Concrete Postgres adapter (support) | `parallax.postgres.adapter` | `parallax.postgres` | `m-db-port`, `m-db-error`, `m-dialect`, psycopg | import-linter cross-package contract |
| Composition root (support) | application/test code calling `parallax.snapshot.connect` | (application-owned) | `parallax.snapshot`, `parallax.postgres` | only the root imports a concrete adapter |

- **Dependency-analysis tool.** import-linter; configuration in
  `languages/python/pyproject.toml` (`[tool.importlinter]`) plus the
  drift-check script `languages/python/tools/check_dag_sync.py`, which parses
  the fenced `dependency-graph` block in `core/spec/modules.md` and asserts
  the contract set covers exactly those edges. Local: `uv run lint-imports &&
  uv run python tools/check_dag_sync.py`. CI: the same pair as a blocking job;
  any wrong-direction import or contract/DAG drift fails.
- **Scopes sharing one artifact.** Every behavioral module in `parallax-core`
  is its own submodule; import-linter's layer contracts operate at submodule
  granularity, so co-location in one wheel cannot legalize a forbidden edge.
  Cross-package contracts forbid `core → snapshot`, `core → postgres`, and
  `snapshot → postgres` in both metadata and imports.
- **Database seam scopes.** Pure dialect strategy in `parallax.core.dialect`
  (driver-free), abstract port in `parallax.core.db_port`, error
  classification in `parallax.core.db_error`, the concrete adapter in
  `parallax.postgres`, and the composition root in application/test code. Only
  the composition root imports the concrete adapter; the port imports nothing
  application-specific.

## 8. Deployable artifact topology

uv workspace under `languages/python/`; PEP 420 namespace `parallax.*` shared
by separately installable distributions (the dormant PyPI `parallax` SSH tool
would collide only if co-installed; documented, accepted). Build backend:
hatchling.

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| `parallax-core` (the common runtime) | production | all `parallax.core.*` scopes of §7 (behavioral modules, entity/statement frontend, driver-free postgres dialect strategy, internal `op_list`) | `pydantic`, `pyyaml` | (none) | `parallax.core`: entity base, `Field`, statement API, `LATEST`, `Pin`, `meta`, `pin_of`, `is_loaded`, errors |
| `parallax-snapshot` (snapshot lifecycle extension) | production | `parallax.snapshot.*` (`materialize`, `handle`) | (none beyond core) | `parallax-core` | `parallax.snapshot`: `connect()`, `Snapshot[T]`, `Execution` |
| `parallax-postgres` (Postgres database adapter) | production | `parallax.postgres.*` (concrete port over psycopg) | `psycopg` (sole declarer) | `parallax-core` | `parallax.postgres`: `PostgresAdapter` |
| `parallax-conformance` | development-only | `parallax.conformance.*` (CLI, case format, corpus loading, provider harness) | `testcontainers`, `jsonschema` | `parallax-core`, `parallax-snapshot`, `parallax-postgres` | `parallax-conformance` console script (`describe` / `compile` / `run`) |

- **Common runtime manifest proof.** `parallax-core`'s manifest declares only
  `pydantic` and `pyyaml`; the clean-install check installs it alone and
  proves `psycopg`, `parallax.snapshot`, testcontainers, and conformance
  modules are absent from both the installed distribution list and the import
  space.
- **Lifecycle extension manifest proof.** `parallax-snapshot` depends only on
  `parallax-core`; the clean-install check proves no sibling lifecycle
  artifact exists in the graph and no concrete driver is present.
- **Adapter manifest proof.** `parallax-postgres` alone declares `psycopg`;
  the driver-free dialect strategy ships inside `parallax-core`
  (explicitly permitted by core), keeping `compile` Docker- and driver-free.
- **Composition root.** Application/test code constructs the adapter and calls
  `parallax.snapshot.connect(adapter=...)`; neither dependency leaks into
  common-runtime code, and no umbrella artifact exists.
- **Clean-install and runtime-load checks.** Three uv-venv fixtures
  (`uv run pytest -m clean_install`): core alone; core + snapshot; core +
  snapshot + postgres. Each inspects installed distributions and import-probes
  to prove unselected lifecycles, adapters, drivers, conformance harnesses,
  benchmarks, and container tooling are absent from the installed and loaded
  production graph.

## 9. Conditional capability decisions

No conditional capability is claimed: process caches, cross-process coherence,
aggregation, additional dialects, and benchmarks are all outside
`slice-snapshot-1` and recorded as deferred in §1, so every conditional
subsection of the template is deleted from this completed spec.

## 10. Mandatory quality toolchain

| Quality concern | Tool and version policy | Configuration path(s) | Local command | Blocking CI command/job | Threshold, exclusions, and enforcement policy |
|---|---|---|---|---|---|
| Dependency directions within and across artifacts | import-linter (pinned in `uv.lock`) + `check_dag_sync.py` | `languages/python/pyproject.toml` `[tool.importlinter]`; `languages/python/tools/check_dag_sync.py` | `uv run lint-imports && uv run python tools/check_dag_sync.py` | `python-static` job, same commands | any wrong-direction edge fails; contract set must equal the `modules.md` DAG (drift fails) |
| Unit tests | pytest (pinned) | `languages/python/pyproject.toml` `[tool.pytest.ini_options]` | `uv run pytest -m unit` | `python-static` job | unit = no container/socket I/O; any failure blocks |
| Code coverage | coverage.py via pytest-cov, branch mode | `[tool.coverage]` in `languages/python/pyproject.toml` | `uv run pytest -m unit --cov --cov-branch` | `python-static` job with `--cov-fail-under=90` | **90% branch minimum**; no generated/vendor code exists to exclude; conformance CLI included; new code may not lower the total |
| Linting | ruff (pinned) | `[tool.ruff]` in `languages/python/pyproject.toml` | `uv run ruff check` | `python-static` job | rule sets E, F, W, I, UP, B, SIM, RUF; `# noqa` requires rule code + one-line justification |
| Deterministic formatter check | ruff format (pinned) | `[tool.ruff.format]` | check: `uv run ruff format --check`; write: `uv run ruff format` | `python-static` job (`--check` only) | CI checks without rewriting |
| Strict static typing | Pyright, strict mode, pinned version | `languages/python/pyrightconfig.json` | `uv run pyright` | `python-static` job | strict across production and tests; zero suppressions at spec time — any future suppression is listed and justified here |
| Import-cycle detection | import-linter layer contracts | `[tool.importlinter]` | `uv run lint-imports` | `python-static` job | covers all production source scopes; any cycle fails |
| Dead code and unused exports | vulture + griffe public-API snapshot test | `[tool.vulture]`; `languages/python/tests/api_surface/` | `uv run vulture && uv run pytest -m api_surface` | `python-static` job | limitation recorded: Python tooling cannot prove an export unused; compensating check is the API-surface snapshot diff, making every public-surface change a reviewed diff |
| Built-artifact and public-export health | `uv build` + twine check + wheel-content pytest | `languages/python/tests/artifact/` | `uv build && uv run twine check dist/* && uv run pytest -m artifact` | `python-static` job | wheels contain no tests/conformance modules, include `py.typed`, declare correct entry points |
| Clean-install production smoke tests | uv-venv fixtures | `languages/python/tests/clean_install/` | `uv run pytest -m clean_install` | `python-static` job | exercises all three §8 selective topologies in clean environments; presence of any unselected artifact fails |
| Supported language/runtime versions | CPython; `requires-python >= 3.12` | each distribution's `pyproject.toml` | (local dev on any supported minor) | CI matrix 3.12 / 3.13 / 3.14 | support current + two prior minors; drop on upstream EOL; floor raises are reviewed spec changes |
| Dependency and supply-chain audit | committed `uv.lock` + `uv lock --check` + pip-audit | `languages/python/uv.lock` | `uv lock --check && uv run pip-audit` | `python-static` job | high-severity findings block; exceptions carry owner + expiry inline; lockfile drift fails |
| Compatibility Conformance Suite | pytest conformance runner + jsonschema envelope validation | `languages/python/tests/conformance/` | `uv run pytest -m compile_sweep` (Docker-free) and `uv run pytest -m conformance` (`pg-full`) | `python-static` (compile sweep) + `python-database` (run sweep) | selection = active slice ∩ capability tags; every envelope validates against `conformance-adapter.schema.json` |
| API Conformance Suite and Usage Guide | pytest + guide generator | `languages/python/tests/api_conformance/`; `languages/python/docs/usage-guide.md` | `uv run pytest -m api_conformance && uv run gen-usage-guide --check` | `python-database` job | coverage partition exact (exercised ∪ reasoned-skips = slice; no stale IDs, no empty reasons); operation and descriptor no-drift guards green; guide drift fails |
| Database-backed verification | testcontainers Postgres profiles | §6 profile definitions | `uv run pytest -m "conformance or provider_contract or adapter_smoke"` | `python-database` job | required profiles `pg-full`, provider contract, adapter smoke; every skipped check is reported with a reason in the session summary; silent skips are forbidden and any CI skip fails |

- **Aggregate static-verification command.** `just python-static` — one local
  command and one blocking CI job running every database-free row above
  (imports/DAG, unit + coverage, ruff check + format check, Pyright strict,
  vulture + API surface, artifact + clean-install checks, supply-chain audit,
  and the Docker-free `compile-sweep`).
- **Aggregate full verification command.** `just python-verify` — static plus
  every database-backed row (`pg-full`, provider contract, adapter smoke, API
  conformance + Usage Guide drift), ending with a summary block listing every
  check as run, failed, or skipped-with-reason.

## Completion check

- No decide-and-record markers or blank required table cells remain.
- Exactly one §3 lifecycle profile (snapshot) and its matching §4 result
  branch are retained; all managed-object instructions are removed.
- `slice-snapshot-1` exists in `slices.md`, is lifecycle-complete, and the §1
  envelope equals its canonical claim except for the `adapter` identity.
- Claimed coverage is the canonical tagged-case union; the two transitive
  unclaimed prerequisites and every explicit deferral are listed separately.
- No conditional section's applicability condition is true, and none is
  present.
- The §7 map covers all claimed modules, both prerequisites, and the support
  scopes, and is mechanically enforceable via import-linter plus the DAG
  drift check.
- The §8 map contains an independent common runtime, exactly the snapshot
  lifecycle extension, a separate Postgres adapter, and a development-only
  tooling artifact, with manifest and selective clean-install proofs.
- Every §10 row names a tool, configuration, local command, blocking CI
  command, and enforcement policy; coverage has a numeric threshold, typing is
  strict, and database skips cannot be silent.
