<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Deep fetch (eager relationships)

`find(..., { includes })` eager-loads relationships in **one bulk query per level** (`1 + L` round trips, never N+1). Each parent is decorated with its children under the relationship's name; the children are managed objects too. Each `find` below is a real, tested case (shown as the operation it builds).

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/deep-fetch.api-conformance.test.ts`).

## 0310-deep-fetch-to-one

```ts
buildFindOperation(all(), { includes: [path("OrderItem.order")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0311-deep-fetch-to-many

```ts
buildFindOperation(all(), { includes: [path("Order.items")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0312-deep-fetch-multi-hop

```ts
buildFindOperation(inList("Order.id", [1, 42]), {
includes: [path("Order.items", "OrderItem.statuses")]
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0313-deep-fetch-two-paths

```ts
buildFindOperation(all(), { includes: [path("Order.items"), path("Order.statuses")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0314-deep-fetch-null-to-one

```ts
buildFindOperation(all(), { includes: [path("OrderStatus.orderItem")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0315-deep-fetch-empty-root

```ts
buildFindOperation(eq("Order.id", 999), {
includes: [path("Order.items", "OrderItem.statuses")]
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0316-deep-fetch-shared-prefix

```ts
buildFindOperation(all(), {
includes: [path("Order.items"), path("Order.items", "OrderItem.statuses")]
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0318-deep-fetch-empty-intermediate

```ts
buildFindOperation(eq("Order.id", 4), {
includes: [path("Order.items", "OrderItem.statuses")]
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0319-deep-fetch-ordered-items-desc

```ts
buildFindOperation(eq("Order.id", 1), { includes: [path("Order.items")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0320-deep-fetch-one-to-one

```ts
buildFindOperation(all(), { includes: [path("Person.passport")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0322-deep-fetch-ordered-tags-multikey

```ts
buildFindOperation(eq("Order.id", 1), { includes: [path("Order.tags")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0323-deep-fetch-ordered-nullable-nulls-last

```ts
buildFindOperation(inList("Order.id", [1, 42]), {
includes: [path("Order.itemsByShipDate")]
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0324-deepfetch-temporal-both-latest

```ts
buildFindOperation(all(), {
includes: [path("Policy.coverages")],
temporal: { asOf: { processing: "now", business: "now" }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0325-deepfetch-temporal-business-past

```ts
buildFindOperation(all(), {
includes: [path("Policy.coverages")],
temporal: { asOf: { processing: "now", business: at("2024-03-01T00:00:00+00:00") }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0326-deepfetch-temporal-processing-past

```ts
buildFindOperation(all(), {
includes: [path("Policy.coverages")],
temporal: { asOf: { processing: at("2024-02-01T00:00:00+00:00"), business: "now" }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0327-deepfetch-temporal-both-past

```ts
buildFindOperation(all(), {
includes: [path("Policy.coverages")],
temporal: {
  asOf: {
    processing: at("2024-02-01T00:00:00+00:00"),
    business: at("2024-03-01T00:00:00+00:00")
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0328-deepfetch-temporal-multihop

```ts
buildFindOperation(all(), {
includes: [path("Policy.coverages", "Coverage.claims")],
temporal: { asOf: { processing: "now", business: "now" }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0329-deepfetch-temporal-to-one

```ts
buildFindOperation(all(), {
includes: [path("Coverage.policy")],
temporal: { asOf: { processing: "now", business: "now" }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0331-deepfetch-processing-only-latest

```ts
buildFindOperation(all(), {
includes: [path("Invoice.lines")],
temporal: { asOf: { processing: "now" }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0332-deepfetch-processing-only-instant

```ts
buildFindOperation(all(), {
includes: [path("Invoice.lines")],
temporal: { asOf: { processing: at("2024-02-01T00:00:00+00:00") }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0333-deepfetch-nontemporal-to-temporal

```ts
buildFindOperation(all(), { includes: [path("Tenant.leases")] })
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0334-deepfetch-temporal-to-nontemporal

```ts
buildFindOperation(all(), {
includes: [path("Lease.notes")],
temporal: { asOf: { processing: "now" }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```

## 0336-deepfetch-temporal-ordered-root

```ts
buildFindOperation(all(), {
includes: [path("Policy.coverages")],
orderBy: [new AttributeExpression("Policy.id").asc()],
limit: 1,
temporal: { asOf: { processing: "now", business: at("2024-03-01T00:00:00+00:00") }
const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);
```
