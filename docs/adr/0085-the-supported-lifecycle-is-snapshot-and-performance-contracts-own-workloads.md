# The supported lifecycle is snapshot and performance contracts own workloads

The core catalog describes the product we intend to implement: snapshot graphs
with explicit writes. We retire the managed-object slice, transaction identity
map, query-backed lists, cascade execution, process caches and coherence,
aggregation, and Valid-Time-Only formation instead of maintaining specifications
and reference-only machinery for unplanned features. This supersedes the two-slice
choice in [ADR 0019](0019-object-lifecycle-splits-into-snapshot-and-managed-slices.md)
and the managed-list surface in
[ADR 0025](0025-lifecycle-result-surfaces-sit-above-the-shared-fetch-algorithm.md);
[slices](../../core/spec/slices.md) and the
[module catalog](../../core/spec/modules.md) own the current scope.

The runtime, planning, read delivery, and snapshot publication stay separate
because they isolate execution conditions, SQL-free planning, stored-data
judgment, and value construction. Retiring the prospective managed consumer does
not erase those current responsibilities. Relationship dependency metadata and
model-evolution observations remain part of the accepted model; they do not
promise a cascade executor.

Performance work already measures the shipped implementation. Its shared contract
keeps deterministic workloads and dataset semantics, while each language owns its
capture instruments, report format, and thresholds. The reference-only authored-SQL
benchmark runner and conformance benchmark command are retired; the measured
workload inputs and retained evidence are preserved.
