# Spec Reconciliation

This note tracks how the core ADRs should be reconciled with the existing core
specification, schemas, fixtures, and compatibility cases.

The root ADRs are design decisions, but they are not automatically normative
until the core spec, schemas, and compatibility corpus agree with them. The
right sequence is:

1. Reconcile the ADR against the existing core module boundary.
2. Promote the agreed language-neutral contract into the relevant `core/spec`
   module.
3. Update schemas only when the model, operation, case, or adapter shape changes.
4. Add compatibility cases only for observable behavior not already covered.

## Promotion Rule

Promote an ADR to core when it describes a language-neutral observable contract:
which rows are read or written, which objects are managed, which operation shape
is portable, which errors are reportable through conformance, or which cache /
transaction behavior must hold across languages.

Keep an ADR in a language context when it describes API spelling, generated type
names, package layout, iteration mechanics, builder syntax, or other host-language
ergonomics.

Add compatibility cases when the contract is observable through the conformance
adapter or the reference harness. Do not add a case for a purely documentary
boundary unless the boundary changes a schema or an adapter observation.

## Already Covered

These core ADRs are already substantially represented in the spec and corpus.
They may need cross-references, but they do not need immediate new cases.

| ADR | Existing coverage | Action |
|---|---|---|
| `0001-find-returns-result-collections` | `M5` operation-backed list results; deep-fetch/cache cases prove lazy resolution behavior | Add terminology alignment only |
| `0002-includes-load-relationship-paths` | `M2` / `M4` `deepFetch`; cases `0310`-`0315` | Reconcile naming before changing cases |
| `0003-managed-finds-do-not-return-partial-objects` | `M2` aggregation returns aggregate rows; managed reads project full entity rows | Add explicit prose if desired |
| `0004-relationships-have-core-kinds` | `M1` relationship cardinality/dependent flags; `M4` navigation/deep fetch | Already covered |
| `0009-transaction-reads-lock-by-default` | `M8`, `M11`, case `0603`, MariaDB case `1001` | Already covered |
| `0013-optimistic-lock-conflicts-are-caller-driven` | `M10`, cases `0703`-`0704` cover conflict detection | Reconcile retry policy |
| `0014-temporal-reads-use-core-axis-names` | `M7`, cases `050x`, `080x`, `082x` | Already covered |
| `0015-temporal-writes-use-explicit-verbs` | `M7`, write cases `0510`-`0512`, `0810`-`0812`, `0822` | Already covered |
| `0017-timestamps-have-microsecond-boundary` | `M0` timestamp precision text | Already covered |
| `0018-identity-cache-is-required` | `M8`, cases `0601`-`0602` | Already covered |
| `0022-core-expressions-define-predicates-assignments-and-sort-keys` | `M2` operation algebra; many `020x` cases | Already covered for predicates/sort; assignments need write-surface reconciliation |
| `0023-predicate-edge-cases-have-portable-semantics` | `M2`, cases `0207`-`0223` | Already covered |
| `0024-projections-return-plain-data` | `M2` aggregation returns aggregate rows, value-object projection case `0922` | Future projection spec should cite this |

## Reconcile Before Adding Cases

### `includes` vs `deepFetch`

Current core uses `deepFetch` as the canonical operation tag in `M2`,
`operation.schema.json`, and compatibility cases. The TypeScript API wants
`includes` as the user-facing option name.

Recommendation: keep `deepFetch` as the core serialized operation for now and
document `includes` as the language-facing option term. If the core term should
be renamed to `includes`, do it as a coordinated change across `M2`, `M3`, `M4`,
`M12`, `operation.schema.json`, every `031x` case, and any harness code that
recognizes `deepFetch`.

No new compatibility cases are needed for the naming choice. Existing `031x`
cases already test relationship path loading, shared-prefix fetches, null
to-one handling, empty roots, and round-trip counts.

### Snapshots vs detached objects

ADR `0019` says snapshots are detached plain data. Current `M9` still specifies
Reladomo-style detached copies and merge-back semantics.

Recommendation: split these concepts explicitly:

- **Domain snapshots** are the core plain-data serialization surface.
- **Detached managed copies** are a separate lifecycle/merge-back capability.

For TypeScript V1, snapshots can be the only detached data surface. Core can
still keep M9 detached managed copies as a fast-follow or parity capability, but
it should not treat snapshots and detached managed copies as interchangeable.

Spec work:

- Add snapshot terminology and serialization-shape rules to `M9` or a small
  serialization subsection adjacent to `M9`.
- State whether detached managed copies remain required, are deferred, or become
  optional relative to snapshots.

Potential compatibility cases:

- Snapshot of a managed object with selected attributes and relationships.
- Snapshot does not expose relationship-reference/runtime state.
- Snapshot input used as create payload, if core accepts that flow.

### Explicit transactions for all writes

ADRs `0005` and `0006` require managed graph mutation and all writes to happen
inside explicit transactions. Current `M8` describes unit-of-work behavior but
does not clearly forbid outside-a-transaction writes as a core rule.

Recommendation: promote the rule into `M8`:

- write operations require an explicit transaction boundary;
- managed object graph mutation requires an active transaction;
- an implementation must report a structured failure when a write is attempted
  without one.

Compatibility cases should be adapter/runtime observation cases, not golden SQL
cases, because the expected behavior is failure before SQL emission.

Potential compatibility cases:

- create outside transaction fails with a stable diagnostic.
- update outside transaction fails with a stable diagnostic.
- delete outside transaction fails with a stable diagnostic.
- relationship collection mutation outside transaction fails.

These likely require extending the conformance adapter observations or adding a
validation/error case shape.

### No public flush

ADR `0010` says flush is not a public application API. Current `M8` says writes
are buffered and flushed at the unit-of-work boundary, but does not state that
public flush is excluded.

Recommendation: add prose to `M8`; do not add compatibility cases unless the
conformance adapter grows an API-surface introspection command. This is primarily
a language-spec/API-surface rule.

### Set-based write surface

ADRs `0011` and `0012` say set-based writes target predicates or unresolved
result collections and return result objects. Current `M5` explicitly defers
broad bulk/set mutation.

Recommendation: leave the ADRs as accepted future direction, but promote the
minimal contract into the future `M5` bulk/set section before adding cases.

Spec work:

- define canonical set-based update and delete operation shapes;
- define write result object fields that are required across languages;
- decide whether assignments live in M2 operation algebra or in M5 write algebra.

Potential compatibility cases:

- delete by predicate emits one set-based statement.
- delete by unresolved result collection preserves set-based execution.
- update by predicate with explicit assignments emits set-based SQL.
- update result reports affected count.

### Optimistic retry policy

ADR `0013` says optimistic lock conflicts are caller-driven. Current `M10`
allows automatic or caller-driven retry as a per-language policy.

Recommendation: choose one:

- If correctness policy belongs in core, update `M10` to forbid automatic retry
  and require surfacing the conflict.
- If retry policy is language-specific, move or soften the root ADR and keep the
  existing M10 language-flex rule.

Compatibility cases already cover conflict detection by affected-row count. A
new case is only needed if core forbids automatic retry and the conformance
adapter can observe that a conflict is surfaced immediately.

### Processing instant clock strategy

ADR `0016` says processing instants come from a configured clock strategy. `M7`
uses `txInstant` but does not fully specify where it comes from.

Recommendation: promote this into `M7` and the conformance adapter setup rules:

- temporal write cases must be able to run with a deterministic processing
  instant;
- production APIs should not expose casual per-operation processing-time
  overrides;
- test/runtime setup may configure the clock strategy.

Potential compatibility case:

- audit-only temporal update with configured processing instant produces
  milestone rows using that instant.

Many existing temporal write cases already prove deterministic `txInstant`
effects, but the source of the instant should be made explicit in spec prose.

### Validation errors and accumulated issues

ADR `0021` requires accumulated structured validation issues. Current M12
adapter output has diagnostics for command errors, but the corpus does not yet
define validation-only cases for user input or descriptor errors with multiple
issues.

Recommendation: promote this into `M12` and
`conformance-adapter-contract.md` only after deciding the validation surfaces:

- descriptor validation;
- operation validation;
- create payload / snapshot input validation;
- runtime API misuse validation.

Potential compatibility cases:

- invalid descriptor with multiple schema/model errors reports multiple issues.
- invalid create payload reports path-addressed attribute and relationship
  issues.
- invalid operation reports path-addressed operation issues.

This likely requires schema support for expected diagnostics.

### Create payload relationship handling

ADR `0020` says create payloads handle relationships explicitly. Core currently
has lifecycle/detach and write-sequence cases, but not a create-payload contract
for nested dependent relationship data or association rejection.

Recommendation: promote after the snapshot/create-payload boundary is settled.

Potential compatibility cases:

- create root with dependent children inserts parent then children.
- create payload that attempts association linking fails unless an explicit link
  operation exists.
- create payload ignores or rejects unsupported relationship data according to
  the chosen core rule.

## Proposed Work Order

1. Reconcile naming: core `deepFetch` vs language-facing `includes`.
2. Reconcile snapshots vs M9 detached managed copies.
3. Promote explicit transaction-required writes into `M8`.
4. Promote clock strategy source for temporal write instants into `M7`.
5. Decide optimistic retry policy and update or narrow ADR `0013`.
6. Define validation diagnostic expectations in `M12` and adapter schema.
7. Define future set-based write result shape in `M5`.
8. Add compatibility cases only for the new observable contracts from steps 2,
   3, 4, 6, and 7.

## Compatibility Case Backlog

High-value cases after spec reconciliation:

- write outside transaction fails before SQL emission;
- relationship mutation outside transaction fails before SQL emission;
- create with dependent relationship payload inserts the full dependent graph;
- create with unsupported association payload fails with structured diagnostics;
- snapshot serialization excludes relationship-reference/runtime state;
- snapshot serialization respects requested attributes and relationships;
- validation accumulates multiple issues with stable paths and codes;
- set-based update by predicate returns affected-count result;
- set-based delete by unresolved result collection preserves set execution;
- temporal write uses configured processing instant.

Cases that should not be added yet:

- cases that only rename `deepFetch` to `includes`;
- cases for no public flush unless API-surface introspection is introduced;
- cases for automatic-vs-caller-driven optimistic retry until core chooses a
  policy;
- broad snapshot/create cases until snapshots and M9 detach are separated in
  spec text.

## Review Findings - 2026-06-28

The prior findings are largely addressed, and DB-free validation passes, but the
TypeScript V1 target still has contradictory conformance claims around
benchmarks, deferred projection, and value-object typing. These gaps mean the
specs/cases are not yet fully sufficient for an agent to implement the
TypeScript ORM unambiguously.

### P1: Keep benchmark claims consistent with section 9

`languages/typescript/spec/01-implementation-spec.md:675-676`

Status: addressed by including `m13` and `benchmark` in the TypeScript V1
capability claim and clarifying that only numeric benchmark targets are deferred.

The V1 claim says M13 benchmark execution is deferred and the example omits
`benchmark` from `commands`, but section 9.1 and ADR-0062 say the V1 execution
hook is `parallax-conformance benchmark` and that the benchmark suite must run
end-to-end. An implementer following section 4.5 would omit a command that
section 9 requires, so the V1 capability claim needs to include benchmark/M13 or
section 9 needs to explicitly defer it.

### P1: Exclude the deferred projection case from V1 claims

`core/compatibility/cases/0922-value-object-project-nested-field.yaml:13`

Status: addressed by tagging the nested-field projection case with `projection`
and excluding that tag from the TypeScript V1 capability claim.

Because section 1.8 defers projection from V1, this nested-field projection read
is outside the intended slice, but its tags are only `m1`, `m3`, `nested`,
`value-object`, and `json`; under the section 4.5 V1 `describe` example it is
still claimed as a normal Postgres read. A V1 adapter returning `unsupported`
for the deferred projection case would therefore fail conformance, so the case
needs a projection tag that the claim excludes, or projection needs to stop being
deferred.

### P2: Remove typed value-object path examples

`languages/typescript/spec/01-implementation-spec.md:72-77`

Status: addressed by replacing the typed nested value-object snapshot selector
with V1-supported scalar selectors and stating that value-object attributes are
selected as whole `ParallaxJsonValue` properties.

The spec says V1 cannot generate structured value-object interfaces or field
paths from the descriptor, but the snapshot examples still use
`Order.customer.address.zipCode`. For a value object exposed only as
`ParallaxJsonValue`, that path requires exactly the field-level metadata the spec
says does not exist, so a fresh implementer cannot tell whether to generate
those paths or reject the example.
