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
- SQL generation that emits the expected per-dialect `goldenSql` and binds.
- Real database execution that matches rows, graphs, table state, affected row
  counts, identity/cache expectations, and round-trip counts.
- Dependency-boundary enforcement that respects the core module DAG.
- A conformance report for every implemented case and dialect.
- Benchmark reports when claiming M13 performance support.

Passing language-specific unit tests is not enough. The compatibility corpus is
the primary behavioral surface.

## Start Here

Before writing runtime code, read these files in this order:

1. [README.md](README.md)
2. [core/spec/00-overview.md](core/spec/00-overview.md)
3. [core/spec/scope-and-tiers.md](core/spec/scope-and-tiers.md)
4. [core/spec/dependency-graph.md](core/spec/dependency-graph.md)
5. [core/spec/language-spec-template.md](core/spec/language-spec-template.md)
6. [core/spec/m12-compatibility-harness.md](core/spec/m12-compatibility-harness.md)
7. [core/spec/conformance-adapter-contract.md](core/spec/conformance-adapter-contract.md)
8. [core/spec/api-conformance-contract.md](core/spec/api-conformance-contract.md)
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
  [core/spec/dependency-graph.md](core/spec/dependency-graph.md).
- Keep language-facing APIs idiomatic, but serialize to the canonical metamodel
  and operation forms.
- Prefer real compatibility cases over duplicated language-only behavioral
  tests. Use unit tests for internal seams, edge cases, and diagnostics.
- Postgres is the first required dialect. Additional dialects are added behind
  the M11 seam.
- The reference harness's internals are non-normative and
  MUST NOT be used as design input for a language implementation; the binding
  inputs are the spec modules, `core/schemas/`, the compatibility corpus, and
  the conformance-adapter contract.

## Planning Deliverables

Before implementation, produce a short plan in the language module that records:

- The completed language spec path.
- The named **Conformance Slice** this build claims — or the definition of a new
  named slice in
  [core/spec/scope-and-tiers.md](core/spec/scope-and-tiers.md) — recorded as its
  `describe` claim. This is the first decision; see
  [Declaring The Conformance Slice](#declaring-the-conformance-slice).
- The module/package map for M0, M1, M2, M3, M4, M5, M7, M8, M9, M10, M11, M12,
  M13, cross-process coherence, and any non-numbered support packages.
- The dependency-boundary enforcement tool and configuration.
- The conformance adapter entry point.
- The concrete provider reset lifecycle for database-backed cases, including the
  empty-schema reset primitive, DDL application point, fixture-load point, and
  fallback if a snapshot optimization is used.
- The first case slice that will be made green.
- The final case/dialect matrix the implementation intends to claim.
- Any deferred modules, with tier justification from
  [core/spec/scope-and-tiers.md](core/spec/scope-and-tiers.md).

## Declaring The Conformance Slice

Slice selection is the first step, taken before any runtime code. It decides what
this build actually claims, and everything downstream — the module/package map,
the case/dialect matrix, the conformance grade, the API Conformance Suite — is
scoped by it. Choose (or define) the named Conformance Slice:

- **Adopt an existing slice.** A fresh first build ordinarily adopts the
  canonical `slice-mvp-1` slice defined in
  [core/spec/scope-and-tiers.md](core/spec/scope-and-tiers.md): Postgres-only, 99
  cases selected by the single `caseTags.include: ["slice-mvp-1"]` tag. Copy its
  `capabilities` block verbatim, changing only the `adapter` identity.
- **Or define a new slice.** If no existing slice fits, define one in
  [core/spec/scope-and-tiers.md](core/spec/scope-and-tiers.md) following the
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
[core/spec/conformance-adapter-contract.md](core/spec/conformance-adapter-contract.md)).

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
| 1 | M0 core conventions and M1 metamodel/descriptor serde | All descriptors in `core/compatibility/models/` parse and round-trip |
| 2 | M2 operation model and operation serde | Operations in `0001`, `0002`, and `02xx` cases parse and round-trip |
| 3 | M11 Postgres dialect seam and M3 basic SQL generation | `0001-find-all.yaml`, `0002-eq.yaml`, then all `02xx` predicate cases emit matching SQL and binds |
| 4 | M4 relationships and M5 operation-backed list results | `0301` through `0313`, including deep-fetch round-trip counts and graphs |
| 5 | M2 aggregation sub-area | `0401` through `0410` |
| 6 | M8 transactions, unit of work, identity cache, query cache, read locks, batching | `0601` through `0604` |
| 7 | M7 audit temporal reads and writes | `0501` through `0512` |
| 8 | M9 lifecycle/detach and M10 optimistic locking | `0701` through `0704` |
| 9 | M7 full two-axis and business-temporal behavior | `0801` through `0822` |
| 10 | M1 inheritance and value objects | `0901` through `0923` |
| 11 | M11 second dialect support | `1001` and `1002`, then every case with that dialect's `goldenSql` |
| 12 | Cross-process coherence | `1101` and `1102` |
| 13 | M13 benchmark methodology and reports | Every file in `core/compatibility/benchmarks/` |
| Suite | API Conformance Suite + Usage Guide over the claimed slice (grows with the developer surface) | Coverage partition is green (exercised ∪ skipped == slice); the Usage Guide renders clean |

The API Conformance Suite is not a trailing phase — it grows alongside the
developer surface, exercising each family of the claimed slice through the
idiomatic public API as that API lands. See
[core/spec/api-conformance-contract.md](core/spec/api-conformance-contract.md).

The first green slice should be intentionally small. A useful first slice is:

- parse `account.yaml`
- parse `0002-eq.yaml`
- build the operation tree
- emit Postgres SQL and binds
- execute against Postgres and compare rows.

## Conformance Adapter

Each language implementation should expose the conformance interface specified
in
[core/spec/conformance-adapter-contract.md](core/spec/conformance-adapter-contract.md).
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
   just dep-graph
   ```

6. Root compatibility corpus sanity check:

   ```bash
   PARALLAX_DATABASES=postgres just test
   ```

7. Claimed language implementation matrix for every supported dialect.
8. Benchmark report when claiming M13.

The root Python harness validates the core corpus. It does not prove a language
implementation conforms unless that implementation is wired through its own
conformance adapter or test runner.

## When A Case Fails

Classify the failure before editing code:

- **Serde failure:** the descriptor or operation cannot round-trip. Fix M1 or M2
  before touching SQL generation.
- **Compile failure:** emitted SQL or binds do not match `goldenSql`. Fix M3 or
  the M11 dialect seam.
- **Result failure:** SQL matches but rows differ. Check fixture loading, type
  conversion, value normalization, and object materialization.
- **Graph failure:** flat rows are correct but deep fetch assembly differs. Check
  M4 relationship joins, parent-key gathering, and list identity behavior.
- **Round-trip failure:** results are correct but statement counts differ. Check
  M4/M5/M8 query planning and cache behavior.
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
- How does each M0 neutral scalar map to generated property/read types,
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
- Which dialects and tiers are claimed?
- What benchmark targets are claimed?
- How does `parallax-conformance benchmark` emit the M13 report shape in the
  adapter envelope, and is any `report.json` file only an artifact copy?
- Does the API Conformance Suite exercise or reason-skip every case in the claimed
  slice, with the coverage partition asserted green (suite partition is green)?
- Is the Usage Guide generated from the suite's source and drift-checked in CI so
  it renders clean?

When in doubt, keep the public surface idiomatic and keep the conformance seam
boring.
