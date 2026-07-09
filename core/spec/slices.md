# Slices

A **slice** is a declared subset of the compatibility corpus that an
implementation claims through the conformance adapter for a specific milestone.
Slices — not module tiers — are how modules compose into deliverables: a slice
names exactly the cases one build honestly supports right now, and MAY defer
*parts* of a module without redefining that module's boundary.

## The slice-tag convention

A slice's name *is* its tag: lowercase, matching `^slice-[a-z0-9][a-z0-9-]*$`.
The `slice-` prefix makes slice tags structurally recognizable in a case's flat
`tags` array (the way the `m-` prefix marks module tags), followed by a short
language-neutral purpose name and an ordinal. `slice-mvp-1` is the first slice,
leaving room for successors (`slice-mvp-2`) and siblings (`slice-temporal-1`).

A slice's machine-readable form is a `describeOk` envelope validated against
`conformance-adapter.schema.json`. Membership is **include-driven**: a case is in
the slice precisely when it carries the slice tag *and* passes the claim's broad
module / dialect / shape filters. Nothing is selected by the *absence* of a tag,
so a slice is immune to the corpus's tag hazards.

## First-implementation Conformance Slice

`slice-mvp-1` is the smallest agent-buildable first build: Postgres only, the
unit-of-work transaction behavior but **not** the process caches, no aggregation,
no inheritance, no detach, no MariaDB, no benchmarks, no coherence. Primary-key
generation (`m-pk-gen`) **is** in the slice: both the `max` strategy
(`coalesce(max(col), ?) + ?`) and the simulated-`sequence` strategy (a registry
`next_val += n` reserve then the reserved id), including a sequence-strategy insert
composed with an audit-only temporal milestone. The full bitemporal write surface
(`m-bitemp-write`) **is** in the slice: the windowed and plain rectangle-split
milestone writes and the optimistic-gated inactivation all gate the build. Value
objects **are** in the slice: their nested-predicate reads, atomic document writes
(including a versioned document write under an optimistic gate), inherited-
temporality reads, materialization graph, and pre-SQL `rejected` negatives all gate
the build (the bitemporal rectangle-split *value-object* write stays out — the one
milestone-chaining write the slice still defers).

The canonical `describe` claim below is the **single source of truth** for the
slice. Its `capabilities.modules` is the derived union of the module tags carried
by the tagged cases; the `dep_graph_check --profile` gate parses this exact block
and asserts the tagged set can never silently drift from it. The claim carries no
`profile` wire key — the slice name lives only in tags and documentation, because
`describeOk` is `additionalProperties: false`.

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

An implementation that adopts this slice claims exactly these capabilities and
returns `unsupported` for every case command outside it — every out-of-slice case
shape, dialect, module, or tag.
