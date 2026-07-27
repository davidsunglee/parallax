# Audit provenance distinguishes revision, state change, and termination

Every audited Entity carries original-creation principal and instant plus the principal that formed its current revision. A Non-Temporal Entity carries the revision instant directly, while a temporal Entity derives it from `tx_start` and derives closure time from `tx_end`; temporal Entities additionally carry nullable `terminated_by` provenance set only by an explicit State Termination, not by an update that merely supersedes a milestone. The meaning is uniform: Transaction-Time-Only termination makes state absent from the current database state onward, while Bitemporal termination makes it absent from a Valid-Time point onward or only within a bounded window. The value is stored on the closed predecessor because absence has no row of its own; surviving Bitemporal head and tail successors remain non-terminated and receive null.

An explicit State Termination assigns `tx_end` and `terminated_by` in the same
gated close `UPDATE`, with the temporal end assignment first and the termination
principal second. It adds one bind and one changed column but no statement,
round trip, lock, Clock Strategy read, or second optimistic/stale-write check.
An ordinary update closure continues to assign only `tx_end`.

A Bitemporal Entity also carries state-change principal and instant: a changed rectangle receives the current transaction's values, while unchanged head and tail rectangles preserve those values from their predecessor, because `valid_start` says when state is true rather than when it was authored. `terminated_by` never means generic revision closure. For an update supersession, the successor revision or revisions whose `tx_start` equals the predecessor's `tx_end` carry the responsible Principal in `revised_by`; for State Termination, the closed predecessor carries that Principal in `terminated_by`. A separate revision-closure principal would duplicate the claimed mutation surface rather than adding value provenance.

Each successful temporal insert starts a Provenance Lineage, and successor milestones preserve that insert's creation provenance. Separate inserts start separate lineages even when they reuse one primary key in disjoint Valid-Time windows. Consequently, two mutation histories may produce identical current Valid-Time coverage but different creation provenance: two bounded inserts create two lineages, while one broad insert followed by a bounded termination leaves surviving rectangles in one lineage.

No audit attribute is an explicit optimistic-lock attribute: a Non-Temporal Entity may declare a separate version attribute, while a temporal Entity continues to use `tx_start` as its derived version analogue without `optimisticLocking: true`. This mode-specific shape avoids duplicated temporal facts, keeps database revision and domain-state authorship separately observable where rectangle splitting makes them diverge, and deliberately remains provenance rather than a complete write-event log.

The contract covers only the currently claimed mutation surface. MAY-tier recovery, purge, archiving, and increment verbs remain deferred because recovery must separately decide whether to preserve imported provenance or attribute reconstruction to the recovery Principal, while physical purge cannot retain row-local provenance.
