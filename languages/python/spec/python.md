# Parallax Python — Language Spec

**Status:** Completed.

This is the per-language spec for the Python implementation of
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
| Claimed capability coverage | Copied verbatim from the canonical claim: the 31 `modules` below, `dialects: ["postgres"]`, the eight `caseShapes`, `caseTags.include: ["slice-snapshot-1"]`, `commands: ["describe", "compile", "run"]`, `provisioning: "self-managed"`. `modules` is the tagged-case union of the slice, **not** a dependency closure and not a packaging plan. |
| Unclaimed implementation prerequisites | `m-db-port` — reached via `m-unit-work` and `m-db-error`; abstract port supplied by the `parallax.core.db_port` scope, concrete adapter by `parallax-postgres`; contract-covered, never case-advertised. |
| Deferred capabilities | MariaDB (dialect); `benchmark` command and `m-perf-bench`; `m-agg` / `m-sql-agg`; Valid-Time-Only models; `m-process-cache` / `m-coherence`; `m-cascade-delete`; the `snapshot-history-includes` feature; the managed-object lifecycle (`m-identity-map`, `m-detach`, public query-backed lists); an async developer surface; MAY-tier mutations (`insertWithIncrement`, `incrementUntil`, `purge`, `inactivateForArchiving`); template-database reset optimization; handle-level default concurrency override; Object Query `where`-refinement chaining and `as_of` re-pinning; authored relationship chains past two hops, and with them multi-hop relationship quantifiers (§2, "a Python-authored relationship chain stops at two hops"); the class-header temporal-axis column-mapping override. Deferral is roadmap intent. The conformance adapter's `unsupported` result remains wire behavior for out-of-claim requests, while Snapshot's `DeferredFeatureError` is the separate runtime preflight for query Features listed in `_DEFERRED_EXECUTION_FEATURES`; neither is a database-provider capability. |
| Supported dialects and commands | Postgres only; `describe`, `compile`, `run`. Exercised locally and in CI by `uv run pytest -m compile_sweep` (Docker-free compile of every compile-eligible claimed case) and `uv run pytest tests/compatibility/test_run_sweep.py` (the `pg-full` run profile, every claimed case), aggregated by `just python-check-dbfree` and `just python-check-db`. |

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "python", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-dialect", "m-document-codec", "m-execution-lifecycle", "m-inheritance", "m-metamodel", "m-model-formation", "m-navigate", "m-object-query", "m-opt-lock", "m-pk-gen", "m-predicate", "m-read-lock", "m-relationship", "m-snapshot-read", "m-sql", "m-storage-layout", "m-temporal-read", "m-txtime-write", "m-unit-work", "m-value-object", "m-wire"],
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
- **Single-witness execution lifecycle.** `m-execution-lifecycle`'s
  `then.executionLifecycle` oracle is graded against a running implementation by
  this target alone: the compatibility harness validates the authored stream but
  installs no Provider of its own, so a disagreement between Python and the
  specification has no second reader. The `then.roundTrips` a `boundary` case or
  a retry-shaped `conflict` case authors is single-witness for the same reason
  and by a second mechanism: the harness executes no `api-conformance`-lane case
  at all, and its retry branch asserts per-attempt affected rows and table state
  without ever counting round trips. Every other claimed module's runtime
  observables are double-witnessed. Both exceptions are deliberate and hold only
  until a second grader exists, not permanent properties of the module;
  [`docs/deferred-ledger.md`](../docs/deferred-ledger.md) forwards to the issue
  that owns building one.
- **Case-selection expression.** Verification selects
  `("slice-snapshot-1" ∈ case.tags) ∧ (dialect = postgres) ∧ (case.shape ∈ claimed caseShapes) ∧ (case module-tags ⊆ claimed modules)`;
  milestone-scoped runs intersect further with capability tags via
  `--parallax-tags <m-slug>[,…]`. Filename prefixes are never a conformance
  target.

## 2. Shared developer API and model surface

### Temporal vocabulary and configuration

Python exposes no public `AsOfAxis` declaration type. Authors select exactly
one framework Entity base:

- `TxTemporal`, which supplies read-only `tx_start`/`tx_end`
  Attributes mapped to `in_z`/`out_z`; or
- `Bitemporal`, which additionally supplies read-only
  `valid_start`/`valid_end` Attributes mapped to `from_z`/`thru_z`.

The supplied members carry no explicit `name=`, so each one's canonical name is
the ordinary snake_case→camelCase conversion every other member goes through:
`tx_start` resolves to `txStart`, `valid_end` to `validEnd`, and so on. The
Python spelling an author reads and queries through is unaffected.

Read-only here means framework-stamped write semantics: each supplied Attribute
carries the derived `framework_owned` designation (§3), so a fresh instance that
sets one is refused at construction and an edit naming one is refused as
`edit-framework-owned`, because the temporal write path derives every interval
bound itself. It is not the record-level `readOnly` Attribute flag — the
supplied Attributes compile with exactly the authored flags a hand-authored
declaration carries, so the exported record stays byte-identical.

The normalized Metamodel still exposes `AsOfAxisMetadata` through the core
interface, keyed by `TemporalDimension`. This leaves a future additive seam for
advanced column overrides without making ordinary Python authors repeat
Attributes, Timestamp types, flags, interval semantics, or columns.

| Python surface | Valid Time | Transaction Time |
|---|---|---|
| Framework base | supplied by `Bitemporal` | supplied by `TxTemporal` and `Bitemporal` |
| Metadata dimension | `TemporalDimension.VALID_TIME` | `TemporalDimension.TRANSACTION_TIME` |
| Query keyword | `valid_time` | `tx_time` |
| `history` dimension constant | `VALID_TIME` | `TX_TIME` |
| `Pin` accessor | `valid_time` | `tx_time` |
| `Edge` accessor | `valid_time` | `tx_time` |
| Conventional Attributes | `valid_start`, `valid_end` | `tx_start`, `tx_end` |
| Canonical Attribute names | `validStart`, `validEnd` | `txStart`, `txEnd` |
| Physical columns | `from_z`, `thru_z` | `in_z`, `out_z` |
| Bitemporal mutation input | `valid_from`; bounded verbs also use `until` | finite clock instant supplied by the Database handle |
| Optimistic temporal observation | not used as a gate | observed `tx_start` (`in_z`) |

Relationship traversal propagates Pin and Edge coordinates by Temporal
Dimension using these same names. The former business/processing vocabulary is
not accepted as aliases in declarations, metadata, queries, Pin/Edge values,
mutations, exceptions, or exports.

### Query and predicate API

The Python target has two deliberately separate value boundaries. Developer-
authored expressions, assignments, entity construction, and managed-object edits
use `parallax.core.base` managed membership and developer-input coercion. They
retain Python-facing `QueryDefinitionError` / `EditError` classifications and
never expose serialized-literal failures. JSON query and write source passes
through `parallax.core.wire.loads` and the sole declared-type decoder in
`parallax.core.wire`; exact JSON number provenance survives until the connected
model resolves the member type. The compatibility YAML loader applies the YAML
1.2 core schema, preserves authored numeric tokens through the codec's private
production seam, and submits the resulting structured value to the same decoder.
`wire.loads` never parses YAML.

Model-aware query preflight returns a private immutable
`ValidatedObjectQuery` carrying the unchanged authored query, exact Metadata,
and a `ValidatedPredicate` of managed operands. `parallax.core.deep_fetch`
transforms it into one `ValidatedEntityQuery` per root or non-empty child read;
the private `sql_gen._compile.compile_read` accepts only that product and returns
`CompiledRead`, whose statement is a metadata-bearing `LoweredStatement`.

Typed and Wire write adapters call separate `prepare_typed_write` and
`prepare_wire_write` producers and converge on `PreparedWrite`. Buffering and
the Write Planner retain managed values and produce closed `PlannedWrite` steps;
the private `sql_gen._write.compile_write_step` accepts only one such step and
returns `LoweredStatement`. Continuation, temporal, navigation, and child-key
generation request producer-owned Predicate/Object Query derivation operations
rather than constructing phase products or re-decoding values themselves.

No SQL, document, adapter, continuation, or conformance path infers a declared
type from a Python carrier. Public Wire output and conformance observations are
recursively built-in JSON carriers in canonical `m-wire` form. Decimal stays
`decimal.Decimal`, timestamps stay aware UTC `datetime`, UUID stays `uuid.UUID`,
bytes stays `bytes`, and Float32 is the widened Python `float` carrier of the
actual binary32 value.

- **Every composed query value names the Entity it addresses.** The exported
  authoring vocabulary is parameterized: `AttributeExpr[E, T]`, `Predicate[E]`,
  `AllPredicate[E]`, `SortKey[E]`, `AttributeAssignment[E]`,
  `RelationshipPath[E, R]`, and `ObjectQuery[E, S]`, where `E` is the position a
  value is rooted at, `R` the related Entity a hop reaches, `T` a declared
  Python value type, and `S` the Entity a query's result returns. `Predicate`,
  `AllPredicate`, `SortKey`, and `AttributeAssignment` are **contravariant** in
  `E` — the inheritance rule expressed as variance, so an ancestor's member is
  addressable from a descendant position and a descendant's member is not
  addressable from an ancestor position. `RelationshipPath` is **covariant** in
  both parameters, for the opposite reason: its source narrows which queried
  objects a path starts from, so any descendant of the queried Entity is a legal
  include source. Composing a value at an Entity that variance does not admit is
  therefore a static error where the call is written. What a parameter measures
  is compatibility under that variance, never identity: a rule needing the
  position exactly is not statable through one, which is where the quantifier's
  interior narrow lands (below). Such a static rejection is restated at run
  time — which is what covers the serialized ingress and any untyped caller —
  whenever the composition it refuses either reaches the wire as a query a
  model-aware validator can refuse at execution preflight, or is one the
  frontend itself refuses with no model at all. Where that composition builds
  a **valid** canonical query instead, the parameter is the only place the
  mistake is visible and no preflight rule could restate it, because the wire
  carries no record of what was refused. Whether a given rejection is one of
  those is settled by a **test**, not by membership in a list: canonicalize the
  refused spelling and the accepted one and compare the resulting queries. Where the
  two are one document, no model-aware rule can refuse either without refusing
  both, and the parameter is the whole of the rule. A rejection lands there
  because lowering discards what the parameter read — the wire records a
  canonical Entity Identity and a declaring member, never the Python class a term
  was spelled through, and an Object Query retains clauses rather than wrapping
  them, so clause order reaches nothing — or because a signature deliberately
  answers wider than the narrowing it describes and refuses a composition that is
  in fact legal. The families that produces, **as examples and not as a closed
  set**, each stated again where it arises: `Entity.all`, since an `all` node
  names no position and nothing distinguishes `Dog.all` from `Animal.all`; an
  **inherited** member spelled through a descendant, since the wire keeps the
  declaring Entity; a member spelled through one of **two distinct Entity Classes
  carrying the same Entity Identity**, since the wire keeps the identity and not
  the class; the two clause-order rules below (a `where` argument or a sort key
  written before the `narrow` that scopes it), since the refused spelling and the
  accepted one build one query; and `ObjectQuery.narrow`'s **conservative
  variadic overload**, which leaves the result parameter where it was for any
  subtype list a fixed overload set cannot read — one expanded from a sequence,
  or one naming more than three alternatives — while the narrowing itself reaches
  the wire and scopes exactly the sort keys preflight then accepts. Nothing here
  closes that list and no count of it is normative: another family arrives with
  any typing decision that lets a parameter read what lowering discards, and
  three have been found after the list was first written. What is fixed is the
  test above and the obligation that follows it — a static rule that fails the
  test is stated where it arises and pinned in the negative-typing corpus
  (`tests/unit/test_typed_query_composition.py`), where
  `reportUnnecessaryTypeIgnoreComment` holds it to both directions. The converse
  direction is open in the same way and for the mirror-image reason: a
  model-aware rule has no static half when nothing the checker reads at the call
  site decides it, which happens either because the fact belongs to the
  **connected model** rather than to the classes, or because it is a class fact
  **no parameter is free to carry**. Each half has its own test. The first is the
  mirror of the test above — hold one Python expression fixed and execute it
  against two models; where one accepts and the other refuses, no static rule
  could have separated them, because the checker read one expression and a Find
  Query names no model. So a bare Entity name that two namespaces of the
  connected model share resolves to no Entity and is refused as
  `reference-ambiguous-entity-name`, while the identical expression is accepted
  against a model declaring one of them; and every relationship hop past the
  first, and every Value Object segment below the statically typed first hop,
  reaches the model as a name rather than as a class, which is why a renamed or
  inherited relationship member, an unknown one, and a nested literal against its
  leaf's declared type are all the model's to refuse. The second test is to name
  the parameter that would state the rule and show what it is already spent on:
  `type[…]` is covariant and a type parameter's bound may not itself be generic,
  so a narrowing form whose one parameter is already spent on what the narrowing
  produces states no relatedness (`narrow-outside-position`, below). That is an
  example on this side too,
  nothing closes this list either, and no count of it is normative. The
  obligation is the same one discharged the other way round: a model-aware rule
  with no static half is stated where it arises and pinned in the same corpus on
  a line carrying **no** suppression, which asserts the checker's silence exactly
  as a rule-coded suppression asserts its diagnostic, because an unsuppressed
  diagnostic fails the typecheck gate. Class access
  reads the **accessing** class rather than the declaring one, so `Dog.name`
  addresses `Dog` even where `Animal` declares it; the wire keeps the declaring
  identity either way, and the remedy for the asymmetry this creates — an
  ancestor's query refusing an inherited member spelled through a descendant —
  is to start every term from the queried Entity. Inheritance is not the only
  way a class and an Identity come apart: Entity Identity is unique **per
  model** (`metamodel-duplicate-entity-identity`) and a class belongs to no
  model until it is composed into one, so two distinct Entity Classes may
  legitimately carry one Identity. A member both declare then lowers to one
  attribute reference at one target from either class, while the parameters hold
  the two classes nominally incompatible — so `TwinLeft.where(TwinRight.id == 1)`
  is a static error whose canonical query is the one
  `TwinLeft.where(TwinLeft.id == 1)` produces. The remedy is the same one: spell every term through the class the
  query is rooted at. A comparison's value parameter is deliberately not
  narrowed to the member's declared Python type because Python's developer-input
  coercion policy may admit a lossless widening before membership is checked.
  That developer path is not a serialized Wire literal path. `.set(value)`
  applies the same developer-input coercion and membership contract immediately
  because an Assignment's value is already a member value.
- **One query-definition error family.** Every Python Attribute Expression,
  Relationship Path, Predicate, Assignment, Sort Key, or Object Query
  construction, composition, and refinement the frontend refuses **by a
  query-definition rule of its own** raises `QueryDefinitionError(ValueError)`
  with a stable `query-*` code. A refusal that is not one of those rules keeps
  the class its own mechanism gives it, and each such case says so where it
  arises below: Python's call binding refuses `Entity.where()`, a path that has
  no owner left to spell a segment from refuses a further hop, and `.set(...)`
  reports the copy surface's verdict rather than minting a second one. What the
  frontend judges is exactly what needs no model — clause arity, single-shot
  clauses, literal and collection shapes, and the target's own declared
  temporal axes — because query authoring reaches no model. There is
  consequently no translation seam: a rule that needs a whole model is stated
  once at execution preflight and once at the predicate-selected write
  boundary, and surfaces there as its owner module's own error carrying its own
  rule code — `ModelRejectedError` for an `m-predicate`, inheritance,
  relationship-navigation, or deep-fetch rejection, `TemporalReadError` for a
  temporal-read one — neither rewrapped nor reclassified, so the typed and the
  serialized ingress report one rejection under one name. Deferred Execution
  Features and execution failures retain their separate classifications.
  The closed stable code set is
  `query-target-mismatch`,
  `query-expression-invalid`, `query-path-invalid`,
  `query-clause-invalid`, `query-assignment-invalid`,
  `query-assignment-target-mismatch`, and
  `query-not-mutation-compatible`. Optional structured `target`, `member`,
  `path`, and `clause` context identifies the exact
  rejection; errors expose neither literal values nor internal model state.
  Invalid operators and literals use `query-expression-invalid`; invalid Value
  Object or relationship hops, quantifiers, and narrowing use
  `query-path-invalid`; invalid, repeated, or conflicting Object Query clauses
  use `query-clause-invalid`; an expression or Predicate rooted at an
  inapplicable Entity uses `query-target-mismatch`; and non-assignable members
  or values use `query-assignment-invalid`. The remaining two codes retain
  their Assignment-target and predicate-selected-write meanings.
- **Separate execution target error.** Query authoring reaches no model, so a
  Object Query carries no model identity and every model-aware rule is stated at
  execution instead. An Object Query executed through a Database whose connected
  model declares no Entity for the query's target raises exported
  `QueryTargetError(RuntimeError)` with sole stable code
  `query-target-not-in-model`, before any I/O. It retains and exposes neither
  the query, the model, nor the Database. There is no ownership relation
  between a query and a model: one Entity Class participates in any number of
  Domain Models and one Domain Model serves any number of Databases.
- **Assignment construction validates immediately.**
  An Attribute Expression's `.set(value)` constructs an immutable Assignment and
  applies the member's assignability, declared neutral-type, and nullability
  rules before returning it. The assignable targets are the **top-level** mapped
  members: a scalar Attribute, and a whole Value Object occurrence — One or
  Many — whose value is rendered to its canonical document (or list of
  documents) and judged as that. A Value Object always binds its whole document,
  so there is no sparse write below its boundary and a **nested** path
  (`Customer.address.city.set(...)`) is refused. Primary-key,
  framework-owned, and read-only targets are rejected, as are values
  that require coercion or violate the declared type or nullability; a
  relationship exposes no `.set(...)` at all. Failure
  raises `EditError(ValueError)` (§3) from `.set(...)` itself, carrying exactly
  one violation — one call names one target, so there is nothing to aggregate —
  and it is never postponed until a Transaction mutation method, write boundary,
  or database call. That class rather than a `query-*` code is deliberate. The
  assignment rules are one set with one home: `.set(...)`, `edit(...)` (§3),
  and the serialized write boundary (§5) all reach the same judgement over the
  member's metadata and the raw value, differing only in the resolution in front
  of it, so `.set(...)` reports the edit surface's refusal rather than minting a
  second verdict for the same rule — a predicate-selected assignment is an edit
  expressed over a predicate rather than over a value, and one rule family with
  two names would have two chances to drift. Assignment-list validation remains separate:
  an assignment-bearing mutation checks nonemptiness, duplicates, and exact
  target compatibility when combining already-valid Assignments with its
  Object Query.
  Under Relational Document Layout, assigning an occurrence binds the whole
  document that rendered assignment states at the occurrence's own Document Path,
  at either cardinality, and replaces the subtree stored there; an explicit `None`
  stores JSON null. Every path the statement does not assign is left standing.
  This changes physical mutation granularity without making a nested member
  independently assignable.
- **Opaque immutable Object Query.** `ObjectQuery[E, S]` — the Entity QUERIED and
  the Entity the result RETURNS, which `narrow` and only `narrow` moves — is
  exported for annotations
  and fluent use, but direct `ObjectQuery(...)` construction is unsupported;
  `Entity.where(...)` is its sole public constructor. Every clause returns a
  new value and leaves its receiver unchanged. Target, Predicate, include, and
  temporal representation fields are not public attributes.
  Object Queries define no structural equality or semantic hash: ordinary
  object-identity equality and hashing apply, so independently authored queries
  compare unequal even when they carry identical canonical queries. Conformance
  code compares canonical queries through its first-party seam.
  Truth-testing with `bool(query)` or `if query:` raises `TypeError` directing
  the caller to execute the query and inspect its Snapshot; an Object Query has no
  pre-execution empty/nonempty state.
  Canonical query extraction and serialization remain first-party
  conformance seams: `object_query()`, `serialize()`, `is_bare()`,
  `is_milestone_set()`, and equivalent state-inspection helpers are not public
  methods.
  The advanced first-party `object_query_node(query) -> ObjectQueryNode` seam
  completes the target-class-local temporal authoring contract: omitted
  Transaction Time becomes explicit Latest, while omitted Valid Time on a
  Bitemporal target raises `QueryDefinitionError(query-clause-invalid)`.
  It introduces no connected-model semantic validation. An `ObjectQuery` privately
  holds the canonical `m-object-query` value its independently authored, already
  validated clauses build — predicate, result narrowing, Temporal Selections,
  ordering, limit, and Includes, each a sibling of every other, beside its
  structured target Entity Identity. It retains no model, and there is no
  lowering step: clause invocation order cannot reach the wire, because no clause
  nests inside another. The answered value contains no model, Entity
  Class, class index, Snapshot feature tags, provider state, SQL, serialization
  method, or public execution surface. `ObjectQueryNode`'s target is
  a position the connected model resolves at execution, so an accepted node is
  not yet a validated one. `object_query_node` is not re-exported from
  top-level `parallax.core`. It answers the query's own immutable value and
  memoizes nothing globally; one execution reads it once and keeps it locally
  through preflight, planning, and execution.
- **Complete fluent surface.** The Object Query interface consists exactly of
  the class-scoped match-all value `Entity.all`,
  `Entity.where(*predicates)`, and the `ObjectQuery` methods
  `include(*relationship_paths)`, `order_by(*sort_keys)`, `limit(count)`,
  `narrow(*subtypes)`, `as_of(*, valid_time=..., tx_time=...)`,
  `history(dimension)`, and
  `as_of_range(*, valid_time=(start, end), tx_time=(start, end))`. There is no
  Object Query `.where(...)` refinement in this slice and no `distinct`, offset,
  pagination, projection, count, aggregation, execution, or serialization
  method. The lower-level Predicate algebra likewise carries no distinct node:
  an Object Query always returns complete root Entities, navigation lowers through
  existence tests, and included graphs are fetched separately. Duplicate roots
  are therefore a lowering or identity-resolution defect, not a condition for
  callers to mask. Distinct projection semantics belong to the future
  aggregate/projection query contract.
  `include(*relationship_paths)` requires at least one path and accumulates
  across calls; passing several paths in one call is equivalent to passing them
  in successive calls. Canonical deep-fetch planning deduplicates shared and
  equivalent effective relationship hops. `order_by(*sort_keys)` likewise
  requires at least one key and accumulates across calls; successive calls
  append keys exactly as if supplied in one call. Sort-key order is precedence
  order. The same resolved Attribute Identity may occur only once across the
  complete accumulated ordering, regardless of direction; a duplicate within
  one call or across calls raises
  `QueryDefinitionError(query-clause-invalid)` while constructing the new Find
  Query. Duplicate keys are never silently removed. Each Sort Key is exactly
  one top-level scalar Attribute Expression, optionally converted with
  `.asc()` or `.desc()`. A bare Attribute Expression means ascending and lowers
  with the core default direction omitted; explicit `.asc()` and `.desc()`
  lower their named direction. Null placement defaults to last for either
  direction. Only a Sort Key already created by `.asc()` or `.desc()` may add
  `.nulls_first()` or `.nulls_last()`; a bare Attribute Expression exposes
  neither placement modifier. Placement is single-shot, so a second modifier
  raises `QueryDefinitionError(query-expression-invalid)`. The explicit choice
  lowers to core's shared `nulls: first | last` value.
  Inherited Attributes are valid, and a
  subtype-declared
  Attribute is valid after the root narrow that establishes its scope. Nested
  Value Object members, Relationship traversals, computed expressions,
  literals, and arbitrary functions cannot form Sort Keys; attempting to do so
  raises `QueryDefinitionError(query-expression-invalid)`. This surface does not
  extend core `orderBy` beyond its Attribute Reference.
  `limit(count)` is
  single-shot: calling it on an Object Query that already carries a limit raises
  `QueryDefinitionError(query-clause-invalid)` rather than replacing or
  tightening the original limit. Code that needs alternate limits derives each
  query from the same unbounded base. Its argument must be a positive built-in
  `int`; `bool`, zero, negative values, other numeric types, and coercible
  values raise `QueryDefinitionError(query-clause-invalid)` without coercion.
  A limit does not require ordering and never injects an implicit primary-key
  Sort Key. Without `order_by(...)`, both row order and which rows survive the
  cap are unspecified; deterministic selection requires caller-authored
  ordering.
  The `ObjectQuery.narrow(...)` clause establishes subtype scope for subsequently
  added sort keys. A key is legal only when its Attribute is available on every
  concrete subtype in the query's effective set at the moment `order_by(...)`
  is called. Thus
  `Animal.where(Animal.all).narrow(Dog).order_by(Dog.bark_volume.desc())` is
  valid, while spelling `order_by(...)` before `narrow(Dog)` is refused;
  later clauses never retroactively legalize an invalid intermediate query.
  This one rule is **stated statically and only statically**: `order_by`'s
  parameter reads the result the receiver carries where the call is written, so
  a subtype's Sort Key against an un-narrowed result is a type error in the
  editor. No model-aware rule restates it, and none could — clause order does
  not reach the wire, so ordering before narrowing and narrowing before ordering
  build one canonical query that no validator can accept in one spelling
  and refuse in the other.
  A first include hop may be authored through any descendant of the Object Query
  target, whether that Entity declares the relationship or inherits it; the
  Entity it is authored through is the path's conditional source set. Legality
  is measured against the query's **effective position** — the target's own
  position — so the source Entity must resolve to a nonempty subset of it. A
  broad root therefore admits every descendant of its target, a path authored
  through the target itself remains broad, and a source outside the position is
  refused; a later clause never repairs it. That refusal has both halves: the
  path parameter is covariant in its source, so a source outside the target's
  own subtree is a type error where the call is written, and a source the
  connected model puts outside the effective position is refused at execution
  preflight as `ModelRejectedError`. Thus
  `Animal.where(Animal.all).include(Dog.doghouse, Cat.ball_of_yarn)` is valid
  and loads `doghouse` only on Dogs and `ball_of_yarn` only on Cats, while
  `Pet.where(Pet.all).include(WildBoar.owner)` raises: the query's position is
  `{Dog, Cat}` and the sibling `WildBoar` lies outside it.
  The `ObjectQuery.narrow(...)` clause constrains the **result**, not which sources
  are legal. It narrows the queried objects a path can start from, so a source
  disjoint from it admits none of them and populates the view nowhere — the
  same observation as a source no result row happens to match, never an error.
  Thus
  `Animal.where(Animal.all).narrow(Dog, Cat).include(
  Animal.owner, Dog.doghouse, Cat.ball_of_yarn)` loads `owner` for Dogs and
  Cats, `doghouse` only for Dogs, and `ball_of_yarn` only for Cats.
  The planner gathers keys only from matching root objects and populates the
  ordinary relationship view only on those objects.
  A path retains the Entity Identity through which its first relationship was
  accessed separately from the canonical Relationship Identity. Consequently
  `Dog.owner` retains relationship identity `Animal.owner` while carrying Dog
  as its source guard and loads `owner` only on Dog-family roots;
  `Animal.owner` remains broad. `Dog.doghouse` follows the same rule regardless
  of the relationship's declaring type. Canonical Include Paths are closed
  objects with a required nonempty `segments` list and an optional
  `appliesTo`. The latter reuses the shared Subtype Selection
  contract: it guards the path's initial Entity
  position, not the Object Query result. Each relationship segment retains its
  existing optional target `narrowTo`. A path is therefore an optional
  source guard followed by alternating relationship segments and
  target-position selections; each target position becomes the next segment's
  source. This expresses multi-level inheritance traversal without per-hop
  source metadata.
  Existing hop-target narrowing remains valid and distinct:
  `Person.pets.narrow(Dog).doghouse` stores Dog narrowing on the `pets` segment,
  populates the `pets[Dog]` view, and continues through `doghouse`; root-source
  guarding does not create a narrowed relationship view.
  `include(Person.pets, Person.pets.narrow(Dog).doghouse)` performs separate
  broad `pets` and narrowed `pets[Dog]` fetches. The planner does not reuse a broad
  view for subtype-conditional continuation; branches use separate paths and
  broad versus target-narrowed hops retain their distinct view and round-trip
  semantics. The effective path-root source set is fetch-hop identity at the
  root position: two prefixes whose guards resolve to the same source set
  deduplicate, and any two that resolve to different sets stay distinct. Broad
  is the unguarded source set rather than a separate kind, so a proper guard —
  every guard that admits fewer than all root objects — differs from broad
  automatically, while a guard admitting every root object is the broad path.
  The planner does not union separately guarded source sets. Consequently
  `include(Dog.owner, Cat.owner)` performs two owner hops, while
  `include(Animal.owner)` performs one broad owner hop whose single child query
  receives the deduplicated parent keys from every active Dog and Cat root.
  Paths `Dog.owner` and `Dog.owner.address` share their identical guarded
  prefix. The core expansion updates `m-predicate`, its schema,
  `m-inheritance`, `m-deep-fetch`, `m-sql`, semantic validation, planning,
  compatibility cases, and claiming frontends atomically.
  `Entity.where(...)` requires at least one Predicate, as a required positional
  parameter, so the empty call is refused by the parameter rather than by a
  clause rule: `Entity.where()` is a static error and Python's own call binding
  raises `TypeError`. A dynamically expanded argument sequence is no different,
  because expansion precedes binding — `Entity.where(*predicates)` over an empty
  `predicates` binds no first argument and raises the same `TypeError`, never
  reaching an Object Query. No `QueryDefinitionError` code answers an empty
  `where(...)`.
  `Entity.all` is the
  non-callable, target-bound Predicate spelling an explicitly
  unfiltered query and lowers to the canonical `all` predicate:
  `Animal.where(Animal.all)`. It is legal only as the sole `where(...)`
  argument. Combining it with another Predicate, whether variadically or
  through Boolean operators, raises
  `QueryDefinitionError(query-expression-invalid)` rather than silently
  simplifying redundant input. There is no `Entity.all()` Object Query
  constructor; `Entity.where(...)` remains the sole query constructor.
  `AllPredicate[E]`'s parameter is the **only** place an unfiltered query
  written at another position is refused: `Animal.where(Dog.all)` is a static
  error, and it is one of the static rejections with no model-aware twin,
  because an `all` node names no position — `Dog.all` and `Animal.all` lower to
  the byte-identical `{"all": {}}` at the same target, which is a valid
  query there is nothing for preflight to refuse.
  `as_of(...)`, `history(...)`, and `as_of_range(...)` form one axis-keyed
  temporal-clause family. Each declared dimension is single-shot: a second
  selection for one dimension raises
  `QueryDefinitionError(query-clause-invalid)`, while separate calls selecting
  different dimensions merge into one canonical query. Mixed variants compose
  in either call order, so `.history(VALID_TIME).as_of(tx_time=LATEST)` and its
  mirror lower identically. A call never replaces an earlier selection.
  Each keyword-based method requires at least one supplied dimension;
  zero-argument `as_of()` and `as_of_range()` calls raise
  `QueryDefinitionError(query-clause-invalid)`. A supplied range must be an
  exact built-in two-item `tuple`; lists, tuple subclasses, arbitrary
  iterables, and coercion are rejected with the same error.
  Independent clause invocation order never changes the canonical query, and
  does so by construction rather than by normalization: every clause is a sibling
  of every other, so there is no order for invocation to record. Thus permuting
  otherwise valid `include`, `order_by`, `limit`, `narrow`, and
  temporal calls produces the identical canonical query. That
  does not weaken the static scope rule: a subtype-specific sort
  key still requires a preceding result narrowing where `order_by(...)` is
  written.
  `Entity.narrow(*subtypes, where=...)` remains the scoped Predicate
  constructor; result-set `ObjectQuery.narrow(*subtypes)` accepts no `where=` and
  is single-shot. Calling it on an already narrowed Object Query raises
  `QueryDefinitionError(query-clause-invalid)`. Every Python narrowing form
  requires at least one subtype alternative. Repeating the same subtype identity
  raises `QueryDefinitionError(query-path-invalid)` during authoring. Whether
  distinct alternatives overlap after inheritance expansion is model-dependent
  and is rejected by model-aware preflight.
  Only `Database.find(query)` and `Transaction.find(query)` execute it.
- **Finder/query entry point.** A free-standing, side-effect-free Object Query is
  built from classmethods on the Entity Class and executed by the Parallax
  Handle. Nonempty variadic `where(*predicates)` conjoins its arguments (the
  natural big-AND of filter criteria), while `where(Entity.all)` is the
  explicit unfiltered spelling. An Object Query has no further `.where()` method.

  ```python
  query = Order.where(
      Order.order_id == 42,
      Order.items.exists(OrderItem.sku.in_(["A", "B"])),
  )
  snapshot = db.find(query)
  ```

  Canonical `m-object-query` serialization of that Object Query:

  ```yaml
  objectQuery:
    target: Order
    predicate:
      and:
        operands:
          - eq: { attr: Order.orderId, value: 42 }
          - exists:
              rel: Order.items
              op:
                in: { attr: OrderItem.sku, values: [A, B] }
  ```

  Relationship predicate paths always carry an explicit cardinality-neutral
  quantifier (`.exists(...)` or `.not_exists(...)`);
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
- **Boolean query inputs.** `.is_(...)` accepts only exact built-in `True` or
  `False`. The keyword-only `case_insensitive=` option on top-level and nested
  string predicates likewise accepts only an exact built-in `bool`; integers,
  strings, and arbitrary truthy objects raise
  `QueryDefinitionError(query-expression-invalid)` without coercion. Omitting
  the option and explicitly passing `False` lower to the same canonical node
  with `caseInsensitive` absent; `True` emits the canonical true flag.
- **Null-test spellings and membership.** Every comparison, range, membership,
  string-pattern, or `.is_(...)` operand of Python `None` raises
  `QueryDefinitionError(query-expression-invalid)` during expression authoring,
  regardless of member nullability. The message directs the caller to
  `.is_null()` / `.is_not_null()`; `== None` and `!= None` are not null-test
  aliases. The named null-test methods require a nullable resolved leaf and raise
  the same error immediately for a non-nullable top-level, nested, or
  element-scoped leaf. Direct or deserialized Predicate null-check nodes retain
  the model-aware `null-check-non-nullable-member` rejection. A value collection
  supplied to `.in_(...)` or `.not_in(...)` must not contain `None`. Any `None`
  member raises
  `QueryDefinitionError(query-expression-invalid)` during expression
  construction. The frontend neither exposes provider three-valued membership
  surprises nor silently rewrites membership into an `isNull`/`isNotNull`
  Boolean combination. The collection must also be nonempty, as required by
  the canonical Predicate algebra: `.in_([])` and `.not_in([])` both raise
  `QueryDefinitionError(query-expression-invalid)` rather than normalizing to
  match-none or match-all Predicates. Each method accepts exactly one
  collection, whose runtime type must be the built-in `list` or `tuple`. The
  frontend immediately copies it into immutable Predicate storage, preserving
  order and duplicate values exactly. Strings, sets, generators, list/tuple
  subclasses, custom iterables, and coercion raise the same error.
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
  idiomatic predicate can never drift from canonical form over grouping. The
  internal group node type exists for serde/tooling and is not public API.
- **Value-object predicates.** Nested value-object paths reuse chained
  class-level attribute access: `Customer.address.city == "Berlin"` builds the
  flat `nestedEq` node carrying the dotted canonical path
  (`nestedEq: { path: Customer.address.city, value: Berlin }`). The scalar
  operator surface maps one-to-one onto the flat `nested*` family. `==` / `!=`
  / `>` / `>=` / `<` / `<=` serialize to `nestedEq` / `nestedNotEq` /
  `nestedGt` / `nestedGte` / `nestedLt` / `nestedLte`; `.between(...)` to
  `nestedBetween`; `.in_(...)` / `.not_in(...)` to `nestedIn` /
  `nestedNotIn`; `.like(...)` / `.not_like(...)` / `.starts_with(...)` /
  `.ends_with(...)` / `.contains(...)` to `nestedLike` / `nestedNotLike` /
  `nestedStartsWith` / `nestedEndsWith` / `nestedContains`; and `.is_null()` /
  `.is_not_null()` to `nestedIsNull` / `nestedIsNotNull` (core's
  absence-collapse semantics). Nested string predicates share the top-level
  case-insensitive option, wildcard escaping, and bind ordering. Descriptor-
  seeded top-level, nested, and element-scoped paths retain enough declaration
  Metadata to resolve every deeper segment when the expression is authored. An
  undeclared segment raises `QueryDefinitionError(query-expression-invalid)` at
  that access, and a typed operation on a metadata-free directly constructed
  expression raises the same error rather than falling back to Wire semantics.
  Every native operand then passes through `coerce_neutral_input`, managed
  membership, and `encode_wire` for the resolved leaf; a mismatch is immediate
  `QueryDefinitionError(query-expression-invalid)`, never a serialized
  `neutral-literal-*` failure. Direct Predicate nodes and deserialized mappings
  retain model-aware path resolution and Wire decoding at execution preflight.
  A flat predicate whose path crosses a `multiplicity: many`
  member keeps the flat node and therefore core's **any-element** semantics:
  each such predicate matches independently, so two ANDed flat predicates may
  be satisfied by *different* elements. **Same-element** composition and
  member-presence tests hang off the value-object-terminated path:
  `.exists(*predicates)` serializes to `nestedExists { path, where }` and
  `.not_exists(*predicates)` to `nestedNotExists { path, where }`; zero arguments
  emit the bare presence/non-empty (`nestedExists`) or absent/empty
  (`nestedNotExists`) node with no `where`. Variadic arguments conjoin exactly
  like `where(*predicates)`; inside the scope, sub-predicates are built from
  the value-object class's own class-level attributes and serialize as
  **element-relative** paths (`type`, `geo.country` — no leading entity
  prefix), composing with `&`/`|`/`~` and parentheses. An element-scoped
  expression is valid only inside an `.exists(...)`/`.not_exists(...)` over that
  element type; a stray one builds an element-relative path the queried Entity
  declares no member for, and is refused at execution preflight under the
  nested-path rules.
  Every new nested operator is also valid on these element-relative paths. A
  flat operator crossing a Many occurrence retains core's any-element
  semantics, but one element must satisfy the complete operator:
  `nestedBetween` is a dedicated canonical node and never lowers to two
  independent flat comparisons that different elements could satisfy.
  A nested `between(lower, upper)` validates both bounds against the leaf's
  declared neutral type, exactly as every other nested literal is validated.
  Top-level and nested `between` alike then compare the two bounds where every
  other model-aware predicate rule is stated — `validate_predicate`, reached at
  execution preflight for a read and at the write boundary for a
  predicate-selected write: a `lower` strictly greater than its
  `upper` names an empty range and raises
  `ModelRejectedError(between-bounds-inverted)` rather than compiling to a
  `BETWEEN` that silently matches nothing. Both bounds first decode through
  `m-wire` against the same resolved leaf declaration; only after both succeed
  are their managed values compared. Equal managed bounds stay legal, while a
  conversion failure wins over ordering. Semantic interval APIs such as
  `as_of_range(...)` keep their own ordered-endpoint requirement.

  A nested string predicate is legal only over a `String` member. `Date`, `Time`,
  `Timestamp`, `Uuid`, and `Bytes` all ride the algebra's portable `string`
  literal, so a pattern against one would otherwise satisfy the typed-literal
  check and lower text matching against a value that is not text; the member's own
  declared type is checked first, and a mismatch raises
  `ModelRejectedError(nested-string-predicate-non-string-member)` at
  execution preflight.

  ```python
  Customer.where(
      Customer.address.phones.exists(
          Phone.type == "home",
          Phone.number == "555-9999",
      )
  )
  ```

- **Deep-fetch/include spelling.** Chained attribute paths on the Object Query:
  `Order.where(...).include(Order.items.statuses, Order.tags)`. One path
  grammar shared with predicates; longer paths imply their intermediates
  (glossary Relationship Path). The first hop is statically typed via descriptor
  `__get__` overloads; deeper hops are composed dynamically from the path's own
  target and the member's spelling, because authoring reaches no model, and
  every hop's legality — an undeclared or renamed relationship, a value-object
  segment, an illegal hop narrow — is validated against the connected model at
  execution preflight, never at the database. An access class equal to the Object Query target authors
  a broad path root. An access class naming a descendant authors the path's
  `appliesTo` guard and is legal whenever it resolves to a nonempty subset
  of the query's effective position; the `ObjectQuery.narrow(...)` clause constrains
  the result rather than the legal sources, so it neither grants nor withholds
  that legality. The canonical Relationship Identity remains the
  declaration identity, so inherited `Dog.owner` is relationship
  `Animal.owner` guarded to Dog-family roots. Each relationship segment may
  independently retain its existing target `narrowTo`, and that narrowed
  target is the source position of the next segment. Every later segment
  resolves relative to that immediately preceding target position—after any
  target narrowing—never relative to the path root, the previous relationship's
  declaring Entity, or an unqualified local Entity name. Structured Entity and
  Relationship Identities retain namespaces throughout resolution. The
  cross-namespace proof is
  `sales.SalesOrder.customer -> crm.Customer` followed by
  `crm.Customer.notes`: Python
  `SalesOrder.where(SalesOrder.all).include(SalesOrder.customer.notes)` and the
  equivalent corpus-authored query document must accept and execute the
  same structured path. Separate paths express subtype branches. A broad
  relationship view and a target-narrowed view remain distinct observable
  views and separate fetch hops; the planner does not reuse the broad view for
  conditional subtype descent.
- **Known limit — a Python-authored relationship chain stops at two hops.** The
  canonical contract sets no depth maximum and the serialized ingress accepts
  any depth, but this target's authoring surface reaches only two. A composed
  hop spells its own segment as `<its target's local name>.<member>`, and after
  one continuation the path no longer knows what its last hop points at, so a
  third authored hop raises `AttributeError` naming the remedy: root the deeper
  traversal at the Entity the next hop is declared on and add it as its own
  `include(...)` path. `SalesOrder.customer.notes` above is a **two**-hop path
  and is within the limit. Two consequences follow and are deferred with it: a
  multi-hop relationship quantifier is unauthorable, so `exists(...)` /
  `not_exists(...)` are single-hop on this surface however deep the canonical
  nesting may go; and the deepest include path a Python caller can author is
  shallower than the deepest a canonical query document may carry. Lifting
  the limit needs a way for a composed segment to name its owner without
  reaching a model at authoring time; no correct one exists today, and deferring
  the owner to preflight is not admissible — the canonical relationship
  reference grammar admits exactly `Owner.member` and no marker form, and a
  canonical field never holds a non-canonical value.
- **Relationship existence predicates.** A Relationship Path exposes
  `exists(*predicates)` and `not_exists(*predicates)` for either to-one or
  to-many cardinality. Zero arguments mean pure path existence or absence.
  Multiple arguments are conjoined in the terminal related-Entity scope, so one
  terminal object must satisfy every argument; separate `exists(...)`
  predicates may be satisfied by different terminal objects. A multi-hop path
  lowers mechanically to nested canonical `exists` nodes — a rule this target
  states and does not yet reach, because the two-hop authoring limit above keeps
  the quantifier single-hop. `not_exists(...)`
  negates existence of that complete nested chain by using `notExists` at the
  outermost hop; it does not negate every hop independently. Hop narrowing
  becomes the corresponding nested `narrow` scope. Callers needing predicates
  on intermediate Entities use explicit nested `exists(...)`; direct multi-hop
  arguments always target the terminal Entity. Predicate inversion recognizes
  existence nodes: `~path.exists(...)` lowers identically to
  `path.not_exists(...)`, and `~path.not_exists(...)` to `path.exists(...)`.
  The same normalization maps `nestedExists` and `nestedNotExists` for Value
  Object occurrence paths. Python therefore retains the general `~predicate`
  idiom without creating a second canonical shape for existence negation.
- **Uniform existence vocabulary.** Value Object occurrence paths use the same
  `exists(*predicates)` / `not_exists(*predicates)` names, lowering to
  `nestedExists` / `nestedNotExists` instead of relational navigation. On a One
  occurrence, zero arguments mean present or absent; on a Many occurrence they
  mean nonempty or empty. Multiple predicates must match the same occurrence.
  The Python surface exposes no `any()` or `none()` methods.
- **Subtype narrowing.** The canonical `narrow` node is spelled with the
  class-level constructor `Entity.narrow(*subtypes, where=...)` on the
  polymorphic position's class, serializing to
  `narrow: { to, operand }`. Context supplies the position; `to` is the shared
  Subtype Selection in canonical Entity Identity order, and `operand` is the
  `where=` expression (omitted ⇒ `all`).
  Inside `where=`, subtype-declared attributes become predicable
  (`Animal.narrow(Dog, where=Dog.bark_volume > 3)`); referencing one outside a
  compatible narrow scope is a static error where the term is written — the
  `where=` parameter is measured against the named subtypes — and is refused
  again at execution preflight, against the connected model, as
  `ModelRejectedError(subtype-attribute-outside-narrow-scope)`. Predicate
  construction itself judges neither: authoring reaches no model, so a built
  Predicate carries the reference and the position settles it. A narrow
  expression is an
  ordinary predicate, so separately narrowed branches compose with the
  Boolean operators:

  ```python
  Animal.where(
      Animal.narrow(Dog, where=Dog.bark_volume > 5) | Animal.narrow(Cat, where=Cat.indoor.is_(True))
  )
  ```

  serializes to `or` over two `narrow` nodes, branch order preserved. Inside a
  relationship quantifier, the quantifier supplies its relationship target as
  the active position. `Person.pets.exists(Pet.narrow(Cat))` and
  `Person.pets.exists(Animal.narrow(Cat))` therefore lower identically: the
  receiver class grants Python predicate scope while the wire retains only the
  selection. A selection escaping the target is refused at execution preflight
  as `ModelRejectedError(narrow-outside-relationship-target)`. The
  Object Query clause
  `Animal.where(...).narrow(Dog, ...)` is the whole-query form: it fills the
  query's own `narrowTo` clause and is single-shot like `as_of`. It is a
  **pure result-set narrowing**, and the same narrowing is stated by passing
  `Entity.narrow(...)` to `where(...)` as the WHOLE filter — a narrowing that is
  the entire selection narrows the result, so it fills `narrowTo` and its own
  scoped predicate becomes the query's predicate. Statically, each `where`
  argument is measured against the position the query is at where the call is
  written and a later clause never retroactively legalizes it, so
  `Animal.where(Dog.bark_volume > 3).narrow(Dog)` is a static error at the
  `where` and the statically valid spelling is
  `Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3))`, which narrows
  before the predicate is measured. Like the sort
  key's own clause-order rule above, **this one is stated statically and only
  statically**: the clause and the constructor converge on the identical
  canonical query — `narrowTo [Dog]` over the predicate
  `greaterThan(Dog.barkVolume, 3)` — so
  neither spelling can drift, and no model-aware rule can accept one and refuse
  the other. A narrowing reached through a Boolean combinator qualifies one term
  of the selection and stays in the predicate. On an include path,
  `.narrow(*subtypes)` on a hop
  (`Owner.pets.narrow(Dog)`, continuable to deeper hops) serializes to the
  path segment's `narrowTo` and requests a distinct **narrowed
  view** (§3). Narrowing is single-shot per path segment:
  `Owner.pets.narrow(Cat, Dog).narrow(ServiceDog)` raises
  `QueryDefinitionError(query-path-invalid)` rather than intersecting or
  replacing the first subtype set. Continuing to another relationship creates
  a new segment that may independently narrow its own polymorphic target.
  Everywhere, the resolved set must stay within the **enclosing
  effective concrete-subtype set** — the threaded active position, re-narrowed
  at every hop and by every enclosing `narrow` scope, never the declared base
  type — so a nested same-position narrow can only constrain the position
  further, and one that broadens back out (a `Cat` narrow inside a `Dog`
  scope) builds and is refused at execution preflight as
  `ModelRejectedError(narrow-outside-position)`, the corpus's
  threaded-position rule. Which concrete subtypes a class resolves to is a
  per-model fact, so the threading is the connected model's to do.
- **What a narrowing signature does not judge.** `Entity.narrow(*subtypes,
  where=...)` and `ObjectQuery.narrow(*subtypes)` solve their parameter from the
  named classes and spend it on what the narrowing produces: the first measures
  the scoped `where=` against them, and the second moves the result parameter to
  their union. The overload set that moves it is fixed at one, two, and three
  alternatives, so a dynamically expanded or longer list falls to a conservative
  variadic overload that leaves the result parameter where it was. Neither form
  can also constrain what the selection starts from; `Animal.narrow(Dog)` and
  `Order.narrow(Customer)` are therefore alike accepted by the checker, and the
  latter is refused by the model-aware `narrow-outside-position` rule. A hop
  narrow retains its static half because its receiver carries the relationship
  target: `Owner.pets.narrow(Dog)` requires subtype classes compatible with that
  target. In every form, the wire carries one canonical Subtype Selection and
  model-aware pairwise disjointness remains execution preflight's question.
- **Temporal-read spelling.** Query-level and dimension-keyed, with Valid
  Time and Transaction Time as the only public vocabulary:

  ```python
  Balance.where(...).as_of(tx_time=t)
  Position.where(...).as_of(valid_time=v, tx_time=t)
  Balance.where(...).history(TX_TIME)
  Balance.where(...).as_of_range(tx_time=(start, end))
  ```

  `history` takes its dimension as the module-level `VALID_TIME` / `TX_TIME`
  constants — `Final` singleton values exported from `parallax.core` in the
  `LATEST` sentinel's pattern; a string dimension argument is rejected at
  Object Query construction.
  Timestamps are timezone-aware `datetime` values, normalized to UTC,
  microsecond precision; naive datetimes are rejected at Object Query
  construction. Every `as_of_range(...)` window is an exact built-in
  two-item `tuple` of finite such instants with `start < end`; lists, tuple
  subclasses, arbitrary iterables, coercion, and `LATEST` endpoints raise
  `QueryDefinitionError(query-clause-invalid)`. An omitted Transaction-Time
  selection defaults to **latest** where the canonical query is read; the
  module-level `LATEST` sentinel spells the same pin explicitly and builds
  the identical canonical selection. An omitted Valid-Time
  selection on a Bitemporal target raises
  `QueryDefinitionError(query-clause-invalid)` there because Latest
  would make a substantive claim about the business timeline rather than merely
  selecting current database knowledge. Canonical serialization is
  deterministic: the Temporal Selection clause is a map keyed by dimension, so it
  carries exactly one selection per declared dimension in canonical dimension
  order. Latest always
  uses the canonical value and never `now`. There is no Now variant: a finite
  current-clock datetime is an ordinary finite coordinate and lowers to
  containment rather than Latest's `end = infinity`. `as_of()`
  with no dimension raises `QueryDefinitionError(query-clause-invalid)` rather
  than duplicating the ordinary query's implicit-latest behavior;
  `as_of_range()` likewise rejects an axis-free scan. A later temporal call may
  select only a dimension not already selected; selecting the same dimension
  twice raises `QueryDefinitionError(query-clause-invalid)`.
  Rejected at build: pinning or scanning an axis the entity does not declare,
  temporal clauses on non-temporal entities, and conflicting double pins.

### Declaration and descriptor-input grammar

A model enters the runtime through exactly two fixed sources: Python Entity
Classes composed into a `DomainModel(*classes)`, or a canonical descriptor
through the optional `parallax.descriptor` Descriptor Frontend. That frontend
creates a Domain Model through a private first-party source seam; descriptor
ingestion and export are not `DomainModel` methods. Sources are never mixed. Entity
Classes are implicitly frozen Pydantic classes built by the Parallax
metaclass; `frozen=True`, `EntityConfig`, `__parallax__`, `Field`,
`Relationship`, `VoField`, and every registry surface are removed, not
deprecated. The grammar below is exhaustive: an authoring form not listed
here does not exist. The API Conformance Suite closes the frontend loop by
authoring idiomatic classes for corpus models and asserting their exported
descriptors structurally equal the corpus YAML, which is authored in
canonical minimal spelling (the no-drift guard). Frontend equivalence is
qualified by authoring reach: for models both grammars can author, the two
frontends expose identical normalized facts and formation outcomes;
grammar-level failures stay representation-specific — the descriptor rejects
through its ingestion phases, Python through class creation — so a shape
only one grammar can spell, or can reject before the shared seam, carries no
equivalence obligation.

#### Spelling the core algebra values

Class headers and the `attr`/`rel`/`index` factories name the members of the
closed core algebras directly rather than through string keywords, so an
unspellable combination is a static error before it is a runtime one. Which
Python spelling a member takes follows from the member itself, and the rule
holds for every algebra value the grammar reaches, including ones added later:

- A variant carrying no payload is a module-level SCREAMING_SNAKE constant —
  `READ_ONLY`, `ONE_TO_ONE`, `MANY_TO_ONE`, `ONE_TO_MANY`,
  `TABLE_PER_CONCRETE_SUBTYPE`, `MAX`. Enumerated algebras follow the same
  spelling through their member access (`TemporalDimension.VALID_TIME`).
- A variant carrying a payload is a CamelCase class instantiated at the call
  site — `Sequence(...)`, `TablePerHierarchy(...)`, `AbstractRoot(...)`,
  `ConcreteSubtype(...)`. Where every parameter of such a class is optional, the
  bare class object reads as the empty instance: `inheritance=AbstractSubtype`
  and `inheritance=AbstractSubtype()` are the same declaration.

Neutral Types are a separate vocabulary and keep their CamelCase type names
(`Int32`, `Float32`, `Int64`, `Decimal`), because `attr(type=)` names a type
rather than an algebra member.

The core specification names the same algebras and variants in CamelCase
(`Cardinality`, `ManyToOne`, `Inheritance`, `TablePerConcreteSubtype`). Those
are model vocabulary shared by every language target; the spellings above are
the Python identifiers an author actually types.

#### Class headers

| Keyword | Value | Applies to | Meaning |
|---|---|---|---|
| `table=` | `str` | standalone entities, TPH roots, TPCS concrete subtypes | the physical `Table(name)` Storage Container — always explicit, never derived from a name; forbidden on TPH descendants and TPCS roots/abstract subtypes (formation-time family rules) |
| `name=` | `str` | any Entity | canonical Entity-name override — any nonempty dot-free string; omission means the class `__name__` verbatim |
| `namespace=` | `str` | any Entity | the Entity Identity namespace, declared per class and never inherited from a base class or module; omitted means unnamespaced |
| `persistence=` | `READ_ONLY` | standalone entities and family roots | the exceptional read-only mapping; omission means Read Write; any descendant declaration is a formation-time issue |
| `layout=` | `Document(column="...")` | standalone entities and family roots | the exceptional Relational Document Layout mapping; omission means conventional Columns storage; any descendant declaration is a formation-time issue |
| `inheritance=` | role value (below) | every family participant | the participant's inheritance role |
| `indices=` | tuple of `index(...)` values | any Entity | the local physical indices |

The Entity name is the class `__name__` verbatim — no case conversion —
and `name=` overrides it for spellings a Python class name cannot carry,
mirroring `attr(name=)`. A standalone Entity (no `inheritance=`) that omits
`table=` fails at class creation (`entity-header-missing-option`), the parity
of the descriptor schema's phase-2 `table` requirement; family table
incoherence (a TPH descendant declaring `table=`, a TPCS concrete omitting
it) stays the formation-time `inheritance-*` issue family.

`layout=` mirrors `persistence=` exactly, including its asymmetry. `Document` is
the only spellable value, because `Columns` is what an omitted keyword means and
the canonical descriptor writes no `layout` property for it (`m-descriptor`);
exposing a second spelling for the default would add a way to say nothing.
`Document`'s `column=` is optional and **defaults to `payload`**, so
`layout=Document` and `layout=Document()` are the same declaration as any other
all-optional variant class, and `layout=Document(column="body")` overrides the
name.

The default is an **authoring** convenience, not a metadata default. The
frontend resolves the Structured Column name during normalization, so accepted
metadata and the exported descriptor always carry it explicitly at
`layout.document.column` — an author who writes `layout=Document()` sees
`column: payload` in the descriptor. No consumer, schema position, or
diagnostic downstream of authoring ever sees a missing name, so none gains an
optional field. This is the established Python-versus-descriptor
divergence: temporal axes have no keyword at all and come from the base class,
and a relationship's omitted ordering direction and null placement normalize to
Ascending and NullsLast.

A malformed `layout=` value — anything that is not `Document` or a `Document`
instance, or a `column=` that is not a nonempty string — fails at class creation
as `entity-header-invalid-value`, like every other ill-typed header value.
Everything semantic about the layout is formation-time: a descendant declaring
one is `inheritance-layout-not-root-owned`, and a Column Override on a
document-resident member, an Index over a document-resident Attribute, or a
Structured Column colliding with a direct column are the `storage-layout-*`
issues below. The frontend performs no role classification, because role
classification needs the whole model.

A local Entity name may be declared in more than one namespace of one model:
the Entity Identity is what must be unique, and the qualified identities differ.
Such an Entity remains declarable, materializable, and queryable through its
family root — the constraint is at the **reference site**, not on the
declaration. A position that names an Entity spells it either canonically as
`<namespace>.<Entity>` or bare, and the bare spelling is legal exactly where it
resolves to one declared Entity — so a bare name two namespaces of the connected
model share resolves to no Entity and the query is refused as
`ModelRejectedError(reference-ambiguous-entity-name)`, naming the canonical
spellings that would resolve. The rule governs every such position — an
attribute or nested-path reference, a relationship reference, a Sort Key, the
query's own `narrowTo` and each alternative of a predicate `narrow`, and an
Include Segment with its narrowing — and is distinct from
`attribute-outside-active-position`, which fires when a reference *does* resolve
and resolves outside the active position. A serialized write instruction's
ambiguous `entity` is the write family's own `WriteInstructionError` rather than
this rule, because that name is the instruction's target rather than a reference
inside a query.

Every Entity Class declares exactly one Parallax base: a framework root
(`Entity`, `TxTemporal`, `Bitemporal`) or exactly one domain Entity
parent. A second Entity base or any non-Parallax mixin is outside the
grammar, and a domain-Entity subclass must declare `inheritance=` — omission
is never an implicit role. Both fail at class creation
(`entity-base-invalid`).

Temporality is selected by the base class — `Entity`, `TxTemporal`, or
`Bitemporal` — never by a keyword, and each base names the `temporality`
profile a descriptor spells: none, `transaction-time`, and `bitemporal`. Both
frontends then reach the `m-metamodel` seam through the one derivation
`m-descriptor` fixes, so `TxTemporal` supplies the reserved read-only
`tx_start`/`tx_end` attributes (canonical `txStart`/`txEnd`, framework-fixed
`in_z`/`out_z`) and `Bitemporal` additionally supplies
`valid_start`/`valid_end` (canonical `validStart`/`validEnd`, framework-fixed
`from_z`/`thru_z`). The Python spelling of each is the canonical name folded by
`default_column_name`, the inverse of the snake-to-camel conversion the
authoring boundary applies to every other member. A descendant inherits its
root's temporal base and cannot change shape. Redeclaring a reserved temporal
name is the shared `metamodel-temporal-member-reserved` rule; the Python
frontend enforces it earlier and more broadly, rejecting the redeclaration at
class creation as `entity-reserved-member-name` (below) for all four canonical
names anywhere below a temporal base. An unknown header keyword or ill-typed
value also fails at class creation (`EntityDefinitionError`, below).

The `inheritance=` value mirrors the core `Inheritance` algebra with the
parent supplied by Python subclassing:

| Role value | Family position | Carries |
|---|---|---|
| `AbstractRoot(TablePerHierarchy(tag_column="..."))` | TPH family root | the strategy and shared-table tag column; the root declares `table=` |
| `AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)` | TPCS family root | the strategy; no `table=` |
| `AbstractSubtype` (bare) | abstract interior node | nothing |
| `ConcreteSubtype(tag_value="...")` | TPH concrete subtype | its tag value; no `table=` |
| `ConcreteSubtype` (bare) | TPCS concrete subtype | nothing; declares its own `table=` |

The variant is the role, so strategy on a descendant, a tag value on a root,
or a tag under TPCS is unspellable. Family-semantic violations that remain
spellable (a TPH descendant declaring `table=`, a descendant `persistence=`,
zero or multiple roots, missing or duplicate tag values) are formation-time
`inheritance-*` issues; the two frontends enforce the same accepted-model
invariants, while the rejection phase and surface remain frontend-specific
(the descriptor schema rejects some of these spellings at ingestion, before
formation).

`index(name, *members, unique=False)` declares one local index: a nonempty
ordered sequence of members by Python member name, with the component order
preserved and every component a local scalar Attribute of the declaring
Entity — never a relationship, Value Object, or inherited member. The
factory rejects an empty member list at call time; an unknown, duplicate, or
non-local member name is the formation-time `metamodel-index-*` issue family.

Member references are uniform across the grammar: the strings in `join=`,
`reverse_of=`, `order_by=`, and `index(...)` are Python declaration names
(snake_case, exactly as declared), lowered to canonical identities at the
authoring boundary. Canonical camelCase spellings are descriptor surface and
are never accepted in a class declaration.

#### Attributes — `Attr[T]` and `attr(...)`

`Attr[T]` is the sole scalar and Value Object member annotation; the
assignment slot optionally holds one `attr(...)` value and nothing else — a
bare value (`qty: Attr[int] = 5`) fails at class creation. The complete
`attr(...)` option set:

| Option | Value | Meaning |
|---|---|---|
| `primary_key=` | `False` (default), `True`, `MAX`, or `Sequence(name=..., batch_size=..., initial_value=..., increment_size=...)` | the `NotPrimaryKey \| PrimaryKey(generation)` sum: `True` means `ApplicationAssigned`; a generation value implies primary key, so a generation without a key is unspellable; `MAX`/`Sequence(...)` require an `Int32`/`Int64` member (`m-pk-gen`) and fail at class creation on any other (`entity-option-context-invalid`), while `True` is unrestricted |
| `column=` | `str` | physical Storage Location override; after canonical identity resolution, omission normalizes through `parallax.core.metamodel.default_column_name(<canonical name>)` |
| `name=` | `str` | canonical-name override (below) |
| `max_length=` | `int` | bounded string length |
| `type=` | `Int32` or `Float32` | narrows the two-variant annotation families; `Attr[int]` alone is `Int64` and `Attr[float]` alone is `Float64`, and a narrowing value under any other annotation is a context error |
| `precision=`, `scale=` | `int` | the required `Decimal(precision, scale)` parameters — mandatory together on a `decimal.Decimal` member, forbidden on every other type |
| `read_only=` | `bool` | framework-computed member |
| `optimistic_locking=` | `bool` | names the version column |

**Nullability is annotation-only.** `Attr[int | None]` (equivalently
`Optional[int]`) declares `nullable=True`; `Attr[int]` declares
`nullable=False`. No `attr(nullable=)` option exists: instance reads type as
the annotation, so a separate option could only echo or contradict it. The
Python type inside `Attr[...]` maps to the Neutral Type per the scalar table
below; a `decimal.Decimal` member requires `attr(precision=..., scale=...)`
because the core `Decimal` variant has no default parameters, a Value Object
class reference declares an embedded composite, and `tuple[VO, ...]` declares
a Many occurrence. There is **no direct `json` attribute**: `m-core` reserves
`Json` for the storage type a whole Value Object maps to and makes it
undeclarable on a member, so structured content is always reached through a
Value Object class reference and never through a free-form document annotation.

Generation values and structured narrowing use the same option surface — the
corpus `max` and `sequence` spellings and the two-variant scalar families
author as:

```python
class Ticket(Entity, table="ticket"):
    id: Attr[int] = attr(
        primary_key=Sequence(
            name="ticket_seq",
            initial_value=1000,
            increment_size=5,
        )
    )  # batch_size takes its semantic default
    qty: Attr[int] = attr(type=Int32)  # Attr[int] alone is Int64
    rating: Attr[float] = attr(type=Float32)
    weight: Attr[float]  # Float64 by default


class Widget(Entity, table="widget"):
    id: Attr[int] = attr(primary_key=MAX)
    label: Attr[str]
```

**Canonical naming.** Python members are snake_case; canonical member names
are camelCase. The deterministic snake→camel conversion (drop each
underscore, capitalize the following character) applies at the authoring
boundary, with a class-creation collision check. `attr(name="...")` and
`rel(name="...")` override the canonical name for irregular cases — legacy
vocabularies and acronym spellings the conversion cannot produce:

```python
class LegacyPart(Entity, table="legacy_part", name="LEGACY_PART"):
    id: Attr[int] = attr(primary_key=True)
    tax_id: Attr[str] = attr(name="taxID", column="tax_id")
    bin_no: Attr[str] = attr(column="BIN_NO")  # canonical binNo, legacy column
```

`name=` is who the member is in the model (its Attribute Identity and
descriptor spelling); `column=` is where it is stored. The class-header
`name=` is the same idea for the Entity itself — here the schema entity name
`LEGACY_PART`, which the snake→camel member conversion never touches. Ingested descriptors
keep canonical names; the ambiguous camel→snake direction is never needed
because classes are not generated.

Identity selection always precedes storage selection. `attr(name=...)` wins
over Python's snake-to-camel conversion, then an explicit `attr(column=...)`
wins over the portable default. Without an explicit column, the supported
`parallax.core.metamodel.default_column_name()` operation inserts an underscore
before each ASCII uppercase letter, lowercases it, and preserves every other
character: `personId -> person_id`, `taxID -> tax_i_d`, and
`legacy_ID -> legacy__i_d`. Consequently `attr(name="taxID")` alone stores in
`tax_i_d`; the example declares `column="tax_id"` because acronym-friendly
storage is an explicit override. `attr(name="personId", column="personId")`
likewise preserves a deliberate camelCase physical column. The operation is
not re-exported from `parallax.core`; `parallax.core.metamodel` is its sole
supported import path.

**Reserved member names.** A member name may not collide with a name the class
object already carries, because class-level access is where the typed expression
surface lives and the class-level name would win. Ten families are reserved,
and a collision fails at class creation (`entity-reserved-member-name`). A body
reaches a class-level name in exactly two ways — a binding and an annotation —
because the third, an entry in the body's `__slots__`, is closed by reserving
`__slots__` itself. Seven of them — the `model_*` namespace, the `__parallax_`
prefix, the copy verb `edit`, the pickle entry point `__reduce_ex__`, the schema
seam `__get_pydantic_core_schema__`, the instance-state names Pydantic keys on,
and the object layout `__slots__` — hold over every declared class body, an
Entity Class and a Value Object Class alike, because both kinds carry what they
protect. The other three are the Entity surface itself and hold on an Entity
Class only: a Value Object has no query root, no declaration protocol, and no
temporal member, so those spellings are ordinary Value Object members.

- the query-root and introspection classmethods — `where`, `narrow`, `include`,
  `as_of`, `as_of_range`, `history`, `meta`, `descriptor`;
- the instance-level copy verb `edit` (§3), on either kind, because both install
  one. A declared `edit` member installs its descriptor over the verb and
  silently disables editing for that class, which is the same harm whichever kind
  authors it;
- the pickle entry point `__reduce_ex__` (§3), on either kind, because what a
  value of either kind becomes outside the process is derived from instance state
  the framework owns. On an Entity it is where the lifecycle refusal below sits,
  and an authored one would run in place of that refusal rather than after it.
  Reserving exactly this name is what keeps `__reduce__` and `__getstate__`
  authorable: `object.__reduce_ex__` consults both, so an authored hook runs
  downstream of a guard that has already passed;
- the schema seam `__get_pydantic_core_schema__`, on either kind, because an
  authored one replaces a declared class's whole validation and serialization
  rather than composing with it, so what publication means for that class's
  instances would become the class's to redefine. Reserving exactly this name is
  what keeps every other Pydantic extension point authorable: a field serializer,
  a model serializer, a computed field, a validator, and the JSON-schema hook
  `__get_pydantic_json_schema__` all still run, and the last of those is
  deliberately NOT reserved — the framework installs none, so an authored one
  composes with Pydantic's own;
- the instance-state names Pydantic keys on, on either kind, because the
  framework decides what each answers. Two of them are the presentation
  `__dict__` and `__pydantic_fields_set__`: Pydantic reads what a model
  physically holds by name rather than through the interpreter's own struct
  pointer, so what is bound under them decides what its equality, hashing, repr,
  compiled serializer, and validation all see. A published value holds no
  instance dictionary and no populated-member set at all, and answers both from
  its compact row; a class body binding either name would answer for its own
  instances instead. The other two are the containers `__pydantic_extra__` and
  `__pydantic_private__`: Pydantic keys every extra field and every private
  attribute on those names, and deriving a copy gives the copy its own mapping
  under each, so a body binding one hands its own instances something other than
  a mapping wherever those are read and written;
- the object layout `__slots__`, on either kind. A declared value's layout is
  the framework's whole — every slot of it is one the framework laid out, which
  is what lets a derived copy carry each without asking whose it is — and a body
  laying out slots of its own is the one remaining route to a slot nothing
  classifies, since a declaration may not extend a foreign base either
  (`entity-base-invalid`). The reservation is on the name, so no spelling
  `__slots__` accepts reaches a layout; non-field per-instance state is held in
  a Pydantic `PrivateAttr`, which an edit carries and which costs a value no
  slot of its own;
- the `model_*` namespace Pydantic reserves, on either kind, since both are
  Pydantic models;
- the framework temporal members, on a class whose family extends `TxTemporal`
  or `Bitemporal` and is therefore supplied them. The reservation is on the
  canonical names `validStart`, `validEnd`, `txStart`, and `txEnd`, so one rule
  covers the Python spellings `valid_start`/`valid_end`/`tx_start`/`tx_end`, a
  literal canonical spelling, and an explicit `name=` that renames onto one;
- the `__parallax_` prefix, on either kind. It names the framework's *private*
  bindings — the markers it puts on a declared class, the private slots it puts
  on an instance (the lifecycle state of a materialized node and an Edited
  Copy's Change Record among them), and the renderer every Value Object
  serializes itself through. The framework's public bindings sit outside the
  prefix and are reserved by name above, so this family reserves exactly what a
  declaration never names, and the whole prefix is reserved rather than the
  current names, so a slot added later needs no second reservation. Only a
  framework root's own body — `Entity`, `TxTemporal`, `Bitemporal`,
  `ValueObject` — binds under it. A declaration binding under it is not a
  shadowed member surface but a shadowed framework value: ordinary reads would
  answer the class's binding, and a `functools.cached_property` spelled under
  one would additionally recompute that binding on an Edited Copy, because §3's
  invalidation rule reads a derived cache off the class;
- the ten declaration members `identity`, `container`, `persistence`, `layout`,
  `attributes`, `relationships`, `value_objects`, `as_of_axes`, `inheritance`,
  and `indices`. An Entity Class *is* its own `UnresolvedEntityDeclaration`: the
  metaclass declares those ten names on the class object without binding
  values and answers each read from the class's own declaration through an
  attribute fallback, which is what lets `type[SomeEntity]` satisfy the protocol
  statically as well as at runtime.

An attribute fallback answers only names the class object does not otherwise
carry, so this last family is what keeps the declaration surface reachable at
all: any class-body name taking one of the ten — a declared member, a class
variable, or a method — wins the lookup, and the class then presents something
other than its declaration to every reader, including Domain Model construction. The
rejection therefore covers every binding a class body makes, not only declared
members. The `model_*` reservation is checked the same way and for the same
reason: an unannotated `def model_copy` in a class body is a binding rather than
a declared member, and admitting it would reinstate a copy door §3 refuses.

Every family is checked against the class body as authored, which makes the
reservation an authoring rule rather than a barrier. A name that reaches the
class object some other way is outside it: one a class-body descriptor's
`__set_name__` installs falls outside the pre-creation namespace scan, and one
assigned onto the class once it exists falls outside class-creation checks
altogether. That difference does not change the rule. Auditing the constructed
class would catch the descriptor, but a plain assignment still reaches the same
binding whatever the class body was permitted to say, so the audit would widen
the check without turning it into a barrier. What the reservation owes an author
is a rejection where the collision is written.

#### Relationships — `Rel[T]` and `rel(...)`

`Rel[T]` is the sole relationship annotation and `rel(...)` is required. The
annotation carries multiplicity and loaded-null optionality; `rel(...)` has
exactly two mutually exclusive forms:

```text
rel(cardinality=..., join=(source_member, target_member),
    dependent=False, order_by=(...), name=...)
rel(reverse_of=target_relationship_name, order_by=(...), name=...)
```

- The defining form owns cardinality — the core `Cardinality` algebra, spelled
  `ONE_TO_ONE`, `MANY_TO_ONE`, or `ONE_TO_MANY` —
  the join (source member of the declaring class, target-local member name),
  dependency, and its direction's ordering. The reverse form names only the
  target's defining relationship and optional ordering. Mixing the forms
  fails at the `rel(...)` call itself.
- `Rel[Target]` names the target: a class object or qualified string
  (`Rel["crm.Customer"]`) is Exact; a bare string (`Rel["Customer"]`) is
  Relative to the declaring class's namespace. Resolution is confined to the
  Domain Model's candidate set — never module globals or `eval`.
- **Multiplicity by annotation.** `Rel[T]` and `Rel[T | None]` are to-one;
  `Rel[tuple[T, ...]]` is to-many. A to-many is never `| None`: loaded-empty
  is `()`.
- **Annotation-shape agreement.** The whole `Rel` annotation shape must
  agree with the accepted model: a direction whose compiled multiplicity is
  Many is spelled `Rel[tuple[T, ...]]`; a One direction is scalar `Rel[T]` /
  `Rel[T | None]`; and scalar optionality follows the loaded-null rule —
  `Rel[T | None]` exactly where a loaded-null answer is possible (a defining
  to-one whose join source attribute is nullable, and every reverse to-one),
  forbidden elsewhere. The rule is checked in the Domain Model constructor's Python
  realization phase from the accepted model; every mismatch — multiplicity
  and optionality alike — is reported together, in canonical order, as
  `EntityDefinitionError(code=
  "entity-relationship-annotation-mismatch")`, and no model is created. The
  annotation never absorbs the *unloaded* state, which always raises
  (`UnloadedRelationshipError`); `None` means exactly "loaded, and there is
  none".
- **Ordering.** `order_by=` is a tuple of target-local member names: a bare
  string means ascending with nulls last; `desc("name")` marks descending,
  with an `asc()` twin for symmetry. Either helper returns an immutable term
  supporting `.nulls_first()` and `.nulls_last()`; omitted placement remains
  nulls last in either direction, and placement is single-shot — a second
  modifier raises `ValueError`. A bare string
  cannot customize null placement because doing so requires an explicit
  `asc(...)` or `desc(...)` term. Ordering is legal only on a to-many direction; an
  unknown member is the formation-time `relationship-order-attribute-invalid`
  issue, and an empty or omitted tuple means no ordering.

```python
class Customer(Entity, table="customer"):
    id: Attr[int] = attr(primary_key=True)
    orders: Rel[tuple["Order", ...]] = rel(
        reverse_of="customer",
        order_by=("placed_at", desc("id").nulls_last()),
    )


class Order(Entity, table="orders"):
    id: Attr[int] = attr(primary_key=True)
    placed_at: Attr[datetime]

    customer_id: Attr[int]  # 1..1: non-nullable FK
    customer: Rel[Customer] = rel(
        cardinality=MANY_TO_ONE,
        join=("customer_id", "id"),
    )

    coupon_id: Attr[int | None]  # 0..1: nullable FK
    coupon: Rel["Coupon | None"] = rel(
        cardinality=MANY_TO_ONE,
        join=("coupon_id", "id"),
    )
    # Spelling coupon as Rel["Coupon"], or customer as Rel[Customer | None],
    # fails Domain Model construction with entity-relationship-annotation-mismatch.
```

At runtime on a Snapshot node the three relationship states stay distinct:
an included 1..1 read is the instance (never `None`, no narrowing); an
included 0..1 read is the instance or `None` (loaded-null); an unincluded
relationship raises `UnloadedRelationshipError` regardless of spelling, and
`is_view_loaded(node, Order.coupon)` is `True` for a loaded-null answer. A reverse
to-one is always `Rel[T | None]` — nothing in the model guarantees a
counterpart row:

```python
class Account(Entity, table="account"):
    id: Attr[int] = attr(primary_key=True)
    profile_id: Attr[int]
    profile: Rel["Profile"] = rel(  # defining 1..1
        cardinality=ONE_TO_ONE,
        join=("profile_id", "id"),
    )


class Profile(Entity, table="profile"):
    id: Attr[int] = attr(primary_key=True)
    account: Rel[Account | None] = rel(reverse_of="profile")
```

#### Value Objects

A Value Object class extends `ValueObject`, is inherently frozen, and uses
the same `Attr[T]` / `attr(...)` vocabulary. A single-use shape may be
declared lexically inside its owner; a reusable shape is a standalone class
referenced by each occurrence's annotation. Neither form is a Domain Model candidate
or requires registration — occurrences are reached only through Entity
declarations. `Attr[Address]` is a One occurrence, `Attr[Address | None]` is
One-nullable, `Attr[tuple[Address, ...]]` is Many (never nullable; a
`| None` Many surfaces during formation as `value-object-many-nullable`). A Value
Object scalar carries the scalar Neutral Type algebra — every neutral type
except `Json` (the schema draws a Value Object attribute `type` from
`scalarType`; the corpus `float64` Value Object members exercise a non-string
scalar), so on Value Object scalar
members `attr(...)` admits the naming and type-shaping options — `name=`,
`type=` (`Int32`/`Float32` narrowing), and `precision=`/`scale=` (mandatory
together on a `decimal.Decimal` member). Entity-only options fail at class
creation: storage, keys, generation, locking, and `max_length=` (the schema
gives a Value Object attribute no length bound). Of the reserved member-name
families above, the six that are not the Entity surface — `model_*`, the
`__parallax_` prefix (which covers the renderer a Value Object serializes itself
through), the copy verb `edit` (§3), the pickle entry point `__reduce_ex__` (§3),
the schema seam `__get_pydantic_core_schema__`, and the instance-state
presentation `__dict__` / `__pydantic_fields_set__` — hold over a Value Object
class body as well, on a declared member and on
an unannotated binding alike. An
Entity-level occurrence member additionally admits `column=`, the occurrence's
Structured Column override. When it is omitted, the already-resolved canonical
occurrence name flows through `default_column_name()` exactly like a scalar
Attribute; nested occurrences and fields remain columnless. Containment cycles
and empty composites are the
formation-time `value-object-*` issues shared with the descriptor frontend.
Distinct scalar Attributes, top-level Value Object occurrences, and a
table-per-hierarchy tag also declare distinct physical columns within each
physical table; Domain Model construction reports
`storage-layout-column-collision` rather than allowing a row mapping to
infer which member a duplicate column key denotes.
Because `Table(name)` identity is name-only, each structural Table accepts
exactly one independent mapping owner: a standalone Entity, one whole TPH family
represented by its root, or one TPCS concrete mapping. TPH participants belong
to their family owner and do not compete with it. Formation visits owners in
canonical Entity Identity order and reports every later independent same-Table
owner as `storage-layout-table-mapping-collision` at that Entity's mapping
provenance with the first owner's provenance related. It never merges separate
model primary keys into one layout that each Entity can only partially supply.
Materialization preserves scalar, Value Object, relationship, and
`familyVariant` provenance to the published field set, which is keyed by declared
member name. A Value Object storage column may therefore equal a differently
named relationship without either value overwriting or renaming the other. Domain Model construction separately reports
`inheritance-materialization-key-collision` when keys that actually coexist in
one rendered node remain ambiguous. A polymorphic node's `familyVariant` uses a
bare concrete class name when family-unique and the canonical qualified Entity
spelling when duplicate local concrete names make the bare spelling ambiguous.

#### Class creation versus Domain Model construction

Class creation (and the `attr`/`rel`/`index` factory calls themselves) rejects
only what prevents a coherent Python class or candidate declaration; every
model-semantic rule — cross-member, cross-class, family, index, ordering, and
reference resolution — fails during Domain Model construction through the same
`MetamodelIssue` codes the descriptor frontend produces, so the two frontends
report equivalent outcomes for models both can author. The Python realization
phase that follows formation inside the same constructor adds only
Python-fact checks: the Entity Class claim and the annotation-shape
agreement rule. An intrinsically invalid factory argument fails at the
factory call itself (`entity-option-invalid-value`); an option whose
legality depends on the annotation or class context fails at class creation
(`entity-option-context-invalid`). The closed `EntityDefinitionError` code
set is:

| Code | Rejected at | Meaning |
|---|---|---|
| `entity-header-unknown-option` | class creation | unknown class-header keyword |
| `entity-header-invalid-value` | class creation | ill-typed or malformed header value, including malformed `inheritance=` and `indices=` values |
| `entity-header-missing-option` | class creation | a required header omitted: a standalone Entity without `table=` |
| `entity-base-invalid` | class creation | an invalid base shape: zero or multiple Parallax bases, a non-Parallax mixin, or a domain-Entity subclass omitting `inheritance=` |
| `entity-annotation-invalid` | class creation | malformed `Attr`/`Rel` annotation: a bare un-aliased annotation, an unsupported inner type, or an optionality/multiplicity shape outside this grammar |
| `entity-member-value-invalid` | class creation | the assignment slot holds a bare value, an `attr(...)` under `Rel[...]`, or a `rel(...)` under `Attr[...]` |
| `entity-option-invalid-value` | factory call | an intrinsically invalid argument value: an ill-typed or out-of-range `attr(...)`, `rel(...)`, `index(...)`, or `Sequence(...)` argument |
| `entity-option-context-invalid` | factory call / class creation | an option illegal in context: mixed defining/reverse `rel(...)` forms, Entity-only options on a Value Object member, an empty `index(...)` member list, a `MAX`/`Sequence(...)` generation on a non-integer member |
| `entity-reserved-member-name` | class creation | a reserved query-root, introspection, or edit-verb name, the pickle entry point `__reduce_ex__`, the schema seam `__get_pydantic_core_schema__`, an instance-state name Pydantic keys on (`__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__`, `__pydantic_private__`), the object layout `__slots__`, a `model_*` name, a `__parallax_` framework name, a framework-temporal member name, or one of the ten declaration member names |
| `entity-canonical-name-collision` | class creation | two members converting to one canonical name |
| `entity-relationship-annotation-mismatch` | Domain Model construction (realization) | a `Rel` annotation shape — multiplicity or optionality — disagreeing with the accepted model; all mismatches reported together in canonical order |

#### Canonical descriptor input

The optional `parallax-descriptor` distribution exposes three module-level
functions that create descriptor-backed Domain Models. There is no format sniffing
(JSON is a YAML subset, so sniffing is unsound) and no filesystem or stream
I/O — acquisition and persistence belong to the caller:

| Function | Input | Syntax phase |
|---|---|---|
| `domain_model_from_document(document)` | an already-decoded `Mapping[str, object]` | none — schema validation is its first gate; it never raises `DescriptorSyntaxError` |
| `domain_model_from_json(text)` | `str \| bytes` (UTF-8) JSON | yes — malformed UTF-8 or JSON is `DescriptorSyntaxError` with `format="json"`, optional line/column, and cause |
| `domain_model_from_yaml(text)` | `str \| bytes` (UTF-8) YAML | yes — as above with `format="yaml"` |

After every ingestion phase succeeds, the Descriptor Frontend adapts its
immutable records to `UnresolvedMetamodel` and calls the private, versioned
first-party seam
`DomainModel._from_unresolved(source: UnresolvedMetamodel)`. That seam creates
a fixed-source Domain Model composing no Entity Class. It is not exported as
a supported third-party frontend extension point, and there is no registration,
discovery, or lazy-import mechanism.

All three yield the same fixed-source Domain Model on success — construction is
construct-or-raise, so a returned model is always authoritative. The phase
boundaries are exact: syntax failures raise
`DescriptorSyntaxError(descriptor-invalid-syntax)` before a model exists;
canonical-schema violations raise
`DescriptorSchemaError(descriptor-schema-invalid)` before a model exists;
value-phase rejections (`m-descriptor` "Type spellings" — e.g. the
schema-valid but unconstructible `decimal(0,9)`) raise
`DescriptorValueError(descriptor-value-invalid)` before a model exists; every
semantic model rule fails last, still inside the same call, as
`MetamodelValidationError`. Each `domain_model_from_*` function therefore raises both
families in that fixed phase order: `DescriptorError` for representation
defects and `MetamodelValidationError` for model defects. The two remain
disjoint types, so one call site catches both. A document uses the schema's two
top-level forms:
`entity:` for one Entity or `entities:` for several. Successful ingestion
converts the accepted input into immutable descriptor-owned records and
retains no caller-owned mutable document. The same model flows through any
door:

```yaml
entities:
  - name: Author
    namespace: bookshop
    table: author
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: name
        type: string
        maxLength: 200
    relationships:
      - name: books
        reverseOf: Book.author
  - name: Book
    namespace: bookshop
    table: book
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: title
        type: string
      - name: authorId
        type: int64
    relationships:
      - name: author
        cardinality: many-to-one
        join:
          source: authorId
          target: { entity: Author, attribute: id }
    indices:
      - name: book_author_id
        attributes: [authorId]
```

```python
from parallax.descriptor import (
    domain_model_from_document,
    domain_model_from_json,
    domain_model_from_yaml,
)

models = domain_model_from_yaml(yaml_text)  # or domain_model_from_json(json_text)
models = domain_model_from_document(document)  # e.g. json.loads(json_text)
```

The same package exports a class-backed or descriptor-backed Domain Model
through `export_document(model) -> dict[str, object]`,
`export_json(model) -> str`, or `export_yaml(model) -> str`.
`export_document` returns a fresh tree of ordinary mappings, lists, and
JSON-compatible scalar values. A Domain Model is accepted by construction and
carries no lifecycle state, so export performs no model-state check and has no
state failure to propagate; it renews no
validation, performs no state change, and retains no descriptor cache. Repeated
document results are structurally equal and repeated text results
byte-identical. Unexpected
conversion or serialization defects raise
`DescriptorExportError(code="descriptor-export-failed")` with target
`document`, `json`, or `yaml` and the original cause, return no partial output,
and leave the model unchanged.

A seventh door answers a question the six above structurally cannot.
`validate_inheritance_families(document) -> None` classifies the
inheritance-family defects that keep a document from forming at all — an unknown
parent, a parent cycle, a non-root redeclaring a family-owned fact, a strategy's
table or tag rules — raising
`parallax.core.inheritance.InheritanceError` whose `rule` is the same
`m-inheritance` identifier the accepted model's own Rule Set reports, so a family
defect reads identically whichever side observed it. It is the ONLY door that
answers for a document expected never to form: `domain_model_from_*` can report such a
document only as a refusal to build a model, and a defect the adaptation discards
— a non-root's own `strategy` — is unobservable past that point. It therefore
parses shape only, without the canonical-schema and value phases the `domain_model_from_*`
doors gate on, and says nothing about any non-family rule; a document whose shape
is not a descriptor at all still raises `DescriptorError`.

The separately distributed Descriptor Frontend reads the model through the
durable first-party collaboration seam
`parallax.core.entity.model_of(model) -> Metamodel`. It returns the same accepted
immutable Metamodel without copying, works for class-backed and
descriptor-backed models, and exposes no Entity Class composition or
construction capability. It belongs to the advanced `parallax.core.entity`
interface and is
not re-exported from `parallax.core`; there is no `DomainModel.model`
property. Ordinary application code uses `models.meta(...)`, `models.entities`,
or the public Descriptor Frontend export functions.

Snapshot connection instead reads the model through the private first-party
`cataloged_model(model) -> CatalogedModel` and
`class_index(model) -> ClassIndex | None` pair. The cataloged model is the
accepted Metamodel paired with the layout catalog derived from it, answered by
the one door that derives and retains that pair, so a connection reaches both
halves at once and neither separately. The class index is present exactly for a
class-backed Domain Model and absent for a descriptor-backed one; it is a
bidirectional Entity Identity/Entity Class map and carries no per-model identity
of its own.
`Database.connect(adapter, model)` has a static `model: DomainModel` input and
accepts no bare-Metamodel overload. At runtime it narrows the same way: a value
that is not a Domain Model at all is rejected before `adapter` is inspected,
with the exported `SnapshotConnectionError(ValueError)` under the sole stable
code `snapshot-class-backed-model-required`. A Domain Model composing no Entity
Class connects, because provenance decides capability rather than connectability;
it is refused under that same code at every modeled read instead. The error
exposes neither an Entity Runtime nor a class index. It is not
`DeferredFeatureError(execution-feature-deferred)`, which is reserved for a
valid query whose execution feature is explicitly deferred.

After that narrowing, Snapshot constructs one private `_ConnectedModel` owned by
the Database. It contains the accepted Metamodel and the exact-model layout
catalog every read converts its rows against as ONE composed value, so a read
lane resolves and converts against one model rather than against two references
that could name two; the Entity Row Codec every write derives its rows through;
the Entity Graph Construction Snapshot materialization requires — absent exactly
for a descriptor-backed model, which is what makes a modeled read refusable
before any I/O; and no identity. The codec and the construction stay separate
references, because neither is derived from the other. It is handle state rather
than a Core runtime value and is neither exported nor shared through the model.

`Database(port, model)` takes the same `model: DomainModel` input and admits no
bare accepted Metamodel. It refuses a value that is not a Domain Model with the
same `SnapshotConnectionError(snapshot-class-backed-model-required)`, so every
connection reaches its accepted Metamodel through a Domain Model and per-model
derived state hangs on that model behind one lookup door. A descriptor-backed
model composes no Entity Class and can never materialize a Snapshot, so
`Database.find` and `Transaction.find` refuse it with that same error — on both
entry points before target resolution, and on the participating one before the
unit of work's force-flush, so a refused read flushes no pending write. The
write lanes and the Wire read that connection does serve are unaffected: they
name Entities rather than classes.

Snapshot owns `_DEFERRED_EXECUTION_FEATURES: frozenset[str]`, the private
immutable set of canonical Feature tags whose query shapes are valid but
whose execution is explicitly deferred by this implementation. Its initial
entry is `snapshot-history-includes`. It is one package-owned module constant
shared by every Database in the installed implementation; no constructor
argument, environment setting, provider, adapter, or application hook can add
or remove entries. After reading a query's canonical value,
Snapshot classifies it for its own execution features and
compares those tags with the deferral set after target resolution and query
validation and before SQL generation, Database Port access, or connection
acquisition. An
intersection raises exported `DeferredFeatureError(RuntimeError)` with stable code
`execution-feature-deferred` and every matching canonical deferred Feature in
its nonempty, ascending `features: tuple[str, ...]` attribute. The expected
completed state is an empty set; every nonempty entry is
an explicit, reviewable implementation deferral. A Feature claimed by the
active Conformance Slice but not implemented is a defect and cannot be made
permissible by listing it here. This set belongs neither to the connected
provider, `_ConnectedModel`, `Dialect`, nor a leased `DbPort`.

Target resolution always precedes this classification. An Object Query whose
target the connected model does not declare raises
`QueryTargetError(query-target-not-in-model)` and exposes no deferral result
even when its clauses would match one or more Deferred Execution
Features; neither path reaches SQL, a Database Port, or connection
acquisition.

One private Snapshot seam centralizes the complete read preflight:
`preflight(query: ObjectQueryNode, *, model, form) -> ValidatedObjectQuery`. It resolves the
query's target in the connected model, validates the canonical Object Query from
that resolved root, classifies it against `_DEFERRED_EXECUTION_FEATURES`, and
last refuses a row-form request that names Include Paths — in that order, which
is the contract rather than an implementation detail. `form` is the one fact a
query does not carry, because graph versus rows is a property of the call. It
performs no SQL, Database
Port access, connection acquisition, materialization, or transaction work.
Every read entry calls this seam rather than reimplementing any step:
`Database.find` and `Transaction.find`, the `db.wire.find` / `tx.wire.find`
peers beside them — each handle runs one read seam for both interfaces, so the
two cannot gate differently — the values lane's `read_rows`, the conformance
compile lane, and the later Session read boundary.

Deferred Execution Features apply only to modeled read execution through
`Database.find`, `Transaction.find`, their Wire peers, and the later Session
read boundary.
Predicate-selected write methods never invoke this classifier. They first
require a mutation-compatible Object Query, so a read-shaped query matching a
deferral still raises `QueryDefinitionError(query-not-mutation-compatible)`
before Unit of Work mutation or I/O.

Adding an entry is one atomic contract change: core defines the valid behavior
and canonical Feature tag, the active Conformance Slice explicitly leaves it
unclaimed, the Python deferred-capabilities list names it, Snapshot classifies
it with zero-I/O execution coverage, and the implementation's deferred ledger
records it only when the deferral would otherwise lack a canonical home.
Removing an entry is likewise atomic: execution support, Compatibility and API
Conformance coverage, the active slice claim, the Python deferred list,
`_DEFERRED_EXECUTION_FEATURES`, and any applicable ledger entry advance
together.

A Domain Model exposes its model-bound capabilities through two named seams and
no composite value:

```text
graph_construction_of(model: DomainModel) -> EntityGraphConstruction   # §3
row_codec_of(model: DomainModel)          -> EntityRowCodec            # §5
```

Each seam answers one capability and is **total**: every accepted Domain Model
reaches both and neither ever answers absence, because a capability derives from
the accepted Metamodel and every model has one. A descriptor-backed model
composes no Entity Class, so the graph construction it reaches can instantiate
nothing and refuses each allocation as
`GraphConstructionError(entity-graph-invalid-entity)` (§3), while the codec it
reaches is fully functional — the codec resolves an Entity Identity against
declared metadata and never consults the Entity Identity/Entity Class index
(§5). Refusing a descriptor-backed model is therefore the job of the caller that
needs classes — `Database.find` and `Transaction.find`, by name and before any
I/O — and never of a seam answering absence.

Each seam is retained by the model on first reach, so repeat calls for one model
return the same value. Both are reached from
`parallax.core.entity`, and neither is re-exported from top-level
`parallax.core`. There is no `EntityRuntime`, no capability pair, tuple, or record, and no
keyed capability bag: read materialization crosses graph construction alone,
write preparation crosses the codec alone, and the one caller that holds both —
Snapshot's private connected-model value — holds two references as cheaply as
one. Atomicity across the pair would guarantee nothing, because each capability
derives on demand from the same accepted model and no state exists in which one
is present and the other cannot be built.

Both seams construct lazily, and the reason is dependency direction rather than
cost. Each capability module sits **above** the Domain Model module in §7's
import DAG, so `DomainModel.__init__` cannot construct either without inverting
an edge the generated import contracts reject; the seam function is therefore
the only place that can build one. The guard is not a performance hedge and
removing it is not an optimization.

`parallax.descriptor` publicly exports the ingestion base
`DescriptorError(ValueError)` and its `DescriptorSyntaxError`,
`DescriptorSchemaError`, and `DescriptorValueError` subclasses; the frozen
`DescriptorSchemaViolation` and `DescriptorValueViolation` records; and the
separate `DescriptorExportError(RuntimeError)`. Export failure is an adapter
defect rather than invalid descriptor input, so `DescriptorExportError` is not
a `DescriptorError`. None of these names is re-exported from `parallax.core`.

The equivalent class declaration — the two frontends converge on the same
accepted Metamodel and canonical export:

```python
class Author(Entity, table="author", namespace="bookshop"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=200)
    books: Rel[tuple["Book", ...]] = rel(reverse_of="author")


class Book(
    Entity,
    table="book",
    namespace="bookshop",
    indices=(index("book_author_id", "author_id"),),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    author_id: Attr[int]
    author: Rel[Author] = rel(
        cardinality=MANY_TO_ONE,
        join=("author_id", "id"),
    )
```

#### Inheritance families, worked

Table-per-hierarchy — the root owns the shared table and tag column;
concretes carry only their tag values:

```python
class Payment(
    Entity,
    table="payment",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


class CardPayment(Payment, inheritance=ConcreteSubtype(tag_value="card")):
    card_last4: Attr[str]


class DigitalPayment(Payment, inheritance=AbstractSubtype):
    provider: Attr[str]


class WalletPayment(
    DigitalPayment,
    inheritance=ConcreteSubtype(tag_value="wallet"),
):
    wallet_ref: Attr[str]
```

Table-per-concrete-subtype — the root and abstract nodes are tableless;
every concrete declares its own table and no tag exists:

```python
class Vehicle(
    Entity,
    inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
):
    id: Attr[int] = attr(primary_key=True)
    vin: Attr[str]


class Car(Vehicle, table="car", inheritance=ConcreteSubtype):
    doors: Attr[int]


class Truck(Vehicle, table="truck", inheritance=ConcreteSubtype):
    payload_kg: Attr[int]
```

### Metadata and model input

#### Storage Layout formation and immutable facet

The built-in Formation Manifest and Profile include the exact
`m-storage-layout` contributions. `StorageLayoutRuleSet` receives only the
Candidate Metamodel and asks `parallax.core.inheritance` for its pure, total
validation-time Table-group projection and `parallax.core.relationship` for its
pure, total validation-time join-endpoint projection; it owns exactly
`storage-layout-table-mapping-collision`,
`storage-layout-column-collision`,
`storage-layout-document-member-column-override`,
and `storage-layout-index-over-document-member`; it never
consumes a facet, and never relies on Rule Set order. Owner collisions are
reported before physical Column claims; the Column collision code remains
exclusive to distinct physical Column contributors, which under Relational
Document Layout are the direct-role Attributes, the table-per-hierarchy tag, and
the one shared Structured Column. After every Rule Set succeeds,
`StorageLayoutCompiler` consumes the same Compiled Metadata object plus
`FacetKey(m-inheritance)` and `FacetKey(m-relationship)` and installs one
`StorageLayoutFacet` under `FacetKey(m-storage-layout)`. It emits no Issue.
Profile drift, compiler ordering, and all-or-nothing publication follow
`m-model-formation` without a Python-specific phase or registry.

`parallax.core.storage_layout` is the supported advanced import path. It
exports `ColumnTier`, `InheritanceDiscriminator`, `RelationalDocument`,
`ColumnContributor`, `ColumnSlot`, `MemberPlacement` with its `DirectColumn` and
`DocumentPath` variants, the `TableLayout`, `EntityLayoutView`,
`PositionLayoutView`, and `StorageLayoutFacet` protocols, and
`view(model) -> StorageLayoutFacet`. These names are not broadly re-exported
from `parallax.core`. Python spellings use `table`, `columns`,
`physical_primary_key`, `declaring_owner`, `effective_nullable`,
`applicable_entities`, `layout_owner`, `slot`, `path`, `members`, and
`placements`; lookup methods use the core contract's `table`, `entity`,
`position`, `column`, `contribution`, and `placement` names.

`placement(member)` is the sole locator for a logical member and is total over
the members applicable to its Table, returning `None` only for an unknown or
inapplicable member. No `parallax.core` or `parallax.snapshot` consumer
re-derives direct-versus-document residency, splits a dotted path against
metadata to reach a document member, or reads a Column spelling to decide where
a member lives. No Rule Set calls it, because during validation no facet exists.
`PositionLayoutView.members` is the position's logical member union and each
branch's `placements` aligns with it, so a polymorphic read gets a per-branch
answer; a Value Object leaf is located through the branch's own
`layout.placement(...)`.

Public values are immutable: `ColumnTier` is an Enum; contributor, slot,
placement, discriminator-assignment, logical-position-column, and branch values
are frozen slotted dataclasses; ordered collections are exact tuples; and
private lookup indexes are read-only. One eager object graph is compiled per
accepted model: one Table Layout per physical Table and one Column Slot per
physical column occurrence. Layout primary keys, Entity selections, position
branches, and placements reference those slots structurally instead of copying
them. Repeated applicability sets may be interned, and arbitrary position views
are not kept in an unbounded model-lifetime cache. Equality is structural;
Python object identity and a particular ordinal/index representation are not
contractual.

The Python facet implements all six tiers and the temporal-over-audit alias
precedence. The claimed model inputs currently supply no accepted Audit
Metadata, so their Audit tier is empty. The compiler's internal classifier seam
accepts optional audit designations for focused unit proof of non-empty Audit
ordering and Transaction-Time revision alias de-duplication; it adds no Python
or descriptor authoring form and performs no audit stamping.

- **Runtime introspection API.** `models.meta(Order)` (or by canonical Entity
  Identity) returns the immutable, local `EntityMetadata` contract from
  `m-metamodel`: declared storage, persistence, attributes, defining/reverse
  relationship declarations, Value Objects, As-Of Axes, inheritance
  declaration, and indices in declaration order. It never flattens inherited
  members and exposes no effective `table`, `temporal`, relationship-target,
  family, or similar convenience aliases. Owner-specific derived behavior is
  obtained from the model's compiled facets. Canonical descriptor export is a
  Descriptor Frontend operation over an accepted Domain Model, not a model or
  Entity metadata method. Class-backed and descriptor-backed models return the same
  compiler-owned objects; there is no package-global `meta(...)` registry
  lookup or parallel `EntityMeta` graph.
  `meta(...)` is the one developer-facing lookup that raises rather than
  answering absence, so it has its own exported family: `MetamodelLookupError`
  (a `LookupError`) with the closed code set `metamodel-invalid-entity-reference`
  for a string that is not a canonical `<namespace>.<name>` (or bare `<name>`)
  spelling, and `metamodel-entity-not-found` for a well-formed key naming no
  Entity of this model — including an Entity Class this model did not compose,
  since a class names an Entity of the models that composed it and of no other.
  It accepts an Entity Class, a canonical spelling, or an `EntityIdentity`, and
  all three answer the same object. The class-free `m-metamodel` lookup protocol
  underneath returns ordinary absence and raises none of these.
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
  | `timestamp` | tz-aware `datetime` | naive rejected; an instant no UTC `datetime` holds rejected; normalized UTC; microseconds | `timestamptz`; aware UTC on read |
  | `uuid` | `uuid.UUID` | `UUID` or canonical string | driver uuid |
  | `json` (value object only — `m-core` admits no direct `json` member) | nested frozen value-object class | the VO class instance; never a raw dict | structured column per dialect |

  Python represents both neutral float widths with its binary64 `float`
  carrier. A `float32` input is a member when narrowing it to IEEE-754 binary32
  is finite and yields the value represented by that input; integral inputs must
  narrow exactly, while fractional inputs may round to the nearest binary32
  value because Python cannot carry that value at binary32 width. Overflow and
  non-finite values are rejected. Reads widen the narrowed binary32 value back
  into the Python `float` carrier.

  This column is the **developer input** policy and is deliberately stricter
  than the wire decode: an interchange seam reads a JSON *number*, where the
  `int` / `float` carrier a parser chose carries no information, so every
  in-range number names the nearest float of the declared width
  (`m-document-codec`). Here the caller chose the Python type, so an `int` no
  float of the width carries exactly is refused rather than rounded — the
  runtime narrows nothing the caller did not write as a float.

- **Metamodel serde ownership.** Source owner and enforcement scope
  `parallax.descriptor`, shipped in the separately installable
  `parallax-descriptor` artifact. Its complete public surface is
  `domain_model_from_document`, `domain_model_from_json`,
  `domain_model_from_yaml`, `export_document`,
  `export_json`, `export_yaml`, `validate_inheritance_families`, and the
  descriptor error/violation types listed above; descriptor records, serde,
  schema machinery, and adapters are private.
  JSON and YAML canonicalization tests run under the internal-behavior
  surface (`uv run pytest tests/unit`), and every corpus descriptor must import, export
  deterministically, and re-export structurally equal to its canonical corpus
  spelling (`m-descriptor` "Metamodel serde": the canonicalization law and its
  omission set).

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
  descriptor schema. A member a descendant inherits rather than declares is the
  declaring class's own field at every depth — the same default and the same
  requiredness — so what a descendant's instance reads for a member no
  construction supplied never depends on which class in the family declared it.

  ```python
  class Order(Entity, table="orders"):
      order_id: Attr[int] = attr(primary_key=True)
      qty: Attr[int]
      items: Rel[tuple["OrderItem", ...]] = rel(reverse_of="order")
  ```

  Rationale: single source of truth in user code, no generated-file lifecycle,
  strict-Pyright-clean class-level expressions via the annotation aliases.
- **Published instance state, and what it trades.** An instance a Snapshot read
  published holds its declared members in one immutable tuple with a presence
  bitmap, on a slot of its own, and carries no instance dictionary and no
  populated-member set at all; an instance ordinary construction produced holds
  Pydantic's own storage unchanged. Which of the two a value carries is not a
  public distinction: the framework answers `__dict__` and
  `__pydantic_fields_set__` for both (the reservation above), so equality,
  hashing, repr, iteration, JSON Schema, and every documented serialization
  option agree between the two backings and with a hand-written plain
  `BaseModel` of the same fields. The **cost is part of the contract**, not an
  implementation detail, because a caller can measure it. Over the canonical mix
  `languages/python/docs/instance-state-baseline.md` records, a published
  instance retains **a little over two fifths** of what an ordinary one does —
  43.8% on CPython 3.14 and 41.0% on 3.13, summed over that mix and measured
  against an ordinary arm built by the validating constructor, which carries no
  lifecycle state because a plainly constructed instance has none (§3) where a
  published node always does — and pays for that at two reads: `model_dump` of a published instance runs roughly twice an ordinary
  instance's and roughly three times a plain Pydantic model's, because the
  presentation is built per read, with equality comparable; and a declared-member
  read of a published instance runs roughly three times an ordinary instance's,
  because a published instance has no instance dictionary and the read therefore
  resolves through the member descriptor rather than through storage. An ordinary
  instance pays neither — its member reads, its serialization, and everything
  else about it are a plain Pydantic model's, unchanged — and no published cost
  is ever moved onto one to reduce it. The presentation is deliberately **not**
  memoized on the instance: a mapping cached at first dump is retained per-node
  state, which is the cost publication exists to remove.
- **Drift prevention without codegen.** The API Conformance Suite's
  descriptor-equality guard (idiomatic class exports ≡ corpus descriptor) and
  the query no-drift guard (idiomatic Object Query serialization ≡ the corpus
  document) are the drift gates; both run in CI.
- **Derivable typed artifacts.** None are generated. The spec deliberately
  promises no generated surface; everything typed is derived at runtime from
  the class declarations, which carry no information absent from the
  descriptor schema.

### Sentinel identity

A sentinel answers a question no ordinary value could — absent, unloaded,
missing, unavailable, SQL null, latest, unobserved, no stored member at all. A
site holding one on its own reads it with `is`; a site holding a union whose
other arms carry data reads the sentinel's own class, which is the test a static
type narrows on and the only one that reaches the carried arm's payload
afterwards. The two never disagree because no second object passes the class
test: constructing a sentinel class answers the instance it already holds, and
the class refuses a subclass that could hold another. `object.__new__` still
reaches past both, as it reaches past every invariant a Python class states in
`__new__`; nothing short of that deliberate bypass makes an object the two
readings would split on. For each sentinel below, **sameness is identity**:

- the module-level constant is the one instance, constructing the class again
  answers that instance rather than a second object, and subclassing is refused
  where the class is declared;
- `repr` is the exported name a reader would spell, not a constructor call; and
- `is` survives construction, `copy.copy`, `copy.deepcopy` at any nesting depth,
  and a pickle round trip at every protocol.

| Sentinel | Owner | Answers |
|---|---|---|
| `LATEST` | `parallax.core.object_query` | the explicit Latest temporal coordinate |
| `ABSENT` | `parallax.core.entity` (private) | a positional member row's absent-or-undecodable position |
| `UNLOADED` | `parallax.core.entity` | a relationship position outside the include set |
| `NULL` | `parallax.core.document_codec` | a document member written as JSON null |
| `MISSING` | `parallax.core.document_codec` | a document member whose key the document does not carry |
| `UNAVAILABLE` | `parallax.core.document_codec` | a member whose hydration would require invention |
| `SQL_NULL` | `parallax.core.base` | a structured-document read whose SQL column is NULL |
| `INERT` | `parallax.core.execution_lifecycle` (private) | the activity every unobserved operation runs against |
| `MISSING_STORED_VALUE` | `parallax.snapshot` | a stored-data issue's evidence that a traversable object held no such member |

Each sentinel's class answers its own name from `__reduce__`, which pickle
resolves in the class's *defining* module — so the singleton is declared at
module level beside its class, whatever re-exports sit above it.

The zero-field facet values — `MAX`, `COLUMNS`, `NON_TEMPORAL`, and their peers
— are deliberately excluded. Their documented contract is equality: a freshly
constructed one is a distinct object equal to the exported constant, and
collapsing construction or a copy onto one instance would give identity a
meaning their contract withholds from it.

The public-API snapshot diffs `__all__` alone, so it observes none of this. The
contract is graded directly instead, one case per sentinel.

`MISSING_STORED_VALUE` is the one of these a caller holds: it travels out on
`StoredDataIssue.stored_value` (§4 *Invalid stored data*), so it is the one whose
identity a caller may copy or pickle across a boundary of their own.

## 3. Object lifecycle profile

### Snapshot lifecycle

- **Public result and node types.** `db.find(query)` executes exactly once,
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
  `list[T]` per call), `pin` (the lowered as-of coordinates), and `__repr__`.
  The result retains no execution-lifecycle record. Deliberately
  absent: iteration/len/truthiness/indexing on the container, refresh or
  write methods, and any lazy behavior. Accessors are pure in-memory reads.
- **Graph-local identity.** Within one materialized graph, one node per
  `(entity family, primary key, lowered as-of coordinates)` key: diamond paths
  share the same node object, cycles/back-references are hard pointers
  (constructed via an implementation-private setattr backdoor during
  materialization), and projections targeting the same key merge into one
  node. Value objects have no identity (fresh values per owner). Identity
  never escapes one graph: nodes from different `find` calls never coalesce.
- **Duplicate projections are value-identical.** Two projections of one logical
  node carry the same values by construction: they resolve the same stored row
  at the same pin, and each covers the full Attribute and Value Object set the
  concrete it resolved to declares — an abstract-position read projects that
  position's superset and keeps exactly the members of the resolved concrete, so
  no projection is a partial one. Merging therefore takes the **first**
  projection's entry for every scalar, Value Object occurrence, and resolved
  concrete Entity and compares nothing; it neither detects nor refuses a
  disagreement, because a read cannot produce one. Relationship Views are the
  only slot two projections legitimately differ on — a path loaded on one and
  not the other — and those are **unioned** rather than won.
- **Declared-type enforcement on a read is the writer's.** Materialization enters
  no Pydantic constructor for an Entity or a Value Object — a published node's
  whole state is assembled and attached once — so a declared member's type is
  enforced by Entity Graph Construction's
  own Neutral Value validation — which raises
  `GraphConstructionError(entity-graph-invalid-value)` — and never by Pydantic.
  The consequence is stated rather than incidental: an author's
  `@field_validator` or `@model_validator` does **not** run on a materialized
  read, while it continues to run on direct construction and on an edited copy
  (§2's build-time rules), because those are the surfaces where a caller
  supplies the value. A declared type is therefore still enforced everywhere; a
  declared *invariant* an author added on top of it is enforced on authored
  values only.
- **Value Object presence.** Within a present Value Object record, an omitted
  scalar or nested-occurrence identity and a present identity mapped to `None`
  are distinct stored-document states. Declared nullability says which of them
  a conforming stored document may hold — a required scalar or One occurrence
  admits neither — but nothing inside a record judges that
  (**Document-resident nullability** below). Both states read as `None`, and
  which of the two the document held is **not** what the value reports; whether
  the document held the member at all is. Field presence lives in the carrier —
  an omitted entry stays outside the frozen Value Object's `model_fields_set`
  and an entry present as `None` sits inside it — which is what lets canonical
  document serialization omit the former and emit the latter as explicit null.
  **Presence survives materialization at every containment depth**, whether the
  member is a top-level occurrence, a nested One, or an element of a Many at any
  depth: the document reduction the read path performs takes its presence from the
  source document rather than from the declared member list. Which members that
  reduction populates is the core read contract (`m-snapshot-read`, *What a
  materialized value carries*), and `model_fields_set` is this target's whole
  realization of it — a member the contract says the value carries is inside it and
  one it says the value does not carry is outside it, including at each position
  where carried and held part. So a Value Object built by ordinary construction and
  one materialized from storage draw the same distinction, and re-serializing a
  materialized occurrence emits exactly the members that contract carries. A
  mutation comparison reduces differently, and deliberately: the document an
  assignment would store is reduced with presence preserved, so a member the
  author omits contributes no key — except a Many, which has no absent state to
  preserve and contributes the `[]` the store will hold either way — and it is
  compared whole against the document the row holds.
  A Many occurrence is an ordered immutable `tuple` of non-null Value Object
  records and is never nullable: `()` is its sole zero-element value, and a
  present entry holding `None` or holding a `None` element is invalid. A stored
  document omitting one is not invalid, and materialization populates the field
  as `()` for it under the read contract above. The same rules apply recursively
  at every nesting depth.
- **The sealed Snapshot graph.** A materializing read builds its whole graph
  through one private first-party builder and publishes it by sealing: the
  builder's accumulation arrays transfer into an opaque `SnapshotGraph` and the
  builder is invalidated in the same step, so nothing observes a half-published
  graph and nothing writes to a published one. Projection merging accepts a
  sealed graph only. A result holder carrying one reads no row, layout, edge,
  identity, or issue off it and holds nothing to read one with; the whole-graph
  pin is the one fact it publishes, because a Snapshot publishes that pin.

  A graph carries, per projection: a reference to the exact-model member layout
  its row is read against, one positional `member_values` tuple, one positional
  relationship view row and the source level that sized it, one dense graph-local
  logical-node ID, and its classified stored-data issues where it has any. Nothing wraps a cell: a position holds the decoded
  value itself, and no per-cell record, member dictionary, or member-keyed entry
  stands between the row and the value. Absence is spelled rather than omitted,
  because a positional row cannot omit, by ONE private sentinel — the one owned
  beside the member layouts a row is read against (*Exact-model member layouts*),
  rather than by this or any other materializing runtime:

  | spelling | meaning |
  | --- | --- |
  | `ABSENT` | absent or unloaded, and what an undecodable cell becomes beside its issue |
  | `None` | an explicit null |
  | `()` | loaded empty, a Many with zero occurrences included |
  | a member row | one Value Object occurrence, in its declaration order |
  | a tuple of member rows | a Many occurrence, order preserved |
  | `int` / `tuple[int, ...]` | a to-one / to-many relationship edge, by projection index |

  The sentinel is not the document codec's own `MISSING` or `UNAVAILABLE`, which
  are consumed and discarded inside decoding, and it never escapes as a final
  public value: a consumer of a row either skips an absent position or is refused
  before publication.

  Edges and roots are exact nonnegative built-in `int` projection indexes. A
  `bool`, a non-`int`, a negative index, and an index past the graph's own
  projections are each refused where the edge or root is recorded, so a graph
  that exists is a graph whose references resolve and no whole-graph validation
  pass stands between building one and merging it. Two entries for one member or
  one view within a projection are unrepresentable rather than rejected: each has
  exactly one position. `roots` order and the tuple
  inside a loaded-many relationship view are semantic and preserved; projection
  order is not. Separate projections may resolve to one logical node; those are
  the duplicate projections the materializer merges. A view never written is
  unloaded, while a written `None` or empty tuple is loaded-null or loaded-empty.
  A root whose primary key is null or undecodable is represented by
  `InvalidRootInput`, whose ordinal IS its result position: its result ordinal and
  classified issues survive, but it contributes no logical identity and is never
  hydrated.

  Milestone processing imports immutable projection rows out of a sealed staging
  graph into a new builder, keeping each row's layout, member row, and issues by
  reference. It reconstructs no second graph and decodes nothing twice.

  Entity Graph Construction takes the same positional rows. Its build callback
  returns exactly `tuple[NodeHandle, ...]`; `EntityGraphWriter.populate(...)`
  accepts a **member row** and a **broad-relationship row**, each an exact
  built-in tuple of the exact Entity's own model-fixed width. The member row is
  laid out against that Entity's member layout — every applicable Attribute in
  ancestry-then-declaration order, then every applicable top-level Value Object
  occurrence in theirs — and a merged node's own row crosses that seam **by
  reference**, because the layout it was laid out against is the layout the
  writer reads it against. The broad-relationship row carries one position per
  navigable direction in the layout's canonical order, each holding `UNLOADED`,
  `None`, one `NodeHandle`, or an exact tuple of them: the value at a position
  names its arm, and the declared cardinality decides whether that arm is
  admissible. No mapping, abstract sequence, mutable collection, or
  caller-defined collection subtype crosses that seam at any depth. Only the
  broad-relationship row is synthesized per node, immediately before that node's
  own `populate` call and unreachable once it returns, so neither the graph nor
  the merge retains one and nothing is accumulated into a second graph-sized
  structure.
- **Value Object member rows.** A Value Object occurrence slot holds `ABSENT`,
  `None`, one member row, or a tuple of member rows, decided by the occurrence's
  declared multiplicity rather than by the value's shape: a One admits
  `ABSENT | None | row` and a Many admits `ABSENT | tuple[row, ...]`. A member row
  is an exact built-in tuple laid out by the model-owned Value Object layout for
  that exact, path-specific `ValueObjectIdentity` — the occurrence's own leaves in
  declaration order, then its nested occurrences in theirs — and the same rule
  applies recursively at every depth. A member the stored document did not carry
  holds `ABSENT` at its own position, which is how presence survives a row that
  cannot omit. Mutable mappings or sequences, raw document dictionaries, Pydantic
  Value Objects, and a separate frozen-map abstraction do not cross this seam.
  Only a Many occurrence's tuple has semantic order, preserved exactly; a member
  row's order is the declaration's.

  Conversion from physical structured-document values into these rows owns
  stored-document presence, container-shape, and Neutral Value validation. It
  records the closed `StoredDataIssueInput` vocabulary on the projection rather
  than raising: required-member absent/null, one/many wrong-kind, undecodable
  leaf, non-nullable Entity Attribute null, unknown family tag, and
  null/undecodable primary key. A `StoredDataIssueInput` carries the concrete
  Entity, applicable member identity when one exists, and a path whose
  member-name strings remain distinct from integer array positions. Entity Graph
  Construction nevertheless revalidates every identity, duplicate, occurrence
  shape, and Neutral Value; invalid direct first-party input raises
  `GraphConstructionError` with `entity-graph-invalid-member` or
  `entity-graph-invalid-value`. A public Snapshot read reaches that path only
  through an implementation defect.
- **Document-resident nullability and classification.** A **document-resident** position — a Value
  Object leaf, and a to-one or to-many occurrence inside a Structured Column —
  is classified before hydration and then follows `m-predicate`'s absence
  collapse for states the hydration table admits: a
  missing key, a stored null (SQL or JSON), and a non-object intermediate all
  arrive as `None`; for a Many, a missing key, a stored null, and a non-array
  all arrive as `()`. Classification is layout-neutral: a Columns occurrence's
  SQL-null-aware carrier and a Relational Document Layout member's located
  carrier pass through the same logical-member classifier before reduction.
  Required absent/null positions and wrong-kind occurrences add findings while
  their unavailable values are not invented; nullable absence and JSON null
  retain the ordinary collapse. A detecting seam owns its verdict once. The
  SQL/document transform carries both its findings and the set of members it
  already classified, so row conversion translates those findings without
  judging a synthesized `None` or `[]` again.

  The write path is untouched by this and still enforces: a Value Object authored
  for an assignment is built by ordinary Pydantic validation, where a required
  leaf admits neither omission nor `None` (§2), which is how a write omitting a
  required attribute or a required One occurrence is refused pre-SQL. Entity
  Graph Construction validates everything else at those positions — structured
  identity, duplicate entries, occurrence shape (record versus tuple), exact
  built-in tuple carriers, and Neutral Value validity. An Entity Attribute is no
  document-resident position under this rule wherever its Member Placement puts
  it: row conversion classifies a `None` for a non-nullable Attribute as
  `stored-data-attribute-null` (or `stored-data-primary-key-null`) and carries no
  fabricated value. Native database temporal infinity is already the distinct
  `INFINITY` sentinel; a SQL NULL temporal end is invalid and is never replaced
  with that sentinel.

  Both public graph materializers and the values lane classify those findings in
  band (§4). Milestone-set staging and predicate-write staging still call one
  publication gate over the reachable merged graph before allocating objects,
  deriving Object Keys, or partitioning by milestone: a milestone read must decode
  a temporal edge before it can partition at all, and a write has no in-band
  channel a verdict could publish through. The gate raises exported
  `SnapshotDecodingError(ValueError)` with
  stable code `snapshot-decoding-failed`, the concrete `EntityIdentity`, and the
  applicable `AttributeIdentity | ValueObjectIdentity |
  ValueObjectAttributeIdentity | None`. It exposes no raw stored value and
  carries no decoding cause. Invalid roots and issue-bearing requested
  descendants therefore publish nothing on those lanes; unrequested projections
  do not affect the verdict.
- **Root classification and the construction scope.** Classification runs once
  over the merged graph, after merging and before construction, and no seam below
  it re-judges what it answers. A root is invalid when any node its requested
  include tree reaches carries an issue; node-level unions and pruning are
  forbidden, one shared invalid node repeats its diagnosis in every affected
  root, and duplicate diagnoses within one root collapse. A root all of whose
  issues admit the normative collapse hydrates and carries its complete value; a
  root reaching `stored-data-leaf-undecodable`, `stored-data-attribute-null`,
  `stored-data-family-tag-unknown`, or either invalid-primary-key code hydrates
  nothing. Construction covers exactly the nodes the hydrating roots reach, so
  atomic publication means everything constructible publishes together. A graph
  carrying no issue is answered without a reachability walk and constructs
  unfiltered and unwrapped.
- **Single graph.** Projection merging is a read-only INDEXED interface over one
  sealed graph, and every consumer — classification, the typed materializer, and
  the wire materializer — reads it directly. It answers by reference into
  something it or its graph already holds: a logical node's member row IS the
  winning projection's row, and a second call for one node answers the identical
  object rather than an equal composition of it.

  It MAY retain the logical-node-to-allocation mapping, the projection-to-
  allocation mapping, the allocation order, the winning projection per logical
  node, its accumulated issues, and one fixed relationship view row per logical
  node aligned to that node's merged view layout. It MUST NOT retain per-cell
  Snapshot carriers, member dictionaries, or any merged object graph — it does
  not clone a node's scalar and Value Object payloads into a second graph-sized
  merged representation, and no per-node record composed out of them is
  permitted, whether retained or composed per call. Construction operations are
  emitted directly out of that indexed state into Entity Graph Construction.
- **Execution-owned view slots.** A relationship view row is positional, and what
  fixes its positions belongs to the EXECUTION rather than to a row, a graph, or
  a model. One fetch plan yields one immutable view schema, and every graph that
  execution builds — its staging graph and each milestone graph alike — is laid
  out by that one schema.

  A schema fixes one slot tuple per `(source level, resolved concrete Entity)`
  pair, where the source level is the plan level that produced the projection: a
  level's own view is a slot on whichever source its parent rows came from, minus
  whatever that level's path-root guard excluded the concrete from. A guard
  selects parents by their own resolved concrete, so admission is a fact about
  the pair and never about a row. Two levels attaching one view key share that
  key's one slot, and the later write is what the slot retains. Broad and
  narrowed views of one direction take distinct slots.

  Each resolved concrete also has one merged slot tuple — the union of that
  concrete's own source layouts, in the member layout's canonical order — plus a
  translation of each source level's row into it, so merging carries a written
  position across once rather than resolving a key per read. Slot tuples are
  derived on the first reach of the pair they describe, are immutable, and are
  interned, so concretes no guard splits share one; and nothing about them is
  retained beyond the execution that planned them. No query shape may be cached
  for the lifetime of a model.
- **Exact-model member layouts.** Which members a resolved concrete Entity
  carries, in what order, where its Attribute / Value Object boundary falls,
  which positions its family's primary key occupies, which of its Attributes may
  hold the open temporal bound, and what canonical order its relationship views
  take are fixed by the accepted Metamodel alone. They
  MUST be derived per exact Entity and shared, never rebuilt per row, per graph,
  or per execution. A model whose accepted metadata fixes no such row — two
  members claiming one position, or a family primary key the row does not
  express — is refused where the layout is derived, as a raised error rather
  than a stored-data classification.

  A row is read against its layout and against nothing else: a graph-local
  logical identity is computed once, while the graph is built, through the
  layout's own primary-key positions, and merging consumes the resulting dense
  IDs without re-extracting or re-hashing a key. Duplicate valid keys within one
  Entity family share an ID; a projection whose key did not decode takes an ID of
  its own and merges with nothing.

  Two things a row is read *with* are owned beside those layouts rather than by
  any one materializing runtime: the single private sentinel a position the read
  did not carry holds, and the translation of a row into Entity Graph
  Construction's own carriers. Both are functions of the layout and the carrier
  algebra alone, so two managed value lifecycles materializing from one row read
  it the one way, and neither declares an absence marker the other's rows do not
  hold.

  A layout is owned by the exact model it was derived from, reached through one
  door, and derived on first reach of the Entity it describes. The collaboration
  has exactly two unsynchronized first reaches — a model's catalog slot, and a
  catalog's entry for one key — so concurrent first reach may publish more than
  one catalog for a model and more than one layout for a key; every catalog over
  one model and every layout for one key is interchangeable, so no layout's
  identity is load-bearing. Retained layout count and size are a function of the
  models a process connects to and the Entities its reads address, and are
  independent of the number of graphs materialized. Concurrency adds only what a
  losing racer was answered and kept, at most one object per lost race and only
  while that caller holds it: losing a model's catalog race retains a second
  catalog, counted over that model exactly like the first because its holder
  keeps deriving into it, and losing one Entity's entry race within a catalog
  retains a second layout for that key. A racer is a connection, any other
  source that holds a model's layouts, or any caller holding one layout for the
  work it reached that layout for. No process-global cache, weak cache,
  data-keyed cache, or query-result cache participates.
- **Deterministic graph order.** Merged logical nodes receive their zero-based
  allocation index by deterministic first-encounter preorder: roots in result
  order; relationships on each node in accepted metadata declaration order;
  the broad view before that relationship's narrowed views; narrowed views by
  canonical effective concrete-identity set; and children in to-many result
  order. That order is a relationship view SLOT order, established by the
  exact-model member layout's own rule and read by index: a walk visits a node's
  views in declaration order without sorting one. A repeated logical node reuses
  its first index. Population and lifecycle-state factory invocation both follow
  allocation order. Every node-indexed error uses that index, and the first
  missing population is the lowest unpopulated index.
- **Entity Graph Construction surface.** The collaboration is reached from
  `parallax.core.entity` and is deliberately absent from top-level
  `parallax.core`:

  ```text
  graph_construction_of(model: DomainModel) -> EntityGraphConstruction
  relationship_value_of(instance, relationship: RelationshipIdentity) -> object
  lifecycle_state_of(instance) -> object | None

  EntityGraphConstruction
    construct(
      build: (EntityGraphWriter) -> tuple[NodeHandle, ...],
      *, state_factory: ((ResolutionView, NodeHandle) -> object) | None = None,
    ) -> tuple[object, ...]

  EntityGraphWriter
    allocate(entity: EntityIdentity) -> NodeHandle
    populate(
      handle: NodeHandle,
      members: tuple[object, ...],        # the exact Entity's member row
      relationships: tuple[object, ...],  # one position per navigable direction
    ) -> None
    #   members[i]:        ABSENT | value | member row | tuple[member row, ...]
    #   relationships[i]:  UNLOADED | None | NodeHandle | tuple[NodeHandle, ...]

  ResolutionView
    resolve(handle: NodeHandle) -> object

  NodeHandle          # opaque, callback-scoped, no public attribute
  ```

  `EntityGraphConstruction` is per Domain Model and is reached only through
  `graph_construction_of(model)`, so `construct(...)` takes no model argument and
  cannot be handed a mismatched one; the per-Entity facts it derives once from
  accepted metadata — concrete class, identity-to-member-name mapping, and the
  declaration-ordered navigable relationships — live there rather than being
  recomputed per read. `build` is invoked exactly once with a writer that closes
  when it returns, and `state_factory` exactly once per node in allocation order
  with a fresh single-use `ResolutionView` that closes when that invocation
  returns. `relationship_value_of` answers the raw slot value including the
  private unloaded sentinel, and `lifecycle_state_of` answers whatever the state
  factory returned; these two are the whole of what a lifecycle reads back.
  Misuse raises `GraphConstructionError(RuntimeError)` carrying `code`,
  `message`, the applicable zero-based allocation `index`, the structured
  `identity` at fault, and an optional conversion `cause`. Its complete code set
  is these ten:

  ```text
  entity-graph-invalid-entity          entity-graph-node-already-populated
  entity-graph-invalid-member          entity-graph-node-unpopulated
  entity-graph-invalid-value           entity-graph-invalid-root
  entity-graph-allocation-closed       entity-graph-foreign-handle
  entity-graph-scope-closed            entity-graph-layout-mismatch
  ```

- **Layout correspondence, checked once per class and model.** A node's rows are
  written against the accepted model's member layout and read back through the
  publication plan its class carries, and those two orders are derived from
  different material — the model's from the inheritance ancestry and each
  contributor's declared members, the class's from the Python MRO and each class
  body's own declarations, at class creation, knowing no model. So the first time
  a model publishes a class the two are compared, and
  `entity-graph-layout-mismatch` refuses the pair when they disagree about the
  member row, about which positions are Value Object occurrences and which Value
  Object Class each takes, about the broad-relationship tail, or about any
  occurrence's own path layout at any containment depth. The comparison is per
  `(class, model)` and is made where the per-Entity facts are derived, so it is
  made once and no member read ever pays for it. It is the mechanism rather than
  a backstop: a positional row of the model's own width says how many members
  there are and nothing about which kind each position is, so a model and a class
  that disagree about a member's kind are unrepresentable at the door and
  detectable only here.

- **Construction is whole-graph per call.** One `construct(...)` allocates,
  populates, and publishes every node the call reaches, and there is no partial,
  incremental, or resumable form. That follows from two contracts already stated
  above rather than from an unfinished optimization: cycle closure requires every
  participant to exist as a shell before any of them is populated, and atomic
  publication requires every state factory to succeed before any lifecycle state
  attaches and before any root is delivered as the call's ordered result. Neither
  is satisfiable across two calls. What one call covers is
  **the roots it is given plus what is reachable from them** — never "the query
  result". A caller holding a result in several parts may construct each part in
  its own call; the parts share no graph-local identity, exactly as two `find`
  calls do not.
- **Graph-construction phase barrier.** Entity Graph Construction has three
  non-overlapping phases: allocate every shell; close allocation permanently
  with the first `populate()` and populate every node; then, only after the
  build callback returns and all population and root checks succeed, invoke
  lifecycle-state factories. Factory resolution sees every final Entity
  instance with scalars, Value Objects, and broad relationships fully wired,
  including cycles. It sees no attached lifecycle state and no published root,
  and it cannot allocate, populate, or publish.
- **Atomic lifecycle-state attachment.** Entity buffers factory results in
  allocation order and attaches none while any factory remains. Only after
  every factory succeeds does it attach all results and publish the ordered
  roots atomically. The first factory failure stops invocation, discards every
  buffered result, and leaves every allocated Entity lifecycle-state-free;
  `construct(...)` delivers no root at all rather than a partial tuple, so no
  node appears in the call's ordered result. What it does not do is take back
  what it already handed a callback, or keep a node the call reached out of
  caller-owned state a factory put it in.
  A factory that keeps the instance its resolution view answered still holds
  that instance after the call fails — fully populated, and
  lifecycle-state-free like every other. Rows attach as nodes are populated and
  are never rolled back, so what a failure withholds is every root and every
  lifecycle state, not the population already attached.
- **Construction scope closure.** A writer closes when its build callback
  exits, and a resolution view closes when its one factory invocation exits.
  Using either retained closed scope raises
  `GraphConstructionError(entity-graph-scope-closed)` before argument
  inspection. An active writer or resolution view receiving a handle from
  another construction instead raises
  `GraphConstructionError(entity-graph-foreign-handle)`. Current-construction
  handles remain resolvable during every factory invocation, but no operation
  accepts them after `construct(...)` exits.
- **Construction failure precedence.** Writer-operation failures are eager. A
  build-callback exception propagates unchanged and suppresses completion,
  root, and factory work. After a successful callback, the lowest unpopulated
  allocation index fails first. Only after every node is populated are roots
  validated from left to right for value shape, foreign construction, and
  membership. Factories then run in allocation order; the first factory
  exception propagates unchanged and stops later factories. State attachment
  and root publication occur last.
- **Whole-graph temporal pinning.** The Object Query's per-dimension temporal
  selections pin the whole graph; omitted Transaction Time is normalized to an
  explicit Latest selection, while Valid Time is always selected explicitly.
  The pin propagates per hop,
  matched by axis, to every temporal entity in the include tree — auto
  injected, never user-written. `history` / `as_of_range` return one root per
  milestone, each root **edge-pinned** at its milestone's from-instant;
  `snapshot.pin` reports only genuinely pinned axes (a scanned axis is absent,
  per the core rule that a scan is not a pin), and
  `parallax.snapshot.pin_of(node)` reports each node's own coordinates.
  `parallax.snapshot.edge_of(node) -> Edge`
  reports a temporal node's **milestone edge** as a distinct frozen `Edge`
  value exposing one strict-typed accessor pair per dimension — the established
  arity-accessor house pattern (§2's `result()` / `result_or_none()`) applied
  to dimension access: `edge.tx_time -> datetime` raises
  `UndeclaredAxisError` when the Entity does not declare the dimension,
  `edge.tx_time_or_none -> datetime | None` returns `None` instead,
  and `edge.valid_time` / `edge.valid_time_or_none` behave identically for
  Valid Time. Every value a declared dimension yields is the **finite**
  from-instant of the node's milestone on that axis (core's edge pin) —
  defined for every temporal node regardless of how the read was pinned;
  calling `edge_of` on a non-temporal node raises. `Edge` is deliberately not
  a `Pin`: a `Pin` carries an entry only per actually-pinned axis and may
  carry the `LATEST` sentinel, while an `Edge` answers every declared axis
  and is always finite — never `LATEST`, never absent-because-scanned. The
  strict accessors keep replay code narrowing-free: a caller replaying an
  Entity's declared dimensions reads `edge.tx_time` as a plain `datetime` and
  either passes it straight to `as_of(...)` or compares it against a freshly
  read edge (the stale-web-edit recipe below). The
  `snapshot-history-includes` feature
  is **deferred, not invalid**: combining `.history()` with `.include()`
  builds an ordinary valid Object Query with no Snapshot feature metadata. After
  target resolution and query validation, Snapshot recognizes a query carrying
  Includes beside a scanning Temporal Selection as matching
  its Deferred Execution Feature and raises
  `DeferredFeatureError(execution-feature-deferred)` before SQL generation
  or Database Port access. It never raises `QueryDefinitionError`. Whether a
  query **scans an axis** is one `m-temporal-read` question with one
  answer, asked here and again by the executor dispatch that sends a scan to
  the milestone-set read. It is a field read over the Temporal Selection clause:
  every other clause is that clause's sibling, so no ordering, cap, or Include
  can stand between the two facts, and one scanned dimension answers *scan*
  however the other dimension is pinned. Neither another clause nor a pin on the
  other dimension can
  hide the deferred Feature from this seam or divert a scan away from the
  milestone-set executor. The milestone-set executor converts every returned row
  into one staging graph and applies the shared publication gate before reading a
  milestone edge or sort key. An unavailable temporal start is therefore a
  `StoredDataIssueInput` and then a `SnapshotDecodingError`, never a temporal
  partitioning or sorting error; only clean rows are grouped by edge.
- **Closed-world relationships.** An included to-one is the related node or
  `None` (loaded-null); an included to-many is a `tuple` (possibly empty —
  loaded-empty is `()`). A relationship outside the include set is
  **unloaded**: attribute access raises `UnloadedRelationshipError` naming the
  path and the include fix, and
  `parallax.snapshot.is_view_loaded(node, Owner.items)`
  answers without raising. Access never issues SQL — there is no lazy loading
  in this lifecycle.
- **Structured inspection keys.** `is_view_loaded` and `view` first require
  private `SnapshotNodeState`. Both accept only a class-derived
  Relationship Path; bare relationship-name strings are not accepted. They
  form one private key per segment from that segment's structured Broad or
  Narrowed Relationship View identity. A Relationship Path carries no model and
  no process-local identity, so there is no ownership relation to check here:
  a path naming a relationship the node's model does not declare is answered by
  the owner rule below rather than by an identity comparison.
- **Relationship-path owner.** The path's starting
  owner must apply to the supplied node's concrete Entity Identity. A
  relationship declared by an accepted ancestor applies to its concrete
  subtype. An unrelated owner raises
  `SnapshotInspectionError(snapshot-view-owner-mismatch)` with the operation,
  node Entity Identity, and structured path. `is_view_loaded` raises this
  error rather than returning `False`. Path construction guarantees that each
  later segment applies to its predecessor's target, including a target
  changed by narrowing.
- **Relationship-path inspection.** `view(node, path)` traverses every
  relationship segment from left to right using only already loaded Snapshot
  state; it never issues SQL. Narrowing changes the accepted target type for
  later segments, so
  `view(owner, Owner.pets.narrow(Dog).doghouse)` traverses the narrowed pets
  view and then the `Dog.doghouse` relationship. To-many segments fan out,
  null and empty intermediate branches contribute no terminal value, and a
  path containing any to-many segment returns one flat tuple of non-null
  terminal values in traversal order with duplicates preserved. An all-to-one
  path returns its terminal Entity or `None`.
- **Relationship-path loaded state.** `is_view_loaded(node, path)` is `True`
  exactly when every relationship view on every reachable branch is loaded.
  The uninstantiated suffix of a null or empty branch is vacuously loaded.
  `view` instead raises `UnloadedRelationshipError` for the first unloaded
  view in path-segment order and, within fan-out, source-tuple order.
- **Narrowed views.** A narrowed include populates a distinct **narrowed
  view** keyed by relationship name plus effective concrete-subtype set — it
  never marks the broad relationship loaded. Views are read with
  `parallax.snapshot.view(node, Owner.pets.narrow(Dog))`: the include-path
  grammar names the view, equivalent authored narrowings (`.narrow(Pet)` vs
  `.narrow(Cat, Dog)`) resolve to the same effective set and therefore the
  same loaded view, and differently narrowed views (the corpus's `pets[Dog]`
  and `pets[Cat]`) coexist on one node as independent simultaneous views. An
  unrequested narrowed view raises `UnloadedRelationshipError` naming the
  derived view key; `is_view_loaded` accepts the same narrowed-path argument.
- **Snapshot inspection failures.** `SnapshotInspectionError(RuntimeError)`
  names the inspection operation and, where one is known, the node's own
  concrete Entity Identity. Its complete code set is these four:

  ```text
  snapshot-node-required        snapshot-pin-unavailable
  snapshot-view-owner-mismatch  snapshot-edge-unavailable
  ```

  `snapshot-node-required` refuses a value that carries no `SnapshotNodeState`
  — a plain Entity instance, or a node of another lifecycle — and is checked
  **before** any path, relationship, or temporal validation, so an inapplicable
  path on a non-Snapshot node reports the lifecycle rather than the path.
- **Materialization failure translation.** A modeled read that fails inside
  graph construction, lifecycle build, or a per-node state factory raises
  exported `SnapshotMaterializationError(RuntimeError)` with the sole stable
  code `snapshot-materialization-failed`, exactly once, preserving the original
  failure as its chained cause and publishing neither a partial Entity graph nor
  a Snapshot. Every other failure a read can take keeps its own owner's
  classification and is never rewrapped here: query definition and target
  resolution, deferred features, transaction ownership, adapter and database
  errors, SQL generation, and the `SnapshotDecodingError` publication refusal
  raised before graph construction begins.
- **Eager include execution.** One query per non-empty relationship level
  (semi-join against the parent level's keys); an empty level short-circuits
  its subtree; declared descriptor `orderBy` governs child ordering; narrowed
  relationship views load exactly the requested narrowed set keyed by
  relationship name and effective concrete-subtype set; the `1 + L` round-trip
  ceiling is pinned by the authored statements and `then.roundTrips` oracle.
- **Explicit writes.** All writes go through the Parallax Transaction
  (§5) — the handle has no write methods. Graph edits are impossible (nodes
  are frozen); the only mutation idiom is deriving an **Edited Copy** through
  `value.edit(**changes)`, which returns the same frozen Entity Class carrying
  a **Change Record** mapping each touched field to its **original** value —
  the value the field held when first touched in the edit chain (edits of
  edits merge records, keeping the earliest original per field). `edit`
  **validates**: it applies the same build-time rules as construction —
  unknown member names are rejected, primary-key, read-only, and
  framework-owned members may not be assigned,
  **relationship members are rejected outright** (only mapped scalar
  attributes and value-object members are assignable; a relationship edit has
  no canonical row lowering in this slice — no cascade and no deferred
  association mutation semantics exist to lower it to), and every
  value passes the §2 scalar input policies — so an invalid edit raises at
  edit time, never at the database. Nodes carry no change tracking; the
  derived copy's change record is an explicit write input, and there is no
  merge-back (no re-association, no returned managed object). At lowering, a
  touched field whose current value equals its recorded original drops out of
  the **effective change set**, so a net-zero edit chain (`100 → 200 → 100`)
  contributes nothing and an update whose effective change set is empty
  issues **no DML** — uniformly for non-temporal and temporal entities
  alike (§5). Write inputs are the entity classes themselves:
  full instances for `insert` (the Create Payload), Edited Copies or
  instances for the other verbs (§5). The **stale-web-edit** recipe
  transports the displayed milestone's **edge on every declared dimension**: at
  render time the service reads the row and captures `edge_of(node)` — the
  `Edge` answers each declared dimension's start instant as a plain `datetime`
  (`edge.tx_time` is the displayed milestone's own `tx_start`, mapped
  to `in_z`) — and sends the
  whole edge with the form. On submit, the service reads the **current**
  milestone and **compares** its Transaction-Time coordinate against the
  transported one: `edge_of(current).tx_time != edge.tx_time` is the
  application's own staleness test, and the refusal it raises is the
  application's own error rather than a framework one — no framework error
  carries the meaning "the milestone the form displayed is no longer the
  current one", and the framework is not a party to this comparison under either
  Effective Concurrency Strategy. A
  Transaction-Time pin cannot make that assertion in a comparison's place: it
  *selects* the displayed milestone whether or not it is still current, which
  is the one thing the submit needs to know. A **Bitemporal** Entity still
  pins Valid Time at the transported coordinate —
  `as_of(valid_time=edge.valid_time)`, strictly `datetime`-typed with no
  narrowing — because a milestone's from-instant lies inside its own
  `[start, end)` interval by construction, so that pin selects exactly the
  **displayed** rectangle rather than a different one reached through a
  defaulted-Latest dimension; its Transaction-Time axis is left at the latest
  default, so the read answers that rectangle's current milestone. The service
  then applies the payload fields to a copy and updates.

  Staleness surfaces at two points and the recipe covers both. A writer who
  chained a replacement **before** the submit read is caught by the
  comparison, which authors no DML at all. A writer who chains one **between**
  the submit read and the flush is caught by the write: the transaction
  observed the current `in_z`, and the concurrent chain leaves a row whose
  fresh `in_z` fails the observed-`in_z` gate (a zero-row close — the conflict;
  a Bitemporal Entity's close additionally *addresses* the observed
  rectangle's own Valid-Time end, under both strategies, so it means exactly that
  rectangle whether or not it gates, per `m-bitemp-write`), while an untouched
  row succeeds. The recipe is therefore legal under **both** effective
  strategies, for different reasons (§5): Locking takes a shared read lock on the
  current row at read time, so once the comparison passes nothing can
  supersede that row before the flush, while Optimistic takes no lock and
  the gate covers exactly that window.

  Weaker transports fail. The `LATEST` sentinel is not a coordinate: it
  re-resolves to whatever milestone is current at submit time, so a comparison
  against it holds vacuously and the stale edit lands. A wall-clock display
  instant is not the milestone's own coordinate: Transaction-Time instants
  order by **assignment**, not commit, so a writer whose transaction began
  before the display fetch can commit a replacement whose `in_z` predates the
  captured instant — a wall-clock value need not equal the `in_z` of the
  milestone actually displayed, and comparing against a coordinate that is not
  the milestone's identity answers a question the submit did not ask. Only the
  edge is exact. Edge transport is Reladomo's own answer with the detach
  removed: its detached copy carries the milestone's `IN_Z` offline and the
  merge-back gate binds that carried coordinate — transport, never
  reconstruction. The idiom requires no detached objects.
- **An edit preserves everything it neither replaces nor invalidates.**
  `edit(**changes)` replaces the declared member state the caller authored and
  carries every other kind of instance state forward unchanged, apart from the
  single derived kind it invalidates below. An Edited Copy
  of a materialized node therefore answers relationships exactly as that node
  does — a loaded to-one or to-many is the *same* already-materialized objects
  rather than a re-read, an unloaded one raises `UnloadedRelationshipError`
  naming the path and the include fix — and `is_view_loaded`, `view`, `pin_of`,
  and `edge_of` all answer for the copy as they answer for its source.

  A carried view describes what the source's read observed, and that is all an
  edit can leave it describing: a relationship member is never assignable
  through `edit`, so no edit changes a relationship member, and a view can only
  come from a read, so the framework never re-resolves one offline. A copy that
  authors a relationship's **join endpoint** consequently carries a view
  describing the **pre-edit** target — `copy.customer_id` is the authored value
  while `copy.customer` is still the customer the read observed — and a view of
  the new target is obtained by reading.

  Preservation is by **complement**: what an edit carries is everything it
  neither replaces nor invalidates, so a new kind of instance state travels
  without the edit surface learning its name unless the class itself declares
  that state derived. Exactly one kind is invalidated rather than carried. A
  slot naming a `functools.cached_property` on the value's class holds an answer
  computed from declared state the edit may have replaced, so the edit drops it
  and the next access recomputes it: a derived cache is recomputed, never
  carried. The rule reads the descriptor off the class, which is what lets it
  need no registry and no lifecycle involvement — and also fixes its reach: a
  cache a class writes into `self.__dict__` by hand declares nothing, so it is
  carried like any other slot. Reading the descriptor off the class also confines
  the rule to names a class may declare: the framework's own `__parallax_` prefix
  is reserved from every declaration's class body (§2), so no class body declares
  a lifecycle's state or a Change Record derived.

  The copy carries the source's `Pin` too, which makes the read-only rule
  indifferent to how the write was authored: an Edited Copy of a view pinned at
  a **finite Transaction-Time instant** is read-only exactly as the view is, so
  `tx.update(node.edit(...))` over such a view raises
  `TransactionTimePinReadOnlyError(transaction-time-pin-read-only)` at the
  verb, under either Effective Concurrency Strategy, before any DML. Deriving a
  copy is not a route to rewriting the Transaction-Time past, and no strategy is
  either. A plainly constructed instance has no views and no lifecycle state to
  carry, so an edited construction and an edited node stay distinguishable by
  **provenance** rather than by editedness: the Snapshot inspection surface
  answers for the second and refuses the first, whatever change record either
  one carries.
- **`edit` is the only door, and every inherited copy path is refused.**
  `model_copy` with or without `update=`, the deprecated Pydantic v1 `copy`,
  `__copy__`, and `__deepcopy__` each raise `EditError(edit-use-edit)` and
  create no value. The refusal short-circuits the whole call before any
  argument is examined, so no partially built value and no unjudged assignment
  exists at any point. One reachable copy path would defeat the purpose, which
  is that no provenance-less Entity value and no unearned Change Record exists:
  `__copy__` and `__deepcopy__` shallow- and deep-copy the instance dictionary
  the Change Record lives in, so the result would carry provenance it did not
  earn and lower to a sparse row built from originals that were never its own;
  and the deprecated `copy` shim reaches neither the framework's name
  resolution nor its judgement, so a primary key or a framework-owned member
  could be set through it. `edit` is the object-copy verb; `update` remains the
  Transaction persistence verb.

  `edit()` with **no changes** is legal and yields an Edited Copy carrying the
  receiver's **own** Change Record forward, which is what the merge rule above
  already says a zero-change merge of records is. On a never-edited value that
  record is empty, so its `edited_row` (§5) is `None`; on an already-edited
  value the pending edit survives, because stamping an empty record would
  discard it and silently turn a write into nothing to write. Nothing is
  validated, because nothing was authored. Refusing it would need a ninth code
  to prevent
  something already represented as "nothing to write", and it would draw a line
  a caller cannot predict: a net-zero edit means the same thing and is not
  detectable at the call site, so only one of the two could ever be refused.
- **A materialized node does not pickle.** Wherever `pickle`'s own dispatch
  asks an Entity value carrying lifecycle state for its reduction and reaches
  `Entity.__reduce_ex__`, `pickle.dumps` raises the language's own
  `pickle.PicklingError` — not a Parallax exception and not a Parallax code —
  with a message naming the value and what to move instead. Both answers a
  pickle could otherwise give are untrue. Carrying the state would hand a
  caller a value that answers a lifecycle's inspection surface and claims a
  stored row's write evidence on the strength of a byte string, its retained
  observation coming back as a fresh object whose consumed state is whatever
  the bytes happened to capture. Dropping it silently would answer a request to
  preserve a value with one that lost what the caller never learned it had, and
  whose write the keyed verbs then refuse (§5) for provenance it appeared to
  carry. So the refusal is at the door, and a caller moving a read's data
  across a process moves domain data — `model_dump(...)` output or a Wire
  read — and reads the row again where a write is meant to settle. Everything
  carrying no lifecycle state is untouched: a plainly constructed value and an
  Edited Copy of one round trip, and so does every Value Object, including one
  a read published, since only an Entity node carries lifecycle state at all.

  The refusal sits on `__reduce_ex__`, the name `pickle`'s own dispatch asks a
  value for, which is why that name is reserved from every class body (§2);
  `__reduce__` and `__getstate__` are what `object.__reduce_ex__` consults once
  the guard has passed, so they stay authorable and an authored one still runs.
  A node nested anywhere in what is being pickled is asked for that name the
  same way the pickle's root is. What the guard asks is whether the
  constructing lifecycle's state is attached to the value's own lifecycle slot
  and holds anything but `None` — that slot read through its own descriptor,
  never a name a class can bind, and the same slot a read attaches state to and
  an edit carries it forward in. So no authored `__getattr__`, `__getattribute__`,
  `__dict__`, or descriptor bound at the slot's own name makes a lifecycle-free
  value answer as a materialized one, or hides the state of one that is.

  What the refusal does not reach is a pickle written without
  `Entity.__reduce_ex__` ever running. A pickling site can supply a reducer for
  the class through `copyreg`, a `Pickler.dispatch_table`, or
  `reducer_override`, which replaces the dispatch; a caller can invoke
  `object.__reduce_ex__(node, protocol)` directly; and a class can answer for
  the name rather than bind it — by authoring `__getattribute__`, which the
  lookup for the name goes through, by assigning `__reduce_ex__` onto the class
  once it exists, or by binding a descriptor whose `__set_name__` installs the
  name after the class body has been judged. The reservation is a judgement of
  the class body as authored, not a hold on the attribute for the life of the
  class. Each of those routes has stepped past the entry point rather than
  through it, and what it gets is the pre-refusal answer rather than a truthful
  one; how much of the lifecycle state travels with it is then its own doing,
  because delegating to `object.__reduce_ex__` reaches `Entity.__getstate__`'s
  strip only when no authored `__reduce__` or `__getstate__` answers first, and
  either of those — both deliberately left authorable — can hand back state
  carrying the slot. So what the refusal is for is `pickle`'s own dispatch
  reaching `Entity.__reduce_ex__` — every accidental pickle, which is where the
  untruth would otherwise be told with nobody choosing it — rather than a
  boundary against a class or a caller that sets out to serialize a node
  anyway. Nothing is refused on the way back in: bytes that carry no lifecycle
  state — including any written before this rule — load into the ordinary value
  they describe.
- **A Value Object has the same copy verb, and the same sealed doors.**
  `ValueObject.edit(**changes)` returns a validated copy carrying every member the
  value populates and the caller did not name, changing only what `changes` names:

  ```python
  customer.edit(address=customer.address.edit(city="Springfield"))
  ```

  Assigning an occurrence replaces its subtree whole under every Storage Layout
  (`core/spec/m-storage-layout.md`), so restating a whole address to change one
  field is what deletes the fields the restatement forgets. This derives the new
  value from the old one instead, which makes the safe spelling also the shortest
  one. `edit-nested-path` still refuses reaching *into* an occurrence from
  outside it, so composing edits is the only spelling of a nested change.

  It is the same verb, not an analogue: one `EditError`, one closed code set, and
  the same `judge_assignment` verdict over the member's own accepted metadata,
  reached through the same resolve-judge-rebuild core `Entity.edit` uses. Three
  things follow from a Value Object having no identity and no Entity, and they are
  the whole difference:

  - **No Change Record.** None is stamped and none is carried. Provenance answers
    "what did this object's caller touch", which is a question about an identity a
    Value Object does not have — an occurrence reaches storage only as part of the
    Entity containing it, so it is never independently written and the Entity Row
    Codec never reads one off it.
  - **Half the code set is unreachable**, structurally rather than by policy.
    `edit-primary-key`, `edit-read-only`, `edit-framework-owned`, and
    `edit-relationship-member` each report something `m-value-object` does not
    have: the declaration engine refuses `primary_key=` and `read_only=` on a
    Value Object member, framework ownership is derived from an Entity's version
    Attribute and As-Of Axes, and a Value Object declares no relationships. The
    reachable subset is therefore `edit-use-edit`, `edit-unknown-member`,
    `edit-nested-path`, and `edit-value-mismatch`. That is a statement about what
    this door can raise, not a narrower error class: minting one would give a
    single rule family two names and two chances to drift.
  - **Presence is carried forward member by member.** A member the value never
    populated stays unpopulated and so stays absent from the serialized document,
    rather than becoming an explicit null; a member named as `None` becomes one.
    That distinction is what lets a value read from storage be written back
    unchanged, which is what replacement semantics rest on.

  The inherited copy doors are sealed exactly as an Entity's are — `model_copy`
  with or without `update=`, `copy`, `__copy__`, `__deepcopy__`, each raising
  `EditError(edit-use-edit)` before any argument is examined — for a reason of
  their own. `model_copy(update=...)` writes its values in **without validating
  them**, so it can build a Value Object no declaration admits: a required member
  cleared, a leaf holding a value of another type. A structurally invalid
  occurrence then serializes into the stored document exactly as a valid one does,
  and under replacement that document is the persisted truth.
- **Edit refusals are aggregated, coded, and canonically ordered.** One
  `EditError(ValueError)` covers all three authoring surfaces — `Entity.edit(...)`
  and `ValueObject.edit(...)` here and a predicate write's `Attr.set(...)` (§2) —
  because the assignment rules are
  one set with one home. There is no `ModelCopyError` and no `ProvenanceError`;
  the shared judgement carrier stays internal to `parallax.core.metamodel` and
  is never re-exported from top-level `parallax.core`.

  ```text
  EDIT_CODES                # the complete set, closed at eight
    edit-use-edit             edit-primary-key
    edit-unknown-member       edit-read-only
    edit-relationship-member  edit-framework-owned
    edit-nested-path          edit-value-mismatch

  EditViolation             # frozen, slotted
    code: str               # drawn from EDIT_CODES
    location: ModelLocation
    member_name: str | None
    message: str            # non-empty; excluded from equality

  EditError(ValueError)
    violations: tuple[EditViolation, ...]   # non-empty, canonically ordered
    codes: frozenset[str]
  ```

  `ModelLocation` is the accepted closed union `MetamodelIssue` already uses,
  and every violation carries one. A violation of a member the authored name
  resolved to locates **at that member** — `AttributeLocation`,
  `RelationshipLocation`, `ValueObjectLocation` for a whole Value Object
  occurrence, or `ValueObjectAttributeLocation` for a scalar inside one — and
  carries the member's name. A violation of a name that resolved to **no**
  member locates at
  the `EntityLocation` of the Entity whose declaration was searched, with
  `member_name` carrying the authored name; the location degrades to the Entity
  rather than becoming absent, because a member location would have to name a
  member the model does not declare. `edit-use-edit` examines no member, so it
  carries that same `EntityLocation` and a `member_name` of `None`. There is
  deliberately no `.code` attribute: selecting one
  violation to expose would misreport the others, which is what `codes` is for.

  Every violation of an **Entity** surface locates that way, because the Entity is
  known at all of them. `ValueObject.edit(...)` is the one surface where none of
  it holds: a Value Object Class is a reusable shape rather than a position in a
  model — the same class composes into occurrences of many Entities, and no one of
  them owns its members — so its violations locate at `ModelRoot`, whatever they
  refuse and whether or not a member resolved. `member_name` still carries the
  member, and the message still names it under the class it was addressed
  through, so a report is no less diagnosable; what it does not do is claim a
  model position this door never reaches.

  An authored **dotted** name is refused as `edit-nested-path` rather than as an
  unknown member, on either edit surface. `customer.edit(**{"address.city": ...})`
  and `address.edit(**{"geo.country": ...})` both name a path below a member's own
  boundary, which is exactly what `Customer.address.city.set(...)` is refused for:
  an edit assigns whole members, and a Value Object binds its whole document, so
  there is no sparse write beneath an occurrence through any door. Reporting the
  member as unknown would misdiagnose a member the declaration carries perfectly
  well. Both codes locate the same way, since a dotted name reaches no member
  either way.

  Reporting is **aggregated, not first-failure**, as core ADR 0001 requires.
  Every member the call names is examined and each contributes **at most one**
  violation — its own first verdict in the shared judgement's settled rule
  order — with resolution preceding judgement, so a name that resolves to no
  member contributes its resolution violation and nothing else. Violations are
  ordered by canonical location key, then code, then `member_name` with an unset
  name first — the first two terms exactly as accumulated Metamodel Issues are
  ordered, and the third because two names that reached no member share one
  `EntityLocation` and one code and would otherwise tie. Ordering is total, so a
  report never depends on caller keyword order. `edit-use-edit` is the one
  refusal that examines no member at all. No cause is retained: the error is
  raised `from None`, and each violation's message carries the judgement's own
  rendered text.

  A message states **what the violation is**, with the facts needed to diagnose
  it: the member as the model declares it, which of the three designations
  refused it, and — for a mismatch — the offending value and the declared type.
  It does not prescribe a remedy, and `edit-use-edit` is the deliberate
  exception that names one. The four judgement-sourced rules refuse an
  assignment that no other call makes legal, so there is no alternative to name;
  and their text is the shared judgement's, rendered verbatim by the serialized
  write boundary (§5), where a remedy phrased for an `edit(...)` caller would be
  wrong. `edit-use-edit` refuses a *call*, is unreachable from any other
  surface, and its remedy is exactly the call the caller should have made.

  `edit-value-mismatch` preserves the judgement's deliberate collapse of scalar
  type, Value Object document, multiplicity, and nullability failures into one
  classification; the finer reason travels in the message, never in the code.
  `edit-read-only` stays separate from `edit-framework-owned` because
  `attr(read_only=True)` is developer-declared.

  **The framework's assignment rules never partially report**: every violation
  of them is in the `EditError`, and the whole aggregate is raised before
  construction begins. That is a claim about those rules, not about the call.
  The judgement checks conformance to the declared Neutral Type; Pydantic
  checks the Python annotation and any author-declared `@field_validator` or
  `@model_validator`, which continue to run on an Edited Copy (§2's build-time
  rules). A value that passes judgement and then fails the validating
  constructor propagates its `ValidationError` **unchanged**. Re-rendering it
  as `edit-value-mismatch` would launder a framework defect into a
  developer-input refusal and make the aggregate dishonest: a disagreement
  between the two about a value is a judgement coverage defect to fix in the
  judgement.
- **Framework-owned members behave three ways.** Accepted metadata designates a
  member `framework_owned` (`core/spec/m-metamodel.md`) when the framework
  supplies its value and the caller never does — today the optimistic-lock
  version column and both endpoints of every declared As-Of Axis, and every
  category a later contract designates without adding a code or a rejection.
  Where such a value arrives from decides what happens:

  - **Authored at construction** — refused where the mistake is, by a
    `field_validator` the declaration engine installs on each framework-owned
    field. It surfaces as Pydantic's own `ValidationError`, in the same report
    as every other construction-time rejection of that call. It is deliberately
    not an `EditError`: construction is not an edit, and minting an edit code
    for it is exactly where the two error families would come to describe one
    call.
  - **Assigned after authoring** — through `edit(...)`, `Attr.set(...)`, or the
    serialized write boundary — refused by the shared judgement as
    `edit-framework-owned`. One rule rather than three checks is the point:
    those surfaces differ only in how they resolve a name to a member.
  - **Arrived by hydration** — readable on the value and silently omitted from
    the Entity Row Codec's `full_row` and `edited_row` (§5), never an error.
    Refusing it would make a stored row unreadable, and emitting it would
    launder stored state into an assignment the caller never made.
    Materialization is safe by construction: it enters no Pydantic constructor
    at all — a published node's whole state is assembled and attached once — so
    the validating constructor that refuses an authored value is never reached.

  A framework-owned member is therefore **never required at construction**,
  whatever its declared nullability: a caller who cannot supply a value cannot
  be asked for one, so the member reads as absent — outside `model_fields_set`
  and valued `None` — until hydration supplies it. An `edit(...)` carries every
  framework-owned member forward untouched rather than re-submitting it to the
  constructor that refuses an authored one, which is also what preserves a
  materialized current milestone's open-interval sentinel.

  The designation is derived rather than authored, so no declaration surface
  gains an option and the canonical descriptor is unchanged. It stays distinct
  from `optimistic_locking`, which names a role, and from `read_only`, which is
  the weaker "authored once, then immutable" claim, so a rejection can say
  which of the three it is. Neutral write validation reads it too: the framework
  supplies the value, so a write row omitting a framework-owned member is not a
  caller omission to report — the version a versioned insert carries is derived
  (`m-opt-lock`), and the interval bounds were never row members at all.

## 4. Result collections and materialization

### Snapshot results

- **Eager materialized collections.** Query construction is side-effect-free;
  execution happens exactly at `db.find(query)` and returns a value. Roots are
  reached only through `Snapshot[T]`'s three accessors; `results()` returns a
  real built-in `list[T]` the caller owns (fresh copy per call — the container
  accessor is unaffected by node immutability). Included to-many
  relationships are `tuple` fields on frozen nodes (§3). Nothing is an
  `m-op-list` query-backed lazy list; iteration, indexing, and bulk
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
  `type(node)`. Narrowed views: `parallax.snapshot.view(node, path)` returns
  the view's `tuple` for a to-many hop (the related node or `None` for
  to-one); a single-concrete view is typed as that concrete class, and a
  multi-concrete view's elements are their concrete classes.

### Streamed results

- **`stream` is the delivery peer of `find`, in every namespace `find` has
  one.** The public streaming surface is `db.stream` / `tx.stream`
  (`SnapshotStream[T]`) beside `db.wire.stream` / `tx.wire.stream`
  (`SnapshotStream[WireEntity]`), exported from `parallax.snapshot`. Delivery is
  the verb and representation stays the namespace, so there is no `format=`
  argument, no public format enum, and no `findInBatches`-shaped call. Each
  accepts exactly the query spellings its `find` peer accepts and crosses the
  same read gate, at context entry rather than at the call.
- **`SnapshotStream[T]` is deliberately not a `Snapshot[T]`.** Its whole
  surface is `__enter__` / `__exit__`, `__iter__`, `checked()`, `pin`, and
  `__repr__`. There is no `results()`, no arity accessor, and no way to re-read
  what already went past — a caller holding one holds a position in a delivery
  rather than a value. Iterating is the default view and raises
  `InvalidDataError` at a root whose stored state contradicted the model;
  `checked()` is the same delivery with that root arriving as its `InvalidData`
  record, and the two views are the exact peers `Snapshot` and
  `CheckedSnapshot` are.
- **Scope binding is one state field checked at every entry point**, in the
  discipline `UnitOfWork` already uses rather than by relying on
  `__enter__`/`__exit__`. Constructing a stream reaches nothing: the gate, the
  page plan, and every statement belong to the entered scope, so an un-entered
  stream emits nothing and reads nothing. Delivery is lazy, so each ADVANCE of a
  view is an entry point of its own: an iterator taken inside the scope and
  advanced after it closed issues no statement, publishes no root, and leaves
  the state the scope exit settled. Entering twice, taking a second view of
  either kind, taking a second pass, advancing a view outside the scope that
  answered it, and reaching `pin` outside the scope all raise
  `SnapshotStreamStateError`, whose message names the rule and never the
  internals. Re-selecting one view is an error rather than a silent empty pass,
  which is the failure mode a still-callable streamed result invites. `pin` is
  available before the first page — a stream computes it from the query, as
  `find` does — and inside the scope alone, so "outside the scope, everything
  raises" is one rule rather than one rule with an exception. A milestone-set
  delivery answers the EMPTY pin there, exactly as `find`'s own milestone-set
  Snapshot does: a scan is not a pin, and each root it publishes stands at its
  own edge, read back through `pin_of` / `edge_of`.
- **`SnapshotStreamContinuationError` is the stream's other refusal, and the only
  one about the DATA.** It is a `RuntimeError` rather than a
  `SnapshotStreamStateError`, because nothing was misused and no caller can avoid
  it: two roots the database placed at ONE Continuation Order coordinate end the
  delivery, after every root before them has been published. It carries `code`
  `"snapshot-stream-continuation-order-not-total"`, `terms` (the
  `AttributeIdentity` tuple the coordinates were measured against), `coordinate`
  (an inert `tuple[object, ...]`, never a cursor), and `ordinal` (the delivery
  position of the first undeliverable root). It is frozen by hand exactly as
  `InvalidDataError` is — the same writable interpreter-owned names, and the same
  bypass boundary stated there — so `add_note` and chaining work while every
  other attribute assignment or deletion raises; `coordinate` is reachable by attribute access
  alone, and stays out of the message, the default repr, lifecycle events, and
  default logging. `m-snapshot-read` *Ending a delivery at a tie* settles when it
  is raised and what precedes it.
- **`batch_size` is public, per-call, and defaults to `1000`.** It counts ROOT
  positions, never included relationship rows, and is validated exactly as
  `limit` is: `type(batch_size) is not int` is an identity check, so nothing is
  coerced and `True` is not the page size 1, and a non-positive or non-`int`
  value raises `ValueError` at the call, before any plan or page exists. There
  is no handle-level default, no connection setting, and no environment
  variable — the only page size is the one a call names. It counts the roots a
  page DELIVERS: the statement asks for one more, which is the lookahead root
  `m-snapshot-read` prices, so `limit ?` binds `batch_size + 1` on every page a
  declared `limit` does not cap.
- **Refusal order matches `find`'s, and one order covers every read entry.**
  Typed `find` and `stream`, Wire `find` and `stream`, and `read_rows` refuse in
  the same sequence: re-entry first, then a connection over a model that
  composes no Entity Class (Typed only), then this call's own arguments —
  including, on a Wire entry, lowering its three accepted spellings to the
  canonical Object Query, which is an argument of the call and not a step above
  the refusal. The read gate and the deferred-Feature refusal follow, at context
  entry for a stream and at the call for every other entry, before any I/O.
- **Stability is per page, and a `tx.stream` loop that writes can be its own
  concurrent writer.** `m-snapshot-read` states the whole rule; what it means
  for this surface is that a loop mutating the member its query ordered by moves
  its own roots across the position the delivery already passed, and a root
  moved past that position is delivered again:

  ```python
  # at risk — the loop rewrites the member it ordered by
  with tx.stream(Order.where(Order.active).order_by(Order.status), batch_size=100) as orders:
      for order in orders:
          tx.update(order.edit(status="done"))

  # immune — an undeclared orderBy orders by the primary key, which no write moves
  with tx.stream(Order.where(Order.active), batch_size=100) as orders:
      for order in orders:
          tx.update(order.edit(status="done"))
  ```

  Delivery is also per ATTEMPT: `db.transact` may re-execute its callback, a
  root already consumed cannot be recalled, and the re-execution opens a fresh
  stream that delivers from the beginning — so a per-root effect owes the same
  retry-safety every other effect inside that callback owes.
- **The memory bound is gated as a SHAPE and reported as a number.**
  `m-snapshot-read` *What a delivery costs* bounds the Parallax-owned working set
  at `O(P_B + G_max)` with three named exclusions; this target grades that in the
  `cost` class (§10), as nine measurements over `tests/unit/`'s memory
  instruments. What is asserted there is a survivor census with no term in the
  result size and no term in how far the delivery has got, with the page graph and
  the published root counted separately and the Continuation Order's own width
  priced on a grid of its own — one coordinate per page ROOT whatever that width
  is, the width itself costing the plan once; the census is read five ways — over
  Parallax's own survivors, over every survivor whatever defined its type, over
  the references they hold, over what a holder older than the window took of
  them, and in bytes over the survivors and everything untracked they hold — so a
  per-PAGE retention hanging off what the delivery published fails it whether what
  grows is objects, references, or the bytes inside one container. All five walk
  outwards from the window's own survivors, so the independence claim is made
  again over the WHOLE PROCESS, as three totals with no baseline: every tracked
  object, every reference they hold, and what they and everything untracked they
  reach report through `sys.getsizeof`, equal across arms that differ only in the
  result size or the position reached. That reading needs no survivor to start at,
  which is what puts a holder older than the window — an implementation-owned
  registry banking one already-existing value per page — inside the claim rather
  than beside it. What it reaches is Python-level structure, so storage an object
  merely points at — a memory mapping (`mmap`), a buffer an extension owns — is a
  constant-size shell in all three, and no measurement in this target observes
  one; the graded claim is about the delivery's Python working set, which is what
  all of Parallax's own storage is. The
  middle layer is priced as a peak over the region one root's publication
  occupies, which the census cannot reach because nothing of it is alive when a
  sample can be taken; that peak is exactly equal across a thirty-two-fold spread
  of page sizes, which is the layer's own bound rather than a tolerance on it. Two
  of the three exclusions are demonstrated rather than claimed; the third — what
  the database and its driver hold — has no witness here, because the port these
  readings run against answers each page from a counter and holds nothing a driver
  would.
  What is not asserted anywhere is a byte total: `just
  python-report-stream-overhead` prints one, reading
  `languages/python/docs/stream-baseline.md`, and belongs to no aggregate for the
  reason every other `report` here does.

### Invalid stored data

- **The result element.** A Snapshot element is `T | InvalidData[T]`: a root
  whose whole requested include tree conforms is delivered as `T`, and a root
  some stored state contradicted is delivered as its record. Stored-data
  violations are always reported; there is no ignore posture, connection
  setting, or Object Query clause.
- **The published shapes**, exported from `parallax.snapshot`. None of the three
  accepts attribute assignment after construction: the two records are frozen and
  slotted, and `InvalidDataError` settles its read-only report and the message
  derived from it in its constructor, then refuses every later attribute
  assignment or deletion — including the inherited `args` the message lives in.
  The error is
  frozen by hand rather than as a frozen dataclass, because that spelling also
  refuses `add_note` on a `BaseException` subclass and `__slots__` restricts
  nothing there — the base always carries an instance dictionary. The hand-written
  refusal leaves exactly the state the interpreter owns (`__cause__`,
  `__context__`, `__notes__`, `__suppress_context__`, `__traceback__`) writable,
  so chaining, tracebacks, and notes behave as on any exception.

  **The freeze is the type's own `__setattr__` / `__delattr__`, so it binds
  attribute assignment and deletion and nothing else.** Writing into the instance
  dictionary, calling `object.__setattr__`, and declaring a subclass that
  replaces those two methods all reach past it — and reach past
  `dataclass(frozen=True)`, slotted spelling included, in exactly the same way,
  so no representation an instance carries its own state in is stronger. They are
  deliberate bypasses, outside the contract as `object.__new__` is for a sentinel
  class, and nothing short of one makes an instance Parallax raised report state
  it was not constructed with:

  ```python
  class StoredDataIssue:
      code: StoredDataIssueCode
      entity: EntityIdentity
      member: MemberIdentity | None
      object_key: ObjectKey | None
      path: tuple[str | int, ...]  # keyword-only, required
      stored_value: object  # keyword-only, required


  class InvalidData[T]:
      issues: frozenset[StoredDataIssue]
      data: T | None
      object_key: ObjectKey | None
      version: int | None
      edge: Edge | None
      ordinal: int


  class InvalidDataError(RuntimeError):
      invalid_data: tuple[InvalidData[object], ...]
  ```

  A `StoredDataIssue` names the concrete Entity it was judged against — the
  queried family root for an unknown family tag, which is the only case with no
  `member` — and the affected object, absent where an invalid primary key or a
  family tag naming no concrete subtype left no identity. It carries no
  cause, no mutable details mapping, and no separately authoritative message.
  `path` and `stored_value` are keyword-only and required, so a hand-constructed
  issue states both rather than inheriting an unavailable-value default.
  `InvalidData.issues` is unordered: identical diagnoses collapse, and reaching
  one affected object through several include paths does not duplicate it.
  `InvalidData.object_key` names the RESULT root rather than an affected
  descendant; `version` is populated for a decoded explicitly versioned root and
  `edge` for a decoded temporal one, so the two never appear together; `ordinal`
  is always the zero-based position in the ordered result. These are diagnostic
  facts only — they expose no observation address and grant no write authority.
  `InvalidDataError.invalid_data` is nonempty and is the exception's sole
  machine-readable report; its message derives a count and an issue-code summary.
- **The evidence an issue carries.** `stored_value` is the provider-normalized
  logical value that was judged and rejected and `path` is the entity-relative
  logical path of that occurrence, both as `m-snapshot-read` *Evidence a public
  issue carries* fixes them. In Python the frozen shapes are ordinary built-ins,
  with no frozen-dict type introduced: an array reads as a `tuple`, an object as
  a `types.MappingProxyType` over a detached copy, stored SQL or JSON null as
  `None`, an immutable scalar as itself, and a byte-like provider carrier as
  `bytes`. A member genuinely absent from a traversable stored object reads as
  `MISSING_STORED_VALUE`, exported from `parallax.snapshot`: a singleton whose
  sameness is identity — `repr` `MISSING_STORED_VALUE`, and the one instance
  through a copy, a deep copy, and a pickle round trip (§2 *Sentinel identity*).
  Both fields participate in `StoredDataIssue`'s equality; because a read-only
  mapping is unhashable and compares insensitively to member order, the record
  computes a matching structural hash of its own and caches it, rather than
  inheriting a field-tuple hash that would refuse the value or disagree with
  equality. `stored_value` is excluded from the record's `repr`, and evidence
  reaches no exception message, lifecycle event, SQL emission, log line, or
  automatic formatter. Exactly one frozen copy of it is retained: conversion
  freezes it where it translates the detecting seam's finding, and shares it by
  reference to the public issue and to `InvalidDataError` — graded in the `cost`
  class (§10) as a retained-bytes difference over the rejected value's own size,
  against one frozen copy of it. Repeated reach shares that one copy too: a
  second projection of a logical node is a second row, judged and frozen apart,
  and the graph builder answers each of its issue records with the equal record
  the node already retains, so the second row's frozen value is discarded with
  the conversion that made it rather than retained beside the first. Sharing is
  settled per rejected occurrence, so two projections that agree about one
  occurrence and disagree about another retain one copy of the first and both of
  the second.
- **Default and checked views.** `Snapshot`'s accessors are the default view:
  each performs its existing arity check FIRST and then raises `InvalidDataError`
  when the roots it narrowed to carry invalid data. `result()` and
  `result_or_none()` therefore report exactly their sole element's record, and
  `results()` aggregates every invalid root in result order.
  `Snapshot.checked() -> CheckedSnapshot[T]` is a read-only view over the same
  result storage: it performs no I/O, forwards `pin`, keeps the
  same arity errors, and returns `T | InvalidData[T]` in band from `result()`,
  `result_or_none()`, and `results()`. `checked().results()` is the complete
  eager checked surface; a caller partitions that finite union with ordinary
  collection operations, and Parallax adds no partition method or side
  collection.

### Wire results

- **Two read interfaces, not a format argument.** The public read surface is
  `db.find` / `tx.find` (`Snapshot[T]`) beside `db.wire.find` / `tx.wire.find`
  (`Snapshot[WireEntity]`), and their streamed peers `db.stream` / `tx.stream`
  beside `db.wire.stream` / `tx.wire.stream` (§4). There is no `format=`
  argument, no public format enum, and no `db.typed` or `tx.typed` namespace. `db.wire` and `tx.wire` are
  lightweight views over the same connected model and adapter; `tx.wire`
  additionally shares the Unit of Work, observation ledger, locking, and
  Execution Lifecycle with the Typed transaction interface, so the two are not
  separate connections or transaction modes.
- **Capability follows the model, not the constructor.** `connect(adapter,
  model)` accepts a Domain Model of either provenance. A class-backed model
  serves both interfaces; a descriptor-backed model serves Wire and refuses
  Typed materialization with `SnapshotConnectionError(snapshot-class-backed-model-required)`
  at the read call, before any I/O. Both connection doors take a Domain Model,
  so provenance is the only thing capability follows.
- **Accepted query spellings.** `find` on either Wire view takes the canonical
  Object Query mapping, the canonical `ObjectQueryNode`, or — on a class-backed
  model — the Typed `ObjectQuery` authoring value directly. All three lower to
  one canonical node before the shared read gate, so no spelling reaches a
  different executor and no public serialization step is introduced. A
  descriptor-backed pure-Wire flow passes the mapping and imports no Entity
  Class, `EntityIdentity`, or Object Query node type.
- **The published value.** Every returned Entity mapping — result root and
  included node alike — is a `WireEntity`; there is no separate root type. Keys
  are declared model member names, never physical column names, and an
  inheritance participant additionally carries its stable variant spelling under
  `familyVariant`. Leaves are canonical Wire Values (`m-wire`), the same
  spelling the document codec stores; a temporal end's open bound carries
  `m-core`'s `infinity` literal. A Value Object occurrence in it is a mapping
  whose keys are the members the read contract carries, at every depth
  (`m-snapshot-read`, *What a materialized value carries*) — a member that
  contract does not carry is no key of it at all, rather than a key holding a
  `None` the document never stored. So a consumer reads presence off the node
  rather than assuming every declared name is there, and the node is exactly the
  document `to_document` derives from the Typed value of the same row: one
  materialization published two ways, never two answers about one stored
  occurrence.
- **Finite unwind.** Relationships render along the requested Include Paths
  rather than the merged identity graph, so a back-reference renders its target
  once, in full, and terminates — never a primary-key stub. A relationship no
  level loaded onto a node is absent from the mapping, which is what unloaded
  means. Positions reaching one merged node under one requested subtree answer
  the identical object, so graph aliasing survives without copying.
- **The Python realization.** `WireEntity` is a public, non-constructible,
  read-only nominal `Mapping[str, WireValue]` implemented by a private frozen
  `dict` subclass; nested mappings and lists are frozen private subclasses too.
  `isinstance(value, dict)` stays true while `type(value) is dict` is false;
  ordinary mutation raises `TypeError` — every named mutator, the operators, and
  the repopulating `value.__init__(...)`, at every depth. The bound is the
  language's, not the design's: a caller that goes around the instance to the
  base descriptor itself (`dict.__setitem__(value, ...)`) reaches the layout that
  makes the value a `dict` at all, and no `dict` or `list` subclass in Python can
  refuse it. Values keep ordinary structural equality
  with plain `dict` and `list` values, remain unhashable, and serialize directly
  through `json`. `dict(value)` and `list(value)` yield ordinary containers the
  caller owns. `copy()`, `copy.copy`, and `copy.deepcopy` answer the same
  immutable value, and pickling produces ordinary domain data — a plain mapping
  or list — rather than reconstructing the frozen subclass. No framework
  metadata key is exposed. `WireValue` stays structural and adds no public frozen
  list or mapping type: deep immutability is a runtime guarantee, and insert
  data, changes, predicates, and Object Query input continue to accept ordinary
  structural mappings.
- **The same verdicts.** Both public materializers consume one root
  classification, so a Wire element is `WireEntity | InvalidData[WireEntity]`
  under exactly the rules §4 states for the Typed one, with the same default and
  checked accessors.

## 5. Transactions and writes

- **Demarcation construct.** Callback-only:
  `db.transact(fn, *, retries: int | None = None, concurrency: Literal["locking", "optimistic"] | None = None, retry_optimistic_conflicts: bool | None = None, isolation: IsolationLevel | None = None)`.
  Every option is **sentinel-backed** so an omitted option is distinguishable
  from an explicitly passed value: `None` (the default) means *apply the
  outermost defaults when this call opens the transaction — `retries=10`,
  `concurrency="optimistic"`, `retry_optimistic_conflicts=False`, and no
  isolation request at all — and inherit the active transaction's settings when
  this call joins one*. The closure
  receives the Parallax Transaction (`def fn(tx): ...`),
  `tx.find(query)` reads inside the transaction (participating according to each
  Entity's Effective Concurrency Strategy), and the call returns the callback's
  `T` directly **only after a durable commit** — on rollback, or on commit failure,
  the call raises instead of returning the value as though durable. A `with`-block demarcation is
  deliberately not offered: the core retry contract requires re-executing the
  closure, which a `with` block cannot do; a decorator form is a possible
  additive future. Bounded automatic retry follows core: deadlock-category
  failures retriable by default, bound default 10, `retries=0` disables the
  loop, exhaustion surfaces diagnosably with the attempt count;
  optimistic-lock conflicts join the retriable set only via
  `retry_optimistic_conflicts=True`.
- **Transient execution lifecycle.** `Database`, `Transaction`, `Snapshot`, and
  stream values expose no lifecycle accessors. An installed Provider receives
  one transaction-invocation Root Execution spanning every physical retry and
  joined invocation; a joined call emits a child Transaction Invocation under
  the current attempt and creates no additional root or attempt.

### Private read composition

- **Each Handle owns one Read Scope.** A `Database` and a `Transaction` each
  construct exactly one private Read Scope. Their Typed `find`, `stream`, and
  `read_rows` entries, and the same Handle's Wire `find` and `stream` entries,
  delegate to that scope. A Wire view retains the scope itself rather than bound
  Handle methods. The Read Scope is an implementation boundary, not a public
  extension point.
- **The selected read model enters through execution policy.** The Read Scope
  obtains the operation's selected read model from its private execution
  adapter, inside the read boundary and after re-entry has been refused; the
  `Database` or `Transaction` does not select it before delegating. That
  immutable value carries the cataloged model and, when available, graph
  construction — never the write codec. Standalone execution may select per
  operation; participating execution returns the Transaction's fixed selection.
  The adapter may reuse an unchanged value, but the Read Scope assumes no
  Database-lifetime model. One stream retains one selection through all of its
  pages.
- **Execution variation stays below the verbs.** One concrete Read Scope owns
  preflight, eager execution, stream construction and paging, and result
  publication. Its private execution adapter supplies four explicit
  capabilities: begin a read, run an eager read, open stream activity, and run
  one stream page. The package constructs the scope through standalone and
  participating factories; it exposes neither an inheritance hierarchy nor a
  closed mode union.
- **Call-owned choices remain call-owned.** Typed or Wire result publication is
  selected for each call, after re-entry refusal, and is not configuration
  retained by the Read Scope. `batch_size` remains a `stream` argument and is
  validated at the call in the refusal order already specified above. Deferred
  Feature classification remains package-wide and crosses the existing preflight
  seam. Moving this composition changes neither public refusal order nor the
  rule that a refused participating read force-flushes nothing.

### Execution lifecycle observability

The canonical public module is `parallax.core.execution_lifecycle`; the Snapshot
package does not re-export it. `connect` adds one keyword-only composition seam:

```python
connect(
    adapter: DatabasePort,
    model: DomainModel,
    *,
    lifecycle_provider: ExecutionLifecycleProvider | None = None,
) -> Database

class ExecutionLifecycleProvider(Protocol):
    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None: ...
    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None: ...

class ExecutionLifecycleHandler(Protocol):
    def handle(self, event: ExecutionEvent, /) -> None: ...
```

`RootExecution` is a frozen, slotted value carrying only `id: UUID` and
`kind: RootExecutionKind`; kinds are `READ`, `TRANSACTION_INVOCATION`, and
`SNAPSHOT_STREAM`. Deterministic public preflight runs first. With no installed
Provider the Handle branches before allocating UUIDs, descriptors, events,
publishers, counters, diagnostics, or lifecycle clock reads, and performs no
allocation, clock read, or I/O; a shared immutable inert activity may stand in
for the activity seam. An
installed Provider receives one UUIDv4 descriptor for each accepted root;
returning `None` declines it and performs no later lifecycle work. `open` may be
called concurrently and every accepted root receives a distinct Handler whose
`handle` calls are serial.

An ordinary exception from `open` raises
`ExecutionLifecycleProviderError` before execution work and preserves the
exception as `__cause__`. The Provider's `report_handler_error` method is the
Error Reporter for the same connection, keeping `connect` to one lifecycle
argument. An ordinary Handler exception quarantines only that Handler for the
rest of the root and calls the owning Provider with a detached
`ExecutionLifecycleHandlerError`; execution behavior is unchanged. That error
carries root ID, event sequence, activity ID, qualified handler type, nested
fan-out path, and Failure Diagnostic, but no event, statement, or binds. An
ordinary reporting failure writes one sanitized correlation-only line to
`sys.__stderr__` and is silently dropped if that path is unavailable. A
`BaseException` from handling or reporting deactivates all lifecycle delivery
for the root, aborts and cleans up without further events, and propagates
unchanged; it produces no Handler Error.

Calls through the originating `Database` or `Transaction` from `open`,
`handle`, or `report_handler_error` raise `ExecutionLifecycleReentryError`
before execution state or database work. During opening it becomes the
Provider Error's cause; from a Handler it is an ordinary delivery failure if it
escapes. Unrelated Handles remain usable.

`ExecutionEvent` is a closed union of frozen, slotted concrete classes:
`ReadStarted`/`ReadFinished`, `WriteBatchStarted`/`WriteBatchFinished`,
`DatabaseCallStarted`/`DatabaseCallFinished`,
`TransactionInvocationStarted`/`TransactionInvocationFinished`,
`TransactionAttemptStarted`/`TransactionAttemptFinished`,
`SnapshotStreamStarted`/`SnapshotStreamFinished`, and
`StreamBatchStarted`/`StreamBatchFinished`. `ActivityStarted` and
`ActivityFinished` are union aliases or parent interfaces, not constructible
kind-plus-payload records. Every event carries `execution_id`, one-based
contiguous `sequence`, one-based contiguous `activity_id`, and
`parent_activity_id: int | None`; only the root activity has no parent. One
event object is delivered to every fan-out child.

The concrete payloads and closed outcomes follow `m-execution-lifecycle`.
Database Call Started and Finished borrow the exact deeply immutable
`LoweredStatement`; a Handler must not retain it. Finished carries integer
`duration_ns` measured by `time.perf_counter_ns` around the port call only.
`FailureDiagnostic` is detached, deeply immutable, total to construct, bounded
to 8 KiB of message and 64 KiB of chained stack without locals, and carries
qualified type, optional safely readable string code, and truncation flags.
Database failures add the existing Category and native code without
reclassification. `DirectFailure` and `CausedFailure` make causal attribution
explicit, and a failure with a diagnostic already rendered for its value — its
own attribution's, or the one its parent holds for a higher-numbered child —
reports that same object. A
failure is the exception value, compared by `is`, so one object raised more than
once is one failure with one attribution; an activity holds exactly one
attribution, pairing that value with one direct child reported either by that
child finishing failed with it or by an explicit `enforcing` bracket naming an
already-finished call, and reports `DirectFailure` for a value it does not hold
when it fails.

The database port's transaction callback returns one internal closed value:
`Committed[T]`, `BeginFailed`, `RolledBack[CallbackRaised | CommitFailed]`, or
`RollbackFailed[CallbackRaised | CommitFailed]`. Composition consumes it
immediately. A rollback failure after an ordinary trigger raises public
`TransactionRollbackError`, exposing `triggering_error` and `rollback_error`
and chaining the rollback failure; successful rollback propagates the original
error. A fatal trigger remains primary and attaches rollback failure through
native chaining. Rollback failure never retries and discards the connection.

`FanoutLifecycleProvider` takes an ordered nonempty sequence of Providers,
rejects the same object twice anywhere in the tree nesting forms, opens children
in order, and declines when all children decline. A child open failure aborts
the root and discards already opened child handlers. Delivery is ordered; an
ordinary child failure quarantines only that child and later siblings still
receive the current and subsequent events. Distinct Providers may share a
concurrency-safe backend.

`LoggingLifecycleProvider` accepts an application-configured `logging.Logger`
and a `LifecycleLogDetail` of `SAFE` (default) or `DIAGNOSTIC`. It owns no queue,
listener, sink, overflow policy, flush, or shutdown. Both modes emit detached
structured records without SQL or binds; Safe includes correlation, activity
and outcome types, entity/interface, counters, duration, error type/code,
database category/native code, and truncation flags, while Diagnostic adds the
bounded message and stack. Started and ordinary non-root Finished events use
DEBUG, successful root summaries INFO, retry-eligible rollbacks WARNING, and
failed roots or rollback failures ERROR. The Logger is asked `isEnabledFor` for
an event's exact level before that event is described, and an event it declines
produces no record and no field mapping; counting is unconditional, so a root
summary's totals cover the transitions no record described. A Logger whose
`isEnabledFor` and `log` disagree therefore loses a record `log` would have
kept: the exposure every guarded-logging idiom carries, accepted here rather
than detected around. Applications use standard-library
queue handlers or custom Providers for structlog, Loguru, OpenTelemetry, and
other backends.

`parallax.core.execution_lifecycle.testing.RecordingLifecycleProvider` is the
testing-only complete recorder. It detaches events, groups concurrent roots,
and grows `O(events)` deliberately; it is absent from production re-exports and
must not be used as the production observability path.

The production performance proof uses one `FanoutLifecycleProvider` containing
Safe INFO logging to an application-owned bounded queue, bounded metrics, and
sampled tracing to a bounded exporter. With `N` concurrent roots, `P` active
Providers, and maximum activity depth `D`, Parallax-owned live lifecycle memory
is `O(N * (P + D))`, independent of completed events, retries, stream length,
result cardinality, and materialized graph size; completed roots leave no core
references, sequential roots show no retained-memory slope, and concurrent
growth is linear. Delivery is `O(events * active providers)` and copies neither
statements nor binds.

On the pinned performance runner, the initial Python ratchet is p95 no greater
than 5 microseconds of Parallax-owned dispatch per event for three lightweight
Handlers, plus p50 no greater than 5 percent and p95 no greater than 10 percent
end-to-end overhead against the same workload without a Provider. The first
implementation records the reproducible baseline and may tighten these
provisional ceilings; exporter latency and application queueing are excluded.
These feature tests do not claim the deferred `benchmark` command or general
`m-perf-bench` module.

- **The first-party seam beside the developer surface.** One capability lives on
  the handles without being developer surface, and it has no `Neutral*`
  vocabulary: the public read interfaces are `db.find` / `tx.find` and
  `db.wire.find` / `tx.wire.find`, and nothing else answers a result.
  `db.read_rows(query)` / `tx.read_rows(query)` are the **values lane** — one
  canonical Object Query into `RowsResult`, whose `rows` is the transformed rows
  in result order as `Mapping | InvalidData[Mapping]`, keyed as the read projected
  them. It shares the root canonicalization, the same compilation with the values
  lane selected, and the same recorded Database Call with `find`, but runs no
  relationship level and builds no graph, because the transformed row is already
  the representation; the shared read gate refuses a query naming Include Paths
  before any I/O. A participating `tx.read_rows` force-flushes, renders the
  read-lock suffix its target Entity's Effective Concurrency Strategy calls for,
  and brackets its Read activity exactly as
  `tx.find` does, and records no write observation — the values lane projects scalars
  only, so a Predecessor Row read off it would be incomplete under Relational
  Document Layout. It is not a third public result format: it exists for a
  first-party caller grading flat results, and its element type is the same union
  both public materializers publish.
  There is **no write peer of it**. A caller holding no Entity Class states its
  writes through `tx.wire.*` exactly as a developer does: an existing row is
  addressed and licensed by a value `tx.wire.find` published, a fresh row by the
  payload `tx.wire.insert` opens it with — which answers the frozen node it
  buffered, so a pure Wire caller can revise the row it just opened — and a set
  by a selection plus its assignments. There is no ingress taking an
  already-decoded write instruction, and therefore no way to name an observed
  state as an address: evidence is what a value carries, never an argument.
  `Database(port, model)` is the advanced connection the values lane is reachable
  through, and takes the same Domain Model of either provenance
  `Database.connect(...)` does; a caller holding no Entity Class connects a
  descriptor-backed one. There is no `read_neutral`, `connect_neutral`, `plan_neutral`,
  `compile_neutral`, neutral write on `Database`, or public flush: runtime returns
  and retains no `WritePlan`, and a buffered write executes only when a dependency
  batch or the outer boundary's pre-commit batch requires it.
- **Nesting, ownership, and concurrency preference.** A `db.transact` call while
  a transaction is already active on the current thread **joins** it, but only
  through the exact `Database` object that opened the boundary. The outermost
  demarcation retains a strong reference to that object, and a nested call joins
  only when the invoked handle **is** it; an alias of the same object joins and
  receives the identical Transaction, while any other handle is refused even
  when it carries the same Domain Model, adapter, dialect, clock, or otherwise
  equivalent configuration, because the demarcation owner is scoped state rather
  than a property of any of those. A mismatch raises exported
  `TransactionOwnershipError(RuntimeError)` with sole stable code
  `transaction-owner-mismatch`, before rollback-only state, Principal
  resolution, option comparison, closure execution, Unit of Work mutation, SQL,
  connection acquisition, or any adapter activity, and it retains neither
  handle. It is a `RuntimeError` rather than a `ValueError` because nothing
  about the call's arguments is wrong — the identical call succeeds from the
  owner — which is also what distinguishes it from
  `TransactionOptionConflictError`, a rejected argument value. A non-Parallax
  unit of work active on the thread keeps its own distinct `UnitOfWorkError`.
  Once ownership succeeds, joining is as it always was —
  aligning with Reladomo (ADR 0004): the inner
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
  after the scope ends. The per-transaction `concurrency` option is a
  **Concurrency Preference**, not one strategy imposed uniformly on every
  Entity. `optimistic` is the default: an Entity with an explicit version or a
  Transaction-Time-derived `in_z` key uses lock-free participating reads plus
  its observation-bound gate, while an unversioned Non-Temporal Entity falls
  back to the dialect's shared read lock. `locking` forces that shared-lock,
  ungated strategy for every lockable Entity. One transaction may therefore use
  optimistic concurrency for one Entity and Locking for another.
- **`isolation` is a closed vocabulary, refused here and mapped by the
  adapter.** `db.transact(..., isolation=...)` names one of the three portable
  Isolation Levels — `parallax.core.db_port.IsolationLevel`, a `Literal` of
  `"read_committed"`, `"repeatable_read"`, `"serializable"` — each defined by
  the anomalies it forbids (`m-unit-work`, `m-db-port`) rather than by any
  database's own spelling; omitting it requests nothing and leaves the
  connection at whatever the adapter or its driver already defaults to (READ
  COMMITTED on Postgres). The value reaches `DbPort.transaction` unchanged and
  `PostgresAdapter` maps it to this engine's name for it
  (`parallax.postgres.isolation_spelling`), so what Parallax promises is the
  GUARANTEE rather than a string's arrival, and a `Literal` is what makes the
  promise expressible.

  A value outside the vocabulary raises a plain `ValueError` naming the three,
  raised where a negative `retries` bound is: at the outer call, before any
  transaction is opened or observed, before a lifecycle event, and before this
  call is compared against an active boundary — so a joining call naming an
  invalid level is refused as INVALID rather than as a conflict. The check
  compares rather than tests set membership, so a value of any type is refused
  the one way. An engine's own spelling of a level Parallax does carry
  (`"repeatable read"`) is refused on the same terms as a level it does not
  (`"read uncommitted"`): being spelled for one database is what makes a name
  unportable.

  The level is a property of a boundary at the moment it opens, so it joins on
  the same terms as the other three options — omit to inherit, repeat the
  active value to be accepted, name a different one for
  `TransactionOptionConflictError` before the joined callback runs — and a
  boundary opened with no level refuses a joining call that names one. Every
  physical attempt of one invocation opens at the same requested level, so a
  retried callback never silently runs at a weaker one; a serialization failure
  or deadlock still retries under `m-auto-retry`'s own bound, and no new error
  class or retry policy comes with the vocabulary. There is no handle-level,
  connection-level, or environment default: the setting is transaction-scoped,
  because a connection setting is only a default for later transactions and a
  long read is exactly the case wanting a different level from the rest of an
  application. `tx.stream` therefore inherits its transaction's level and
  `db.stream` carries no isolation option at all — a caller wanting one
  database snapshot across a whole delivery streams inside `db.transact`.

  An installed lifecycle Provider observes the level on the outer invocation's
  Started transition and nowhere else (`m-execution-lifecycle`): the requested
  value, or nothing at all where the call named none, because the default an
  omitting call keeps is the adapter's own and Parallax does not infer it. A
  joined invocation reports none, and neither does a Transaction Attempt — the
  level belongs to the invocation that requested it, and every attempt opens at
  that same one.
- **Buffering, flush, and read-your-own-writes.** Writes buffer in the unit of
  work and flush at commit, combined and batched per `m-batch-write` (multi-row
  INSERT collapse, per-key UPDATE batching, IN-list DELETE collapse) and
  ordered to respect foreign keys (parents inserted before children, deleted
  after). A read that depends on a buffered write forces a flush inside the
  still-open atomic scope first (read-your-own-writes); aborts discard
  buffered, force-flushed, and cached effects alike. No public explicit
  `flush()` control is offered in v1.
- **The attempt owns one lazy Transaction Instant.** Each outermost attempt holds
  one uncaptured instant, and the Planning Request carries that holder rather
  than a captured literal, so the **Clock Strategy is consulted only when a
  surviving write actually needs a Transaction-Time boundary** (ADR 0010). An empty
  transaction, a read-only one, a buffer that same-transaction coalescing cancels
  to nothing, an update whose effective change set is empty, and a flush whose
  every surviving write is non-temporal all complete with **zero** clock reads.
  The first temporal write in an attempt captures one instant; every later
  temporal write in that attempt — across a forced read-your-own-writes flush and
  the commit flush alike — binds the same value, so `in_z` and `out_z` stay
  coherent within the transaction. A retry is a new attempt with its own
  uncaptured instant and reads the clock again only if it independently reaches
  temporal work.
- **Write finalization settles a step before lowering.** A buffered write that
  survives planning is settled into one **Planned Write** — the closed
  `m-unit-work` algebra — before any SQL exists, and lowering then answers a
  purely physical question about it: which Columns participate, in which order,
  quoted for which dialect. A settled step carries its **Write Target** (the
  primary keys it addresses, a readless predicate, or the milestone slot a close
  addresses), its **concurrency decision** (an explicit version gate, an explicit
  temporal gate, an explicit ungated decision, or no version at all), its
  assignments including the framework-derived version advance, and its
  **Affected Rows Policy** — the expected effect plus the neutral outcome class a
  shortfall names. Whether a gate applies is decided while the step is being
  settled from the transaction's Concurrency Preference and the target Entity's
  Optimistic Lock Facet, so no lowering reads either input; a missing
  required observation is likewise a planning error raised there, never a null
  value that reaches SQL.
- **Temporal topology is settled, not lowered.** A temporal mutation expands
  during finalization into one **Planned Close** followed immediately by its
  zero-to-three **Planned Insert** successors, in the facet's canonical order —
  inactivation, then head, middle, tail where each exists — with no unrelated
  step interleaved. `parallax.core.txtime_write` and `parallax.core.bitemp_write`
  answer only the neutral topology of one authored mutation (its close cause, the
  axis whose observed start an optimistic close gates on, and each successor's
  interval and represented state); finalization resolves that description against
  the observed predecessor, the authored row, and the attempt's Transaction
  Instant. Expansion is legal there precisely because it needs no dialect, and it
  is why lowering never reads a milestone plan, an observation, or an instant.
- **Observations are a closed algebra with structural absence.** A read records
  either the optimistic-lock **version** a versioned non-temporal row was read
  at, or the whole **predecessor milestone** a temporal row was read as — its
  complete persisted state, and nothing about the read that reached it. Inserts
  and unversioned non-temporal writes record nothing at all rather than an empty
  observation, so "a version and a predecessor" and "neither" are both
  unrepresentable. Absence extends to the buffer: only a keyed write with an
  observation buffers paired with it, and the two carriers a write with none may
  take — `ObjectClaimedWrite`, and the bare instruction — hold no observation
  field to be null, so no no-observation value exists at any point,
  and `PlanningRequest` carries no observation map for the planner to search.
- **An observation is addressed by the exact state it observed.** The address is
  the closed `ObservedStateKey` union — `VersionedStateKey(object, version)` for
  a versioned non-temporal row, and `TemporalStateKey(object, milestone)` for a
  temporal one, whose milestone is that row's own `Edge`, the same value
  `edge_of(node)` answers for. An `ObjectKey` stays state-independent and
  addresses the object across its states; inserts and unversioned non-temporal
  writes observe no state and have no `ObservedStateKey` at all — which is not
  the same as claiming nothing, per the claim-scope derivation below. Reading one key
  twice at coordinates that resolve to **different** states therefore retains
  evidence about each, and a later write settles against the state the value it
  was handed came from; reading one state twice answers one retained
  observation. That second half is the deliberate **converse** of `pin_of`'s
  rule that distinct coordinates denote distinct pinned views (§3): a view is a
  way of looking, an observation is what was seen. The coordinate is derived
  from the observation's own evidence, so no retaining site can address evidence
  by a state other than the one it is recording, and the write side reads its
  coordinate off the value through the same derivation.
- **Evidence belongs to the source value; the transaction holds a weak index.**
  A graph-form read attaches a private Source Hint to every Entity node it
  publishes — the concrete Entity, the object the row denotes, the participation
  its read licensed, and the retained observation for the state it saw. A Typed
  node reaches its hint through the same private lifecycle state `edge_of` and
  `pin_of` read, and a pickle reaching Entity's own entry point is refused at
  that door rather than stripped (§3); a frozen `WireEntity` node carries it on
  a slot, never as a mapping entry, so `dict(value)`, JSON, and pickle produce
  ordinary domain data with no keyed-source status. Only an Entity node can
  carry one: a nested Value Object mapping has no slot. `Entity.edit(...)`
  preserves lifecycle state and therefore transfers the claim to the derived
  value; a Wire copy answers the same object and therefore the same claim. A
  standalone `db.find` / `db.wire.find` produces sources exactly as a
  participating read does and differs only in stamping no participation. A
  transaction keeps a `WeakValueDictionary` of the states its own reads saw
  plus the participation token an effective-Locking write tests against, so
  eligibility is strong reachability: when every source value and every
  buffered write for a state is released, its evidence is gone, on the
  runtime's ordinary collection schedule and with no claim counting, stack
  inspection, or reference-count semantics.
- **A successful flush consumes the evidence its writes used.** A retained
  observation carries one mutable fact — whether it has been spent — which lives
  on the shared object rather than in a transaction-side set, because a later
  transaction handed the same still-live source must be refused. A flush spends
  the claims its **surviving** writes carried, once the executor returns.
  Buffered work finalization retires — folded into a pending insert, cancelled
  against one, or eliminated as a known no-op — spends none, and that holds
  per write rather than per batch: a retired write's claim stays eligible even
  when a sibling write of the same flush executed. One claim that several
  surviving writes of a flush carried is spent **once**, because what
  consumption records is a fact about the observed state rather than about a
  statement. An aborted flush spends none and needs no restoration. A keyed verb refuses a source whose evidence the
  target Entity's
  Effective Concurrency Strategy cannot use with `WriteEvidenceError`
  (`LookupError`), carrying its `code` and the visible `object_key` the write
  addressed and never the Source Hint or the Observed State Key behind it. The
  codes are `write-evidence-unavailable` — the Optimistic strategy found no
  retained observation, or the Locking strategy found no participation of this
  transaction — `write-evidence-consumed`, and
  `write-evidence-already-claimed`. Every one is raised synchronously
  at the verb, before buffering and before any database access; a conflict the
  database discovers later keeps its own flush-time classification.
- **What a keyed write claims is derived from the write kind, in three arms.**
  `opt_lock.settled_evidence(key, mutation, ...)` is the one derivation — total
  over the target Entity's own `OptimisticKey` and the verb's mutation, the same
  shape `effective_strategy(preference, key)` takes: an `insert` claims nothing,
  a versioned or temporal existing-row write claims the `ObservedStateKey` its
  source retained, and an unversioned non-temporal existing-row write claims its
  `ObjectKey`, whose shared row lock is the evidence its `locking` arm just
  required. Its `key` is the three variants themselves and never their absence:
  a write's target is resolved against the model before the derivation runs, and
  `opt_lock.optimistic_key` refuses an Identity the Optimistic Lock Facet does
  not name rather than reading it as `Unversioned`, so no arm is reached because
  something was missing — an insert observes no state either. The three arms
  answer for a write addressing ONE object; a keyed instruction naming several
  rows has no single `ObjectKey` and no single observed state, so the derivation
  answers nothing for it and — its caller having supplied nothing either — it
  claims nothing and buffers bare. Evidence supplied WITH such an instruction is
  refused by the single-row carrier instead, before the write takes any claim,
  because one observation is evidence about one row. No runtime ingress builds a
  plural keyed instruction — every verb, Typed and Wire, addresses one row — so
  that shape is reachable only by a caller holding an instruction rather than the
  value it came from, and such a caller reads the whole ingress rule, supplied
  evidence used as given and the derivation otherwise, from one
  `opt_lock.instruction_evidence`. The write travels to planning as the
  carrier its answer implies: `ObservedKeyedWrite` with the retained observation,
  `ObjectClaimedWrite` with the members its author restored, or the bare
  instruction.
- **Several buffered writes may claim one scope, and one rule says what the
  second becomes.** Each carries a Write Intent — an assignment or
  a destruction, over the authored Valid-Time region — and the intent a buffer
  already holds at that exact scope decides: assignments over one region merge
  in authored order with the later value winning a repeated member, a destruction
  supersedes the assignments buffered before it, an identical destruction
  deduplicates, and a different region, an assignment after a destruction, or a
  state a predicate write's Materialized Write Group already selected are
  `write-evidence-already-claimed`. The verb-time refusal and the flush-time
  merge read the same rule, so they cannot disagree. Effective-change elimination
  runs after the merge and compares each winning assignment with its source's
  own original — for a Typed write, the Change Record's — so a member an author
  touched and then restored cancels an assignment buffered earlier at the same
  scope, and a write left with nothing but its key is eliminated, issues no
  statement, and consumes no observation.
- **An observation is keyed by the row's own resolved Entity Identity.** A read
  observes each row under the exact Entity that row's own compiled read
  resolved it to — a per-row fact under table-per-hierarchy — never under the
  position the query targeted. Root and included levels alike follow that one
  rule, so a keyed write on any node a participating read materialized is
  licensed by that read's observation: an included child, a polymorphic level's
  concrete, and an abstract-target root's concrete are each reachable by the
  write that names them. The key carries the structured Entity Identity rather
  than a spelling of it, so no producer stringifies one and two entities
  sharing a bare name across namespaces cannot resolve one another's
  observations. A serialized write instruction keeps its wire `str` entity,
  which planning resolves to an identity before keying.
- **A read observation's carrier stays physical.** The carrier an observation
  records is keyed by **physical column**, and that is settled rather than
  interim. A projection row structurally cannot carry the raw Structured
  Column, which a temporal observation retains so a successor is patched from
  what the row held rather than rebuilt from the members the model declares
  (ADR 0042). Collection happens at the read executor while the row is live,
  deliberately upstream of the graph, which is the only point at which the row
  and the projection it converts into are both in hand. And physical keying is the
  carrier's purpose rather than its convenience: it is a faithful record of a
  persisted row for a later SQL comparison, not a projection of the model.
  Retaining a second, logical carrier beside it would be strictly worse than
  the single one that exists, and the identity-to-Column translation already
  goes through the Storage Layout facet.
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
  follow the same authentic-evidence rule as versioned writes (below). The
  values a bitemporal rectangle split carries forward, the close's own **address**,
  and — under the Optimistic strategy only — the observed `tx_start` (`in_z`)
  its gate binds all come from the source's privately retained observation,
  never from visible caller-authored fields or an implicit write-path read.
  Under Locking that source must have participated in this transaction; under
  Optimistic it may come from a standalone Parallax read. The **close target is
  mode-independent** (`m-bitemp-write`, ADR 0046): the lowered `UPDATE` is keyed on
  the primary key plus one exclusive upper bound per declared as-of axis — the
  observed rectangle's own `thru_z` for a Bitemporal Entity, then the invariant
  `out_z = infinity` — under both Effective Concurrency Strategies, and only the
  trailing `and in_z = ?` gate varies. A key plus `out_z = infinity` alone would
  be ambiguous on a Bitemporal Entity, whose one key may have several disjoint
  Valid-Time rectangles current on Transaction Time.
- **The Entity Row Codec derives every row.** One model-bound `EntityRowCodec`,
  reached through `row_codec_of(model)` (§2), is what turns an Entity value into
  a canonical row. The framework asks it for a row and learns nothing about
  Pydantic, private provenance storage, physical column names, temporal
  planning, or Audit Provenance:

  ```text
  EntityRowCodec                    # model-bound; per-Entity facts memoized
                                    #   by EntityIdentity
    full_row(value)     -> dict[str, object]
    identity_row(value) -> dict[str, object]
    edited_row(value)   -> dict[str, object] | None

  row_codec_of(model: DomainModel) -> EntityRowCodec

  EntityRowError(RuntimeError)      # exported from parallax.core.entity
    entity-row-not-an-entity          entity-row-malformed-provenance
    entity-row-target-not-in-model
    entity-row-member-missing
  ```

  **Input validation resolves; it does not own.** The codec resolves the Entity
  Identity the value's class declares and fails with
  `entity-row-target-not-in-model` when its model declares no such Entity — the
  same resolution-not-ownership distinction `QueryTargetError` draws (§2). The
  bidirectional Entity Identity/Entity Class index is never consulted to decide
  whether a value belongs; it exists for materialization and is never an
  authorization structure. A value from another model whose identity this model
  also declares therefore **resolves**, because the emitted row is a function of
  the resolved identity's declared members alone. Resolving is not the whole
  call: whether such a value yields a row is the member rule's business below,
  and that rule's answer varies by operation.

  **The candidate set is the model's; the selection is the operation's.**
  Members come from the model's family-effective metadata, which also supplies
  the canonical keys, and each operation selects from those candidates by its
  own rule: `full_row` selects what `model_fields_set` reports as populated,
  `identity_row` selects the primary key, and `edited_row` selects the primary
  key plus the members the Change Record names. Neither side alone would do:
  metadata cannot know what the caller populated, and the class cannot be the
  authority on which members the model declares. A member an operation selects
  but **cannot emit** raises `entity-row-member-missing` rather than being
  dropped, and that one code names the one harm from either side of the pairing:
  the resolved identity declares no such member, so no canonical key names it,
  or the value's class carries no attribute for one it does declare. The second
  side reaches only the cross-model value resolution admits, whose own
  declaration of the same Entity is free to key it by other members — an
  `identity_row` that dropped those would hand a keyed write an unkeyed row.
  Silently discarding a value the caller authored, and emitting a row short of
  what the selection claims, both signal nothing.
  **Refusal follows selection**, so the rule reaches an
  operation's own selection and nothing else — neither the populated set at
  large nor the narrower set the finished row carries. The harm it names is
  losing a member the operation's selection claims, and an operation that drops
  members by contract — `identity_row` every non-key member, `edited_row` every
  member its Change Record does not name — loses nothing by dropping one more.
  So a populated undeclared member an edit never touched is outside
  `edited_row`'s selection and outside its judgement, while `full_row` on that
  same value still raises. Effectiveness is weighed after the selection is
  judged and never narrows it: an undeclared recorded name still raises when the
  edit that touched it restored its original value, though the row would have
  carried nothing for it. Judging the populated set uniformly instead would
  refuse a keyed write over a member no keyed write emits, and it would refuse
  it on exactly the cross-model value the resolution-not-ownership rule above
  admits past resolution, whose class is free to declare members this model does
  not.

  **Rows are fresh, plain, caller-owned `dict[str, object]`**, keyed by
  canonical Attribute names and ordered by an explicit category pass over the
  family-effective members — Attributes in declaration order, base-first, then
  top-level Value Objects in theirs — the same category-then-declaration-order
  shape every other ordered projection of a model already takes
  (`m-storage-layout`'s Column claim order, `m-descriptor`'s derived
  primary-key index). A row's key order is therefore a function of the model
  alone, never of caller keyword order and never of the value's class: where a
  declaration interleaves an Attribute and a Value Object, that interleaving is
  recoverable only from the class, while the accepted Metamodel a row is derived
  from keeps the two as separate declaration-ordered sequences. Physical names
  never appear: the canonical-member-to-default-column rule stays authoritative,
  so `taxID` is emitted as `taxID` and its column `tax_i_d` is
  `m-storage-layout`'s business. All three operations carry
  **serialized** values, so a caller holding several rows of one value compares
  like with like. Uniformity moves no emitted bind: a primary key is
  structurally an Attribute of a scalar type, which serialization passes through
  by identity, so `identity_row`'s values are the ones the instance holds
  whatever the rule says.

  `edited_row` returns the identity row plus the **effective** caller-authored
  changes, those whose current value differs from the recorded original. It
  preserves first-touched originals across a chain and answers `None` when the
  value carries no effective change. `None` is one proposition — *this value
  names no change to write* — so a net-zero edit and a value no edit ever
  touched are the same answer, and "nothing to write" has exactly one
  representation whatever the value's history.

  A **Change Record** is a mapping from each member the edit chain touched to
  the value that member held when it was first touched, stored in one private
  first-party slot that only `edit(...)` ever writes. It is first-party state,
  not a surface a class answers for, so no authored `__dict__`, `__getattr__`,
  `__getattribute__`, or descriptor bound at the slot's own name drops an edit's
  row or earns one an edit never authored. An absent slot and an empty record
  name the same empty selection, because both say the chain touched nothing; a
  value whose slot holds something that is **not** a Change Record raises
  `entity-row-malformed-provenance` instead, and private state the framework
  never wrote is such a thing however well shaped it is, because what makes a
  mapping a Change Record is that `edit(...)` made it. That refusal reports
  corruption of private first-party state rather than classifying anything a
  developer authored, which is why it survives while the absent-record refusal
  does not: collapsing an unreadable carrier into "nothing to write" would name
  the wrong defect and leave the corruption unreported. Which verbs accept a plain,
  never-edited value is not the codec's question at all — the write verb decides
  it from the value's provenance, before deriving any row (§5). A recorded name
  the resolved identity does not declare is not a provenance defect either — it
  is the same undeclared-member case `full_row` reports, so it raises
  `entity-row-member-missing`.

  **Refusals are ordered, so one input has one code.** Every operation resolves
  the value's Entity Identity first — `entity-row-not-an-entity`, then
  `entity-row-target-not-in-model` — and judges members last. `edited_row`
  settles the carrier in between, before the Change Record is read for names: a
  carrier no edit wrote raises `entity-row-malformed-provenance` whatever else
  that value populates, so `entity-row-member-missing` from `edited_row` always
  reports a name an accepted record supplied. An absent record narrows
  nothing: the primary-key half of the selection is judged exactly as it is for
  a net-zero chain, so a value whose class supplies no attribute for a declared
  key member is refused rather than answered `None`. `full_row` and
  `identity_row` read no Change Record at all, so the same plain value whose
  populated member the model does not declare raises
  `entity-row-member-missing` from `full_row` and emits a row from
  `identity_row`, whose selection is the declared primary key.

  Provenance comparison is stated rather than implied: an occurrence compares as
  a **whole** at either cardinality, presence preserved on both sides, because
  assigning one replaces its subtree (`m-unit-work` *Comparing an assigned member
  with its persisted value*). A declared member the authored value omits is a
  member the write removes, so it makes the edit effective rather than passing
  as un-authored; an explicit null and an omitted key stay distinct on both
  sides, the same explicit-versus-defaulted distinction canonical document
  serialization draws (§3). A nested Many is the one member an omission does not
  remove, and it is not preserved as one: it has no absent state, so both sides
  read it as the `()` / `[]` the write stores either way, and an occurrence
  authored short of it is a no-op against a row already holding that zero. The
  Wire keyed verb applies that identical rule to its own effective-change set,
  and it weighs it against the same observed value: this comparison reads the
  hydrated original's populated set and the Wire verb reads the node its read
  published, which is that same materialization's own document (§4) — one
  document under two names. One authored value therefore earns one answer from
  both peer interfaces, including where the answer turns on presence: against a
  row storing an occurrence short of a declared member, authoring that member's
  explicit null is an effective change through either, and the two emit the same
  DML, while authoring the occurrence short of a nested Many is DML through
  neither.

  **The codec is an authoring codec, never a provenance decorator.** It emits
  only caller-authored identity and domain values in canonical Attribute-keyed
  form, and it never computes, stamps, preserves as an assignment, or accepts a
  caller-authored framework-owned value (§3). It depends on no Principal,
  Subject Identity, Session, Clock Strategy, Transaction Instant, Audit
  Metadata, AuditFacet, audit enablement policy, temporal topology planning,
  Write Planner, SQL, or Storage Layout, and §7's generated import contracts
  enforce that rather than leaving it to review. Future Audit Provenance is
  applied to typed Planned Writes inside the Write Planner (ADR 0037) and is
  never a codec extension point.

  Codec misuse is first-party misuse rather than rejected developer input, so
  `EntityRowError` sits in the `RuntimeError` tier `GraphConstructionError`
  already reasons about, and `entity-row-not-an-entity` refuses a value that is
  no Entity at all. The developer-facing steering for handing a persistence verb
  a value with no Change Record belongs to that verb, which knows what the
  developer called; the codec knows only that it received a value its operation
  does not accept.
- **Keyed writes require authentic evidence; set-based writes materialize.**
  Existing-object Typed and Wire keyed writes accept only a source produced by a
  Parallax read; neither an ordinary mapping nor a caller-authored version is
  evidence. The framework never issues an implicit resolving `SELECT` on behalf
  of a keyed verb. After ordinary no-op and assignment legality rules, the target
  Entity's Effective Concurrency Strategy decides what evidence that authentic
  source must supply. Under **Locking**, the source must have been read by this
  transaction through `tx.find` or `tx.wire.find`, proving that the current
  attempt acquired and still holds the shared row lock. A value from `db.find` or
  `db.wire.find` cannot prove that participation. Under **Optimistic**, an
  authentic versioned or temporal source may instead carry the version or exact
  milestone observed by a standalone read; the emitted database gate detects an
  intervening writer. An unversioned Non-Temporal Entity has no gate and therefore
  uses the Locking evidence rule even when the Unit Work's preference is
  `optimistic`. The shared row lock is the whole of such a row's evidence, so a
  keyed verb needs it as surely as a versioned verb needs its version:
  `tx.delete(OrderItem(id=200, ...))` over a constructed instance proves nothing
  about the row it addresses and is refused. Unconditional intent has its own
  spelling — `tx.delete_where(OrderItem.where(OrderItem.id == 200))` says outright
  that the caller means to remove whatever matches, rather than arriving there by
  building a throwaway value.

  A keyed assignment payload that tries to change the Entity's version Attribute
  raises `CallerAuthoredVersionError` before evidence resolution. An authentic
  Typed or Wire read source naturally exposes its observed version as ordinary
  Entity data, but that property is read-only for write authoring and its visible
  value is never trusted as evidence; Parallax uses the source's privately retained
  observation. The version is framework-owned end to end (ADR 0013). A write whose source came
  from a finite historical Transaction-Time milestone is likewise refused at the
  verb as `TransactionTimePinReadOnlyError(transaction-time-pin-read-only)` under
  either effective strategy. A Locking temporal close is licensed by the
  current-transaction read that locked the exact milestone it closes; an
  Optimistic close may bind the authentic standalone source's observed `in_z`.

  A versioned `UPDATE` advances the framework-computed version under either
  strategy, and a `DELETE` writes no version. The target Entity's effective
  Optimistic strategy appends the observed-version or `in_z` gate uniformly for
  update, delete, and temporal close; Locking emits no gate for any of them. A
  gated zero-row shortfall is `OptimisticLockConflictError`, surfaced always and
  retriable only through `retry_optimistic_conflicts=True`. An ungated,
  observation-requiring shortfall is the never-retriable stale-write outcome.

  **Set-based** writes — selecting rows by predicate rather than key — are the
  path where the framework itself materializes observations: one participating
  read resolves the predicate to rows, recording each matched row's observed
  version or milestone and taking shared locks exactly when that Entity's
  Effective Concurrency Strategy is Locking, then one keyed per-object statement
  per written row — for the
  assignment-bearing verbs (`update_where` / `update_until_where`), each
  resolved row that survives the per-row no-op elimination below; for the
  delete and terminate verbs, every resolved row (`1 + N` round trips, a
  mid-batch zero-row gate aborting like any conflict). An Object Query becomes
  a write target only in its **mutation-compatible** form — one carrying
  nothing but its target and its predicate (the `where(...)` arguments);
  `order_by`, `limit`, `include`, `as_of`, `history` / `as_of_range`, and
  `narrow` are all rejected on any write target, each naming the clauses it
  carries, because every one of them shapes a **result** and a set-based write
  has none to shape. This is the single definition; the set-based verbs below
  reference it rather than restating fragments. Version values are
  framework-owned end to end: the version field on a node, an edited copy, or
  caller input never feeds the gate or advance. An edited authentic versioned or
  temporal source fetched outside the writing transaction may be updated directly
  only when its Entity's Effective Concurrency Strategy is Optimistic. The same
  source under Locking, and every unversioned Non-Temporal source, must be reread
  inside the transaction so the required shared lock is actually held.
- **A finite Transaction-Time pin is read-only under both strategies.** Every keyed
  verb — `insert`, `update`, `delete`, `terminate`, and the `*_until` trio —
  refuses a source value whose view is pinned at a finite Transaction-Time
  instant, raising exported
  `TransactionTimePinReadOnlyError(transaction-time-pin-read-only)` at the call,
  before Unit of Work buffering, SQL, or adapter access, and emitting no DML.
  The refusal is **mode-independent**: it is this target's instance of
  `m-txtime-write`'s invariant that Parallax never rewrites the Transaction-Time
  past *across the required parity surface* (`m-identity-map`), and that
  invariant is a property of the write surface rather than of a concurrency
  decision. The Optimistic strategy is emphatically **not** a way past it: the same DML
  under optimistic concurrency addresses a superseded milestone, whose gate
  matches zero rows, so it raises `OptimisticLockConflictError` instead of
  silently rewriting history. An **Edited Copy** carries its source's `Pin`
  (§3), so `tx.update(node.edit(...))` over such a view is refused exactly as
  the node itself is — deriving a copy is not a route past the rule either. A
  **finite Valid-Time** pin stays writable: mutating one is the retroactive
  correction that lowers to the `m-bitemp-write` rectangle split. The
  MAY-tier administrative mutations that would widen the invariant
  (`insertForRecovery`, `purge`, `inactivateForArchiving`) sit outside the
  required parity surface and are not offered.
- **A keyed write verb accepts a value by its provenance.** Which verbs accept
  a given value is decided by which framework-managed source, if any, produced
  it from a read (`m-unit-work` *Write value provenance*), never by whether an
  author has since changed it. The three answers partition the values a verb
  can be handed, so a refused value carries exactly one code of exported
  `KEYED_WRITE_VALUE_CODES` on exported `KeyedWriteValueError` — a `ValueError`
  for the reason `TransactionTimePinReadOnlyError` is one, since both refuse a
  neutral application-lifecycle argument the caller supplied. Both names are
  reached from `parallax.snapshot` and from `parallax.snapshot.handle`: a
  developer catches the class on the ordinary `connect` / `transact` path, and
  names the codes from the module they caught it in. `update` / `update_until`
  handed a value **no** read of this store produced raise
  `write-value-not-stored`, whose message names `tx.insert(...)`; `insert` /
  `insert_until` handed a value this store's own read produced raise
  `write-value-already-stored`, whose message names `tx.update(...)`; and both
  families refuse a value **another** framework-managed source produced with
  `write-value-foreign-lifecycle`. The classifier's axis is which managed
  **lifecycle** attached the value's state, never which `Database` issued the
  read: every `Database` over one store shares this one lifecycle, so a value a
  second handle read is this source's value, and a non-transactional
  `db.find(...)` produces one exactly as `tx.find(...)` does (ADR 0010). What such
  a value may then be written into is the write-evidence rule's answer rather
  than provenance's: an effective Locking strategy requires this transaction's
  participating read, while an effective Optimistic strategy may accept the
  authentic standalone source's retained version or milestone. On the **update**
  side the two families now overlap — a value no managed read produced, and a
  value another source produced, both carry no usable evidence either — and
  provenance keeps precedence because it is the more specific diagnosis: it names
  the verb that does accept the value rather than reporting only that evidence
  was missing. The **insert** side does not overlap at all: an insert observes no
  state, so `write-value-already-stored` is the only refusal a stored value earns
  there. The
  refusal is decided in the shared keyed-verb preamble, **before** any row is
  derived, so a refused value reaches no codec, no buffer, no plan, and no
  adapter — it is never a translation of a lower-level failure, and the refusal
  a caller observes carries no codec failure as its cause. `delete`,
  `terminate`, and `terminate_until` derive an identity row alone and take no
  position on provenance. **An unchanged stored value is no refusal at all**: a
  node this store's read returned that no edit touched carries the empty
  effective change set, so `tx.update` on it buffers nothing, issues no
  statement, and raises nothing — exactly as an edit whose net change is empty
  does. Writing every value a find returned and editing only some of them is
  correct code, which is the point of tracking changes on the author's behalf.
  **A value this transaction already buffered an insert for is exempt** from
  `write-value-not-stored`: a row this unit of work inserted is a row it stores,
  so `tx.update` of that object is accepted and the pair coalesces into the
  single final-value write the flush emits (`m-unit-work` *Insert-then-update
  coalesces in place*) — the same read-your-own-writes provenance the bullet
  below grants a keyed temporal close. The exemption is keyed by the OBJECT,
  so a value naming a primary key this transaction never inserted is refused
  exactly as any other value no read produced is. Which object a value names is
  read off its own primary-key members rather than derived through the Entity Row
  Codec, because the refusal this exemption lifts is decided before any row
  exists: a cross-model value whose class keys the same Entity by other members
  names no object at all, and it therefore reaches `write-value-not-stored`
  rather than the `entity-row-member-missing` an identity row would have raised
  on its behalf.
- **A keyed temporal close requires a value that names a milestone.** The
  observation a temporal `update`/`terminate`/`*_until` settles against is
  resolved at the verb from the **value being written** — its own `Edge` —
  rather than from the primary key it carries. A fresh instance and an edited
  copy of one name no milestone, so no observation can match and the verb raises
  its write-evidence error before any DML. A source returned by `tx.find` names
  the milestone and, under effective Locking, proves the lock is held. An
  authentic source returned by `db.find` also names the milestone and may be
  closed directly under effective Optimistic because its retained `in_z`
  supplies the database gate; it is insufficient under Locking. Thus
  `tx.terminate(Position(id=1, ...))` is unsupported, while closing an authentic
  current Typed or Wire read source follows the Entity's effective strategy. The
  same-transaction exemption is unaffected — an inserted instance names no
  milestone either, so the insert and a close derived from it resolve to one
  slot and the pair still coalesces.
- **Set-based write verbs.** Every mutation verb that targets existing rows
  has a predicate-selected `_where` flavor, so the keyed and set-based
  surfaces mirror each other completely (`insert` alone has no set-based
  flavor — there is no matching set to select):

  ```python
  tx.update_where(query, Account.balance.set(Decimal("0.00")))  # non-temporal
  tx.delete_where(query)  # non-temporal
  tx.terminate_where(query)  # Transaction-Time-Only
  tx.update_where(query, Position.px.set(x), valid_from=v)  # Bitemporal plain
  tx.terminate_where(query, valid_from=v)
  tx.update_until_where(query, Position.px.set(x), valid_from=v, until=u)
  tx.terminate_until_where(query, valid_from=v, until=u)
  ```

  Assignments belong to the **assignment-bearing** verbs alone —
  `update_where` and `update_until_where`; `delete_where`, `terminate_where`,
  and `terminate_until_where` take no assignments, and passing any raises at
  build — a delete or terminate names nothing to assign. Assignments are the
  typed `.set(value)` spelling on Attribute Expressions. Each `.set(...)`
  call has already applied §2's Assignment-construction contract before the
  mutation call receives it; the mutation method never supplies the first
  assignability, declared-type, or nullability check. Three list-level rules
  remain at the assignment-bearing verb: the assignment list must be non-empty
  (zero assignments raises),
  each field may be assigned at most once (a duplicate raises), and every
  assigned attribute or value-object member must be declared by the exact
  target entity — set-based writes already reject inheritance-family targets
  (below), so ancestry resolution never arises. The target Object Query must be
  **mutation-compatible** (the single definition above), and one that is not
  raises `QueryDefinitionError(query-not-mutation-compatible)` before Unit of
  Work buffering, SQL, or adapter access;
  resolution happens inside the transaction and participates according to the
  target Entity's Effective Concurrency Strategy (shared-locked under Locking,
  lock-free under Optimistic). Lowering
  follows the observation rule above, with **per-path no-op semantics**.
  Versioned and temporal targets **materialize** — the resolving read records
  per-row observations, then one keyed per-row statement (gated under
  Optimistic), `1 + N` round trips where `N` counts **written** rows. Which rows
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
  shape no golden pins. Assigning a document-resident `many` on this route raises
  `WriteRejectedError` with rule
  `predicate-write-readless-document-many-unsupported` before buffering or I/O.
  Scalar and `one` assignments remain one-statement readless writes; the intended
  later widening is to materialize only the refused shape. The remaining readless
  lowering is pinned so nothing is
  left to invent: `update_where` emits exactly one
  `update <table> set <col> = ?, … where <predicate>` whose `set` columns
  filter the target's Entity Layout slots in table order — the same
  `m-storage-layout` sequence canonical row-write lowering and fixture loading
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
  `update_where` is covered under both strategies (`m-opt-lock-003` / `-004`) and its
  mixed equal/changed-row elimination in `m-opt-lock-014`; versioned
  `delete_where` is predicate-shaped in `m-opt-lock-015`; readless
  non-versioned `delete_where` / `update_where` (including Entity Layout
  order) are `m-batch-write-005` / `-006`; audit-only `terminate_where` is
  `m-txtime-write-007`; and the bitemporal plain update/terminate plus both
  bounded forms are `m-bitemp-write-010`–`-013`. The nine newly authored cases
  (`m-opt-lock-014` / `-015`, `m-batch-write-005` / `-006`,
  `m-txtime-write-007`, and `m-bitemp-write-010`–`-013`) are deliberately
  `slice-snapshot-1` only: they are the snapshot claim's executable oracle,
  not a managed API partition expansion. The upgraded legacy
  `m-opt-lock-003` / `-004` retain their existing `slice-managed-1` tags. The API still has
  broader surface area than any finite corpus sample — arbitrary valid bare
  predicates, multiple assignable fields, and every valid temporal bound are
  validated and documented by the implementation/API suite — but no covered
  mutation flavor is a language-local semantic extension.
- **Affected-row enforcement is target-driven, and an excess is always
  non-retriable.** Every non-insert step's execution result is checked
  against its Write Cardinality — one row per key for a Key Target (one
  **aggregate** expectation for a collapsed multi-key statement, `m-batch-write-008`), one
  row for a Milestone Target — and a shortfall raises the classification the
  concurrency decision already fixed while the step was settled, never the
  verb: the never-retriable `StaleWriteError` for the ungated
  observation-requiring shortfall described above; `OptimisticLockConflictError`
  for a gated shortfall, retriable only via `retry_optimistic_conflicts=True`;
  and the never-retriable `MissingTargetError` for an **unversioned** keyed
  `update`/`delete` whose row does not exist — behavior a prior implementation
  committed as a silent zero-row no-op (`m-unit-work-013` / `-014`). A result
  reporting **more** rows than its target's cardinality permits — an accepted
  identity, storage, or lowering invariant broken, never a concurrency outcome
  — raises the never-retriable `CardinalityCorruptionError` under either strategy,
  for a keyed write or a temporal close alike. No compatibility case drives it:
  a temporal close addresses its Milestone Target by what is now the physical
  primary key, so no corpus fixture can stage state a correctly addressed close
  matches twice, and the class is reachable only from corruption a writer
  outside Parallax introduced. The four
  classes — `MissingTargetError`, `StaleWriteError`,
  `OptimisticLockConflictError`, `CardinalityCorruptionError` — are the public
  Write Effect Error family `parallax.core.unit_work` owns; each carries only
  the Entity Identity, the Write Target (retained by reference), and the
  expected and actual counts — no SQL, statement index, or driver exception.
- **The Wire write interface is `tx.wire`, and it shares one pipeline with the
  Typed verbs.** The same view that answers `tx.wire.find` carries the complete
  keyed and predicate write families. There is no `tx.write(instruction)`, no
  flat `wire_*` method, no overload of a Typed verb with a dictionary, and no
  observation address in any signature.

  ```python
  tx.wire.insert(entity_name, data, valid_from=...)  # valid_from: Bitemporal only
  tx.wire.insert_until(entity_name, data, valid_from=..., until=...)

  tx.wire.update(observed, changes, valid_from=...)
  tx.wire.delete(observed)
  tx.wire.terminate(observed, valid_from=...)
  tx.wire.update_until(observed, changes, valid_from=..., until=...)
  tx.wire.terminate_until(observed, valid_from=..., until=...)

  tx.wire.update_where(target, changes, valid_from=...)
  tx.wire.delete_where(target)
  tx.wire.terminate_where(target, valid_from=...)
  tx.wire.update_until_where(target, changes, valid_from=..., until=...)
  tx.wire.terminate_until_where(target, valid_from=..., until=...)
  ```

  Only the representation differs. A Typed verb takes an Entity value whose
  Change Record already names its effective change; a Wire verb takes the frozen
  mapping a Wire read published plus an explicit changes document. Everything
  after that is the one pipeline: the same evidence resolver, the same claim
  algebra, the same instruction IR, the same buffer, the same planner, and the
  same transient lifecycle publisher. A Typed write and a Wire write of one object therefore merge,
  deduplicate, supersede, and conflict by the rules above rather than by any
  interface-specific one, and the buffered-insert ledger read-your-own-writes
  consults is one ledger, so an insert through either verb exempts a later write
  through the other.

  **A keyed source is a Parallax Wire read result, and nothing else.** The
  concrete Entity, the object addressed, the as-of pin, the participation, and
  the observed state all come from the value's own private Source Hint, so
  `insert` — which opens a row and has no source — is the one keyed verb that
  names an Entity, and it resolves that name by the reference-position rule
  every write target resolves through: the canonical `<namespace>.<name>`, or a
  bare local name exactly one Entity of the model carries, with a bare spelling
  two namespaces share refused as `reference-ambiguous-entity-name` rather than
  resolved to a first match. There is no
  explicit-Entity ordinary-mapping overload: a mapping a caller built, a
  `dict(node)` conversion, a JSON or pickle round trip, an `InvalidData` wrapper,
  and the `None` a non-hydrating root publishes in place of data are all refused
  for the same reason, that provenance was lost. A hydratable `InvalidData.data`
  passes: classification says what contradicted the model, never who may write.

  **Static validation precedes evidence resolution, always.** Verb and source
  shape, the finite-Transaction-Time refusal, the temporal window, member names,
  values, and assignment legality are judged from the model and the input alone;
  only then is the target Entity's Effective Concurrency Strategy derived and its
  evidence resolved. Within that static half, the authored documents' own shape
  comes first — it needs neither a source nor the model — so a call
  passing both a malformed change set and a source that lost its provenance hears
  about the change set, an `insert` whose payload is no document hears that
  before its Entity spelling is resolved, and a selection's shape runs all the way
  through the predicate node, whose `m-predicate` algebra is judged before the
  Entity, the window, or the assignments beside it are. Each verb then reads its
  remaining argument — the source a keyed verb was handed, the Entity spelling an
  `insert` names — before anything the target Entity or the model decides.
  A change set is a document the update verbs require: only
  the destructive and close verbs, which name no member, state one by passing
  none, and `{}` is a document naming no member rather than an absent argument.
  What that states differs by family. A keyed update addresses one row whose
  values its source published, so `{}` is the ordinary no-op — the same one an
  empty Typed effective change set is. A predicate update lowers to the canonical
  assignment algebra, whose list must be non-empty (above), and a selection has no
  published values to be a no-op against, so `{}` is refused there exactly as
  `tx.update_where(query)` with no assignments is. Malformed Wire input therefore
  always earns a static refusal
  rather than a `WriteEvidenceError`, whichever is also true — and the Typed lane
  reaches the same order for free, because `edit()` rejects an illegal assignment
  before `tx.update()` receives a value.

  **Which static refusal follows from whose rule was broken.**
  `WriteInstructionError` is the write verb's OWN verdict: input that states no
  well-formed write at all — a document position that is not a mapping of names
  to values, a self-containing container, an unresolvable target, an undeclared
  or unassignable member, a temporal bound the target's own temporality does not
  admit, a `[valid_from, until)` window stated as one bound rather than as a pair,
  an unordered one. A `*_until` verb requires both bounds whatever else the call
  turns out to be, because a keyed update whose change set is wholly restoring
  buffers no instruction, so the window no verb judged is a window nothing
  judges. A rule another module owns
  keeps that module's classification instead, so one input is classified one way
  at every boundary that accepts it: the closed pre-SQL `WriteRejectedError`
  vocabulary where a normative payload rule classifies the defect more exactly,
  which is the same carrier and the same rule names a predicate verb already
  answers with; `CanonicalDocumentError` where `m-predicate`'s own serde refuses
  a predicate node, which is also why a verb captures caller input without
  translating its spellings — a Python tuple rewritten as a list would make this
  the one boundary accepting an operand array that serde rejects; and
  `InstantError` where an admitted bound is no `m-core` instant — a naive
  datetime, a value of no datetime type at all, or an aware one naming no
  instant a UTC `datetime` holds. All are `ValueError`s and
  all precede any evidence question. Assignment
  legality is `judge_assignment`'s single verdict, reached through the same
  family-effective resolution the canonical predicate assignment uses, so
  identity, optimistic-version, temporal-axis, computed, and read-only members
  are refused for exactly the reasons their Typed peers are, and a relationship or
  otherwise undeclared name is refused as naming no member. Every named member is
  judged whether or not it turns out to be an effective change: legality may not
  depend on the stored state. An `insert` additionally refuses a framework-owned
  member, which the Typed Entity constructor refuses one layer earlier, and
  refuses a published read result as its payload under the same
  `write-value-already-stored` code the Typed provenance rule uses.

  **Wire values are the accepted wire spellings of their declared types.** A
  changes document, an insert payload, and a predicate assignment all cross the
  serde seam once at the verb and reach the instruction IR as the native carriers
  every other ingress hands it. That is what makes writing back what a read
  published a no-op: a member whose authored value already equals the source's
  own is a RESTORATION rather than an assignment, comparison is over decoded
  values rather than spellings, and a change set that restores everything it names
  issues no DML at all — the zero-round-trip no-op an empty Typed effective change
  set is, and the same restoration that cancels an assignment already buffered at
  the same claim scope. Assigning a Value Object supplies its complete
  replacement document.

  **Caller-owned input is captured at the call.** Inserted data, changes, the
  predicate target, and the temporal bounds are snapshotted recursively before
  the verb returns, so later mutation of any nested list or mapping cannot alter
  buffered intent. A keyed source is not copied — it is already deeply frozen —
  and what the verb retains of it is its identity, its resolved evidence, and the
  published value of the members the caller explicitly changed. The cost is
  proportional to authored input and never duplicates a read result.

  **A Wire write target is the canonical selection, not an Object Query.** The
  `_where` family takes exactly `{"entity", "predicate"}`; ordering, the cap,
  temporal selection, result narrowing, and Include Paths all shape a RESULT, and
  a set-based write has none to shape, so a target carrying any other key is
  refused. The changes document lowers to the same canonical assignment algebra
  the typed `.set(...)` spelling does, and the readless-versus-materializing
  dispatch is the one stated above.

- **The serialized write instruction has its own ingress family.** Beside the
  typed developer surface, `parallax.core.unit_work` accepts a canonical
  `m-unit-work` write-instruction document — the form the conformance adapter
  hands it, and the form an Object Query never becomes. A document that is not a
  well-formed canonical instruction raises `WriteInstructionError(ValueError)`:
  an unknown mutation, a missing or ill-typed `entity`, `rows`, or Valid-Time
  bound, an unexpected key, a forbidden framework-owned row key, an `entity`
  the connected model does not declare or two of its namespaces share, or a row
  naming a member the target's family does not declare. It is deliberately not
  a `QueryDefinitionError`: nothing authored it, so no `query-*` code describes
  it. It also carries this ingress's assignment refusals, which reach the same
  judgement the typed `.set(...)` path does and render the same message under
  this family's name rather than the copy family's. Once the document is well
  formed, the model-aware query rules it is subject to are exactly the ones
  the typed verbs reach and raise their owner families unchanged, so the two
  ingresses classify one input one way.

## 6. Database support and compatibility proof

### Independent Storage Layout oracle boundary

The reference harness remains an independent executable oracle over the core
specifications, schemas, and corpus. It compiles its own minimal conceptual
Table Layout from frozen descriptor and Inheritance facts for physical claim
validation, DDL, fixtures, golden write-shape checks, and Table read-back. It
MUST NOT import `parallax.core.storage_layout`, Python conformance provisioning,
generated Python layout output, or another Python production implementation.

The Python conformance adapter follows the opposite side of that boundary: its
model-derived DDL, fixture loading, SQL compilation, write lowering, and Table
observations use the accepted model's production `StorageLayoutFacet` and never
ask the reference harness to supply physical shape. Both implementations are
graded against the same language-neutral contract and corpus, so disagreement
remains observable rather than making Python its own oracle.

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
  case's compiled Table Layouts (`applyDdl`), then fixture rows in Entity
  Layout order
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
  error-code classification predicates. Runs in `uv run pytest tests/dialect`
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
  `query`, `exec`, `execRolledBack`, and `peer` against the container. The
  contract's **dialect-binding** obligation is discharged Docker-free in
  `tests/unit/test_dialect_binding.py`, which resolves `PostgresAdapter.dialect`
  off the class with no instance and no connection, and drives both shipped
  decorating ports — `FaultInjectingPort`, including the copy it re-wraps around
  a transaction-scoped port, and the engine's `_AbortingPort` — over a port
  declaring a second dialect no adapter here declares, so a decorator that
  authored `POSTGRES` of its own would fail rather than pass by coincidence.
  `tests/unit/test_postgres_adapter.py` pins the third port that stands in for
  another: the one `transaction` hands its body.
- **Matrix profiles.** One declared profile, **full**: `pg-full` — every claimed
  case, `run`, expected count derived from the corpus at runtime, never
  hard-coded. Beside it, and not a profile, runs the Docker-free `compile-sweep`
  lane: every **compile-eligible** claimed case, `compile`, emissions and binds
  vs golden plus normalization. It compiles without a database and so has no
  adapter to derive a dialect from, which is why it stays marker-driven and
  selected by `compile --dialect` rather than by a profile name. A claimed case
  the corpus declares run-only (`compileEligibility`, `m-case-format`) is graded
  by `pg-full` only; the compile lane's refusing port makes it emit the
  `compile-run-only` diagnostic (`m-conformance-adapter`) rather than a golden
  comparison, so the sweep stays honest without hard-coding which cases are
  excluded. No partial profiles exist; MariaDB is a §1 deferral, not a profile
  exclusion.
  `pg-full` is a declared value — `parallax.conformance.profile.PROFILES`, whose
  entries name a provisioner, which declares the adapter it opens. A profile's
  dialect is read back off that adapter's class, so it is answerable with no
  container and no connection, and no profile can name a dialect its adapter does
  not execute in. The `pg-full` sweep resolves that declaration rather than
  restating it: `tests/conftest.py`'s `profile_run` fixture is the profile's own
  provisioning, and the per-dialect goldens it grades against are keyed by the
  profile's own dialect. The conformance CLI resolves the same declaration —
  `parallax-conformance run --case <case> --profile pg-full` provisions through the
  profile and reports both the profile it ran and the dialect the container's
  adapter executed in; a name no profile declares is answered `unsupported`
  (`unsupported-profile`, exit 10) before anything is provisioned. `capabilities.dialects` is derived from `PROFILES` too
  (`parallax.conformance.claim`), so a claimed dialect is one some profile
  actually runs; the derivation reaches the concrete adapter through a deferred
  import, keeping psycopg out of the conformance adapter's import graph.
  A profile also constitutes the runs made under its name. `run_case` takes one
  `ProfileRun` — the profile's reporting name paired with the port the case
  executes through — and a run is constructed from a profile rather than from a
  name: `provisioned()` yields a `ProvisionedRun`, which opens the profile's own
  provisioner itself and takes no other recipe, `unprovisioned()` yields the run of
  a `rejected`-shape case over a port that refuses SQL, and `on_stand_in(port)`
  names the substitution the unit tests and Docker-free sweeps make when they stand
  a double in for a database. No caller names a port or a recipe beside the
  profile, so a run reported under one profile beside another's database is
  unspellable rather than merely checked
  (`database-provider-test-contract.md`). Constructing a `ProvisionedRun` acquires
  a live database, so it is a declared seam of `tools/check_database_access.py`
  alongside the provisioner itself. The declaration itself does not travel,
  because a declaration answers a dialect and a signature holding a port derives the
  dialect from the port alone. The `run` lane still refuses a profile `PROFILES`
  does not declare wherever it is entered — a `Profile` is constructible without
  being declared — so the CLI answers `unsupported-profile` before a case is read
  and `run_case` refuses the run's reporting name against the same roster before
  reading the case. `tests/unit/test_profile.py` pins the lookup, its refusal of
  an undeclared name, the dialect resolved with nothing constructed, what each
  constructor pairs, and both import-graph facts.
- **Commands and skip reporting.** Every collected item carries exactly one
  scheduling marker — `dbfree`, `db`, or `cost` — added at collection from what
  the item requires: `db` when its fixture closure reaches the session-scoped
  database fixture, `cost` when its function carries the `in_a_child_interpreter`
  boundary, `dbfree` otherwise. No item can carry none, and requiring both
  resources is a collection error rather than a precedence. `compile_sweep` and
  `adapter_smoke` remain as orthogonal focused selectors and classify nothing.
  `just python-test-dbfree`, `just python-test-db`, and `just python-test-cost`
  each own one invocation of their class, aggregated by
  `just python-check-dbfree`, `just python-check-db`, `just python-check-cost`,
  and `just python-check`. The `cost` class is outside `just check` and inside
  `just check-all` (`core/spec/language-testing.md` §7); its own CI job gates it
  on every change.
  Database-backed checks skip only when Docker is
  unavailable; a session-scoped fixture prints a final summary naming every
  skipped database-backed check and its reason, and the CI database lane fails
  on any skip — silent skips are structurally impossible.
- **Database Error mapping.** At the port boundary every driver exception raised
  by work the port itself performs — a statement, or the `transaction`
  boundary's begin, commit, or rollback — is
  re-raised as a Parallax Error carrying the neutral `m-db-error` category,
  the preserved native SQLSTATE, and the driver message; no driver exception
  type the port raises ever crosses above it. The one exclusion is the caller's
  own `transaction` body: an exception it raises is not the port's, so it
  crosses unchanged even when it is a driver exception, which is what keeps a
  body-authored deadlock-class failure from reading as retriable to
  `m-auto-retry` and having the body replayed. The translation constructs that error at the
  failing call and caches nothing, satisfying the `m-db-port` rule that no two
  invocations share an error instance — which lets Execution Lifecycle causal
  attribution identify the call whose error escaped. The provider test
  contract's failure-instance obligation is discharged Docker-free in
  `tests/unit/test_postgres_adapter.py`, which drives every raise site twice each
  over one connection stub that raises a single reused psycopg exception for all
  of them — a failed `execute`, a failed `execute_write`, and each failure of the
  boundary `transaction` wraps whole: its begin, its commit, and its rollback —
  and asserts the adapter hands back ten distinct errors carrying the same
  category, native code, and message. Repetition rules out reuse within a raise
  site and the shared adapter rules it out across them. The same file pins the
  rule's boundary in both directions: a body raising a psycopg exception over a
  succeeding rollback surfaces that identical object, while the same body over a
  rollback that itself fails with a psycopg exception surfaces the translated
  port error — including when the driver hands the body and the rollback ONE
  reused exception object, which is why the adapter separates a body failure
  from a boundary failure by where it occurred rather than by the object's
  identity or type. The
  SQLSTATE→category table (`40P01`,
  `40001` → deadlock; `55P03` → lock-wait timeout; `23505` → unique violation;
  …) lives in the pure dialect strategy where the Docker-free contract suite
  tests it.

### API Conformance Suite and Usage Guide

- **Framework and location.** pytest under
  `languages/python/tests/api/`, executing idiomatic public-API
  code through the shipped `parallax-snapshot` extension and
  `parallax-postgres` adapter against the real Testcontainers Postgres.
- **Coverage partition and no-drift guards.** An assertion computes
  `exercised ∪ reasoned-skipped == active slice` from corpus data at runtime,
  failing on stale case IDs or empty skip reasons. Four no-drift guards
  close the loop. Two run per example: the idiomatic Object Query's
  serialization equals the corpus document, and idiomatic class descriptors
  equal corpus descriptors. A third, scoped to every registered write story,
  drives it against a recording fake port and asserts its wire DML equals its
  corpus golden byte-exact (a commit story the golden DML, an abort story
  nothing for the discarded buffer). The fourth is a Docker-free, database-free
  **copy-to-row contract test** (`tests/api/test_copy_to_row_no_drift.py`, in the
  `dbfree` class), scoped to the
  write shapes that actually pass through Edited Copy lowering — keyed
  non-temporal updates and keyed temporal updates driven by an Edited Copy;
  inserts, deletes/terminates, and set-based materialize paths never reach
  `edited_row` and are proven by the ordinary conformance path. For
  each in-scope claimed write case it builds the fixture node, applies the
  case's changes through `edit(...)`, and lowers the Edited Copy through the
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

A claim about observable behavior is graded by behavior at the API boundary,
never by inspecting source structure. This specification constrains structure
only where a decision is itself about the source: which scope owns a module and
which artifact ships it, what a surface exports and what it keeps private,
whether anything is generated and where it lands, and what the toolchain runs.
That test is the rule, and it is applied to a sentence wherever the sentence
stands. §§1, 2, 6, 8, and 10 hold such decisions today, and the enforcement
scopes and reaches are recorded here; that list orients a reader and bounds
nothing, so a structural decision standing in a section it does not name answers
to the same test rather than being licensed by its absence from it. A behavioral
section that phrases a consequence as a fact about source text has misplaced it —
restate it as what a caller observes, or record it here.

Behavioral modules map onto Python submodules (enforcement scopes) inside the
distributions of §8. `m-metamodel`, `m-model-formation`, `m-inheritance`,
`m-storage-layout`, and `m-relationship` own the dedicated
`parallax.core.metamodel`, `parallax.core.model_formation`,
`parallax.core.inheritance`, `parallax.core.storage_layout`, and
`parallax.core.relationship` scopes.
`parallax.core._formation_profile` is the built-in Model Formation
composition root; its declared grants are exactly the formation runner plus every
module whose Formation Manifest row supplies a Rule Set or compiler, and
`m-pk-gen` supplies neither and is not imported. Every behavioral scope reaches
the metamodel it needs through `m-metamodel` and the typed owner facets.
`m-descriptor` maps to the separate `parallax.descriptor` scope and imports the
common runtime only through its language-neutral `m-core`, `m-metamodel`, and
`m-inheritance` edges — the last because a descriptor document may declare an
inheritance family that never forms, and the pre-formation walk that classifies
such a family reports it in `m-inheritance`'s own rule vocabulary rather than
minting a second one. Its private child support scope `parallax.descriptor._hub` alone imports
the Python-specific Domain Model construction and accepted-model read seams in
`parallax.core.entity`. This direct support edge is required because the class
and Descriptor Frontends deliberately return one concrete `DomainModel` type,
while the Domain Model's class-backed constructor owns Python realization and
therefore does not belong to the
representation-independent `parallax.core.metamodel` module. No
common-runtime, Snapshot, or Postgres scope imports the descriptor package.

The enforcement unit is the **scope**, not a package's `__all__`: an importer
granted `parallax.core.entity` reaches every module that scope owns, private
ones included. Three Snapshot modules use that grant for six names the Entity
frontend deliberately does not export — `parallax.snapshot._inspection` and
`parallax.snapshot.handle._write_inputs` read declarations from
`parallax.core.entity._declaration` (`declaration_of`, `is_entity_class`,
`members_of`), `parallax.snapshot.handle._write_inputs` reads the merged
member-name correspondences from `parallax.core.entity._entity`
(`wire_names_of`), and `parallax.snapshot.handle._database` reads the cataloged
model — the accepted Metamodel and the exact-model layout catalog derived from it
as one value — and the class index from `parallax.core.entity._model`
(`cataloged_model`, `class_index`).
Each is a seam between two first-party packages that a developer
never needs, so exporting the names to spell the reach publicly would widen the
developer surface to serve one lifecycle package. None of the three modules
takes a scope row of its own: they belong to `parallax.core.entity`, whose edge
every importer above already declares, and
`parallax.core.entity._construction_input`, `._expressions`, `._instance_state`,
`._layout`, and `._pydantic_storage` carry rows below because each needs a
NARROWER grant than its parent — not because they are the only children an
importer may reach.

`parallax.core.entity._instance_state` owns the physical backing beneath a
published Entity or Value Object — the per-class publication plan, the compact
slot, the tuple and its presence bitmap, both Adapters, and the Pydantic root
that answers for a value's instance state — and its grant row is what keeps that
a deep module rather than a second declaration engine. Granted two siblings and
nothing else, it can reach neither the engine that builds a class nor the writer
that publishes one, so a publication plan has to ARRIVE as plain data the engine
computed rather than be derived here from a model the scope could import.
`._construction_input` is the first sibling, and is granted `(none)`: the
sentinels a positional construction input spells, and the opaque handle a
relationship position names a node by, are read by the layout side, by a runtime
that lays a stored row out against one, by the writer, by the descriptors that
answer a member read, and by the backing above, which are scopes that
deliberately cannot reach one another — so they are housed where every one of
them may reach and nothing may be reached back, which is also what keeps a row's
producer structurally unable to reach the writer, `construct`, or model
formation. `._pydantic_storage` is the second, and is granted `(none)` for its own
reason: it reaches a value's attribute storage past every binding over it —
including the framework's own presentation, which is layered directly on it —
and what it reaches is Pydantic's own slot descriptors and nothing else, so a
first-party import of any kind would mean it had grown a second job. All three
are marked **sealed**, for the reason the three below them are.

`parallax.core.entity._layout` is reached the other way round. It carries a row
of its own because a runtime that materializes values from stored rows needs the
member layouts — the positions a row is laid out at and the canonical
broad-relationship order a full-width relationship row is written at — without
the frontend's own closure. So every Snapshot module that carries one
connection's cataloged model, or the layouts inside it, names the declared scope
that owns what it reads rather than reaching a private module through the
parent's edge; the same is true of the sentinel a row spells absence with, which
is why that runtime is granted `._construction_input` as well. Both are marked
**sealed** below, because "nothing else" is a claim about the package they sit in
as much as about the ones they do not.

`parallax.core.object_query._fluent` is the one child scope declared for the
opposite reason: it needs a WIDER grant than its parent. The typed Object Query is
generic over Entity Classes, so it reaches the Entity frontend for the descriptor
values a clause call is written with, while `m-object-query` itself must stay
reachable by `m-temporal-read`, `m-deep-fetch`, `m-sql`, and the read-preflight
seam — none of which may reach that frontend. The parent package's own interface
therefore does not import this module: a consumer of the canonical query value
never pulls the typed surface in, and one that wants the typed surface names this
module. That is what keeps the widening contained rather than leaking through the
package.

`parallax.snapshot.handle._read_scope` is the read composition both Handles
delegate to, scoped apart from its package so its row states what a read ladder
reaches and what it does not: the query and temporal vocabulary it lowers
through, the page plan a stream is delivered against, the read result it
publishes, the Database Port, the unit of work, and the lifecycle activities it
opens — and none of batch writes, Transaction-Time writes, or Bitemporal writes,
which nothing in that closure names. Bounded automatic retry is deliberately NOT
among the exclusions, and the row does not claim it: `modules.md` declares
`m-execution-lifecycle --> m-auto-retry`, and a forbidden row is the complement
of a closure, so a scope granted the lifecycle module it needs for the re-entry
gate and the read roots carries retry with it whatever the composition itself
imports. What the row says about retry is that this scope inherits it, not that
it is forbidden. Write lowering is a child scope of the same parent, which the
general target set excludes, so not importing it is the only exclusion available
there.

A behavioral module maps to the scope that needs its whole edge set.
`m-execution-lifecycle` is owned by `parallax.core.execution_lifecycle`, while
the Snapshot handle is the composition scope that publishes snapshot reads and
streams through the injected internal publisher. Snapshot results and
materialization scopes neither import the lifecycle module nor retain events.
This keeps observation at the Handle boundary without granting SQL generation
to row-to-graph materialization.

import-linter forbids every production scope-pair import the DAG does not
permit — the generated forbidden-edge complement below, with the
conformance-family scopes exempted as importers per `modules.md` — so illegal
non-edges are rejected, not merely wrong directions; artifact separation never
legalizes a forbidden edge.

A grant names a whole scope, so a scope granted a parent may ordinarily import
anything nested inside it. A scope marked **isolated** below is the exception:
it is a forbidden target in every production row that neither contains it nor is
contained by it, whatever those rows are granted, so reaching it is a rejected
import rather than an unstated grant. The rows carrying that mark are the whole
of it. The one import no row can reject is its own ancestors' —
a forbidden entry there would overlap that contract's source, and import-linter
skips it — so `tools/check_scope_ownership.py` rejects that edge over the files
instead, resolving relative imports and reading an imported name as a possible
submodule, so no spelling escapes — neither the dotted path nor the relative
one, and neither naming the scope nor naming a member of it. No production
module imports an isolated scope, and the two halves together are what enforce
it.

A scope marked **sealed** below is that same overlap seen from the other side: a
child whose row is the whole of what it imports, inside the package holding it as
well as outside it. A row can neither forbid what sits inside its own source
package nor except it, so it refuses a neighbour only through the chain that
leaves it — reaching one whose own closure escapes the row is reported at
whatever it escapes to, which is what keeps the writer, `construct`, and model
formation out of reach of the scopes below. A neighbour that reaches nothing the
row does not already permit leaves no chain to report, so nothing rejects that
import, and a narrow grant's completeness would rest on what the modules beside
it happen to import. The same `tools/check_scope_ownership.py` walk closes that
residue over the sealed scope's own files, in every spelling, so what a sealed
scope reaches inside its parent package is what its row grants and nothing more,
and a granted sibling stays legal however the import that reaches it is written.
The rows carrying that mark are the whole of it;
a scope not marked so is judged by its contract alone, and reaching a private
module of its parent is what child scopes ordinarily do. Write-observation
retention is sealed for the rule read the other way round: the find executor
drives it while its rows are live, and retention names nothing of that executor
back. The executor is a module of the parent package, so no contract sourced at
the child can reject that import, and the seal is where the one-way rule is
graded rather than merely stated.

Sealing generates nothing, so a scope losing that mark silently keeps every
contract it had; isolation shapes the target set of nearly every generated
contract, so losing it changes them all at once. Both marks are therefore
declared exactly once — the rows below, each naming the parent its guarantee is
stated against — and `tools/check_dag_sync.py` compares mark and parent alike
with the tables `tools/check_scope_ownership.py` enforces, so marking a scope in
one place alone, against the wrong parent, or twice — a second declaration is a
contradiction to reject, not a later reading to keep — fails the sync check.

| Behavioral/support module | Source owner/path | Enforcement scope | Allowed direct dependencies | Enforcement rule/config |
|---|---|---|---|---|
| `m-core` | `parallax.core.base` | `parallax.core.base` | (none) | generated forbidden contracts, `languages/python/pyproject.toml` |
| `m-wire` | `parallax.core.wire` | `parallax.core.wire` | `m-core` | generated forbidden contracts |
| `m-metamodel` | `parallax.core.metamodel` | `parallax.core.metamodel` | `m-core` | generated forbidden contracts |
| `m-model-formation` | `parallax.core.model_formation` | `parallax.core.model_formation` | `m-metamodel` | generated forbidden contracts |
| Model formation composition root (support) | `parallax.core._formation_profile` | `parallax.core._formation_profile` | `m-metamodel`, `m-model-formation`, `m-inheritance`, `m-storage-layout`, `m-value-object`, `m-relationship`, `m-temporal-read`, `m-opt-lock` | generated forbidden contracts |
| `m-descriptor` | `parallax.descriptor` | `parallax.descriptor` | `m-core`, `m-metamodel`, `m-inheritance` | generated forbidden contracts + cross-package contract |
| `m-pk-gen` | `parallax.core.pk_gen` | `parallax.core.pk_gen` | `m-metamodel` | generated forbidden contracts |
| `m-inheritance` | `parallax.core.inheritance` | `parallax.core.inheritance` | `m-metamodel`, `m-model-formation` | generated forbidden contracts |
| `m-storage-layout` | `parallax.core.storage_layout` | `parallax.core.storage_layout` | `m-metamodel`, `m-model-formation`, `m-inheritance`, `m-relationship` | generated forbidden contracts |
| `m-value-object` | `parallax.core.value_object` | `parallax.core.value_object` | `m-metamodel`, `m-model-formation` | generated forbidden contracts |
| `m-document-codec` | `parallax.core.document_codec` | `parallax.core.document_codec` | `m-core`, `m-metamodel`, `m-wire` | generated forbidden contracts |
| `m-relationship` | `parallax.core.relationship` | `parallax.core.relationship` | `m-metamodel`, `m-model-formation` | generated forbidden contracts |
| `m-predicate` | `parallax.core.predicate` | `parallax.core.predicate` | `m-metamodel`, `m-inheritance`, `m-wire` | generated forbidden contracts |
| `m-object-query` | `parallax.core.object_query` | `parallax.core.object_query` | `m-predicate`, `m-metamodel`, `m-inheritance`, `m-wire` | generated forbidden contracts |
| Typed Object Query surface (support, child of `parallax.core.object_query`) | `parallax.core.object_query._fluent` | `parallax.core.object_query._fluent` | `m-core`, `m-metamodel`, `m-predicate`, `parallax.core.entity` | generated forbidden contracts |
| `m-sql` | `parallax.core.sql_gen` | `parallax.core.sql_gen` | `m-predicate`, `m-object-query`, `m-dialect`, `m-metamodel`, `m-inheritance`, `m-storage-layout`, `m-relationship`, `m-document-codec`, `m-wire`, `m-unit-work`, `m-deep-fetch` | generated forbidden contracts |
| `m-dialect` | `parallax.core.dialect` (incl. driver-free `dialect.postgres`) | `parallax.core.dialect` | `m-core` | generated forbidden contracts |
| `m-db-port` | `parallax.core.db_port` (abstract) | `parallax.core.db_port` | `m-core`, `m-dialect` | generated forbidden contracts |
| `m-db-error` | `parallax.core.db_error` | `parallax.core.db_error` | `m-db-port`, `m-dialect` | generated forbidden contracts |
| `m-unit-work` | `parallax.core.unit_work` | `parallax.core.unit_work` | `m-predicate`, `m-wire`, `m-db-port`, `m-temporal-read` | generated forbidden contracts |
| `m-read-lock` | `parallax.core.read_lock` | `parallax.core.read_lock` | `m-unit-work`, `m-dialect` | generated forbidden contracts |
| `m-auto-retry` | `parallax.core.auto_retry` | `parallax.core.auto_retry` | `m-unit-work`, `m-db-error` | generated forbidden contracts |
| `m-execution-lifecycle` | `parallax.core.execution_lifecycle` | `parallax.core.execution_lifecycle` | `m-sql`, `m-db-port`, `m-db-error`, `m-unit-work`, `m-auto-retry` | generated forbidden contracts |
| `m-opt-lock` | `parallax.core.opt_lock` | `parallax.core.opt_lock` | `m-unit-work`, `m-temporal-read`, `m-metamodel`, `m-model-formation`, `m-inheritance` | generated forbidden contracts |
| `m-temporal-read` | `parallax.core.temporal_read` | `parallax.core.temporal_read` | `m-predicate`, `m-object-query`, `m-metamodel`, `m-model-formation`, `m-inheritance` | generated forbidden contracts |
| `m-txtime-write` | `parallax.core.txtime_write` | `parallax.core.txtime_write` | `m-temporal-read`, `m-unit-work` | generated forbidden contracts |
| `m-bitemp-write` | `parallax.core.bitemp_write` | `parallax.core.bitemp_write` | `m-txtime-write` | generated forbidden contracts |
| `m-batch-write` | `parallax.core.batch_write` | `parallax.core.batch_write` | `m-unit-work` | generated forbidden contracts |
| `m-navigate` | `parallax.core.navigate` | `parallax.core.navigate` | `m-predicate`, `m-unit-work`, `m-temporal-read`, `m-inheritance`, `m-relationship` | generated forbidden contracts |
| `m-deep-fetch` | `parallax.core.deep_fetch` | `parallax.core.deep_fetch` | `m-navigate`, `m-relationship`, `m-object-query`, `m-inheritance`, `m-predicate`, `m-unit-work`, `m-wire` | generated forbidden contracts |
| `m-snapshot-read` | `parallax.snapshot._read_result` | `parallax.snapshot._read_result` | `m-deep-fetch`, `m-document-codec`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-temporal-read`, `m-execution-lifecycle`, `m-wire` | generated forbidden contracts + cross-package contract |
| Streamed-read page plan (support) | `parallax.core.continuation` | `parallax.core.continuation` | `m-metamodel`, `m-inheritance`, `m-predicate`, `m-object-query`, `m-temporal-read`, `m-wire` | generated forbidden contracts |
| Snapshot handle and composition surface (support) | `parallax.snapshot.handle` | `parallax.snapshot.handle` | `parallax.core.continuation`, `parallax.snapshot.materialize`, `parallax.snapshot._read_result`, `parallax.snapshot._inspection`, `parallax.core.entity`, `m-core`, `m-wire`, `m-metamodel`, `m-predicate`, `m-inheritance`, `m-storage-layout`, `m-temporal-read`, `m-deep-fetch`, `m-navigate`, `m-dialect`, `m-db-port`, `m-sql`, `m-unit-work`, `m-read-lock`, `m-auto-retry`, `m-execution-lifecycle`, `m-opt-lock`, `m-batch-write`, `m-txtime-write`, `m-bitemp-write` | generated forbidden contracts + cross-package contract |
| Execution lifecycle recorder (support, isolated child of `parallax.core.execution_lifecycle`) | `parallax.core.execution_lifecycle.testing` | `parallax.core.execution_lifecycle.testing` | `m-execution-lifecycle` | generated forbidden contracts + `tools/check_scope_ownership.py` |
| Snapshot node inspection (support) | `parallax.snapshot._inspection` | `parallax.snapshot._inspection` | `parallax.core.entity`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-temporal-read` | generated forbidden contracts |
| Snapshot graph materialization (support, child of `parallax.snapshot.handle`) | `parallax.snapshot.handle._materializer` | `parallax.snapshot.handle._materializer` | `parallax.snapshot.materialize`, `parallax.snapshot._inspection`, `parallax.core.entity`, `m-metamodel`, `m-inheritance`, `m-temporal-read` | generated forbidden contracts |
| Snapshot row-to-graph conversion and the sealed graph (support) | `parallax.snapshot.materialize` | `parallax.snapshot.materialize` | `parallax.core.entity._construction_input`, `parallax.core.entity._layout`, `m-deep-fetch`, `m-document-codec`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-temporal-read`, `m-wire` | generated forbidden contracts + cross-package contract |
| Snapshot read-result row-to-graph edge (support edge of the snapshot read-result scope) | `parallax.snapshot._read_result` | `parallax.snapshot._read_result` | `parallax.snapshot.materialize` | generated forbidden contracts |
| Snapshot read preflight (support, child of `parallax.snapshot.handle`) | `parallax.snapshot.handle._preflight` | `parallax.snapshot.handle._preflight` | `m-metamodel`, `m-predicate`, `m-object-query` | generated forbidden contracts |
| Snapshot read composition (support, child of `parallax.snapshot.handle`) | `parallax.snapshot.handle._read_scope` | `parallax.snapshot.handle._read_scope` | `parallax.core.entity`, `parallax.core.continuation`, `parallax.snapshot._read_result`, `parallax.snapshot._inspection`, `m-object-query`, `m-temporal-read`, `m-db-port`, `m-unit-work`, `m-read-lock`, `m-opt-lock`, `m-execution-lifecycle` | generated forbidden contracts |
| Snapshot handle refusals (support, child of `parallax.snapshot.handle`) | `parallax.snapshot.handle._errors` | `parallax.snapshot.handle._errors` | (none) | generated forbidden contracts + `tools/check_scope_ownership.py` |
| Snapshot handle write execution (support, child group of `parallax.snapshot.handle`) | `parallax.snapshot.handle._family`, `._keyed_sql`, `._write_lowering` | those three scopes, sharing one grant row | `m-core`, `m-wire`, `m-metamodel`, `m-inheritance`, `m-storage-layout`, `m-document-codec`, `m-temporal-read`, `m-dialect`, `m-db-port`, `m-sql`, `m-unit-work`, `m-opt-lock`, `m-txtime-write`, `m-bitemp-write` | generated forbidden contracts |
| Snapshot write-observation retention (support, sealed child of `parallax.snapshot.handle`) | `parallax.snapshot.handle._retention` | `parallax.snapshot.handle._retention` | `m-metamodel`, `m-unit-work`, `m-temporal-read`, `parallax.snapshot.handle._family` | generated forbidden contracts + `tools/check_scope_ownership.py` |
| `m-case-format` | `parallax.conformance.case_format` (dev-only) | `parallax.conformance.case_format` | `m-core` | generated forbidden contracts (dev tree) |
| `m-conformance-adapter` | `parallax.conformance.cli` (dev-only) | `parallax.conformance.cli` | `m-case-format`, plus any claimed behavioral or support scope it harnesses — the core conformance-family exception | generated forbidden contracts (dev tree) |
| `m-api-conformance` | `languages/python/tests/api` (dev-only) | `tests.api` | `m-case-format` (harnesses the public surface) | pytest collection boundary |
| Descriptor Hub orchestration (support, child of `parallax.descriptor`) | `parallax.descriptor._hub` | `parallax.descriptor._hub` | `parallax.core.entity` (private Hub-construction seam only) | generated forbidden contracts + cross-package contract |
| Entity and Object Query frontend (support) | `parallax.core.entity` | `parallax.core.entity` | `m-core`, `m-metamodel`, `m-inheritance`, `m-relationship`, `m-predicate`, `m-object-query`, `m-temporal-read`, `m-document-codec`, `parallax.core._formation_profile` | generated forbidden contracts |
| Query expression values (support, child of `parallax.core.entity`) | `parallax.core.entity._expressions` | `parallax.core.entity._expressions` | `m-core`, `m-wire`, `m-metamodel`, `m-predicate`, `m-object-query` | generated forbidden contracts |
| Construction-input sentinels and the node handle (support, sealed child of `parallax.core.entity`) | `parallax.core.entity._construction_input` | `parallax.core.entity._construction_input` | (none) | generated forbidden contracts + `tools/check_scope_ownership.py` |
| Published instance state (support, sealed child of `parallax.core.entity`) | `parallax.core.entity._instance_state` | `parallax.core.entity._instance_state` | `parallax.core.entity._construction_input`, `parallax.core.entity._pydantic_storage` | generated forbidden contracts + `tools/check_scope_ownership.py` |
| A value's own Pydantic storage (support, sealed child of `parallax.core.entity`) | `parallax.core.entity._pydantic_storage` | `parallax.core.entity._pydantic_storage` | (none) | generated forbidden contracts + `tools/check_scope_ownership.py` |
| Exact-model member layouts (support, sealed child of `parallax.core.entity`) | `parallax.core.entity._layout` | `parallax.core.entity._layout` | `m-metamodel`, `m-inheritance`, `m-relationship` | generated forbidden contracts + `tools/check_scope_ownership.py` |
| Concrete Postgres adapter (support) | `parallax.postgres.adapter` | `parallax.postgres` | `m-core`, `m-wire`, `m-db-port`, `m-db-error`, `m-dialect`, psycopg | generated forbidden contracts + cross-package contract |
| Composition root (support) | application/test code calling `parallax.snapshot.connect` | (application-owned) | `parallax.snapshot`, `parallax.postgres` | only the root imports a concrete adapter |

Behavioral modules carry a module tag, so their allowed direct dependencies are
already machine-readable from the fenced `dependency-graph` block in
`core/spec/modules.md`. Support scopes carry no tag, and a behavioral scope may
also need a Python-only support edge that has no language-neutral module tag;
their rows above are the only declaration of those edges. The fenced
`support-scope-graph` block below is the machine-readable form of exactly those
support edges, written in the same `A --> B` grammar and naming enforcement
scopes on both sides.
`parallax.descriptor._hub --> parallax.core.entity` is the descriptor
distribution's sole Python-only edge; the parent `m-descriptor` scope's
`m-core` and `m-metamodel` edges remain language-neutral and come from
`core/spec/modules.md`.
The prose rows and the block MUST agree. `tools/check_dag_sync.py` parses
**both** — the rows' "Allowed direct dependencies" column and the block — and
fails when they disagree with each other or when its own `SUPPORT_SCOPE_DEPS`
table disagrees with either, so the generated contracts cannot drift from this
section and no single representation can be edited alone. Each support scope is
declared by exactly one prose row, and a second row for a support scope already
declared fails rather than replacing the first. In the rows, only a
backticked module tag or `parallax.*` scope declares a grant; unbackticked
prose (`psycopg`) names no enforcement scope. A scope granting nothing has no
edge to write and must still be declared, because its emptiness is what it
enforces: both representations spell it `(none)` — the dependency column
outright, the block as the edge target — and naming `(none)` beside a real
grant is rejected as a contradiction.

```support-scope-graph
parallax.core._formation_profile --> parallax.core.metamodel
parallax.core._formation_profile --> parallax.core.model_formation
parallax.core._formation_profile --> parallax.core.inheritance
parallax.core._formation_profile --> parallax.core.storage_layout
parallax.core._formation_profile --> parallax.core.value_object
parallax.core._formation_profile --> parallax.core.relationship
parallax.core._formation_profile --> parallax.core.temporal_read
parallax.core._formation_profile --> parallax.core.opt_lock
parallax.descriptor._hub --> parallax.core.entity
parallax.core.entity --> parallax.core.base
parallax.core.entity --> parallax.core.metamodel
parallax.core.entity --> parallax.core.inheritance
parallax.core.entity --> parallax.core.relationship
parallax.core.entity --> parallax.core.predicate
parallax.core.entity --> parallax.core.object_query
parallax.core.entity --> parallax.core.temporal_read
parallax.core.entity --> parallax.core.document_codec
parallax.core.entity --> parallax.core._formation_profile
parallax.core.entity._expressions --> parallax.core.metamodel
parallax.core.entity._expressions --> parallax.core.predicate
parallax.core.entity._expressions --> parallax.core.object_query
parallax.core.entity._expressions --> parallax.core.base
parallax.core.entity._expressions --> parallax.core.wire
parallax.core.object_query._fluent --> parallax.core.base
parallax.core.object_query._fluent --> parallax.core.metamodel
parallax.core.object_query._fluent --> parallax.core.predicate
parallax.core.object_query._fluent --> parallax.core.entity
parallax.core.entity._construction_input --> (none)
parallax.core.entity._pydantic_storage --> (none)
parallax.core.entity._instance_state --> parallax.core.entity._construction_input
parallax.core.entity._instance_state --> parallax.core.entity._pydantic_storage
parallax.core.entity._layout --> parallax.core.metamodel
parallax.core.entity._layout --> parallax.core.inheritance
parallax.core.entity._layout --> parallax.core.relationship
parallax.core.execution_lifecycle.testing --> parallax.core.execution_lifecycle
parallax.snapshot._inspection --> parallax.core.entity
parallax.snapshot._inspection --> parallax.core.metamodel
parallax.snapshot._inspection --> parallax.core.inheritance
parallax.snapshot._inspection --> parallax.core.relationship
parallax.snapshot._inspection --> parallax.core.temporal_read
parallax.core.continuation --> parallax.core.metamodel
parallax.core.continuation --> parallax.core.inheritance
parallax.core.continuation --> parallax.core.predicate
parallax.core.continuation --> parallax.core.object_query
parallax.core.continuation --> parallax.core.temporal_read
parallax.core.continuation --> parallax.core.wire
parallax.snapshot.handle --> parallax.core.continuation
parallax.snapshot.handle --> parallax.snapshot.materialize
parallax.snapshot.handle --> parallax.snapshot._read_result
parallax.snapshot.handle --> parallax.snapshot._inspection
parallax.snapshot.handle --> parallax.core.entity
parallax.snapshot.handle --> parallax.core.base
parallax.snapshot.handle --> parallax.core.wire
parallax.snapshot.handle --> parallax.core.metamodel
parallax.snapshot.handle --> parallax.core.predicate
parallax.snapshot.handle --> parallax.core.inheritance
parallax.snapshot.handle --> parallax.core.storage_layout
parallax.snapshot.handle --> parallax.core.temporal_read
parallax.snapshot.handle --> parallax.core.deep_fetch
parallax.snapshot.handle --> parallax.core.navigate
parallax.snapshot.handle --> parallax.core.dialect
parallax.snapshot.handle --> parallax.core.db_port
parallax.snapshot.handle --> parallax.core.sql_gen
parallax.snapshot.handle --> parallax.core.unit_work
parallax.snapshot.handle --> parallax.core.read_lock
parallax.snapshot.handle --> parallax.core.auto_retry
parallax.snapshot.handle --> parallax.core.execution_lifecycle
parallax.snapshot.handle --> parallax.core.opt_lock
parallax.snapshot.handle --> parallax.core.batch_write
parallax.snapshot.handle --> parallax.core.txtime_write
parallax.snapshot.handle --> parallax.core.bitemp_write
parallax.snapshot._read_result --> parallax.snapshot.materialize
parallax.snapshot.materialize --> parallax.core.entity._construction_input
parallax.snapshot.materialize --> parallax.core.entity._layout
parallax.snapshot.materialize --> parallax.core.deep_fetch
parallax.snapshot.materialize --> parallax.core.document_codec
parallax.snapshot.materialize --> parallax.core.metamodel
parallax.snapshot.materialize --> parallax.core.inheritance
parallax.snapshot.materialize --> parallax.core.relationship
parallax.snapshot.materialize --> parallax.core.temporal_read
parallax.snapshot.materialize --> parallax.core.wire
parallax.snapshot.handle._materializer --> parallax.snapshot.materialize
parallax.snapshot.handle._materializer --> parallax.snapshot._inspection
parallax.snapshot.handle._materializer --> parallax.core.entity
parallax.snapshot.handle._materializer --> parallax.core.metamodel
parallax.snapshot.handle._materializer --> parallax.core.inheritance
parallax.snapshot.handle._materializer --> parallax.core.temporal_read
parallax.snapshot.handle._preflight --> parallax.core.metamodel
parallax.snapshot.handle._preflight --> parallax.core.predicate
parallax.snapshot.handle._preflight --> parallax.core.object_query
parallax.snapshot.handle._read_scope --> parallax.core.entity
parallax.snapshot.handle._read_scope --> parallax.core.continuation
parallax.snapshot.handle._read_scope --> parallax.snapshot._read_result
parallax.snapshot.handle._read_scope --> parallax.snapshot._inspection
parallax.snapshot.handle._read_scope --> parallax.core.object_query
parallax.snapshot.handle._read_scope --> parallax.core.temporal_read
parallax.snapshot.handle._read_scope --> parallax.core.db_port
parallax.snapshot.handle._read_scope --> parallax.core.unit_work
parallax.snapshot.handle._read_scope --> parallax.core.read_lock
parallax.snapshot.handle._read_scope --> parallax.core.opt_lock
parallax.snapshot.handle._read_scope --> parallax.core.execution_lifecycle
parallax.snapshot.handle._errors --> (none)
parallax.snapshot.handle._family --> parallax.core.base
parallax.snapshot.handle._family --> parallax.core.wire
parallax.snapshot.handle._family --> parallax.core.metamodel
parallax.snapshot.handle._family --> parallax.core.inheritance
parallax.snapshot.handle._family --> parallax.core.storage_layout
parallax.snapshot.handle._family --> parallax.core.document_codec
parallax.snapshot.handle._family --> parallax.core.temporal_read
parallax.snapshot.handle._family --> parallax.core.dialect
parallax.snapshot.handle._family --> parallax.core.db_port
parallax.snapshot.handle._family --> parallax.core.sql_gen
parallax.snapshot.handle._family --> parallax.core.unit_work
parallax.snapshot.handle._family --> parallax.core.opt_lock
parallax.snapshot.handle._family --> parallax.core.txtime_write
parallax.snapshot.handle._family --> parallax.core.bitemp_write
parallax.snapshot.handle._keyed_sql --> parallax.core.base
parallax.snapshot.handle._keyed_sql --> parallax.core.wire
parallax.snapshot.handle._keyed_sql --> parallax.core.metamodel
parallax.snapshot.handle._keyed_sql --> parallax.core.inheritance
parallax.snapshot.handle._keyed_sql --> parallax.core.storage_layout
parallax.snapshot.handle._keyed_sql --> parallax.core.document_codec
parallax.snapshot.handle._keyed_sql --> parallax.core.temporal_read
parallax.snapshot.handle._keyed_sql --> parallax.core.dialect
parallax.snapshot.handle._keyed_sql --> parallax.core.db_port
parallax.snapshot.handle._keyed_sql --> parallax.core.sql_gen
parallax.snapshot.handle._keyed_sql --> parallax.core.unit_work
parallax.snapshot.handle._keyed_sql --> parallax.core.opt_lock
parallax.snapshot.handle._keyed_sql --> parallax.core.txtime_write
parallax.snapshot.handle._keyed_sql --> parallax.core.bitemp_write
parallax.snapshot.handle._write_lowering --> parallax.core.base
parallax.snapshot.handle._write_lowering --> parallax.core.wire
parallax.snapshot.handle._write_lowering --> parallax.core.metamodel
parallax.snapshot.handle._write_lowering --> parallax.core.inheritance
parallax.snapshot.handle._write_lowering --> parallax.core.storage_layout
parallax.snapshot.handle._write_lowering --> parallax.core.document_codec
parallax.snapshot.handle._write_lowering --> parallax.core.temporal_read
parallax.snapshot.handle._write_lowering --> parallax.core.dialect
parallax.snapshot.handle._write_lowering --> parallax.core.db_port
parallax.snapshot.handle._write_lowering --> parallax.core.sql_gen
parallax.snapshot.handle._write_lowering --> parallax.core.unit_work
parallax.snapshot.handle._write_lowering --> parallax.core.opt_lock
parallax.snapshot.handle._write_lowering --> parallax.core.txtime_write
parallax.snapshot.handle._write_lowering --> parallax.core.bitemp_write
parallax.snapshot.handle._retention --> parallax.core.metamodel
parallax.snapshot.handle._retention --> parallax.core.unit_work
parallax.snapshot.handle._retention --> parallax.core.temporal_read
parallax.snapshot.handle._retention --> parallax.snapshot.handle._family
parallax.postgres --> parallax.core.base
parallax.postgres --> parallax.core.wire
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
  edge follows the identical reasoning: `Transaction.find`
  is a claimed find, so it composes `parallax.core.navigate.canonicalize`
  immediately after `m-temporal-read`'s root injection, mirroring the
  conformance engine's own composition-at-the-engine order. The generator also encodes
  the core **conformance-family exception** (`modules.md`): the
  conformance-family scopes (`parallax.conformance.*`, plus the
  pytest-bounded `tests.api`) are exempted from the complement
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
- **Carrier-neutral private compiler reaches.** The defining leaves, imported
  names, and authorized importing modules are exact. A second importer or name is
  a new topology decision, not an incidental use of an existing scope grant.

  ```carrier-neutral-private-reaches
  parallax.core.sql_gen._compile | CompiledRead, MaterializedReadRow, compile_read | parallax.snapshot.handle._read
  parallax.core.sql_gen._compile | CompiledRead, compile_read | parallax.snapshot.handle._predicate_writes; parallax.conformance.engine
  parallax.core.sql_gen._write | compile_write_step | parallax.snapshot.handle._write_lowering; parallax.conformance.engine
  ```

  Snapshot's imports are first-party private implementation reaches;
  conformance imports are development-only adapter reaches. Neither defining
  leaf is exported from `parallax.core.sql_gen`, and no other consumer imports
  these names. The topology contract test pins this block independently of the
  broader generated scope graph. The source exact-set inventory MUST use this
  same importer/name set, so an implementation cannot widen either set silently.
- **The conformance family's accepted private reaches.** The enforcement unit is
  the scope, so the importing-side exemption above already reaches a granted
  scope's private modules; what the exemption does not decide is *which* of them
  the adapter may read. The adapter drives production through supported entry
  points, and the residue is an enumerated set rather than a habit, one that
  **reaches no shipped distribution but the common runtime**:
  `parallax.core.entity._model.model_of` in its corpus-model loader, and — in its
  second-frontend fixture — `parallax.core.entity._model.cataloged_model` and
  both names its one import of
  `parallax.core.object_query._fluent` binds, `ObjectQuery` and
  `object_query_node`. All four are **rebutted rather than exempted**: `model_of`
  and the two typed-query names are already accepted private seams of
  production's own composition root and read preflight, and the typed surface is
  reached by naming the module that owns it — which is what a consumer wanting it
  does above, the Snapshot handle included, and why `ObjectQuery` appears here
  although §8 re-exports it. `model_of` exists precisely so a separately
  distributed frontend can read the accepted model out of a Domain Model
  (*Canonical descriptor input*), which is what the adapter is doing.
  `cataloged_model` is accepted for the same composition root and for the same
  reason the second frontend needs it: a source that drives the production find
  executor takes the accepted model and the layout catalog paired with it through
  the one door, rather than reading either half separately or building a second
  catalog beside it. A second managed value lifecycle merges and constructs for
  itself — that is what makes it second — but a node's member row is neither: it
  crosses `populate` as the merge laid it out, against the same model-owned
  member layout the writer reads it against, so the fixture hands a row over the
  one way production hands one over and no rule is restated in a second place.
  The adapter engine and second-source fixture also import the private Snapshot
  `preflight` operation so compile-only and alternate-source reads consume the
  same validated execution token as production. The engine's private `m-sql`
  compiler reaches are enumerated separately in the carrier-neutral block above,
  and the case loader's `wire._json.authored_number` reach is the production YAML
  token-preservation seam. Compatibility inputs use canonical Wire literals, so
  case ingress needs no private token-inspection reach. Each remaining reach stays
  keyed by its exact importing module and imported names in the source inventory.
  Widening
  `parallax.core.entity`'s shipped surface to serve a development-only consumer
  of a documented first-party seam would be the wrong repair.

  The `m-descriptor` record graph is **not** in the set: corpus models
  reach the adapter through the public `domain_model_from_*` doors and are read
  through the accepted model's own vocabulary, so no `parallax.descriptor`
  private module is imported at all. Each reach is keyed by the module that
  makes it, so a second importer of an accepted name is a new decision here.
  `tests/unit/test_source_enforcement_topology.py` holds the exact set for both
  this family and Snapshot's, as an inventory that fails when it drifts.
- **Child enforcement scopes.** A support scope MAY declare child scopes over
  its own private implementation modules when the child's declared grants are
  materially narrower than the parent's closure or when one orchestration leaf
  requires a narrowly additive first-party grant that must remain forbidden to
  the rest of the parent package. The declared children of
  `parallax.snapshot.handle` are the narrower wrapping and read-preflight
  scopes, the write-lowering scopes, and the zero-grant refusal leaf.
  `parallax.descriptor._hub` is the additive case: its sole extra grant is the
  first-party Entity frontend seam required to construct and read the one
  concrete `DomainModel` type. `parallax.snapshot.handle._errors` is the empty case: the
  read-preflight and write-lowering scopes raise one error class while granting
  disjoint dependencies, so the module holding it may reach nothing at all. A
  grant row of `(none)` forbids it every scope outside its own package **and**
  every sibling child scope inside it. A sibling is neither an ancestor nor a
  descendant of a zero-grant scope, so — unlike the shared parent package, which
  a package-scoped `forbidden` row cannot name from inside — it is a target the
  row can state, and an import of a **declared** sibling is refused rather than
  left to convention. Only a **zero-grant** row takes its siblings as targets: a
  scope with grants has a closure to complement, and naming siblings in its row
  would forbid intra-package edges this section permits. A sibling module over
  which this section declares no child scope is not stated in the row either;
  `tools/check_scope_ownership.py` requires such a module to carry a first-party
  import, so that importing it is reported wherever the chain through it leaves
  the package. The shared parent package stays the single name such a row cannot
  state, which no scope declaration could change. What makes two scopes granting
  disjoint dependencies able to share a zero-grant module is their **own** rows:
  each forbids everything its grants do not reach, so a dependency added to the
  shared module breaks the row of whichever consumer is not already granted it.
  `parallax.core.entity._layout` is the **grantable**
  case: a child scope may also be named as another scope's grant,
  which is how a consumer takes a narrow part of a package without taking what
  the rest of that package reaches. `parallax.core.entity._expressions` is the
  narrowing case within one package: query authoring reaches no model, so the
  values a developer composes must reach no model formation and no whole-model
  semantic view, and the row is what proves it rather than the module docstring
  alone. All are generated as ordinary contract
  sources, and none is a new supported import path. Because
  import-linter's `forbidden` contracts are package-scoped on both sides, a
  child is emitted as a contract **source**, and as a forbidden target only in
  a *sibling's* zero-grant row: naming it as a forbidden target of its own
  parent would overlap the parent's source package and be skipped, and naming
  it in any other scope's row would only restate what the parent's own entry
  already forbids for every descendant. When a child has an additive grant,
  the generator keeps the
  parent's forbidden row unchanged and emits one wildcarded `ignore_imports`
  entry for each exact child-to-direct-grant edge. A grant naming a scope inside
  the parent's own package is not one: a row can neither forbid nor except what
  sits inside its source, and whatever that sibling reaches further is already
  reported from the sibling itself. Ignoring that first hop also
  withdraws import-linter's indirect chains through it; no transitive grant
  receives a second exception. `unmatched_ignore_imports_alerting="error"`
  ensures an exception cannot outlive the import it describes. The handle
  scope declares no `m-pk-gen` grant: nothing
  under `parallax.snapshot.handle` imports primary-key generation, so the
  generated complement forbids it. The unused direct `m-navigate` grant is
  retained on purpose — navigation stays reachable through `m-snapshot-read`
  → `m-deep-fetch` → `m-navigate`, so removing it would forbid nothing while
  contradicting the deliberate edge described above.
- **Boundaries a scope must not reach.** A forbidden row is the complement of a
  closure, so a scope is never forbidden what its own grants reach transitively.
  A scope that exists in order to stay clear of some boundary must therefore be
  granted narrowly enough that the boundary falls **outside** its closure; there
  is no exception mechanism that puts a reachable target back into a row.
  `parallax.snapshot.handle._preflight` is the case in point: the seam resolves
  a target and validates a query before any I/O, so it must reach no
  Database Port, and the `parallax.core.entity` package reaches one through
  `parallax.core._formation_profile` → `m-opt-lock` → `m-unit-work` →
  `m-db-port`. Its grants are therefore `m-metamodel`, `m-predicate` and
  `m-object-query` — the canonical query value plus what resolves and validates
  it — none of which reaches the Entity frontend, and the ordinary generated row
  forbids `parallax.core.entity` outright along with `m-db-port`, `m-opt-lock`,
  `m-unit-work` and `parallax.core._formation_profile`, with indirect chains
  reported. `_preflight` naming `parallax.core.entity._model` therefore breaks
  the gate twice over: on the frontend package it may not name at all, and on
  `_model`'s own edge to `parallax.core._formation_profile`.
  Granting a child scope instead omits that child's ancestors from the row,
  because a forbidden entry naming the ancestor package would also forbid the
  granted child inside it. Only the ancestor's **name** is given up: what the
  rest of that package reaches stays forbidden and is reported as an indirect
  chain, which is why `parallax.snapshot.materialize`, granted
  `parallax.core.entity._layout`, still has `parallax.core._formation_profile`
  in its own row.
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
  check, which runs in `just python-check-scope-ownership`. The same tool adds
  the file-level requirement no scope table can state: inside a
  package holding a scope granted `(none)`, every module must either resolve to
  a scope that row names — the zero-grant scope itself, one of its declared
  siblings, or any scope declared beneath them, since a forbidden target is
  package-scoped and covers its whole subtree — or carry a first-party import,
  so that importing it is reported wherever the chain through it leaves the
  package. A module that is neither is refused. The rule is derived
  from the declared scopes rather than written against one package; the
  package's own interface module is outside it, because no declaration could
  bring it inside a row that cannot name its own ancestor. The same tool also
  carries the other half of the **isolated** scope rule: a forbidden row may not
  name a module inside its own source package, so the tool parses the files of an
  isolated scope's ancestors — resolving relative imports, and reading an
  imported name as a possible submodule — and refuses any import reaching that
  scope in any spelling. The **sealed** scope rule is the same overlap read the
  other way, and is carried the same way: the tool parses a sealed scope's own
  files and refuses every import landing inside its parent package that no
  granted scope covers, so the grants stated for it are complete rather than
  complete only outside that package. `from <parent> import <sibling>` is read
  as one reach at the sibling rather than at the parent alone, so a grant holds
  in every spelling of the import it permits, exactly as a refusal does.
- **Scopes sharing one artifact.** Every behavioral module in `parallax-core`
  is its own submodule; the generated forbidden contracts operate at
  submodule granularity, so co-location in one wheel cannot legalize a
  forbidden edge. Cross-package contracts permit the production artifact edges
  `descriptor → core`, `snapshot → core`, and `postgres → core` only.
  Consequently core cannot import descriptor, Snapshot, or Postgres;
  descriptor cannot import Snapshot or Postgres; and Snapshot and Postgres
  cannot import one another or descriptor. The development-only conformance
  family may import every artifact it harnesses.
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
| `parallax-core` (the common runtime) | production | all `parallax.core.*` scopes of §7 (behavioral modules, Entity/Object Query frontend, driver-free postgres dialect strategy) | `pydantic` | (none) | `parallax.core`: the `Entity`/`TxTemporal`/`Bitemporal`/`ValueObject` bases, `Attr`, `Rel`, `attr`, `rel`, `index`, `desc`, `asc`, `Int32`, `Float32`, `MAX`, `Sequence`, the cardinality, persistence, inheritance role and strategy values, `DomainModel`, the Object Query authoring vocabulary — `ObjectQuery`, `AttributeExpr`, `RelationshipPath`, `Predicate`, `AllPredicate`, `SortKey` — `LATEST`, `VALID_TIME`, `TX_TIME`, `Pin`, `Edge`, and its documented errors; `parallax.core.wire`: `WireValue`, `WireDecodingReason`, `WireDecodingError`, `WireEncodingError`, `loads`, `decode_wire`, `decode_canonical_wire`, and `encode_wire`; `parallax.core.sql_gen`: `LoweredStatement` and `SqlGenError`; `parallax.core.execution_lifecycle`: the Provider/Handler protocols, root and event values, outcomes and diagnostics, lifecycle errors, `FanoutLifecycleProvider`, `LoggingLifecycleProvider`, and `LifecycleLogDetail` |
| `parallax-descriptor` (descriptor interchange) | production, optional | `parallax.descriptor` (`m-descriptor` plus its private Hub orchestration) | `pyyaml`, `jsonschema` | `parallax-core` | `parallax.descriptor`: `domain_model_from_document`, `domain_model_from_json`, `domain_model_from_yaml`, `export_document`, `export_json`, `export_yaml`, `validate_inheritance_families`, `DescriptorError`, `DescriptorSyntaxError`, `DescriptorSchemaError`, `DescriptorValueError`, `DescriptorSchemaViolation`, `DescriptorValueViolation`, `DescriptorExportError` |
| `parallax-snapshot` (snapshot lifecycle extension) | production | `parallax.snapshot.*` (`materialize`, `handle`) | (none beyond core) | `parallax-core` | `parallax.snapshot`: `connect()`, `Snapshot[T]`, `CheckedSnapshot[T]`, `WireEntity`, `InvalidData[T]`, `StoredDataIssue`, `MISSING_STORED_VALUE`, `ObjectKey`, `InvalidDataError`, `NoResultFound`, `TooManyResultsFound`, `is_view_loaded`, `view`, `pin_of`, `edge_of`, `UnloadedRelationshipError`, `DeferredFeatureError`, `SnapshotConnectionError`, `SnapshotDecodingError`, `SnapshotMaterializationError`, `SnapshotInspectionError`, `TransactionOwnershipError`, `QueryTargetError`, `KeyedWriteValueError`, `KEYED_WRITE_VALUE_CODES`, `WriteEvidenceError`, `WriteEvidenceErrorCode`, `WRITE_EVIDENCE_CODES`, `WriteInstructionError` |
| `parallax-postgres` (Postgres database adapter) | production | `parallax.postgres.*` (concrete port over psycopg) | `psycopg[binary]` (sole declarer) | `parallax-core` | `parallax.postgres`: `PostgresAdapter`, `isolation_spelling` |
| `parallax-conformance` | development-only | `parallax.conformance.*` (CLI, case format, corpus loading, provider harness) | `testcontainers`, `jsonschema` | `parallax-core`, `parallax-descriptor`, `parallax-snapshot`, `parallax-postgres` | `parallax-conformance` console script (`describe` / `compile` / `run`) |

- **Common runtime manifest proof.** `parallax-core`'s manifest declares only
  `pydantic`; the clean-install check installs it alone and proves
  `parallax-descriptor`, `pyyaml`, `jsonschema`, `psycopg`,
  `parallax.snapshot`, testcontainers, and conformance modules are absent from
  both the installed distribution list and the import space.
- **Descriptor manifest and schema-resource proof.** `parallax-descriptor`
  directly declares `parallax-core`, `pyyaml`, and `jsonschema`, so every
  installed Descriptor Frontend can execute all three ingestion phases without
  an optional-import failure branch. The language-neutral
  `core/schemas/metamodel.schema.json` remains authoritative; the wheel and
  sdist embed a byte-for-byte package-data copy loaded through
  `importlib.resources`. Build and artifact checks compare the packaged
  resource with the authoritative source and fail on drift. Runtime code never
  searches repository-relative paths.
- **Lifecycle extension manifest proof.** `parallax-snapshot` depends only on
  `parallax-core`; the clean-install check proves no sibling lifecycle
  artifact, Descriptor Frontend, descriptor parser, schema validator, or
  concrete driver is present.
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
- **Clean-install and runtime-load checks.** Four uv-venv fixtures
  (`uv run pytest tests/distribution/test_clean_install.py`): core alone; core + descriptor; core +
  snapshot; core + snapshot + postgres. Each inspects installed distributions
  and import-probes to prove unselected interchange, lifecycle, adapter,
  driver, conformance, benchmark, and container dependencies are absent from
  the installed and loaded production graph. The descriptor fixture also
  imports its packaged schema and exercises one JSON and one YAML round trip.

## 9. Conditional capability decisions

`m-storage-layout` is claimed, so the Relational Document Layout decision below
is recorded. Every other conditional subsection of the template is deleted from
this completed spec: process caches, cross-process coherence, aggregation,
additional dialects, and benchmarks are all outside `slice-snapshot-1` and
recorded as deferred in §1.

### Relational Document Layout

**Support.** The Python target supports the root-owned `Document` Storage
Layout. The authoring spelling is the class-header keyword `layout=Document()`
(§2, *Class headers*): `column=` is optional and defaults to `payload`, the
frontend resolves the name during normalization, and the canonical descriptor
always carries the resolved name at `layout.document.column`. `Columns` has no
spelling — omitting `layout=` is what selects it — and there is no path
authoring form.

**Member Placement exposure.** `parallax.core.storage_layout` exports
`MemberPlacement` with `DirectColumn` and `DocumentPath`, and every consumer —
SQL lowering, write lowering, materialization, provisioning, and fixture
loading — locates a logical member through `TableLayout.placement(...)` or a
`PositionBranch.placements` entry (§2, *Storage Layout formation and immutable
facet*). No consumer re-derives residency, and no Rule Set calls placement.

**Database support.** PostgreSQL is the claimed dialect, so the production
adapter binds and reads the `jsonb` Structured Column. MariaDB remains deferred
here and is proven by the language-neutral reference and conformance paths, as
for every other MariaDB behavior (§1).

**Partitioned locking reads.** When heterogeneous TPH variants interpret a
Document Path with incompatible types, SQL lowering emits the core contract's
tag-disjoint derived identity relation, joins it back to the shared base Table
on the complete primary key, and applies PostgreSQL `for share` to that base
alias in one outer SELECT. This preserves one statement and one round trip while
ensuring no variant-specific cast observes a sibling row and the returned base
rows receive the transaction's shared lock.

## 10. Mandatory quality toolchain

| Quality concern | Tool and version policy | Configuration path(s) | Local command | Blocking CI command/job | Threshold, exclusions, and enforcement policy |
|---|---|---|---|---|---|
| Dependency directions within and across artifacts | import-linter (pinned in `uv.lock`) + `check_dag_sync.py` + `check_scope_ownership.py` | `languages/python/pyproject.toml` `[tool.importlinter]`; `languages/python/tools/check_dag_sync.py`; `languages/python/tools/check_scope_ownership.py` | `just python-check-imports`, whose prerequisites are `python-check-dag-sync` and `python-check-scope-ownership` | `python-check-dbfree` job, same recipe | any production-scope import outside the DAG's transitive closure fails — the forbidden-edge complement generated from `modules.md` rejects illegal non-edges, not just wrong directions, with only the §7 conformance-family importer exemption; generated-contract drift fails, as does any disagreement among the three declarations of the support-scope graph — `check_dag_sync.py`'s support-scope table, the §7 prose rows, and the §7 `support-scope-graph` block — including the case where two of the three are edited consistently and the third is left stale, and the case where one support scope is declared by two prose rows; a child scope §7 marks isolated or sealed that `check_dag_sync.py`'s corresponding set does not name, the reverse, a mark naming a parent `check_dag_sync.CHILD_SCOPE_PARENT` does not declare for that scope, or the same mark declared twice for one scope, fails the same way; a production source file owned by no §7 scope (and so covered by no contract), owned by undeclared overlapping scopes, importing an isolated scope from inside that scope's own ancestors, reaching — from inside a sealed scope — a module of its own parent package no granted scope covers, or covered by a stale exemption also fails |
| Unit tests | pytest (pinned) | `languages/python/pyproject.toml` `[tool.pytest.ini_options]` | `uv run pytest tests/unit` | `python-check-dbfree` job | the internal-behavior surface proves seams, diagnostics, and failure modes with no container or socket I/O; Storage Layout tests pin Rule Set ownership, exact immutable layouts/views, all six tiers, applicability, effective nullability, physical keys, alias de-duplication, unknown lookups, and bounded allocation; any failure blocks |
| Code coverage | coverage.py via pytest-cov, branch mode + diff-cover (both pinned) | `[tool.coverage]` in `languages/python/pyproject.toml` | `just python-test-dbfree` then `just python-coverage-diff` | CPython 3.14 `python-check-dbfree` leg with `--cov-fail-under=95` plus the same diff-cover gate | **95% branch-mode minimum** overall, re-baselined against the measured database-free selection rather than carried across from a narrower one; diff-cover requires **100%** of changed lines vs the merge-base with `main`, making the no-new-uncovered-code policy executable, and the measurement is the database-free class alone, so a database-backed test cannot satisfy it; no generated/vendor code exists to exclude; conformance CLI included |
| Linting | ruff (pinned) | `[tool.ruff]` in `languages/python/pyproject.toml` | `uv run ruff check` | `python-check-dbfree` job | rule sets E, F, W, I, UP, B, SIM, RUF; `# noqa` requires rule code + one-line justification |
| Deterministic formatter check | ruff format (pinned) | `[tool.ruff.format]` | check: `uv run ruff format --check`; write: `uv run ruff format` | `python-check-dbfree` job (`--check` only) | CI checks without rewriting |
| Strict static typing | Pyright, strict mode, pinned version | `languages/python/pyrightconfig.json` | `uv run pyright` | `python-check-dbfree` job | strict across production and tests; a `# pyright: ignore[<rule>]` or `# type: ignore[<code>]` carries its specific code and a one-line justification at the site, as `# noqa` does; `reportUnnecessaryTypeIgnoreComment` (set in `pyrightconfig.json`) reports any idle suppression as an error, so every suppression is load-bearing — removing it fails the gate — and each is a reviewed diff line rather than a spec-maintained list |
| Import-cycle detection | import-linter generated forbidden contracts | `[tool.importlinter]` | `uv run lint-imports` | `python-check-dbfree` job | covers all production source scopes; the permitted closure is acyclic, so any cycle necessarily crosses a forbidden edge and fails |
| Dead code and unused exports | vulture + griffe public-API snapshot test | `[tool.vulture]`; `languages/python/tests/api/` | `uv run vulture && uv run pytest tests/api/test_public_api.py` | `python-check-dbfree` job | limitation recorded: Python tooling cannot prove an export unused; compensating check is the API-surface snapshot diff, making every public-surface change a reviewed diff |
| Built-artifact and public-export health | `uv build` + twine check + wheel-content pytest | `languages/python/tests/distribution/` | `uv build && uv run twine check dist/* && uv run pytest tests/distribution/test_wheels.py` | `python-check-dbfree` job | wheels contain no test or conformance modules, include `py.typed`, declare correct entry points; `parallax-descriptor` contains the authoritative-schema copy and its bytes match `core/schemas/metamodel.schema.json` |
| Clean-install production smoke tests | uv-venv fixtures | `languages/python/tests/distribution/` | `uv run pytest tests/distribution/test_clean_install.py` | `python-check-dbfree` job | exercises all four §8 selective topologies in clean environments; presence of any unselected artifact fails |
| Supported language/runtime versions | CPython; `requires-python >= 3.13` | each distribution's `pyproject.toml` | (local dev on any supported minor) | CI matrix: 3.14 full gate; 3.13 database-free tests without coverage | support the latest minor + one prior minor; the latest minor owns every version-independent verdict and the full database and cost gates, while the prior minor proves database-free runtime compatibility; admitting a new latest minor and raising the floor are reviewed spec changes |
| Dependency and supply-chain audit | committed `uv.lock` + `uv lock --check` + pip-audit + scheduled `uv lock --upgrade` refresh | `languages/python/uv.lock` | `uv lock --check && uv run pip-audit` | `python-check-dbfree` job on every PR, plus a monthly scheduled CI job opening a `uv lock --upgrade` refresh PR | high-severity findings block; exceptions carry owner + expiry inline; lockfile drift fails; freshness: the monthly upgrade PR is human-reviewed like any change and may not be merged red |
| Compatibility Conformance Suite | pytest conformance runner + jsonschema envelope validation | `languages/python/tests/compatibility/` | `uv run pytest -m compile_sweep` (Docker-free) and `uv run pytest tests/compatibility/test_run_sweep.py` (`pg-full`) | `python-check-dbfree` (compile sweep) + `python-check-db` (run sweep) | selection = active slice ∩ capability tags; every envelope validates against `conformance-adapter.schema.json` |
| API Conformance Suite and Usage Guide | pytest + guide generator | `languages/python/tests/api/`; `languages/python/docs/usage-guide.md` | `uv run pytest tests/api && uv run gen-usage-guide --check` | `python-check-dbfree` (partition, no-drift guards, guide drift) + `python-check-db` (story and boundary runs) | coverage partition exact (exercised ∪ reasoned-skips = slice; no stale IDs, no empty reasons); query, descriptor, and database-free copy-to-row no-drift guards green; guide drift fails |
| Database-backed verification | testcontainers Postgres profiles | §6 profile definitions | `uv run pytest -m db` | `python-check-db` job | required profiles `pg-full`, provider contract, adapter smoke; every skipped check is reported with a reason in the session summary; silent skips are forbidden and any CI skip fails |

- **Storage Layout contract verification.** Before the target advertises the
  expanded claim, `just core-check-module-graph`, `just core-check-slice-profiles`,
  both canonical slice inspections, and
  `just core-show-language-spec languages/python/spec/python.md` prove the
  catalog/manifest/claim boundary; focused unit tests prove the Rule Set,
  compiler, facet, and profile wiring; and compile/conformance intersections
  selected by `--parallax-tags m-storage-layout` prove every physical consumer.
  The reference-harness structural layout tests and corpus layout baseline run
  independently and no Python test satisfies them by importing or serializing
  production layout objects.
- **Scheduling classes.** `dbfree`, `db`, and `cost`, the §6 partition every
  collected item carries exactly one of.
- **Aggregate `dbfree` command.** `just python-check-dbfree` — one local command
  and one blocking CI job composing every database-free row above on CPython
  3.14 (imports/DAG, the `dbfree` test class + coverage, ruff check + format
  check, Pyright strict, vulture + API surface, database-access guard, build +
  distribution metadata, clean-install checks, supply-chain audit, and the
  Docker-free `compile-sweep`). The same job's CPython 3.13 leg runs the
  `dbfree` test class with coverage disabled to prove prior-minor compatibility.
- **Aggregate `db` command.** `just python-check-db` — one local command and one
  blocking CI job composing every database-backed row above (`pg-full`, provider
  contract, adapter smoke, API conformance + Usage Guide story runs).
- **Aggregate `cost` command.** `just python-check-cost` — one command and one
  blocking CI job composing the `cost` test class and the guard confining the
  memory instruments to it. It is the one aggregate outside `just check` and
  inside `just check-all` (§6, *Commands and skip reporting*): a retained-byte
  reading is machine-relative, so the fixed CI runner owns it rather than a
  developer's local merge gate, and CI gates it on every change.
- **Report-only measurement evidence.** Retained-memory and timing evidence for
  published instance state is a `report` — `just python-report-instance-state`,
  reading `languages/python/docs/instance-state-baseline.md` — and belongs to no
  aggregate and to no CI job. Its siblings are the same: the streamed delivery's
  working set is `just python-report-stream-overhead`, reading
  `languages/python/docs/stream-baseline.md`. There is deliberately **no timing gate anywhere in
  this target**: a total in bytes and an elapsed time are machine- and
  interpreter-relative, and every CI job runs a floating runner label, so a
  threshold over either would fail for reasons unrelated to the change under it.
  What is gated instead is the SHAPE of what is retained, in the `cost` class
  above. The two comparisons the measurement contract does name — an aggregate
  reduction against its target, and a representative operation against its
  threshold — are computed by the report and DISPLAYED as an escalation block, so
  each returns to a human decision by being emitted rather than by being noticed.
  Neither reaches the report's exit code, which is what keeps it non-blocking
  under `core/spec/language-testing.md` §2: it exits non-zero on exactly one
  thing, a matrix cell it has no reading for, which says there is nothing to read
  rather than that what was read is wrong.
- **Complete verification command.** `just python-check` — all three class
  aggregates, ending with a summary block listing every check as run, failed, or
  skipped-with-reason.

## Completion check

- Every surface this document describes exists in the synchronized core
  specifications, schemas, compatibility corpus, dialects, and every claiming
  frontend, so nothing here is ahead of the shared contract.
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
