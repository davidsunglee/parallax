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
there is no value-object-specific temporal machinery.

## Reading and filtering inner fields

The inner fields are **read and filtered** with the `m-op-algebra`
nested-attribute access form over a dotted path (`Class.valueObject.path`), which
`m-sql` lowers to a dialect-specific document extraction. Because a value object
has no identity of its own, it is accessed by value only and is never a
relationship target.

## Materialization and navigation contract

A value object is reached **only by value, through its owner** — never as a
navigable, identity-bearing peer. The following is normative, stated positively
rather than left true by omission:

1. **Getters exist to arbitrary depth.** An implementation MUST expose a typed
   getter for every declared inner member — each `attribute` and each nested
   `valueObject`, at every depth — reachable from the owning entity (owner →
   top-level value object → nested value object → … → leaf attribute). A `one`
   member's getter yields a single value (or null); a `many` member's getter
   yields the ordered list of element values.
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
