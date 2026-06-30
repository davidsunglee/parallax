# TypeScript Language Spec

This document defines the TypeScript developer-facing surface for Parallax. The
language-neutral contract remains the core specification in
[`../../../core/spec`](../../../core/spec); this file records the TypeScript
choices the core deliberately leaves open.

This spec describes the first TypeScript API shape. TypeScript V1 adopts the
canonical `first-implementation-mvp` conformance slice, which is smaller than
the core MVP tier: it claims only cases tagged for that slice. Some core
capabilities are therefore recorded here as future TypeScript surface decisions
but deferred from the first conformance claim. A deferred capability is not
removed from Parallax; it is simply not claimed by the TypeScript conformance
adapter until the corresponding compatibility slice passes.

## 1. Generated Import Surface

Applications import the generated API through the package-local alias
`#parallax`. The physical generated output path is hidden behind that alias.

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

The generated barrel exports:

- `parallax`
- `Parallax`
- `ParallaxTransaction`
- generated entity symbol values, such as `Order`
- managed object types, such as `type Order`
- entity input validators and types, such as `OrderInput` and
  `type OrderInput`
- snapshot types, such as `type OrderSnapshot`
- public runtime types, such as `ParallaxList`, `ParallaxDecimal`, and
  `ParallaxJsonValue`
- public error classes rooted at `ParallaxError`

TypeScript's value/type namespace overlap is accepted for ergonomics. `Order` is
both the entity symbol value used in expressions and `type Order` is the managed
object type. Documentation may alias the type as `OrderObject` when clarity
matters.

TypeScript generates only artifacts derivable from the canonical descriptor. The
descriptor has no enum element and does not describe value-object fields, so
TypeScript does not generate enum types or structured value-object interfaces.
When value-object descriptors are claimed by a later compatibility slice, value
objects are exposed as `ParallaxJsonValue` / `null` according to their
nullability, and nested value-object predicates use untyped string paths after
the declared value-object name.

## 2. Metadata And Generation

TypeScript V1 is descriptor-first. The source of truth is the canonical
Parallax YAML/JSON descriptor set. Decorators and TypeScript schema builders may
be added later as descriptor-authoring conveniences, but V1 starts from the same
serialized metamodel used by the compatibility corpus.

Generator config uses `descriptors`, not `specs` or `models`:

```ts
import { defineParallaxConfig } from "@parallax/typescript/config";

export default defineParallaxConfig({
  descriptors: ["./parallax/**/*.yaml"],
  output: "./.parallax/generated",
  importAlias: "#parallax",
});
```

Generated output is derived code. It is gitignored by default and regenerated
during install, build, and CI. The default output directory is
`./.parallax/generated`, outside `src/`, so generated implementation detail does
not look like user-owned source.

Generated files are inspectable but not editable. Customization belongs in
descriptors, generator configuration, runtime adapters, and application-owned
domain functions.

## 3. CLI

The TypeScript package provides the generated-API CLI and the V1 claimed
conformance commands:

```text
parallax init
parallax generate
parallax generate --check
parallax-conformance describe
parallax-conformance compile --case <case.yaml> --dialect <dialect>
parallax-conformance run --case <case.yaml> --dialect <dialect>
```

`parallax init` is a conservative setup assistant. It may create or update:

- `parallax.config.ts`
- the gitignore entry for generated output
- explicit package scripts
- resolver configuration for `#parallax`

It supports `--dry-run` to preview changes and `--force` to overwrite
conflicting content. Without `--force`, conflicting setup produces accumulated
validation or configuration issues.

By default, `init` adds explicit scripts only:

```json
{
  "scripts": {
    "parallax:generate": "parallax generate",
    "parallax:check": "parallax generate --check"
  }
}
```

Lifecycle scripts such as `prebuild` and `pretest` are opt-in through a flag such
as `--wire-lifecycle`.

`parallax generate` materializes the generated output. `parallax generate
--check` validates descriptors, generator configuration, and code generation,
then fails if generation would fail. Since generated files are not committed,
`--check` is not a git drift check.

Conformance is exposed through the separate `parallax-conformance` CLI adapter,
not through the generated `#parallax` API. Each conformance command writes the
JSON envelope required by
[`../../../core/spec/conformance-adapter-contract.md`](../../../core/spec/conformance-adapter-contract.md)
to stdout.

The M13 benchmark command is a post-slice conformance command:

```text
parallax-conformance benchmark --benchmark <benchmark.yaml> --dialect <dialect>
```

TypeScript V1 may document that command shape, but it does not claim
`benchmark` in `parallax-conformance describe` until the M13 slice is
implemented.

## 4. Parallax Handle

The generated `parallax(...)` factory creates the configured `Parallax` handle:

```ts
const px: Parallax = parallax({
  database,
  clock,
});
```

`Parallax` is the application-side handle into the generated API. It is not a
raw database connection, database client, or transaction/session. It binds the
generated metamodel, database adapter, clock strategy, read API, transaction
API, and runtime behavior behind one entry point.

Application code conventionally names the handle `px`.

## 5. Query API

TypeScript uses one generated fluent expression DSL for predicates,
relationships, assignments, and sort keys. There is no second Prisma-style
object filter language.

`find` is the only V1 read operation that returns managed domain objects. It
always returns a `ParallaxList`, which may resolve to zero, one, or many objects:

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

Calling `find()` without a predicate is shorthand for `find(Entity.all())`.
Generated entity symbols also expose `none()` for dynamic predicate
construction.

### Predicates

Predicate methods use compact TypeScript-friendly names:

- `eq`
- `notEq`
- `gt`
- `gte`
- `lt`
- `lte`
- `isNull`
- `isNotNull`
- `in`
- `notIn`

`eq(null)` and `notEq(null)` are rejected; callers use `isNull()` and
`isNotNull()`. Empty membership predicates normalize before serialization:
`attr.in([])` becomes `none`, and `attr.notIn([])` becomes `all`.

String predicates use options for case-insensitive matching rather than separate
method names:

```ts
Order.name.startsWith("acme", { caseInsensitive: true });
```

Boolean chaining with `.and(...)` and `.or(...)` is left-associative. Explicit
precedence is expressed with postfix `.group()`:

```ts
Order.status.eq("Processing")
  .and(Order.priority.eq("High").or(Order.customer.region.eq("NA")).group());
```

Predicates expose postfix `.not()`. To-many relationships expose explicit
`notExists`.

### Relationship Navigation In Queries

To-one relationships support direct path navigation:

```ts
Order.customer.region.eq("NA");
```

To-many relationships require an explicit quantifier:

```ts
Order.lineItems.exists(item => item.quantity.gt(2));
Order.lineItems.notExists(item => item.cancelled.eq(true));
```

### Includes

Eager relationship loading uses the `includes` option. Include values are
generated relationship paths:

```ts
px.orders.find(Order.all(), {
  includes: [Order.customer, Order.lineItems.product],
});
```

Longer include paths imply their prefixes. `Order.lineItems.product` implies
`Order.lineItems`.

Navigating a relationship that was not included may lazily resolve it. Includes
optimize eager loading by issuing batched secondary fetches per relationship hop,
not by turning every to-one into a left join.

### Ordering

Ordering uses generated sort keys:

```ts
await px.orders.find(Order.status.eq("processing"), {
  orderBy: [Order.createdAt.desc(), Order.id.asc()],
  limit: 50,
});
```

Sort keys are query expressions in V1. They are not JavaScript comparators.

### Projection And Aggregation

`find` never returns partial managed objects. Future selective retrieval and
grouped aggregate reads use `project(...)`, which returns plain data rather than
managed objects:

```ts
const summaries = await px.orders.project({
  where: Order.status.eq("Processing"),
  groupBy: [Order.customerId],
  select: {
    customerId: Order.customerId,
    orderCount: Order.id.count(),
    totalAmount: Order.totalAmount.sum(),
  },
  having: agg => agg.orderCount.gt(10),
  orderBy: agg => [agg.totalAmount.desc()],
});
```

Projection and aggregation are deferred from V1.

### In-Memory Expression Reuse

V1 does not make Parallax predicates usable as native JavaScript `Array.filter`
callbacks, and it does not make sort keys usable as native `Array.sort` or
`Array.toSorted` comparators. In-memory expression reuse is deferred until
relationship traversal can work without a scalar-only split or hidden N+1
behavior.

## 6. ParallaxList

`ParallaxList<T>` is an async, operation-backed result collection. It implements
async iteration and resolves its backing operation on first object-returning
access.

Helpers:

- `toArray`
- `toSnapshots`
- `first`
- `firstOrNull`
- `single`
- `singleOrNull`
- `count`
- `isEmpty`
- `notEmpty`

`count`, `isEmpty`, and `notEmpty` may use optimized SQL while unresolved and do
not mark the list resolved. Once resolved, they answer from the materialized
in-memory result.

Object-returning helpers resolve the list. `first` throws
`ParallaxNotFoundError` when empty. `single` throws `ParallaxNotFoundError` when
empty and `ParallaxTooManyResultsError` when more than one object exists. The
`OrNull` variants return `null` for empty lists and still throw
`ParallaxTooManyResultsError` for multiple results.

`ParallaxList` does not emulate arrays. It does not trap `length`, numeric
indexing, or synchronous iteration. Normal JavaScript behavior is acceptable for
those operations.

## 7. Relationships On Managed Objects

Relationships on managed objects use references and managed collections, not
Promise-valued properties and not plain arrays.

To-one relation references expose:

```ts
await order.customer.get();      // Customer | null
await order.customer.required(); // Customer or ParallaxNotFoundError
await order.customer.set(customer);
await order.customer.clear();
```

`set` and `clear` mutate the association and require an active transaction.

To-many relationship collections are async iterable and expose the same read
helpers as `ParallaxList`. V1 mutation support is limited to dependent
relationships:

```ts
await order.lineItems.add(input);
await order.lineItems.remove(item);
```

`add` accepts an entity input for a dependent relationship and creates a new
owned child. `remove` accepts a managed child from a dependent relationship and
deletes or terminates it. Adding existing child objects, reparenting, and
non-dependent link/unlink APIs are deferred. V1 callers change non-dependent
associations through explicit foreign-key updates or explicit join-entity writes.

## 8. Transactions And Writes

All writes require an explicit transaction. Reads may use `px`; writes are
available only through `tx`.

```ts
await px.transaction(async tx => {
  const order = await tx.orders.create(input);

  await tx.orders.update(Order.id.eq(order.id), {
    set: [Order.status.set("Processing")],
  });

  await tx.orders.delete(Order.id.eq(order.id));
});
```

`transaction` returns the callback's resolved value after the unit of work
flushes and commits. If the callback throws, rejects, or commit fails, the
transaction rolls back and the returned promise rejects. A `ParallaxTransaction`
is invalid after its callback completes.

Nested transactions join the active transaction. There are no savepoints in V1;
an inner failure rolls back the enclosing transaction.

There is no public `flush` API in V1. The runtime flushes at commit and uses
unit-of-work state for read-your-writes behavior.

Reads performed through `ParallaxTransaction` use the core in-transaction
read-lock behavior by default. V1 does not expose `lock: false`.

Set-based `update` and `delete` accept either a predicate or an unresolved
`ParallaxList` target:

```ts
await tx.customers.update(Customer.customerId.eq(10), {
  set: [
    Customer.name.set("Acme Corp"),
    Customer.status.set("Active"),
  ],
});
```

Updates use explicit assignment arrays, not partial objects. Set-based writes
return result objects with at least `affectedRows`.

Managed-object writes that expect exactly one versioned row and affect zero rows
throw `ParallaxOptimisticLockError`. Set-based writes return `{ affectedRows }`
unless a later API adds explicit expected-count or conflict-policy options.
Optimistic lock conflicts are caller-driven; the runtime does not automatically
retry them.

## 9. Entity Inputs And Snapshots

`OrderInput` is the generated input validation namespace and type for data
accepted by `create`:

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

`parse` returns a typed entity input or throws `ParallaxValidationError`.
`safeParse` returns:

```ts
type ParallaxParseResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: ParallaxValidationError };
```

Entity inputs are distinct from snapshots. `OrderInput` is what Parallax accepts
for constructing a new managed object. `OrderSnapshot` is what Parallax emits
from managed objects for serialization.

`OrderInput` includes only create-accepted data: writable scalar attributes,
writable value objects, app-assigned primary keys when configured, foreign-key
attributes when exposed as writable attributes, and nested dependent
relationships only when explicitly allowed.

It excludes database-generated IDs, read-only attributes, optimistic lock/version
fields, processing timestamps, and server-owned fields.

Create consumes nested relationship data only when listed in `relationships`.
Payload relationship data listed in `ignoreRelationships` is accepted but
ignored. Any remaining nested relationship data is rejected.

## 10. JSON Serialization

Managed objects are not plain old JavaScript objects. `JSON.stringify` over a
managed object is scalar-only and synchronous; it does not lazy-load
relationships.

Async snapshot APIs produce plain JSON-serializable domain snapshots:

```ts
const snapshot = await order.toSnapshot({
  attributes: [Order.id, Order.customer.address.zipCode],
  relationships: [Order.customer, Order.lineItems],
});

const snapshots = await orders.toSnapshots({
  relationships: [Order.lineItems.product],
});
```

Snapshot output includes all scalar and value-object attributes by default and no
relationships by default. `attributes` and `excludeAttributes` are mutually
exclusive. Relationship paths are opt-in. There is no `excludeRelationships`
option because omitted relationships are already excluded.

List-level snapshots should batch-load requested relationships like includes, to
avoid N+1 behavior.

Reladomo-style detached objects are not part of TypeScript V1. Snapshots are the
detached data surface.

## 11. Temporal API

TypeScript timestamps use `Temporal.Instant`, constrained to the Parallax core
microsecond boundary. Values with non-zero sub-microsecond precision are
rejected.

Temporal reads use core axis names:

```ts
px.positions.find(predicate, {
  asOf: {
    processing: processingInstant,
    business: businessInstant,
  },
});

px.positions.find(predicate, {
  range: {
    business: { start, end },
  },
});

px.positions.find(predicate, {
  history: ["business"],
});
```

`asOf`, `range`, and `history` are mutually exclusive per axis. Ranges use
inclusive `start` and exclusive `end`.

Processing instants come from a `Clock Strategy` configured when `Parallax` is
created. Application code does not pass processing instants to individual
transactions or operations.

Temporal writes use explicit verbs. The first TypeScript conformance slice
claims only non-temporal writes and audit-only processing-temporal writes:

- ordinary `update` performs entity-normal semantics: in-place for non-temporal,
  close-and-chain for temporal
- `terminate` closes the current temporal row

The business-axis and full-bitemporal write surface is post-slice:

- `createUntil`, `updateUntil`, and `terminateUntil` are bounded business-window
  operations; `createUntil` maps to the core `insertUntil` mutation
- bounded temporal write options use `business: { start, end }`

Users never supply processing timestamps for writes.

## 12. Errors And Validation

The public TypeScript error hierarchy is rooted at `ParallaxError`.

Initial public classes:

- `ParallaxError`
- `ParallaxConfigurationError`
- `ParallaxValidationError`
- `ParallaxNotFoundError`
- `ParallaxTooManyResultsError`
- `ParallaxTransactionError`
- `ParallaxOptimisticLockError`

Errors expose stable machine-readable `code` strings. Messages are
human-readable diagnostics and may evolve.

`ParallaxValidationError` accumulates validation issues rather than failing
fast. Each issue carries:

```ts
type ParallaxValidationIssue = {
  code: string;
  path: readonly (string | number)[];
  pointer: string;
  message: string;
  details?: Record<string, unknown>;
};
```

Issue `path` is the programmatic path array. `pointer` is the JSON Pointer string
for display, logs, and interchange. Validation errors use two levels of codes:
the top-level error code, such as `PARALLAX_VALIDATION_FAILED`, and per-issue
codes, such as `REQUIRED_ATTRIBUTE_MISSING`.

## 13. Domain Behavior

Generated domain objects are managed data and relationship surfaces, not user
extension points. Application-specific behavior lives in ordinary TypeScript
modules as standalone domain functions:

```ts
export async function orderTotal(order: Order): Promise<Money> {
  const items = await order.lineItems.toArray();
  return sum(items.map(item => item.extendedPrice));
}
```

Users should not edit generated files or subclass generated objects.

## 14. Conformance And Capability Claims

The generated API does not expose runtime capability metadata. Application code
relies on generated types, package versions, documentation, and conformance
results, not runtime capability branching.

The conformance adapter reports claimed modules through `parallax-conformance
describe`. TypeScript V1 claims the M8 transaction and unit-of-work cases tagged
`first-implementation-mvp`, including read-your-own-writes, but it does not yet
claim the M8 identity-cache and query-cache scenario slice. Until that cache
slice is claimed, repeated reads of the same primary key are not guaranteed to
return the same JavaScript object instance. A resolved `ParallaxList` remains
stable for its own materialized result, but that is not the full core
identity-cache guarantee.

The post-V1 target remains the core `M8` contract: within a cache scope, reads of
the same primary key resolve to the same logical managed object, repeated equal
operations are served from the query cache, and cache hits preserve identity.

## 15. Tooling

Repository-level TypeScript and Node tooling uses pnpm. Generated project setup
should prefer pnpm scripts and `pnpm exec`.

The implementation should enforce module dependency boundaries mechanically with
a TypeScript ecosystem tool such as `dependency-cruiser` or
`eslint-plugin-boundaries`, mapping implementation modules to the core
dependency graph in
[`../../../core/spec/dependency-graph.md`](../../../core/spec/dependency-graph.md).
Implementation source lives under `languages/typescript/packages/*`; the
surrounding `languages/typescript/spec` and `languages/typescript/docs`
directories are documentation. The non-numbered `@parallax/typescript` package is
the composition package for the CLI, generator config, public runtime facade, and
generated-barrel support.

The TypeScript conformance test runner should use the shared compatibility
corpus and the `parallax-conformance` adapter. Database-backed test provisioning
should use Testcontainers for Node unless a later implementation note records a
better equivalent seam.

## 16. Deferred From V1

The following are intentionally deferred from the first TypeScript conformance
slice:

- projection queries via `project(...)`
- grouped aggregate projection
- in-memory predicate/comparator reuse
- non-dependent `link` / `unlink`
- adding existing children and reparenting through collections
- full `M8` identity cache and query cache conformance
- PK-generation compatibility cases
- value-object compatibility cases
- inheritance compatibility cases
- detached object lifecycle
- M11 database error-code classification cases
- bounded business-window and bitemporal rectangle-split writes
- MariaDB provider and dialect conformance
- M13 benchmark command and numeric performance targets
- M14 cross-process cache coherence
- public flush
- runtime capability metadata
- transaction read lock disabling

Deferred TypeScript API does not weaken the core spec. The implementation must
not claim a core module, dialect, command, case tag, or case shape until the
corresponding compatibility slice passes.
