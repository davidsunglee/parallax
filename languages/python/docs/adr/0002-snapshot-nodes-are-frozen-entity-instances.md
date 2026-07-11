# Snapshot nodes are frozen entity instances with raising unloaded access

Snapshot graph nodes are instances of the user's own entity classes with
`frozen=True`, not wrappers or generated node types. Accessing a relationship
outside the include set raises `UnloadedRelationshipError` (with `is_loaded`
as the non-raising probe); loaded-empty is `[]` and loaded-null is `None`.
Freezing makes both core snapshot invariants structural rather than
behavioral: the graph cannot issue SQL because nothing is lazy, and edits
cannot masquerade as persistence because nodes cannot be edited at all —
mutable-but-inert nodes (rejected) would look exactly like every managed ORM
surface while silently persisting nothing.

Two accepted costs: unloaded state is invisible to static typing (inherent to
closed-world graphs in a dynamic language; compensated by the precise error),
and cyclic back-references are wired during materialization through an
implementation-private setattr backdoor. Freezing is also what makes ADR 0003
sound.
