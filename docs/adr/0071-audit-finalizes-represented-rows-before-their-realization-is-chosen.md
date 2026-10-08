# Audit finalizes represented rows before their realization is chosen

This supersedes the ordering and the port shape of ADR 0037. The provenance
semantics that record states for each origin and close cause are unchanged; what
changes is when they are applied and through which operations.

ADR 0037 decorated each finalized physical step after temporal topology was
chosen, through one generic operation over any Planned Write, and left a
Materialized Write Group's rows undecorated because they are rebuilt on demand.
Comparing produced successors as complete persisted state, and preparing what a
write persists once for both comparison and SQL, needs final audit values before
settlement decides whether a row is inserted or revises a row the attempt owns.
Decorating the eventual physical step cannot supply that: an insert and an owned
revision of one represented row would receive audit through different
operations, and a candidate merged away would never be audited at all.

The audit port therefore has three explicit operations. `finalize_row` receives
one represented row — a new lineage's opening, or a successor carried or changed
from its predecessor — once, before its realization is chosen, and returns its
final values with every value it adds stated as an executed assignment of the
row. `decorate_update` stamps a Non-Temporal update, keyed or readless, without
requesting a complete row or predecessor. `decorate_close` stamps a closed
predecessor. None changes topology, target, gate, cause, or affected-row policy,
and guards, removals, deletes, and milestones kept unchanged receive none. The
unit of work holds each answer to that contract before settlement uses it.

Every settlement path uses the same operations. A Materialized Write Group
finalizes its rows and decorates its closes and updates while it settles, and
keeps only what its audit added beside its compact evidence, so rebuilding one of
its steps audits nothing again. The audit-neutral default answers each input
itself and never resolves the Transaction Instant, and a group under it builds no
row merely to ask.

Alternatives considered: keeping the generic decorator alongside a successor
finalization hook, which would leave two operations able to stamp one row; and
manufacturing provisional insert steps to decorate before choosing a revision,
which builds and repairs physical plans. Both were rejected.

The contract lives in `core/spec/m-unit-work.md` (*The planning pipeline*) and
`core/spec/m-write-plan.md` (*Write Rows, Row Origin, and Close Cause*).
