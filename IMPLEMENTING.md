# Implementing A Language Target

This guide is for an agent or maintainer building a concrete language
implementation of Parallax. It sits between the language-neutral core spec and
a language-specific implementation plan.

The core repository already defines the behavior and the compatibility corpus.
The language target's job is to provide an idiomatic developer surface that
conforms to that shared contract.

## Definition Of Success

A language target is credible when it can show all of the following:

- A completed language spec with no unresolved template markers.
- Canonical metamodel and operation serde in JSON and YAML.
- Runtime metamodel introspection over the same descriptor shape used by the
  corpus.
- SQL generation that emits the expected per-dialect golden `then.statements` (dialect-keyed `sql`) and binds.
- Real database execution that matches rows, graphs, table state, affected row
  counts, identity/cache expectations, and round-trip counts.
- Dependency-boundary enforcement that respects the core module DAG.
- A conformance report for every implemented case and dialect.
- Benchmark reports when claiming `m-perf-bench` performance support.

Passing language-specific unit tests is not enough. The compatibility corpus is
the primary behavioral surface.

## Start Here

Before writing runtime code, read these files in this order:

1. [README.md](README.md)
2. [core/spec/00-overview.md](core/spec/00-overview.md)
3. [core/spec/modules.md](core/spec/modules.md)
4. [core/spec/slices.md](core/spec/slices.md)
5. [core/spec/language-spec-template.md](core/spec/language-spec-template.md)
6. [core/spec/m-case-format.md](core/spec/m-case-format.md)
7. [core/spec/m-conformance-adapter.md](core/spec/m-conformance-adapter.md)
8. [core/spec/m-api-conformance.md](core/spec/m-api-conformance.md)
9. [core/schemas/](core/schemas/)
10. [core/compatibility/models/](core/compatibility/models/)
11. [core/compatibility/cases/](core/compatibility/cases/)
12. [core/compatibility/benchmarks/](core/compatibility/benchmarks/)

Then copy the language spec template into the language module, for example:

```text
typescript/spec/typescript.md
python/spec/python.md
java/spec/java.md
```

Replace every `*(decide and record)*` marker with a concrete decision and a
short rationale. Do not start implementation while the language spec still has
open decisions that affect public API shape, model input, transaction
demarcation, temporal read/write spelling, test integration, code generation,
collection behavior, dependency enforcement, or performance targets.

## Non-Negotiables

- Treat `core/spec`, `core/schemas`, and `core/compatibility` as the source of
  truth. Do not change them just to make a language implementation pass.
- If the core contract appears wrong or incomplete, update the spec, schema,
  fixtures, and cases together, then run the root verification gates.
- Implement in the legal dependency direction from
  [core/spec/modules.md](core/spec/modules.md).
- Keep language-facing APIs idiomatic, but serialize to the canonical metamodel
  and operation forms.
- Prefer real compatibility cases over duplicated language-only behavioral
  tests. Use unit tests for internal seams, edge cases, and diagnostics.
- Postgres is the first required dialect. Additional dialects are added behind
  the database seam (`m-dialect` / `m-db-port`).
- The reference harness's internals are non-normative and
  MUST NOT be used as design input for a language implementation; the binding
  inputs are the spec modules, `core/schemas/`, the compatibility corpus, and
  the conformance-adapter contract.

## Planning Deliverables

Before implementation, produce a short plan in the language module that records:

- The completed language spec path.
- The named **Conformance Slice** this build claims — or the definition of a new
  named slice in
  [core/spec/slices.md](core/spec/slices.md) — recorded as its
  `describe` claim. This is the first decision; see
  [Declaring The Conformance Slice](#declaring-the-conformance-slice).
- The behavioral-module → source-ownership / enforcement-scope map covering the
  catalog in [core/spec/modules.md](core/spec/modules.md), plus any support
  scopes.
- The dependency-boundary enforcement tool and configuration.
- The conformance adapter entry point.
- The concrete provider reset lifecycle for database-backed cases, including the
  empty-schema reset primitive, DDL application point, fixture-load point, and
  fallback if a snapshot optimization is used.
- The first case slice that will be made green.
- The final case/dialect matrix the implementation intends to claim.
- Any deferred modules, with their status from
  [core/spec/modules.md](core/spec/modules.md).

## Declaring The Conformance Slice

Slice selection is the first step, taken before any runtime code. It decides what
this build actually claims, and everything downstream — the
behavioral-module/source-enforcement map, the case/dialect matrix, the
conformance grade, the API Conformance Suite — is scoped by it. Choose (or
define) the named Conformance Slice:

- **Adopt an existing slice.** A fresh first build ordinarily adopts one of the
  two object-lifecycle slices defined in
  [core/spec/slices.md](core/spec/slices.md) — `slice-snapshot-1` (plain
  snapshot-graph reads, explicit writes) or `slice-managed-1` (managed objects
  with the transaction-scoped identity map). Both are Postgres-only, selected by
  a single `caseTags.include` tag. Copy the chosen claim's `capabilities` block
  verbatim, changing only the `adapter` identity.
- **Or define a new slice.** If no existing slice fits, define one in
  [core/spec/slices.md](core/spec/slices.md) following the
  slice-naming convention (`^slice-[a-z0-9][a-z0-9-]*$`, where the slice's name
  is its tag) and tag the included cases. A slice is case-granular: it may claim
  some features of a module while deferring others, without redefining that
  module's boundary.

Record the claim as a `describe` (`describeOk`) envelope that validates against
[core/schemas/conformance-adapter.schema.json](core/schemas/conformance-adapter.schema.json).
That envelope is the slice's machine-readable form, and its `caseTags.include`
tag is the slice's name. Inside it, `modules`, `dialects`, and `caseShapes` are
broad filters and `caseTags` is the fine-grained slice filter; a case command is
in-claim only when it satisfies all of them (see
[core/spec/m-conformance-adapter.md](core/spec/m-conformance-adapter.md)).

Then hold the `unsupported` discipline. For every case command outside the
claimed slice — an out-of-slice case shape, dialect, module, or tag — the adapter
MUST return `status: "unsupported"` (exit `10`), and it MUST NOT return
`unsupported` for any in-slice case command. That two-sided rule is what makes the
slice an honest claim rather than an ad hoc partial-pass list.

## Implementation Sequence

The dependency graph is not just documentation. Use it to decide the build order.
Each phase should leave behind runnable verification before the next phase
starts.

| Phase | Capability | First verification target |
| --- | --- | --- |
| 0 | Scaffold, package layout, dependency-boundary check, conformance CLI placeholder | Language tests run; illegal module imports fail the build |
| 1 | `m-core` conventions and `m-descriptor` metamodel/serde | All descriptors in `core/compatibility/models/` parse and round-trip |
| 2 | `m-op-algebra` operation model and operation serde | The `m-op-algebra-*` cases parse and round-trip |
| 3 | `m-dialect` Postgres seam and `m-sql` basic SQL generation | `m-op-algebra-001-find-all.yaml`, `m-op-algebra-002-eq.yaml`, then the predicate cases emit matching SQL and binds |
| 4 | `m-navigate` relationships and `m-op-list` operation-backed list results | The `m-navigate-*` and `m-deep-fetch-*` cases, including deep-fetch round-trip counts and graphs |
| 5 | `m-agg` aggregation (deferred module) | The `m-agg-*` cases |
| 6 | `m-unit-work` transactions, `m-read-lock`, `m-batch-write`, `m-auto-retry` (identity/query cache `m-process-cache` deferred) | The `m-unit-work-*`, `m-read-lock-*`, and `m-batch-write-*` cases |
| 7 | `m-temporal-read` reads and `m-audit-write` audit temporal writes | The `m-temporal-read-*` and `m-audit-write-*` cases |
| 8 | `m-detach` lifecycle and `m-opt-lock` optimistic locking | The `m-detach-*` and `m-opt-lock-*` cases |
| 9 | `m-bitemp-write` two-axis writes (`m-business-only` deferred) | The `m-bitemp-write-*` cases — the bounded `*Until` / optimistic family (`-001`–`-005`, `-008`) and the plain open-interval writes `-006`/`-007`/`-009` (update split, terminate, insert); see the case-family map below |
| 10 | `m-inheritance` and `m-value-object` | The `m-inheritance-*` and `m-value-object-*` cases; the inheritance families are enumerated in the case-family map below |
| 11 | `m-dialect` second dialect support | The MariaDB cases (e.g. `m-read-lock-009`, `m-core-004`), then every case whose `then.statements` entries carry that dialect's `sql` key |
| 12 | `m-coherence` cross-process coherence (deferred) | The `m-coherence-*` cases |
| 13 | `m-perf-bench` benchmark methodology and reports | Every file in `core/compatibility/benchmarks/` |
| Suite | API Conformance Suite + Usage Guide over the claimed slice (grows with the developer surface) | Coverage partition is green (exercised ∪ skipped == slice); the Usage Guide renders clean |

The API Conformance Suite is not a trailing phase — it grows alongside the
developer surface, exercising each family of the claimed slice through the
idiomatic public API as that API lands. See
[core/spec/m-api-conformance.md](core/spec/m-api-conformance.md).

The first green slice should be intentionally small. A useful first slice is:

- parse `account.yaml`
- parse `m-op-algebra-002-eq.yaml`
- build the operation tree
- emit Postgres SQL and binds
- execute against Postgres and compare rows.

### Inheritance and plain-bitemporal case families (phases 9–10)

Phases 9 (`m-bitemp-write`) and 10 (`m-inheritance`) each fan out into several
case families. Run them family by family; the family names below map onto the
`core/compatibility/cases/` file-name slugs. Every `m-inheritance-*` case is
tagged `slice-snapshot-1` **and** `slice-managed-1` (never `slice-mvp-1`), so
both object-lifecycle slices claim the whole family.

**Plain bitemporal writes (`m-bitemp-write`, phase 9).** Beyond the bounded
`*Until` rectangle-split and optimistic cases (`m-bitemp-write-001`–`-005`,
`-008`), the plain open-interval write family is `m-bitemp-write-006` (plain
update split), `m-bitemp-write-007` (plain terminate), and `m-bitemp-write-009`
(plain insert, Postgres-only). These are the inheritance-independent
insert/update/terminate witnesses that the temporal inheritance cases compose
with subtype routing.

**Inheritance reads (phase 10).**

- Table-per-hierarchy: concrete-target reads `m-inheritance-001`/`-002`; abstract
  reads `-003`/`-004`/`-017` (root, animal-family root, empty result); abstract
  subtype read `-011`; subtype narrowing `-012`–`-016` (to one concrete, to an
  abstract subtype, to multiple concretes, `or` across branches, redundant
  narrow).
- Table-per-concrete-subtype: concrete reads `m-inheritance-005`/`-006`; `union
  all` abstract and narrowed reads `-050`–`-053` (abstract root, abstract
  subtype, narrow to an abstract subtype, narrow to multiple concretes).

**Polymorphic navigation and narrowed deep fetch (phase 10).**

- Table-per-hierarchy: polymorphic relationships `m-inheritance-060`/`-061`;
  narrowed `exists` `-062`/`-063`; narrowed deep fetch `-065`–`-067` (narrowed
  view, equivalent narrowings deriving one view key, two narrowed views sharing a
  path prefix).
- Table-per-concrete-subtype: polymorphic relationship `m-inheritance-070`;
  narrowed `exists` `-071`.

**Concrete-subtype writes (phase 10).** Creates `m-inheritance-007`/`-010`/
`-080`/`-081`; updates `-082`/`-083` (inherited and own attributes) and the
optimistic-lock composition `-084`; deletes `-009`/`-085`.

**Rejected cases (phase 10).** Model-invariant `when.model` rejects
`m-inheritance-020`–`-032` (one per closed-tree invariant); operation-level
narrow rejects `-040`–`-042`; relationship-scope narrow rejects `-064`/`-072`;
write rejects `-086`–`-089` (sibling attribute, metadata field, abstract target,
set-based).

**Temporal inheritance composition (phase 10).** Audit-only terminate
`m-inheritance-090`/`-091`; temporal abstract reads `-092` (as-of) / `-093`
(`union all`); bitemporal terminate `-094`/`-095`; bitemporal terminate-until
`-096`/`-097`.

## Conformance Adapter

Each language implementation should expose the conformance interface specified
in
[core/spec/m-conformance-adapter.md](core/spec/m-conformance-adapter.md).
A CLI is the easiest cross-language seam because it can be driven by any
runner.

Recommended commands:

```text
parallax-conformance describe
parallax-conformance compile --case <case.yaml> --dialect postgres
parallax-conformance run --case <case.yaml> --dialect postgres
parallax-conformance benchmark --benchmark <benchmark.yaml> --dialect postgres
```

Every command writes a single JSON document that validates against
[core/schemas/conformance-adapter.schema.json](core/schemas/conformance-adapter.schema.json).
The adapter should stay narrow: load a core case, compile or run it, and report
emissions or observations. Do not expose internal classes or language-specific
query builders through this conformance seam.

## Verification Ladder

Use the smallest verification that can catch the bug you are working on, then
walk upward before claiming a milestone.

1. Language unit tests for parser/compiler/cache internals.
2. Language dependency-boundary enforcement.
3. Language conformance tests for the active case slice.
4. API Conformance Suite: the coverage partition over the claimed slice
   (Docker-free), the Docker-backed developer-surface run through the shipped
   adapter, and the Usage Guide drift check.
5. Root static checks:

   ```bash
   just lint
   just core-dep-graph
   ```

6. Root compatibility corpus sanity check:

   ```bash
   PARALLAX_DATABASES=postgres just oracle-test
   ```

7. Claimed language implementation matrix for every supported dialect.
8. Benchmark report when claiming `m-perf-bench`.

The root Python harness validates the core corpus. It does not prove a language
implementation conforms unless that implementation is wired through its own
conformance adapter or test runner.

## When A Case Fails

Classify the failure before editing code:

- **Serde failure:** the descriptor or operation cannot round-trip. Fix
  `m-descriptor` or `m-op-algebra` before touching SQL generation.
- **Compile failure:** emitted SQL or binds do not match the golden `then.statements`. Fix `m-sql`
  or the `m-dialect` seam.
- **Result failure:** SQL matches but rows differ. Check fixture loading, type
  conversion, value normalization, and object materialization.
- **Graph failure:** flat rows are correct but deep fetch assembly differs. Check
  `m-navigate` relationship joins, parent-key gathering, and list identity behavior.
- **Round-trip failure:** results are correct but statement counts differ. Check
  `m-navigate` / `m-op-list` / `m-unit-work` query planning and cache behavior.
- **Temporal failure:** check interval closure, infinity representation,
  defaulted as-of dimensions, and milestone write chaining.
- **Scenario failure:** check transaction boundaries, identity cache, query
  cache invalidation, read locks, and batched writes.

If a case looks wrong, first prove the issue against the core Python harness or
by adding a new failing core case. Do not silently fork behavior in the language
target.

## Language Spec Completion Checklist

A language spec is ready for implementation when it answers these questions:

- How does a developer author a model?
- How is the canonical metamodel produced, introspected, and serialized?
- How does each `m-core` neutral scalar map to generated property/read types,
  create/update input types, adapter bind types, and materialized result types?
- How does a developer spell common operations, relationship navigation,
  grouping, aggregation, deep fetch, and temporal reads (`asOf`, range, history)?
- How does a developer spell temporal writes, including audit-only
  insert/update/terminate and the full-bitemporal `insertUntil` / `updateUntil` /
  `terminateUntil` trio or language-specific aliases?
- Which runtime timestamp type represents temporal instants, what precision
  boundary is enforced, and where processing instants come from?
- How are transactions demarcated?
- How are lazy lists, single-result lookups, and bulk operations surfaced?
- Is code generation used? If yes, where do generated files live and how are
  they refreshed?
- Are all generated types and helpers derivable from the canonical descriptor,
  with enum/value-object typed surfaces omitted or explicitly backed by core
  schema?
- Which test runner provisions Postgres and runs compatibility cases?
- Which dependency-boundary tool enforces the module DAG?
- Which dialects and slices are claimed?
- What benchmark targets are claimed?
- How does `parallax-conformance benchmark` emit the `m-perf-bench` report shape
  in the adapter envelope, and is any `report.json` file only an artifact copy?
- Does the API Conformance Suite exercise or reason-skip every case in the claimed
  slice, with the coverage partition asserted green (suite partition is green)?
- Is the Usage Guide generated from the suite's source and drift-checked in CI so
  it renders clean?

When in doubt, keep the public surface idiomatic and keep the conformance seam
boring.
