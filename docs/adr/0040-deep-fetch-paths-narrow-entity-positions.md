# Deep fetch paths narrow entity positions

Deep Fetch paths may start from a subtype without changing the Object Query's
result set. Canonically, each path is a closed object with an optional
root-position `narrow: {entity, to}` followed by relationship segments whose
existing `narrow: {to}` values constrain their target positions. This
alternating position-and-relationship model makes inherited `Dog.owner` retain
relationship identity `Animal.owner` while applying only to Dog-family roots,
and it supports further inheritance boundaries without per-hop source metadata.

A path-root Narrow guards existing root objects and creates no relationship
view; a segment target Narrow populates a distinct Narrowed View. Broad and
target-narrowed views therefore remain separate fetches, and distinct
path-root source sets remain distinct hops rather than being unioned. The
slightly higher round-trip count keeps loaded-view identity, branch provenance,
deduplication, and statement-count expectations explicit.

Hop identity keys on what each position actually distinguishes: the resolved
source set at the path root, where a guard creates no view, so two guards
resolving to one set are one hop and a guard admitting every root object is the
broad path; and the authored narrow flag at a segment, where the view key is
derived from the authoring rather than from the resolved set. Reusing a broad
view to serve a narrowed fetch is rejected outright rather than deferred: it
would make an authored path's statement cost depend on which other paths were
authored beside it, and on whether the storage layout's broad read even projects
the narrowed branch's members.

The canonical path-shape change lands atomically across the operation schema,
inheritance and Deep Fetch semantics, SQL planning, compatibility cases, and
claiming language frontends — no intermediate state exists in which the schema
admits a path-root Narrow that a frontend does not emit or a dialect does not
lower.
