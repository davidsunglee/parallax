# Lifecycle result surfaces sit above the shared fetch algorithm

`modules.md` declared `m-navigate --> m-op-list` and `m-deep-fetch --> m-op-list`,
reasoning that "navigation *yields* lists and deep fetch *populates* them." That
framing folded the **managed lifecycle's** list result surface into the shared
read stack as a dependency of both navigation and deep fetch. The DAG-closure
rule that every language target's claimed-module set must include — `required_modules
= claimed ∪ transitive_prerequisites` — then forced any target claiming
`m-navigate` or `m-deep-fetch` to also carry `m-op-list` in its closure, even a
plain-value target that will never emit an operation-backed list. The Python
snapshot-lifecycle spec had accordingly reserved a `parallax.core.op_list` scope
for no reason but to satisfy that closure rule, despite `m-op-list.md` itself
stating that "a plain-value read is **not** an operation-backed list."

The decision is that the two lifecycle result surfaces — operation-backed lists
for the managed lifecycle, snapshot graphs for the plain-value lifecycle — are
**peers above the shared fetch algorithm**, neither living underneath it nor
underneath one another. Three edges change:

- `m-navigate --> m-op-list` becomes `m-navigate --> m-op-algebra` — the honest
  replacement: navigation's `navigate` / `exists` / `notExists` nodes **are**
  algebra vocabulary, and `m-op-algebra` was previously reachable from
  `m-navigate` only transitively, through the edge being removed.
- `m-deep-fetch --> m-op-list` is **deleted**. Deep fetch is a pure per-level
  fetch algorithm; nothing about it is a list, and a navigation filter used as a
  predicate inside an operation yields no list either — it is a semi-join.
- `m-op-list --> m-deep-fetch` is **added**: a lazy list is *populated by* deep
  fetch, the exact mirror of the existing, documented `m-snapshot-read -->
  m-deep-fetch` edge. Acyclicity holds against the full graph: nothing reaches
  back to `m-op-list`, and the untouched `m-cascade-delete --> m-op-list` edge
  stays layered above it as before.

The snapshot slice's DAG closure no longer contains `m-op-list`: a plain-value
target may claim `m-navigate` and `m-deep-fetch` without carrying any list scope
at all. A managed target composes its list surface **over** deep fetch instead of
navigation depending on it — which is what `m-op-list`'s own contract text
already described ("this laziness is what makes the deep-fetch round-trip
guarantees observable"). Compatibility cases are untouched: the `m-op-list-*`
cases keep their managed-lifecycle tags, and the profile gate stays
tagged-case-union based, so nothing about the corpus moves. Language specs are
updated to match: the Python snapshot-lifecycle spec
(`languages/python/spec/python.md`) drops its `op_list` prerequisite and scope
row, leaving `m-db-port` as its sole unclaimed prerequisite, and no
`parallax.core.op_list` scope is ever created; any language enforcement tooling
that mirrors these edges is re-pinned mechanically, not redesigned.

The normative edges and their rationale are recorded in
[`core/spec/modules.md`](../../core/spec/modules.md); the header prose of
[`core/spec/m-navigate.md`](../../core/spec/m-navigate.md),
[`core/spec/m-deep-fetch.md`](../../core/spec/m-deep-fetch.md), and
[`core/spec/m-op-list.md`](../../core/spec/m-op-list.md) restate the inverted
direction consistently. The Python side is
[`languages/python/spec/python.md`](../../languages/python/spec/python.md).
