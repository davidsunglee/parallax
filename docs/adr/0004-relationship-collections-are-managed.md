# Relationship collections are managed

Object relationship collections are Parallax-managed collections, not plain arrays. Adding to a relationship collection wires join or foreign-key values from the owning object and registers the related object change in the active transaction, while removing from a relationship follows relationship metadata: dependent relationships delete or terminate the child, non-dependent relationships dissociate when possible, and impossible dissociations fail explicitly.

Relationship collections are async iterable and expose the same read helpers as `ParallaxList`, including `toArray`, `first`, `firstOrNull`, `single`, `singleOrNull`, `count`, `isEmpty`, and `notEmpty`. Mutation methods such as `add` and `remove` require an active transaction. In the first TypeScript API, `add` accepts a create payload for a dependent relationship and creates a new owned child, while `remove` accepts a managed child from a dependent relationship and deletes or terminates it; adding existing child objects, reparenting, and non-dependent linking are deferred.

Non-dependent association mutation is deferred to a future explicit `link` / `unlink` surface. In v1, callers change non-dependent associations through FK updates or explicit join-entity writes.
