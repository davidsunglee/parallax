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

For Relational Document Layout, complete predecessor state additionally retains
the raw Structured Column document alongside its decoded known members. A
temporal successor starts from that raw document and applies its declared path
assignments before binding the complete successor value, preserving unknown
keys written by a newer model version without another database read except
where the authored assignment replaces their containing structure. A `one`
Value Object assignment with an authored document recursively patches only the
declared members it names; assigning null replaces the occurrence with JSON null
and discards its descendants. A `many` assignment replaces its array whole.
Retaining only decoded members would satisfy the current model's shape while
silently destroying forward-version state during temporal chaining.

## Amendment (2026-08): a Temporal Observation retains the predecessor alone

The variant recorded above is
`TemporalObservation(predecessor, transaction_time_basis)`, where the
Transaction-Time Basis is `LatestPinned | HistoricalPinned` — "the information
needed to license or reject an ungated locking-mode write."

**Superseding decision:** the variant is `TemporalObservation(predecessor)`, and
the Transaction-Time Basis is retired from the observation algebra, the neutral
specification, and the locking-license rule it existed to serve.

The Basis described the **read**, not the milestone, while the observation it
rode on describes the milestone. Once an observation is filed under the
milestone it observed and resolved from the value being written, that mismatch
becomes a defect rather than a nuance: two reads at different as-of coordinates
resolving to one milestone would produce two observations equal in their
predecessor and unequal in their Basis, so an ordinary audit read of a row
already read at latest could revoke the license of a write the shared read lock
fully protected. There is nothing to license separately — a locking-mode close
addresses the milestone its own written value came from, and the observation
supplying that address is the record of the read that locked it. A read at a
finite Transaction-Time coordinate is refused by the Transaction-Time pin rule,
at the verb, under both Effective Concurrency Strategies, before any planning.

The lock-scope statement this ADR makes is unchanged and still load-bearing: the
resolving read locks the one selected current physical milestone row and not the
whole edge, lineage, or every Valid-Time rectangle sharing the primary key, so a
multi-rectangle mutation must still materialize and observe each affected
rectangle. What the amendment removes is the claim that the observation carries a
separate licensing classification beside that row.

Everything else recorded above is unchanged: the complete immutable predecessor
row, the authored close cause, the Write Target and gate remaining separate
facts, the shared variant across Transaction-Time-only and Bitemporal writes, and
the Relational Document Layout raw-document retention.

## Amendment (2026-08): an assigned occurrence replaces its subtree whole

The Relational Document Layout paragraph above records that "a `one` Value Object
assignment with an authored document recursively patches only the declared
members it names".

**Superseding decision:** an assignment of a Value Object occurrence **replaces**
that occurrence's subtree whole, at any depth, under every Storage Layout.
Nothing inside the replaced subtree survives: a declared member the authored
document omits is absent afterwards, and a key no member declares is gone. A
`many` assignment already replaced its array whole, and both cardinalities now
answer the same way, because an author stating an occurrence has stated a
complete value either way.

The patch rule made assignment mean two different things depending on a physical
decision the developer may not have made — a top-level occurrence's own column
was bound atomically under conventional Columns while the same assignment patched
member by member under Relational Document Layout. Round-trip is what decides it:
a Value Object is defined entirely by its content, so a write of `A` that does not
make the stored value equal `A` breaks the abstraction. Assigning null still
replaces the occurrence with JSON null and discards its descendants, which the
collapse leaves untouched.

The retention decision this ADR exists for is unchanged, and the collapse depends
on it: a temporal successor still starts from the retained raw Structured Column
document and still preserves unknown keys written by a newer model version
without another database read. What narrows is the scope of that preservation.
The unit of replacement is the **assigned occurrence**, never the row, so every
undeclared key outside every assigned occurrence still rides forward exactly as
recorded above — and every key inside one is gone, which is what the authored
assignment says.
