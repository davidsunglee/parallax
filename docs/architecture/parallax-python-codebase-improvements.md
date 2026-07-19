# Parallax Python codebase improvement review

**Reviewed:** 2026-07-19

**Scope:** `languages/python`

**Repository state reviewed:** `8e26b84` (`docs: refresh project overview for Python slice`)
**Visual report:** [parallax-python-architecture-review.html](parallax-python-architecture-review.html)

## Purpose

This document preserves the architecture review of the Python implementation,
with particular attention to:

1. whether build-enforced dependencies are making the source architecture
   awkward; and
2. how to reduce monolithic files toward an iterative target of roughly
   500–750 lines per file.

The review uses the architecture vocabulary from the codebase-design guidance:
**module**, **interface**, **implementation**, **depth**, **seam**, **adapter**,
**leverage**, and **locality**.

## Current decision

The first selected improvement is to turn
`parallax.snapshot.handle` from one file into a package.

Conceptually:

```text
Before
packages/parallax-snapshot/src/parallax/snapshot/
  handle.py

After
packages/parallax-snapshot/src/parallax/snapshot/
  handle/
    __init__.py
    ...private implementation modules...
```

This source reorganization does **not** create a new deployable artifact.
Everything remains inside the existing `parallax-snapshot` distribution, with
the same `pyproject.toml`, dependency graph, and lifecycle-extension role.
The import path remains `parallax.snapshot.handle`, and its existing public
exports remain compatible.

The internal module layout, migration phases, test split, and conditional
enforcement audit are now accepted in
[parallax-snapshot-handle-package-design.md](parallax-snapshot-handle-package-design.md).
The existing handle interface remains stable; frozen-node wrapping becomes
private handle implementation and the non-public sibling module is retired.
The exact current handle `__all__` is now protected by the committed API-surface
snapshot before the first runtime move.

## Executive conclusions

- Keep the existing deployable artifact topology. The separation among
  `parallax-core`, `parallax-snapshot`, `parallax-postgres`, and the
  development-only `parallax-conformance` artifact is earning its keep.
- Keep the language-neutral behavioral DAG. No illegal modeled production
  import was found during this review.
- The build does not require one behavioral module per file. An enforcement
  scope may be a package containing multiple internal source modules.
- The primary dependency friction is the granularity and completeness of
  Python source ownership, not the artifact topology.
- `parallax.snapshot.handle` is a legitimate, deep composition seam. The
  problem is its 2,723-line implementation, not the existence of the seam.
- `parallax.snapshot.wrap` is production code outside every generated
  enforcement scope. This is a real enforcement gap.
- `parallax.core.value_object` appears shallow: the behavioral source module is
  used only by its tests, while actual production consumers use parallel
  descriptor helpers. Improving it requires an explicit core DAG/design
  decision rather than a Python-only move.

## Dependency-enforcement findings

### What is working

The project intentionally distinguishes four topologies:

- language-neutral behavioral modules;
- Python source modules;
- build enforcement scopes; and
- deployable artifacts.

That distinction is healthy. In particular:

- the common runtime does not depend on a lifecycle extension or concrete
  database driver;
- the Snapshot lifecycle remains a separate extension over the common runtime;
- the Postgres adapter is the only production artifact that declares psycopg;
- the conformance harness stays out of production dependency graphs; and
- the application/test composition root selects and injects the adapter.

These properties implement ADR 0022 and should not be weakened merely to make
files smaller.

### Where enforcement is awkward

The Python scope map is manually duplicated between:

- `languages/python/spec/python.md` §7;
- `MODULE_SCOPE` in `languages/python/tools/check_dag_sync.py`;
- `SUPPORT_SCOPE_DEPS` in the same script; and
- the generated import-linter contracts in
  `languages/python/pyproject.toml`.

The generator correctly derives the forbidden-edge complement from the core
DAG once the Python mapping is supplied, but it does not prove that every
production file belongs to a scope.

Concrete gaps and over-grants found during the review:

- `parallax.snapshot.wrap` is not owned by any generated enforcement scope.
  It imports inheritance, descriptor, Entity Class frontend, temporal-read,
  and Snapshot materialization behavior.
- `parallax.core.__init__` and `parallax.snapshot.__init__` are also unmodeled.
  Their package-interface role may justify an explicit exemption, but that
  exemption should be machine-checked rather than implicit.
- The handle support scope declares direct grants for `m-pk-gen` and
  `m-navigate`, although `handle.py` currently imports neither directly. These
  are not equivalent: removing `m-pk-gen` would genuinely tighten the generated
  complement, whereas removing `m-navigate` is byte-for-byte
  enforcement-neutral because navigation remains reachable through Snapshot
  materialization → deep fetch → navigation.
- The broad `parallax.core.entity` support scope cannot detect the internal
  dependency cycles and lazy back-imports among `base.py`, `expressions.py`,
  `statement.py`, `meta.py`, and `graph_state.py`.

### Recommended enforcement change

For the current target, keep `languages/python/spec/python.md` §7 authoritative
and make the tooling parse or otherwise verify its mapping rather than silently
duplicating it. Use that authority to generate or verify all of the following:

1. `MODULE_SCOPE` and `SUPPORT_SCOPE_DEPS` parity with the spec table;
2. import-linter contracts generated from the verified mapping;
3. exhaustive filesystem ownership, requiring every production module to
   belong to exactly one scope or an explicit package-interface exemption; and
4. a report of support-scope grants that no observed import uses.

If a later specification decision replaces the prose table with a separate
machine-readable authority, it must update the spec and tooling together; the
current `SUPPORT_SCOPE_DEPS` constant is not independently authoritative.

Do not tighten new internal scopes before the source has been split into stable
concerns. First improve locality; then use enforcement to preserve the proven
directions.

## File-size hotspots

Line counts are from the reviewed repository state.

| Lines | File | Kind | Responsibility clusters |
|---:|---|---|---|
| 3,468 | `parallax/conformance/engine.py` | development | reads/graphs; write translation and execution; interleaving; conflict/error/rejected cases |
| 2,723 | `parallax/snapshot/handle.py` | production | write lowering; Snapshot/read execution; Transaction; observations/materializing writes; Database/retry/flush |
| 1,553 | `parallax/core/sql_gen/compile.py` | production | general reads; inheritance reads; navigation; scalar/value-object predicates |
| 1,393 | `parallax/core/entity/base.py` | production | registry/metamodel; wire and row helpers; declaration compiler; Pydantic metaclass; Edited Copy provenance |
| 1,182 | `parallax/conformance/api_suite.py` | development | example registry; skip policy; partition computation; Usage Guide rendering |
| 892 | `parallax/conformance/stories.py` | development | executable write stories and their metadata |
| 778 | `parallax/core/inheritance/__init__.py` | production | family resolution; descriptor validation; write validation |
| 713 | `parallax/core/entity/expressions.py` | production | already within the requested target band |
| 594 | `parallax/core/op_algebra/serde.py` | production | within target band |
| 559 | `parallax/core/unit_work/planner.py` | production | within target band |
| 544 | `parallax/conformance/graph_stories.py` | development | within target band |
| 542 | `parallax/core/descriptor/serde.py` | production | within target band |
| 537 | `parallax/core/op_algebra/validate.py` | production | within target band |

Large tests mirror the two largest implementations:

- `tests/unit/test_engine.py`: 2,814 lines;
- `tests/unit/test_transact.py`: 2,444 lines; and
- `tests/unit/test_sql_gen.py`: 998 lines.

The production split should be accompanied by test splits along the same
behavioral concerns. Tests should exercise the existing module interface where
possible rather than reaching into private implementation.

## Improvement candidates

### 1. Deepen the Snapshot handle as a package — Strong, selected

#### Files

- `parallax/snapshot/handle.py`
- `parallax/snapshot/wrap.py`
- `tests/unit/test_transact.py`
- `tests/unit/test_snapshot_find.py`
- `tests/unit/test_snapshot_wrap.py`

#### Problem

The handle is the intentional composition seam that can legally see both the
neutral Unit of Work plan and SQL generation. It passes the deletion test:
removing it would spread transaction, retry, read execution, materialization,
and write-lowering complexity across callers. However, its implementation now
contains several independent change reasons in one 2,723-line file.

`parallax.snapshot.wrap` is closely related production implementation and is
currently outside every build enforcement scope.

#### Direction

Keep the `parallax.snapshot.handle` interface and the `parallax-snapshot`
artifact. Convert the file to a package and separate private implementation by
change reason. The accepted ownership and migration design is recorded in
[parallax-snapshot-handle-package-design.md](parallax-snapshot-handle-package-design.md).
The implementation clusters are:

- Snapshot result values;
- read and history execution;
- keyed write lowering;
- temporal and set-based write lowering;
- Transaction verbs;
- write-input preparation and observations; and
- Database demarcation, retry, and flush execution.

Frozen-node wrapping gains explicit ownership as private `handle._wrap`
implementation. The sibling `parallax.snapshot.wrap` path is intentionally
removed without a forwarding module: it is absent from the declared public
surface, only its focused tests import it directly, and `spec/python.md` §8
already lists `materialize` and `handle` as the Snapshot artifact's source
surface without listing `wrap`.

#### Benefits

- locality: read, write, and transaction changes stop colliding;
- leverage: callers keep one stable handle interface;
- the existing `DbPort` seam remains real, with Postgres and test adapters;
- most files can land between roughly 160 and 650 lines; and
- wrapping can no longer escape dependency enforcement.

#### Guardrails

- Do not move write lowering into `m-unit-work` or `m-sql` merely to shrink the
  handle. Their separation is intentional.
- Keep write coalescing owned by `m-unit-work` (ADR 0023/0024).
- Keep Snapshot results above shared fetch (ADR 0025).
- Keep the Snapshot lifecycle separate from the common runtime and Postgres
  adapter (ADR 0019/0022).
- Do not create a new deployable artifact.

### 2. Make source ownership exhaustive — Strong

#### Problem

Dependency truth is distributed across prose, Python constants, generated
TOML, and implicit filesystem conventions. A new production file can fall
outside the generated contracts without failing the build.

#### Direction

Use one authoritative scope map to generate documentation and contracts, audit
every production module's ownership, explicitly model package-interface
modules, and report unused support grants.

#### Benefits

- locality: dependency truth concentrates in one module;
- leverage: one map drives several proofs;
- new production source cannot silently escape enforcement; and
- over-broad composition scopes become visible before they grow.

### 3. Give `m-value-object` real depth — Worth exploring

#### Problem

`parallax.core.value_object` is only 104 lines and has no production importer.
Operation validation, write validation, and SQL generation instead use
descriptor-owned value-object helpers or repeat the same rationale because the
current DAG does not let them depend on the value-object scope.

The module fails the deletion test: deleting it removes almost no production
complexity.

#### Direction

Revisit behavioral ownership and DAG edges so value-object path and document
behavior can concentrate in the behavioral module that names them.

#### Warning

This is a core specification/DAG decision, not a Python-only refactor. It must
be adopted explicitly rather than smuggled through a file move.

### 4. Split the conformance engine by case execution lane — Strong

#### Problem

The conformance importer exemption is correct, but `engine.py` has grown to
3,468 lines and its 2,814-line unit test reaches at least two dozen private
names. Read/graph execution, write compilation, write execution, interleaving,
connection termination, and terminal case shapes do not share one change
reason.

#### Direction

Preserve `parallax.conformance.engine` as the interface while moving its
implementation into lane-owned private modules. Split tests by the same lanes
and replace private cross-module testing with tests at each owned interface.

The conformance-family import exemption remains unchanged.

### 5. Keep SQL generation deep; split its implementation — Strong

#### Problem

`parallax.core.sql_gen` already has a relatively small interface and passes the
deletion test, but its 1,553-line `compile.py` contains general read assembly,
inheritance-family lowering, navigation lowering, and scalar/value-object
predicate lowering.

#### Direction

Retain the existing SQL-generation interface and shared private compilation
context. Separate the implementation concerns internally without creating new
public seams. Continue testing through the compiler interface.

### 6. Deepen the Metamodel Hub class frontend — Strong

#### Problem

`entity/base.py` combines registry state, scoped Metamodel Hub assembly, wire
names, row translation, class-declaration compilation, the Pydantic metaclass,
and Edited Copy provenance. Other `entity` modules import it, while
`expressions.py` and `statement.py` contain lazy back-imports to it. The broad
parent enforcement scope cannot detect this internal coupling.

#### Direction

Keep the `parallax.core.entity` interface. Separate registry/scoped metamodel
state, declaration compilation, row/provenance behavior, and Entity
implementation. Once the direction settles, add finer internal enforcement
scopes to prevent cycles from returning.

### 7. Move inheritance implementation out of `__init__.py` — Worth exploring

#### Problem

The 778-line package interface file also implements three distinct concerns:
family resolution, descriptor-family validation, and write validation.

#### Direction

Keep `parallax.core.inheritance` as the interface and move those concerns into
private modules. Preserve one shared family-root resolver for temporal axes and
optimistic locking; do not duplicate that logic across the split.

This candidate is just over the target band and can follow the larger
production monoliths.

## Recommended order

1. Package `parallax.snapshot.handle` without changing behavior or its existing
   import path.
2. Split the matching transaction/read/write tests.
3. Give frozen-node wrapping explicit enforcement ownership.
4. Add exhaustive source-ownership verification and trim unused handle grants.
5. Split SQL generation.
6. Split the Entity Class frontend, then tighten its internal dependency
   directions.
7. Split the conformance engine in parallel with development-only work when
   practical.
8. Explore the `m-value-object` behavioral decision separately because it
   requires a core specification change.

## Relevant decisions

- [ADR 0019 — Object lifecycle splits into snapshot and managed slices](../../docs/adr/0019-object-lifecycle-splits-into-snapshot-and-managed-slices.md)
- [ADR 0022 — Deployable artifacts follow optional-dependency seams](../../docs/adr/0022-deployable-artifacts-follow-optional-dependency-seams.md)
- [ADR 0023 — Same-transaction writes coalesce in the unit of work](../../docs/adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md)
- [ADR 0024 — Write instructions are hosted in m-unit-work](../../docs/adr/0024-write-instructions-are-hosted-in-m-unit-work-and-cases-declare-compile-eligibility.md)
- [ADR 0025 — Lifecycle result surfaces sit above shared fetch](../../docs/adr/0025-lifecycle-result-surfaces-sit-above-the-shared-fetch-algorithm.md)
- [ADR 0026 — Inheritance temporal axes are root-owned](../../docs/adr/0026-inheritance-family-temporal-axes-are-declared-only-by-the-root.md)
- [ADR 0027 — Inheritance optimistic locking is root-owned](../../docs/adr/0027-inheritance-family-optimistic-locking-is-declared-only-by-the-root.md)

## Visual report notes

The companion HTML report is self-contained apart from its Tailwind and Mermaid
CDN imports. It contains the before/after diagrams, hotspot mass chart,
recommendation badges, and the top recommendation used during the review.
