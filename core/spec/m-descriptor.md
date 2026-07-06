# m-descriptor — Domain Model & Metamodel

The metamodel is the **portable description of a domain**: the language-neutral
replacement for Reladomo's `mithraobject.xsd`. It is both an introspectable
runtime protocol and a serializable document — and that serialized document **is**
the compatibility suite's model-fixture format. `m-descriptor` depends only on
`m-core`.

The canonical schema is
[`core/schemas/metamodel.schema.json`](../schemas/metamodel.schema.json); a model
descriptor (e.g. `core/compatibility/models/orders.yaml`) is an instance of it.

The metamodel also declares the elements owned by the finer metamodel modules:
`pkGenerator` (`m-pk-gen`), `inheritance` (`m-inheritance`), and `valueObject`
(`m-value-object`). Their metamodel surface is summarized here; their behavior is
specified in those modules.

## Naming conventions (DQ16)

- Element-type and property **names** are `camelCase`.
- Neutral data-type **names** are lowercase (e.g. `int64`, `string`,
  `decimal(p,s)`).
- Enumerated string **values** are `kebab-case`, lowercase (e.g.
  `read-only`, `table-per-hierarchy`).
- Booleans are `true` / `false`.

The base elements for a single non-temporal entity are `entity`, `attribute`,
and `pkGenerator`. A descriptor may declare **multiple entities** so relationships
can name sibling entities, plus **`asOfAttribute`** (a temporal dimension), and
the two metamodel extensions **`inheritance`** (table-per-hierarchy with a
discriminator, or table-per-leaf — **never** table-per-class) and **`valueObject`**
(an embedded composite element mapped to a single dialect-native
structured-document column).

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
| `type` | neutral type from the `m-core` table (REQUIRED); `decimal(p,s)` carries precision/scale |
| `column` | DB column name (REQUIRED) |
| `primaryKey` | bool, default `false` |
| `nullable` | bool, default `false` |
| `maxLength` | for `string` (⇒ `varchar(n)`) |
| `readOnly` | bool, default `false` — immutable after insert |
| `optimisticLocking` | bool, default `false` — marks the version attribute (`m-opt-lock`) |
| `pkGenerator` | `none` (default) \| `max` \| `sequence` (`m-pk-gen`) |
| `default` | optional default value |

> The `type` value is the neutral type name. `decimal` is written with its
> precision and scale, e.g. `decimal(18,2)`. Reladomo's per-attribute
> `timezoneConversion` is intentionally absent (timestamps are UTC-normalized
> globally, per `m-core`).

The `readOnly` and `optimisticLocking` flags are the metamodel surface two
modules build on. `readOnly` marks an attribute that is immutable after insert
(an implementation **MUST NOT** emit it in an `UPDATE` `set`).
`optimisticLocking: true` **names** the entity's **version attribute**
(`m-opt-lock`): at most one per entity, an integer that **every** issued `UPDATE`
**advances**, and that a write **gates on** only when the unit of work runs in
optimistic mode (`m-unit-work` strategy selection) — turning a stale-version write
into a detectable conflict. The flag names the column; it does not by itself
decide the strategy — that is the unit of work's per-transaction choice. The flag
is purely metamodel here; its conflict-detection semantics are `m-opt-lock`, and
the object-lifecycle states that decide *when* an attribute is written (in-memory
vs. persisted vs. detached) are `m-detach`.

**Composition with `asOfAttribute` (temporal entities).** A processing-axis
temporal entity **derives** its optimistic key from the processing-from column —
the observed processing-from (`in_z`) is the version analogue — and therefore
declares **no** version attribute. Combining an explicit `optimisticLocking`
attribute with `asOfAttributes` on one entity is **invalid** and an implementation
**MUST** reject such a descriptor (a schema-level metamodel error). A
**business-temporal-only** entity has no processing axis to derive the key from, so
it **cannot** participate in optimistic mode; because mode is the unit of work's
per-transaction choice (not a static model property), that combination surfaces as
a validation error **at the unit-of-work write boundary**, not at metamodel-load
time. The composition contract is `m-opt-lock` (which owns the derived key and the
conflict contract) over the temporal write shapes (`m-audit-write` /
`m-bitemp-write`).

## `relationship` — a navigable association

A `relationship` is a **named, navigable association** from its owning entity to
a related entity. The join columns are **auto-derived from the navigation
predicate** — a query never writes ON-conditions by hand (`m-op-algebra`
`navigate` and `m-deep-fetch` traverse the relationship by name).

| Property | Values / meaning |
|---|---|
| `name` | relationship name (REQUIRED) |
| `relatedEntity` | target entity name (REQUIRED) |
| `cardinality` | `one-to-one` \| `many-to-one` \| `one-to-many` \| `many-to-many` (REQUIRED) |
| `join` | navigation predicate (REQUIRED), e.g. `this.id = OrderItem.orderId` |
| `reverseName` | optional reverse-relationship name on the related entity |
| `dependent` | bool, default `false` — target is **owned** ⇒ participates in cascade (`m-cascade-delete`) |
| `foreignKey` | optional FK hint (the column on the many side) |
| `orderBy` | optional ordering for a to-many relationship (list of `{ attr, direction? }`) |

The `join` predicate has the canonical form `this.<attr> = <Entity>.<attr>`:
`this.<attr>` names an attribute of the **owning** entity and `<Entity>.<attr>`
names the matching attribute of the **related** entity. From it, both the SQL
join (`m-sql`) and the deep-fetch key columns (`m-deep-fetch`) are derived. A
**reverse** relationship (`reverseName`) is the same association navigated from
the other side; a **dependent** relationship marks the target as owned (cascade,
`m-cascade-delete`). The full navigation and deep-fetch semantics are `m-navigate`
and `m-deep-fetch`.

## `index` — a (possibly unique) index

| Property | Values / meaning |
|---|---|
| `name` | index name (REQUIRED) |
| `attributes` | ordered attribute-name list (REQUIRED, non-empty) |
| `unique` | bool, default `false` — a unique index enables the cache fast-path |

Indices are metadata: they declare the storage indices an implementation
**SHOULD** create and the **unique** keys the identity cache can exploit. A
unique index over the primary-key attributes is the canonical fast-path key.

## `asOfAttribute` — a temporal dimension

An `asOfAttribute` declares a temporal axis: a query-time virtual attribute
backed by a **pair of timestamp columns** forming a `[from, to)` interval. Its
full semantics (as-of read predicates, milestone-chaining writes) are the temporal
modules (`m-temporal-read` / `m-audit-write` / `m-bitemp-write`); this is its
metamodel surface.

| Property | Values / meaning |
|---|---|
| `name` | dimension name (REQUIRED), e.g. `processingDate`, `businessDate` |
| `fromColumn` | the interval's inclusive lower-bound column (REQUIRED) |
| `toColumn` | the interval's upper-bound column (REQUIRED); `= infinity` ⇒ current row |
| `axis` | `processing` \| `business` (REQUIRED) |
| `toIsInclusive` | bool, default `false` ⇒ `[from, to)`; `true` ⇒ `[from, to]` |
| `infinity` | the open-bound sentinel; always `infinity` (`m-dialect` owns the concrete representation, `m-core`) |
| `default` | default-if-unspecified for a query; `now` (the current milestone). Only `now` is defined for the temporal MVP |

An entity declares **one** `asOfAttribute` (unitemporal) or **two**, one per
axis (bitemporal). The `entity.temporal` classification is derived from them (see
above). A temporal entity's **physical primary key** is the business key plus
each dimension's `fromColumn` (many milestone rows share one business key); the
DDL an implementation derives **MUST** reflect this so the milestone chain is
admissible.

## Metamodel serde (protocol seam)

The metamodel is **serializable and deserializable** through the same
format-agnostic canonical serde seam as the operation algebra (`m-op-algebra`),
with concrete writers for **JSON and YAML**. The descriptor **is** the serialized
metamodel: `serialize(deserialize(descriptor)) == descriptor` **MUST** hold, in
both formats. The reference harness asserts this round-trip for every model
referenced by a compatibility case. *How* a language populates its in-memory model
(descriptor files, annotations, decorators, builders) is a per-language choice;
the serializable canonical form is the portable backbone.
