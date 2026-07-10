# Implementing A Language Target

This guide is for an agent or maintainer building a concrete language
implementation of Parallax. The core repository defines observable behavior and
the compatibility corpus; a completed per-language spec defines the idiomatic
API, lifecycle, source boundaries, deployable topology, database support, and
quality toolchain for one target.

Authoring that spec and implementing it are separate journeys. Finish the
language spec first. During implementation, treat it as the source of language
decisions and use this guide only for dependency-respecting milestones and
verification.

## Definition Of Success

A language target is credible when it can show all of the following:

- A completed language spec with one lifecycle profile, an exact canonical
  Conformance Slice claim, complete source and artifact topology maps, and no
  unresolved markers.
- Canonical metamodel and operation serde in JSON and YAML.
- Runtime metamodel introspection over the same descriptor shape used by the
  corpus.
- SQL generation that emits the expected per-dialect golden
  `then.statements` and binds.
- Real database execution that matches rows, graphs, table state, affected row
  counts, identity expectations, and round-trip counts.
- Dependency-boundary enforcement that respects the core module DAG even when
  several behavioral modules share an artifact.
- Selective clean-install checks for the common runtime, chosen lifecycle
  extension, and chosen database adapter.
- A conformance report for every claimed case and dialect.
- An API Conformance Suite and generated Usage Guide covering the idiomatic
  developer surface of the same claim.
- Benchmark reports only when the implementation separately claims
  `m-perf-bench`.

Passing language-specific unit tests is not enough. The compatibility corpus is
the primary behavioral surface.

## Spec-Authoring Journey

Before writing runtime code, read these files in this order:

1. [README.md](README.md)
2. [core/spec/00-overview.md](core/spec/00-overview.md)
3. [core/spec/modules.md](core/spec/modules.md)
4. [core/spec/slices.md](core/spec/slices.md)
5. [core/spec/m-conformance-adapter.md](core/spec/m-conformance-adapter.md)
6. [core/spec/language-spec-template.md](core/spec/language-spec-template.md)
7. The behavioral module specs named by the selected claim and their
   transitive prerequisites
8. [core/schemas/](core/schemas/)
9. [core/compatibility/models/](core/compatibility/models/)
10. [core/compatibility/cases/](core/compatibility/cases/)

Copy the language spec template into the language module, for example:

```text
languages/typescript/spec/typescript.md
languages/python/spec/python.md
languages/java/spec/java.md
```

Complete it according to its applicability labels. Retain exactly one lifecycle
profile and its matching result-materialization branch. The completed spec must
record the canonical claim, unclaimed implementation prerequisites, deferred
capabilities, developer API decisions, provider lifecycle, source-enforcement
map, deployable-artifact map, and executable quality toolchain. Its completion
check is the readiness gate for implementation.

Do not answer those design questions again in an implementation plan. If a
decision changes, update the completed language spec first.

## Implementation Journey

The per-language operational guide or implementation plan should link to the
completed language spec and contain only:

- dependency-respecting milestones and current status;
- commands for unit, boundary, conformance, API, packaging, and database checks;
- local database setup and the selected reset/profile commands; and
- deviations or blockers that require a language-spec decision to change.

Before the first milestone, confirm that the commands, paths, topology maps,
selected lifecycle, canonical claim, and quality gates all come from the
completed language spec. Do not copy the claim or its API and packaging
decisions into the operational guide.

### Binding rules

- Treat `core/spec`, `core/schemas`, and `core/compatibility` as the source of
  truth. Do not change them just to make a language implementation pass.
- If the core contract appears wrong or incomplete, update the spec, schema,
  fixtures, and cases consistently, then run the root verification gates.
- Implement in the legal dependency direction from
  [core/spec/modules.md](core/spec/modules.md), using the completed language
  spec's enforcement scopes.
- Keep language-facing APIs idiomatic, but serialize to the canonical metamodel
  and operation forms.
- Prefer compatibility cases over duplicated language-only behavioral tests.
  Use unit tests for internal seams, diagnostics, and failure modes.
- Use the conformance interface in
  [core/spec/m-conformance-adapter.md](core/spec/m-conformance-adapter.md); do
  not invent a language-specific conformance surface.
- The reference harness's internals are non-normative and MUST NOT be used as
  design input. The binding inputs are the module specs, schemas, compatibility
  corpus, and conformance-adapter contract.

## Claim, Prerequisites, And Developer Surface

A Conformance Slice is a named corpus claim, not an implementation layer. Its
`capabilities.modules` is the union of module tags on its cases, not the
transitive dependency closure and not a packaging plan. Snapshot and managed
object slices are sibling lifecycle choices over a shared behavioral base.

An implementation prerequisite is a module required by the normative DAG even
when it is absent from the selected claim. Implement it behind the source
boundary and verify its internal or contract obligations, but do not advertise
its cases or developer surface unless the canonical claim includes it.

Two prerequisites are especially easy to mistake for claimed behavior:

- `slice-snapshot-1` needs `m-op-list` transitively because `m-navigate` and
  `m-deep-fetch` depend on it. The snapshot extension uses the required internal
  operation/list mechanics but returns eager plain-value graphs; it must not
  expose the managed operation-backed list surface or add `m-op-list` to the
  claim.
- Both lifecycle claims need `m-db-port` through `m-unit-work` and `m-db-error`.
  It is contract-covered rather than case-covered, so it is proved through the
  database-provider contract and is not added to the tagged-case coverage
  union.

Conversely, a claimed developer surface is behavior selected by the canonical
claim and exposed through the idiomatic API as specified by the language spec.
It needs both compatibility-adapter proof and API Conformance Suite coverage.

## Dependency-Respecting Milestones

The ordering below is a partial-order schedule for either first lifecycle claim.
Within a milestone, implement a dependency before anything that names it. Do not
start a later row merely because a convenient case filename sorts earlier.

| Milestone | Modules and work, in legal dependency order | Exit evidence |
| --- | --- | --- |
| Scaffold and conformance infrastructure | Package/artifact scaffolding; dependency-boundary checks; `m-core`; `m-case-format`; then `m-conformance-adapter` | Language tests run, canonical envelopes validate, illegal imports fail, and selective package smoke tests can run |
| Descriptor and case contracts | `m-descriptor`; then `m-pk-gen`, `m-inheritance`, and `m-value-object`; descriptor/case serde and corpus loading | Every canonical descriptor parses and round-trips; rejected descriptors retain their expected classification |
| SQL walking skeleton | `m-op-algebra`; `m-dialect` and abstract `m-db-port`; then `m-sql`; one concrete Postgres adapter wired only at the composition root | A tracer case compiles to canonical Postgres SQL/binds and runs against a reset database through the shipped adapter |
| Transaction and temporal backbone | `m-unit-work`; `m-temporal-read`; `m-db-error` after its port and dialect dependencies | Transaction commit/rollback, as-of lowering, and database-error classification pass focused unit/provider checks |
| Selected lifecycle branch | Follow exactly one branch below | The branch's materialization, relationship, identity/lifecycle, and failure checks pass |
| Shared writes and correctness | `m-batch-write`; `m-read-lock`; `m-auto-retry`; `m-opt-lock`; `m-audit-write`; then `m-bitemp-write` | Active-claim write, conflict, retry, lock, and temporal families pass; bitemporal writes are not attempted before audit writes |
| Claim closure | Finish any still-partial claimed behavior; complete `m-api-conformance`; run the exact canonical case/dialect/shape/tag matrix | `describe` equals the canonical claim except for adapter identity, every in-claim case is supported, every out-of-claim request is classified unsupported, and both proof surfaces are green |

The descriptor milestone completes `m-inheritance` before `m-op-algebra`
because `narrow` depends on the inheritance family model. The walking skeleton
places `m-dialect` before `m-sql`, and the backbone places `m-db-port` before
`m-unit-work` and `m-db-error`. These constraints remain in force if a language
splits a milestone into smaller commits. Starting a module at its earliest legal
point does not imply that every case composing it with downstream behavior is
already green; finish those intersections as their other tagged modules become
reachable, then close the whole claim in the final row.

### Snapshot branch

Use this branch only when the completed language spec retains the snapshot
lifecycle:

1. Implement the internal `m-op-list` prerequisite without exposing a managed
   lazy-list result.
2. Implement `m-navigate`, then `m-deep-fetch`.
3. Implement `m-snapshot-read` materialization over that graph stack, including
   graph-local identity, whole-graph temporal pinning, closed-world loaded state,
   eager includes, and explicit-write separation.
4. Verify the snapshot-tagged intersections and materialization failures. Do not
   implement or claim `m-identity-map` or `m-detach`.

This reaches every module in the canonical `slice-snapshot-1` coverage union;
`m-op-list` and `m-db-port` remain unclaimed prerequisites. No process cache,
aggregation, business-only temporal behavior, additional dialect, benchmark, or
managed-lifecycle behavior is required to close the claim.

### Managed-object branch

Use this branch only when the completed language spec retains the managed-object
lifecycle:

1. Implement `m-identity-map` after `m-unit-work` and `m-temporal-read`, including
   family-normalized keys and lowered as-of coordinates.
2. Implement `m-op-list`, then `m-navigate`, then `m-deep-fetch`, materializing
   through the transaction-scoped identity map.
3. Implement `m-detach` after the identity map, including scope-end detach,
   abort restoration, deliberate detach, and merge-back.
4. Verify the managed-tagged intersections, identity behavior, relationship
   loading, and detach/abort transitions.

This reaches every module in the canonical `slice-managed-1` coverage union;
`m-db-port` remains an unclaimed contract prerequisite. No snapshot
materialization, process cache, aggregation, business-only temporal behavior,
additional dialect, or benchmark is required to close the claim.

## Tracer Case

Make the first database-backed milestone deliberately small. It is a tracer case
or walking skeleton, never a Conformance Slice. A useful tracer is:

1. Parse `account.yaml`.
2. Parse `m-op-algebra-002-eq.yaml`.
3. Build the operation tree.
4. Emit canonical Postgres SQL and binds.
5. Execute through the abstract port and selected adapter.
6. Compare the observed rows.

The tracer proves that descriptor loading, operation serde, SQL compilation,
adapter composition, reset, fixture load, and result normalization connect
end-to-end. It does not weaken or rename the canonical claim.

## Selecting Verification Cases

For every milestone, select compatibility cases by intersecting the active slice
tag with the relevant capability tags. For example, a managed temporal-read
target means cases carrying both `slice-managed-1` and `m-temporal-read`, further
filtered by the claim's dialect, case-shape, command, and complete module-tag
rules. A snapshot graph target similarly intersects `slice-snapshot-1` with
`m-snapshot-read` or the relevant graph capability tag.

Do not select conformance targets by filename prefix. Filenames help humans
navigate the corpus, but tags and the canonical `describe` filters determine
membership. Before running a milestone target, ensure every module-like tag on
each selected case is already implemented; otherwise the case belongs to a later
intersection even if it carries the milestone's capability tag.

The adapter must apply all filters from
[m-conformance-adapter](core/spec/m-conformance-adapter.md): command, dialect,
shape, every module-like tag, and included/excluded case tags. Returning
`unsupported` for an in-claim command is a conformance failure. Attempting an
otherwise well-formed out-of-claim case command instead of returning
`unsupported` is also a conformance failure.

## Continuous API Conformance Lane

The API Conformance Suite and Usage Guide grow with every public capability;
they are not a final implementation phase. Begin their framework and coverage
partition with the scaffold. At each milestone:

1. Add idiomatic public-API examples for the newly reachable case intersection.
2. Execute those examples through the shipped lifecycle extension and database
   adapter against a real database.
3. Update the coverage partition so exercised cases plus reasoned skips equal
   the active slice, with no stale case IDs or empty reasons.
4. Keep the no-drift guard between idiomatic operations and corpus operations
   green.
5. Regenerate the Usage Guide from suite source and run its drift check.

The conformance adapter proves wire-level emissions and observations. The API
suite proves that developers can reach the same behavior through the idiomatic
surface. Neither substitutes for the other.

## Post-Claim Expansion

Close and report the selected canonical claim before adding behavior outside it.
Each expansion needs an updated or new canonical claim and corresponding
language-spec decisions; none may silently enlarge `describe`.

| Expansion | Dependency-respecting start |
| --- | --- |
| Aggregation | Implement deferred `m-agg` after `m-op-algebra`, then deferred `m-sql-agg` after both `m-agg` and `m-sql` |
| Business-only temporal behavior | Implement deferred `m-business-only` after `m-temporal-read` and `m-unit-work` |
| Process caching and coherence | Implement deferred `m-process-cache` after `m-unit-work`, then deferred `m-coherence` after `m-process-cache` |
| Cascade delete | Implement `m-cascade-delete` after `m-op-list` and `m-unit-work` when a later claim includes it |
| Snapshot history includes | Extend snapshot materialization only under a claim carrying the feature-tagged cases |
| Additional dialects | Add the pure dialect strategy and a separately deployable adapter/driver, golden SQL, provider profiles, and selective clean-install proof |
| Benchmarks | Implement `m-perf-bench` after `m-conformance-adapter`, then add fixture-defined reports and thresholds from the completed language spec |

Measure optimization work after correctness. Extra dialects, caches, and
benchmark tooling must preserve the production artifact boundaries recorded in
the language spec.

## Conformance Adapter

Expose the interface specified by
[core/spec/m-conformance-adapter.md](core/spec/m-conformance-adapter.md). A CLI is
the simplest cross-language seam:

```text
parallax-conformance describe
parallax-conformance compile --case <case.yaml> --dialect postgres
parallax-conformance run --case <case.yaml> --dialect postgres
parallax-conformance benchmark --benchmark <benchmark.yaml> --dialect postgres
```

Every command writes one JSON document that validates against
[core/schemas/conformance-adapter.schema.json](core/schemas/conformance-adapter.schema.json).
Keep the adapter narrow: load a core case, compile or run it, and report
emissions or observations. Do not expose internal classes or language-specific
query builders through this seam.

Only advertise commands present in the canonical claim. In particular,
`benchmark` remains unsupported until a separate claim includes
`m-perf-bench`.

## Verification Ladder

Use the smallest verification that can catch the problem being worked on, then
walk upward before declaring a milestone complete:

1. Language unit tests for parsers, compilers, materializers, lifecycle state,
   and diagnostics.
2. Language dependency-boundary and import-cycle enforcement.
3. Conformance tests for the active-slice and capability-tag intersection.
4. API Conformance Suite coverage partition and Usage Guide drift check.
5. Built-artifact inspection and selective clean-install smoke tests.
6. Root static checks:

   ```bash
   just lint
   just core-dep-graph
   ```

7. Root compatibility-corpus sanity check:

   ```bash
   PARALLAX_DATABASES=postgres just oracle-test
   ```

8. Claimed language matrix for every supported dialect and provider profile.
9. Benchmark reports only under a claim that includes `m-perf-bench`.

Run the exact aggregate local and CI commands recorded in the completed language
spec. Report every database-backed check that could not run and its reason;
silent skips are failures. The root Python harness validates the core corpus. It
does not prove a language implementation conforms unless that implementation is
wired through its own adapter or test runner.

## Classifying Failures

Classify a failure before editing code:

- **Serde failure:** a descriptor, operation, case, or adapter envelope cannot
  round-trip or validate. Fix the owning contract implementation before SQL.
- **Compile failure:** emitted SQL or binds differ from the selected golden
  statement. Fix `m-sql` or the pure dialect seam.
- **Provider failure:** reset, DDL, fixture load, query/write execution, rollback,
  peer connection, or driver translation violates the provider contract.
- **Result failure:** SQL matches but rows differ. Check value conversion,
  normalization, fixture loading, and materialization.
- **Graph failure:** flat rows are correct but relationship assembly, ordering,
  or shared paths differ. Check `m-navigate` and `m-deep-fetch`.
- **Snapshot materialization failure:** an eager plain-value graph has incorrect
  graph-local identity, temporal pin propagation, unloaded/null/empty state, or
  performs SQL after materialization. Fix `m-snapshot-read`; do not add managed
  identity or lazy loading.
- **Managed identity failure:** instances that should coalesce do not, pinned
  views collide, or identity escapes/ends before its owning unit of work. Fix
  `m-identity-map` key lowering and interning timing.
- **Round-trip failure:** observations are correct but statement counts differ.
  Check query planning, eager/deferred loading, and whether an unclaimed cache
  was accidentally assumed.
- **Detach/abort failure:** scope-end state, rollback restoration, deliberate
  copies, deletion state, or merge-back differs. Fix lifecycle transitions in
  `m-detach` and transaction rollback before optimistic locking.
- **Temporal failure:** check interval closure, infinity representation,
  defaulted as-of dimensions, processing-instant sourcing, and milestone write
  chaining.
- **Database Error failure:** native codes are lost or errors are assigned the
  wrong Parallax Error class at the port boundary. Fix `m-db-error` without
  leaking driver types upward.
- **Unsupported-classification failure:** an in-claim request returns
  `unsupported`, or an out-of-claim command, dialect, shape, module/tag
  combination is attempted. Fix the full claim-filter intersection before the
  underlying behavior.

If a case appears wrong, first prove the issue against the normative module,
schema, and corpus artifacts, using the reference harness only as an executable
oracle. Do not silently fork behavior in the language target.

## Completion Check

Before claiming the language target is complete:

- The completed language spec still passes its completion rules and the
  implementation matches both topology maps.
- The dependency tool proves every implemented edge is legal under the full
  normative module DAG.
- `describe` equals the selected slice's canonical claim except for adapter
  identity.
- Case discovery uses the active slice and capability-tag intersection, and the
  full claimed matrix is green.
- Every in-claim command returns `ok` or `error`; every otherwise well-formed
  out-of-claim case command is classified `unsupported` without executing
  behavior.
- The selected lifecycle branch reaches all and only its claimed developer
  surfaces; unclaimed prerequisites remain internal or contract-only.
- The API Conformance Suite coverage partition and generated Usage Guide are
  current.
- Artifact inspection and clean-install checks prove that unselected lifecycle
  extensions, adapters, drivers, and development tooling are absent.
- All mandatory static, database, packaging, and supply-chain commands from the
  language spec ran, or each skipped database-backed check is reported with a
  reason.
- Optional aggregation, business-only temporal behavior, process caches,
  coherence, additional dialects, snapshot-history includes, cascade delete,
  and benchmarks remain outside the first claim unless a later canonical claim
  and updated language spec explicitly include them.
