# m-temporal-read — As-Of Temporal Reads

`m-temporal-read` owns temporal coordinates and automatically injected as-of
predicates over half-open intervals. The operation nodes belong to
`m-op-algebra`, SQL emission belongs to `m-sql`, infinity representation belongs
to `m-core`/`m-dialect`, and temporal writes belong to `m-txtime-write` and
`m-bitemp-write`.

The supported temporal Entity shapes are **Transaction-Time-Only** and
**Bitemporal**. Valid-Time-Only is not supported. The module's Model Compiler
produces the immutable Temporal Facet ("The Temporal Facet", below), which
derives each Entity's applicable root-owned As-Of Axes without copying axis or
Attribute Metadata.

## Canonical terminology

The following mapping is exhaustive and normative across core metadata,
descriptor serde, operations, relationship propagation, language bindings,
writes, and physical storage:

| Surface | Valid Time | Transaction Time |
|---|---|---|
| Meaning | When a fact is true in the modeled world | When a fact is present in the database |
| Core dimension | `ValidTime` | `TransactionTime` |
| Core shape variant | declared by `Bitemporal` | declared by `TransactionTimeOnly` and `Bitemporal` |
| Descriptor `temporality` deriving it | `bitemporal` | `transaction-time` and `bitemporal` |
| Operation `dimension` | `valid-time` | `transaction-time` |
| Derived start Attribute | `validStart` | `txStart` |
| Derived end Attribute | `validEnd` | `txEnd` |
| Framework-fixed start column | `from_z` | `in_z` |
| Framework-fixed end column | `thru_z` | `out_z` |
| Python query keyword | `valid_time` | `tx_time` |
| Python Pin/Edge accessor | `valid_time` | `tx_time` |
| Python framework base | supplied by `Bitemporal` | supplied by `TxTemporal` and `Bitemporal` |
| Compatibility Pin key | `valid-time` | `transaction-time` |
| Relationship propagation coordinate | source Valid-Time coordinate | source Transaction-Time coordinate |
| Neutral / Python write lower-bound argument | `validFrom` / `valid_from` | transaction clock supplied by the handle |
| Bitemporal bounded-write upper bound | `until` (a Valid-Time bound) | not caller-authored |
| Optimistic temporal observation | not an optimistic key | observed `txStart` / physical `in_z` |
| Finite-pin mutation error | writable retroactive correction | `transaction-time-pin-read-only` |

The retired business/processing vocabulary is not an alias. Physical column
names remain stable but never identify a dimension. Neither the Attribute names
nor the columns are authored: a descriptor spells the `temporality` profile and
`m-descriptor` derives both. A public `AsOfAxis`
authoring abstraction does not exist; the core metadata value is
`AsOfAxisMetadata(dimension, start_attribute, end_attribute)`.

## Interval and metadata model

Every axis is `[start, end)`. An axis is current when `end = infinity`. Axis
Metadata contains no query default, inclusivity option, name, kind, or physical
column. Both referenced Attributes are distinct local Timestamp Attributes of
the containing Entity.

Transaction-Time-Only declares Transaction Time. Bitemporal declares Valid
Time followed by Transaction Time. Under inheritance, only the root declares
axes and every descendant receives the same effective set through the Temporal
Facet.

## The Temporal Facet

The Model Compiler consumes the Inheritance Facet and produces the immutable
`TemporalFacet` under `FacetKey(m-temporal-read)`; typed access is this
module's `view(model) -> TemporalFacet` function. The module contributes no
Rule Set or Issue Codes — malformed axes are rejected by `m-metamodel`'s
foundational rules and axis root ownership by `m-inheritance` before any
compiler runs.

```text
TemporalFacet
  shape(EntityIdentity) -> TemporalShape | absent
  axis(EntityIdentity, TemporalDimension) -> AsOfAxisMetadata | absent

TemporalShape =
    NonTemporal
  | TransactionTimeOnly(transaction_time: AsOfAxisMetadata)
  | Bitemporal(valid_time: AsOfAxisMetadata,
               transaction_time: AsOfAxisMetadata)
```

Both lookups are total, nonthrowing, and expected amortized O(1). `shape`
covers **every** accepted Entity and returns absent only for an identity
outside the accepted Metamodel: an Entity's shape derives from its family
root's declared axes (the Inheritance Facet supplies the root), and a
standalone Entity is its own root. `axis` returns absent for an unknown
identity or a dimension the Entity's shape does not declare. The closed
`TemporalShape` algebra makes the unsupported Valid-Time-Only formation
unrepresentable: no variant declares Valid Time without Transaction Time.

Each `AsOfAxisMetadata` value is the declaring root's accepted value by
reference — its start and end Attribute Identities keep the root Entity —
never a copied axis or Attribute Metadata. Every position in one family
returns the same values as its root.

## Latest and Now

Every canonical temporal read names exactly one selection for every dimension
the queried Entity declares. A selection is an `asOf`, `asOfRange`, or `history`
node. This completeness rule is model-aware: the operation schema admits the
individual nodes, while validation against the queried Entity verifies that its
declared dimensions are covered exactly once.

**Latest** is the authoring default for an omitted Transaction-Time selection.
The authoring surface normalizes that omission to an explicit
`asOf(transaction-time, Latest)` node before producing the canonical operation.
Latest is the infinity sentinel and lowers to the single current-row predicate
`end = infinity`.

Valid Time has no omission default on a Bitemporal Entity. Omitting it is an
error because `Latest` would make a substantive claim about the business
timeline rather than merely selecting the database's current knowledge. This
asymmetry follows Parallax's own contract; Reladomo's temporal defaults are
prior art rather than a second normative surface.

There is no **Now** coordinate or operation variant. A caller may pass a finite
instant obtained from its current clock, and that ordinary finite coordinate
lowers to interval containment, `start <= d and end > d`. It is not synonymous
with Latest, and canonical descriptor/operation serde never uses `now` as a
coordinate spelling.

For a dimension pinned to coordinate `d`:

| Coordinate | Injected predicate | Binds |
|---|---|---|
| Latest | `end = ?` | `[infinity]` |
| finite `d` | `start <= ? and end > ?` | `[d, d]` |

The injected temporal terms follow the user predicate in canonical bind order.
For Bitemporal reads, Valid-Time terms precede Transaction-Time terms.

## Operations

```text
asOf(operand, dimension, Latest | finite instant)
asOfRange(operand, dimension, start, end)
history(operand, dimension)
```

- `asOf` pins one dimension. Every declared dimension has its own explicit
  selection in the canonical operation.
- `asOfRange` scans every milestone whose interval overlaps `[start, end)`.
- `history` removes the injected predicate for its selected dimension and
  returns the full milestone chain.

For a Bitemporal Entity, a query selects both dimensions independently. The
authoring surface may omit Transaction Time, which normalizes to explicit
Latest, but it MUST select Valid Time. The canonical nested operation order is
Valid Time outside Transaction Time, which produces Valid-Time binds first.

| Valid-Time coordinate | Transaction-Time coordinate | Physical predicate |
|---|---|---|
| Latest | Latest | `thru_z = ? and out_z = ?` |
| finite `v` | Latest | `from_z <= ? and thru_z > ? and out_z = ?` |
| Latest | finite `t` | `thru_z = ? and in_z <= ? and out_z > ?` |
| finite `v` | finite `t` | `from_z <= ? and thru_z > ? and in_z <= ? and out_z > ?` |

The final row means: at Transaction Time `t`, which fact was valid at Valid
Time `v`?

## Pinning, edges, and relationships

A Pin contains every selected dimension that is pinned rather than scanned; its
coordinates may be Latest or finite. An Edge contains one finite start instant
for every declared dimension of a materialized milestone. History and range
results use the milestone's own start as their Edge coordinate.

Relationship traversal propagates selections by dimension, never by physical
column or positional axis. A target that declares the same dimension receives
the source selection; a target without it receives no selection. An omitted
Transaction-Time selection at the authoring root is first normalized to Latest
and that normalized value propagates through the graph. A temporal target
reached from a source that declares no matching dimension selects Latest for
that unmatched dimension.

## Writes

The handle supplies the finite Transaction-Time clock instant used to close and
open Transaction-Time intervals. Callers do not author it as Latest or Now.
Transaction-Time-Only writes use that clock and no Valid-Time argument.

Bitemporal writes receive `valid_from`; bounded `insertUntil`, `updateUntil`,
and `terminateUntil` additionally receive `until`, with
`valid_from < until`. These are Valid-Time coordinates. Transaction-Time
coordinates still come exclusively from the handle clock. The physical DML
continues to use `from_z`/`thru_z` and `in_z`/`out_z`.

## Verification

Compatibility cases distinguish authoring-defaulted/explicit Latest from finite
Now, prove boundary behavior at `start` and `end`, exercise all four Bitemporal
coordinate combinations, propagate pins across relationships, expose finite
milestone Edges, and verify Transaction-Time-Only and Bitemporal writes without
changing physical columns or canonical SQL shape.

The temporal specification, descriptor/operation schemas, compatibility cases,
generated artifacts, glossaries, and language specs switch to this vocabulary
and pass their contract gates before runtime temporal behavior is changed.
There is no temporary translation that a later dependency-inversion step must
reinterpret.
