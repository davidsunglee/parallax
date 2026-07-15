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
  [§4](#4-transaction-block-demarcation-m-unit-work) transaction-block demarcation,
  [§7](#7-codegen-or-not-dq5) codegen, and [§8](#8-collection-idioms-m-op-list)
  collection idioms record the V1 API surface inline.
- [§3](#3-metadata--model-input-format-dq5-dq6) metamodel introspection + serde,
  [§5](#5-test-double-integration-m-case-format-dq15) test-double integration,
  [§6](#6-api-conformance-suite--usage-guide) the API Conformance Suite & Usage
  Guide, [§9](#9-build-time-dependency-enforcement-dq3-dependency-graph)
  build-time dependency enforcement,
  [§10](#10-optional-optimized-data-structures-m-perf-bench-dq10) optional optimized data
  structures, and
  [§11](#11-per-language-performance-targets-m-perf-bench-dq10) per-language performance
  targets close the remaining decide-and-record items.

Beyond the template skeleton, the spec also includes a supplementary
[Object lifecycle: detach, snapshots, and entity inputs](#object-lifecycle-detach-snapshots-and-entity-inputs-m-detach)
section (`m-detach`).

The document is self-contained: no section defers its answer to another document.
Links to `core/` files point at the authoritative source of truth, but the
substance each one fixes (the metamodel schema's element types, the legal-edge
DAG, the benchmark report schema) is transcribed inline, so the spec is readable
end-to-end on its own.

The [Template Coverage Appendix](#template-coverage-appendix) at the end maps
every template section to its answer location and an explicit status, so any
future gap surfaces as an explicit marker rather than silent prose.

## 1. Conformance Slice declaration

**ANSWERED — see [core ADR 0018](../../../docs/adr/0018-slice-tags-follow-the-slice-naming-convention.md).**
The Conformance Slice this build claims leads the spec because it scopes every
other section — the module → package map, the case/dialect matrix
([§5](#5-test-double-integration-m-case-format-dq15)), the conformance-adapter grade, and
the API Conformance Suite ([§6](#6-api-conformance-suite--usage-guide)) are all
bounded by it. A Conformance Slice is a declared, **case-granular** subset of the
compatibility corpus; its machine-readable form is a `describeOk` capability
claim and its name is its `caseTags.include` tag.

### 1.1 V1 conformance capability claims

TypeScript V1 **is** the canonical `slice-mvp-1` Conformance Slice
declared in [`slices.md`](../../../core/spec/slices.md#first-implementation-conformance-slice)
([core ADR 0018](../../../docs/adr/0018-slice-tags-follow-the-slice-naming-convention.md)). The V1
conformance adapter MUST report a case-slice-aware `describe`
result whose `capabilities` are **exactly** that canonical slice's capabilities —
the slice is **include-driven** (`caseTags.include: ["slice-mvp-1"]`),
so V1 claims every case selected by the canonical claim and returns
`unsupported` for everything else. A V1 adapter that implements the specified
transaction, relationship, list, temporal (bitemporal **reads and writes** +
audit-only processing-temporal), optimistic-locking, and value-object (typed nested
predicates, atomic document writes, inherited-temporality reads, materialization
graph, and the pre-SQL `rejected` negatives) surfaces but defers aggregation,
identity-cache scenarios, query-cache scenarios, m-detach detached merge-back, PK
generation, inheritance, error classification, the bitemporal rectangle-split
*value-object* write, m-perf-bench benchmarks, and non-Postgres dialects claims
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
      "m-api-conformance",
      "m-audit-write",
      "m-auto-retry",
      "m-batch-write",
      "m-bitemp-write",
      "m-case-format",
      "m-conformance-adapter",
      "m-core",
      "m-db-error",
      "m-deep-fetch",
      "m-descriptor",
      "m-dialect",
      "m-navigate",
      "m-op-algebra",
      "m-op-list",
      "m-opt-lock",
      "m-pk-gen",
      "m-read-lock",
      "m-sql",
      "m-temporal-read",
      "m-unit-work",
      "m-value-object"
    ],
    "dialects": ["postgres"],
    "caseShapes": ["read", "writeSequence", "scenario", "conflict", "boundary", "error", "concurrencySuccess", "rejected"],
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
  therefore outside the claim even though basic m-op-algebra predicate reads are inside it.
- The transaction, read-lock, and batched-write case subset is inside §4, but the
  m-read-lock identity-cache and query-cache scenario capability set is deferred
  by TS-0027. Those
  cache/identity cases are untagged and outside the V1 claim.
- The `scenario` shape is **inside** the claim: the read-your-own-writes scenario
  `m-unit-work-001-read-your-own-writes` is tagged `slice-mvp-1` and runs as
  part of the m-unit-work unit-of-work case subset. The deferred m-unit-work cache `scenario` cases
  (identity / query cache) are simply untagged, so they fall outside the claim
  without excluding the shape.
- m-detach detached merge-back is deferred by the lifecycle section, so the `detached` /
  `lifecycle detach` cases are untagged and outside the V1 claim unless a later
  implementation adopts a canonical claim that includes them.
- m-perf-bench benchmarks are **outside** the V1 claim: `m-perf-bench` is not in `modules` and the
  `benchmark` command is not in `commands` (TS-0032, core ADR 0018). TypeScript still
  binds to the shared m-perf-bench methodology and report shape (§11), but the first build
  does not *claim* benchmark execution in its Conformance Slice — the benchmark
  surface lands after the current claim.
- MariaDB cases remain outside the V1 **conformance adapter claim** because
  `dialects` contains only `postgres`. Separately, TypeScript ships MariaDB as
  the second concrete m-db-port dialect/adapter/provider and proves it through
  first-class partial m-case-format and selectable API-conformance profiles described in
  [§5](#5-test-double-integration-m-case-format-dq15) and [§6](#6-api-conformance-suite--usage-guide).

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

No generated enum types are part of TypeScript V1 (the canonical descriptor has
no enum element). Value objects, by contrast, **are** structured in V1: a
`valueObject` declares typed inner `attributes`, self-nested `valueObjects` to
arbitrary depth, and `cardinality: one | many` (m-value-object), all stored in
its one structured-document column. Codegen therefore emits a typed value-object
class per declared member and parent-to-nested **getters to arbitrary depth**
(no reverse getters, no lock/cache/statement machinery — [§7](#7-codegen-or-not-dq5)),
and the query DSL exposes a typed nested-predicate builder whose comparisons,
`in`, null tests, and `exists`/`notExists` (with a scoped element `where`) carry
the declared `Class.vo.field` path (m-op-algebra `nested*` family). The whole
document still materializes with its owner in one round trip and binds atomically
on write; a value object is never a queryable root, a navigation target, or a
`deepFetch` segment — those misuses are the pre-SQL `rejected` negatives.

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
([§8](#8-collection-idioms-m-op-list)), which may resolve to zero, one,
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
(`m-op-list`, [§8](#8-collection-idioms-m-op-list)). Single-object access is spelled through
`ParallaxList` helpers (`first` / `firstOrNull` / `single` / `singleOrNull`):
`first`/`single` throw `ParallaxNotFoundError` when empty and `single` throws
`ParallaxTooManyResultsError` for more than one result. Full collection idioms
are in [§8](#8-collection-idioms-m-op-list).

### 2.5 Predicates and the `group` operator (`m-op-algebra`)

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

### 2.6 Relationship navigation and deep-fetch (`m-deep-fetch`)

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

### 2.8 Aggregation spelling (`m-agg` sub-area) — deferred

`find` never returns partial managed objects. Selective retrieval and grouped
aggregate reads are reserved for `project(...)` (`where` / `groupBy` / `select` /
`having` / `orderBy`), which returns plain data rather than managed objects.
**Projection and aggregation are deferred from V1** (recorded so the surface
choice is not re-opened). In-memory reuse of predicates as `Array.filter`
callbacks and of sort keys as `Array.sort` comparators is likewise deferred.

### 2.9 Temporal reads (`m-temporal-read`)

TypeScript timestamps use `Temporal.Instant` and are constrained to the core m-core
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
m-op-algebra and the rows that resolve when the list is read.

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

The TypeScript adapter serializes explicit temporal reads to the core m-op-algebra nodes:

- `asOf.processing` / `asOf.business` → `asOf`
- `range.processing` / `range.business` → `asOfRange`
- `history: ["processing" | "business"]` → `history`

When both axes are present, serialization is deterministic: the business-axis
wrapper is outside the processing-axis wrapper, matching the core bind order
(business binds before processing binds). Omitted temporal axes are not
serialized; the m-temporal-read default-injection rule still applies and reads them as
current (`now`).

### 2.10 Inheritance and subtype narrowing (illustrative — deferred from V1)

**Non-normative and deferred.** Inheritance is **not** part of the TypeScript V1
`slice-mvp-1` claim (§1.1 lists it among the deferred surfaces), and nothing in
this subsection changes that claim or adds a V1 obligation. The two
object-lifecycle slices (`slice-snapshot-1` / `slice-managed-1`) do claim
`m-inheritance`, so the sketches below record the idiomatic shape a later
TypeScript build would grow to satisfy them. The **only** normative inheritance
commitment today is the `InheritanceMeta` reader shape in §3.2; the code below
fixes no wire contract — the binding surfaces stay the core corpus and the
conformance-adapter observations (`familyVariant`, narrowed graph view keys).

An inheritance family is a closed tree with an abstract `root`, optional
`abstract-subtype`s, and instantiable `concrete-subtype`s (§3.2). Codegen would
emit a symbol per participant, so a `find` over an abstract position returns a
**discriminated union** of the concrete managed-object types, and the illustrative
combinators below serialize to the core `narrow` operation node and read back the
core `familyVariant`.

**Abstract-target read and subtype narrowing.** A `find` over an abstract entity
addresses the whole family; a `narrow(...)` combinator restricts a polymorphic
position to an effective concrete set, authored with abstract-subtype and/or
concrete-subtype symbols. Narrowing may only stay within (or below) the position's
effective set — broadening is a validation error, mirroring the core narrow rule.

```ts
// Whole family — each object is one concrete variant.
const animals = px.animals.find(Animal.name.startsWith("R"));

// Narrow to an abstract subtype's descendants (Pet → Cat, Dog):
const pets = px.animals.find(Animal.all().narrow(Pet));

// Narrow to an explicit concrete set, with a concrete-subtype predicate in scope:
const loudDogs = px.animals.find(
  Animal.all().narrow(Dog).where(Dog.barkVolume.gt(5)),
);
```

**Polymorphic navigation.** A relationship whose target is an abstract position
navigates polymorphically; a `narrow(...)` inside the quantifier restricts the
traversed set and must name a subset of the relationship target's effective set.

```ts
const dogOwners = px.people.find(
  Person.pets.narrow(Dog).exists(dog => dog.barkVolume.gt(5)),
);
```

**Narrowed includes.** A narrowed hop in `includes` eager-fetches only the
requested concrete set and populates a distinct narrowed view; equivalent authored
narrowings (`narrow(Pet)` vs `narrow(Cat, Dog)`) resolve to the same view.

```ts
const people = px.people.find(Person.all(), {
  includes: [Person.pets.narrow(Dog)],   // the pets[Dog] narrowed view
});
```

**Concrete-subtype writes.** Writes go through the concrete-subtype symbol; the
accepted payload is exactly the ancestry chain (root + abstract ancestors + own).
Abstract-target writes, sibling-branch attributes, and the metadata fields
(`tag` / `tagValue` / `familyVariant`) are rejected before SQL.

```ts
await px.transaction(async tx => {
  const dog = await tx.dogs.create({ name: "Rex", ownerId: 1, barkVolume: 7 });
  await tx.dogs.update(Dog.id.eq(dog.id), { set: [Dog.barkVolume.set(9)] });
  await tx.dogs.delete(Dog.id.eq(dog.id));
});
```

**Idiomatic subtype-identity exposure.** `familyVariant` is surfaced idiomatically,
not as a mandatory string property the caller must read. The natural TypeScript
spellings are generated type guards, a sealed discriminated union, and pattern
matching:

```ts
for (const animal of await animals.toArray()) {
  if (Dog.isInstance(animal)) {
    animal.barkVolume;          // narrowed to Dog
  } else if (Cat.isInstance(animal)) {
    animal.indoor;              // narrowed to Cat
  }

  // …or a sealed switch on the concrete-subtype discriminant:
  switch (animal.variant) {
    case "Dog": /* animal: Dog */ break;
    case "Cat": /* animal: Cat */ break;
    case "WildBoar": /* animal: WildBoar */ break;
  }
}
```

The `narrow` combinator, the `includes` narrowed hop, and the discriminant all
serialize to (or materialize from) the same core artifacts the corpus pins — the
`narrow` operation node, the narrowed-view graph key `pets[Cat,Dog]`, and the
`familyVariant` observation — so a future build proves this surface against the
existing `m-inheritance-*` cases with no TypeScript-specific conformance channel.

## 3. Metadata / model input format (DQ5, DQ6)

**ANSWERED — see [TS-0008](../docs/adr/0008-metamodel-introspection-api-has-generic-and-typed-layers.md),
[TS-0009](../docs/adr/0009-one-canonical-serde-shared-by-metamodel-and-operations.md),
[TS-0010](../docs/adr/0010-serde-states-roundtrip-contract-and-names-libraries-nonbindingly.md).**
The metamodel (`m-descriptor`) is one artifact wearing two hats — an introspectable runtime
protocol and a serializable document — and this section specifies both hats so an
implementer can build the metamodel layer without inferring its shape from
`m-descriptor.md`.

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

Introspection is exposed in **two layers over the same descriptor** (TS-0008): a
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
| `attribute` | `AttributeMeta` | `name`, `type` (m-core neutral type, incl. `decimal(p,s)`), `column`, `primaryKey`, `nullable`, `maxLength?`, `readOnly`, `optimisticLocking`, `pkGenerator?`, `default?` |
| `relationship` | `RelationshipMeta` | `name`, `relatedEntity`, `cardinality` (`one-to-one`/`many-to-one`/`one-to-many`/`many-to-many`), `join`, `reverseName?`, `dependent`, `foreignKey?`, `orderBy?` (`{ attr, direction }[]`) |
| `index` | `IndexMeta` | `name`, `attributes` (ordered attribute names), `unique` |
| `asOfAttribute` | `AsOfAttributeMeta` | `name`, `fromColumn`, `toColumn`, `axis` (`processing`/`business`), `toIsInclusive`, `infinity` (`"infinity"`), `default` (`"now"`) |
| `valueObject` | `ValueObjectMeta` | `name`, `type` (logical struct name), `column` (single structured-document column), `mapping` (`"json"`), `nullable` |
| `inheritance` | `InheritanceMeta` | `strategy` (`table-per-hierarchy`/`table-per-concrete-subtype`; declared on the `root` only), `role` (`root`/`abstract-subtype`/`concrete-subtype`), `parent?` (non-root), `tag?` (`{ column }`; `table-per-hierarchy` root only), `tagValue?` (`table-per-hierarchy` concrete subtype only) |
| `pkGenerator` | `PkGeneratorMeta` | `strategy` (`none`/`max`/`sequence`); for `sequence`: `sequenceName?`, `batchSize?`, `initialValue?`, `incrementSize?` (the bare-enum form normalizes to `{ strategy }`) |

Defaulting follows the schema: readers surface the schema defaults
(`mutability: "read-only"`, `temporal: "non-temporal"`, `primaryKey: false`,
`nullable: false`, `readOnly: false`, `optimisticLocking: false`,
`dependent: false`, `unique: false`, `toIsInclusive: false`, `mapping: "json"`,
`nullable: false`) when a field is omitted, so the typed and generic layers agree
on every value. This mirrors the Python harness's `Entity` / `Model` accessors,
which are the concrete generic reader over the raw parsed descriptor.

### 3.2.1 m-core scalar runtime mapping

Generated TypeScript code maps every m-core neutral scalar to one public runtime
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

| m-core scalar | Generated property / snapshot type | Create / update input type | Adapter bind type | Materialization rule |
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
| `timestamp` | `Temporal.Instant` | `Temporal.Instant \| string` | Dialect-normalized timestamp bind | Parse strings as absolute instants; reject non-zero sub-microsecond precision; materialize UTC instants as `Temporal.Instant`. Postgres binds canonical UTC ISO wire strings; MariaDB keeps typed `Temporal.Instant` / `infinity` values until the adapter renders `datetime(6)` / the max-sentinel. |
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
serde seam, shared by the metamodel (`m-descriptor`) and the operation algebra (`m-op-algebra`) — the
same shared seam the Python harness realizes in `serde.py` and proves as `m-case-format`
layer 4a/4b (TS-0009). Giving serde its own package satisfies the template's
"dedicated module" requirement; sharing it across `m-descriptor`/`m-op-algebra` guarantees the adapter
canonicalizes identically to the oracle.

```ts
// @parallax/serde — canonical serialize / deserialize / round-trip
canonical(value): unknown                  // sort object keys recursively, PRESERVE list order
serialize(value, fmt: "json" | "yaml"): string
deserialize(text: string, fmt: "json" | "yaml"): unknown
assertRoundTrip(value): void               // JSON and YAML; idempotent + value-identity
```

The serde module MUST satisfy this **round-trip contract** (TS-0010), transcribed
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
  canonicalizes back to the same value (no data loss). This realizes the `m-descriptor`
  normative requirement `serialize(deserialize(descriptor)) == descriptor` in both
  formats, asserted for every model referenced by a compatibility case.

The `yaml` package (or `js-yaml`) plus built-in `JSON` is a **non-binding** suggested
default with the canonicalizer written in-house; the round-trip contract above —
not any named library — is the normative requirement (TS-0010).

## 4. Transaction-block demarcation (m-unit-work)

**ANSWERED — specified in full below.** All writes require an explicit
transaction; reads may use `px`, writes are available only through `tx`.

- **Demarcation construct.** A **closure**: `await px.transaction(async tx =>
  { … }, options?)`. `transaction` returns the callback's resolved value after the
  unit of work flushes and commits. If the callback throws, rejects, or commit
  fails, the transaction rolls back and the returned promise rejects. A
  `ParallaxTransaction` is invalid after its callback completes.
- **Strategy selection.** `TransactionOptions.concurrency` (`"locking" |
  "optimistic"`, default `"locking"`) selects the m-unit-work correctness strategy for the
  unit of work: `locking` takes the implicit shared read lock on in-transaction
  reads and advances a versioned entity's version with no gate; `optimistic` takes
  no lock and gates a versioned update on the observed version (m-opt-lock).

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
  `false`) configure the m-auto-retry/m-opt-lock retry contract (core ADR 0008 / ts ADR 0026). On a
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
  core ADR 0002 / core ADR 0012); `optimistic`-mode reads take no lock either. A versioned
  read records the observed version so a later update can gate on / advance from it.
  V1 does not expose a per-read `lock: false`.
- **Set-based writes.** `update` / `delete` accept either a predicate or an
  unresolved `ParallaxList` target, use explicit assignment arrays (not partial
  objects), and return result objects carrying at least `affectedRows`. On a
  versioned entity the framework-owned version (core ADR 0013) advances in both modes
  and gates in `optimistic` mode: updating a row the unit of work never observed
  throws `ParallaxReadBeforeWriteError`, a stale gate (zero rows) throws
  `ParallaxOptimisticLockError`, and an update whose assignment array changes no
  attribute issues no DML. Optimistic-lock conflicts are caller-driven and not
  auto-retried.

### 4.1 Temporal writes (`m-temporal-read`)

All temporal writes run through `ParallaxTransaction`; the root `px` handle has
no write methods. Processing instants are never accepted as per-operation
options. They come from the clock strategy supplied to `parallax({ clock })`, so
production code cannot rewrite audit history while tests can inject a fixed
clock.

The canonical TypeScript V1 `slice-mvp-1` claim requires only the
audit-only processing-temporal write surface below, plus the temporal read
surface in §2.3. Business-temporal-only writes and bounded bitemporal
rectangle-split writes are specified here as the post-claim m-bitemp-write
surface, but they remain outside V1 until the implementation adopts a later
canonical claim that includes them.

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

The following types and methods belong to a later canonical claim that includes
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

## 5. Test-double integration (m-case-format, DQ15)

**ANSWERED — see [TS-0030](../docs/adr/0030-cases-discovered-by-glob-executed-through-conformance-adapter.md),
[TS-0031](../docs/adr/0031-typescript-runs-postgres-only-in-ci-pinned-to-postgres-17.md).**
The TypeScript conformance suite proves the implementation against the same
language-neutral corpus the Python reference harness proves green. This section
specifies the runner, how cases are discovered and executed, how the database is
provisioned, and which dialects run in CI — enough to stand up the suite without
inferring it from the harness internals.

### 5.1 Test runner

The runner is **vitest** (TS-0030). The suite is a parametrized matrix of
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

Cases are **executed through the `parallax-conformance` adapter contract** (TS-0030,
[`m-conformance-adapter.md`](../../../core/spec/m-conformance-adapter.md)),
**not** by reaching into runtime internals:

- `parallax-conformance compile --case <c.yaml> --dialect <d>` emits SQL + binds and
  MUST NOT execute; the test compares the emitted statements and round-trip count.
- `parallax-conformance run --case <c.yaml> --dialect <d>` provisions, executes, and
  returns observations; the test compares the JSON envelope using the **same
  comparison rules `m-case-format` uses**.

The adapter is the single behavioral boundary: the suite imports no finder builders,
cache objects, or other internals. This decouples the suite from implementation
detail and reuses the shared corpus as the primary behavioral surface.

The suite MUST begin with `parallax-conformance describe` and use the returned
capability claims to decide whether a case is expected to run or expected to
return `status: "unsupported"`. TypeScript uses the core
`caseTags.include` / `caseTags.exclude` claim model; it MUST NOT treat broad
`modules` + `caseShapes` claims as sufficient when the V1 claim deliberately
defers part of a module.

### 5.3 Provisioning seam

Provisioning is **Testcontainers for Node** behind the same database-provider seam
the `parallax-conformance run` adapter consumes. Postgres uses
`@testcontainers/postgresql` pinned to **`postgres:17`**. MariaDB uses
`@testcontainers/mysql`'s `MySqlContainer` pinned to **`mariadb:11.4`**. The pins
move only when the corresponding compatibility provider pin moves.

The container is booted once per dialect/profile (session-scoped), but database
state is reset **through the provider seam**, not through a test-runner call to a
container-specific API. The TypeScript provider MUST expose this reset and
execution lifecycle:

```ts
interface CompatibilityDatabaseProvider {
  readonly dialect: "postgres" | "mariadb";
  reset(): Promise<void>;                 // clean, empty database/schema
  applyDdl(statements: readonly string[]): Promise<void>;
  loadFixtures(
    table: string,
    columns: readonly string[],
    rows: readonly (readonly unknown[])[],
  ): Promise<void>;
  query(sql: string, binds: readonly unknown[]): Promise<readonly ProviderRow[]>;
  exec(sql: string, binds: readonly unknown[]): Promise<number>;
  execRolledBack(sql: string, binds: readonly unknown[]): Promise<number>;
}
```

For every database-backed `run` case, the conformance adapter calls
`provider.reset()`, derives and applies DDL for the case's model, and then loads
fixture rows according to the core case lifecycle (`writeSequence` cases start
empty unless the case sets `given.fixtures`; read/scenario/conflict cases load the
model fixtures). This yields the same clean / migrated / isolated state as the
Python harness without coupling the suite to Testcontainers internals. The
composition-root providers also expose the shipped `database` adapter,
`dialectImpl`, and an independent `peer` connection for the API Conformance Suite
and provider contract tests; those additions stay at the composition root and do
not change the generic m-case-format runner port.

The normative Postgres reset is drop-and-recreate of the active schema:
`drop schema if exists public cascade; create schema public`. The MariaDB reset
drops every base table in the working schema. An implementation MAY optimize
`reset()` with a documented snapshot mechanism provided by a concrete dependency
and version, but that optimization must be invisible to the test runner and MUST
have the documented drop/recreate (or drop-table) fallback. The spec does not
require a portable Testcontainers snapshot API.

### 5.4 CI dialect set and per-dialect golden-SQL selection

The V1 `parallax-conformance describe` claim remains **Postgres-only**. That is
the official adapter grade for `slice-mvp-1`. TypeScript nevertheless ships two
database implementations behind the m-dialect seam:

- **Postgres full m-case-format profile** (`postgres-full-slice-mvp-1`): every
  harness-lane case selected by `slice-mvp-1` over `postgres:17` (including all
  value-object cases — their nested-predicate reads, materialization graph,
  atomic document writes, inherited-temporality reads, and pre-SQL `rejected`
  refusals, plus the standalone plain-bitemporal-insert witness `m-bitemp-write-009`,
  a Postgres-only golden that stays off the curated MariaDB profile), included in
  `just ts-db`.
- **MariaDB curated m-case-format profile** (`mariadb-curated-36`): a first-class partial
  profile over `mariadb:11.4`, included in `just ts-db-all`. Its mechanically
  checked membership includes harness-lane cases whose `then.statements` entries
  carry a `mariadb` `sql`
  key (COR-26 added the audit-chaining backfill `m-audit-write-002`/`-003`/`-004`, then the
  full-bitemporal `position` write/conflict cases `m-bitemp-write-001`-`-008` once the
  harness reserved-word set became per-dialect — those cases now EXECUTE on the TS run-lane
  too, covering rectangle-split write sequences and optimistic-conflict closes, because the
  temporal-insert builder emits the sqlglot-canonical quoted-table spacing
  (`` insert into `position` (…) ``); the reference-harness oracle is the independent second
  witness) plus the marquee MariaDB
  dialect/error-classification proofs (`m-read-lock-009`, `m-temporal-read-021`, `m-core-004`, `m-db-error-001`-`m-db-error-008`).
  The value-object cases DO carry `mariadb` golden, but they are deliberately
  **not** run through the curated run-lane profile: their MariaDB golden-SQL
  parity is proven directly by the Phase-10 dialect-lowering compile tests
  (`packages/dialect/test/value-object-lowering.test.ts`,
  `packages/sql/test/value-object.test.ts`), so the curated profile stays at its
  marquee (non-value-object) set.

Per-dialect golden SQL is selected by the provider's own `dialect` identifier,
which is the `sql`-map key inside each `then.statements` entry. The MariaDB profile
does not silently skip cases. Every Postgres full-profile case that the curated
profile does not run is classified as an explicit MariaDB profile exclusion:
either `no mariadb golden statements in this partial MariaDB profile` (no
`mariadb` `sql` key) or, for a value-object case, `value-object MariaDB parity is
proven by the Phase-10 direct compile tests, not this run-lane profile`.

### 5.5 Database provider support and matrix profiles

TypeScript implements the portable database-provider test contract in
[`../../../core/spec/database-provider-test-contract.md`](../../../core/spec/database-provider-test-contract.md):

- **Docker-free dialect contract:** `packages/dialect/test/dialect-conformance.test.ts`
  is a shared table with one row per dialect. It proves quoting, null ordering,
  read locks, column types, bytes projection, infinity, placeholders, parsers,
  bind behavior, and error classification for Postgres and MariaDB.
- **Real-adapter smoke:** `packages/typescript/test/db-adapter-smoke.test.ts`
  runs both shipped adapters, `@parallax/db-postgres` and
  `@parallax/db-mariadb`, through connection construction, managed scalar reads,
  transaction callback behavior, bytes write round trip, affected-row semantics,
  and feasible lock-timeout classification.
- **Provider contract:** `packages/typescript/test/db-provider-contract.test.ts`
  selects providers from the same registry as API conformance
  (`PARALLAX_DATABASES`) and proves `reset`, `applyDdl`, `loadFixtures`, `query`,
  `exec`, `execRolledBack`, and peer visibility.
- **Matrix profiles:** `packages/typescript/test/m-case-format-profiles.ts` declares the
  canonical Postgres full profile, the historical Postgres read/graph/txn/temporal
  subsets as named profiles, and the MariaDB curated partial profile. The
  Docker-free `m-case-format-profiles.test.ts` guards profile membership and explicit
  MariaDB exclusions.
- **Commands:** `just ts-db-fast` runs the Docker-free dialect/provider/profile
  checks; `just ts-db` is the primary Docker-backed DB gate, covering adapter
  smoke, the provider contract, the Postgres full m-case-format profile, and default
  Postgres API conformance; `just ts-db-all` adds the MariaDB API Conformance
  Suite and curated m-case-format profile. Docker-backed suites use a `docker info` gate
  and report skipped database checks when Docker is unavailable.

## 6. API Conformance Suite & Usage Guide

**ANSWERED — the suite lives at
`packages/typescript/test/api-conformance/` and the Usage Guide at
`languages/typescript/docs/guide/`.** Beyond the wire-level conformance adapter of
[§5](#5-test-double-integration-m-case-format-dq15), TypeScript proves that the idiomatic
developer surface of [§2](#2-api-surface-non-normative--dq3) reproduces the
claimed case set against a real Postgres through the shipped `@parallax/db-postgres`
adapter by default (`just ts-db`), with a MariaDB fan-out lane (`just ts-db-all`)
that runs the same developer reads and writes through `@parallax/db-mariadb`.
It also renders a Usage Guide from that same suite source. Both are the
worked example of the language-neutral
[`m-api-conformance.md`](../../../core/spec/m-api-conformance.md):
they are additive proof beside the conformance-adapter grade and never touch the
grader.

### 6.1 Suite framework and location

The API Conformance Suite is a **vitest** suite at
`packages/typescript/test/api-conformance/`, run by `just ts-db` against a
Testcontainers `postgres:17` container and by `just ts-db-all` for the MariaDB
fan-out — the same images [§5.3](#53-provisioning-seam) pins. Each family
(`reads` / `deep-fetch` / `temporal` / `transactions` / `locking`) is a
`*.api-conformance.test.ts` file that provisions the case's model, writes the
**idiomatic `px.*` / `px.transaction` developer code** an application would write,
and asserts the corpus's expected results. Family suites gate their Docker-backed
runs on a `docker info` probe; the Docker-free `coverage.test.ts` enforces the
partition below.

### 6.2 Coverage partition and no-drift guard

- **Coverage partition.** `coverage.test.ts` (Docker-free) discovers every case
  selected by the canonical `slice-mvp-1` claim and asserts
  `exercised ∪ skipped == claimed cases`
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

Cases are reason-skipped because what they prove is
serde/harness machinery a developer never authors, not a developer-facing
surface — the four below; the deep-fetch × value-object composition witness
(`m-deep-fetch-018`, a run-only case whose root and child both materialize a
value-object document at every graph level — a composition of the already-exercised
deep-fetch and value-object-materialization surfaces, proven end-to-end by the
harness run lane); the eleven value-object `rejected` negatives
(`m-value-object-034`-`m-value-object-044`), whose whole assertion is a **pre-SQL
refusal**: the invalid input (a value-object root, an unknown nested path, a
`deepFetch`/navigation targeting a value object, a type-mismatched literal, a
missing required attribute or a missing required nested / top-level value object)
is refused before any query is built, so there is no idiomatic developer query to
author — the refusal is proven by the harness run lane and the
`@parallax/operation` validators; the nine bitemporal milestone-chaining writes
(`m-bitemp-write-001`-`m-bitemp-write-009`), whose rectangle-split / plain /
optimistic-gated DML is proven end-to-end by the harness and conformance run lanes
(`slice-run` drives `@parallax/conformance`'s write-sequence / conflict plan), not
the developer-surface object API; and the COR-26 Phase-5 type-fidelity,
value-object-write, and pk-gen writes — the scalar WRITE round-trips / boundaries
(`m-core-005`-`m-core-008`), the value-object document writes (`m-value-object-045`
multi-row batched insert, `m-value-object-046` under an optimistic gate), and the
primary-key allocations (`m-pk-gen-001`/`-002` `max`, `m-pk-gen-004`/`-006`/`-014`
simulated-`sequence`) — each proven end-to-end by the reference harness (both
dialects; the pk-allocation oracle) and the conformance run lane, not a
developer-authored serde/allocation surface. The four serde-canonicalization /
concurrency-choreography skips are:

- **`m-op-algebra-024`** — an `equivalentEncodings` serde-canonicalization check (two surface
  spellings collapse to one canonical operation). Its query semantics are
  exercised through the developer surface elsewhere; its ungrouped sibling `m-op-algebra-025`
  runs in `reads.api-conformance.test.ts`.
- **`m-read-lock-006`** — read-lock-blocks-writer, a HARNESS-lane two-connection concurrency
  case (a held `for share` read excludes a concurrent writer → `lockWaitTimeout`).
  Its behavioral proof is discharged by the reference harness and the TypeScript
  conformance runner's two-session run lane (`slice-run` / `mariadb-run` drive
  `@parallax/conformance`'s `runRun`), not the developer surface — a developer
  never authors the barrier + lowered-lock-budget choreography (the read lock's
  developer-observable behavior is exercised by `m-read-lock-001`/`m-read-lock-002`).
- **`m-read-lock-007`** — read-lock-shared-compatible, a HARNESS-lane two-connection
  concurrency-success case (A and B both take `for share` and both succeed — the
  lock is shared, not exclusive). Like `m-read-lock-006`, discharged by the reference harness
  and the conformance runner's two-session `runRun`, not the developer surface.
- **`m-read-lock-008`** — projection-omits-lock-admits-writer, a HARNESS-lane two-connection
  concurrency-success case (A holds an unlocked `distinct` projection, B's UPDATE is
  admitted). Discharged by the same two-session `runRun`; the projection-omits-lock
  emission is exercised by `m-read-lock-003`.

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
  typed value-object classes with parent-to-nested getters to arbitrary depth,
  the typed nested-predicate builder, and operation accessors are all generated
  from it. Codegen MUST emit only artifacts derivable from
  `metamodel.schema.json`: value objects generate typed structure because the
  descriptor declares their `attributes` / nested `valueObjects` / `cardinality`
  (m-value-object), while enum types are not generated in V1 because the
  descriptor has no enum element. Codegen is
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
  `describe` / `compile` / `run`; `benchmark` is the post-claim m-perf-bench command
  described in §11 and is not claimed by `slice-mvp-1` —
  see [§5](#5-test-double-integration-m-case-format-dq15).
- **Where generated artifacts live / regeneration.** Generated output is derived
  code: gitignored by default, written to `./.parallax/generated` (outside
  `src/`, so it does not look like user-owned source), and regenerated during
  install, build, and CI. Generated files are inspectable but not editable —
  customization belongs in descriptors, generator configuration, runtime adapters,
  and application-owned domain functions. Applications import the output through
  the package-local `#parallax` alias.

## 8. Collection idioms (m-op-list)

**ANSWERED — specified in full below.**

- **Concrete collection type.** A list result is a `ParallaxList<T>`: an async,
  operation-backed result collection. It implements async iteration and resolves
  its backing operation (`m-op-list`) on first object-returning access — laziness and
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
  a bulk target ([§4](#4-transaction-block-demarcation-m-unit-work)).

## 9. Build-time dependency enforcement (DQ3, dependency-graph)

**ANSWERED — see [TS-0034](../docs/adr/0034-module-dag-enforced-by-dependency-cruiser.md).**
The normative module-dependency graph
([`modules.md`](../../../core/spec/modules.md)) is the **only**
legal dependency direction between core modules, and each per-language
spec **SHOULD** prescribe a build-time mechanism that fails the build on any
module-to-module dependency the graph does not declare. This section names the
tool, maps every core module `m-core`–`m-coherence` onto a TypeScript package under
`languages/typescript/packages/*`, records the support packages
`@parallax/serde` and `@parallax/typescript`, and transcribes the legal
module edges one-to-one from the core graph so the TypeScript edge set
is mechanically diff-able against it. The support-package edges are explicit
package-topology edges, not additions to the core module DAG.

### 9.1 Enforcement tool

The tool is **dependency-cruiser** (TS-0034), run as a standalone
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
      comment: "Only documented module, support, and composition edges are legal.",
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
    // Support package edges.
    { from: { path: "^languages/typescript/packages/metamodel/" },     to: { path: "^languages/typescript/packages/serde/" } },
    { from: { path: "^languages/typescript/packages/operation/" },     to: { path: "^languages/typescript/packages/serde/" } },

    // Composition package edges. Implementation packages MUST NOT import
    // from @parallax/typescript; it is the CLI/generator/application facade.
    { from: { path: "^languages/typescript/packages/typescript/" },    to: { path: "^languages/typescript/packages/(core|metamodel|operation|sql|relationships|lists|bitemporal|transactions|lifecycle|locking|dialect|db|db-postgres|db-mariadb|conformance|benchmark|coherence|serde)/" } },

    // m-db-port port/adapter support edges.
    { from: { path: "^languages/typescript/packages/db-postgres/" },   to: { path: "^languages/typescript/packages/db/" } },
    { from: { path: "^languages/typescript/packages/db-postgres/" },   to: { path: "^languages/typescript/packages/dialect/" } },
    { from: { path: "^languages/typescript/packages/db-mariadb/" },    to: { path: "^languages/typescript/packages/db/" } },
    { from: { path: "^languages/typescript/packages/db-mariadb/" },    to: { path: "^languages/typescript/packages/dialect/" } },

    // Numbered module edges from core/spec/modules.md.
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

Modules are language-neutral behavioral modules, not packages. Each
**pnpm-workspace package** under `languages/typescript/packages/` implements one
**or more** core modules and enforces the module-dependency graph internally
(TS-0034). Real workspace packages — rather than path-ruled directories — make the
workspace graph itself participate in the layering: a package's `package.json`
lists only the sibling packages it is permitted to depend on, and
dependency-cruiser is the mechanical gate over the `import` graph. The
`languages/typescript/` directory is the TypeScript language workspace root:
`languages/typescript/spec/` and `languages/typescript/docs/` are documentation,
while `languages/typescript/packages/*` contains implementation source.

| TS package | Modules implemented | Responsibility |
|---|---|---|
| `@parallax/core` | `m-core` | Core conventions (types · infinity · tz) |
| `@parallax/metamodel` | `m-descriptor`, `m-pk-gen`, `m-inheritance`, `m-value-object` | Domain model & metamodel |
| `@parallax/operation` | `m-op-algebra` (`m-agg` deferred) | Query / operation algebra |
| `@parallax/sql` | `m-sql` (`m-sql-agg` deferred) | SQL generation contract |
| `@parallax/relationships` | `m-navigate`, `m-deep-fetch` | Relationships & deep fetch |
| `@parallax/lists` | `m-op-list`, `m-batch-write`, `m-cascade-delete` | Lists & bulk/set operations |
| `@parallax/bitemporal` | `m-temporal-read`, `m-audit-write`, `m-bitemp-write` (`m-business-only` deferred) | Temporal reads & milestoning writes |
| `@parallax/transactions` | `m-unit-work`, `m-read-lock`, `m-auto-retry` (`m-process-cache` deferred) | Transactions, unit of work, read lock & retry |
| `@parallax/lifecycle` | `m-detach` | Object lifecycle & detach |
| `@parallax/locking` | `m-opt-lock` | Optimistic locking |
| `@parallax/dialect` | `m-dialect` | Pure dialect / portability layer (SQL strings + typed-bind/type-parse fns; no I/O) |
| `@parallax/db` | `m-db-port`, `m-db-error` | Abstract runtime database port + portable error surface (`execute`/`executeWrite`/`transaction`; normalize-at-boundary) |
| `@parallax/db-postgres` | `m-db-port` (Postgres adapter) | Concrete Postgres adapter over the `postgres` driver (one per DB type) |
| `@parallax/db-mariadb` | `m-db-port` (MariaDB adapter) | Concrete MariaDB adapter over the `mysql2` driver (one per DB type) |
| `@parallax/conformance` | `m-case-format`, `m-conformance-adapter`, `m-api-conformance` | Compatibility harness & conformance adapter |
| `@parallax/benchmark` | `m-perf-bench` | Performance & benchmark harness |
| `@parallax/coherence` | `m-coherence` (deferred) | Cross-process cache coherence |
| `@parallax/serde` | serde seam (support) | Canonical metamodel / operation serde |
| `@parallax/typescript` | — (composition root) | CLI, generator config, public runtime facade, generated-barrel support |

The shared
`@parallax/serde` package (the canonical serde seam of
[§3.3](#33-serde-module)) is a public pnpm-workspace support package, not a
core-module package and not part of the generated `#parallax` application
barrel. It has no sibling-package dependencies. The only legal direct imports to
it are `@parallax/metamodel -> @parallax/serde` and `@parallax/operation ->
@parallax/serde`, which the dependency-cruiser allowlist above encodes
explicitly.

The `@parallax/typescript` package is a **composition package** at
`languages/typescript/packages/typescript`. It owns the `parallax` CLI,
`parallax-conformance` CLI entry point, generator configuration API
(`@parallax/typescript/config`), public runtime facade, and generated-barrel
support. It MAY depend on any implementation package and on
`@parallax/serde`, because it is the composition root. No implementation package or
support package may depend on `@parallax/typescript`; implementation modules stay
below the facade.

**`m-dialect` maps to more than one package** (per the core
[`language-spec-template.md`](../../../core/spec/language-spec-template.md) §9 rule
and [`m-db-port.md`](../../../core/spec/m-db-port.md) →
*m-dialect decomposition*): the database seam is normatively decomposed into a **pure
dialect / portability** module (`@parallax/dialect` — SQL strings +
typed-bind normalization and type-parse functions to managed values; no I/O, no
driver), an **abstract runtime database port** (`@parallax/db` — the `execute(sql, binds)` /
`executeWrite(sql, binds)` / `transaction(body)` contract plus the
normalize-at-boundary rule so an adapter returns managed scalars for reads and
native affected-row counts for writes), and **N concrete adapters**
(`@parallax/db-postgres` and `@parallax/db-mariadb`), one per database type, each
depending **only** on the port
and the pure dialect layer. All three share the single `m-dialect --> m-core` edge
— the decomposition is a rule *within* the module, not new DAG nodes, so
[`modules.md`](../../../core/spec/modules.md) is unchanged and
`@parallax/db` / `@parallax/db-postgres` / `@parallax/db-mariadb` are
**language-impl support edges** (like
the `@parallax/serde` edges), documented in §9.3 but absent from the module-edge
block. `@parallax/db` is a leaf (it reaches only `@parallax/core`), and
`@parallax/db-postgres` carries the `postgres` driver + porsager OID registration
and `@parallax/db-mariadb` carries the `mysql2` driver + MariaDB type-cast
registration, but neither contains wire/grading logic (*managed at the boundary,
wire at the grader*). The two structural rules the core spec mandates hold:
**only the composition root (`@parallax/typescript`) may depend on a concrete
adapter** (concrete adapters appear nowhere in the implementation packages), and **the
port depends on nothing application-specific**. The composition-root conformance
providers retain provisioning (Testcontainers + `reset`/`applyDdl`/`loadFixtures`)
but delegate SQL execution to concrete `@parallax/db-*` instances, then render
managed scalars to the canonical wire form for the run envelope — so there is **no
`m-case-format → m-dialect` edge** and the claimed case set is continuous proof the shipped adapters
work.

### 9.3 Legal-edge contract

The module legal edges are transcribed **one-to-one** from
[`modules.md`](../../../core/spec/modules.md), keyed by the same
module slugs so the edge set is mechanically diff-able against core. Each edge
`A --> B` reads "A depends on B"; the reverse is a spec violation. Combined with
the mapping table, the two explicit `@parallax/serde` support-package edges, the
two **m-db-port port/adapter support edges** below, and the top-level
`@parallax/typescript` composition edge above, this block is the source the
`.dependency-cruiser.js` allowlist encodes.

Beyond the module edges, the m-dialect decomposition (§9.2) contributes two
**support edges** that are *not* new DAG edges (the whole seam shares the
one `m-dialect --> m-core` edge above) but are enforced by the allowlist:

- `@parallax/db-postgres --> @parallax/db` and
  `@parallax/db-mariadb --> @parallax/db` — concrete adapters depend on the
  abstract port.
- `@parallax/db-postgres --> @parallax/dialect` and
  `@parallax/db-mariadb --> @parallax/dialect` — each adapter delegates every
  parse decision to the pure dialect layer (the single source of parse logic), so
  parse rules are never duplicated across adapters.

`@parallax/db` (the port) depends only on `@parallax/core` (the universal leaf
allowance), and `@parallax/db` + the concrete adapters are added to the
composition-root `@parallax/typescript --> (…)` `to` set — the composition root is
the only layer permitted to depend on a concrete adapter. No implementation package
depends on a concrete adapter, and no above-seam module reaches a driver.

```dependency-graph
m-descriptor --> m-core
m-dialect --> m-core
m-op-algebra --> m-descriptor
m-sql --> m-op-algebra
m-sql --> m-dialect
m-unit-work --> m-op-algebra
m-unit-work --> m-dialect
m-op-list --> m-op-algebra
m-op-list --> m-unit-work
m-navigate --> m-op-algebra
m-navigate --> m-unit-work
m-navigate --> m-temporal-read
m-op-list --> m-deep-fetch
m-temporal-read --> m-unit-work
m-detach --> m-unit-work
m-opt-lock --> m-unit-work
m-case-format --> m-op-algebra
m-case-format --> m-sql
m-case-format --> m-navigate
m-case-format --> m-temporal-read
m-case-format --> m-unit-work
m-case-format --> m-detach
m-case-format --> m-opt-lock
m-case-format --> m-dialect
m-perf-bench --> m-case-format
m-coherence --> m-unit-work
```

The non-obvious directions carry over verbatim from the core graph: `m-unit-work` depends
on `m-op-algebra` not `m-sql` (the transaction / unit-of-work layer is expressed over
operations, not SQL); `m-navigate` depends on `m-op-algebra` directly (navigation's
`navigate`/`exists`/`notExists` nodes are algebra vocabulary — [core ADR
0025](../../../docs/adr/0025-lifecycle-result-surfaces-sit-above-the-shared-fetch-algorithm.md)
inverted the lifecycle-result-surface edges, so `m-op-algebra` is no longer reachable from
navigate only transitively, through the now-removed `m-navigate → m-op-list` edge); `m-op-list`
depends on `m-deep-fetch` in turn (a lazy list is *populated by* deep fetch — core's own graph
gives the snapshot-read lifecycle the same relationship with deep fetch, `m-snapshot-read -->
m-deep-fetch`, though `slice-mvp-1` does not claim that module: the two lifecycle result
surfaces sit as peers *above* the shared fetch algorithm, and neither depends on the other);
`m-navigate` depends on
`m-temporal-read` (a pinned as-of value
propagates per relationship hop, so the relationship layer references the as-of
model — the edge the claimed temporal deep-fetch 03xx cases require); and `m-sql`
depends on `m-dialect` (SQL generation routes through the portability seam). `m-case-format`
additionally depends on `m-unit-work` directly — the harness realizes m-unit-work unit-of-work
behavior itself (batched write-sequence flushes, read-your-own-writes scenarios),
a direct edge that coexists with the transitive `m-case-format → m-opt-lock → m-unit-work` path, mirroring
how `m-navigate → m-unit-work` coexists with the transitive `m-navigate → m-temporal-read →
m-unit-work` path — and on `m-dialect` directly, since the
harness applies the dialect's DDL / quoting / read-lock-application rules to
assemble SQL (`applyReadLock`). m-coherence's
single legal direction `m-coherence → m-unit-work` is
transcribed in the block above, keeping the TypeScript edge set one-to-one with
the core graph; the `@parallax/coherence` package is a **fast-follow** capability
that TypeScript V1 MAY defer implementing, but its boundary is documented here so
the dependency-cruiser allowlist stays complete and mechanically diff-able against
the core graph.

## 10. Optional optimized data structures (m-perf-bench, DQ10)

**DEFERRED-with-rationale — non-normative, no V1 decision; see
[TS-0033](../docs/adr/0033-optimized-data-structures-non-normative-no-v1-decision.md).**
This section is **non-normative**: the optional optimized data structures exist
only to back the `m-process-cache` identity / query caches, and that cache/identity capability set in
m-unit-work is deferred from TypeScript V1 (TS-0027,
[§4](#4-transaction-block-demarcation-m-unit-work)). The transaction, read-lock, and write
capability set specified in §4 still belongs to V1. There is nothing cache-specific to
optimize for V1, so no V1 decision is recorded. The core itself marks these
techniques optional and non-normative — a language may hit its targets any way it
likes.

The two optional techniques the template lists are recorded here so the deferral
is deliberate rather than an omission:

- **Open-addressing map/set analogues** (`UnifiedMap` / `UnifiedSet`) for the
  identity / query caches — lower per-entry overhead than chained hash tables.
- **Key-derived hashing analogue** (`HashingStrategy`) — index domain objects by
  a derived (e.g. composite-PK) key without allocating wrapper key objects.

**Post-V1 note (non-binding):** when the m-unit-work identity/query-cache capabilities land, a
built-in `Map` keyed by a canonical primary-key string is the idiomatic
JavaScript baseline for both caches. The Java open-addressing /
no-wrapper-key-allocation techniques have **no compelling direct JavaScript
analogue** — short string keys are effectively interned by the engine and V8
`Map`s are already compact, so a composite-PK string key captures the same
benefit without a custom hashing strategy or an open-addressing table. This
decision is deferred with the cache/identity capabilities and made when that
surface is implemented.

## 11. Per-language performance targets (m-perf-bench, DQ10)

**DEFERRED-with-rationale (m-perf-bench command and numeric targets) + the
`expectRoundTrips` invariant is binding for V1 compatibility cases — see
[TS-0032](../docs/adr/0032-performance-methodology-bound-numeric-targets-deferred.md).**
TypeScript records the shared `m-perf-bench` methodology now, but the canonical
`slice-mvp-1` Conformance Slice does **not** claim module `m-perf-bench` or
the `benchmark` command. A V1 adapter adopting that claim may therefore return
`unsupported` for `parallax-conformance benchmark`. The benchmark command and
numeric targets are enabled by a later canonical claim that includes
m-perf-bench, after a real implementation can produce a baseline. Numbers
invented against a non-existent implementation would be fabricated rather than
measured.

### 11.1 Post-claim benchmark methodology

The methodology is the durable, comparable part of `m-perf-bench`. When TypeScript claims
the m-perf-bench benchmark capability, it uses this contract:

- **Shared fixtures.** The same benchmark fixtures under
  [`core/compatibility/benchmarks/`](../../../core/compatibility/benchmarks)
  (`read-mix.yaml`, `deep-fetch.yaml`, `milestone-write.yaml`), run against the
  same deterministically generated datasets at the same scale, so a TypeScript
  number is directly comparable to the reference figures and to past runs.
- **Nearest-rank percentile.** `wallTimeMs.p50` / `wallTimeMs.p95` are computed
  with the nearest-rank percentile, matching the Python harness.
- **`report.json` schema.** The emitted report uses the schema fixed in
  [`m-perf-bench.md`](../../../core/spec/m-perf-bench.md): `generatedAt`,
  `dialect`, `benchmarks[].{ fixture, model, datasetRows, workloads[] }` (each
  workload carrying `name`, `iterations`, `wallTimeMs.{ p50, p95 }`, `roundTrips`,
  and the optional `expectRoundTrips` / `roundTripsOk`), and
  `memory.{ peakBytes, steadyBytes }`.
- **Execution hook.** Once the m-perf-bench benchmark command is claimed, benchmarks run
  through the
  `parallax-conformance benchmark --benchmark <b.yaml> --dialect <d>` command of
  the [conformance adapter
  contract](../../../core/spec/m-conformance-adapter.md), against the
  Postgres provider seam of [§5](#5-test-double-integration-m-case-format-dq15). The
  command writes the standard adapter envelope to stdout with the m-perf-bench report under
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

**Tracking note.** Once the first TypeScript implementation claims m-perf-bench, runs the
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
in V1 through m-conformance-adapter and, once m-perf-bench is claimed, by the benchmark runner too:

- **`m-case-format` round-trip-count layer** — for every compatibility case,
  `len(then.statements[].sql[dialect])` MUST equal the case's `then.roundTrips`
  ([§5.2](#52-case-discovery-and-execution-boundary) compares this via the
  `parallax-conformance` envelope's `roundTrips`).
- **Post-claim `m-perf-bench` benchmark runner** — when the benchmark command is claimed,
  a workload's actual round trips MUST equal its declared `expectRoundTrips`; a
  deep fetch that silently regresses to N+1 fails the benchmark run.

This invariant is binding even though the wall-time and memory numbers are not.

## Object lifecycle: detach, snapshots, and entity inputs (m-detach)

This section is supplementary to the template's §1–§11 (the template has no
object-lifecycle slot). It records the TypeScript surface for getting data **out
of** and **back into** managed objects — the TypeScript analogue of Reladomo's
detach / merge-back lifecycle (`m-detach`, the `@parallax/lifecycle` package of
[§9.2](#92-module--package-mapping)). The decisions are recorded in
[TS-0020](../docs/adr/0020-snapshots-are-the-typescript-detached-data-surface.md)
and
[TS-0018](../docs/adr/0018-generated-entity-inputs-provide-validation-helpers.md).

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
since omitted relationships are already excluded), and each top-level value
object is selected as one whole structured-document property (its typed nested
composite) rather than a per-nested-field selection. List-level snapshots
batch-load requested relationships like
includes
([§2.6](#26-relationship-navigation-and-deep-fetch-m-deep-fetch)) to avoid N+1.
(`JSON.stringify` over a managed object is scalar-only and synchronous and does
not lazy-load relationships, so use a snapshot when relationship data is needed.)

**Entity inputs are the create / reattach surface.** `OrderInput` is the
generated input-validation namespace and type for data accepted by `create`
([§4](#4-transaction-block-demarcation-m-unit-work)) — the surface for turning
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
or replace `tx.entity.create(...)` (TS-0018).

**Deferred from V1.** The full Reladomo-style detached-object lifecycle — the
`m-detach` state machine (`persisted` → `detached` → `detached-deleted`) and merge-back
(`getDetachedCopy` / `copyDetachedValuesToOriginalOrInsertIfNew`) — is **deferred
from TypeScript V1**. When `m-detach` merge-back lands it should be expressed through
explicit snapshot apply / merge APIs that preserve the core observable semantics
(TS-0020), not by introducing detached managed objects.

## Template Coverage Appendix

This table maps every `language-spec-template.md` section §1–§11 to its answer
location in this document and an explicit status. Every section is specified
inline here and is now resolved — `ANSWERED` or `DEFERRED-with-rationale` — with
no decide-and-record debt remaining. The spec also carries a supplementary
[Object lifecycle](#object-lifecycle-detach-snapshots-and-entity-inputs-m-detach)
section (`m-detach`) beyond the template skeleton; it is not a template row.

| Template section | Status | Answer location | ADRs |
|---|---|---|---|
| §1 Conformance Slice declaration | ANSWERED | [§1](#1-conformance-slice-declaration) | [core ADR 0018](../../../docs/adr/0018-slice-tags-follow-the-slice-naming-convention.md) |
| §2 API surface | ANSWERED | [§2](#2-api-surface-non-normative--dq3) | — |
| §3 Metadata / introspection + serde | ANSWERED | [§3](#3-metadata--model-input-format-dq5-dq6) | [TS-0008](../docs/adr/0008-metamodel-introspection-api-has-generic-and-typed-layers.md), [TS-0009](../docs/adr/0009-one-canonical-serde-shared-by-metamodel-and-operations.md), [TS-0010](../docs/adr/0010-serde-states-roundtrip-contract-and-names-libraries-nonbindingly.md) |
| §4 Transaction-block demarcation | ANSWERED | [§4](#4-transaction-block-demarcation-m-unit-work) | — |
| §5 Test-double integration | ANSWERED | [§5](#5-test-double-integration-m-case-format-dq15) | [TS-0030](../docs/adr/0030-cases-discovered-by-glob-executed-through-conformance-adapter.md), [TS-0031](../docs/adr/0031-typescript-runs-postgres-only-in-ci-pinned-to-postgres-17.md) |
| §6 API Conformance Suite & Usage Guide | ANSWERED | [§6](#6-api-conformance-suite--usage-guide) | — |
| §7 Codegen-or-not | ANSWERED | [§7](#7-codegen-or-not-dq5) | — |
| §8 Collection idioms | ANSWERED | [§8](#8-collection-idioms-m-op-list) | — |
| §9 Build-time dependency enforcement | ANSWERED | [§9](#9-build-time-dependency-enforcement-dq3-dependency-graph) | [TS-0034](../docs/adr/0034-module-dag-enforced-by-dependency-cruiser.md) |
| §10 Optional optimized data structures | DEFERRED-with-rationale | [§10](#10-optional-optimized-data-structures-m-perf-bench-dq10) | [TS-0033](../docs/adr/0033-optimized-data-structures-non-normative-no-v1-decision.md) |
| §11 Per-language performance targets | DEFERRED-with-rationale | [§11](#11-per-language-performance-targets-m-perf-bench-dq10) | [TS-0032](../docs/adr/0032-performance-methodology-bound-numeric-targets-deferred.md) |

### Completion check

This document satisfies the `language-spec-template.md` completion check:

- **No remaining markers.** Every template section §1–§11 is resolved; no
  *decide-and-record* placeholder remains. Nine sections are `ANSWERED`;
  [§10](#10-optional-optimized-data-structures-m-perf-bench-dq10) and
  [§11](#11-per-language-performance-targets-m-perf-bench-dq10) are `DEFERRED-with-rationale`
  (deliberate, ADR-backed decisions, not omissions), and the §11 `expectRoundTrips`
  invariant stays binding.
- **No contradiction with core.** The
  [§9](#9-build-time-dependency-enforcement-dq3-dependency-graph) legal-edge block
  is transcribed one-to-one from
  [`modules.md`](../../../core/spec/modules.md) and keyed by the
  same module slugs, while the `@parallax/serde` and `@parallax/typescript` edges
  are explicit TypeScript package-topology edges outside the core graph; the
  [§1](#1-conformance-slice-declaration) capability claim is byte-equal to the
  canonical `slice-mvp-1` claim in
  [`slices.md`](../../../core/spec/slices.md); the
  [§3](#3-metadata--model-input-format-dq5-dq6) metadata shapes are drawn
  one-to-one from
  [`metamodel.schema.json`](../../../core/schemas/metamodel.schema.json)'s eight
  element types; [§5](#5-test-double-integration-m-case-format-dq15) pins the same
  `postgres:17` image the reference harness pins; and
  [§11](#11-per-language-performance-targets-m-perf-bench-dq10) binds the same `m-perf-bench`
  methodology, fixtures, and `report.json` schema.
- **Self-sufficient for a fresh implementer.** This document specifies every
  template section §1–§11 inline; together with the cited ADRs it is sufficient to
  author a TypeScript implementation and run the compatibility suite to green
  **without re-reading the core spec or any other Parallax document**.
