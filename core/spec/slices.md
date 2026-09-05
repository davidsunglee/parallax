# Slices

A **slice** is a declared subset of the compatibility corpus that an
implementation claims through the conformance adapter for a specific milestone.
Slices — not module tiers — are how cases compose into named behavioral claims:
a slice names exactly the cases one build honestly supports right now, and MAY
defer *parts* of a module without redefining that module's boundary. A slice is
coverage, not a source or deployable topology.

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
include PK generation, inheritance, canonical storage layouts, value objects and
the portable document encoding they store, and the full temporal write family up
to the bitemporal rectangle split.

- **`slice-snapshot-1`** — the **plain-value** surface: reads materialize
  snapshot graphs (`m-snapshot-read`); writes are explicit only. No managed
  lifecycle: the slice claims neither `m-identity-map` nor `m-detach`, and not
  `m-op-list` (a snapshot read is not a query-backed lazy list; its
  round-trip observability is pinned by `m-snapshot-read`). It is also the only
  slice claiming `m-execution-lifecycle`: transient execution observability is
  lifecycle-neutral, but its dedicated case spine is authored over the
  plain-value surface, so the managed slice claims it once cases carry that tag.
  It is likewise the only slice claiming `m-model-evolution` and
  `m-schema-delta`: describing the difference between two accepted models and
  lowering it to dialect statements are both lifecycle-neutral, and the
  `evolution` case shape they bring with them is claimed here for the same
  reason.
- **`slice-managed-1`** — the **managed-object** surface: reads materialize
  managed objects interned in the transaction-scoped identity map
  (`m-identity-map`), mutation buffers through the unit of work, objects detach
  at their owning scope's end and merge back (`m-detach`), and relationship
  access resolves through query-backed lists (`m-op-list`).

Neither slice claims the deferred process caches (`m-process-cache`,
`m-coherence`), aggregation (`m-agg`, `m-sql-agg`), the deferred Valid-Time-Only
formation (`m-validtime-only`), cascade delete (`m-cascade-delete`), MariaDB, or
benchmarks (`m-perf-bench`). The `snapshot-history-includes` feature
(`m-snapshot-read`) is feature-tagged and claimed by neither.

## Snapshot Conformance Slice

The canonical `describe` claim for `slice-snapshot-1`:

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "reference", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-dialect", "m-document-codec", "m-execution-lifecycle", "m-inheritance", "m-metamodel", "m-model-evolution", "m-model-formation", "m-navigate", "m-object-query", "m-opt-lock", "m-pk-gen", "m-predicate", "m-read-lock", "m-relationship", "m-schema-delta", "m-snapshot-read", "m-sql", "m-storage-layout", "m-temporal-read", "m-txtime-write", "m-unit-work", "m-value-object", "m-wire"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "error", "concurrencySuccess", "rejected", "evolution"],
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
    "modules": ["m-api-conformance", "m-auto-retry", "m-batch-write", "m-bitemp-write", "m-case-format", "m-conformance-adapter", "m-core", "m-db-error", "m-deep-fetch", "m-descriptor", "m-detach", "m-dialect", "m-document-codec", "m-identity-map", "m-inheritance", "m-metamodel", "m-model-formation", "m-navigate", "m-object-query", "m-op-list", "m-opt-lock", "m-pk-gen", "m-predicate", "m-read-lock", "m-relationship", "m-sql", "m-storage-layout", "m-temporal-read", "m-txtime-write", "m-unit-work", "m-value-object", "m-wire"],
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
