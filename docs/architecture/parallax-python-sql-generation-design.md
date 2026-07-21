# Python SQL generation internal split

**Status:** Accepted

**Accepted:** 2026-07-20

**Review remediated:** 2026-07-20

**Scope:** `languages/python/packages/parallax-core/src/parallax/core/sql_gen`

## Purpose

Split the 1,553-line implementation of the Python SQL generation module into
cohesive private modules while preserving its depth, observable behavior, and
existing `m-sql` enforcement scope.

This design refines Candidate 05 from
[parallax-python-codebase-improvements.md](parallax-python-codebase-improvements.md)
and the corresponding visual architecture review. It is a source-locality
refactor with a deliberate deepening of one internal runtime interface. It does
not change the language-neutral `m-sql` contract, the specified Python
developer API, deployable artifact topology, or behavioral dependency DAG.

## Vocabulary

- **SQL generation module** means the deep module at the supported
  `parallax.core.sql_gen` seam.
- **Read compiler** means the `compile_read` pipeline within that module.
- **Compiled SQL statement** means the SQL-generation `Statement` value. This
  avoids confusing it with the Python glossary's developer-authored **Find
  Statement**.

## Settled constraints

- Preserve `parallax.core.sql_gen` as the sole supported module interface and
  deepen it as part of this cleanup.
- Do not preserve `parallax.core.sql_gen.compile` as a compatibility import.
  There are no external users, and implementation paths must not constrain the
  clean target topology.
- Replace the separately coordinated `compile_read`, `family_variant_plan`,
  `apply_family_variant`, and `read_narrow_to` results with one `CompiledRead`
  value returned by `compile_read`.
- Make `FamilyVariantPlan` and the three standalone read-consumption helpers
  private implementation details.
- Add an explicit interface check for the deliberately reduced
  `parallax.core.sql_gen` seam so it cannot drift during extraction.
- Preserve exact SQL, bind ordering, error types and asserted messages, result
  values, refusals, deferred-feature behavior, and all current caller behavior.
- Apart from the settled SQL-generation interface deepening, do not combine the
  split with an `m-sql` or Python specification change, further interface
  redesign, new capability, or semantic cleanup. Record any such opportunity
  as separate work.
- Keep the existing `m-sql` enforcement scope and the `parallax-core`
  deployable artifact. Do not create a new public seam or adapter.
- Do not preserve implementation metadata such as private definition paths,
  `__module__`, or byte-identical pickle payloads. Verify only supported value
  behavior and ordinary serialization or introspection needed by repository
  callers.

## Behavioral authority and compatibility baseline

Apart from the deliberate package-interface deepening, this is a strictly
behavior-preserving refactor. The completed Python and core specifications,
schemas, and compatibility corpus are authoritative. Current consumers and
implementation behavior may characterize behavior only where they conform to
those sources: given the same operation, metamodel, dialect, target, and
options, the refactored implementation must produce the same conforming
compiled SQL statement or the same failure.

If characterization exposes a divergence between the current implementation or
consumer behavior and an authoritative specification, schema, or corpus case,
stop this refactor at a green phase. Resolve the divergence separately as a
specification, corpus, or implementation defect before continuing; do not
preserve it as compatibility behavior in this source-topology change.

In particular, the split must not change canonical alias assignment, bind
ordering, projection order, clause order, inheritance-family ordering, Family
Variant materialization, navigation correlation, value-object traversal,
read-lock placement, or unaliased write-predicate lowering.

## Target package

```text
parallax/core/sql_gen/
  __init__.py
  _compile.py
  _context.py
  _predicate.py
  _inheritance.py
  _navigation.py
```

### Ownership

| Source module | Ownership |
|---|---|
| `sql_gen.__init__` | The supported, deliberately reduced SQL generation interface. |
| `_compile` | Read and write-predicate orchestration, ordinary-read projection, clause-tail assembly, canonical normalization, and assembly of compiled SQL statements and `CompiledRead` values. It peels result directives and selects ordinary versus inheritance-family lowering. |
| `_context` | Shared mutable lowering state and its operations only: metamodel and dialect access, alias allocation, and ordered bind accumulation. It owns no projection, clause-tail, normalization, or result-transformation policy. |
| `_predicate` | The sole recursive operation dispatcher, parameterized by an immutable entity or value-object-element resolution scope, including scalar, boolean, string, membership, nested value-object, and value-object-array predicate lowering. |
| `_inheritance` | Table-per-hierarchy and table-per-concrete-subtype plans, effective-position and stable-superset resolution, inheritance projection policy, tag guards, and the private Family Variant row-transform value. |
| `_navigation` | Relationship resolution and monomorphic or polymorphic correlated-hop plans. |

The underscored modules are private implementation, absent from
`sql_gen.__all__`, and are not independent test surfaces.

### Intended private direction

```text
_compile -> _context, _predicate, _inheritance
_predicate -> _context, _inheritance, _navigation
_navigation -> _context, _inheritance
_inheritance -> _context
```

The graph is acyclic. `_predicate` has one recursive entry point that accepts the
operation, shared lowering context, and an immutable `_ResolutionScope` sum
value. An entity scope carries the active entity and alias plus aliased-versus-
unaliased column resolution; an element scope carries the active value-object
container and unnested element alias. Boolean recursion preserves the current
scope. Navigation plans produce a child entity scope, while scoped
`nestedExists` plans produce an element scope, and both return the inner
operation to the same dispatcher. The element scope admits only the
`elementPredicate` vocabulary and preserves element-relative paths; an invalid
node raises the existing `SqlGenError`. There is no second element dispatcher,
and element resolution state is not added to `_context`.

**Correction (2026-07-21, post-acceptance).** Three details of the paragraph
above are design intent that the implementation departed from; they are recorded
here rather than edited in place, so this section keeps reading as the accepted
design.

- The shipped type is `ResolutionScope`, not `_ResolutionScope`. A private
  *module* carries the privacy in this codebase and its published names are not
  underscore-prefixed — pyright's `reportPrivateUsage` fails the static gate on a
  cross-module underscore import. The naming convention is right; the reason
  first recorded here was not. The scope types have exactly one cross-module
  importer, `_compile` (`_compile.py:67`, `EntityScope as _EntityScope`).
  `_navigation` and `_inheritance` never import them and could not: both sit
  *below* `_predicate` in the enforced layer order and take the narrowed
  `ColumnScope` / `PlanScope` protocols from `_context` instead. The same naming
  rule applies to `EntityScope` and `ElementScope`, the two arms of the sum.
- The dispatcher takes **two** arguments, not three: `lower_predicate(op, scope)`.
  The scope *holds* the shared lowering context rather than travelling beside it,
  because the alternatives were to duplicate the metamodel and dialect onto every
  scope (two sources of truth, and a scope pairable with a foreign context) or to
  thread the context through roughly ninety lowering sites and both plan-only
  capability protocols. Every bind site therefore spells `scope.ctx.bind(...)`,
  which keeps the bind ordering this refactor exists to protect greppable in one
  expression.
- Neither a navigation plan nor a scoped `nestedExists` *produces* a resolution
  scope; `_predicate` constructs both. `_navigation.open_branch` returns an
  `OpenBranch` carrying the branch's entity and alias, and `_predicate` builds the
  child scope from that data (`_predicate.py:437-438`,
  `scope.child(opened.entity, opened.alias)`). A scoped `nestedExists` has no plan
  at all: `_lower_nested_exists` resolves the path and constructs the
  `ElementScope` inline (`_predicate.py:633`). Plans carry the *inputs*; scope
  construction belongs to the dispatcher, which is precisely what keeps
  `_navigation` and `_inheritance` free of any scope type. The paragraph's
  following claim — that both hand the inner operation back to the same
  dispatcher — does hold.

The paragraph's remaining claims were each re-checked against the shipped code
and hold: one recursive entry point (`lower_predicate`); an entity scope carrying
the active entity, its alias, and aliased-versus-unaliased column resolution
(`EntityScope`, `_predicate.py:145-162`); an element scope carrying the active
value-object container and the unnested element alias (`ElementScope`,
`_predicate.py:234-250`); boolean recursion preserving the current scope
(`_predicate.py:287-294`); an element scope admitting only the `elementPredicate`
vocabulary and raising the existing `SqlGenError` on anything else
(`_predicate.py:300-304`); no second element dispatcher; and no element
resolution state on `_context` (`Ctx.__slots__` is exactly
`_next_alias_index`, `binds`, `dialect`, `meta`).

Navigation and inheritance do not call back into `_predicate`; instead they
return immutable private plans containing the resolved tables, positions,
correlations, tag guards, branches, resolution-scope inputs, and any inner
operation. `_predicate` recursively lowers the returned inner operation through
its one entry point. Top-level inheritance reads return family-read plans that
`_compile` assembles through the same predicate renderer.

This plan-first design keeps policy local to its concern while avoiding a
callback re-entry interface, handler registry, visitor framework, or
hypothetical adapter.

### Lowering-context invariants

One private context owns each compiled SQL statement's mutable lowering state.
Immutable entity and element resolution scopes select how a predicate reference
is interpreted without changing or duplicating that state:

- nested resolution scopes share the same bind list and alias counter by
  identity;
- aliases advance once in depth-first source order across nested and sibling
  correlated subqueries;
- each independent table-per-concrete-subtype union branch starts a fresh
  alias sequence at `t0` and contributes binds in canonical branch order;
- projection and dialect binds precede predicate binds;
- user or inner-predicate binds precede framework-added tag binds;
- limit binds are last; and
- unaliased write predicates reuse the same predicate vocabulary without
  forking its lowering rules.

## Supported interface

The intended package interface is deliberately smaller than the current
nine-name surface:

```python
@dataclass(frozen=True, slots=True)
class _RowTransform:
    kind: Literal["identity", "tph", "tpcs"]
    column: str | None = None
    tag_pairs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledRead:
    statement: Statement
    narrow_to: tuple[str, ...] | None
    _row_transform: _RowTransform

    def transform_row(self, row: Mapping[str, object]) -> dict[str, object]: ...


def compile_read(...) -> CompiledRead: ...


@dataclass(frozen=True, slots=True)
class CompiledPredicate:
    sql: str
    binds: tuple[object, ...]


def compile_write_predicate(...) -> CompiledPredicate: ...
```

`CompiledRead.statement` is the canonical SQL and ordered binds.
`CompiledRead.narrow_to` carries the authored top-level root narrowing needed
by Snapshot materialization. Its private `_row_transform` field is a frozen,
slotted, tagged sum value rather than a closure or mutable mapping. The three
valid forms are:

- `identity`, with no column and no tag pairs, returns an ordinary `dict` copy;
- `tph`, with the projected raw tag column and canonically ordered immutable
  `(tagValue, concreteName)` pairs, removes that column and writes the resolved
  name to `familyVariant`; and
- `tpcs`, with the projected `family_variant` literal column and no tag pairs,
  removes that column and renames its value to `familyVariant`.

`CompiledRead.transform_row` delegates to that value one row at a time and
preserves the current missing-column and unknown-tag failures. The transform
participates in `CompiledRead` value equality. `CompiledRead.__repr__` is an
explicit stable value representation containing `statement`, `narrow_to`, and
the transform's semantic `kind`, `column`, and `tag_pairs`; it contains no
function identity or mapping-address representation. Exact repr tests cover all
three forms. Same-version `pickle.dumps` / `pickle.loads` round trips must
preserve equality, repr, and `transform_row` behavior for identity, TPH, and
TPCS compiled reads; byte-identical payloads and cross-version private paths
remain unsupported.

The transformation remains row-at-a-time. The conformance caller can first
convert driver-native values to wire values, while Snapshot execution can
transform raw database rows directly. SQL generation remains pure and I/O-free;
it does not acquire the database port, execute a statement, or materialize
Snapshot nodes.

`FamilyVariantPlan`, `family_variant_plan`, `apply_family_variant`, and
`read_narrow_to` become private implementation details of compilation and the
`CompiledRead` value.

`CompiledPredicate` names the result of unaliased write-predicate lowering. It
is deliberately distinct from `Statement`: its `sql` is a bare predicate
fragment without a `where` keyword or target-table alias, not a complete SQL
statement.

The supported `parallax.core.sql_gen` interface contains exactly six names:

- `CompiledPredicate`;
- `CompiledRead`;
- `SqlGenError`;
- `Statement`;
- `compile_read`; and
- `compile_write_predicate`.

`ResultForm` becomes a private typing detail; the two accepted literal values
remain part of `compile_read`'s typed parameter contract.

## Test design

Replace the 998-line `tests/unit/test_sql_gen.py` with behavior-owned suites:

| Test module | Observable behavior |
|---|---|
| `test_sql_gen_compile.py` | Ordinary reads, projection and result shaping, locks, compiled values, normalization, general refusals, and the supported interface. |
| `test_sql_gen_inheritance.py` | TPH/TPCS projections, tag guards, canonical branch ordering, narrowing, and Family Variant row transformation through `CompiledRead`. |
| `test_sql_gen_navigation.py` | Monomorphic and polymorphic correlated hops, multi-hop recursion, negation, aliases, and bind ordering. |
| `test_sql_gen_value_objects.py` | Scalar extraction, nested traversal, any-element and same-element semantics, guards, and malformed-path refusals. |
| `test_sql_gen_write_predicate.py` | Unaliased predicate fragments and `CompiledPredicate` behavior. |

Every suite imports only `parallax.core.sql_gen`. No private context, plan, or
lowering function becomes a test seam. Existing upstream canonicalization and
consumer suites remain in place.

Before moving implementation, add interface-level characterization for every
state invariant. The matrix must include navigation nested inside narrowing,
multi-hop aliases, sibling subquery aliases, user-before-tag binds, and:

- an ordinary read with a dialect-produced projection bind, a predicate bind,
  and a limit bind, asserting that exact bind order;
- a multi-branch TPCS union in which every branch contains a nested subquery,
  asserting `t0`/nested-alias restart inside each branch and deterministic
  branch-order bind concatenation; and
- equality, exact repr, identity/TPH/TPCS `transform_row` behavior, and pickle
  round trips for `CompiledRead`'s immutable private row-transform value.

Add a package-interface snapshot that asserts exactly the six supported
exports. Every characterization crosses `parallax.core.sql_gen`; none imports a
private module or inspects lowering state.

## Migration phases

Every phase must leave the tree green and be independently reviewable.

1. **Characterize and split tests.** Add the missing recursion/state cases and
   reorganize the monolithic SQL-generation suite without moving production
   behavior.
2. **Deepen the supported interface.** Introduce `CompiledRead` and
   `CompiledPredicate`, update every caller, reduce `sql_gen.__all__`, make
   `ResultForm` and Family Variant machinery private, and rename `compile.py`
   to `_compile.py`.
3. **Extract the context.** Move only shared alias/bind state and its operations
   into `_context.py`. Keep ordinary projection, clause-tail assembly, and
   normalization in `_compile.py`; inheritance projection policy remains for
   Phase 4. Preserve every state invariant.
4. **Extract inheritance planning.** Move TPH/TPCS position, projection,
   branch, tag, and Family Variant behavior into plan-only `_inheritance.py`.
5. **Extract recursive lowering.** Move navigation planning to
   `_navigation.py` and the sole recursive dispatcher to `_predicate.py`.
   Introduce the immutable entity-versus-element `_ResolutionScope` at that
   dispatcher seam and remove the second element-predicate dispatcher.
6. **Enforce and clean up.** Audit the resulting imports, add the private
   direction and package-back-import contracts, update stale implementation-path
   references, add the built-wheel layout assertion, and run final verification.
   The stale-reference audit explicitly covers comments and docstrings in
   `parallax.core.dialect`, `parallax.core.read_lock`,
   `parallax.core.op_algebra.validate`, `parallax.snapshot.materialize`, and
   `parallax.conformance.read_stories`; relevant SQL-generation, read-lock,
   materialization, and Snapshot-find tests; and
   `docs/architecture/parallax-snapshot-handle-package-design.md`. Preserve the
   intentional historical “Before” references in Candidate 05 of
   `parallax-python-codebase-improvements.md` and
   `parallax-python-architecture-review.html`.

## Enforcement

Keep the generated broad `parallax.core.sql_gen` forbidden-import contract as
the enforcement of the language-neutral `m-sql` dependency edges. All new
private modules remain descendants of that one enforcement scope.

Import Linter 2.13 cannot place `parallax.core.sql_gen` beside its descendants in
one layers contract: the modules have shared descendants. After extraction, add
the following two adjacent Python-specific contracts, with fully qualified
module names, outside the `check_dag_sync.py` generated markers:

```toml
# Additive private source-order enforcement; generated contracts remain the core behavioral-DAG authority.
[[tool.importlinter.contracts]]
name = "parallax.core.sql_gen private modules follow source order"
type = "layers"
layers = [
    "parallax.core.sql_gen._compile",
    "parallax.core.sql_gen._predicate",
    "parallax.core.sql_gen._navigation",
    "parallax.core.sql_gen._inheritance",
    "parallax.core.sql_gen._context",
]

[[tool.importlinter.contracts]]
name = "parallax.core.sql_gen private modules do not import the package seam"
type = "forbidden"
source_modules = [
    "parallax.core.sql_gen._compile",
    "parallax.core.sql_gen._predicate",
    "parallax.core.sql_gen._navigation",
    "parallax.core.sql_gen._inheritance",
    "parallax.core.sql_gen._context",
]
forbidden_modules = ["parallax.core.sql_gen"]
as_packages = false
```

The five-module layers contract rejects upward private imports; the adjacent
exact-module forbidden contract rejects a private module's direct or indirect
back-import to `sql_gen.__init__` without treating the package root and its
descendants as overlapping packages. Do not add the private modules to
`core/spec/modules.md`, `MODULE_SCOPE`, or the language-spec behavioral mapping.

## Verification

Run the narrowest affected SQL-generation and consumer suites after every
phase. Run the DAG-sync check, import-linter, and `just python-static` after
each structural phase.

Before completion, run from `languages/python`:

```text
uv run python tools/check_dag_sync.py
uv run lint-imports
just python-static
just python-verify
```

The final database-backed verification is mandatory because exact SQL and
result behavior must conform to the authoritative specifications and corpus as
well as the conforming compatibility baseline. The implementation handoff must
name every skipped database-backed lane and why; an unexplained skip does not
satisfy the ticket.

Also extend `tests/artifact/test_wheels.py` to require the supported
`sql_gen/__init__.py` and all five private implementation files in the
`parallax-core` wheel, and to forbid the retired `sql_gen/compile.py` path. A
cold import of `parallax.core.sql_gen` from the built artifact must succeed.

## Acceptance criteria

- `parallax.core.sql_gen` exposes exactly the six settled names, and no private
  plan or helper leaks through its interface.
- `compile_read` returns `CompiledRead`; all production and conformance callers
  use its `statement`, `narrow_to`, and `transform_row` behavior instead of
  independently coordinating Family Variant and narrowing helpers.
- `compile_write_predicate` returns `CompiledPredicate`, clearly representing
  an unaliased SQL fragment rather than a complete statement.
- `sql_gen/compile.py` is removed. The implementation has exactly the target
  private modules and the intended acyclic direction.
- Exact SQL, binds, row transformations, refusals, and error behavior remain
  unchanged across the corpus and consumer suites.
- Tests are split by observable behavior and import only the supported package
  interface; the characterization cases protect recursive alias/bind state.
- The broad generated `m-sql` contract still enforces the core behavioral DAG.
  The explicitly additive Python-specific layers and exact-module forbidden
  contracts enforce the private source direction and prevent package-seam
  back-imports.
- The built `parallax-core` wheel contains the complete private implementation,
  excludes `sql_gen/compile.py`, and cold-imports the supported interface.
- Full static and database-backed verification passes.

## Excluded

- No change to `core/spec/m-sql.md`, `core/spec/modules.md`, or the Python
  language specification.
- No new SQL capability, dialect behavior, projection form, normalization rule,
  or previously deferred lowering.
- No movement of SQL behavior into `m-op-algebra`, `m-inheritance`,
  `m-navigate`, `m-value-object`, a lifecycle extension, or a database adapter.
- No new deployable artifact, public implementation submodule, adapter,
  registry, visitor framework, or private test interface.
- No TypeScript or reference-harness implementation prior art.

## Domain-model and decision records

No glossary change is required. **Predicate**, **Inheritance Family**, **Family
Variant**, **Value Object**, and Python **Find Statement** already provide the
domain language; SQL generation, read compiler, and compiled SQL statement are
architecture or implementation terms rather than new Parallax domain concepts.

No ADR is required. This is a reversible internal source-topology decision that
preserves the normative semantics and does not meet the repository threshold
for a hard-to-reverse, surprising trade-off.

## Relevant decisions

- [ADR 0012 — In-transaction read locks apply to object finds, not aggregations](../adr/0012-in-transaction-read-locks-apply-to-object-finds-not-aggregations.md)
- [ADR 0014 — Set-based writes are readless; versioned entities materialize](../adr/0014-set-based-writes-are-readless-versioned-entities-materialize.md)
- [ADR 0016 — Reference harness is not an input to language implementations](../adr/0016-reference-harness-is-not-an-input-to-language-implementations.md)
- [ADR 0020 — Inheritance families are closed trees with explicit concrete writes](../adr/0020-inheritance-families-are-closed-trees-with-explicit-concrete-writes.md)
- [ADR 0022 — Deployable artifacts follow optional-dependency seams](../adr/0022-deployable-artifacts-follow-optional-dependency-seams.md)
