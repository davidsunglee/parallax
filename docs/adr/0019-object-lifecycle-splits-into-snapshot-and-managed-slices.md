# Object lifecycle splits into a snapshot slice and a managed slice

The ORM landscape divides along two separable axes — identity/uniquing scope
(none → graph-local → transaction → process) and change tracking (explicit
writes → operation-buffered mutation → flush-time dirty checking). Parallax
takes two deliberate positions on that plane as two conformance slices that
replace `slice-mvp-1` (which shipped a hybrid: managed mutation without any
identity guarantee, a configuration in which two managed instances of one row
can buffer conflicting updates). `slice-snapshot-1` reads **Snapshot Graphs** —
typed, graph-locally identity-resolved value graphs pinned whole-graph at one
set of as-of coordinates, strictly closed-world — and writes only through
explicit APIs, with no diffing write-back. `slice-managed-1` reads **managed
objects** interned in a transaction-scoped **Identity Map** and mutates them
through operation-buffered setters. Two new modules carry the distinguishing
behavior: `m-snapshot-read` (graph materialization) and `m-identity-map`
(interning); `m-unit-work` sheds its identity promise (previously delegated to
deferred `m-process-cache`, unproven, and disclaimed by the TypeScript
implementation) and becomes purely operational.

**Identity scope is the unit of work; there is no session.** A
Hibernate/SQLAlchemy-style scope spanning transactions was rejected: the
conversation pattern is served honestly by detach → edit → merge-back gated by
`m-opt-lock` (Reladomo's model, already spec'd in `m-detach`), and
cross-transaction value reuse is a freshness claim belonging to the deferred
`m-process-cache`/`m-coherence` family — prior art agrees (SQLAlchemy expires
all cached state at every commit by default; Hibernate and EF Core steer away
from long-lived sessions/contexts; Reladomo has no session object at all). The
word "session" is reserved, unspent, for a possible future conversation scope.
The exclusion is not a one-way door, kept so by two drafting rules: managed
objects detach when *the scope that owns them* ends (today, the transaction),
and cross-transaction identity is *not promised* but never mandated-distinct —
no spec text or corpus case may assert that two transactions must return
different instances.

**The Identity Map key is (entity family, primary key, lowered as-of coordinate
per declared axis)**, following Reladomo's dated-cache uniquing: a managed
temporal object is a view of its milestone timeline pinned at a coordinate, so
same-key views at different pins coexist in one transaction, and every held
view reflects an in-transaction milestone write at its own pin. The entity
component normalizes to the inheritance family, so a row read through the
abstract root and through a concrete subtype interns to the same object.
`history()`/`asOfRange` results are edge-pinned at each milestone's from-instant
(Reladomo's `equalsEdgePoint`, which uses the from column for half-open
intervals), making every version navigable at its own pin; combining history
with includes is staged behind a feature tag rather than rejected, per the
no-mandated-negatives rule.

**Relationship access never issues SQL implicitly from a snapshot graph, and
loading has one semantic with per-language triggers.** Core defines a single
deferred-load semantic — resolves only through the live unit of work,
propagates each source's as-of coordinates, batches over ad-hoc object sets
(`m-deep-fetch` machinery) — and languages choose the trigger idiom: eager
includes, an explicit load call, or transparent property access in synchronous
languages. This deliberately diverges from Reladomo's implicit per-object lazy
loading; with identity scoped to the transaction, the classic lazy-loading
hazards (loads escaping the transaction, N+1 in view code) are structurally
absent, and round-trip counts stay a portable corpus contract. On a detached
object a deferred load raises a defined Parallax Error.

**Held managed objects transition to detached when the scope that owns them
ends — today, the unit of work, whether it commits or aborts** — reads work,
mutations land only in the object, persistence goes through merge-back in a new
transaction — and on abort their visible state first reverts to
as-materialized values, so an escaped object never shows discarded writes.
Write-through outside transactions (the Reladomo/ActiveRecord model, where a
bare setter executes standalone DML) was rejected as hidden I/O,
consistent with the TypeScript decision that writes require explicit
transactions (TS ADR 0021).
