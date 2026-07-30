# Readless predicate writes are ordering barriers

A Readless Write partitions the pending write stream into independently
reorderable regions. The Write Planner may coalesce, batch, and dependency-order
writes within each region, but neither a preceding nor following write may move
across the readless Predicate Write Target, which retains its authored position
between those regions. The barrier is private planning structure and does not
become a group identifier or wrapper in the finalized Write Plan.

The finalized `PredicateTarget` carries only its typed Predicate because the
enclosing Planned Update or Planned Delete already owns the Entity Identity. Its
presence implies unversioned Non-Temporal concurrency, unrestricted affected-row
count, and barrier behavior; it repeats no keys, observations, pins, concurrency
data, or barrier flag. A predicate write requiring observations materializes
into singleton Key Targets before finalization and therefore cannot retain a
Predicate Target.

Unlike a keyed or materialized write, a readless Predicate does not reveal its
exact read/write set during planning. Moving another write across it could
change which rows the Predicate matches and therefore change transaction
semantics. Treating the entire stream as globally reorderable could produce
larger batches, but only by assuming non-overlap the planner cannot prove.
Reladomo's corresponding predicate delete is likewise immovable relative to
other queued operations.
