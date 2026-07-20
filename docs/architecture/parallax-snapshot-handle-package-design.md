# Snapshot handle package design

**Status:** Accepted

**Accepted:** 2026-07-19

**External review remediated:** 2026-07-19

**Scope:** `languages/python/packages/parallax-snapshot/src/parallax/snapshot/handle.py`

## Purpose

Convert the 2,723-line `parallax.snapshot.handle` module into a package whose
private modules own complete implementation concerns while preserving the
existing handle interface and the `parallax-snapshot` deployable artifact.

The handle remains the deep composition seam that legally sees both neutral
Unit of Work planning and SQL generation. This cleanup improves implementation
locality; it does not move behavior into `m-unit-work`, `m-sql`, or a concrete
database adapter, and it does not create a new public seam or deployable
artifact.

This design refines the selected direction in
[parallax-python-codebase-improvements.md](parallax-python-codebase-improvements.md).

## Settled constraints

- Preserve the import path `parallax.snapshot.handle`.
- Preserve the existing `parallax-snapshot` distribution, manifest, and
  dependency topology.
- Preserve the exact existing `parallax.snapshot.handle.__all__` throughout
  the cleanup. Interface reduction is separate work. The exact list is now a
  committed `parallax.snapshot.handle` entry in
  `languages/python/tests/api_surface/public_api.json`; that gate must pass in
  every migration phase.
- Preserve the specified `parallax.snapshot` exports: `connect`, `Snapshot`,
  `Execution`, `NoResultFound`, and `TooManyResultsFound`.
- Preserve the conformance-facing handle imports.
- Retire the non-public sibling path `parallax.snapshot.wrap`. Frozen-node
  wrapping becomes private handle implementation; there will be no permanent
  forwarding module.
- Keep Unit of Work coalescing in `m-unit-work`.
- Keep Snapshot results above shared fetch.
- Keep the Postgres adapter injected at the application or test composition
  root; `parallax-snapshot` must not depend on `parallax-postgres`.
- Do not use another language implementation or reference-harness internals as
  design input.
- Treat roughly 500–750 lines as an iterative locality target, not a reason to
  create shallow public modules.

## Compatibility inventory

The existing handle exports fall into three usage groups. All remain available
from `parallax.snapshot.handle` during this cleanup.

| Usage | Existing exports |
|---|---|
| Specified `parallax.snapshot` surface | `Execution`, `NoResultFound`, `Snapshot`, `TooManyResultsFound`, `connect` |
| Developer and conformance composition | `Database`, `Transaction`, `TransactionOptionConflictError`, `WriteLoweringError`, `find`, `find_history`, `lower_temporal_close`, `lower_write` |
| Exported compatibility/result values | `ExecutedStatement`, `FindResult`, `HistoryFindResult`, `LoweredStatement`, `MilestoneGraph` |

Re-exporting an object preserves its import path and identity, but moving its
definition may change implementation metadata such as `__module__`. No current
specification or public-surface check promises that metadata. The implementation
should not add wrappers or subclasses solely to disguise the private definition
site; any discovered serialization or introspection dependency must be treated
as a compatibility finding and resolved explicitly.

`parallax.snapshot.wrap` is the one intentional compatibility exception. It is
not in the specified or declared public surface, has no production caller other
than the handle, and is currently imported directly only by its focused unit
tests. Those tests move to the private wrapping seam or to observable handle
behavior, and the sibling module is removed. This also brings the distribution
into line with `spec/python.md` §8, whose `parallax-snapshot` source surface
already lists `materialize` and `handle` but not `wrap`; no specification edit
is required for the removal.

## Target package

```text
parallax/snapshot/
  __init__.py
  materialize.py
  handle/
    __init__.py
    _family.py
    _write_types.py
    _keyed_sql.py
    _write_lowering.py
    _read.py
    _wrap.py
    _write_inputs.py
    _transaction.py
    _database.py
```

### Ownership

| Private module | Ownership |
|---|---|
| `handle.__init__` | The stable handle interface. It documents and re-exports the existing names; it contains no lasting runtime orchestration. |
| `_family` | Shared family-effective descriptor lookups: temporal axes, version attributes, member-to-column resolution, and family column order. This is a small private leaf shared by lowering and write-input preparation, not a public seam. |
| `_write_types` | `WriteLoweringError` and lowering result values shared by the lowering and flush paths. This is a small private leaf, not a public seam. |
| `_keyed_sql` | Primitive keyed and collapsed-batch INSERT, UPDATE, and DELETE rendering, including markers, tags, keys, and ordered cells. Named for the SQL side of the lowering boundary: inside this package "write" keeps meaning the neutral instruction level, so this is the one module named for what it emits. |
| `_write_lowering` | `lower_write` dispatch plus temporal and predicate-selected lowering. It composes neutral write plans with keyed DML primitives and owns `lower_temporal_close`. |
| `_read` | `Snapshot` and execution/result values, `find` and `find_history`, history grouping, all read-side pin derivation (`deep_fetch_statement_pin`, `is_milestone_set_op`, and the module-local `_pin_from_milestone`), and conversion of neutral results into Snapshots. |
| `_wrap` | Conversion of neutral materialized nodes into frozen developer entity graphs, including graph-local identity, projection merging, inheritance, value objects, and temporal metadata. |
| `_write_inputs` | Observation capture, write-input validation, sparse/full row preparation, assignment application, and materialized predicate-write row preparation. It consumes `FindResult`/`Pin` values from `_read`; `_read` never imports observation code. |
| `_transaction` | `Transaction` verbs, transactional find participation, buffering, prior-observation rules, and predicate-write orchestration. |
| `_database` | `Database`, `connect`, callback demarcation, joining, retry policy, flush execution, and conflict classification. |

The small `_family` and `_write_types` leaf modules prevent dependency cycles
between substantive concerns. Their interfaces are private to the handle
package and should not be re-exported independently.

### Private-module naming

Most existing Python implementation files use non-underscored names because
they are the named internal interfaces of behavioral packages: for example,
`descriptor.serde`, `unit_work.planner`, and `sql_gen.compile`. The handle split
is different: `parallax.snapshot.handle` remains the one caller-facing seam, and
none of its new implementation modules is independently supported. Leading
underscores make that intent visible without expanding `handle.__all__`.

The relevant repository precedent is `entity/_annotations.py` and
`entity/_validation.py`, not the dominant behavioral-package convention. Those
files extract cycle-avoiding leaf concerns shared inside the broad
`parallax.core.entity` support scope, expose usable names to sibling
implementation, and are deliberately absent from `entity.__all__`. The handle
private modules use the same package-internal convention; the underscore does
not create another public seam or enforcement scope.

The underscore belongs on the module, not on every name inside it. A helper
called from a *sibling* module is spelled bare: under pyright's strict mode an
underscored name imported across a module boundary is a `reportPrivateUsage`
error, and `pyrightconfig.json` carries no per-rule relaxation. Privacy for the
cluster is already carried by the private module name and by the frozen
`handle.__all__`, so per-name underscores would buy nothing and cost a
suppression at every call site. The `entity/_annotations.py` precedent settles
this too: a private module exposing a bare `class_body_annotations`. Two cases
keep the underscore — a helper whose every caller lives in its own module, and a
frozen external seam such as `Transaction._buffer_predicate_instruction`, which
the conformance engine calls directly and so cannot be renamed. When dropping an
underscore, check the bare name against the module's existing imports: `_read`'s
`_statement_pin` became `deep_fetch_statement_pin`, not `statement_pin`, because
the plain name collided with the `parallax.core.temporal_read` function it wraps.

### Read result co-location

Keeping `ExecutedStatement`, `Execution`, `FindResult`, `MilestoneGraph`,
`HistoryFindResult`, and `Snapshot` beside the read executor in `_read` is
deliberate. The executor constructs these values, Snapshot conversion consumes
them immediately, and callers learn them through the stable handle interface;
they do not yet have an independent change reason that would justify another
module. This remains cohesive and within the locality target.

The co-location does not violate ADR 0025. `_read` remains lifecycle-level
handle implementation that composes `m-snapshot-read`, which remains above the
shared `m-deep-fetch` algorithm; no Snapshot result value moves into that shared
fetch implementation. Split result values later only if they acquire a real
independent change reason, not merely to mirror type-versus-function syntax.

## Intended internal direction

```text
_keyed_sql      -> _family, _write_types
_write_lowering -> _family, _write_types, _keyed_sql
_read           -> _wrap
_write_inputs   -> _family, _read
_transaction    -> _family, _read, _write_inputs
_database       -> _read, _transaction, _write_lowering, _write_types
handle.__init__ -> exported implementation modules
```

More precisely:

- `_keyed_sql` may depend on `_family` and `_write_types`.
- `_write_lowering` may depend on `_family`, `_write_types`, and `_keyed_sql`.
- `_read` may depend on `_wrap`.
- `_write_inputs` may depend on `_family` and read result values from `_read`.
- `_transaction` may depend on `_family`, `_read`, and `_write_inputs`.
- `_database` may depend on `_read`, `_transaction`, `_write_lowering`, and
  `_write_types`.
- `handle.__init__` may import the modules required to re-export the existing
  interface.

The intended graph is acyclic. Private imports in the opposite direction are a
design smell and must be resolved rather than hidden with lazy imports. In
particular, the three pin helpers belong to `_read`, even though a transaction
uses two of them and observation capture consumes their `Pin` result. Moving
them to `_write_inputs` would create the forbidden `_read` ↔ `_write_inputs`
cycle in Phase 4.

### Enforcement descendant semantics

The locked import-linter version is 2.13. Its forbidden contract defaults
`as_packages` to `True`, so both `source_modules` and `forbidden_modules` include
the named package and all descendants. The generated
`source_modules = ["parallax.snapshot.handle"]` contract therefore covers every
new `handle._*` module without additional configuration; this is a known
mechanism to exercise during extraction, not an unresolved tool question.

The same rule intentionally tightens the other direction. The generated
`parallax.snapshot.materialize` contract already forbids
`parallax.snapshot.handle`; after wrapping moves, that target includes
`handle._wrap`. Thus `_wrap` may depend on materialization through the permitted
handle → materialize direction, while materialize may not back-import wrapping
or any other handle descendant.

## Migration phases

Each phase must leave the tree green and should be independently reviewable.

### Phase 1 — Mechanical file-to-package conversion

The pre-migration interface gate is already in place:
`languages/python/tests/api_surface/public_api.json` records the exact current
`parallax.snapshot.handle.__all__`. Run that focused test before the move and
after every edit to `handle/__init__.py`; keep the Phase-1 `__all__` list as the
canonical scaffold rather than reconstructing it during later extractions.

Move `handle.py` to `handle/__init__.py` without extracting code, changing
imports, moving tests, or changing behavior. Verify immediately that:

- `parallax.snapshot.handle` remains importable;
- existing handle and top-level Snapshot exports remain importable;
- the existing handle enforcement contract still recognizes the package
  interface as its source scope;
- a targeted assertion added to `tests/artifact/test_wheels.py` proves the
  built `parallax-snapshot` wheel contains
  `parallax/snapshot/handle/__init__.py` and no longer contains
  `parallax/snapshot/handle.py`; and
- no artifact dependency changes.

This phase isolates Python packaging, wheel discovery, and import-linter source
recognition from later implementation movement. The first extraction phase,
which introduces actual descendants, must then prove that those descendants
are analyzed through import-linter's known `as_packages=True` behavior by running
`lint-imports` against the real descendant files. Hatch's directory discovery
alone is not the wheel proof: without the targeted artifact assertion, the
current suite's prefix checks cannot distinguish the old and new layouts.

### Phase 2 — Read execution and wrapping

Extract `_read.py` and move `wrap.py` to `handle/_wrap.py`. Remove the sibling
module rather than leaving a forwarding adapter. Update wrapping tests to use
the intentional private seam or observable `Database.find` / `Transaction.find`
behavior. Move `_statement_pin`, `_is_milestone_set_op`, and
`_pin_from_milestone` with the complete read concern.

This is the first phase that imports through two package levels. Private
modules must import their concrete siblings directly rather than reaching
through a partially initialized `parallax.snapshot` or
`parallax.snapshot.handle` package interface. Add a cold-import smoke check in a
fresh interpreter for both `parallax.snapshot` and `parallax.snapshot.handle`.
Run `test_snapshot_find.py` unchanged as the focused proof of the extracted
find/history executor, and run the wrapping suites that cover Pydantic
`model_construct`, copy/deepcopy/pickle behavior, and the re-exported result
classes after their definition sites move. A changed private `__module__` value
is acceptable only after these serialization and introspection checks show no
caller-visible dependency on the old definition site.

Update repository prose and test comments that name the old
`parallax.snapshot.wrap` implementation path in the same phase. The migration
check must search production source, tests, guides, conformance support, and
architecture documents so stale references cannot survive merely because only
`test_snapshot_wrap.py` imports the old module.

Extend the targeted wheel assertion to require `_read.py` and `_wrap.py` and to
forbid `parallax/snapshot/wrap.py`. Each later extraction phase adds its new
private modules to the same explicit expected-path set, so the final full-layout
criterion is executable rather than inferred from Hatch discovery.

### Phase 3 — Write lowering

Extract the complete lowering cluster together: `_family.py`,
`_write_types.py`, `_keyed_sql.py`, and `_write_lowering.py`. Existing keyed and
temporal lowering tests continue to exercise the exported handle functions.

### Phase 4 — Write inputs and observations

Extract `_write_inputs.py`. Tests must reach observation and row-preparation
behavior through transaction operations rather than importing its helpers.
The extraction consumes read-owned `FindResult` and `Pin` values and must not
introduce an import from `_read` back to `_write_inputs`.

### Phase 5 — Transaction

Extract `_transaction.py` after its read and write-input dependencies exist.
Keep the class whole; do not use mixins or partial-class machinery to make the
file smaller. The resulting module is estimated at roughly 723 lines, near the
top of the 500–750-line locality target but still within it. Transaction verbs
share one state machine, buffering rules, participation mode, and observation
invariants; mixins or partial-class splitting would scatter that state and make
navigation and verification worse. Revisit the size only if a coherent
collaborator with its own narrow interface and independent change reason
emerges.

### Phase 6 — Database demarcation

Extract `_database.py` last because it composes Transaction, read execution,
write lowering, retry, and flush behavior. At completion, `handle/__init__.py`
is the stable re-exporting interface rather than a second implementation file.
Only re-export imports change here; the canonical `__all__` scaffold from Phase
1 is not rewritten.

### Phase 7 — Conditional internal enforcement

Keep the existing broad `parallax.snapshot.handle` support scope through the
extraction phases. Once the source graph is settled:

1. derive the actual sibling-import graph;
2. compare it with the intended direction above;
3. fail and correct cycles or unjustified opposite-direction imports;
4. add a blocking filesystem-ownership check that discovers every production
   Python file under the production distributions and proves it belongs to
   exactly one enforcement scope or to an exact, explicitly justified
   package-interface exemption. Zero owners, overlapping owners, and stale
   exemptions all fail; a review-time inventory is not sufficient;
5. inventory every private module's direct external-scope imports, including
   imports that are legal for the broad parent only through transitive closure;
   the current monolith directly imports `m-core`, `m-descriptor`, `m-inheritance`,
   `m-op-algebra`, `m-dialect`, `m-temporal-read`, and `m-deep-fetch` even though
   those scopes are absent from the handle's direct-grant row;
6. audit the parent scope's declared grants against `spec/python.md` §7 and
   actual imports. Treat `m-pk-gen` and `m-navigate` separately: removing the
   unused `m-pk-gen` grant genuinely forbids that scope, while removing the
   unused direct `m-navigate` grant is enforcement-neutral because navigation
   remains reachable through `m-snapshot-read` → `m-deep-fetch` →
   `m-navigate`;
7. add a parity check so the tooling's `SUPPORT_SCOPE_DEPS` entry cannot drift
   from the authoritative Snapshot-handle row in `spec/python.md` §7; and
8. add generated child-scope enforcement only where the stable direction
   protects useful locality.

Granular enforcement is conditional on this audit. Tiny leaf modules may remain
grouped when separate scopes would prove nothing. If a direction is genuinely
unstable, record the evidence and defer that specific child contract. Any new
contracts must follow the authoritative §7 grant row and be generated rather
than hand-maintained directly in `pyproject.toml`. A child-scope model must
declare the actual direct external imports each child needs from within the
parent's permitted transitive closure; blindly copying only the parent's direct
grant row would strand the seven existing transitive imports listed above.

## Test design

Tests follow observable handle behavior rather than mirroring every private
file.

Split `test_transact.py` into:

| Test module | Behavior |
|---|---|
| `test_database_transact.py` | Commit and abort, joining, retry bounds and classification, flush conflicts, and escaped transaction references. |
| `test_transaction_reads.py` | Force-flush, read locks, pins and history, and observations demonstrated through subsequent writes. |
| `test_transaction_writes.py` | Keyed verbs, write validation, temporal windows, and prior-observation rules. |
| `test_transaction_predicate_writes.py` | Readless and materializing `*_where` behavior. |

`test_where_verbs.py` retains statement-building and bare-statement rules; its
end-to-end transaction cases move to the predicate-write suite.

Keep `test_snapshot_find.py` as the focused fake-port suite for the read module:
it protects round-trip accounting, empty-level and back-reference behavior,
family variants, narrowing, and history grouping during the earliest and
largest extraction. Its exported `find` / `find_history` seam remains part of
the compatibility inventory.

Replace tests that import `_record_observations` with assertions through
`Database` and `Transaction`. Observation capture is reachable through later
writes and does not need a private test seam.

Preserve the focused `_pin_from_milestone` missing-axis test and move it from
`test_transact.py` to the focused read suite in Phase 2. The production history
path constructs every `MilestoneGraph.pin` through `_edge_pin`, which always
populates every declared as-of attribute, so `Database.find` and
`Transaction.find` cannot exercise the helper's defensive absent-key branch.
The direct `_read._pin_from_milestone` test is therefore an intentional private
internal-seam exception, required to protect that generic-`Mapping` behavior
under the branch-coverage and changed-line coverage gates.

Retain the focused single-validator identity test as a deliberate structural
invariant. Behavioral rejection tests cannot detect a byte-for-byte fork of
`validate_write`; the test must continue proving that both the conformance
engine and the transaction buffer reference the one
`parallax.core.unit_work.validate_write` object. When Transaction moves, update
the assertion to inspect its owning private module rather than requiring
`validate_write` to leak through `handle.__init__`.

`wrap_graph` is also an intentional private internal-seam exception: its graph
identity and projection merge are a substantial in-process private module with
a small interface. Its focused tests may import `handle._wrap`, but the current
862-line suite should split into identity/projection and value/temporal
behavior. The existing keyed and temporal write-lowering suites already align
with exported conformance-facing functions and remain separate.

Test-only fixtures may be shared through narrowly named private test support
when multiple new files need them. Do not move test fixtures into production
modules or duplicate large model/port fixtures merely to avoid a test helper.

## Acceptance criteria

- `parallax.snapshot.handle` is a package and exposes the exact pre-cleanup
  `__all__`, enforced by the committed `parallax.snapshot.handle` API-surface
  snapshot in every phase.
- Existing specified and conformance import paths continue to work.
- `parallax.snapshot.__all__` is unchanged.
- `parallax.snapshot.wrap` is removed intentionally and has no forwarding
  module.
- Runtime behavior, SQL, binds, retry behavior, transaction semantics, and
  Snapshot results are unchanged.
- `parallax-snapshot` remains one lifecycle-extension distribution depending
  only on `parallax-core`.
- The built wheel contains `parallax/snapshot/handle/__init__.py` and its
  private modules, and no longer contains `parallax/snapshot/handle.py` or
  `parallax/snapshot/wrap.py`; targeted artifact assertions name these paths.
- Import-linter's `as_packages=True` descendant semantics are exercised against
  the extracted files: the broad handle contract covers every handle descendant,
  and materialize remains forbidden from importing any of them.
- The final enforcement audit records whether useful child scopes were added,
  grouped, or deferred and why, accounts for direct external imports reachable
  only through the parent's transitive closure, and proves the tooling map
  agrees with authoritative spec §7.
- A blocking filesystem-discovery check proves every production Python file has
  exactly one enforcement owner or an exact package-interface exemption.
- Transaction tests are split by observable behavior and no longer reach
  through the handle interface to transaction helper functions. The complete
  private-test allowlist is the read-owned `_pin_from_milestone` defensive
  branch, the single-`validate_write` object-identity invariant at Transaction's
  owning private module, and the focused `_wrap.wrap_graph` suite; no additional
  private implementation seam is implied.
- No production, test, guide, conformance-support, or architecture prose still
  names `parallax.snapshot.wrap` as the live implementation path.
- No substantive implementation file is split merely to satisfy a line count,
  and no permanent shallow forwarding module remains.

## Verification

Use the narrowest affected unit suites after each phase. The API-surface test is
mandatory after every `handle/__init__.py` edit. Phase 1 adds and runs the
targeted wheel-layout assertion; Phase 2 additionally runs the cold-import
smoke checks, `test_snapshot_find.py`, both wrapping suites, and the focused
serialization/introspection coverage for moved classes. Before implementation
handoff, run from `languages/python`:

```text
uv run python tools/check_dag_sync.py
uv run lint-imports
just python-static
```

Also run the public-interface and built-artifact checks affected by the
file-to-package conversion, including the API-surface snapshot and
`parallax-snapshot` wheel contents. The implementation handoff must report any
database-backed checks that were skipped and why; a documentation-only design
session does not require those lanes.

## Relevant decisions

- [ADR 0019 — Object lifecycle splits into snapshot and managed slices](../adr/0019-object-lifecycle-splits-into-snapshot-and-managed-slices.md)
- [ADR 0022 — Deployable artifacts follow optional-dependency seams](../adr/0022-deployable-artifacts-follow-optional-dependency-seams.md)
- [ADR 0023 — Same-transaction writes coalesce in the unit of work](../adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md)
- [ADR 0024 — Write instructions are hosted in m-unit-work](../adr/0024-write-instructions-are-hosted-in-m-unit-work-and-cases-declare-compile-eligibility.md)
- [ADR 0025 — Lifecycle result surfaces sit above shared fetch](../adr/0025-lifecycle-result-surfaces-sit-above-the-shared-fetch-algorithm.md)
