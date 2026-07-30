# Temporal plans retain complete predecessor state and authored close cause

Every surviving temporal mutation against existing state retains one immutable,
complete predecessor row in its Write Observation. Successors refer to that row
as carried state or changed state, while the predecessor close records whether
the authored verb superseded or terminated state; an update is supersession and
a terminate is termination even when a Bitemporal head or tail survives. The
Write Target and concurrency gate remain separate facts rather than being
inferred from this predecessor value.

Transaction-Time-only and Bitemporal writes use the same
`TemporalObservation(predecessor, transaction_time_basis)` variant; the Temporal
Facet already determines expansion topology. The Transaction-Time Basis is only
`LatestPinned | HistoricalPinned`, the information needed to license or reject
an ungated locking-mode write. It is not a full read Pin or lock-scope claim. In
locking mode the resolving read locks the one selected current physical
milestone row; it does not lock the whole temporal edge, lineage, or every
Valid-Time rectangle sharing the primary key. A multi-rectangle mutation must
therefore materialize and observe each affected rectangle.

Keeping only identity, temporal bounds, or a loose optional observation would
save plan data but force temporal expansion, Audit Provenance, or SQL lowering
to reconstruct meaning or perform another read. Retaining the complete
predecessor makes carried provenance and physical rectangle addressing
deterministic, and preserving the authored close cause avoids the information
loss in prior art where both causes eventually become generic close updates.
This builds on ADR 0033's distinction between revision and termination and ADR
0037's provenance-neutral successor and close dispositions.
