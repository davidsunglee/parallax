# Milestone targets use axis upper bounds independent of gates

Every finalized temporal close addresses a Milestone Target: the entity's
primary-key tuple plus the write-required exclusive upper bound on every As-Of
Axis. Valid Time, when present, uses the observed predecessor's exclusive end;
Transaction Time always uses Infinity so an operational close can address only
the current row. A Planned Close accepts only this target shape. The Write
Planner derives it from the complete temporal Write Observation and the
Transaction-Time currentness invariant, while that observation remains
available separately for successor composition and Audit Provenance.

The resolved compact form is
`MilestoneTarget(key_attributes, key_values, end_attributes, end_values)`.
The singular key-value tuple aligns with the complete canonical primary-key
shape. The nonempty end-attribute and end-value sequences align one exclusive
end per canonical As-Of Axis; each value is
`TemporalUpperBound = Finite(Instant) | Infinity`. No axis start, gate, or
concurrency mode is part of the target. The valid end may therefore be finite or
Infinity, while the transaction end is invariantly Infinity.

Target predicates are identical in locking and optimistic modes. Optimistic
mode may append the observed Transaction-Time start as a concurrency gate;
locking mode records an explicit ungated decision, but still uses every
Milestone Target component. The gate can therefore change conflict detection
without changing which stored temporal row the mutation means to close.

This separation is required for an optimistic write based on a historical
Transaction-Time observation. Its observed predecessor has a finite historical
transaction end, but the target still selects the current slot with
`tx_end = Infinity`; the old observed start in the Temporal Gate then fails
against a concurrently chained current row. Copying the historical transaction
end into the target could mutate already-closed history. Locking mode rejects
the same historical observation before planning because its read lock did not
license the current row.

A key plus the current Transaction-Time upper bound is insufficient for a
Bitemporal entity because several disjoint current Valid-Time rectangles may
share both values. The previous shape compensated only in optimistic mode with
an observation-derived Valid-Time discriminator, leaving locking-mode
addressing ambiguous. Reladomo's dated update predicates provide the prior-art
rule adopted here: primary key and every As-Of `to` bound identify the row,
operational writes constrain its `OUT_Z` upper bound to Infinity, and the
observed `IN_Z` start value is an additional optimistic gate.

## Amendment (2026-08): locking mode rejects no observation before planning

The reasoning recorded above justifies the target/gate separation partly by a
locking-mode refusal: "Locking mode rejects the same historical observation
before planning because its read lock did not license the current row."

**Superseding decision:** there is no such refusal. The pre-planning
locking-license check is retired along with the Transaction-Time Basis it read
(ADR 0042's amendment), and locking mode accepts exactly the observations
optimistic mode does.

What the separation now serves is the **stale** observation — one that named the
current milestone when it was read and that another transaction has since
superseded. Its target still selects `tx_end = Infinity` while its observed start
rides the optimistic gate, so closed history is never mutated and the conflict is
reported by the gate. A locking-mode close reaches that shape only in principle:
its observing read holds a shared lock on the milestone the observation names,
which is the milestone the close addresses. An observation of a milestone the
Transaction-Time past holds never reaches planning in either mode, because
mutating a view pinned at a finite Transaction-Time instant is refused at the
verb.

Everything else recorded above is unchanged: the Milestone Target is the primary
key plus one write-required exclusive upper bound per As-Of Axis, identical in
both concurrency modes, and the gate remains a separate optimistic-only addition.
