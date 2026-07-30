# Deferred Execution Features are explicit Snapshot debt

Snapshot owns a private immutable `_DEFERRED_EXECUTION_FEATURES` set for valid,
specified query forms whose execution is deliberately staged outside the active
Conformance Slice; `snapshot-history-includes` is the initial entry. The set is
expected to become empty, and every nonempty entry is reviewable implementation
debt: a Feature already claimed by the active slice but missing in code is a
defect and cannot be listed. This state belongs neither to the database
provider, Dialect, connected Hub, nor leased Database Port because it describes
Snapshot execution completeness rather than provider variability. Snapshot
classifies its privately lowered canonical operation against this set; the
lifecycle-neutral Find Query carries no Snapshot feature tags. The set is one
package-owned constant shared by every Database, with no application,
environment, provider, or adapter customization. An entry is added only with
the defining core behavior and Feature tag, explicit slice deferral, Python
specification entry, and zero-I/O rejection coverage, plus a deferred-ledger
record only when the deferral would otherwise lack a canonical home. An entry
is removed only when execution, compatibility and API coverage, the slice
claim, specification, and any applicable ledger record advance atomically.

A match raises Snapshot's `DeferredFeatureError` with stable code
`execution-feature-deferred` and every matching canonical Feature tag in
ascending order. This public name describes implementation staging directly
rather than preserving the rejected database-provider capability
interpretation. Exact-hub ownership is checked first, so a foreign-hub query
always raises `QueryOwnershipError(query-owner-mismatch)` without exposing a
deferral result.

The classifier belongs only to modeled Snapshot reads. Predicate-selected
writes first enforce their ordinary mutation-compatible Find Query contract;
a read-shaped query therefore raises
`QueryDefinitionError(query-not-mutation-compatible)` rather than a deferral
error.

Snapshot centralizes lowering, exact-hub ownership, and deferral classification
in one private `preflight_find` seam returning the local `LoweredFindQuery`.
Database, Transaction, and Session read boundaries reuse it before any new
connection acquisition or Database Port access.
