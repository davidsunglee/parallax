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

This phase introduces the base elements needed for a single non-temporal entity:
`entity`, `attribute`, and `pkGenerator`. Later phases add `relationship`,
`index`, `asOfAttribute`, `valueObject`, and `inheritance`.

## `entity` — the unit of mapping

| Property | Values / meaning |
|---|---|
| `name` | entity (domain class) name (REQUIRED) |
| `namespace` | logical namespace (language-neutral; replaces Java-style "package") |
| `table` | default table name (REQUIRED) |
| `mutability` | `read-only` (default) \| `transactional` |
| `temporal` | derived classification: `non-temporal` (default) \| `unitemporal-processing` \| `unitemporal-business` \| `bitemporal` |
| children | `attributes` (REQUIRED, non-empty) |

The `temporal` classification is **derived** from the `asOfAttribute` children an
entity declares (none ⇒ `non-temporal`). It is recorded explicitly for clarity
and validated for consistency. In this phase every entity is `non-temporal`.

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

## `pkGenerator` — primary-key generation strategy

A primary-key attribute MAY declare how its value is allocated. For the walking
skeleton, only `none` is exercised; the other strategies are specified so the
schema is stable.

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
