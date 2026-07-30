# Temporal mutations expand in place after ordering

A surviving temporal mutation remains one private, indivisible planning unit
through compatible batching and dependency ordering. Once its position in the
pending stream is fixed, the Write Planner expands its Temporal Write Topology
in place: the predecessor close appears first and its zero-to-three successors
follow immediately in their semantic order. No unrelated Planned Write may be
interleaved within that topology.

The private planning unit disappears after expansion. The finalized Write Plan
needs neither an `AtomicUnit` wrapper nor a public group identifier because
ordering has already fixed adjacency. This keeps temporary constraints out of
the lowering contract while ensuring that batching or foreign-key movement
cannot separate a close from the rows that replace it.

Reladomo expands temporal topology before queue combination and compensates
with specialized dated-operation movement rules. Parallax deliberately orders
the indivisible mutation first and expands afterward, localizing the temporal
constraint and allowing one ordinary finalized algebra for temporal and
Non-Temporal writes.
