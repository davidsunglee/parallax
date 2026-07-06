# m-value-object — Embedded Value Objects

`m-value-object` is the **embedded composite element** a metamodel entity may
declare. It depends on `m-descriptor` (the entity it annotates).

A `valueObject` is an embedded composite sub-value of an entity (an address, a
money amount, a geo point) that has no identity of its own. Unlike Reladomo, which
**column-flattens** an embedded value object into individual columns of the owning
table, core maps the **whole value object to a single neutral `json` column**
(`m-core`). The dialect seam (`m-dialect`) maps that neutral type to the database's
structured-document storage, such as Postgres `jsonb`, Snowflake `VARIANT`, or
MariaDB `json`. This deviation keeps the composite atomic and schema-flexible and
lets the inner fields be filtered directly.

| Property | Values / meaning |
|---|---|
| `name` | value-object element name (REQUIRED) |
| `type` | the value-object's logical (struct) type name (REQUIRED, documentary) |
| `column` | the single structured-document column the whole object is stored in (REQUIRED) |
| `mapping` | neutral storage mapping; `json` (the only mapping in core) |
| `nullable` | bool, default `false` |

An entity MAY declare zero or more `valueObjects`. Each value object's backing
column is the `m-core` `json` neutral type; the harness derives the concrete
column type through `m-dialect` exactly as it does for scalar attributes. The
inner fields are **read and filtered** with the `m-op-algebra` nested-attribute
access form (`nestedEq` / `nestedNotEq` over a dotted path
`Class.valueObject.field`), which `m-sql` lowers to a dialect-specific document
extraction.
