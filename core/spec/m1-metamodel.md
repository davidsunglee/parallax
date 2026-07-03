# M1 — Domain Model & Metamodel

The metamodel is the **portable description of a domain**: the language-neutral
replacement for Reladomo's `mithraobject.xsd`. It is both an introspectable
runtime protocol and a serializable document — and that serialized document **is**
the compatibility suite's model-fixture format. `M1` depends only on `M0`.

The canonical schema is
[`core/schemas/metamodel.schema.json`](../schemas/metamodel.schema.json); a model
descriptor (e.g. `core/compatibility/models/orders.yaml`) is an instance of it.

## Naming conventions (DQ16)

- Element-type and property **names** are `camelCase`.
- Neutral data-type **names** are lowercase (e.g. `int64`, `string`,
  `decimal(p,s)`).
- Enumerated string **values** are `kebab-case`, lowercase (e.g.
  `read-only`, `table-per-hierarchy`).
- Booleans are `true` / `false`.

The base elements for a single non-temporal entity are `entity`, `attribute`,
and `pkGenerator`. Earlier revisions added `relationship` and `index`, and
admit **multiple entities per descriptor** so relationships can name sibling
entities, plus **`asOfAttribute`** (the M7 temporal dimension). This revision
adds two metamodel extensions (DQ9 definitely-do): **`inheritance`**
(table-per-hierarchy with a discriminator, or table-per-leaf — **never**
table-per-class) and **`valueObject`** (an embedded composite element mapped to a
single dialect-native structured-document column).

## One or many entities per descriptor

A descriptor declares **either** a single top-level `entity` (a one-entity
model) **or** a top-level `entities` array (a multi-entity model whose
relationships traverse between siblings). The two forms are mutually exclusive.
The single-`entity` form is exactly the one-element case of `entities`; an
implementation **MUST** accept both.

## `entity` — the unit of mapping

| Property | Values / meaning |
|---|---|
| `name` | entity (domain class) name (REQUIRED) |
| `namespace` | logical namespace (language-neutral; replaces Java-style "package") |
| `table` | default table name (REQUIRED) |
| `mutability` | `read-only` (default) \| `transactional` |
| `temporal` | derived classification: `non-temporal` (default) \| `unitemporal-processing` \| `unitemporal-business` \| `bitemporal` |
| children | `attributes` (REQUIRED, non-empty); `relationships`, `indices`, `asOfAttributes`, `valueObjects`, `inheritance` (optional) |

The `temporal` classification is **derived** from the `asOfAttribute` children an
entity declares and **MUST** be consistent with them:

| `asOfAttributes` | `temporal` |
|---|---|
| none | `non-temporal` |
| one, `axis: processing` | `unitemporal-processing` |
| one, `axis: business` | `unitemporal-business` |
| two (one per axis) | `bitemporal` |

It is recorded explicitly for clarity and validated for consistency. The temporal
MVP exercises `non-temporal` and `unitemporal-processing` (audit-only).

Every entity **MUST** declare at least one `attribute` with `primaryKey: true`.

## `attribute` — a typed, mapped scalar field

| Property | Values / meaning |
|---|---|
| `name` | attribute name (REQUIRED) |
| `type` | neutral type from the M0 table (REQUIRED); `decimal(p,s)` carries precision/scale |
| `column` | DB column name (REQUIRED) |
| `primaryKey` | bool, default `false` |
| `nullable` | bool, default `false` |
| `maxLength` | for `string` (⇒ `varchar(n)`) |
| `readOnly` | bool, default `false` — immutable after insert |
| `optimisticLocking` | bool, default `false` — marks the version attribute (M10) |
| `pkGenerator` | `none` (default) \| `max` \| `sequence` |
| `default` | optional default value |

> The `type` value is the neutral type name. `decimal` is written with its
> precision and scale, e.g. `decimal(18,2)`. Reladomo's per-attribute
> `timezoneConversion` is intentionally absent (timestamps are UTC-normalized
> globally, per M0).

The `readOnly` and `optimisticLocking` flags are the metamodel surface two
fast-follow modules build on. `readOnly` marks an attribute that is immutable
after insert (an implementation **MUST NOT** emit it in an `UPDATE` `set`).
`optimisticLocking: true` **names** the entity's **version attribute** (`M10`): at
most one per entity, an integer that **every** issued `UPDATE` **advances**, and
that a write **gates on** only when the unit of work runs in optimistic mode
(`M8` strategy selection) — turning a stale-version write into a detectable
conflict. The flag names the column; it does not by itself decide the strategy —
that is the unit of work's per-transaction choice. The `optimisticLocking` flag is
purely metamodel here; its conflict-detection semantics are `M10`, and the
object-lifecycle states that decide *when* an attribute is written (in-memory vs.
persisted vs. detached) are `M9`.

**Composition with `asOfAttribute` (temporal entities).** A processing-axis
temporal entity **derives** its optimistic key from the processing-from column —
the observed processing-from (`in_z`) is the version analogue — and therefore
declares **no** version attribute. Combining an explicit `optimisticLocking`
attribute with `asOfAttributes` on one entity is **invalid** and an implementation
**MUST** reject such a descriptor (a schema-level metamodel error). A
**business-temporal-only** entity has no processing axis to derive the key from, so
it **cannot** participate in optimistic mode; because mode is the unit of work's
per-transaction choice (not a static model property), that combination surfaces as a
validation error **at the unit-of-work write boundary**, not at metamodel-load time.
The composition contract is `M10` (which owns the derived key and the conflict
contract) over `M7` (which owns the temporal write shapes).

## `relationship` — a navigable association

A `relationship` is a **named, navigable association** from its owning entity to
a related entity. The join columns are **auto-derived from the navigation
predicate** — a query never writes ON-conditions by hand (M2 `navigate` and the
M4 deep-fetch traverse the relationship by name).

| Property | Values / meaning |
|---|---|
| `name` | relationship name (REQUIRED) |
| `relatedEntity` | target entity name (REQUIRED) |
| `cardinality` | `one-to-one` \| `many-to-one` \| `one-to-many` \| `many-to-many` (REQUIRED) |
| `join` | navigation predicate (REQUIRED), e.g. `this.id = OrderItem.orderId` |
| `reverseName` | optional reverse-relationship name on the related entity |
| `dependent` | bool, default `false` — target is **owned** ⇒ participates in cascade (M5) |
| `foreignKey` | optional FK hint (the column on the many side) |
| `orderBy` | optional ordering for a to-many relationship (list of `{ attr, direction? }`) |

The `join` predicate has the canonical form `this.<attr> = <Entity>.<attr>`:
`this.<attr>` names an attribute of the **owning** entity and `<Entity>.<attr>`
names the matching attribute of the **related** entity. From it, both the SQL
join (M3) and the deep-fetch key columns (M4) are derived. A **reverse**
relationship (`reverseName`) is the same association navigated from the other
side; a **dependent** relationship marks the target as owned (cascade, deferred
to M5). The full M4 deep-fetch and navigation semantics build on these fields.

## `index` — a (possibly unique) index

| Property | Values / meaning |
|---|---|
| `name` | index name (REQUIRED) |
| `attributes` | ordered attribute-name list (REQUIRED, non-empty) |
| `unique` | bool, default `false` — a unique index enables the cache fast-path |

Indices are metadata: they declare the storage indices an implementation
**SHOULD** create and the **unique** keys the identity cache can exploit. A
unique index over the primary-key attributes is the canonical fast-path key.

## `valueObject` — an embedded composite mapped to a structured column

A `valueObject` is an **embedded composite element** — a structured sub-value of
an entity (an address, a money amount, a geo point) that has no identity of its
own. Unlike Reladomo, which **column-flattens** an embedded value object into
individual columns of the owning table, core maps the **whole value object to a
single neutral `json` column** (M0). The M11 dialect seam maps that neutral type
to the database's structured-document storage, such as Postgres `jsonb`,
Snowflake `VARIANT`, or MariaDB `json`. This deviation keeps the composite
atomic and schema-flexible and lets the inner fields be filtered directly.

| Property | Values / meaning |
|---|---|
| `name` | value-object element name (REQUIRED) |
| `type` | the value-object's logical (struct) type name (REQUIRED, documentary) |
| `column` | the single structured-document column the whole object is stored in (REQUIRED) |
| `mapping` | neutral storage mapping; `json` (the only mapping in core) |
| `nullable` | bool, default `false` |

An entity MAY declare zero or more `valueObjects`. Each value object's backing
column is the M0 `json` neutral type; the harness derives the concrete column
type through M11 exactly as it does for scalar attributes. The inner fields are
**read and filtered** with the M2 nested-attribute access form (`nestedEq` /
`nestedNotEq` over a dotted path `Class.valueObject.field`), which M3 lowers to
a dialect-specific document extraction.

## `inheritance` — class-hierarchy mapping

An entity that participates in a class hierarchy declares an `inheritance`
element naming its **strategy** and its **role**. Core admits exactly two
strategies and **rejects the third**:

| Strategy | Meaning | In core? |
|---|---|---|
| `table-per-hierarchy` | the whole hierarchy in **one** table; rows discriminated by a `discriminator` column | **yes** |
| `table-per-leaf` | one table **per concrete leaf**; no discriminator | **yes** |
| `table-per-class` | one table per class, joined at query time | **REJECTED** — the metamodel schema does not admit it |

`table-per-class` is intentionally excluded (DQ9): per-query joins to assemble a
single object are exactly the kind of hidden N+1 / fan-out cost the suite exists
to prevent, and the two admitted strategies cover the field's real use. A
descriptor declaring `strategy: table-per-class` **MUST** fail schema validation
(a negative compatibility test asserts this).

| Property | Values / meaning |
|---|---|
| `strategy` | `table-per-hierarchy` \| `table-per-leaf` (REQUIRED) |
| `role` | `root` (owns / names the hierarchy) \| `subtype` (a leaf) (REQUIRED) |
| `parent` | for a `subtype`: the entity it extends (REQUIRED for a subtype, FORBIDDEN for a root) |
| `discriminator` | table-per-hierarchy only, REQUIRED there and FORBIDDEN for table-per-leaf: `{ column }`, the column distinguishing leaves in the shared table |
| `discriminatorValue` | table-per-hierarchy only, REQUIRED there and FORBIDDEN for table-per-leaf: the discriminator value THIS entity's rows carry |

**Table-per-hierarchy.** The `root` and every `subtype` map to the **same
table** and declare the shared `discriminator` column plus their own
`discriminatorValue`; a query for a subtype injects a
**discriminator-equality predicate** (`t0.<discriminator> = ?`), and a query
across a family of subtypes injects a discriminator `in (?, …)`. The root query
(no discriminator predicate) sees every row. M3 fixes the discriminator-filter
golden SQL.

**Table-per-leaf.** Each concrete leaf maps to its **own table** (its own
`table`), so a leaf query is an ordinary single-table read of that table with
**no** discriminator — the subtype is selected by *which table* is queried. No
shared table and no discriminator column exist.

## `asOfAttribute` — a temporal dimension

An `asOfAttribute` declares a temporal axis: a query-time virtual attribute
backed by a **pair of timestamp columns** forming a `[from, to)` interval. Its
full semantics (as-of read predicates, milestone-chaining writes) are M7; this is
its metamodel surface.

| Property | Values / meaning |
|---|---|
| `name` | dimension name (REQUIRED), e.g. `processingDate`, `businessDate` |
| `fromColumn` | the interval's inclusive lower-bound column (REQUIRED) |
| `toColumn` | the interval's upper-bound column (REQUIRED); `= infinity` ⇒ current row |
| `axis` | `processing` \| `business` (REQUIRED) |
| `toIsInclusive` | bool, default `false` ⇒ `[from, to)`; `true` ⇒ `[from, to]` |
| `infinity` | the open-bound sentinel; always `infinity` (the M11 dialect owns the concrete representation, M0) |
| `default` | default-if-unspecified for a query; `now` (the current milestone). Only `now` is defined for the temporal MVP |

An entity declares **one** `asOfAttribute` (unitemporal) or **two**, one per
axis (bitemporal). The `entity.temporal` classification is derived from them (see
above). A temporal entity's **physical primary key** is the business key plus
each dimension's `fromColumn` (many milestone rows share one business key); the
DDL an implementation derives **MUST** reflect this so the milestone chain is
admissible.

## `pkGenerator` — primary-key generation strategy

A primary-key attribute MAY declare how its value is allocated. `none` (the
default) is application-assigned; `max` allocates `max(col)+1`; `sequence` is a
*simulated sequence* (Reladomo-style): a registry table whose counter is advanced
by `batchSize x incrementSize` per allocation, reserving a block of ids the
application hands out (a partially-consumed block leaves a gap). All three are
exercised by the compatibility suite (`max` and `sequence` via writeSequence
cases `0620`-`0632`); the simulated sequence is realized in portable SQL (a table
plus an `UPDATE`), so it carries no dialect seam.

| Strategy | Meaning |
|---|---|
| `none` | application-assigned (default) |
| `max` | `max(col)+1`-style allocation |
| `sequence` | simulated sequence (`sequenceName`, `batchSize`, `initialValue`, `incrementSize`) |

## Metamodel serde (protocol seam)

The metamodel is **serializable and deserializable** through the same
format-agnostic canonical serde seam as the operation algebra (M2), with concrete
writers for **JSON and YAML**. The descriptor **is** the serialized metamodel:
`serialize(deserialize(descriptor)) == descriptor` **MUST** hold, in both formats.
The reference harness asserts this round-trip for every model referenced by a
compatibility case. *How* a language populates its in-memory model (descriptor
files, annotations, decorators, builders) is a per-language choice; the
serializable canonical form is the portable backbone.
