<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Temporal reads

Temporal reads pin one or both axes with `{ asOf }`, a `range`, or full `history`. An omitted axis defaults to *now* (the current row); the business axis is applied outside the processing axis. You never write the interval predicates — the engine injects them. Each `find` below is a real, tested case.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/temporal.api-conformance.test.ts`).

## m-navigate-018-exists-temporal-hop

```ts
buildFindOperation(Policy.coverages.exists(Coverage.amount.gte(600.0)), {
temporal: { asOf: { processing: "now", business: "now" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-navigate-023-exists-temporal-hop-defaulted

```ts
Policy.coverages.exists(Coverage.amount.gte(600.0))
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-001-as-of-now-defaulted

```ts
buildFindOperation(all())
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-002-as-of-now-explicit

```ts
buildFindOperation(all(), {
temporal: { asOf: { processing: "now" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-003-as-of-past-instant

```ts
buildFindOperation(all(), {
temporal: { asOf: { processing: at("2024-04-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-004-history

```ts
buildFindOperation(new Predicate({ eq: { attr: "Balance.id", value: 1 } }), {
temporal: { history: ["processing"]
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-005-as-of-now-with-predicate

```ts
buildFindOperation(Balance.acctNum.eq("A"), {
temporal: { asOf: { processing: "now" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-006-as-of-range

```ts
buildFindOperation(all(), {
temporal: {
  range: {
    processing: {
      start: at("2024-06-15T00:00:00+00:00"),
      end: at("2024-07-01T00:00:00+00:00")
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-007-as-of-boundary-exclusive

```ts
buildFindOperation(all(), {
temporal: { asOf: { processing: at("2024-06-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-008-as-of-boundary-inclusive

```ts
buildFindOperation(all(), {
temporal: { asOf: { processing: at("2024-06-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-013-bitemporal-as-of-now-both-axes

```ts
buildFindOperation(all(), {
temporal: { asOf: { processing: "now", business: "now" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-014-bitemporal-business-past-processing-now

```ts
buildFindOperation(all(), {
temporal: {
  asOf: { processing: "now", business: at("2024-03-01T00:00:00+00:00")
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-015-bitemporal-both-axes-past

```ts
buildFindOperation(all(), {
temporal: {
  asOf: {
    processing: at("2024-02-01T00:00:00+00:00"),
    business: at("2024-03-01T00:00:00+00:00")
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-016-bitemporal-history

```ts
buildFindOperation(new Predicate({ eq: { attr: "Position.id", value: 1 } }), {
temporal: { history: ["processing", "business"]
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-017-bitemporal-omitted-processing-default

```ts
buildFindOperation(all(), {
temporal: { asOf: { business: at("2024-03-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```
