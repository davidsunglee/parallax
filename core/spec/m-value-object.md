# m-value-object — Embedded Value Objects

`m-value-object` is the **embedded composite element** a metamodel entity may
declare. It depends on `m-descriptor` (the entity it annotates).

A `valueObject` is an embedded composite sub-value of an entity (an address, a
money amount, a geo point) that has no identity of its own. Unlike Reladomo, which
**column-flattens** an embedded value object into individual columns of the owning
table, core maps the **whole value object to a single neutral `json` column**
(`m-core`). The dialect seam (`m-dialect`) maps that neutral type to the database's
structured-document storage, such as Postgres `jsonb`, MariaDB `json`, or a future
Snowflake `VARIANT`. This deviation keeps the composite atomic and schema-flexible
and lets the inner fields be filtered directly.

## Declared structure

A value object is a **recursive, typed composite**, not an opaque blob. It
declares typed `attributes`, further `valueObjects` nested inside it to arbitrary
depth, and its own `cardinality`. A **top-level** value object — one declared
directly on an entity — additionally carries the single storage `column`; a
**nested** value object carries no storage properties at all (it lives in its
ancestor's column; see below).

| Property | Values / meaning |
|---|---|
| `name` | value-object element name (REQUIRED) |
| `column` | the single structured-document column the whole object is stored in (REQUIRED, **top-level only**) |
| `mapping` | neutral storage mapping; `json` (the only mapping in core); **top-level only** |
| `cardinality` | `one` — a single embedded document (the default) — or `many` — a JSON array of documents in the same column |
| `nullable` | bool, default `false` |
| `attributes` | this value object's typed inner fields (each a `valueObjectAttribute`); no per-field column |
| `valueObjects` | value objects nested inside this one, to arbitrary depth (each a `nestedValueObject`) |

A `valueObjectAttribute` is a typed inner field. It carries **no per-field
`column`** — the whole value object lives in one structured-document column, so an
inner field has no column of its own.

| Property | Values / meaning |
|---|---|
| `name` | attribute name (REQUIRED) |
| `type` | m-core neutral type (REQUIRED); normative for nested-predicate literal typing and casting (`m-op-algebra` / `m-sql`) |
| `nullable` | bool, default `false` |

A `nestedValueObject` has the same shape as a top-level value object **minus**
`column`/`mapping`: `name`, `cardinality`, `nullable`, its own typed `attributes`,
and its own further-nested `valueObjects`. The schema forbids a nested member from
carrying `column` or `mapping`. An entity MAY declare zero or more top-level
`valueObjects`.

## One column — never extra columns, rows, or joins

The recursive shape does **not** change storage: there is **exactly one
structured-document column per top-level value object**. That top-level value
object declares the `column`; every nested value object and every inner
attribute, at any depth, lives **inside that same column**. Nested definitions
MUST NOT carry a `column` or a `mapping`, and MUST NOT introduce extra columns,
extra rows, joins, or identity-bearing objects. A `one` member is a single
embedded document and a `many` member is a JSON array of documents — both within
the one column. The harness derives the concrete column type through `m-dialect`
exactly as it does for a scalar attribute, and it MUST NOT emit a column for any
nested value object or inner attribute. The column is part of the entity's column
order, positioned after the scalar attributes.

## Inherited temporality

A value object has **no independent temporality**. It declares no
`asOfAttributes` — the schema does not admit them on a value object — and it owns
no timeline. Its backing column is part of the owning entity's column order, so it
rides the owner's (possibly milestoned) row and inherits whatever temporal
classification the entity declares (`m-temporal-read`). On a temporal owner the
document is carried across milestone chaining exactly like any scalar column;
there is **no value-object-specific temporal machinery** — the as-of read predicate
and the milestone-chaining write are the *owner's*, and the document is simply the
value in one more column.

This is proven end to end on a **unitemporal** (audit-only, processing) owner and a
**bitemporal** owner, each declaring the same nested-plus-to-many value object. As-of
`read` cases show the document is visible **per milestone** — reading the *same* owner
at different processing / business instants returns a *different* document:
`m-value-object-028` returns each supplier's current-milestone document while
`m-value-object-029` returns a superseded processing milestone's; `m-value-object-030`
returns the fully-current (both-axes) document while `m-value-object-031` reconstructs
the originally-believed document of a past audit read. `writeSequence` cases show the
document is **carried across the chain** exactly like a scalar column: an audit-only
update closes the current row and chains a new milestone whose golden DML binds the
whole document in `columnOrder` position (`m-value-object-032`, `m-audit-write`), and a
bitemporal `updateUntil` rectangle split carries the document verbatim onto the
head / middle / tail rectangles (`m-value-object-033`, `m-bitemp-write`) — in both, the
close / inactivating `UPDATE` sets only the interval bound and never touches the
document column.

## Reading and filtering inner fields

The inner fields are **read and filtered** with the `m-op-algebra`
nested-attribute access form over a dotted path (`Class.valueObject.path`), which
`m-sql` lowers to a dialect-specific document extraction. Because a value object
has no identity of its own, it is accessed by value only and is never a
relationship target.

## Writing — one atomic document bind

A top-level value object is **written atomically as one document**. On an insert
or an update its backing column takes **exactly one bind** in the entity's
`columnOrder` position (after the scalar attributes), carrying the whole embedded
composite — every inner attribute and every nested `one` / `many` value object,
at every depth — as a single structured-document value. The write path **MUST
NOT** decompose the document into path-level binds: a value-object column
participates in insert/update DML **exactly like a scalar column** (one `?` in
`columnOrder` position), and the concrete document value is adapted to the
dialect's structured-document type at bind time (`m-dialect` — e.g. Postgres
`jsonb`, MariaDB `json`). This mirrors Reladomo's embedded value riding the
owner's row, expressed as one atomic document rather than flattened columns.

A **null** value object (`nullable: true`, written absent) binds SQL `NULL` — the
whole column is null, not a document of nulls. A `nullable: false` value object
MUST be present at write time (`m-op-algebra` / the `rejected` write-validation
cases).

A value-object column's write value is **always the literal document** — the
object, the array, or the `NULL` above — and is **never** interpreted as a
DB-computed write marker. The `m-case-format` neutral write input (①) admits, on a
**scalar attribute** column, a one-key DB-computed marker (the pk-generation
`{computed: "maxPlusOne"}` and the self-advance `{increment: n}` forms) whose bind
the database derives; those marker semantics apply **only to scalar attribute
columns**. A value object binds its whole document even when that document is
*shaped* like a marker (its sole field happening to be `computed` or `increment`).
The two are disambiguated by the field's declared **metamodel role** — resolved
from the entity's `columnOrder` (scalar attribute vs value object) — **not** by the
value's shape. This keeps the atomic-document guarantee total: a value object is
bound as one document value regardless of what that value happens to look like.

There are **no partial-document (path-level) writes**. A whole-document update
**replaces** the entire column value with the newly bound document; there is no
`UPDATE` of a path *inside* the document and no merge with the prior value. This
matches the single-column storage model (`m-value-object` [one
column](#one-column--never-extra-columns-rows-or-joins)): the document is the unit
of write exactly as it is the unit of storage. On a temporal owner the same
atomic document rides milestone chaining like any scalar column (see [Inherited
temporality](#inherited-temporality)): an audit-only update chains it onto the new
current milestone (`m-value-object-032`) and a bitemporal `updateUntil` carries it
across the rectangle split (`m-value-object-033`); there is no
value-object-specific write machinery.

Atomic writes are proven by `writeSequence` cases whose golden DML binds the
document in `columnOrder` position and whose `then.tableState` reads it back
(`m-case-format`): `m-value-object-025` inserts a Customer whose whole
nested-plus-to-many `address` document binds as one value; `m-value-object-026`
replaces that whole document with an update (`set address = ?`), proving no
path-level merge; `m-value-object-027` nulls a nullable value object out to SQL
`NULL`. A required-member-missing write is refused pre-SQL as a `rejected` case
(`m-case-format`).

## Materialization and navigation contract

A value object is reached **only by value, through its owner** — never as a
navigable, identity-bearing peer. The following is normative, stated positively
rather than left true by omission:

1. **Getters exist to arbitrary depth.** An implementation MUST expose a typed
   getter for every declared inner member — each `attribute` and each nested
   `valueObject`, at every depth — reachable from the owning entity (owner →
   top-level value object → nested value object → … → leaf attribute). A `one`
   member's getter yields a single value (or null); a `many` member's getter
   yields the collection of element values. **Element order within a `many`
   member is unspecified** — an implementation MAY preserve the
   document/storage order, but that order is NOT guaranteed and consumers MUST
   NOT rely on it. Accordingly the compatibility `then.graph` comparison for
   value-object arrays is **order-insensitive**: a multiset comparison in which
   element multiplicity still matters (duplicate elements are distinguished),
   only order does not.
2. **They materialize with the owner in one round trip.** A value object
   materializes **with its owning entity in the same read**: the owner's single
   statement projects the whole structured-document column, and every nested
   to-one and to-many value is decoded from that one column. Invoking a getter
   MUST NOT take a lock, populate an identity cache, or emit **any** statement —
   there is no per-value-object fetch, and `m-deep-fetch` never applies.
3. **No reverse getters.** A value object has no identity and holds no reference
   back to its owner; a reverse (value-object → owner) getter MUST NOT exist.
4. **Not a navigation or deep-fetch target.** A `deepFetch` path and a
   relationship-navigation path (`m-deep-fetch` / `m-navigate`) traverse
   relationships **between identity-bearing entities**; a value-object segment is
   invalid in either grammar and MUST be rejected. Value objects carry no
   correlation columns, no portal, and no reverse relationship to navigate.
5. **No `find()` root.** `find()` MUST NOT be rooted at a value object — a value
   object is not a queryable root entity. It is queried only *through* its owner
   (a nested-attribute predicate on the owner, `m-op-algebra`).
6. **Inherited temporality, no unit of work.** A value object inherits the
   owner's temporality (see [Inherited temporality](#inherited-temporality)) and
   participates in **no unit-of-work semantics of its own** — it holds no
   independent transaction, lock, identity, cache, or dirty-tracking state.

One-round-trip materialization is proven by `read` cases carrying `then.graph` at
`roundTrips: 1`: the owning entity's assembled graph carries its nested to-one and
to-many value-object values, decoded from the single document column, with **no**
child statement (`m-value-object-023` materializes every row's full nested
composite under `all`; `m-value-object-024` materializes the matching owners'
composites under a nested-field filter). The invalid uses above (a
`deepFetch`/navigation path through a value object, a `find()` rooted at a value
object) are pinned as pre-SQL `rejected` cases (`m-case-format`).
