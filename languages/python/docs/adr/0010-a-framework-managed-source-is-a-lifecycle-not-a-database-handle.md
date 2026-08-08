# A framework-managed source is a lifecycle, not a Database handle

The keyed write verbs decide which verbs accept a value from its **provenance**
(`m-unit-work` *Write value provenance*), and the source that provenance names is
the managed value lifecycle — the machinery that materializes rows into instances
and attaches to each the state by which it later recognizes its own — never the
`Database` that issued the read. The Snapshot runtime ships exactly one such
lifecycle, so every `Database` over one store is one source: a value any handle
read is `thisSource`, and `ForeignLifecycle` names a value some *other* lifecycle
produced. `validate_write_value` therefore reads only `lifecycle_state_of` (is
there any managed state?) and `snapshot_state_of` (is it this lifecycle's?), and
`SnapshotNodeState` carries `entity`, `views`, `pin`, and `edge` and no handle
identity, which is the same stance `_ConnectedModel` already takes — "two
Databases over one Domain Model hold equal state and neither is preferred".

The load-bearing consequence is what provenance does *not* promise. Provenance
answers which lifecycle produced a value; it carries no guarantee about what an
earlier read saw, and none is asked of it. The framework's axis of guarantee is
**did this unit of work observe this row**: `UnitOfWork._observations` is fresh
per unit of work and is populated only by `record_observations`, which runs inside
the transaction-scoped read that recorded it. `Database.find` deliberately records
nothing — "there being no unit of work to observe into, this passes the executor
no observation collector at all" — and it is a first-class part of the read
surface, not an escape hatch.

So the arrangement a handle-shaped notion of source would have caught,
`dbA.find(...)` followed by `dbB.transact(lambda tx: tx.update(...))`, is the
*same situation* as `db.find(...)` followed by `db.transact(...)` on one handle.
Both hand a write a value whose read the writing unit of work did not observe, and
both reach the identical outcome, decided entirely by what the target declares:

- A **versioned** target raises `UnobservedVersionError` when the flush plans the
  write — the new version is always `observed + 1`, and the framework issues no
  resolving `SELECT` on a keyed write's behalf, in either concurrency mode.
- A **temporal** target raises `UnobservedMilestoneError` synchronously at the
  verb, before anything is buffered: the close resolves its milestone from the
  value's own `Edge`, and a value carrying no observation of this unit of work's
  has nothing to close against.
- A **plain unversioned, non-temporal** target **succeeds**. The planner emits an
  update addressed by primary key with `UNVERSIONED` concurrency, because there is
  nothing to gate on. That is what unversioned means, and it is the correct
  outcome for both arrangements alike.

Those are one rule family — the prior-observation license — enforced at two sites,
plus the orthogonal finite-Transaction-Time-pin rule (`validate_source_pin`), which
refuses a value read at a finite Transaction-Time instant at every keyed verb
whatever its provenance.

The alternative considered was making a `Database` handle a source, so that
`dbB` would refuse `dbA`'s value as `ForeignLifecycle`. It was rejected. It would
introduce the framework's first per-handle distinction, on an axis orthogonal to
the one that carries the guarantees: no framework state is per-handle, so there is
nothing a cross-handle value could corrupt that a same-handle one could not. It
would be paid for in the exported `find` / `find_history` signature — which take
metadata, dialect, target, and port, and no handle — plus new identity on every
materialized node, plus a normative `m-unit-work` amendment declaring a handle to
be a source. And it would buy no safety even then: the one case where it would
change an outcome is the plain unversioned update, which stays accepted on a
single handle for exactly the same reason, so the arrangement it refuses is
neither more nor less observed than the one it admits. A new normative notion of
source, wearing the clothes of a bug fix, is the wrong trade at that price.

Under this decision `ForeignLifecycle` is reachable only from a second managed
lifecycle, and the Python *runtime* is one. No read the Snapshot performs produces
a foreign value, so the conformance adapter **supplies** the second source rather
than synthesizing a value for it: `parallax.conformance.another_source` executes
its own query through the shared find executor and materializes what that read
returned itself — its own merge over the Snapshot Graph Input, its own Entity
Graph Construction drive, its own per-node state, and its own recognizer for the
values carrying that state.

That is a second lifecycle by the definition `m-unit-work` gives — machinery that
materializes values from reads and attaches the state by which it later
recognizes its own — and a source is machinery, not a shipped product. So
`m-unit-work-019` arranges what it says it arranges: a value a read through
another framework-managed source produced, refused by both verb families. It
shares the port with the source under test on purpose, because a connection is
not a source under this very decision.

`validate_write_value` reads only `lifecycle_state_of` (is there managed state?)
and `snapshot_state_of` (is it this lifecycle's?), so the classifier's answer
would be the same for a value built from literals — which is exactly why building
one would not witness the rule: it would arrange the token rather than the value
(`m-case-format` *Keyed write action steps*). What the case is still **not**
evidence of is that a second *shipped* lifecycle would interoperate correctly
across the rest of the runtime; the adapter's source materializes flat graphs and
writes nothing.

No compatibility case witnesses the cross-handle arrangement, deliberately. Under
this decision a value from a second handle is definitionally not another source,
so there is no neutral behavior for a case to observe — the arrangement collapses
into `thisSource`, which `m-unit-work-018` already witnesses, alongside
`m-unit-work-017` for `unmanaged` and `m-unit-work-019` for `anotherSource`. A
case built around two handles would pin a Python-shaped implementation detail into
the neutral corpus, which states provenance and never how to obtain it. The
equivalence is held instead by Python unit tests, which pin that a second
`Database` over one store and a non-transactional `Database.find` on the writing
handle classify identically — the second being what fails first if handle identity
is ever threaded through the read path.
