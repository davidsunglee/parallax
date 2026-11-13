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
so a slice is immune to the corpus's tag hazards.

Each fenced `json` claim below is the **single source of truth** for its slice.
A claim's `capabilities.modules` is the derived union of the module tags carried
by its tagged cases; the `dep_graph_check --profile` gate parses every claim
block in this file and asserts each tagged set can never silently drift from its
claim. A claim carries no `profile` wire key — the slice name lives only in tags
and documentation, because `describeOk` is `additionalProperties: false`.

## Snapshot behavior

`slice-snapshot-1` is the Postgres plain-value surface: reads materialize snapshot
graphs (`m-snapshot-read`) and writes are explicit. It includes primary-key
generation, inheritance, canonical storage layouts, value objects and their
portable document encoding, and temporal writes through the bitemporal rectangle
split. Execution observability, model evolution, and schema delta are part of its
claim.

The claim excludes MariaDB and performance workloads (`m-perf-bench`). The
`snapshot-history-includes` feature (`m-snapshot-read`) remains feature-tagged
and unclaimed.

## Snapshot Conformance Slice

The canonical `describe` claim for `slice-snapshot-1`:

```json
{
  "schemaVersion": "1", "command": "describe", "status": "ok",
  "adapter": { "language": "reference", "name": "parallax-core", "version": "0.1.0" },
  "capabilities": {
    "modules": ["m-api-conformance", "m-auto-retry", "m-batch-write", "m-case-format", "m-concurrency", "m-conformance-adapter", "m-core", "m-database-binding", "m-db-error", "m-read-planning", "m-descriptor", "m-dialect", "m-document-codec", "m-edit", "m-execution", "m-execution-authority", "m-execution-lifecycle", "m-inheritance", "m-metamodel", "m-model-evolution", "m-model-formation", "m-navigate", "m-object-query", "m-pk-gen", "m-predicate", "m-read-delivery", "m-relationship", "m-schema-delta", "m-snapshot-read", "m-sql", "m-storage-layout", "m-temporal-read", "m-temporal-write", "m-unit-work", "m-value-object", "m-wire", "m-write-payload", "m-write-plan"],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "edit", "error", "concurrencySuccess", "rejected", "evolution"],
    "caseTags": { "include": ["slice-snapshot-1"] },
    "commands": ["describe", "compile", "run"],
    "provisioning": "self-managed"
  }
}
```

An implementation that adopts a slice claims exactly its capabilities and
returns `unsupported` for every case command outside it — every out-of-slice
case shape, dialect, module, or tag.
