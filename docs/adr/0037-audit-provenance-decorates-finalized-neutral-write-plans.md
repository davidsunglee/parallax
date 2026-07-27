# Audit provenance decorates finalized neutral write plans

Audit Provenance enriches a finalized neutral write plan after Unit Work coalescing and temporal milestone planning but before ordinary SQL lowering. The decorator consumes accepted Audit Metadata, the boundary-captured Subject Identity, the attempt's lazily captured Transaction Instant, and any observed predecessor state. It assigns provenance only to rows and assignments in a nonempty flush: canceled and net-zero writes that never flush receive no stamps and do not force a Clock Strategy read, temporal topology remains owned by the temporal planners, and SQL/dialect modules remain audit-unaware because they lower the resulting explicit attributes normally.

The finalized-plan interface exposes provenance-neutral write dispositions. It
distinguishes a row that starts a lineage, a successor that carries represented
state, a successor that changes represented state, an ordinary revision close,
and an explicit State Termination. The planner that creates the topology
already knows these facts and records them without naming an audit attribute.
The Audit Provenance decorator consumes those dispositions rather than
reverse-engineering mutation verbs or depending directly on Transaction-Time,
Bitemporal, or batch planner implementations.

The current Python implementation composes this decorator at its single write-lowering seam. That placement is an implementation waypoint rather than ownership by a lifecycle extension. When write preparation moves behind the hub-owned Entity Row Codec, the decorator moves into that accepted write pipeline and Snapshot depends only on the codec capability; the Audit Provenance semantics, finalized-plan ordering, and language-neutral module boundary remain unchanged.

A readless Non-Temporal predicate update remains one statement and stamps every matched row's revision provenance, even when an assignment happens to equal the stored value; discovering equality would require the read this write family intentionally avoids. Matching zero rows remains a successful no-op with no provenance change. Materialized temporal writes retain their existing effective-change and no-op rules.

The catalog records the resulting direct edges:

```text
m-principal --> m-core

m-unit-work --> m-principal
m-snapshot-read --> m-principal
m-op-list --> m-principal

m-audit-provenance --> m-principal
m-audit-provenance --> m-metamodel
m-audit-provenance --> m-model-formation
m-audit-provenance --> m-inheritance
m-audit-provenance --> m-temporal-read
m-audit-provenance --> m-unit-work
```

Both modules are active, case-covered common-runtime behavior claimed by
`slice-snapshot-1` and `slice-managed-1`. SQL, dialect, temporal, and batch
planning modules remain independent of Audit Provenance.
