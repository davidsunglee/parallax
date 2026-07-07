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
