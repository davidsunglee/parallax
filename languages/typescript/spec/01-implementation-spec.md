# TypeScript Implementation Spec

This document is the **template-format companion** to
[`00-overview.md`](00-overview.md). It follows the prescribed §1–§9 skeleton of
[`../../../core/spec/language-spec-template.md`](../../../core/spec/language-spec-template.md)
and exists to satisfy that template's *(decide and record)* checklist so a fresh
reader can author a TypeScript implementation and run the compatibility suite to
green **without re-reading the core spec**.

The narrative API-surface description lives in `00-overview.md` and is preserved
unchanged. This document does not restate it in full. Instead:

- For the sections the overview already answers — §1 API surface, §3
  transaction-block demarcation, §5 codegen, §6 collection idioms — this
  document gives a concise restatement and cross-references the matching
  `00-overview.md` section for detail. Re-reading another *TypeScript* document
  (`00-overview.md`) is permitted; the template's completion check only forbids
  re-reading the **core** spec.
- For the sections the overview only gestures at or leaves open — §2 metamodel
  introspection + serde, §4 test-double integration, §7 build-time dependency
  enforcement, §8 optional optimized data structures, §9 per-language
  performance targets — this document is the full specification.

The [Template Coverage Appendix](#template-coverage-appendix) at the end maps
every template section to its answer location and an explicit status, so any
future gap surfaces as an explicit marker rather than silent prose.

## 1. API surface (non-normative — DQ3)

**ANSWERED — see [`00-overview.md` §5 Query API](00-overview.md#5-query-api)
(and §1, §6, §9) for the full surface.** Summary of the recorded choices:

- **Finder / query entry point.** TypeScript uses one generated fluent
  expression DSL on the entity symbol; reads go through the `Parallax` handle's
  per-entity accessor. The running example
  `Order where orderId == 42 and items.sku in ['A','B']` is spelled:

  ```ts
  px.orders.find(
    Order.id.eq(42).and(Order.lineItems.exists(item => item.sku.in(["A", "B"]))),
  );
  ```

- **Result types.** `find` always returns a `ParallaxList` (an async,
  operation-backed list per `M5`), which may resolve to zero, one, or many
  objects. Single-object access is spelled through `ParallaxList` helpers —
  `first` / `firstOrNull` / `single` / `singleOrNull` — where `first`/`single`
  throw `ParallaxNotFoundError` when empty and `single` throws
  `ParallaxTooManyResultsError` for more than one result.
- **`group` operator surface (`M2`).** Precedence uses **postfix** `.group()`
  (`a.or(b).group().and(c)`); boolean chaining is left-associative. This
  serializes to the canonical `group` node.
- **Deep-fetch spelling (`M4`).** The eager-fetch navigation set is declared
  with the `includes` option, whose values are generated relationship paths
  (`includes: [Order.customer, Order.lineItems.product]`); longer paths imply
  their prefixes.
- **Aggregation spelling (`M2` sub-area).** Reserved for `project(...)`
  (`groupBy` / aggregate functions / `having`), which returns plain data rather
  than managed objects. Projection and aggregation are **deferred from V1**
  (recorded here so the surface choice is not re-opened).

This document adds no claim that contradicts the overview; it only restates the
recorded choices.

## 2. Metadata / model input format (DQ5, DQ6)

**ANSWERED — see [TS-0055](../docs/adr/0055-metamodel-introspection-api-has-generic-and-typed-layers.md),
[TS-0056](../docs/adr/0056-one-canonical-serde-shared-by-metamodel-and-operations.md),
[TS-0057](../docs/adr/0057-serde-states-roundtrip-contract-and-names-libraries-nonbindingly.md).**
The metamodel (`M1`) is one artifact wearing two hats — an introspectable runtime
protocol and a serializable document — and this section specifies both hats so an
implementer can build the metamodel layer without inferring its shape from
`m1-metamodel.md`.

### 2.1 Primary authoring format

The authoring format is **descriptor-first**, exactly as
[`00-overview.md` §2 Metadata And Generation](00-overview.md#2-metadata-and-generation):
the source of truth is the canonical Parallax YAML/JSON descriptor set — the same
serialized metamodel the compatibility corpus uses — and a descriptor validates
against [`metamodel.schema.json`](../../../core/schemas/metamodel.schema.json). A
descriptor is either a single `entity` or an `entities` array (≥1 entity, so
relationships can name siblings). The typed entity symbols and the generic reader
below are both derived from that one descriptor; decorators/builders may be added
later as authoring conveniences but the serialized descriptor stays the backbone.

### 2.2 Introspection API (the `RelatedFinder` / `ReladomoClassMetaData` analogue)

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
types**, so every property in a descriptor is reachable from §2 alone:

| Element type | Reader shape | Fields (← schema) |
|---|---|---|
| `entity` | `EntityMetadata` | `name`, `table`, `namespace?`, `mutability`, `temporal`, `attributes`, `asOfAttributes`, `relationships`, `indices`, `valueObjects`, `inheritance?`; plus derived `primaryKeyAttributes`, `attributeByName(name)`, `relationshipByName(name)`, `isTemporal` |
| `attribute` | `AttributeMeta` | `name`, `type` (M0 neutral type, incl. `decimal(p,s)`), `column`, `primaryKey`, `nullable`, `maxLength?`, `readOnly`, `optimisticLocking`, `pkGenerator?`, `default?` |
| `relationship` | `RelationshipMeta` | `name`, `relatedEntity`, `cardinality` (`one-to-one`/`many-to-one`/`one-to-many`/`many-to-many`), `join`, `reverseName?`, `dependent`, `foreignKey?`, `orderBy?` (`{ attr, direction }[]`) |
| `index` | `IndexMeta` | `name`, `attributes` (ordered attribute names), `unique` |
| `asOfAttribute` | `AsOfAttributeMeta` | `name`, `fromColumn`, `toColumn`, `axis` (`processing`/`business`), `toIsInclusive`, `infinity` (`"infinity"`), `default` (`"now"`) |
| `valueObject` | `ValueObjectMeta` | `name`, `type` (logical struct name), `column` (single JSONB column), `mapping` (`"jsonb"`), `nullable` |
| `inheritance` | `InheritanceMeta` | `strategy` (`table-per-hierarchy`/`table-per-leaf`), `role` (`root`/`subtype`), `parent?`, `discriminator?` (`{ column }`), `discriminatorValue?` |
| `pkGenerator` | `PkGeneratorMeta` | `strategy` (`none`/`max`/`sequence`); for `sequence`: `sequenceName?`, `batchSize?`, `initialValue?`, `incrementSize?` (the bare-enum form normalizes to `{ strategy }`) |

Defaulting follows the schema: readers surface the schema defaults
(`mutability: "read-only"`, `temporal: "non-temporal"`, `primaryKey: false`,
`nullable: false`, `readOnly: false`, `optimisticLocking: false`,
`dependent: false`, `unique: false`, `toIsInclusive: false`,
`mapping: "jsonb"`, `nullable: false`) when a field is omitted, so the typed and
generic layers agree on every value. This mirrors the Python harness's `Entity` /
`Model` accessors, which are the concrete generic reader over the raw parsed
descriptor.

### 2.3 Serde module

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

## 3. Transaction-block demarcation (M8)

**ANSWERED — see
[`00-overview.md` §8 Transactions And Writes](00-overview.md#8-transactions-and-writes)
for the full surface.** Summary of the recorded choices:

- **Demarcation construct.** A **closure**: `await px.transaction(async tx =>
  { … })`. Writes are available only through `tx`; reads may use `px`.
  Commit-on-success: `transaction` returns the callback's resolved value after
  the unit of work flushes and commits. Rollback-on-exception: if the callback
  throws, rejects, or commit fails, the transaction rolls back and the returned
  promise rejects. A `ParallaxTransaction` is invalid after its callback
  completes.
- **Nested / re-entrant transactions.** Nested transactions **join** the active
  transaction. There are no savepoints in V1; an inner failure rolls back the
  enclosing transaction.
- **Unit-of-work surfacing.** There is **no public `flush` API** in V1. The
  runtime flushes at commit and uses unit-of-work state for read-your-writes
  behavior.

## 4. Test-double integration (M12, DQ15)

- **(decide and record)** Test runner and how a suite run discovers and executes
  `core/compatibility/cases/**`.
- **(decide and record)** Provisioning mechanism (Testcontainers vs. embedded
  binary) behind the database provider seam.
- **(decide and record)** Which dialects this language runs in CI and how the
  per-dialect golden SQL is selected.

## 5. Codegen-or-not (DQ5)

**ANSWERED — see
[`00-overview.md` §2 Metadata And Generation](00-overview.md#2-metadata-and-generation)
and [§3 CLI](00-overview.md#3-cli) for the full surface.** Summary of the
recorded choices:

- **Technique.** TypeScript V1 uses **codegen**. It is descriptor-first: the
  source of truth is the canonical Parallax YAML/JSON descriptor set (the same
  serialized metamodel the compatibility corpus uses), and the typed entity
  symbols, domain types, entity input types, snapshot types, and operation
  accessors are generated from it. Codegen is chosen over runtime
  reflection/proxies so the typed finder/object surface is statically checkable
  and matches the generated import barrel.
- **Generator entry point and inputs.** The `parallax generate` CLI command
  materializes generated output from the descriptors named in the generator
  config's `descriptors` key. `parallax generate --check` validates descriptors,
  generator configuration, and code generation.
- **Where generated artifacts live / regeneration.** Generated output is derived
  code, gitignored by default, written to `./.parallax/generated` (outside
  `src/`), and regenerated during install, build, and CI. Applications import it
  through the package-local `#parallax` alias.

## 6. Collection idioms (M5)

**ANSWERED — see
[`00-overview.md` §6 ParallaxList](00-overview.md#6-parallaxlist) for the full
surface.** Summary of the recorded choices:

- **Concrete collection type.** A list result is a `ParallaxList<T>`: an async,
  operation-backed result collection. It implements async iteration and resolves
  its backing operation (`M5`) on first object-returning access — laziness and
  query-backing are surfaced by deferring the fetch until results are read.
  `count` / `isEmpty` / `notEmpty` may answer with optimized SQL while
  unresolved without marking the list resolved.
- **Iteration / indexing / bulk-operation ergonomics.** `ParallaxList` exposes
  read helpers (`toArray`, `toSnapshots`, `first`, `firstOrNull`, `single`,
  `singleOrNull`, `count`, `isEmpty`, `notEmpty`) and is async-iterable. It does
  **not** emulate arrays: no trapping of `length`, numeric indexing, or
  synchronous iteration. Set-based `update` / `delete` accept an unresolved
  `ParallaxList` as a bulk target.

## 7. Build-time dependency enforcement (DQ3, dependency-graph)

- **(decide and record)** The enforcement tool and its config.
- **(decide and record)** The mapping from the core modules (`M0`–`M13`) onto
  this language's packages/modules, and the contract that encodes the legal edges
  (the same DAG as `dependency-graph.md`).

## 8. Optional optimized data structures (M13, DQ10)

- **(decide and record, optional)** Whether to use open-addressing map/set
  analogues (`UnifiedMap` / `UnifiedSet`) for the identity / query caches.
- **(decide and record, optional)** Whether to use a key-derived hashing
  analogue (`HashingStrategy`) to index domain objects by a derived key without
  allocating wrapper key objects.
- **(decide and record, optional)** Any language-specific result-interchange
  technique.

## 9. Per-language performance targets (M13, DQ10)

- **(decide and record)** Wall-time targets (`p50` / `p95`) per benchmark
  workload family.
- **(decide and record)** Memory targets (peak / steady resident set).
- **(decide and record)** Confirm the implementation honors the fixtures'
  `expectRoundTrips` invariant (a deep fetch is `1 + levels`, never N+1).

## Template Coverage Appendix

This table maps every `language-spec-template.md` section §1–§9 to its answer
location and an explicit status. `ANSWERED` rows that cross-reference
`00-overview.md` are restated above; gap-section rows are filled in this
document. Rows marked `PENDING` are completed by later phases of this spec's
authoring and carry no `(decide and record)` debt at completion.

| Template section | Status | Answer location | ADRs |
|---|---|---|---|
| §1 API surface | ANSWERED | [`00-overview.md` §5](00-overview.md#5-query-api) (with §1, §6, §9); restated in [§1](#1-api-surface-non-normative--dq3) | — |
| §2 Metadata / introspection + serde | ANSWERED | [§2](#2-metadata--model-input-format-dq5-dq6) | [TS-0055](../docs/adr/0055-metamodel-introspection-api-has-generic-and-typed-layers.md), [TS-0056](../docs/adr/0056-one-canonical-serde-shared-by-metamodel-and-operations.md), [TS-0057](../docs/adr/0057-serde-states-roundtrip-contract-and-names-libraries-nonbindingly.md) |
| §3 Transaction-block demarcation | ANSWERED | [`00-overview.md` §8](00-overview.md#8-transactions-and-writes); restated in [§3](#3-transaction-block-demarcation-m8) | — |
| §4 Test-double integration | PENDING | [§4](#4-test-double-integration-m12-dq15) | — |
| §5 Codegen-or-not | ANSWERED | [`00-overview.md` §2](00-overview.md#2-metadata-and-generation), [§3](00-overview.md#3-cli); restated in [§5](#5-codegen-or-not-dq5) | — |
| §6 Collection idioms | ANSWERED | [`00-overview.md` §6](00-overview.md#6-parallaxlist); restated in [§6](#6-collection-idioms-m5) | — |
| §7 Build-time dependency enforcement | PENDING | [§7](#7-build-time-dependency-enforcement-dq3-dependency-graph) | — |
| §8 Optional optimized data structures | PENDING | [§8](#8-optional-optimized-data-structures-m13-dq10) | — |
| §9 Per-language performance targets | PENDING | [§9](#9-per-language-performance-targets-m13-dq10) | — |
