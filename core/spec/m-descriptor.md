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

## Type spellings

`m-descriptor` alone owns the serialized spelling of the `m-core` `NeutralType`
algebra: an `attribute.type` or Value Object Attribute `type` carries exactly
one of the spellings below. The structured variant a spelling denotes never
crosses the `m-metamodel` interface as text, and no behavioral module parses a
type string.

| `NeutralType` variant (`m-core`) | `type` spelling |
|---|---|
| `Boolean` | `boolean` |
| `Int32` | `int32` |
| `Int64` | `int64` |
| `Float32` | `float32` |
| `Float64` | `float64` |
| `Decimal(precision, scale)` | `decimal(<precision>,<scale>)` |
| `String` | `string` |
| `Bytes` | `bytes` |
| `Date` | `date` |
| `Time` | `time` |
| `Timestamp` | `timestamp` |
| `Uuid` | `uuid` |
| `Json` | `json` |

Every spelling is a single lowercase token. `decimal` is the sole parameterized
spelling: `decimal(` + precision + `,` + scale + `)` with both decimal-integer
parameters REQUIRED and no interior whitespace — e.g. `decimal(18,2)`. Each
parameter is spelled as unsigned canonical decimal digits (no sign, no leading
zeros), and the pair MUST satisfy the `m-core` bounds (`precision >= 1`,
`0 <= scale <= precision`). The schema admits any digit string, so a spelling
whose parameters break the bounds or carry non-canonical digits — e.g.
`decimal(0,9)`, `decimal(2,5)`, or `decimal(09,2)` — is schema-valid text the
adapter rejects in the semantic phase; every in-bounds spelling round-trips to
and from the structured `Decimal(precision, scale)` variant.
Reladomo's per-attribute `timezoneConversion` is intentionally absent
(timestamps are UTC-normalized globally, per `m-core`).

## Value encodings

`m-descriptor` alone owns the wire encoding of every `m-core` `NeutralValue`.
An encoded value appears wherever a descriptor document carries a typed value —
today the attribute `default`. The declared `type` disambiguates the encoding;
no consumer infers a type from an encoded value's shape.

| Declared `type` | Wire encoding |
|---|---|
| `boolean` | JSON/YAML boolean |
| `int32`, `int64` | JSON/YAML integer |
| `float32`, `float64` | JSON/YAML number denoting a finite IEEE-754 value, spelled in the canonical shortest round-trip rendering (see "Canonical float rendering" below); no NaN or infinity encoding exists because the `m-core` value spaces are finite |
| `decimal(p,s)` | string of the exact digits at the declared scale (e.g. `"12.30"` for scale 2): an optional leading `-`, an integer part with no superfluous leading zero, and — only when `s > 0` — a `.` followed by exactly `s` fractional digits. Negative zero, a leading `+`, exponents, and digit grouping are invalid |
| `date` | ISO-8601 calendar-date string `YYYY-MM-DD` |
| `time` | ISO-8601 wall-clock string `hh:mm:ss`, with fractional seconds per the timestamp rule |
| `timestamp` | ISO-8601 UTC instant string `YYYY-MM-DDThh:mm:ss` with the literal offset `+00:00` — the same spelling fixture `tableState` timestamps use; `Z` and non-zero offsets are invalid |
| `uuid` | canonical lowercase hyphenated UUID string |
| `bytes` | base64 string (RFC 4648 §4, with `=` padding) |
| `string` | JSON/YAML string |
| `json` | native JSON/YAML structure (any value of the JSON data model) |

Fractional seconds (`time` / `timestamp`) are omitted when the microsecond
component is zero and otherwise carry the fewest digits that represent it
exactly (no trailing zeros), so each logical value has exactly one canonical
spelling. The schema constrains each encoding structurally per declared `type`
(`metamodel.schema.json`); agreement with the declared decimal
precision/scale, integer range, the canonical-digit rules above, and the
canonical float rendering below are semantic checks the adapter performs on a
schema-valid document.

### Canonical float rendering

A `float32` / `float64` value's canonical spelling is the rendering the
ECMAScript number-to-string algorithm produces (ECMA-262 `Number::toString`
base 10 — the same rendering RFC 8785 canonical JSON pins): the shortest
decimal digit sequence that round-trips to the same IEEE-754 value, formatted
as plain decimal notation for magnitudes in `[10^-6, 10^21)` and as exponential
notation otherwise, with a lowercase `e`, an explicitly signed exponent with no
leading zeros, no leading `+` or superfluous leading zeros in the significand,
no trailing fractional zeros (an integral value carries no decimal point, e.g.
`1` not `1.0`), and zero — one logical value per `m-core`, so never
sign-prefixed — rendered as `0`. For `float32` the digit sequence is selected
at binary32 precision by the same rule `Number::toString` pins for binary64:
among the decimal digit sequences that read back to the binary32 value under
round-to-nearest, ties-to-even, take those with the fewest significant digits;
among equally short candidates, the one whose exact decimal value is closest
to the exact binary32 value; on an exact halfway tie, the candidate whose
final digit is even. The formatting rules are unchanged, so every binary32
value has exactly one canonical spelling.

Ingestion reads a float default as the IEEE-754 value the JSON number denotes
under round-to-nearest, ties-to-even at the declared width. A number whose
spelling is not the canonical rendering of the value it denotes (e.g. `1.0`,
`0.10`, `-0.0`, `1e2`) is rejected in the semantic phase, exactly like a
non-canonical decimal digit string, so `serialize(deserialize(descriptor)) ==
descriptor` holds byte-for-byte for float defaults.

### `default` presence semantics

`attribute.default` serializes `m-metamodel`'s
`AttributeDefault = NoDefault | DefaultValue(value)`:

- an **omitted** `default` key is `NoDefault`;
- a **present** `default: null` is `DefaultValue(null)` — legal for every
  declared type;
- any other present value is `DefaultValue(value)` in the declared type's
  encoding above.

JSON and YAML both distinguish an absent key from a null value, so no unset
sentinel value exists, and the canonical serializer never drops an explicit
`default: null`. The reading is unambiguous for a `json` attribute too: a bare
top-level `null` is not a member of the `Json` value space (`m-core`), so
`default: null` always denotes `DefaultValue(null)` and never a `Json` value —
JSON `null` reaches a `json` default only nested inside an array or object.

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
| `type` | neutral type spelling (REQUIRED; see "Type spellings"); `decimal(p,s)` carries precision/scale |
| `column` | optional DB column override; omission means the Attribute `name` |
| `primaryKey` | bool, default `false` |
| `nullable` | bool, default `false` |
| `maxLength` | for `string` (⇒ `varchar(n)`) |
| `readOnly` | bool, default `false` — immutable after insert |
| `optimisticLocking` | bool, default `false` — marks the version attribute (`m-opt-lock`) |
| `pkGeneration` | optional `application-assigned` \| `max` \| Sequence object; legal only when `primaryKey: true`, omission on a primary key means application-assigned |
| `default` | optional typed default value in the declared type's encoding (see "Value encodings"); omission means no default |

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
