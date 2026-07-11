# Snapshot nodes are frozen entity instances with raising unloaded access

Snapshot graph nodes are instances of the user's own entity classes with
`frozen=True`, not wrappers or generated node types. Accessing a relationship
outside the include set raises `UnloadedRelationshipError` (with `is_loaded`
as the non-raising probe); loaded-empty is the empty tuple `()` and
loaded-null is `None`. Pydantic's `frozen=True` is only faux-immutable — it
rejects attribute assignment but cannot deep-freeze field values — so every
collection-valued node field is an immutable type: included to-many
relationships and many-cardinality value-object members are **tuples**, never
lists, keeping `node.items.append(...)`-style deep edits unrepresentable
rather than merely discouraged. Hashability is conditional, not promised: a
node is hashable exactly when hashing terminates over hashable field values
(scalars and value objects always; to-many tuples when their elements are; a
loaded back-reference cycle makes the hash non-terminating). Freezing makes
both core snapshot invariants structural rather than behavioral: the graph
cannot issue SQL because nothing is lazy, and edits cannot masquerade as
persistence because nodes cannot be edited at all — mutable-but-inert nodes
(rejected) would look exactly like every managed ORM surface while silently
persisting nothing.

Two accepted costs: unloaded state is invisible to static typing (inherent to
closed-world graphs in a dynamic language; compensated by the precise error),
and cyclic back-references are wired during materialization through an
implementation-private setattr backdoor. Freezing is also what makes ADR 0003
sound.
