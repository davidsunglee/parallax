# Slices

A **slice** is a declared subset of the compatibility corpus that an
implementation claims through the conformance adapter for a specific milestone.
Slices — not module tiers — are how modules compose into deliverables: a slice
names exactly the cases one build honestly supports right now, and MAY defer
*parts* of a module without redefining that module's boundary.

The slice ⇒ module reference is **one-way**: this file names modules; a module
spec never names a slice.

## The slice-tag convention

A slice's name *is* its tag: lowercase, matching `^slice-[a-z0-9][a-z0-9-]*$`.
The `slice-` prefix makes slice tags structurally recognizable in a case's flat
`tags` array (the way the `m-` prefix marks module tags), followed by a short
language-neutral purpose name and an ordinal.

A slice's machine-readable form is a `describeOk` envelope validated against
`conformance-adapter.schema.json`. Membership is **include-driven**: a case is in
the slice precisely when it carries the slice tag *and* passes the claim's broad
module / dialect / shape filters. Nothing is selected by the *absence* of a tag,
so a slice is immune to the corpus's tag hazards. A case MAY carry several slice
tags — the two slices below share their non-lifecycle base.

Each fenced `json` claim below is the **single source of truth** for its slice.
A claim's `capabilities.modules` is the derived union of the module tags carried
by its tagged cases; the `dep_graph_check --profile` gate parses every claim
block in this file and asserts each tagged set can never silently drift from its
claim. A claim carries no `profile` wire key — the slice name lives only in tags
and documentation, because `describeOk` is `additionalProperties: false`.

## The two object-lifecycle slices

Parallax's first-implementation surface is **two slices over one shared base**,
split by object-lifecycle model (ADR 0019). Both are Postgres-only and both
include PK generation, inheritance, value objects, and the full temporal write
family up to the bitemporal rectangle split. They supersede `slice-mvp-1`
(below, **deprecated**), which is retired — tags, claim, and all — when the
TypeScript implementation migrates its conformance claim to `slice-managed-1`.

- **`slice-snapshot-1`** — the **plain-value** surface: reads materialize
  snapshot graphs (`m-snapshot-read`); writes are explicit only. No managed
  lifecycle: the slice claims neither `m-identity-map` nor `m-detach`, and not
  `m-op-list` (a snapshot read is not an operation-backed lazy list; its
  round-trip observability is pinned by `m-snapshot-read`).
- **`slice-managed-1`** — the **managed-object** surface: reads materialize
  managed objects interned in the transaction-scoped identity map
  (`m-identity-map`), mutation buffers through the unit of work, objects detach
  at their owning scope's end and merge back (`m-detach`), and navigation yields
  operation-backed lists (`m-op-list`).

Neither slice claims the deferred process caches (`m-process-cache`,
`m-coherence`), aggregation (`m-agg`, `m-sql-agg`), the business-only temporal
flavor (`m-business-only`), cascade delete (`m-cascade-delete`), MariaDB, or
benchmarks (`m-perf-bench`). The `snapshot-history-includes` feature
(`m-snapshot-read`) is feature-tagged and claimed by neither.

## Snapshot Conformance Slice

The canonical `describe` claim for `slice-snapshot-1`:

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "reference", "name": "parallax-core", "version": "0.1.0" },
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

## Managed-Object Conformance Slice

The canonical `describe` claim for `slice-managed-1`:

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "reference", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-audit-write", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-detach", "m-dialect", "m-identity-map", "m-inheritance", "m-navigate", "m-op-algebra", "m-op-list", "m-opt-lock", "m-pk-gen", "m-read-lock", "m-sql", "m-temporal-read", "m-unit-work", "m-value-object"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "error", "concurrencySuccess", "rejected"],
    "caseTags": { "include": ["slice-managed-1"] },
    "commands": ["describe", "compile", "run"],
    "provisioning": "self-managed"
  }
}
```

An implementation that adopts a slice claims exactly its capabilities and
returns `unsupported` for every case command outside it — every out-of-slice
case shape, dialect, module, or tag.

## First-implementation Conformance Slice

**Deprecated.** `slice-mvp-1` was the smallest agent-buildable first build and
is superseded by the two object-lifecycle slices above; it survives only because
the TypeScript V1 conformance claim still selects by its tag. It adds no new
membership — every `slice-mvp-1` case also carries `slice-snapshot-1` (except
the `m-op-list`-tagged cases) and `slice-managed-1`. Delete this claim and the
`slice-mvp-1` tags together with the TypeScript migration to `slice-managed-1`.

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "reference", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-audit-write", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-dialect", "m-navigate", "m-op-algebra", "m-op-list", "m-opt-lock", "m-pk-gen", "m-read-lock", "m-sql", "m-temporal-read", "m-unit-work", "m-value-object"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "error", "concurrencySuccess", "rejected"],
    "caseTags": { "include": ["slice-mvp-1"] },
    "commands": ["describe", "compile", "run"],
    "provisioning": "self-managed"
  }
}
```
