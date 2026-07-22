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
| Claimed capability coverage | Copied verbatim from the canonical claim: the 26 `modules` below, `dialects: ["postgres"]`, the eight `caseShapes`, `caseTags.include: ["slice-snapshot-1"]`, `commands: ["describe", "compile", "run"]`, `provisioning: "self-managed"`. `modules` is the tagged-case union of the slice, **not** a dependency closure and not a packaging plan. |
| Unclaimed implementation prerequisites | `m-db-port` — reached via `m-unit-work` and `m-db-error`; abstract port supplied by the `parallax.core.db_port` scope, concrete adapter by `parallax-postgres`; contract-covered, never case-advertised. |
| Deferred capabilities | MariaDB (dialect); `benchmark` command and `m-perf-bench`; `m-agg` / `m-sql-agg`; Valid-Time-Only models; `m-process-cache` / `m-coherence`; `m-cascade-delete`; the `snapshot-history-includes` feature; the managed-object lifecycle (`m-identity-map`, `m-detach`, public operation-backed lists); an async developer surface; MAY-tier mutations (`insertWithIncrement`, `incrementUntil`, `purge`, `inactivateForArchiving`); template-database reset optimization; isolation-level configuration; handle-level default concurrency override; statement `where`-refinement chaining and `as_of` re-pinning. Deferral is roadmap intent; **unsupported classification** is the adapter's wire behavior for out-of-claim requests — the two are recorded separately and never conflated. |
| Supported dialects and commands | Postgres only; `describe`, `compile`, `run`. Exercised locally and in CI by `uv run pytest -m compile_sweep` (Docker-free compile of every compile-eligible claimed case) and `uv run pytest -m conformance` (the `pg-full` run profile, every claimed case), aggregated by `just python-static` and `just python-verify`. |

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "python", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-audit-write", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-dialect", "m-inheritance", "m-metamodel", "m-model-formation", "m-navigate", "m-op-algebra", "m-opt-lock", "m-pk-gen", "m-read-lock", "m-relationship", "m-snapshot-read", "m-sql", "m-temporal-read", "m-unit-work", "m-value-object"],
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

### Temporal vocabulary and configuration

Python exposes no public `AsOfAxis` declaration type. Authors select exactly
one framework Entity base:

- `TransactionTimeOnly`, which supplies read-only `tx_start`/`tx_end`
  Attributes mapped to `in_z`/`out_z`; or
- `Bitemporal`, which additionally supplies read-only
  `valid_start`/`valid_end` Attributes mapped to `from_z`/`thru_z`.

The normalized Metamodel still exposes `AsOfAxisMetadata` through the core
interface, keyed by `TemporalDimension`. This leaves a future additive seam for
advanced column overrides without making ordinary Python authors repeat
Attributes, Timestamp types, flags, interval semantics, or columns.

| Python surface | Valid Time | Transaction Time |
|---|---|---|
| Framework base | supplied by `Bitemporal` | supplied by `TransactionTimeOnly` and `Bitemporal` |
| Metadata dimension | `TemporalDimension.ValidTime` | `TemporalDimension.TransactionTime` |
| Query keyword | `valid_time` | `transaction_time` |
| `history` dimension literal | `"valid_time"` | `"transaction_time"` |
| `Pin` accessor | `valid_time` | `transaction_time` |
| `Edge` accessor | `valid_time` | `transaction_time` |
| Conventional Attributes | `valid_start`, `valid_end` | `tx_start`, `tx_end` |
| Physical columns | `from_z`, `thru_z` | `in_z`, `out_z` |
| Bitemporal mutation input | `valid_from`; bounded verbs also use `until` | finite clock instant supplied by the Database handle |
| Optimistic temporal observation | not used as a gate | observed `tx_start` (`in_z`) |

Relationship traversal propagates Pin and Edge coordinates by Temporal
Dimension using these same names. The former business/processing vocabulary is
not accepted as aliases in declarations, metadata, queries, Pin/Edge values,
mutations, exceptions, or exports.

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
  Because expressions reject `__bool__`, a boolean attribute cannot be used as
  a bare truthy predicate, and the `== True` spelling trips Ruff `E712` under
  the mandatory §10 lint policy — so boolean attribute expressions additionally
  offer `.is_(True)` / `.is_(False)`, a **spelling redundancy** that serializes
  to the identical canonical `eq` node as the operator form (one canonical
  representation, two spellings that cannot drift). The `==` spelling remains
  legal in user code; documented examples and the generated Usage Guide use the
  lint-clean `.is_()` form throughout.
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
- **Value-object predicates.** Nested value-object paths reuse chained
  class-level attribute access: `Customer.address.city == "Berlin"` builds the
  flat `nestedEq` node carrying the dotted canonical path
  (`nestedEq: { path: Customer.address.city, value: Berlin }`). The scalar
  operator surface maps one-to-one onto the flat `nested*` family —
  `==` / `!=` / `>` / `>=` / `<` / `<=` / `.in_(...)` serialize to `nestedEq` /
  `nestedNotEq` / `nestedGt` / `nestedGte` / `nestedLt` / `nestedLte` /
  `nestedIn`, and `.is_null()` / `.is_not_null()` to `nestedIsNull` /
  `nestedIsNotNull` (core's absence-collapse semantics). The first hop is
  statically typed via the `Attr[...]` descriptor overloads; deeper hops
  resolve dynamically and are validated at statement build against the
  declared value-object structure — an undeclared segment or a literal
  mismatching the leaf's declared neutral type is rejected at build, never at
  the database. A flat predicate whose path crosses a `multiplicity: many`
  member keeps the flat node and therefore core's **any-element** semantics:
  each such predicate matches independently, so two ANDed flat predicates may
  be satisfied by *different* elements. **Same-element** composition and
  member-presence tests hang off the value-object-terminated path:
  `.any(*predicates)` serializes to `nestedExists { path, where }` and
  `.none(*predicates)` to `nestedNotExists { path, where }`; zero arguments
  emit the bare presence/non-empty (`nestedExists`) or absent/empty
  (`nestedNotExists`) node with no `where`. Variadic arguments conjoin exactly
  like `where(*predicates)`; inside the scope, sub-predicates are built from
  the value-object class's own class-level attributes and serialize as
  **element-relative** paths (`type`, `geo.country` — no leading entity
  prefix), composing with `&`/`|`/`~` and parentheses. An element-scoped
  expression is valid only inside an `.any(...)`/`.none(...)` over that
  element type; a stray one is rejected at statement build.

  ```python
  Customer.where(
      Customer.address.phones.any(
          Phone.type == "home",
          Phone.number == "555-9999",
      )
  )
  ```

- **Deep-fetch/include spelling.** Chained attribute paths on the statement:
  `Order.where(...).include(Order.items.statuses, Order.tags)`. One path
  grammar shared with predicates; longer paths imply their intermediates
  (glossary Include Path). The first hop is statically typed via descriptor
  `__get__` overloads; deeper hops resolve dynamically and are validated
  against the metamodel at statement-build time — never at execution and never
  at the database.
- **Subtype narrowing.** The canonical `narrow` node is spelled with the
  class-level constructor `Entity.narrow(*subtypes, where=...)` on the
  polymorphic position's class, serializing to
  `narrow: { entity, to, operand }` — `entity` is the position, `to` preserves
  the authored subtype list verbatim (each entry a concrete or abstract
  subtype class), and `operand` is the `where=` expression (omitted ⇒ `all`).
  Inside `where=`, subtype-declared attributes become predicable
  (`Animal.narrow(Dog, where=Dog.bark_volume > 3)`); referencing one outside a
  compatible narrow scope is rejected at statement build
  (`subtype-attribute-outside-narrow-scope`). A narrow expression is an
  ordinary predicate, so separately narrowed branches compose with the
  Boolean operators:

  ```python
  Animal.where(
      Animal.narrow(Dog, where=Dog.bark_volume > 5)
      | Animal.narrow(Cat, where=Cat.indoor.is_(True))
  )
  ```

  serializes to `or` over two `narrow` nodes, branch order preserved. Inside a
  relationship quantifier the constructor must be called on exactly the
  relationship target (`Person.pets.any(Pet.narrow(Cat))` — `m-navigate`'s
  exact-naming rule, checked at build). The statement-level clause
  `Animal.where(...).narrow(Dog, ...)` is the whole-statement form: it wraps
  the statement's conjoined predicate as the single top-level `narrow` node's
  operand (zero predicates ⇒ `all`) and is single-shot like `as_of`. It is a
  **pure result-set narrowing** that grants no attribute scope to the
  already-built `where` arguments: every predicate is validated immediately as
  it is built, so subtype-declared attributes are predicable **only** inside
  the scoped constructor's `where=` —
  `Animal.where(Dog.bark_volume > 3).narrow(Dog)` is rejected the moment the
  first predicate is built
  (`subtype-attribute-outside-narrow-scope`), and the valid spelling is
  `Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3))`. The clause
  and the constructor converge on the identical canonical node, so neither
  spelling can drift. On an include path, `.narrow(*subtypes)` on a hop
  (`Owner.pets.narrow(Dog)`, continuable to deeper hops) serializes to the
  path segment's `narrow: { to: [...] }` and requests a distinct **narrowed
  view** (§3). Everywhere, the resolved set must stay within the **enclosing
  effective concrete-subtype set** — the threaded active position, re-narrowed
  at every hop and by every enclosing `narrow` scope, never the declared base
  type — so a nested same-position narrow can only constrain the position
  further, and one that broadens back out (a `Cat` narrow inside a `Dog`
  scope) is rejected at build time (`narrow-outside-position`, the corpus's
  threaded-position rule).
- **Temporal-read spelling.** Statement-level and dimension-keyed, with Valid
  Time and Transaction Time as the only public vocabulary:

  ```python
  Balance.where(...).as_of(transaction_time=t)
  Position.where(...).as_of(valid_time=v, transaction_time=t)
  Balance.where(...).history("transaction_time")
  Balance.where(...).as_of_range(transaction_time=(start, end))
  ```

  Timestamps are timezone-aware `datetime` values, normalized to UTC,
  microsecond precision; naive datetimes are rejected at statement build. An
  omitted axis defaults to **latest** per the core default-injection rule; the
  module-level `LATEST` sentinel spells the same pin explicitly and lowers to
  the identical injected predicate. Canonical serialization is deterministic:
  each explicitly passed dimension serializes exactly one wrapper node, and
  when both are passed the Valid-Time `asOf` is the outer wrapper enclosing the
  Transaction-Time `asOf`; an
  omitted axis serializes **no** wrapper — its latest default is injected at
  lowering — while an explicit `LATEST` pin serializes its wrapper with the
  canonical Latest value, never `now`. A finite current-clock datetime is Now
  and lowers to containment rather than Latest's `end = infinity`. `as_of` is
  single-shot: calling it on an
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
- **Runtime introspection API.** `models.meta(Order)` (or by canonical Entity
  Identity) returns the immutable, local `EntityMetadata` contract from
  `m-metamodel`: declared storage, persistence, attributes, defining/reverse
  relationship declarations, Value Objects, As-Of Axes, inheritance
  declaration, and indices in declaration order. It never flattens inherited
  members and exposes no effective `table`, `temporal`, relationship-target,
  family, or similar convenience aliases. Owner-specific derived behavior is
  obtained from the hub's compiled facets. Canonical descriptor export is a
  hub operation, not a method on an Entity metadata view. Class-backed and
  descriptor-backed hubs return the same compiler-owned objects; there is no
  package-global `meta(...)` registry lookup or parallel `EntityMeta` graph.
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
  The static-typing carrier is the **annotation itself**: entity fields are
  declared with the exported `Mapped[T]`-style aliases `Attr[T]` (attributes
  and value objects) and `Rel[T]` (relationships), each backed by a descriptor
  whose overloaded `__get__` returns the typed expression object for class
  access and the plain `T` for instance access, so strict Pyright sees both
  sides without a plugin or stub files. Plain `qty: int` annotations are
  **not** the mechanism — Pyright would type class access as `int` and hide
  the expression surface, and no runtime metaclass swap is visible to the
  checker. The metaclass unwraps `Attr[T]` / `Rel[T]` to their inner types
  when building the Pydantic model fields, so instances stay ordinary frozen
  values and the classes still carry no information absent from the
  descriptor schema.

  ```python
  class Order(Entity, frozen=True):
      order_id: Attr[int] = Field(primary_key=True)
      qty: Attr[int]
      items: Rel[tuple["OrderItem", ...]] = Relationship()
  ```

  Rationale: single source of truth in user code, no generated-file lifecycle,
  strict-Pyright-clean class-level expressions via the annotation aliases.
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
  classes** — plain values, shareable and serializable. Pydantic
  `frozen=True` is faux-immutable (it rejects attribute assignment but cannot
  deep-freeze field values), so every collection-valued node field is an
  immutable type: included to-many relationships and `multiplicity: many`
  value-object members materialize as **tuples** (§4), keeping deep edits
  unrepresentable rather than merely discouraged. Hashability is conditional,
  stated precisely: a node is hashable exactly when hashing terminates over
  hashable field values — scalar and value-object fields always qualify,
  to-many tuples qualify when their elements do, and a back-reference include
  that closes a cycle makes the derived hash non-terminating, so such nodes
  are shareable but not hashable. `Snapshot[T]`'s
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
  reports each node's own coordinates. `parallax.core.edge_of(node) -> Edge`
  reports a temporal node's **milestone edge** as a distinct frozen `Edge`
  value exposing one strict-typed accessor pair per dimension — the established
  arity-accessor house pattern (§2's `result()` / `result_or_none()`) applied
  to dimension access: `edge.transaction_time -> datetime` raises
  `UndeclaredAxisError` when the Entity does not declare the dimension,
  `edge.transaction_time_or_none -> datetime | None` returns `None` instead,
  and `edge.valid_time` / `edge.valid_time_or_none` behave identically for
  Valid Time. Every value a declared dimension yields is the **finite**
  from-instant of the node's milestone on that axis (core's edge pin) —
  defined for every temporal node regardless of how the read was pinned;
  calling `edge_of` on a non-temporal node raises. `Edge` is deliberately not
  a `Pin`: a `Pin` carries an entry only per actually-pinned axis and may
  carry the `LATEST` sentinel, while an `Edge` answers every declared axis
  and is always finite — never `LATEST`, never absent-because-scanned. The
  strict accessors keep replay code narrowing-free: a caller replaying an
  Entity's declared dimensions reads `edge.transaction_time` as a plain `datetime` and
  passes it straight to `as_of(...)` (the stale-web-edit recipe below). The
  `snapshot-history-includes` feature
  is **deferred, not invalid**: combining `.history()` with `.include()`
  raises `UnsupportedFeatureError` naming the deferral, distinct from
  validation errors.
- **Closed-world relationships.** An included to-one is the related node or
  `None` (loaded-null); an included to-many is a `tuple` (possibly empty —
  loaded-empty is `()`). A relationship outside the include set is
  **unloaded**: attribute access raises `UnloadedRelationshipError` naming the
  path and the include fix, and `parallax.core.is_loaded(node, "items")`
  answers without raising. Access never issues SQL — there is no lazy loading
  in this lifecycle.
- **Narrowed views.** A narrowed include populates a distinct **narrowed
  view** keyed by relationship name plus effective concrete-subtype set — it
  never marks the broad relationship loaded. Views are read with
  `parallax.core.narrowed(node, Owner.pets.narrow(Dog))`: the include-path
  grammar names the view, equivalent authored narrowings (`.narrow(Pet)` vs
  `.narrow(Cat, Dog)`) resolve to the same effective set and therefore the
  same loaded view, and differently narrowed views (the corpus's `pets[Dog]`
  and `pets[Cat]`) coexist on one node as independent simultaneous views. An
  unrequested narrowed view raises `UnloadedRelationshipError` naming the
  derived view key; `is_loaded` accepts the same narrowed-path argument.
- **Eager include execution.** One query per non-empty relationship level
  (semi-join against the parent level's keys); an empty level short-circuits
  its subtree; declared descriptor `orderBy` governs child ordering; narrowed
  relationship views load exactly the requested narrowed set keyed by
  relationship name and effective concrete-subtype set; the `1 + L` round-trip
  ceiling holds and is observable via `snapshot.execution.round_trips`.
- **Explicit writes.** All writes go through the Parallax Transaction
  (§5) — the handle has no write methods. Graph edits are impossible (nodes
  are frozen); the only mutation idiom is deriving an **edited copy**: the
  Parallax base class overrides `model_copy` so a copy of a node carries a
  **Change Record** mapping each touched field to its **original** value —
  the value the field held when first touched in the copy chain (copies of
  copies merge records, keeping the earliest original per field). The
  override also **validates**: Pydantic's own `model_copy` does not validate
  `update=` data, so the Parallax override applies the same build-time rules
  as construction — unknown field names are rejected, framework-owned fields
  (the version column) and primary-key fields may not be assigned,
  **relationship fields are rejected outright** (only mapped scalar
  attributes and value-object members are assignable; a relationship edit has
  no canonical row lowering in this slice — no cascade and no deferred
  association mutation semantics exist to lower it to), and every
  value passes the §2 scalar input policies — so an invalid edit raises at
  copy time, never at the database. Nodes carry no change tracking; the
  derived copy's change record is an explicit write input, and there is no
  merge-back (no re-association, no returned managed object). At lowering, a
  touched field whose current value equals its recorded original drops out of
  the **effective change set**, so a net-zero edit chain (`100 → 200 → 100`)
  contributes nothing and an update whose effective change set is empty
  issues **no DML** — uniformly for non-temporal and temporal entities
  alike (§5). Write inputs are the entity classes themselves:
  full instances for `insert` (the Create Payload), edited copies or
  instances for the other verbs (§5). The **stale-web-edit** recipe
  transports the displayed milestone's **edge on every declared dimension**: at
  render time the service reads the row and captures `edge_of(node)` — the
  `Edge` answers each declared dimension's start instant as a plain `datetime`
  (`edge.transaction_time` is the displayed milestone's own `tx_start`, mapped
  to `in_z`) — and sends the
  whole edge with the form. On submit, the service re-fetches with **every
  declared dimension** pinned at the transported edge —
  `as_of(transaction_time=edge.transaction_time)` for a
  Transaction-Time-Only Entity,
  `as_of(transaction_time=edge.transaction_time,
  valid_time=edge.valid_time)` for a Bitemporal one; a replay passes exactly
  its Entity's declared dimensions, so
  every `as_of` argument is strictly `datetime`-typed with no narrowing —
  inside an optimistic transaction, applies the payload
  fields to a copy, and updates. A milestone's from-instant lies inside its
  own `[start, end)` interval on each dimension by construction, so the
  re-fetch selects exactly the **displayed** rectangle — never a different
  Valid-Time rectangle reached through a defaulted-Latest dimension — even
  after a concurrent
  writer has chained a replacement: the transaction observes the displayed
  `in_z`, and the concurrent chain leaves a current row whose fresh `in_z`
  fails the observed-`in_z` gate (a zero-row close — the conflict; for a
  Bitemporal Entity the gate also binds the Valid-Time discriminator when the
  key's current rows share an `in_z`, per `m-bitemp-write`, so the close
  targets exactly the observed rectangle), while an
  untouched row succeeds. Weaker transports fail: the `LATEST` sentinel is
  not replayable (it re-resolves to whatever milestone is current at submit
  time), and a wall-clock display instant is racy because Transaction-Time instants
  order by **assignment**, not commit — a writer whose transaction began
  before the display fetch can commit a replacement whose `in_z` predates the
  captured instant, which a wall-clock replay then selects, letting the stale
  overwrite pass. Edge transport is Reladomo's own answer with the detach
  removed: its detached copy carries the milestone's `IN_Z` offline and the
  merge-back gate binds that carried coordinate — transport, never
  reconstruction. The idiom requires no detached objects.

## 4. Result collections and materialization

### Snapshot results

- **Eager materialized collections.** Query construction is side-effect-free;
  execution happens exactly at `db.find(op)` and returns a value. Roots are
  reached only through `Snapshot[T]`'s three accessors; `results()` returns a
  real built-in `list[T]` the caller owns (fresh copy per call — the container
  accessor is unaffected by node immutability). Included to-many
  relationships are `tuple` fields on frozen nodes (§3). Nothing is an
  `m-op-list` operation-backed lazy list; iteration, indexing, and bulk
  operations are ordinary Python on ordinary lists and tuples.
- **Result-shape appearances.** Root-empty: `results() == []`, `result()`
  raises `NoResultFound`, `result_or_none()` is `None`. Relationship-empty:
  `()`. Relationship-null (to-one): `None`. Unloaded: raising access as in §3.
  Ordered children: descriptor `orderBy` order. Shared prefixes: one query per
  level regardless of how many include paths share it. Graph-local shared
  identity: diamond paths yield the *same* node object (`is`-identical), which
  is also how identity expectations are observed by scenario cases.
  Polymorphic positions: every materialized node is an instance of its
  concrete entity class, so the corpus's `familyVariant` is observable as
  `type(node)`. Narrowed views: `parallax.core.narrowed(node, path)` returns
  the view's `tuple` for a to-many hop (the related node or `None` for
  to-one); a single-concrete view is typed as that concrete class, and a
  multi-concrete view's elements are their concrete classes.

## 5. Transactions and writes

- **Demarcation construct.** Callback-only:
  `db.transact(fn, *, retries: int | None = None, concurrency: Literal["locking", "optimistic"] | None = None, retry_optimistic_conflicts: bool | None = None)`.
  Every option is **sentinel-backed** so an omitted option is distinguishable
  from an explicitly passed value: `None` (the default) means *apply the
  outermost defaults when this call opens the transaction — `retries=10`,
  `concurrency="locking"`, `retry_optimistic_conflicts=False` — and inherit
  the active transaction's settings when this call joins one*. The closure
  receives the Parallax Transaction (`def fn(tx): ...`),
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
- **Nesting, ownership, and participation mode.** A `db.transact` call while
  a transaction is already active on the current thread **joins** it —
  aligning with Reladomo and the TypeScript target (ADR 0004): the inner
  closure receives the **same** Parallax Transaction (no nested database
  transaction, no savepoint) and its return value is returned immediately;
  commit, abort, and the bounded retry loop belong exclusively to the
  **outermost** boundary (an inner body re-executes only as part of the
  outermost closure's retry), and an inner failure aborts the whole
  transaction with defined **rollback-only** semantics: before the exception
  propagates out of the joined scope, the root transaction is marked
  rollback-only, so even if the outer callback catches the exception and
  returns normally, commit is **refused** — the refusal preserves the
  original cause and its retriability classification (the outermost retry
  loop still applies per the original failure's category), and the callback's
  return value is withheld exactly as on any abort (Reladomo's root
  `setExpectRollback` behavior). Rollback-only also forecloses re-entry: a
  `db.transact` call that would join a transaction already marked
  rollback-only raises `RollbackOnlyError` **immediately, before executing
  its closure** — a distinct error naming the rollback-only state and
  carrying the original failure as its cause (`__cause__`) — because no new
  work may start inside a doomed scope. A callback that catches an inner
  failure therefore has exactly one defined continuation: clean up and let
  the outermost boundary abort (and retry per the original failure's
  classification). A joining call may not re-negotiate the
  boundary: an explicit (non-`None`) option whose value conflicts with the
  active transaction's setting raises, an explicit value equal to the active
  setting is accepted, and omitted (`None`) options inherit the active
  settings. The active transaction
  is tracked per thread; a transaction object is owned by its outermost
  closure invocation and is not thread-safe; escaping references raise on use
  after the scope ends. The per-transaction participation mode is
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
  edited copy and emits the sparse row (primary key + the **effective change
  set** — touched fields whose current value differs from the copy's recorded
  original; a provenance-less instance raises, and changing a PK field
  raises); temporal `update` takes an edited copy or instance and emits the
  full row (close-and-chain); `delete`/`terminate` take a node or
  instance and key off it. The **no-op rule is uniform**: an `update` driven
  by an edited copy whose effective change set is empty issues **no DML at
  all** — zero round trips, no version advance, and for a temporal entity no
  close and no chained row (a value-identical milestone would pollute the
  audit history with a spurious change; Reladomo's dated setters likewise
  refuse to enroll an equal value). A **non-empty** effective change set on a
  temporal edited copy emits the full close-and-chain replacement row. A
  provenance-less temporal instance carries no change record, so it always
  chains; callers wanting no-op elision pass edited copies. Bitemporal plain
  verbs require keyword-only `valid_from`; the `*_until` trio additionally
  requires `until`, with `valid_from < until`, both aware-UTC-microsecond
  datetimes, all validated at build. `delete` on a temporal Entity and
  `terminate` on a non-temporal Entity are rejected. Transaction-Time instants
  come from the handle-configured
  **Clock Strategy** (default system UTC; tests inject a fixed clock) — never
  from callers, with no per-operation overrides. Temporal `update`/`terminate`
  follow the same prior-observation rule as versioned writes (below): the
  values a bitemporal rectangle split carries forward and, under optimistic
  mode, the observed `tx_start` (`in_z`) for the gated close (with the Valid-Time
  discriminator when current rows share an `in_z`, per `m-bitemp-write`) come
  from the milestone this unit of work observed via a transaction-scoped
  read — never from an implicit write-path read.
- **Versioned keyed writes require prior observation; set-based writes
  materialize.** One observation rule, matching `m-opt-lock` exactly, ordered
  no-op-first. **First**, no-op detection: an update whose effective change
  set is empty is dropped before any observation or locking concern — no
  observation read, no DML, zero round trips (the corpus's no-op scenario
  shape). **Then**, for every write that survives, the version driving a keyed
  write must already have been **observed by this unit of work** — recorded by
  a transaction-scoped read (`tx.find`, or the set-based materialize read
  below) that in `locking` mode takes the dialect's shared read lock and in
  `optimistic` mode takes none. A keyed `update` or `delete` of a versioned
  row this unit of work never observed **raises** in either mode; the
  framework never issues an implicit resolving `SELECT` on behalf of a keyed
  write (which would add round trips no corpus golden represents). A keyed
  write row that itself authors an explicit value for the entity's version
  attribute **raises** `CallerAuthoredVersionError`, checked before the
  observation-required rule above even runs: the version is framework-owned
  end to end (ADR 0013), so a row-carried value is never a legitimate
  alternative to the unit of work's own recorded observation, observed or
  not. **Locking
  mode additionally requires that the observation be of the current
  milestone**: a temporal observation licenses a locking-mode write only when
  its read was **latest-pinned on the written Transaction-Time dimension** — a
  versioned non-temporal row satisfies this trivially, since its single row
  is always the current one. Locking-mode closes are **ungated**, so the
  shared read lock is the only protection, and a shared lock on a historical
  or edge-pinned milestone locks the wrong row: a concurrent chain replaces
  the current row without touching the locked one, and the ungated close
  would then silently re-close the replacement — a lost update. A write whose
  only transaction-scoped observation is historical or edge-pinned therefore
  raises `HistoricalObservationError` in locking mode; the same observation
  is legal in **optimistic** mode, where the observed-`in_z` gate detects the
  staleness (a superseded milestone's gate matches zero rows — the conflict),
  which is exactly why the §3 stale-web-edit recipe runs its edge-pinned
  re-fetch inside an optimistic transaction. The lowered
  `UPDATE` sets the effective
  changed fields plus the framework-computed advance (`observed + 1`) in
  both modes and adds the `and version = ?` gate binding the observed
  version in optimistic mode only; the lowered `DELETE` is keyed and binds
  the observed version. A gated statement affecting zero rows is the
  optimistic conflict — surfaced always, retriable only via
  `retry_optimistic_conflicts=True`. **Set-based** writes — selecting rows by
  predicate rather than key — are the one path where the framework itself
  materializes observations: one real read resolves the predicate to rows,
  recording each matched row's observed version (locked in `locking` mode),
  then one keyed per-object statement per written row — for the
  assignment-bearing verbs (`update_where` / `update_until_where`), each
  resolved row that survives the per-row no-op elimination below; for the
  delete and terminate verbs, every resolved row (`1 + N` round trips, a
  mid-batch zero-row gate aborting like any conflict). A statement becomes
  a write target only as a **bare statement** — one carrying nothing but a
  predicate (its `where(...)` arguments); `order_by`, `limit`, `include`,
  `as_of`, `history` / `as_of_range`, and `narrow` are all rejected on any
  write target. This is the single definition; the set-based verbs below
  reference it rather than restating fragments. Version values are
  framework-owned end
  to end: the version field on a node, an edited copy, or any caller input
  never feeds the gate or the advance. The developer-experience consequence
  is stated plainly: an edited copy whose original node was fetched
  **outside** the writing transaction cannot be updated directly — the row
  must be re-fetched inside the transaction before `tx.update` (a
  latest-pinned observation under locking mode; under optimistic mode the
  milestone whose gate should bind, the displayed edge in the §3
  stale-web-edit recipe, which runs under optimistic mode for exactly this
  reason).
- **Set-based write verbs.** Every mutation verb that targets existing rows
  has a predicate-selected `_where` flavor, so the keyed and set-based
  surfaces mirror each other completely (`insert` alone has no set-based
  flavor — there is no matching set to select):

  ```python
  tx.update_where(op, Account.balance.set(Decimal("0.00")))  # non-temporal
  tx.delete_where(op)                                        # non-temporal
  tx.terminate_where(op)                                     # Transaction-Time-Only
  tx.update_where(op, Position.px.set(x), valid_from=v)   # Bitemporal plain
  tx.terminate_where(op, valid_from=v)
  tx.update_until_where(op, Position.px.set(x), valid_from=v, until=u)
  tx.terminate_until_where(op, valid_from=v, until=u)
  ```

  Assignments belong to the **assignment-bearing** verbs alone —
  `update_where` and `update_until_where`; `delete_where`, `terminate_where`,
  and `terminate_until_where` take no assignments, and passing any raises at
  build — a delete or terminate names nothing to assign. Assignments are the
  typed `.set(value)` spelling on attribute expressions,
  validated at statement build as one rule family shared with `model_copy`'s
  `update=` validation (§3) — the assignability and scalar-input rules are
  stated once there and referenced here, never duplicated, so the two lists
  cannot drift: only mapped scalar attributes and value-object members are
  assignable, never relationship fields. Three list-level rules complete the
  family, scoped to the assignment-bearing verbs: the assignment list must
  be non-empty (zero assignments raises),
  each field may be assigned at most once (a duplicate raises), and every
  assigned attribute or value-object member must be declared by the exact
  target entity — set-based writes already reject inheritance-family targets
  (below), so ancestry resolution never arises. The target statement must be
  a **bare statement** (the single definition above);
  resolution happens inside the transaction and participates in its mode
  (shared-locked under `locking`, lock-free under `optimistic`). Lowering
  follows the observation rule above, with **per-path no-op semantics**.
  Versioned and temporal targets **materialize** — the resolving read records
  per-row observations, then one keyed per-row statement (gated in optimistic
  mode), `1 + N` round trips where `N` counts **written** rows. Which rows
  are written is per-verb. For the assignment-bearing verbs, per-row no-op
  elimination applies: a resolved row whose assignments all equal its
  current values (structural equality, the same rules as the change-record
  effective-set test) is skipped — no DML, no version advance, no chained
  milestone, and no round trip — mirroring the keyed no-op rule (Reladomo's
  equal-value setters likewise refuse to enroll). The delete and terminate
  verbs write **every** resolved row: with no assignments there is no value
  equality to test — a delete or terminate changes a row's existence or
  currency, never its values — so no resolved row is ever skipped, and `N`
  equals the resolved-row count. An unversioned non-temporal
  target lowers to a single set-based statement with **no** no-op elimination
  — plain SQL set semantics, so already-equal rows are matched and affected
  like any SQL `UPDATE` — because the readless path observes nothing to
  compare against, and inventing a null-safe difference filter would add SQL
  shape no golden pins. That readless lowering is itself pinned so nothing is
  left to invent: `update_where` emits exactly one
  `update <table> set <col> = ?, … where <predicate>` whose `set` columns
  follow the model's declared attribute order — the descriptor `columnOrder`
  convention that canonical row-write lowering and fixture loading already
  follow — never the authored assignment order, so equivalent calls with
  reordered assignments emit identical SQL (deterministic emission,
  authoring-order-insensitive goldens); the binds are the assignment values
  in the emitted column order followed by the predicate binds (the
  corpus statement-entry bind convention), and `delete_where` emits
  `delete from <table> where <predicate>`; both shapes are core-contract
  behavior with canonical corpus goldens (`m-batch-write-005` / `-006`), not
  language-local extensions. A
  set-based write whose target entity belongs to an inheritance
  family is **rejected before SQL** with the corpus's
  `subtype-write-set-based-unsupported` classification (`m-inheritance-089`).
  Corpus coverage is annotated per flavor, honestly: versioned non-temporal
  `update_where` is covered in both modes (`m-opt-lock-003` / `-004`) and its
  mixed equal/changed-row elimination in `m-opt-lock-014`; versioned
  `delete_where` is predicate-shaped in `m-opt-lock-015`; readless
  non-versioned `delete_where` / `update_where` (including descriptor-column
  order) are `m-batch-write-005` / `-006`; audit-only `terminate_where` is
  `m-audit-write-007`; and the bitemporal plain update/terminate plus both
  bounded forms are `m-bitemp-write-010`–`-013`. The nine newly authored cases
  (`m-opt-lock-014` / `-015`, `m-batch-write-005` / `-006`,
  `m-audit-write-007`, and `m-bitemp-write-010`–`-013`) are deliberately
  `slice-snapshot-1` only: they are the snapshot claim's executable oracle,
  not a managed API partition expansion. The upgraded legacy
  `m-opt-lock-003` / `-004` retain their existing `slice-managed-1` tags. The API still has
  broader surface area than any finite corpus sample — arbitrary valid bare
  predicates, multiple assignable fields, and every valid temporal bound are
  validated and documented by the implementation/API suite — but no covered
  mutation flavor is a language-local semantic extension.

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
- **Adapter smoke and provider contract suites.** The psycopg adapter — the
  production `parallax-postgres` artifact declaring `psycopg[binary]`, whose
  bundled `libpq` makes it self-contained (§8) — is proven by a smoke suite
  covering construction from documented connection configuration, a
  managed scalar read returning adapter-boundary values (e.g. `Decimal`),
  a transaction callback that commits and returns its value, a bytes write
  round trip through the dialect bind seam, affected-row semantics for matched
  and unmatched DML, and a **real transient classification proof** (two
  crossed-update connections via `peer` provoke a genuine `40P01` deadlock).
  The provider contract suite exercises `reset`, `applyDdl`, `loadFixtures`,
  `query`, `exec`, `execRolledBack`, and `peer` against the container.
- **Matrix profiles.** Two named profiles, both **full**: `pg-full` (every
  claimed case, `run`, postgres, expected count derived from the corpus at
  runtime — never hard-coded) and `compile-sweep` (every **compile-eligible**
  claimed case, `compile`, Docker-free, emissions and binds vs golden plus
  normalization). A claimed case the corpus declares run-only
  (`compileEligibility`, `m-case-format`) is graded by `pg-full` only; the
  compile lane's refusing port makes it emit the `compile-run-only` diagnostic
  (`m-conformance-adapter`) rather than a golden comparison, so the sweep stays
  honest without hard-coding which cases are excluded. No partial profiles
  exist; MariaDB is a §1 deferral, not a profile exclusion.
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
  failing on stale case IDs or empty skip reasons. Four no-drift guards
  close the loop. Two run per example: the idiomatic statement's
  serialization equals the corpus operation, and idiomatic class descriptors
  equal corpus descriptors. A third, scoped to every registered write story,
  drives it against a recording fake port and asserts its wire DML equals its
  corpus golden byte-exact (a commit story the golden DML, an abort story
  nothing for the discarded buffer). The fourth is a Docker-free, unit-lane
  **copy-to-row contract test** (`uv run pytest -m unit`), scoped to the
  write shapes that actually pass through edited-copy lowering — keyed
  non-temporal updates and keyed temporal updates driven by an edited copy;
  inserts, deletes/terminates, and set-based materialize paths never touch
  `model_copy` lowering and are proven by the ordinary conformance path. For
  each in-scope claimed write case it builds the fixture node, applies the
  case's changes through `model_copy`, and lowers the edited copy through the
  lowering seam, which takes the **transaction observation** (the observed
  version or `in_z` the unit of work supplies at flush) as an explicit input:
  the test supplies a synthetic observation and asserts the lowered
  row-shaped write input (sparse row non-temporal, full row temporal) binds
  exactly that observation, and a companion assertion lowers the SAME edited
  copy against a *different* observation and proves the bound value tracks
  the observation, never anything the copy itself carries — so the
  copy-provenance lowering (ADR 0003) and the framework-owned observation
  rule (§5) cannot drift while the other three proof paths stay green.
- **Usage Guide.** Generated from suite source (`uv run gen-usage-guide`) into
  `languages/python/docs/usage-guide.md`; CI runs `--check` and fails on
  drift. The guide and suite are additive to conformance-adapter proof, never
  substitutes.

## 7. Source-enforcement topology

Behavioral modules map onto Python submodules (enforcement scopes) inside the
distributions of §8. During the COR-45 contract transition, `m-metamodel`,
`m-model-formation`, and `m-relationship` are distinct normative module rows but
are co-located in the existing `parallax.core.descriptor` enforcement scope.
COR-46 separates those scopes as it moves behavioral consumers to the Metamodel
Interface; COR-45 does not pre-implement that dependency-graph refactor.
import-linter forbids every production
scope-pair import the DAG does not permit — the generated forbidden-edge
complement below, with the conformance-family scopes exempted as importers
per `modules.md` — so illegal non-edges are rejected, not merely wrong
directions; artifact co-location never legalizes a forbidden edge.

| Behavioral/support module | Source owner/path | Enforcement scope | Allowed direct dependencies | Enforcement rule/config |
|---|---|---|---|---|
| `m-core` | `parallax.core.base` | `parallax.core.base` | (none) | generated forbidden contracts, `languages/python/pyproject.toml` |
| `m-metamodel` | `parallax.core.descriptor` (temporary co-location) | `parallax.core.descriptor` | `m-core` | generated forbidden contracts |
| `m-model-formation` | `parallax.core.descriptor` (temporary co-location) | `parallax.core.descriptor` | `m-metamodel` | generated forbidden contracts |
| `m-descriptor` | `parallax.core.descriptor` | `parallax.core.descriptor` | `m-core`, `m-metamodel` | generated forbidden contracts |
| `m-pk-gen` | `parallax.core.pk_gen` | `parallax.core.pk_gen` | `m-descriptor`, `m-metamodel` | generated forbidden contracts |
| `m-inheritance` | `parallax.core.inheritance` | `parallax.core.inheritance` | `m-descriptor`, `m-metamodel`, `m-model-formation` | generated forbidden contracts |
| `m-value-object` | `parallax.core.value_object` | `parallax.core.value_object` | `m-descriptor`, `m-metamodel`, `m-model-formation` | generated forbidden contracts |
| `m-relationship` | `parallax.core.descriptor` (temporary co-location) | `parallax.core.descriptor` | `m-metamodel`, `m-model-formation` | generated forbidden contracts |
| `m-op-algebra` | `parallax.core.op_algebra` | `parallax.core.op_algebra` | `m-metamodel`, `m-inheritance` | generated forbidden contracts |
| `m-sql` | `parallax.core.sql_gen` | `parallax.core.sql_gen` | `m-op-algebra`, `m-dialect` | generated forbidden contracts |
| `m-dialect` | `parallax.core.dialect` (incl. driver-free `dialect.postgres`) | `parallax.core.dialect` | `m-core` | generated forbidden contracts |
| `m-db-port` | `parallax.core.db_port` (abstract) | `parallax.core.db_port` | `m-core` | generated forbidden contracts |
| `m-db-error` | `parallax.core.db_error` | `parallax.core.db_error` | `m-db-port`, `m-dialect` | generated forbidden contracts |
| `m-unit-work` | `parallax.core.unit_work` | `parallax.core.unit_work` | `m-op-algebra`, `m-db-port` | generated forbidden contracts |
| `m-read-lock` | `parallax.core.read_lock` | `parallax.core.read_lock` | `m-unit-work`, `m-dialect` | generated forbidden contracts |
| `m-auto-retry` | `parallax.core.auto_retry` | `parallax.core.auto_retry` | `m-unit-work`, `m-db-error` | generated forbidden contracts |
| `m-opt-lock` | `parallax.core.opt_lock` | `parallax.core.opt_lock` | `m-unit-work`, `m-temporal-read`, `m-metamodel`, `m-model-formation`, `m-inheritance` | generated forbidden contracts |
| `m-temporal-read` | `parallax.core.temporal_read` | `parallax.core.temporal_read` | `m-op-algebra`, `m-metamodel`, `m-model-formation`, `m-inheritance` | generated forbidden contracts |
| `m-audit-write` | `parallax.core.audit_write` | `parallax.core.audit_write` | `m-temporal-read`, `m-unit-work` | generated forbidden contracts |
| `m-bitemp-write` | `parallax.core.bitemp_write` | `parallax.core.bitemp_write` | `m-audit-write` | generated forbidden contracts |
| `m-batch-write` | `parallax.core.batch_write` | `parallax.core.batch_write` | `m-unit-work` | generated forbidden contracts |
| `m-navigate` | `parallax.core.navigate` | `parallax.core.navigate` | `m-op-algebra`, `m-unit-work`, `m-temporal-read`, `m-inheritance`, `m-relationship` | generated forbidden contracts |
| `m-deep-fetch` | `parallax.core.deep_fetch` | `parallax.core.deep_fetch` | `m-navigate` | generated forbidden contracts |
| `m-snapshot-read` | `parallax.snapshot.materialize` | `parallax.snapshot.materialize` | `m-deep-fetch` | generated forbidden contracts + cross-package contract |
| Snapshot handle and composition surface (support) | `parallax.snapshot.handle` | `parallax.snapshot.handle` | `parallax.snapshot.materialize`, `m-unit-work`, `m-auto-retry`, `m-read-lock`, `m-opt-lock`, `m-batch-write`, `m-audit-write`, `m-bitemp-write`, `m-sql`, `m-navigate`, `m-db-port`, `parallax.core.entity` | generated forbidden contracts + cross-package contract |
| Snapshot handle wrapping (support, child of `parallax.snapshot.handle`) | `parallax.snapshot.handle._wrap` | `parallax.snapshot.handle._wrap` | `parallax.snapshot.materialize`, `parallax.core.entity`, `m-descriptor`, `m-inheritance`, `m-temporal-read` | generated forbidden contracts |
| Snapshot handle write lowering (support, child group of `parallax.snapshot.handle`) | `parallax.snapshot.handle._family`, `._write_types`, `._keyed_sql`, `._write_lowering` | those four scopes, sharing one grant row | `m-core`, `m-descriptor`, `m-inheritance`, `m-dialect`, `m-db-port`, `m-sql`, `m-unit-work`, `m-opt-lock`, `m-audit-write`, `m-bitemp-write` | generated forbidden contracts |
| `m-case-format` | `parallax.conformance.case_format` (dev-only) | `parallax.conformance.case_format` | `m-core` | generated forbidden contracts (dev tree) |
| `m-conformance-adapter` | `parallax.conformance.cli` (dev-only) | `parallax.conformance.cli` | `m-case-format`, plus any claimed behavioral or support scope it harnesses — the core conformance-family exception | generated forbidden contracts (dev tree) |
| `m-api-conformance` | `languages/python/tests/api_conformance` (dev-only) | `tests.api_conformance` | `m-case-format` (harnesses the public surface) | pytest collection boundary |
| Entity and statement frontend (support) | `parallax.core.entity` | `parallax.core.entity` | `m-descriptor`, `m-op-algebra`, `m-temporal-read` | generated forbidden contracts |
| Concrete Postgres adapter (support) | `parallax.postgres.adapter` | `parallax.postgres` | `m-db-port`, `m-db-error`, `m-dialect`, psycopg | generated forbidden contracts + cross-package contract |
| Composition root (support) | application/test code calling `parallax.snapshot.connect` | (application-owned) | `parallax.snapshot`, `parallax.postgres` | only the root imports a concrete adapter |

Behavioral modules carry a module tag, so their allowed direct dependencies are
already machine-readable from the fenced `dependency-graph` block in
`core/spec/modules.md`. Support scopes carry no tag, so their rows above are the
only declaration of their edges. The fenced `support-scope-graph` block below is
the machine-readable form of exactly those rows, written in the same
`A --> B` grammar and naming enforcement scopes on both sides.
The prose rows and the block MUST agree. `tools/check_dag_sync.py` parses
**both** — the rows' "Allowed direct dependencies" column and the block — and
fails when they disagree with each other or when its own `SUPPORT_SCOPE_DEPS`
table disagrees with either, so the generated contracts cannot drift from this
section and no single representation can be edited alone. In the rows, only a
backticked module tag or `parallax.*` scope declares a grant; unbackticked
prose (`psycopg`) names no enforcement scope.

```support-scope-graph
parallax.core.entity --> parallax.core.descriptor
parallax.core.entity --> parallax.core.op_algebra
parallax.core.entity --> parallax.core.temporal_read
parallax.snapshot.handle --> parallax.snapshot.materialize
parallax.snapshot.handle --> parallax.core.unit_work
parallax.snapshot.handle --> parallax.core.auto_retry
parallax.snapshot.handle --> parallax.core.read_lock
parallax.snapshot.handle --> parallax.core.opt_lock
parallax.snapshot.handle --> parallax.core.batch_write
parallax.snapshot.handle --> parallax.core.audit_write
parallax.snapshot.handle --> parallax.core.bitemp_write
parallax.snapshot.handle --> parallax.core.sql_gen
parallax.snapshot.handle --> parallax.core.navigate
parallax.snapshot.handle --> parallax.core.db_port
parallax.snapshot.handle --> parallax.core.entity
parallax.snapshot.handle._wrap --> parallax.snapshot.materialize
parallax.snapshot.handle._wrap --> parallax.core.entity
parallax.snapshot.handle._wrap --> parallax.core.descriptor
parallax.snapshot.handle._wrap --> parallax.core.inheritance
parallax.snapshot.handle._wrap --> parallax.core.temporal_read
parallax.snapshot.handle._family --> parallax.core.base
parallax.snapshot.handle._family --> parallax.core.descriptor
parallax.snapshot.handle._family --> parallax.core.inheritance
parallax.snapshot.handle._family --> parallax.core.dialect
parallax.snapshot.handle._family --> parallax.core.db_port
parallax.snapshot.handle._family --> parallax.core.sql_gen
parallax.snapshot.handle._family --> parallax.core.unit_work
parallax.snapshot.handle._family --> parallax.core.opt_lock
parallax.snapshot.handle._family --> parallax.core.audit_write
parallax.snapshot.handle._family --> parallax.core.bitemp_write
parallax.snapshot.handle._write_types --> parallax.core.base
parallax.snapshot.handle._write_types --> parallax.core.descriptor
parallax.snapshot.handle._write_types --> parallax.core.inheritance
parallax.snapshot.handle._write_types --> parallax.core.dialect
parallax.snapshot.handle._write_types --> parallax.core.db_port
parallax.snapshot.handle._write_types --> parallax.core.sql_gen
parallax.snapshot.handle._write_types --> parallax.core.unit_work
parallax.snapshot.handle._write_types --> parallax.core.opt_lock
parallax.snapshot.handle._write_types --> parallax.core.audit_write
parallax.snapshot.handle._write_types --> parallax.core.bitemp_write
parallax.snapshot.handle._keyed_sql --> parallax.core.base
parallax.snapshot.handle._keyed_sql --> parallax.core.descriptor
parallax.snapshot.handle._keyed_sql --> parallax.core.inheritance
parallax.snapshot.handle._keyed_sql --> parallax.core.dialect
parallax.snapshot.handle._keyed_sql --> parallax.core.db_port
parallax.snapshot.handle._keyed_sql --> parallax.core.sql_gen
parallax.snapshot.handle._keyed_sql --> parallax.core.unit_work
parallax.snapshot.handle._keyed_sql --> parallax.core.opt_lock
parallax.snapshot.handle._keyed_sql --> parallax.core.audit_write
parallax.snapshot.handle._keyed_sql --> parallax.core.bitemp_write
parallax.snapshot.handle._write_lowering --> parallax.core.base
parallax.snapshot.handle._write_lowering --> parallax.core.descriptor
parallax.snapshot.handle._write_lowering --> parallax.core.inheritance
parallax.snapshot.handle._write_lowering --> parallax.core.dialect
parallax.snapshot.handle._write_lowering --> parallax.core.db_port
parallax.snapshot.handle._write_lowering --> parallax.core.sql_gen
parallax.snapshot.handle._write_lowering --> parallax.core.unit_work
parallax.snapshot.handle._write_lowering --> parallax.core.opt_lock
parallax.snapshot.handle._write_lowering --> parallax.core.audit_write
parallax.snapshot.handle._write_lowering --> parallax.core.bitemp_write
parallax.postgres --> parallax.core.db_port
parallax.postgres --> parallax.core.db_error
parallax.postgres --> parallax.core.dialect
```

- **Dependency-analysis tool.** import-linter; configuration in
  `languages/python/pyproject.toml` (`[tool.importlinter]`) **generated** by
  `languages/python/tools/check_dag_sync.py`, which parses the fenced
  `dependency-graph` block in `core/spec/modules.md`, computes the DAG's
  transitive closure over the table above (core edges plus the declared
  support-scope edges), and emits the **forbidden-edge complement**
  as import-linter `forbidden` contracts — one forbidden import per
  production scope pair the closure does not permit. The handle scope's
  `m-sql` edge is deliberate: `m-unit-work` takes no edge to SQL generation
  (core routes dialect SQL through the `m-db-port` execution seam at the
  composition surface), so `parallax.snapshot.handle` is where claimed finds
  are compiled and buffered DML is lowered, and the generated complement
  permits that edge rather than forbidding it. The handle scope's `m-navigate`
  edge (COR-3 Phase 7 increment 3) follows the identical reasoning: `Transaction.find`
  is a claimed find, so it composes `parallax.core.navigate.canonicalize`
  immediately after `m-temporal-read`'s root injection, mirroring the
  conformance engine's own composition-at-the-engine order. The generator also encodes
  the core **conformance-family exception** (`modules.md`): the
  conformance-family scopes (`parallax.conformance.*`, plus the
  pytest-bounded `tests.api_conformance`) are exempted from the complement
  on the **importing** side — the CLI may import any compiler/runtime scope
  it harnesses — while every production scope remains forbidden from
  importing any conformance scope, so the production → conformance
  direction stays a generated `forbidden` contract. Layer contracts alone
  cannot encode this
  partial order: a `layers` contract lets a higher layer import *every* lower
  layer, silently legalizing illegal non-edges (e.g. `m-batch-write`
  importing `m-temporal-read`), so the gate must reject illegal non-edges,
  not merely confirm that listed edges match `modules.md`. The script
  re-generates and fails on any diff against the committed contracts. Local:
  `uv run python tools/check_dag_sync.py && uv run lint-imports`. CI: the
  same pair as a blocking job; any import outside the closure, and any
  generated-contract drift, fails.
- **Child enforcement scopes.** A support scope MAY declare child scopes over
  its own private implementation modules when the child's declared grants are
  materially narrower than the parent's closure. The two declared children of
  `parallax.snapshot.handle` are the wrapping leaf and the write-lowering
  cluster; both are generated exactly like any other scope, and neither is a
  new supported import path. Because import-linter's `forbidden` contracts are
  package-scoped on both sides, a child is emitted only as a contract
  **source**: naming it as a forbidden target of its own parent would overlap
  the parent's source package and be skipped, and the parent's existing row
  already forbids the same targets for every descendant. The handle scope
  declares no `m-pk-gen` grant: nothing under `parallax.snapshot.handle`
  imports primary-key generation, so the generated complement forbids it. The
  unused direct `m-navigate` grant is retained on purpose — navigation stays
  reachable through `m-snapshot-read` → `m-deep-fetch` → `m-navigate`, so
  removing it would forbid nothing while contradicting the deliberate edge
  described above.
- **Filesystem ownership.** `languages/python/tools/check_scope_ownership.py`
  walks every `packages/*/src/**/*.py` file in the production distributions and
  proves it resolves to exactly one **most-specific** enforcement scope of this
  section — plus, where child scopes are declared, that scope's declared
  ancestors — or to an exact, listed package-interface exemption. A file inside
  a child scope is deliberately owned by both the child and its parent: that is
  the state child scopes exist to create, and the child's tighter grant row is
  what governs it. Zero owners, **undeclared** overlapping owners (two or more
  matching scopes that are not a parent/child chain declared in
  `check_dag_sync.CHILD_SCOPE_PARENT`), and stale exemptions each fail the
  check, which runs in `just python-static`.
- **Scopes sharing one artifact.** Every behavioral module in `parallax-core`
  is its own submodule; the generated forbidden contracts operate at
  submodule granularity, so co-location in one wheel cannot legalize a
  forbidden edge. Cross-package contracts forbid `core → snapshot`,
  `core → postgres`, and `snapshot → postgres` in both metadata and imports.
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
| `parallax-core` (the common runtime) | production | all `parallax.core.*` scopes of §7 (behavioral modules, entity/statement frontend, driver-free postgres dialect strategy) | `pydantic`, `pyyaml` | (none) | `parallax.core`: entity base, `Field`, `Relationship`, `Attr`, `Rel`, statement API, `LATEST`, `Pin`, `Edge`, `pin_of`, `edge_of`, `is_loaded`, `narrowed`, errors |
| `parallax-snapshot` (snapshot lifecycle extension) | production | `parallax.snapshot.*` (`materialize`, `handle`) | (none beyond core) | `parallax-core` | `parallax.snapshot`: `connect()`, `Snapshot[T]`, `Execution` |
| `parallax-postgres` (Postgres database adapter) | production | `parallax.postgres.*` (concrete port over psycopg) | `psycopg[binary]` (sole declarer) | `parallax-core` | `parallax.postgres`: `PostgresAdapter` |
| `parallax-conformance` | development-only | `parallax.conformance.*` (CLI, case format, corpus loading, provider harness) | `testcontainers`, `jsonschema` | `parallax-core`, `parallax-snapshot`, `parallax-postgres` | `parallax-conformance` console script (`describe` / `compile` / `run`) |

- **Common runtime manifest proof.** `parallax-core`'s manifest declares only
  `pydantic` and `pyyaml`; the clean-install check installs it alone and
  proves `psycopg`, `parallax.snapshot`, testcontainers, and conformance
  modules are absent from both the installed distribution list and the import
  space.
- **Lifecycle extension manifest proof.** `parallax-snapshot` depends only on
  `parallax-core`; the clean-install check proves no sibling lifecycle
  artifact exists in the graph and no concrete driver is present.
- **Adapter manifest proof.** `parallax-postgres` alone declares the driver,
  and it declares `psycopg[binary]`: the `binary` extra bundles a self-contained
  `libpq` in the wheel, so the adapter — and the clean-install topology proof
  below — installs and imports with **no system `libpq`** present. The accepted
  trade-off is the pre-built binary build over compiling `psycopg[c]`/pure
  `psycopg` against a system `libpq` (the binary build is discouraged only for
  large-scale production connection tuning, out of scope for this slice), so the
  self-contained deployment the topology proof relies on is the deliberate
  default. The driver-free dialect strategy ships inside `parallax-core`
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
| Dependency directions within and across artifacts | import-linter (pinned in `uv.lock`) + `check_dag_sync.py` + `check_scope_ownership.py` | `languages/python/pyproject.toml` `[tool.importlinter]`; `languages/python/tools/check_dag_sync.py`; `languages/python/tools/check_scope_ownership.py` | `uv run python tools/check_dag_sync.py && uv run python tools/check_scope_ownership.py && uv run lint-imports` | `python-static` job, same commands | any production-scope import outside the DAG's transitive closure fails — the forbidden-edge complement generated from `modules.md` rejects illegal non-edges, not just wrong directions, with only the §7 conformance-family importer exemption; generated-contract drift fails, as does any disagreement among the three declarations of the support-scope graph — `check_dag_sync.py`'s support-scope table, the §7 prose rows, and the §7 `support-scope-graph` block — including the case where two of the three are edited consistently and the third is left stale; a production source file owned by no §7 scope (and so covered by no contract), owned by undeclared overlapping scopes, or covered by a stale exemption also fails |
| Unit tests | pytest (pinned) | `languages/python/pyproject.toml` `[tool.pytest.ini_options]` | `uv run pytest -m unit` | `python-static` job | unit = no container/socket I/O; any failure blocks |
| Code coverage | coverage.py via pytest-cov, branch mode + diff-cover (both pinned) | `[tool.coverage]` in `languages/python/pyproject.toml` | `uv run pytest -m unit --cov --cov-branch --cov-report=xml && uv run diff-cover coverage.xml --compare-branch origin/main --fail-under 100` | `python-static` job with `--cov-fail-under=90` plus the same diff-cover gate | **90% branch minimum** overall; diff-cover requires **100%** of changed lines vs the merge-base with `main`, making the no-new-uncovered-code policy executable; no generated/vendor code exists to exclude; conformance CLI included |
| Linting | ruff (pinned) | `[tool.ruff]` in `languages/python/pyproject.toml` | `uv run ruff check` | `python-static` job | rule sets E, F, W, I, UP, B, SIM, RUF; `# noqa` requires rule code + one-line justification |
| Deterministic formatter check | ruff format (pinned) | `[tool.ruff.format]` | check: `uv run ruff format --check`; write: `uv run ruff format` | `python-static` job (`--check` only) | CI checks without rewriting |
| Strict static typing | Pyright, strict mode, pinned version | `languages/python/pyrightconfig.json` | `uv run pyright` | `python-static` job | strict across production and tests; zero suppressions at spec time — any future suppression is listed and justified here |
| Import-cycle detection | import-linter generated forbidden contracts | `[tool.importlinter]` | `uv run lint-imports` | `python-static` job | covers all production source scopes; the permitted closure is acyclic, so any cycle necessarily crosses a forbidden edge and fails |
| Dead code and unused exports | vulture + griffe public-API snapshot test | `[tool.vulture]`; `languages/python/tests/api_surface/` | `uv run vulture && uv run pytest -m api_surface` | `python-static` job | limitation recorded: Python tooling cannot prove an export unused; compensating check is the API-surface snapshot diff, making every public-surface change a reviewed diff |
| Built-artifact and public-export health | `uv build` + twine check + wheel-content pytest | `languages/python/tests/artifact/` | `uv build && uv run twine check dist/* && uv run pytest -m artifact` | `python-static` job | wheels contain no tests/conformance modules, include `py.typed`, declare correct entry points |
| Clean-install production smoke tests | uv-venv fixtures | `languages/python/tests/clean_install/` | `uv run pytest -m clean_install` | `python-static` job | exercises all three §8 selective topologies in clean environments; presence of any unselected artifact fails |
| Supported language/runtime versions | CPython; `requires-python >= 3.12` | each distribution's `pyproject.toml` | (local dev on any supported minor) | CI matrix 3.12 / 3.13 / 3.14 | support current + two prior minors; drop on upstream EOL; floor raises are reviewed spec changes |
| Dependency and supply-chain audit | committed `uv.lock` + `uv lock --check` + pip-audit + scheduled `uv lock --upgrade` refresh | `languages/python/uv.lock` | `uv lock --check && uv run pip-audit` | `python-static` job on every PR, plus a monthly scheduled CI job opening a `uv lock --upgrade` refresh PR | high-severity findings block; exceptions carry owner + expiry inline; lockfile drift fails; freshness: the monthly upgrade PR is human-reviewed like any change and may not be merged red |
| Compatibility Conformance Suite | pytest conformance runner + jsonschema envelope validation | `languages/python/tests/conformance/` | `uv run pytest -m compile_sweep` (Docker-free) and `uv run pytest -m conformance` (`pg-full`) | `python-static` (compile sweep) + `python-database` (run sweep) | selection = active slice ∩ capability tags; every envelope validates against `conformance-adapter.schema.json` |
| API Conformance Suite and Usage Guide | pytest + guide generator | `languages/python/tests/api_conformance/`; `languages/python/docs/usage-guide.md` | `uv run pytest -m api_conformance && uv run gen-usage-guide --check` | `python-database` job | coverage partition exact (exercised ∪ reasoned-skips = slice; no stale IDs, no empty reasons); operation, descriptor, and unit-lane copy-to-row no-drift guards green; guide drift fails |
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
- Claimed coverage is the canonical tagged-case union; the sole transitive
  unclaimed prerequisite and every explicit deferral are listed separately.
- No conditional section's applicability condition is true, and none is
  present.
- The §7 map covers all claimed modules, the prerequisite, and the support
  scopes, and is mechanically enforceable via the generated import-linter
  forbidden-edge complement plus the DAG drift check.
- The §8 map contains an independent common runtime, exactly the snapshot
  lifecycle extension, a separate Postgres adapter, and a development-only
  tooling artifact, with manifest and selective clean-install proofs.
- Every §10 row names a tool, configuration, local command, blocking CI
  command, and enforcement policy; coverage has a numeric threshold, typing is
  strict, and database skips cannot be silent.
