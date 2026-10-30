# Entity Graph Construction publishes a node-indexed graph

`EntityGraphConstruction.publish(graph, lifecycle_states)` is the one
construction entry point, replacing `construct(build, state_factory=...)` and
its build callback, `EntityGraphWriter`, `NodeHandle`, and `ResolutionView`. The
graph is an `IndexedGraph`: node `i` answers its layout, its member row, and its
broad relationship values, where a loaded relationship names nodes by index.
Entity allocates an instance for every node before filling any, so a cycle
closes on an object that already exists, fills each node from its rows, then
calls `lifecycle_states` once with every instance in node order. The states are
buffered and counted before the first is attached, so a failing or miscounted
answer attaches none. Node 0 is returned; every call creates fresh instances.

The handles existed only to be undone. Snapshot's Root View is already a
node-indexed graph, so publishing through handles meant turning each index
into a handle and back into an index, plus a writer, a resolution view and a
state-factory call per node. Those layers were a large share of the per-object
cost of a read, and the handle protocol's generality served no caller that
could not produce an indexed graph as easily.

The boundary between Entity and its lifecycles stays. Snapshot's Typed
publisher and the conformance adapter's `ForeignLifecycleSource` — the second
managed lifecycle `m-unit-work-019` needs (ADR 0010) — both publish through it,
and the write side tells lifecycles apart by `lifecycle_state_of`. Removing the
boundary would move Pydantic allocation and instance state into Snapshot.
Ownership is unchanged: Entity selects the concrete class, allocates and fills
it, builds Value Objects, and attaches lifecycle state; each lifecycle owns the
graph it hands over and the state it answers.

`GraphConstructionError` keeps four codes: `entity-graph-invalid-entity`,
`-invalid-member`, `-invalid-value` and `-layout-mismatch`. Its `index` names
the node whose row holds the refused value. The six handle-misuse codes
(`-foreign-handle`, `-scope-closed`, `-allocation-closed`,
`-node-already-populated`, `-node-unpopulated`, `-invalid-root`) describe
mistakes the indexed graph cannot express and are removed. An empty graph and a
lifecycle-state count other than the node count are `-invalid-value`. Exceptions
the graph or the callback raise propagate unchanged.

Keeping `construct` beside `publish` as a compatibility path was rejected: the
advanced surface has no external callers, and two construction paths would
leave the slower one maintained for nobody.

This supersedes, in part, the Entity Graph Construction section of
[ADR 0007](0007-entity-classes-compose-into-explicit-sealed-metamodel-hubs.md).
