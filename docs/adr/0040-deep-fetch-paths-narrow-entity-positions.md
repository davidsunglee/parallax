# Deep fetch paths narrow entity positions

Deep Fetch paths may start from a subtype without changing the Find Query's
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

The canonical path-shape change lands atomically across the operation schema,
inheritance and Deep Fetch semantics, SQL planning, compatibility cases, and
claiming language frontends.
