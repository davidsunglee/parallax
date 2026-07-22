# m-descriptor — Domain Model & Metamodel

The descriptor is the **portable serialized description of a domain**: the
language-neutral replacement for Reladomo's `mithraobject.xsd` and the
compatibility suite's model-fixture format. It is not the runtime metamodel
protocol. Descriptor adapters normalize schema-valid documents to the
`m-metamodel` Unresolved Metamodel seam and export accepted Metamodels back to
this canonical form.

The canonical schema is
[`core/schemas/metamodel.schema.json`](../schemas/metamodel.schema.json); a model
descriptor (e.g. `core/compatibility/models/orders.yaml`) is an instance of it.

The descriptor also declares the elements owned by finer model modules:
`pkGeneration` (`m-pk-gen`), `inheritance` (`m-inheritance`), and `valueObject`
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
and `pkGeneration`. A descriptor may declare **multiple entities** so relationships
can name sibling entities, plus **`asOfAxes`** (temporal dimensions), and
the two metamodel extensions **`inheritance`** (a closed class tree —
table-per-hierarchy with a `tag`/`tagValue` discriminator, or
table-per-concrete-subtype; **never** table-per-leaf or table-per-class) and
**`valueObject`** (an embedded composite element mapped to a single dialect-native
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
| `table` | physical table name (**conditionally** required — see below) |
| `persistence` | `read-write` (default for standalone/root) \| `read-only`; descendants omit and inherit |
| children | `attributes` (**conditionally** required, non-empty); `relationships`, `indices`, `asOfAxes`, `valueObjects`, `inheritance` (optional) |

`persistence` describes whether Parallax accepts persistence writes. It does
not describe object mutability, security access, transaction demarcation, or a
temporal dimension. The spellings `mutability`, `transactional`, and a default
of `read-only` are invalid. Persistence is family-wide and root-owned: a
descendant MUST omit it even when repeating the root's value.

### Conditional `table` / `attributes` requirements (inheritance)

`table` and `attributes` are required **except** where the `inheritance` role
(`m-inheritance`) makes them meaningless:

| Entity kind | `table` | `attributes` |
|---|---|---|
| no `inheritance` | REQUIRED | REQUIRED (non-empty) |
| TPH `role: root` | REQUIRED (owns the family's shared table mapping) | optional — its attributes are inherited by descendants |
| TPH descendant | FORBIDDEN | optional — a subtype declaring only inherited attributes has none of its own |
| TPCS `role: concrete-subtype` | REQUIRED (owns its physical table) | optional — a subtype declaring only inherited attributes has none of its own |
| TPCS `role: root` / `abstract-subtype` | FORBIDDEN — abstract nodes are tableless and rowless | optional — its attributes are inherited by descendants |

The full inherited attribute/column set of a concrete subtype is **derived from
its ancestry chain** (root → … → self), so a concrete subtype never repeats
inherited attributes (`m-inheritance`). An abstract root or subtype still declares
the attributes it *introduces* (inherited by descendants) but owns no table and no
rows.

Every entity **MUST** have exactly one **primary key** — for a concrete subtype it
may be inherited from an abstract ancestor rather than declared locally.

Temporal classification is derived from `asOfAxes` and is not repeated as an
Entity property. The supported shapes are no axes, Transaction-Time-Only, and
Bitemporal. An authored `temporal` classification is invalid.

**For an inheritance participant, "the `asOfAxes` children an entity
declares" means the family's — not necessarily this entity's own local —
children.** Temporal axes are family-wide metadata declared only on the root
(`m-inheritance` "Inherited members"); an abstract-subtype or concrete-subtype
declares none of its own, so its **derived temporal classification** is the
root's, inherited unchanged, never re-derived from an empty local
`asOfAxes`. A model-aware reader that does not flatten inheritance (a
per-entity introspection view) MAY still surface a non-root participant's own,
locally-empty `asOfAxes` for structural inspection; every OTHER
consumer — reads, writes, provisioning, identity, propagation — MUST use the
entity's **effective inherited classification** within its family.

Every entity **MUST** resolve to at least one `attribute` with `primaryKey: true`
— declared locally, or (for a concrete subtype) inherited from an abstract
ancestor through its ancestry chain (`m-inheritance`).

## `attribute` — a typed, mapped scalar field

| Property | Values / meaning |
|---|---|
| `name` | attribute name (REQUIRED) |
| `type` | neutral type from the `m-core` table (REQUIRED); `decimal(p,s)` carries precision/scale |
| `column` | optional DB column override; omission means the Attribute `name` |
| `primaryKey` | bool, default `false` |
| `nullable` | bool, default `false` |
| `maxLength` | for `string` (⇒ `varchar(n)`) |
| `readOnly` | bool, default `false` — immutable after insert |
| `optimisticLocking` | bool, default `false` — marks the version attribute (`m-opt-lock`) |
| `pkGeneration` | optional `application-assigned` \| `max` \| Sequence object; legal only when `primaryKey: true`, omission on a primary key means application-assigned |
| `default` | optional default value |

The Sequence object is exactly:

```yaml
pkGeneration:
  strategy: sequence
  name: order_ids
  batchSize: 20
  initialValue: 1
  incrementSize: 1
```

`name` is required. `batchSize`, `initialValue`, and `incrementSize` may be
omitted only when the schema supplies their canonical semantic defaults; the
adapter always exposes a fully populated Sequence value. The retired
`pkGenerator`, `none`, and `sequenceName` spellings are invalid.

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

**Composition with `asOfAxes` (temporal entities).** A Transaction-Time Entity
**derives** its optimistic key from the Transaction-Time start Attribute (by
convention `tx_start`, physically `in_z`) and therefore declares **no** version
Attribute. Combining an explicit `optimisticLocking` Attribute with a
Transaction-Time axis is invalid. Transaction-Time-Only and Bitemporal are the
supported temporal shapes, so every writable temporal Entity has that derived
key. The composition contract is `m-opt-lock` over the temporal write shapes
(`m-audit-write` / `m-bitemp-write`).

**Composition with inheritance (declaration site).** For an inheritance
participant (`m-inheritance`), `optimisticLocking: true` is family-level
metadata like a temporal axis, not an ordinary per-entity flag: only the family
**root** may declare it, and every abstract and concrete descendant inherits the
root's version column unchanged. A descendant **MUST NOT** declare its own
`optimisticLocking` attribute — not even to redeclare the root's own verbatim, or
to add a second version attribute under a different name — regardless of whether
the root itself is versioned (`inheritance-optimistic-locking-not-root-owned`,
`m-inheritance` "Family invariants"). The at-most-one-per-entity rule above
therefore composes family-wide for a participant: at most one `optimisticLocking`
attribute across the whole family, declared only at the root.

## `relationship` — a navigable association

A relationship is exactly one branch of a closed defining/reverse union. One
defining declaration owns the association facts; an optional reverse
declaration names it without repeating those facts.

The defining form is:

| Property | Values / meaning |
|---|---|
| `name` | local relationship name (REQUIRED) |
| `cardinality` | `one-to-one` \| `many-to-one` \| `one-to-many` (REQUIRED) |
| `join` | `{ source: <local attribute>, target: { entity: <entity reference>, attribute: <target-local attribute> } }` (REQUIRED) |
| `dependent` | bool, default `false` — target is owned and participates in cascade (`m-cascade-delete`) |
| `orderBy` | optional target-attribute ordering for a to-many direction; each item is `{ attribute, direction? }` |

The reverse form is:

| Property | Values / meaning |
|---|---|
| `name` | local relationship name (REQUIRED) |
| `reverseOf` | `<entity-reference>.<relationship-name>` (REQUIRED) |
| `orderBy` | optional target-attribute ordering for this direction |

The forms are exclusive. A reverse declaration MUST NOT repeat `cardinality`,
`join`, `dependent`, or a separate target. A defining declaration MUST NOT
carry `reverseOf`. The retired `relatedEntity`, `reverseName`, and `foreignKey`
properties are invalid. Direct many-to-many is invalid; use an explicit
association Entity.

An Entity Reference in `join.target.entity` or `reverseOf` follows
`m-metamodel`: a bare Entity name is relative to the declaring Entity's
namespace, while a dot-qualified Entity name is exact. `reverseOf` splits at
its final dot, so the final segment is the relationship name. Canonical export
always emits a namespace-qualified Entity spelling when the target is
namespaced.

`join.source` is local to the declaring Entity. `join.target.attribute` and
each `orderBy.attribute` are local to the target Entity. Omitted ordering
direction normalizes to `asc`; ordering is valid only for a direction whose
target multiplicity is Many. Both SQL correlation and deep-fetch keys derive
from the resolved structured join. Behavioral consumers never parse descriptor
strings or infer a foreign key.

## `valueObject` — an embedded composite

A top-level Value Object occurrence has this exact authoring shape:

| Property | Values / meaning |
|---|---|
| `name` | local occurrence name (REQUIRED) |
| `column` | optional structured-document column override; omission means `name` |
| `multiplicity` | `one` (default) \| `many` |
| `nullable` | bool, default `false`; valid only with `one` |
| `attributes` | ordered typed scalar members |
| `valueObjects` | ordered nested Value Object occurrences |

A nested occurrence has the same shape except that it MUST NOT carry `column`.
Only the top-level occurrence owns storage; all descendants live inside the same
structured-document column. There is no `mapping` discriminator: structured
column storage is the only current representation.

Every occurrence is nonempty across `attributes` and `valueObjects`. A `many`
occurrence is a non-null ordered collection that may be empty. A `one`
occurrence is one composite and may be nullable. Inner scalar attributes carry
only `name`, `type`, and optional `nullable`; they have no column, generation,
locking, or Entity identity facts. Full recursive semantics belong to
`m-value-object`.

## `index` — a (possibly unique) index

| Property | Values / meaning |
|---|---|
| `name` | index name (REQUIRED) |
| `attributes` | ordered attribute-name list (REQUIRED, non-empty) |
| `unique` | bool, default `false` — a unique index enables the cache fast-path |

Indices are metadata: they declare the storage indices an implementation
**SHOULD** create and the **unique** keys the identity cache can exploit. A
unique index over the primary-key attributes is the canonical fast-path key.

## `asOfAxes` — temporal dimensions

`asOfAxes` declares zero, one, or two temporal dimensions. Each entry references
two ordinary Timestamp Attributes forming one fixed half-open interval
`[start, end)`. The dimension identifies the axis; there is no authored axis
name, kind, default, inclusivity flag, infinity field, or repeated physical
column.

| Property | Values / meaning |
|---|---|
| `dimension` | `validTime` \| `transactionTime` (REQUIRED) |
| `startAttribute` | local Timestamp Attribute name for the inclusive lower bound (REQUIRED) |
| `endAttribute` | distinct local Timestamp Attribute name for the exclusive upper bound (REQUIRED) |

Transaction-Time-Only declares one `transactionTime` entry. Bitemporal
declares `validTime` followed by `transactionTime`. Valid-Time-Only is not a
supported model shape. Query defaulting belongs to `m-temporal-read`, not model
metadata.

The conventional Attribute and physical-column mappings are normative:

| Dimension | Start Attribute / column | End Attribute / column |
|---|---|---|
| `validTime` | `valid_start` / `from_z` | `valid_end` / `thru_z` |
| `transactionTime` | `tx_start` / `in_z` | `tx_end` / `out_z` |

Physical column overrides remain ordinary Attribute `column` overrides. The
axis never repeats them. A temporal Entity's physical primary key is its model
primary key plus each dimension's start Attribute. Temporal Attributes appear
after domain Attributes, with Valid Time before Transaction Time, preserving
`from_z, thru_z, in_z, out_z` projection order for Bitemporal Entities.

## Metamodel serde (protocol seam)

The descriptor is **serializable and deserializable** through the same
format-agnostic canonical serde seam as the operation algebra (`m-op-algebra`),
with concrete writers for **JSON and YAML**. The descriptor **is** the serialized
metamodel: `serialize(deserialize(descriptor)) == descriptor` **MUST** hold, in
both formats. The reference harness asserts this round-trip for every model
referenced by a compatibility case. *How* a language populates its in-memory model
(descriptor files, annotations, decorators, builders) is a per-language choice;
the serializable canonical form is the portable backbone.

## Contract activation

This descriptor revision is a breaking canonical-form change. The schema,
compatibility models/cases, generated artifacts, reference tooling, and active
language descriptor consumers MUST switch to these spellings together and be
green before runtime consumers migrate to `m-metamodel`. No dual-read input,
compatibility alias, or temporary semantic translation is part of the contract.
