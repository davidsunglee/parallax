# Typed and Wire are peer interfaces over one transaction

Typed and Wire reads and writes are peer interfaces over the same handle and,
inside a transaction, the same Unit Work, observation ledger, locking, and
Execution Log. A read in either representation may therefore supply the
transaction-owned evidence required by a later write in either representation.
A Wire Entity value may carry an opaque Source Hint selecting its exact Entity
and milestone, but the hint neither contains nor grants a Write Observation;
the transaction validates it against its own ledger, and Observation Keys remain
internal. This permits mixed and classless flows without public provenance
metadata or representation-specific transaction authority.

Python realizes the peer interface as `db.find` / `tx.find` for Typed work and
`db.wire.find` / `tx.wire.find` plus `tx.wire` verbs for Wire work. The Wire
namespace is a lightweight view, not a connection or transaction mode. This was
chosen over partitioned transaction protocols, a runtime `format=` argument,
overloaded Typed verbs, public observation values, flat `wire_*` methods, and a
general write-instruction method because the representation varies per call
while transaction semantics do not.
