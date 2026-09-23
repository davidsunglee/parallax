# Typed results publish Wire form from result envelopes

A Wire Entity is finite because a read request selected a root position and a
finite tree of included relationship positions. That shape belongs to the
completed read, not to any Entity instance inside it. A Typed `Snapshot`
therefore retains the canonical IncludeTree produced by planning and the
existing CatalogedModel accepted for that read, and exposes `wire()` as an
explicit result operation. A Typed `SnapshotStream` exposes the element form
only while delivery is paused at a root of its current Page. Projection reads
already-published instance state and uses the same canonical Wire walk and
scalar/document codecs as direct Wire publication. It does not serialize
Pydantic output, execute another query, reclassify stored data, or capture an
execution authority.

The eager whole-result form preserves the envelope's root order, Pin, Model
Edition, and invalid verdicts. Element forms accept an eligible published Entity
or `InvalidData[Entity]` and an optional exact requested position. Position
resolution uses the retained original model and request shape; it performs no
graph membership scan. Projected nodes carry the exact Read Origin their Typed
counterparts already hold, while hydrated invalid graphs retain structural
inspection state without acquiring write evidence. Direct and projected Wire
results are not projection-capable receivers, enforced statically by
Entity-bounded receiver annotations and defensively at runtime by the absence of
the retained model capability.

Working state is bounded by the projection lifetime rather than retained on the
source graph. An eager call owns its Entity reader, identity memo, class/layout
checks, scalar encoder, and traversal frames only until the call returns or
fails. A stream creates the corresponding state lazily for the current Page,
holds inputs weakly, clears Entity outputs and compatibility facts at every
actual Page transition, rotates the scalar cache with delivery Pages, and
releases all projection state at exhaustion, failure, or close. The returned
eager storage is the required Wire envelope, frozen containers, invalid records,
and exact shared provenance closure. The measured six-scenario report records
retained output, transient and peak allocation, fresh projection time, same-call
reuse, and direct Wire publication beside the existing `model_dump` reading;
structural cost tests reject surviving projection scaffolding.

The retained IncludeTree memoizes the continuation answers the walk derives from
it, so one plan derives each of them once rather than once per published node.
That memo lives on the tree rather than in a side table keyed by plan, because
the tree is what a result envelope and its projection hold: a side table would
leave projection deriving the same answers again and would refill whenever plan
caching evicted its key. Its keys are drawn from the plan's own positions and
the accepted model's concretes, so it is bounded by the includes clause and the
model and never by roots or published nodes — the bound the retained shape
already carries. What a closed result keeps reachable therefore rises by a
bounded amount and remains bounded metadata lifetime.

Putting the operation on Entity was rejected. An Entity does not own the finite
IncludeTree or original model position, and a cycle detector would derive shape
from the object graph rather than from what the read requested. Installing a
Parallax serializer through `__get_pydantic_core_schema__` was rejected because
Pydantic serialization is an independent authored surface and the schema hook
can rebuild published values without lifecycle state. A standalone adapter
taking a private include tree was rejected because it would expose request
internals while leaving model and position admission as caller-managed
arguments. The result envelope is the deep boundary: it already owns the
publication facts, can preserve invalid and envelope metadata, and can keep the
projection wholly in memory without adding an Entity serialization door.
