# Concurrency mode determines write gates uniformly

Every observation-requiring write uses the same closed concurrency decision.
Optimistic mode emits a Version Gate for a versioned Non-Temporal update or
delete and a Temporal Gate for a temporal close. Locking mode emits neither
predicate and records an explicit Ungated decision because the required prior
observation's shared read lock provides the concurrency guarantee. Observations
remain mandatory in both modes.

Planned Updates and Planned Deletes encode gate applicability as
`NonTemporalConcurrency = Unversioned | Versioned(VersionGate | Ungated)`.
Planned Closes carry `TemporalGate | Ungated` directly because a temporal close
always requires an observation. This structure distinguishes a genuinely
unversioned write from an observation-bound locking write without a nullable
gate or a universal no-gate sentinel. `Unversioned` describes a finalized
write; it is not a no-observation member of the planning-input algebra.

Gate payloads retain only what lowering needs to add the equality predicate:
`VersionGate(attribute: AttributeIdentity, observed_version: int)` and
`TemporalGate(start_attribute: AttributeIdentity, observed_start: Instant)`.
`Ungated` is payload-free. Advanced versions and close instants already appear
in assignments, while full observations and concurrency mode are consumed
during planning rather than repeated in gates.

Affected-row classification follows that decision. A gated shortfall is a
retriable-when-enabled Optimistic Lock Conflict; an ungated
observation-requiring shortfall is a non-retriable Stale Write. An unversioned,
observation-free keyed shortfall remains a Missing Target, and every excess is
Cardinality Corruption.

The previous Python path applied this rule to versioned updates and temporal
closes but always retained the observed-version predicate on a versioned
delete, even in locking mode. That made gate meaning depend on the mutation
kind and allowed a locking failure to masquerade as an optimistic conflict.
Parallax removes that asymmetry; Reladomo likewise appends its optimistic
predicate only under optimistic participation.
