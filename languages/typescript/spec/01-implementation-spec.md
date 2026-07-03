# TypeScript Implementation Spec

This document is a **standalone, template-format specification** for the
TypeScript implementation of Parallax. It follows the prescribed §1–§11 skeleton
of
[`../../../core/spec/language-spec-template.md`](../../../core/spec/language-spec-template.md)
and satisfies that template's *decide-and-record* checklist, so a fresh reader
can author a TypeScript implementation and run the compatibility suite to green
**without re-reading the core spec or any other Parallax document**.

Every template section §1–§11 is specified in full here:

- [§1](#1-conformance-slice-declaration) declares the Conformance Slice this
  build claims — the decision that scopes every other section.
- [§2](#2-api-surface-non-normative--dq3) API surface,
  [§4](#4-transaction-block-demarcation-m8) transaction-block demarcation,
  [§7](#7-codegen-or-not-dq5) codegen, and [§8](#8-collection-idioms-m5)
  collection idioms record the V1 API surface inline.
- [§3](#3-metadata--model-input-format-dq5-dq6) metamodel introspection + serde,
  [§5](#5-test-double-integration-m12-dq15) test-double integration,
  [§6](#6-api-conformance-suite--usage-guide) the API Conformance Suite & Usage
  Guide, [§9](#9-build-time-dependency-enforcement-dq3-dependency-graph)
  build-time dependency enforcement,
  [§10](#10-optional-optimized-data-structures-m13-dq10) optional optimized data
  structures, and
  [§11](#11-per-language-performance-targets-m13-dq10) per-language performance
  targets close the remaining decide-and-record items.

Beyond the template skeleton, the spec also includes a supplementary
[Object lifecycle: detach, snapshots, and entity inputs](#object-lifecycle-detach-snapshots-and-entity-inputs-m9)
section (`M9`).

The document is self-contained: no section defers its answer to another document.
Links to `core/` files point at the authoritative source of truth, but the
substance each one fixes (the metamodel schema's element types, the legal-edge
DAG, the benchmark report schema) is transcribed inline, so the spec is readable
end-to-end on its own.

The [Template Coverage Appendix](#template-coverage-appendix) at the end maps
every template section to its answer location and an explicit status, so any
future gap surfaces as an explicit marker rather than silent prose.

## 1. Conformance Slice declaration

**ANSWERED — see [TS-0064](../docs/adr/0064-adopt-first-implementation-mvp-slice.md).**
The Conformance Slice this build claims leads the spec because it scopes every
other section — the module → package map, the case/dialect matrix
([§5](#5-test-double-integration-m12-dq15)), the conformance-adapter grade, and
the API Conformance Suite ([§6](#6-api-conformance-suite--usage-guide)) are all
bounded by it. A Conformance Slice is a declared, **case-granular** subset of the
compatibility corpus; its machine-readable form is a `describeOk` capability
claim and its name is its `caseTags.include` tag.

### 1.1 V1 conformance capability claims

TypeScript V1 **is** the canonical `slice-mvp-1` Conformance Slice
declared in [`scope-and-tiers.md`](../../../core/spec/scope-and-tiers.md#first-implementation-conformance-slice)
([TS-0064](../docs/adr/0064-adopt-first-implementation-mvp-slice.md)). The V1
conformance adapter MUST report a case-slice-aware `describe`
result whose `capabilities` are **exactly** that canonical slice's capabilities —
the slice is **include-driven** (`caseTags.include: ["slice-mvp-1"]`),
so V1 claims precisely the 116 cases tagged for the slice and returns
`unsupported` for everything else. A V1 adapter that implements the specified
transaction, relationship, list, temporal (bitemporal **reads** + audit-only
processing-temporal), and optimistic-locking surfaces but defers aggregation,
identity-cache scenarios, query-cache scenarios, M9 detached merge-back, PK
generation, value objects, inheritance, error classification, bitemporal
rectangle-split writes, M13 benchmarks, and non-Postgres dialects claims
capabilities in this shape:

```json
{
  "schemaVersion": "1",
  "command": "describe",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "capabilities": {
    "modules": [
      "m0",
      "m1",
      "m2",
      "m3",
      "m4",
      "m5",
      "m7",
      "m8",
      "m10",
      "m11",
      "m12"
    ],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary"],
    "caseTags": {
      "include": ["slice-mvp-1"]
    },
    "commands": ["describe", "compile", "run"],
    "provisioning": "self-managed"
  }
}
```

These `capabilities` are mechanically asserted equal to the canonical slice claim
(see the anti-drift test in
[`test_conformance_adapter_schema.py`](../../../reference-harness/tests/test_conformance_adapter_schema.py));
only the `adapter` identity (`language` / `name` / `version`) differs. The
important V1 rule is the slice boundary:

- The single tag `slice-mvp-1` **is** the slice: a case is claimed
  precisely when it carries that tag and also passes the broad module / dialect /
  shape filters above. Selection is by *presence* of the tag, never by absence, so
  the V1 claim is immune to the corpus's tag hazards (e.g. the single-case
  `mariadb` / `identity cache` tags).
- Aggregation and projection are deferred by §2.8, so 04xx `aggregate` /
  `groupBy` / `having` cases and cases tagged `projection` are untagged and
  therefore outside the claim even though basic M2 predicate reads are inside it.
- The transaction/read-lock/batched-write slice of M8 is inside §4, but the M8
  identity-cache and query-cache scenario slice is deferred by TS-0054. Those
  cache/identity cases are untagged and outside the V1 claim.
- The `scenario` shape is **inside** the claim: the read-your-own-writes scenario
  `0607-read-your-own-writes` is tagged `slice-mvp-1` and runs as
  part of the M8 unit-of-work slice. The deferred M8 cache `scenario` cases
  (identity / query cache) are simply untagged, so they fall outside the claim
  without excluding the shape.
- M9 detached merge-back is deferred by the lifecycle section, so the `detached` /
  `lifecycle detach` cases are untagged and outside the V1 claim unless a later
  implementation explicitly adds that slice.
- M13 benchmarks are **outside** the V1 claim: `m13` is not in `modules` and the
  `benchmark` command is not in `commands` (TS-0062, TS-0064). TypeScript still
  binds to the shared M13 methodology and report shape (§11), but the first build
  does not *claim* benchmark execution in its conformance slice — the benchmark
  surface lands after the first slice.
- MariaDB cases are outside the V1 claim because `dialects` contains only
  `postgres`.

For a case outside the claim, the adapter SHOULD return `status: "unsupported"`
with a diagnostic such as `unsupported-case-tag` or `unsupported-dialect`.
For a case inside the claim, returning `unsupported` is a conformance failure;
the adapter must return `ok` or `error`.

## 2. API surface (non-normative — DQ3)

**ANSWERED — specified in full below.** TypeScript exposes one generated, typed
API surface, imported through the package-local `#parallax` alias.

### 2.1 Generated import surface

Applications import the generated API through the alias `#parallax`; the physical
output path is hidden behind it. The generated barrel exports the `parallax`
factory, the `Parallax` and `ParallaxTransaction` types, each generated entity
symbol (e.g. `Order`) and its managed-object type (`type Order`), entity input
validators/types (`OrderInput`, `type OrderInput`), snapshot types
(`type OrderSnapshot`), public runtime types such as `ParallaxList`,
`ParallaxDecimal`, and `ParallaxJsonValue`, and the public error classes rooted
at `ParallaxError`.

```ts
import {
  Order,
  OrderInput,
  ParallaxOptimisticLockError,
  parallax,
  type Order as OrderObject,
  type OrderSnapshot,
  type Parallax,
  type ParallaxTransaction,
} from "#parallax";
```

The value/type namespace overlap is deliberate: `Order` is both the entity symbol
value used in expressions and the managed object `type Order` (aliasable as
`OrderObject` when clarity matters).

No generated enum types or structured value-object interfaces are part of
TypeScript V1. The canonical descriptor has no enum element, and a `valueObject`
declares only its element name, logical type name, backing column, mapping, and
nullability. Generated value-object properties therefore use the unstructured
`ParallaxJsonValue` scalar mapping from [§3.2.1](#321-m0-scalar-runtime-mapping),
and nested value-object predicates use untyped string paths after the declared
value-object name. A future core descriptor extension that describes enum values
or value-object fields may add generated types, but V1 codegen MUST NOT invent
them from TypeScript-local assumptions.

### 2.2 Parallax handle

The generated `parallax(...)` factory creates the configured `Parallax` handle
(conventionally named `px`), binding the generated metamodel, database adapter,
clock strategy, read API, transaction API, and runtime behavior behind one entry
point. It is not a raw connection, client, or session.

```ts
const px: Parallax = parallax({ database, clock });
```

### 2.3 Finder / query entry point

TypeScript uses one generated fluent expression DSL for predicates,
relationships, assignments, and sort keys — there is no second object-filter
language. `find` is the only V1 read operation that returns managed domain
objects; it always returns a `ParallaxList`
([§8](#8-collection-idioms-m5)), which may resolve to zero, one,
or many objects. `find()` without a predicate is shorthand for
`find(Entity.all())`; entity symbols also expose `none()` for dynamic predicate
construction.

```ts
const orders = px.orders.find(
  Order.status.eq("Processing").and(
    Order.lineItems.exists(item => item.quantity.gt(2)),
  ),
  {
    includes: [Order.customer, Order.lineItems.product],
    orderBy: [Order.createdAt.desc(), Order.id.asc()],
    limit: 50,
  },
);
```

### 2.4 Result types

`find` returns a `ParallaxList` — an async, operation-backed list
(`M5`, [§8](#8-collection-idioms-m5)). Single-object access is spelled through
`ParallaxList` helpers (`first` / `firstOrNull` / `single` / `singleOrNull`):
`first`/`single` throw `ParallaxNotFoundError` when empty and `single` throws
`ParallaxTooManyResultsError` for more than one result. Full collection idioms
are in [§8](#8-collection-idioms-m5).

### 2.5 Predicates and the `group` operator (`M2`)

Predicate methods use compact names: `eq`, `notEq`, `gt`, `gte`, `lt`, `lte`,
`isNull`, `isNotNull`, `in`, `notIn`. `eq(null)` / `notEq(null)` are rejected in
favor of `isNull()` / `isNotNull()`. Empty membership predicates normalize before
serialization: `attr.in([])` → `none`, `attr.notIn([])` → `all`. String
predicates take a `{ caseInsensitive: true }` option rather than separate method
names (e.g. `Order.name.startsWith("acme", { caseInsensitive: true })`).
Predicates expose postfix `.not()`; to-many relationships expose explicit
`notExists`.

Boolean chaining with `.and(...)` / `.or(...)` is **left-associative**; explicit
precedence is expressed with **postfix `.group()`**, which serializes to the
canonical `group` node:

```ts
Order.status.eq("Processing")
  .and(Order.priority.eq("High").or(Order.customer.region.eq("NA")).group());
```

### 2.6 Relationship navigation and deep-fetch (`M4`)

To-one relationships support direct path navigation
(`Order.customer.region.eq("NA")`); to-many relationships require an explicit
quantifier (`Order.lineItems.exists(...)` / `.notExists(...)`). The eager-fetch
navigation set is declared with the `includes` option, whose values are generated
relationship paths (`includes: [Order.customer, Order.lineItems.product]`);
longer paths imply their prefixes (`Order.lineItems.product` implies
`Order.lineItems`). Includes issue batched secondary fetches per relationship hop
(the `1 + levels` deep-fetch contract of
[§11.3](#113-binding-invariant--expectroundtrips-non-placeholder)), not a left join
per to-one.
Navigating a relationship that was not included may lazily resolve it.

### 2.7 Ordering

Ordering uses generated sort keys (`orderBy: [Order.createdAt.desc(),
Order.id.asc()]`). Sort keys are query expressions in V1, not JavaScript
comparators.

### 2.8 Aggregation spelling (`M2` sub-area) — deferred

`find` never returns partial managed objects. Selective retrieval and grouped
aggregate reads are reserved for `project(...)` (`where` / `groupBy` / `select` /
`having` / `orderBy`), which returns plain data rather than managed objects.
**Projection and aggregation are deferred from V1** (recorded so the surface
choice is not re-opened). In-memory reuse of predicates as `Array.filter`
callbacks and of sort keys as `Array.sort` comparators is likewise deferred.

### 2.9 Temporal reads (`M7`)

TypeScript timestamps use `Temporal.Instant` and are constrained to the core M0
microsecond boundary: values with non-zero sub-microsecond precision are rejected
at the Parallax API boundary rather than truncated. The explicit current-row
token is the string literal `"now"`; in an `asOf` option it serializes to the
core `now` temporal pin and is equivalent to omitting that axis.

```ts
type TemporalAxis = "processing" | "business";
type TemporalPoint = Temporal.Instant | "now";
type TemporalRange = {
  start: Temporal.Instant;
  end: Temporal.Instant;
};
type TemporalReadOptions = {
  asOf?: {
    processing?: TemporalPoint;
    business?: TemporalPoint;
  };
  range?: {
    processing?: TemporalRange;
    business?: TemporalRange;
  };
  history?: readonly TemporalAxis[];
};
```

`TemporalReadOptions` is part of the second `find` argument. `find` still returns
`ParallaxList<T>`; the temporal options only affect the operation serialized to
M2 and the rows that resolve when the list is read.

```ts
const currentBalances = px.balances.find(Balance.acctNum.eq("A"));

const historicalBalances = px.balances.find(Balance.acctNum.eq("A"), {
  asOf: {
    processing: Temporal.Instant.from("2024-04-01T00:00:00Z"),
  },
});

const rangedBalances = px.balances.find(Balance.all(), {
  range: {
    processing: {
      start: Temporal.Instant.from("2024-06-15T00:00:00Z"),
      end: Temporal.Instant.from("2024-07-01T00:00:00Z"),
    },
  },
});

const fullPositionHistory = px.positions.find(Position.id.eq(1), {
  history: ["business", "processing"],
});
```

Axis names are the core temporal axis names, not column names. For a given
entity, `processing` maps to the entity's `asOfAttribute` with
`axis: "processing"` and `business` maps to the one with `axis: "business"`.
Supplying an axis the entity does not declare is a validation error.

`asOf`, `range`, and `history` are mutually exclusive **per axis**. For example,
`{ asOf: { business: t }, history: ["processing"] }` is valid for a bitemporal
entity, but `{ asOf: { business: t }, history: ["business"] }` is rejected.
Range `start` is inclusive and `end` is exclusive; `start` must be strictly
before `end`.

The TypeScript adapter serializes explicit temporal reads to the core M2 nodes:

- `asOf.processing` / `asOf.business` → `asOf`
- `range.processing` / `range.business` → `asOfRange`
- `history: ["processing" | "business"]` → `history`

When both axes are present, serialization is deterministic: the business-axis
wrapper is outside the processing-axis wrapper, matching the core bind order
(business binds before processing binds). Omitted temporal axes are not
serialized; the M7 default-injection rule still applies and reads them as
current (`now`).

## 3. Metadata / model input format (DQ5, DQ6)

**ANSWERED — see [TS-0055](../docs/adr/0055-metamodel-introspection-api-has-generic-and-typed-layers.md),
[TS-0056](../docs/adr/0056-one-canonical-serde-shared-by-metamodel-and-operations.md),
[TS-0057](../docs/adr/0057-serde-states-roundtrip-contract-and-names-libraries-nonbindingly.md).**
The metamodel (`M1`) is one artifact wearing two hats — an introspectable runtime
protocol and a serializable document — and this section specifies both hats so an
implementer can build the metamodel layer without inferring its shape from
`m1-metamodel.md`.

### 3.1 Primary authoring format

The authoring format is **descriptor-first** (the codegen pipeline is specified
in [§7](#7-codegen-or-not-dq5)): the source of truth is the canonical Parallax
YAML/JSON descriptor set —
the same serialized metamodel the compatibility corpus uses — and a descriptor
validates
against [`metamodel.schema.json`](../../../core/schemas/metamodel.schema.json). A
descriptor is either a single `entity` or an `entities` array (≥1 entity, so
relationships can name siblings). The typed entity symbols and the generic reader
below are both derived from that one descriptor; decorators/builders may be added
later as authoring conveniences but the serialized descriptor stays the backbone.

### 3.2 Introspection API (the `RelatedFinder` / `ReladomoClassMetaData` analogue)

Introspection is exposed in **two layers over the same descriptor** (TS-0055): a
**generic reader** over any parsed descriptor (no codegen required), and **typed
accessors** generated onto each entity symbol that delegate to it. The generic
layer is what the generator, the serde round-trip, and the `parallax-conformance`
adapter use, since they handle arbitrary corpus descriptors with no generated
symbols; the typed layer is the application-facing surface, hung off the existing
query-DSL symbols.

```ts
// Typed layer — on the generated entity symbol (the RelatedFinder analogue)
Order.table;                            // string — the mapped table name
Order.namespace;                        // string | undefined
Order.mutability;                       // "read-only" | "transactional"
Order.temporal;                         // "non-temporal" | "unitemporal-processing"
                                        //   | "unitemporal-business" | "bitemporal"
Order.attributes;                       // readonly AttributeMeta[]
Order.primaryKeyAttributes;             // readonly AttributeMeta[] (primaryKey === true)
Order.asOfAttributes;                   // readonly AsOfAttributeMeta[] (0–2)
Order.relationships;                    // readonly RelationshipMeta[]
Order.indices;                          // readonly IndexMeta[]
Order.valueObjects;                     // readonly ValueObjectMeta[]
Order.inheritance;                      // InheritanceMeta | undefined
Order.attributeByName("status");        // AttributeMeta | undefined
Order.relationshipByName("lineItems");  // RelationshipMeta | undefined
Order.status.column;                    // metadata reachable on the attribute symbol

// Generic layer — over any parsed descriptor, no codegen required
px.metamodel.entity("Order");           // EntityMetadata (same shape as the typed symbol)
px.metamodel.entity("Order").attributes;
px.metamodel.entities;                  // readonly EntityMetadata[] (normalizes single-vs-array)
```

Both layers expose the **same metadata shapes**, one per metamodel element type. The
field set below is drawn one-to-one from `metamodel.schema.json`'s **eight element
types**, so every property in a descriptor is reachable from §3 alone:

| Element type | Reader shape | Fields (← schema) |
|---|---|---|
| `entity` | `EntityMetadata` | `name`, `table`, `namespace?`, `mutability`, `temporal`, `attributes`, `asOfAttributes`, `relationships`, `indices`, `valueObjects`, `inheritance?`; plus derived `primaryKeyAttributes`, `attributeByName(name)`, `relationshipByName(name)`, `isTemporal` |
| `attribute` | `AttributeMeta` | `name`, `type` (M0 neutral type, incl. `decimal(p,s)`), `column`, `primaryKey`, `nullable`, `maxLength?`, `readOnly`, `optimisticLocking`, `pkGenerator?`, `default?` |
| `relationship` | `RelationshipMeta` | `name`, `relatedEntity`, `cardinality` (`one-to-one`/`many-to-one`/`one-to-many`/`many-to-many`), `join`, `reverseName?`, `dependent`, `foreignKey?`, `orderBy?` (`{ attr, direction }[]`) |
| `index` | `IndexMeta` | `name`, `attributes` (ordered attribute names), `unique` |
| `asOfAttribute` | `AsOfAttributeMeta` | `name`, `fromColumn`, `toColumn`, `axis` (`processing`/`business`), `toIsInclusive`, `infinity` (`"infinity"`), `default` (`"now"`) |
| `valueObject` | `ValueObjectMeta` | `name`, `type` (logical struct name), `column` (single structured-document column), `mapping` (`"json"`), `nullable` |
| `inheritance` | `InheritanceMeta` | `strategy` (`table-per-hierarchy`/`table-per-leaf`), `role` (`root`/`subtype`), `parent?`, `discriminator?` (`{ column }`), `discriminatorValue?` |
| `pkGenerator` | `PkGeneratorMeta` | `strategy` (`none`/`max`/`sequence`); for `sequence`: `sequenceName?`, `batchSize?`, `initialValue?`, `incrementSize?` (the bare-enum form normalizes to `{ strategy }`) |

Defaulting follows the schema: readers surface the schema defaults
(`mutability: "read-only"`, `temporal: "non-temporal"`, `primaryKey: false`,
`nullable: false`, `readOnly: false`, `optimisticLocking: false`,
`dependent: false`, `unique: false`, `toIsInclusive: false`, `mapping: "json"`,
`nullable: false`) when a field is omitted, so the typed and generic layers agree
on every value. This mirrors the Python harness's `Entity` / `Model` accessors,
which are the concrete generic reader over the raw parsed descriptor.

### 3.2.1 M0 scalar runtime mapping

Generated TypeScript code maps every M0 neutral scalar to one public runtime
representation. These choices are part of the compatibility boundary: generated
managed objects, snapshots, input validators, assignment expressions, operation
binds, and conformance adapter results all use the same mapping. Adapter-specific
database client types such as Node `Buffer`, Postgres numeric strings, or driver
date objects are normalized at the adapter boundary and are not exposed through
generated application APIs.

The generated barrel re-exports `ParallaxDecimal` and `ParallaxJsonValue` from
`@parallax/core`, alongside the other public runtime types. `ParallaxDecimal` is
a Parallax-owned immutable exact-decimal value constructed from a canonical
decimal string and rendered back with `toString()`. It is not JavaScript
`number`, and the spec does not require a particular third-party decimal
library. `ParallaxJsonValue` is the structural JSON value type:
`null | boolean | number | string | ParallaxJsonValue[] | { [key: string]:
ParallaxJsonValue }`.

| M0 scalar | Generated property / snapshot type | Create / update input type | Adapter bind type | Materialization rule |
|---|---|---|---|---|
| `boolean` | `boolean` | `boolean` | `boolean` | Preserve the boolean value exactly. |
| `int32` | `number` | `number` | `number` | Validate a signed 32-bit integer; reject non-integers and out-of-range values. |
| `int64` | `bigint` | `bigint \| string` | Canonical base-10 string | Parse input strings as signed 64-bit integers; reject `number` input to avoid precision loss; materialize database integers/text as `bigint`. |
| `float32` | `number` | `number` | `number` | Validate a finite JavaScript number and bind through the dialect's 32-bit float path. |
| `float64` | `number` | `number` | `number` | Validate a finite JavaScript number and bind through the dialect's 64-bit float path. |
| `decimal(p,s)` | `ParallaxDecimal` | `ParallaxDecimal \| string` | Canonical decimal string | Validate precision `p` and scale `s`; reject `number` input; materialize exact database numeric text as `ParallaxDecimal`. |
| `string` | `string` | `string` | `string` | Preserve UTF-8 text and enforce `maxLength` when present. |
| `bytes` | `Uint8Array` | `Uint8Array \| ArrayBuffer` | `Uint8Array` | Copy input bytes before persistence; materialize a fresh `Uint8Array`; adapters may convert to client-specific binary values internally. |
| `date` | `Temporal.PlainDate` | `Temporal.PlainDate \| string` | ISO `YYYY-MM-DD` string | Parse strings as timezone-naive calendar dates; reject offsets and time components. |
| `time` | `Temporal.PlainTime` | `Temporal.PlainTime \| string` | ISO wall-clock time string | Parse strings as timezone-naive times of day; reject dates and timezone offsets. |
| `timestamp` | `Temporal.Instant` | `Temporal.Instant \| string` | UTC ISO instant string with microsecond precision | Parse strings as absolute instants; reject non-zero sub-microsecond precision; materialize UTC instants as `Temporal.Instant`. |
| `uuid` | `string` | `string` | Canonical lowercase UUID string | Validate RFC 4122 shape and normalize to lowercase canonical text. |
| `json` | `ParallaxJsonValue` | `ParallaxJsonValue` | `ParallaxJsonValue` | Preserve JSON-compatible structure only; reject `undefined`, functions, symbols, bigint, dates, and cyclic objects; adapters lower to dialect-native structured-document columns. |

Nullability is orthogonal to the scalar mapping. When an attribute or value
object is `nullable: true`, generated property and input types union the mapped
type with `null`; non-nullable fields reject `null` before binding. `undefined`
means "field omitted" only in validation helpers for optional create/update
payloads; it is never a persisted scalar value.

`Temporal.PlainDate`, `Temporal.PlainTime`, and `Temporal.Instant` use the
standard Temporal API. Runtimes without native Temporal support MUST provide the
same API through a polyfill before generated code executes. JavaScript `Date` is
not part of the public scalar surface.

### 3.3 Serde module

A dedicated **`@parallax/serde`** package is the single canonical, format-agnostic
serde seam, shared by the metamodel (`M1`) and the operation algebra (`M2`) — the
same shared seam the Python harness realizes in `serde.py` and proves as `M12`
layer 4a/4b (TS-0056). Giving serde its own package satisfies the template's
"dedicated module" requirement; sharing it across `M1`/`M2` guarantees the adapter
canonicalizes identically to the oracle.

```ts
// @parallax/serde — canonical serialize / deserialize / round-trip
canonical(value): unknown                  // sort object keys recursively, PRESERVE list order
serialize(value, fmt: "json" | "yaml"): string
deserialize(text: string, fmt: "json" | "yaml"): unknown
assertRoundTrip(value): void               // JSON and YAML; idempotent + value-identity
```

The serde module MUST satisfy this **round-trip contract** (TS-0057), transcribed
from the Python harness so it canonicalizes identically to the oracle:

- **Safe load.** `deserialize` uses a safe loader that never constructs arbitrary
  types from input (the YAML analogue of `yaml.safe_load`; `JSON.parse` is already
  safe).
- **Deterministic recursive key sort.** `canonical` sorts object keys recursively.
- **List-order preservation.** Array order is preserved (never sorted), because
  order is significant in the operation algebra and in attribute/row sequences.
- **Lossless JSON+YAML round-trip.** For each of JSON and YAML,
  `assertRoundTrip(value)` asserts serialization is idempotent
  (`serialize(canonical(value))` is a fixed point) and that re-parsing
  canonicalizes back to the same value (no data loss). This realizes the `M1`
  normative requirement `serialize(deserialize(descriptor)) == descriptor` in both
  formats, asserted for every model referenced by a compatibility case.

The `yaml` package (or `js-yaml`) plus built-in `JSON` is a **non-binding** suggested
default with the canonicalizer written in-house; the round-trip contract above —
not any named library — is the normative requirement (TS-0057).

## 4. Transaction-block demarcation (M8)

**ANSWERED — specified in full below.** All writes require an explicit
transaction; reads may use `px`, writes are available only through `tx`.

- **Demarcation construct.** A **closure**: `await px.transaction(async tx =>
  { … }, options?)`. `transaction` returns the callback's resolved value after the
  unit of work flushes and commits. If the callback throws, rejects, or commit
  fails, the transaction rolls back and the returned promise rejects. A
  `ParallaxTransaction` is invalid after its callback completes.
- **Strategy selection.** `TransactionOptions.concurrency` (`"locking" |
  "optimistic"`, default `"locking"`) selects the M8 correctness strategy for the
  unit of work: `locking` takes the implicit shared read lock on in-transaction
  reads and advances a versioned entity's version with no gate; `optimistic` takes
  no lock and gates a versioned update on the observed version (M10).

  ```ts
  await px.transaction(async tx => {
    const order = await tx.orders.create(input);
    await tx.orders.update(Order.id.eq(order.id), {
      set: [Order.status.set("Processing")],
    });
    await tx.orders.delete(Order.id.eq(order.id));
  });
  ```

- **Bounded automatic retry.** `TransactionOptions.retries` (default **10**; `0`
  disables the loop) and `TransactionOptions.retryOptimisticConflicts` (default
  `false`) configure the M8/M10 retry contract (ADR 0031 / TS ADR 0065). On a
  **retriable** failure the boundary rolls back, discards the unit of work's
  observed state, and re-executes the body against fresh state, up to `retries`
  re-executions — each attempt opens a **fresh** driver transaction and a **fresh**
  `ParallaxTransaction`, so the retry re-reads (there is no process-wide cache to
  invalidate). A **transient** database failure (a `ParallaxTransientError` whose
  `retriable` is set — the `deadlock` category, covering deadlock and serialization
  failure, classified from the driver's SQLSTATE through `@parallax/dialect`) is
  retried by default; a `ParallaxOptimisticLockError` joins the retriable set only
  when `retryOptimisticConflicts` is `true` (then a re-executed body re-reads the
  fresh version and succeeds with no caller retry code). A lock-wait timeout
  (`55P03`) is not retriable. An exhausted bound surfaces the failure to the caller,
  its message annotated with the attempt count.

  ```ts
  await px.transaction(body, {
    concurrency: "optimistic",
    retries: 10,                     // default; 0 disables the loop
    retryOptimisticConflicts: true,  // else a conflict surfaces after one attempt
  });
  ```

- **Nested / re-entrant transactions.** Nested transactions **join** the active
  transaction. There are no savepoints in V1; an inner failure rolls back the
  enclosing transaction.
- **Unit-of-work surfacing.** There is **no public `flush` API** in V1. The
  runtime flushes at commit and uses unit-of-work state for read-your-writes
  behavior.
- **In-transaction reads.** An **object find** performed through
  `ParallaxTransaction` in the default `locking` mode takes the core shared row lock
  automatically — applying the lock is a **dialect concern** (the runtime asks
  `@parallax/dialect`'s `applyReadLock` to attach `for share of t0`), shared by the
  flat find and every deep-fetch level through one in-transaction read executor. A
  **projection / aggregation** read (a `distinct` result) takes **no** lock and
  **proceeds unlocked — it never errors** (no base row to lock; unmanaged data per
  ADR 0024 / ADR 0030); `optimistic`-mode reads take no lock either. A versioned
  read records the observed version so a later update can gate on / advance from it.
  V1 does not expose a per-read `lock: false`.
- **Set-based writes.** `update` / `delete` accept either a predicate or an
  unresolved `ParallaxList` target, use explicit assignment arrays (not partial
  objects), and return result objects carrying at least `affectedRows`. On a
  versioned entity the framework-owned version (ADR 0029) advances in both modes
  and gates in `optimistic` mode: updating a row the unit of work never observed
  throws `ParallaxReadBeforeWriteError`, a stale gate (zero rows) throws
  `ParallaxOptimisticLockError`, and an update whose assignment array changes no
  attribute issues no DML. Optimistic-lock conflicts are caller-driven and not
  auto-retried.

### 4.1 Temporal writes (`M7`)

All temporal writes run through `ParallaxTransaction`; the root `px` handle has
no write methods. Processing instants are never accepted as per-operation
options. They come from the clock strategy supplied to `parallax({ clock })`, so
production code cannot rewrite audit history while tests can inject a fixed
clock.

The canonical TypeScript V1 `slice-mvp-1` slice requires only the
audit-only processing-temporal write surface below, plus the temporal read
surface in §2.3. Business-temporal-only writes and bounded bitemporal
rectangle-split writes are specified here as the post-slice M7 surface, but they
are not claimed by V1 until the canonical slice's case tags and capabilities are
expanded.

```ts
type WriteResult = {
  affectedRows: number;
};
```

The V1 temporal write surface is:

```ts
await tx.balances.create(input);

await tx.balances.update(Balance.id.eq(1), {
  set: [Balance.value.set(150)],
});

await tx.balances.terminate(Balance.id.eq(1));
```

`create` returns `Promise<T>` for the generated managed-object type `T`.
`update` and `terminate` return `Promise<WriteResult>`. Each method validates
the entity's temporal mode before issuing SQL.

`create` on an audit-only processing-temporal entity opens the current milestone
at the transaction processing instant. `update` closes the current row and chains
a new current row; `terminate` closes the current row and inserts no replacement.
`terminate` is temporal removal; `delete` remains the physical-delete operation
for non-temporal entities.

#### Deferred business-axis temporal writes

The following types and methods belong to a later slice that claims
business-axis writes:

```ts
type BusinessStart = {
  business: {
    start: Temporal.Instant;
  };
};

type BusinessWindow = {
  business: {
    start: Temporal.Instant;
    end: Temporal.Instant;
  };
};
```

```ts
await tx.reservations.create(input, {
  business: {
    start: Temporal.Instant.from("2024-01-01T00:00:00Z"),
  },
});

await tx.positions.createUntil(input, {
  business: {
    start: Temporal.Instant.from("2024-03-01T00:00:00Z"),
    end: Temporal.Instant.from("2024-09-01T00:00:00Z"),
  },
});

await tx.positions.updateUntil(Position.id.eq(1), {
  set: [Position.value.set(200)],
}, {
  business: {
    start: Temporal.Instant.from("2024-03-01T00:00:00Z"),
    end: Temporal.Instant.from("2024-09-01T00:00:00Z"),
  },
});

await tx.positions.terminateUntil(Position.id.eq(1), {
  business: {
    start: Temporal.Instant.from("2024-03-01T00:00:00Z"),
    end: Temporal.Instant.from("2024-09-01T00:00:00Z"),
  },
});
```

`create(input, { business: { start } })` and `createUntil` return `Promise<T>`
for the generated managed-object type `T`. `update`, `terminate`, `updateUntil`,
and `terminateUntil` return `Promise<WriteResult>`. Each method validates its
temporal option before issuing SQL.

For a business-temporal-only entity, `create(input, { business: { start } })`
opens a row effective from `start` to infinity. `update` and `terminate` accept
the same `BusinessStart` option and close/chain on the business axis from that
instant.

For a bitemporal entity, bounded business-window writes use explicit `*Until`
verbs and a required `BusinessWindow`. The TypeScript public insert spelling is
`createUntil` because the non-temporal insert API is `create`; the conformance
adapter maps it to the core `insertUntil` write-sequence mutation. `updateUntil`
maps to the core `updateUntil` rectangle split, and `terminateUntil` maps to the
core `terminateUntil` rectangle split without a middle row.

All `BusinessStart` and `BusinessWindow` instants are `Temporal.Instant` values
subject to the same microsecond boundary as timestamp attributes. `BusinessWindow`
uses half-open `[start, end)` semantics and requires `start < end`. Passing a
processing axis, a processing instant, or a sub-microsecond instant is a
validation error.

## 5. Test-double integration (M12, DQ15)

**ANSWERED — see [TS-0058](../docs/adr/0058-compatibility-suite-uses-vitest.md),
[TS-0059](../docs/adr/0059-cases-discovered-by-glob-executed-through-conformance-adapter.md),
[TS-0060](../docs/adr/0060-typescript-runs-postgres-only-in-ci-pinned-to-postgres-17.md).**
The TypeScript conformance suite proves the implementation against the same
language-neutral corpus the Python reference harness proves green. This section
specifies the runner, how cases are discovered and executed, how the database is
provisioned, and which dialects run in CI — enough to stand up the suite without
inferring it from the harness internals.

### 5.1 Test runner

The runner is **vitest** (TS-0058). The suite is a parametrized matrix of
discovered compatibility cases × dialects — the same shape as the Python harness's
parametrized `test_compatibility.py` — and vitest's `test.each` / programmatic test
generation maps directly onto it, so every `(case, dialect)` pair is its own named,
independently reportable test. vitest is dev-only test tooling, not shipped runtime
code. `node:test` is the documented fallback if a strict no-dev-dependency stance is
later preferred; it would run the same matrix but push case-matrix generation into a
hand-rolled harness module.

### 5.2 Case discovery and execution boundary

Cases are **discovered by glob**, mirroring the Python harness's `discover_cases`
(`reference-harness/src/reference_harness/case.py`):

- Glob `core/compatibility/cases/**/*.{yaml,yml}`, **dedupe and sort**, then load
  each case and the model descriptor it references (resolving `models/<name>.yaml`
  and the stem-matched `fixtures/<model-stem>.yaml` sidecar).
- Generate one parametrized test per `(case × dialect)`.

Globbing the same files the oracle proves keeps the case set authoritative — there
is no hand-maintained list to drift — and the sorted, deduped order makes the
matrix deterministic.

Cases are **executed through the `parallax-conformance` adapter contract** (TS-0059,
[`conformance-adapter-contract.md`](../../../core/spec/conformance-adapter-contract.md)),
**not** by reaching into runtime internals:

- `parallax-conformance compile --case <c.yaml> --dialect <d>` emits SQL + binds and
  MUST NOT execute; the test compares the emitted statements and round-trip count.
- `parallax-conformance run --case <c.yaml> --dialect <d>` provisions, executes, and
  returns observations; the test compares the JSON envelope using the **same
  comparison rules `M12` uses**.

The adapter is the single behavioral boundary: the suite imports no finder builders,
cache objects, or other internals. This decouples the suite from implementation
detail and reuses the shared corpus as the primary behavioral surface.

The suite MUST begin with `parallax-conformance describe` and use the returned
capability claims to decide whether a case is expected to run or expected to
return `status: "unsupported"`. TypeScript uses the core
`caseTags.include` / `caseTags.exclude` claim model; it MUST NOT treat broad
`modules` + `caseShapes` claims as sufficient when a V1 slice deliberately
defers part of a module.

### 5.3 Provisioning seam

Provisioning is **Testcontainers for Node** — `@testcontainers/postgresql` — behind
the same database-provider seam the `parallax-conformance run` adapter consumes
(TS-0060). The image is pinned to **`postgres:17`**, the exact image the reference
harness pins (`reference-harness/src/reference_harness/providers/postgres.py`,
`POSTGRES_IMAGE = "postgres:17"`); the two are already aligned, so no harness change
or downgrade is required, and the TypeScript pin bumps only when the harness bumps
its major.

The container is booted once per dialect (session-scoped, as the Python harness
does), but database state is reset **through the provider seam**, not through a
test-runner call to a container-specific API. The TypeScript provider MUST expose
a reset lifecycle equivalent to the reference `DatabaseProvider` seam:

```ts
interface CompatibilityDatabaseProvider {
  readonly dialect: "postgres";
  reset(): Promise<void>;                 // clean, empty database/schema
  applyDdl(statements: readonly string[]): Promise<void>;
  load(
    table: string,
    columns: readonly string[],
    rows: readonly (readonly unknown[])[],
  ): Promise<void>;
}
```

For every database-backed `run` case, the conformance adapter calls
`provider.reset()`, derives and applies DDL for the case's model, and then loads
fixture rows according to the core case lifecycle (`writeSequence` cases start
empty unless the case sets `loadFixtures`; read/scenario/conflict cases load the
model fixtures). This yields the same clean / migrated / isolated state as the
Python harness without coupling the suite to Testcontainers internals.

The normative Postgres reset is drop-and-recreate of the active schema, matching
the reference provider's `drop schema if exists public cascade; create schema
public` behavior. An implementation MAY optimize this behind
`CompatibilityDatabaseProvider.reset()` with a documented snapshot mechanism
provided by a concrete dependency and version (for example a Postgres-module
snapshot API), but that optimization must be invisible to the test runner and
MUST have a drop/recreate fallback. The spec does not require a portable
Testcontainers snapshot API.

### 5.4 CI dialect set and per-dialect golden-SQL selection

For V1, TypeScript runs **Postgres only** in CI (TS-0060) — the round-1 normative
target (`m11-dialect-seam.md`). Per-dialect golden SQL is selected by the provider's
own `dialect` identifier, which is the `goldenSql` key on the case:

- When the active dialect **has** a `goldenSql` entry, the full set of layers runs,
  including database execution against the container.
- When the active dialect has **no** `goldenSql` entry, **database execution is
  skipped** and the dialect-agnostic checks still run (schema conformance,
  normalization determinism, serde round-trip, equivalent encodings, round-trip
  count) — the same skip behavior the Python harness applies.

**MariaDB is deferred-but-additive**, not removed: adding it later is a new provider
behind the same seam plus a `goldenSql.mariadb` key on the affected cases — never a
runner redesign. The dialect seam is already proven beyond Postgres by the Python
oracle, so a second CI database buys no additional V1 conformance and is omitted from
V1 in keeping with the thin-slice posture (cf. TS-0054).

## 6. API Conformance Suite & Usage Guide

**ANSWERED — the suite lives at
`packages/typescript/test/api-conformance/` and the Usage Guide at
`languages/typescript/docs/guide/`.** Beyond the wire-level conformance adapter of
[§5](#5-test-double-integration-m12-dq15), TypeScript proves that the idiomatic
developer surface of [§2](#2-api-surface-non-normative--dq3) reproduces the
claimed slice against a real Postgres through the shipped `@parallax/db-postgres`
adapter, and renders a Usage Guide from that same suite source. Both are the
worked example of the language-neutral
[`api-conformance-contract.md`](../../../core/spec/api-conformance-contract.md):
they are additive proof beside the conformance-adapter grade and never touch the
grader.

### 6.1 Suite framework and location

The API Conformance Suite is a **vitest** suite at
`packages/typescript/test/api-conformance/`, run by the `just ts-api-conformance`
lane against a Testcontainers `postgres:17` container — the same image
[§5.3](#53-provisioning-seam) pins. Each family
(`reads` / `deep-fetch` / `temporal` / `transactions` / `locking`) is a
`*.api-conformance.test.ts` file that provisions the case's model, writes the
**idiomatic `px.*` / `px.transaction` developer code** an application would write,
and asserts the corpus's expected results. Family suites gate their Docker-backed
runs on a `docker info` probe; the Docker-free `coverage.test.ts` enforces the
partition below.

### 6.2 Coverage partition and no-drift guard

- **Coverage partition.** `coverage.test.ts` (Docker-free) discovers exactly the
  116 `slice-mvp-1` cases and asserts `exercised ∪ skipped == slice`
  with no stale ids: every in-slice case is either exercised by a family suite
  (`covered.ts`) or listed in the reasoned skip manifest (`skip-manifest.ts`),
  and every skip carries a non-empty reason — a silent gap fails the build.
- **No-drift guard.** Every developer-surface case first calls
  `assertSameOperation(built, corpus)`: the operation the idiomatic DSL builds
  MUST canonically equal the corpus operation, so the suite can never pass by
  exercising a different query than the one the corpus pins.
- **Golden SQL text is excluded** (it is not a developer-facing surface). The
  suite compares rows, graphs, table state, and round-trip counts, and
  additionally asserts language-specific managed shapes (`bigint` /
  `ParallaxDecimal` / `Temporal.*` / `Uint8Array`) that the wire-value grader
  deliberately ignores.

### 6.3 Reasoned skips

Two of the 116 cases are reason-skipped because what they prove is serde/harness
machinery a developer never authors, not a developer-facing surface:

- **`0222`** — an `equivalentEncodings` serde-canonicalization check (two surface
  spellings collapse to one canonical operation). Its query semantics are
  exercised through the developer surface elsewhere; its ungrouped sibling `0223`
  runs in `reads.api-conformance.test.ts`.
- **`0226`** — `distinct` on a single *projected* column, whose witness result is
  projection-specific. V1 `find` returns whole managed objects, so a
  projected-column result needs the out-of-V1 aggregation/projection surface
  (deferred by §2.8).

### 6.4 Usage Guide rendering and drift check

The Usage Guide (`docs/guide/*.md`) is **generated from the suite's source** by
`scripts/render-guide.mjs`, so its worked examples are the executed suite code
rather than hand-maintained copies. CI re-runs `render-guide.mjs --check`, which
fails if the committed guide has drifted from the suite source — the
language-local realization of the contract's guide drift-check requirement.

## 7. Codegen-or-not (DQ5)

**ANSWERED — specified in full below.**

- **Technique.** TypeScript V1 uses **codegen** and is **descriptor-first**: the
  source of truth is the canonical Parallax YAML/JSON descriptor set (the same
  serialized metamodel the compatibility corpus uses, validated against
  `metamodel.schema.json` per [§3.1](#31-primary-authoring-format)). The typed
  entity symbols, managed-object types, entity input types, snapshot types,
  value-object properties as unstructured JSON values, and operation accessors
  are all generated from it. Codegen MUST emit only artifacts derivable from
  `metamodel.schema.json`; enum types and structured value-object field types are
  not generated in V1 because the descriptor does not define them. Codegen is
  chosen over runtime reflection/proxies so the typed finder/object surface is
  statically checkable and matches the generated import barrel
  ([§2.1](#21-generated-import-surface)). Decorators and TypeScript schema
  builders may be added later as descriptor-authoring conveniences, but the
  serialized descriptor stays the backbone.
- **Generator config and inputs.** Generator config uses the `descriptors` key
  (not `specs` / `models`):

  ```ts
  import { defineParallaxConfig } from "@parallax/typescript/config";

  export default defineParallaxConfig({
    descriptors: ["./parallax/**/*.yaml"],
    output: "./.parallax/generated",
    importAlias: "#parallax",
  });
  ```

- **CLI.** The package provides `parallax init` (a conservative setup assistant
  supporting `--dry-run` / `--force`; it adds explicit `parallax:generate` /
  `parallax:check` scripts by default and wires `prebuild` / `pretest` lifecycle
  hooks only under an opt-in flag such as `--wire-lifecycle`), `parallax generate`
  (materializes the generated output), and `parallax generate --check` (validates
  descriptors, generator configuration, and code generation, failing if generation
  would fail; since generated files are uncommitted, this is not a git drift
  check). Conformance is exposed through the **separate** `parallax-conformance`
  CLI, not the generated `#parallax` API. The canonical V1 command claim exposes
  `describe` / `compile` / `run`; `benchmark` is the post-slice M13 command
  described in §11 and is not claimed by the `slice-mvp-1` slice —
  see [§5](#5-test-double-integration-m12-dq15).
- **Where generated artifacts live / regeneration.** Generated output is derived
  code: gitignored by default, written to `./.parallax/generated` (outside
  `src/`, so it does not look like user-owned source), and regenerated during
  install, build, and CI. Generated files are inspectable but not editable —
  customization belongs in descriptors, generator configuration, runtime adapters,
  and application-owned domain functions. Applications import the output through
  the package-local `#parallax` alias.

## 8. Collection idioms (M5)

**ANSWERED — specified in full below.**

- **Concrete collection type.** A list result is a `ParallaxList<T>`: an async,
  operation-backed result collection. It implements async iteration and resolves
  its backing operation (`M5`) on first object-returning access — laziness and
  query-backing are surfaced by deferring the fetch until results are read.
- **Read helpers.** `toArray`, `toSnapshots`, `first`, `firstOrNull`, `single`,
  `singleOrNull`, `count`, `isEmpty`, `notEmpty`. `count` / `isEmpty` /
  `notEmpty` may answer with optimized SQL while unresolved without marking the
  list resolved; once resolved, they answer from the materialized in-memory
  result. Object-returning helpers resolve the list: `first` throws
  `ParallaxNotFoundError` when empty; `single` throws `ParallaxNotFoundError` when
  empty and `ParallaxTooManyResultsError` when more than one object exists; the
  `OrNull` variants return `null` for empty lists and still throw
  `ParallaxTooManyResultsError` for multiple results.
- **No array emulation.** `ParallaxList` does **not** trap `length`, numeric
  indexing, or synchronous iteration — normal JavaScript behavior is acceptable
  for those. Set-based `update` / `delete` accept an unresolved `ParallaxList` as
  a bulk target ([§4](#4-transaction-block-demarcation-m8)).

## 9. Build-time dependency enforcement (DQ3, dependency-graph)

**ANSWERED — see [TS-0061](../docs/adr/0061-module-dag-enforced-by-dependency-cruiser-with-m0-m14-package-map.md).**
The normative module-dependency graph
([`dependency-graph.md`](../../../core/spec/dependency-graph.md)) is the **only**
legal dependency direction between numbered core modules, and each per-language
spec **SHOULD** prescribe a build-time mechanism that fails the build on any
module-to-module dependency the graph does not declare. This section names the
tool, maps every core module `M0`–`M14` onto a TypeScript package under
`languages/typescript/packages/*`, records the non-numbered support packages
`@parallax/serde` and `@parallax/typescript`, and transcribes the legal
numbered-module edges one-to-one from the core graph so the TypeScript edge set
is mechanically diff-able against it. The non-numbered package edges are explicit
package-topology edges, not additions to the core module DAG.

### 9.1 Enforcement tool

The tool is **dependency-cruiser** (TS-0061), run as a standalone
`depcruise --validate` build step decoupled from ESLint. Its `forbidden` /
`allowed` from/to contract encodes the DAG edges directly: the legal edges become
an `allowed` allowlist of `{ from, to }` package selectors, and any
module-to-module dependency not on the allowlist is reported as `not-in-allowed`
and fails the build — the TypeScript analogue of the reference harness's
`dep_graph_check.py` three-colour DFS, where a wrong-direction edge surfaces as a
violation. `eslint-plugin-boundaries` was the considered alternative but ties the
check to the ESLint run and its element taxonomy; dependency-cruiser keeps the DAG
check a first-class, independent step.

Config sketch (`.dependency-cruiser.js`):

```js
module.exports = {
  forbidden: [
    {
      name: "no-undeclared-module-dependency",
      comment: "Only documented numbered-module, support, and composition edges are legal.",
      severity: "error",
      from: { path: "^languages/typescript/packages/([^/]+)/" },
      to: {
        path: "^languages/typescript/packages/([^/]+)/",
        // a cross-package import is forbidden unless it matches an allowed edge
        pathNot: "^languages/typescript/packages/$1/",
        moreThanOneDependencyType: false,
      },
    },
  ],
  // The legal edges are the allowlist; see the mapping table and edge block below.
  allowed: [
    // Non-numbered support package edges.
    { from: { path: "^languages/typescript/packages/metamodel/" },     to: { path: "^languages/typescript/packages/serde/" } },
    { from: { path: "^languages/typescript/packages/operation/" },     to: { path: "^languages/typescript/packages/serde/" } },

    // Non-numbered composition package edges. Numbered packages MUST NOT import
    // from @parallax/typescript; it is the CLI/generator/application facade.
    { from: { path: "^languages/typescript/packages/typescript/" },    to: { path: "^languages/typescript/packages/(core|metamodel|operation|sql|relationships|lists|bitemporal|transactions|lifecycle|locking|dialect|conformance|benchmark|coherence|serde)/" } },

    // Numbered module edges from core/spec/dependency-graph.md.
    { from: { path: "^languages/typescript/packages/metamodel/" },     to: { path: "^languages/typescript/packages/core/" } },
    { from: { path: "^languages/typescript/packages/dialect/" },        to: { path: "^languages/typescript/packages/core/" } },
    { from: { path: "^languages/typescript/packages/operation/" },      to: { path: "^languages/typescript/packages/metamodel/" } },
    { from: { path: "^languages/typescript/packages/sql/" },            to: { path: "^languages/typescript/packages/operation/" } },
    { from: { path: "^languages/typescript/packages/sql/" },            to: { path: "^languages/typescript/packages/dialect/" } },
    { from: { path: "^languages/typescript/packages/transactions/" },   to: { path: "^languages/typescript/packages/operation/" } },
    { from: { path: "^languages/typescript/packages/transactions/" },   to: { path: "^languages/typescript/packages/dialect/" } },
    { from: { path: "^languages/typescript/packages/lists/" },          to: { path: "^languages/typescript/packages/operation/" } },
    { from: { path: "^languages/typescript/packages/lists/" },          to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/relationships/" },  to: { path: "^languages/typescript/packages/lists/" } },
    { from: { path: "^languages/typescript/packages/relationships/" },  to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/relationships/" },  to: { path: "^languages/typescript/packages/bitemporal/" } },
    { from: { path: "^languages/typescript/packages/bitemporal/" },     to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/lifecycle/" },      to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/locking/" },        to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/coherence/" },      to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/operation/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/sql/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/relationships/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/bitemporal/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/transactions/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/lifecycle/" } },
    { from: { path: "^languages/typescript/packages/conformance/" },    to: { path: "^languages/typescript/packages/locking/" } },
    { from: { path: "^languages/typescript/packages/benchmark/" },      to: { path: "^languages/typescript/packages/conformance/" } },
  ],
  allowedSeverity: "error",
};
```

### 9.2 Module → package mapping

Each core module maps to one **pnpm-workspace package** under
`languages/typescript/packages/`, named for its responsibility and tagged with
its core `M`-number (TS-0061). Real workspace packages — rather than path-ruled
directories — make the workspace graph itself participate in the layering: a
package's `package.json` lists only the sibling packages it is permitted to
depend on, and dependency-cruiser is the mechanical gate over the `import` graph.
The `languages/typescript/` directory is the TypeScript language workspace root:
`languages/typescript/spec/` and `languages/typescript/docs/` are documentation,
while `languages/typescript/packages/*` contains implementation source.

| Core module | Responsibility | TS package | Tag |
|---|---|---|---|
| M0 | Core conventions (types · infinity · tz) | `@parallax/core` | M0 |
| M1 | Domain model & metamodel | `@parallax/metamodel` | M1 |
| M2 | Query/operation/aggregation algebra | `@parallax/operation` | M2 |
| M3 | SQL generation contract | `@parallax/sql` | M3 |
| M4 | Relationships & deep fetch | `@parallax/relationships` | M4 |
| M5 | Lists & bulk/set operations | `@parallax/lists` | M5 |
| M7 | Bitemporal / milestoning | `@parallax/bitemporal` | M7 |
| M8 | Transactions, UoW & identity/query cache | `@parallax/transactions` | M8 |
| M9 | Object lifecycle & detach | `@parallax/lifecycle` | M9 |
| M10 | Optimistic locking | `@parallax/locking` | M10 |
| M11 (portability) | Pure dialect / portability layer (SQL strings + type-parse fns; no I/O) | `@parallax/dialect` | M11 |
| M11 (port) | Abstract runtime database port (`execute`/`transaction`; normalize-at-boundary) | `@parallax/db` | M11 |
| M11 (adapter) | Concrete Postgres adapter over the `postgres` driver (one per DB type) | `@parallax/db-postgres` | M11 |
| M12 | Compatibility harness | `@parallax/conformance` | M12 |
| M13 | Performance & benchmark harness | `@parallax/benchmark` | M13 |
| M14 | Cross-process cache coherence | `@parallax/coherence` | M14 |
| Support | Canonical metamodel/operation serde | `@parallax/serde` | unnumbered |
| Facade | CLI, generator config, public runtime facade, generated-barrel support | `@parallax/typescript` | unnumbered |

**`M6` is deliberately absent** — aggregation is folded into `M2`, and the gap is
preserved to keep cross-references to the core numbering stable. The shared
`@parallax/serde` package (the canonical serde seam of
[§3.3](#33-serde-module)) is a public pnpm-workspace support package, not a
numbered core module and not part of the generated `#parallax` application
barrel. It has no sibling-package dependencies. The only legal direct imports to
it are `@parallax/metamodel -> @parallax/serde` and `@parallax/operation ->
@parallax/serde`, which the dependency-cruiser allowlist above encodes
explicitly.

The `@parallax/typescript` package is a non-numbered **composition package** at
`languages/typescript/packages/typescript`. It owns the `parallax` CLI,
`parallax-conformance` CLI entry point, generator configuration API
(`@parallax/typescript/config`), public runtime facade, and generated-barrel
support. It MAY depend on any numbered TypeScript package and on
`@parallax/serde`, because it is the composition root. No numbered package or
support package may depend on `@parallax/typescript`; implementation modules stay
below the facade.

**`M11` maps to more than one package** (per the core
[`language-spec-template.md`](../../../core/spec/language-spec-template.md) §9 rule
and [`m11-dialect-seam.md`](../../../core/spec/m11-dialect-seam.md) →
*M11 decomposition*): the database seam is normatively decomposed into a **pure
dialect / portability** module (`@parallax/dialect` — SQL strings + type-parse
functions to managed values; no I/O, no driver), an **abstract runtime database
port** (`@parallax/db` — the `execute(sql, binds)` / `transaction(body)` contract
plus the normalize-at-boundary rule so an adapter returns managed scalars), and
**N concrete adapters** (`@parallax/db-postgres`, and a future
`@parallax/db-mysql`), one per database type, each depending **only** on the port
and the pure dialect layer. All three share the single `M11 --> M0` numbered edge
— the decomposition is a rule *within* the module, not new DAG nodes, so
[`dependency-graph.md`](../../../core/spec/dependency-graph.md) is unchanged and
`@parallax/db` / `@parallax/db-postgres` are **language-impl support edges** (like
the `@parallax/serde` edges), documented in §9.3 but absent from the numbered-edge
block. `@parallax/db` is a leaf (it reaches only `@parallax/core`), and
`@parallax/db-postgres` carries the `postgres` driver + porsager OID registration
but **no** wire/grading logic (*managed at the boundary, wire at the grader*). The
two structural rules the core spec mandates hold: **only the composition root
(`@parallax/typescript`) may depend on a concrete adapter** (`@parallax/db-postgres`
appears nowhere in the numbered packages), and **the port depends on nothing
application-specific**. The composition-root conformance provider retains
provisioning (Testcontainers + `reset`/`applyDdl`/`loadFixtures`) but delegates
SQL execution to a `@parallax/db-postgres` instance, then renders its managed
scalars to the canonical wire form for the run envelope — so there is **no
`M12 → M11` edge** and the 116-case slice is continuous proof the shipped adapter
works.

### 9.3 Legal-edge contract

The numbered-module legal edges are transcribed **one-to-one** from
[`dependency-graph.md`](../../../core/spec/dependency-graph.md), keyed by the same
`M`-numbers so the edge set is mechanically diff-able against core. Each edge
`A --> B` reads "A depends on B"; the reverse is a spec violation. Combined with
the mapping table, the two explicit `@parallax/serde` support-package edges, the
two **M11 port/adapter support edges** below, and the top-level
`@parallax/typescript` composition edge above, this block is the source the
`.dependency-cruiser.js` allowlist encodes.

Beyond the numbered edges, the M11 decomposition (§9.2) contributes two
**support edges** that are *not* new numbered-DAG edges (the whole seam shares the
one `M11 --> M0` edge above) but are enforced by the allowlist:

- `@parallax/db-postgres --> @parallax/db` — a concrete adapter depends on the
  abstract port.
- `@parallax/db-postgres --> @parallax/dialect` — the adapter delegates every
  parse decision to the pure dialect layer (the single source of parse logic), so
  parse rules are never duplicated across adapters.

`@parallax/db` (the port) depends only on `@parallax/core` (the universal leaf
allowance), and `@parallax/db` + `@parallax/db-postgres` are added to the
composition-root `@parallax/typescript --> (…)` `to` set — the composition root is
the only layer permitted to depend on the concrete adapter. No numbered package
depends on `@parallax/db-postgres`, and no above-seam module reaches a driver.

```dependency-graph
M1 --> M0
M11 --> M0
M2 --> M1
M3 --> M2
M3 --> M11
M8 --> M2
M8 --> M11
M5 --> M2
M5 --> M8
M4 --> M5
M4 --> M8
M4 --> M7
M7 --> M8
M9 --> M8
M10 --> M8
M12 --> M2
M12 --> M3
M12 --> M4
M12 --> M7
M12 --> M8
M12 --> M9
M12 --> M10
M12 --> M11
M13 --> M12
M14 --> M8
```

The non-obvious directions carry over verbatim from the core graph: `M8` depends
on `M2` not `M3` (the transaction / unit-of-work layer is expressed over
operations, not SQL); `M4` depends on `M5` (relationship navigation yields lists,
the reverse of the obvious guess); `M4` depends on `M7` (a pinned as-of value
propagates per relationship hop, so the relationship layer references the as-of
model — the edge the claimed temporal deep-fetch 03xx cases require); and `M3`
depends on `M11` (SQL generation routes through the portability seam). `M12`
additionally depends on `M8` directly — the harness realizes M8 unit-of-work
behavior itself (batched write-sequence flushes, read-your-own-writes scenarios),
a direct edge that coexists with the transitive `M12 → M10 → M8` path, mirroring
how `M4 → M8` coexists with `M4 → M5 → M8` — and on `M11` directly, since the
harness applies the dialect's DDL / quoting / read-lock-application rules to
assemble SQL (`applyReadLock`). M14's
single legal direction `M14 → M8` is
transcribed in the block above, keeping the TypeScript edge set one-to-one with
the core graph; the `@parallax/coherence` package is a **fast-follow** capability
that TypeScript V1 MAY defer implementing, but its boundary is documented here so
the dependency-cruiser allowlist stays complete and mechanically diff-able against
the core graph.

## 10. Optional optimized data structures (M13, DQ10)

**DEFERRED-with-rationale — non-normative, no V1 decision; see
[TS-0063](../docs/adr/0063-optimized-data-structures-non-normative-no-v1-decision.md).**
This section is **non-normative**: the optional optimized data structures exist
only to back the `M8` identity / query caches, and that cache/identity slice of
M8 is deferred from TypeScript V1 (TS-0054,
[§4](#4-transaction-block-demarcation-m8)). The transaction/read-lock/write
slice specified in §4 still belongs to V1. There is nothing cache-specific to
optimize for V1, so no V1 decision is recorded. The core itself marks these
techniques optional and non-normative — a language may hit its targets any way it
likes.

The two optional techniques the template lists are recorded here so the deferral
is deliberate rather than an omission:

- **Open-addressing map/set analogues** (`UnifiedMap` / `UnifiedSet`) for the
  identity / query caches — lower per-entry overhead than chained hash tables.
- **Key-derived hashing analogue** (`HashingStrategy`) — index domain objects by
  a derived (e.g. composite-PK) key without allocating wrapper key objects.

**Post-V1 note (non-binding):** when the M8 identity/query-cache slice lands, a
built-in `Map` keyed by a canonical primary-key string is the idiomatic
JavaScript baseline for both caches. The Java open-addressing /
no-wrapper-key-allocation techniques have **no compelling direct JavaScript
analogue** — short string keys are effectively interned by the engine and V8
`Map`s are already compact, so a composite-PK string key captures the same
benefit without a custom hashing strategy or an open-addressing table. This
decision is deferred with the cache/identity slice and made when that slice is
implemented.

## 11. Per-language performance targets (M13, DQ10)

**DEFERRED-with-rationale (M13 command and numeric targets) + the
`expectRoundTrips` invariant is binding for V1 compatibility cases — see
[TS-0062](../docs/adr/0062-performance-methodology-bound-numeric-targets-deferred.md).**
TypeScript records the shared `M13` methodology now, but the canonical
`slice-mvp-1` conformance slice does **not** claim module `m13` or
the `benchmark` command. A V1 adapter adopting that slice may therefore return
`unsupported` for `parallax-conformance benchmark`. The benchmark command and
numeric targets are enabled by a later M13 slice, after a real implementation can
produce a baseline. Numbers invented against a non-existent implementation would
be fabricated rather than measured.

### 11.1 Post-slice benchmark methodology

The methodology is the durable, comparable part of `M13`. When TypeScript claims
the M13 benchmark slice, it uses this contract:

- **Shared fixtures.** The same benchmark fixtures under
  [`core/compatibility/benchmarks/`](../../../core/compatibility/benchmarks)
  (`read-mix.yaml`, `deep-fetch.yaml`, `milestone-write.yaml`), run against the
  same deterministically generated datasets at the same scale, so a TypeScript
  number is directly comparable to the reference figures and to past runs.
- **Nearest-rank percentile.** `wallTimeMs.p50` / `wallTimeMs.p95` are computed
  with the nearest-rank percentile, matching the Python harness.
- **`report.json` schema.** The emitted report uses the schema fixed in
  [`m13-performance.md`](../../../core/spec/m13-performance.md): `generatedAt`,
  `dialect`, `benchmarks[].{ fixture, model, datasetRows, workloads[] }` (each
  workload carrying `name`, `iterations`, `wallTimeMs.{ p50, p95 }`, `roundTrips`,
  and the optional `expectRoundTrips` / `roundTripsOk`), and
  `memory.{ peakBytes, steadyBytes }`.
- **Execution hook.** Once the M13 benchmark command is claimed, benchmarks run
  through the
  `parallax-conformance benchmark --benchmark <b.yaml> --dialect <d>` command of
  the [conformance adapter
  contract](../../../core/spec/conformance-adapter-contract.md), against the
  Postgres provider seam of [§5](#5-test-double-integration-m12-dq15). The
  command writes the standard adapter envelope to stdout with the M13 report under
  `report`; for a single benchmark fixture invocation, `report.benchmarks`
  contains one entry for the requested fixture. Writing the same object to
  `report.json` is allowed as a CI artifact, but stdout is the conformance
  contract. This command is outside the canonical V1 command claim.

### 11.2 Deferred (numeric targets)

The **absolute numeric ceilings are deferred placeholders** pending a first
baseline run, with this tracking note:

- **Wall-time targets** (`p50` / `p95`) per benchmark workload family — **deferred
  (TODO: set from baseline).**
- **Memory targets** (peak / steady resident set) — **deferred (TODO: set from
  baseline).**

**Tracking note.** Once the first TypeScript implementation claims M13, runs the
benchmark suite, and records a baseline, this section is updated with grading
targets derived from that baseline. Until then there are no numeric ceilings to
grade against and no V1 conformance requirement to run the benchmark suite
end-to-end; an implementation that does claim the benchmark command must emit a
well-formed `report.json`.

### 11.3 Binding invariant — `expectRoundTrips` (non-placeholder)

The compatibility `expectRoundTrips` invariant is **carved out of the deferral and
is a hard, non-placeholder requirement** for V1 claimed cases: **a deep fetch
costs `1 + levels` round trips regardless of fan-out, never N+1.** The TypeScript
implementation **MUST** honor it for claimed compatibility cases. It is enforced
in V1 through M12 and, once M13 is claimed, by the benchmark runner too:

- **`M12` round-trip-count layer** — for every compatibility case,
  `len(goldenSql[dialect])` MUST equal the case's `roundTrips`
  ([§5.2](#52-case-discovery-and-execution-boundary) compares this via the
  `parallax-conformance` envelope's `roundTrips`).
- **Post-slice `M13` benchmark runner** — when the benchmark command is claimed,
  a workload's actual round trips MUST equal its declared `expectRoundTrips`; a
  deep fetch that silently regresses to N+1 fails the benchmark run.

This invariant is binding even though the wall-time and memory numbers are not.

## Object lifecycle: detach, snapshots, and entity inputs (M9)

This section is supplementary to the template's §1–§11 (the template has no
object-lifecycle slot). It records the TypeScript surface for getting data **out
of** and **back into** managed objects — the TypeScript analogue of Reladomo's
detach / merge-back lifecycle (`M9`, the `@parallax/lifecycle` package of
[§9.2](#92-module--package-mapping)). The decisions are recorded in
[TS-0036](../docs/adr/0036-snapshots-are-the-typescript-detached-data-surface.md)
and
[TS-0037](../docs/adr/0037-generated-entity-inputs-provide-validation-helpers.md).

**Snapshots are the detached-data surface.** TypeScript does not expose
Reladomo-style detached *managed objects* in V1; the plain, JSON-serializable
**snapshot** is the idiomatic detached representation (for REST, UI editing,
messaging, and later merge workflows). `OrderSnapshot` is what Parallax **emits**
from a managed object:

```ts
const snapshot = await order.toSnapshot({
  attributes: [Order.id, Order.status],
  relationships: [Order.customer, Order.lineItems],
});

const snapshots = await orders.toSnapshots({
  relationships: [Order.lineItems.product],
});
```

Snapshot output includes all scalar and value-object attributes by default and no
relationships by default; `attributes` and `excludeAttributes` are mutually
exclusive, relationship paths are opt-in (there is no `excludeRelationships`,
since omitted relationships are already excluded), and value-object attributes
are selected as whole `ParallaxJsonValue` properties rather than typed nested
field paths. List-level snapshots batch-load requested relationships like
includes
([§2.6](#26-relationship-navigation-and-deep-fetch-m4)) to avoid N+1.
(`JSON.stringify` over a managed object is scalar-only and synchronous and does
not lazy-load relationships, so use a snapshot when relationship data is needed.)

**Entity inputs are the create / reattach surface.** `OrderInput` is the
generated input-validation namespace and type for data accepted by `create`
([§4](#4-transaction-block-demarcation-m8)) — the surface for turning
external/detached data back into a managed object:

```ts
const input = OrderInput.parse(req.body);

const result = OrderInput.safeParse(req.body);
if (!result.ok) {
  return response.status(400).json(result.error);
}

await px.transaction(async tx => {
  await tx.orders.create(input);
});
```

`parse` returns a typed entity input or throws `ParallaxValidationError`;
`safeParse` returns `{ ok: true; value } | { ok: false; error }`. Entity inputs
are **distinct from snapshots**: `OrderInput` is what Parallax *accepts* to
construct a new managed object, `OrderSnapshot` is what it *emits*. `OrderInput`
includes only create-accepted data (writable scalar attributes, writable value
objects, app-assigned primary keys when configured, foreign-key attributes
exposed as writable, and nested dependent relationships only when explicitly
allowed) and excludes database-generated IDs, read-only attributes,
optimistic-lock/version fields, processing timestamps, and server-owned fields.
Create consumes nested relationship data only when listed in `relationships`;
data listed in `ignoreRelationships` is accepted but ignored; any remaining
nested relationship data is rejected. These helpers validate plain payloads —
they do **not** create managed objects, parse detached entities, parse snapshots,
or replace `tx.entity.create(...)` (TS-0037).

**Deferred from V1.** The full Reladomo-style detached-object lifecycle — the
`M9` state machine (`persisted` → `detached` → `detached-deleted`) and merge-back
(`getDetachedCopy` / `copyDetachedValuesToOriginalOrInsertIfNew`) — is **deferred
from TypeScript V1**. When `M9` merge-back lands it should be expressed through
explicit snapshot apply / merge APIs that preserve the core observable semantics
(TS-0036), not by introducing detached managed objects.

## Template Coverage Appendix

This table maps every `language-spec-template.md` section §1–§11 to its answer
location in this document and an explicit status. Every section is specified
inline here and is now resolved — `ANSWERED` or `DEFERRED-with-rationale` — with
no decide-and-record debt remaining. The spec also carries a supplementary
[Object lifecycle](#object-lifecycle-detach-snapshots-and-entity-inputs-m9)
section (`M9`) beyond the template skeleton; it is not a template row.

| Template section | Status | Answer location | ADRs |
|---|---|---|---|
| §1 Conformance Slice declaration | ANSWERED | [§1](#1-conformance-slice-declaration) | [TS-0064](../docs/adr/0064-adopt-first-implementation-mvp-slice.md) |
| §2 API surface | ANSWERED | [§2](#2-api-surface-non-normative--dq3) | — |
| §3 Metadata / introspection + serde | ANSWERED | [§3](#3-metadata--model-input-format-dq5-dq6) | [TS-0055](../docs/adr/0055-metamodel-introspection-api-has-generic-and-typed-layers.md), [TS-0056](../docs/adr/0056-one-canonical-serde-shared-by-metamodel-and-operations.md), [TS-0057](../docs/adr/0057-serde-states-roundtrip-contract-and-names-libraries-nonbindingly.md) |
| §4 Transaction-block demarcation | ANSWERED | [§4](#4-transaction-block-demarcation-m8) | — |
| §5 Test-double integration | ANSWERED | [§5](#5-test-double-integration-m12-dq15) | [TS-0058](../docs/adr/0058-compatibility-suite-uses-vitest.md), [TS-0059](../docs/adr/0059-cases-discovered-by-glob-executed-through-conformance-adapter.md), [TS-0060](../docs/adr/0060-typescript-runs-postgres-only-in-ci-pinned-to-postgres-17.md) |
| §6 API Conformance Suite & Usage Guide | ANSWERED | [§6](#6-api-conformance-suite--usage-guide) | — |
| §7 Codegen-or-not | ANSWERED | [§7](#7-codegen-or-not-dq5) | — |
| §8 Collection idioms | ANSWERED | [§8](#8-collection-idioms-m5) | — |
| §9 Build-time dependency enforcement | ANSWERED | [§9](#9-build-time-dependency-enforcement-dq3-dependency-graph) | [TS-0061](../docs/adr/0061-module-dag-enforced-by-dependency-cruiser-with-m0-m14-package-map.md) |
| §10 Optional optimized data structures | DEFERRED-with-rationale | [§10](#10-optional-optimized-data-structures-m13-dq10) | [TS-0063](../docs/adr/0063-optimized-data-structures-non-normative-no-v1-decision.md) |
| §11 Per-language performance targets | DEFERRED-with-rationale | [§11](#11-per-language-performance-targets-m13-dq10) | [TS-0062](../docs/adr/0062-performance-methodology-bound-numeric-targets-deferred.md) |

### Completion check

This document satisfies the `language-spec-template.md` completion check:

- **No remaining markers.** Every template section §1–§11 is resolved; no
  *decide-and-record* placeholder remains. Nine sections are `ANSWERED`;
  [§10](#10-optional-optimized-data-structures-m13-dq10) and
  [§11](#11-per-language-performance-targets-m13-dq10) are `DEFERRED-with-rationale`
  (deliberate, ADR-backed decisions, not omissions), and the §11 `expectRoundTrips`
  invariant stays binding.
- **No contradiction with core.** The
  [§9](#9-build-time-dependency-enforcement-dq3-dependency-graph) legal-edge block
  is transcribed one-to-one from
  [`dependency-graph.md`](../../../core/spec/dependency-graph.md) and keyed by the
  same `M`-numbers, while the `@parallax/serde` and `@parallax/typescript` edges
  are explicit TypeScript package-topology edges outside the core graph; the
  [§1](#1-conformance-slice-declaration) capability claim is byte-equal to the
  canonical `slice-mvp-1` claim in
  [`scope-and-tiers.md`](../../../core/spec/scope-and-tiers.md); the
  [§3](#3-metadata--model-input-format-dq5-dq6) metadata shapes are drawn
  one-to-one from
  [`metamodel.schema.json`](../../../core/schemas/metamodel.schema.json)'s eight
  element types; [§5](#5-test-double-integration-m12-dq15) pins the same
  `postgres:17` image the reference harness pins; and
  [§11](#11-per-language-performance-targets-m13-dq10) binds the same `M13`
  methodology, fixtures, and `report.json` schema.
- **Self-sufficient for a fresh implementer.** This document specifies every
  template section §1–§11 inline; together with the cited ADRs it is sufficient to
  author a TypeScript implementation and run the compatibility suite to green
  **without re-reading the core spec or any other Parallax document**.
