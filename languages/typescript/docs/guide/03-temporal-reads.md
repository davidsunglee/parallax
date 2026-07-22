<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Temporal reads

Temporal reads pin one or both axes with `{ asOf }`, a `range`, or full `history`. An omitted dimension defaults to *Latest* (the current row); Valid Time is applied outside Transaction Time. You never write the interval predicates — the engine injects them. Each `find` below is a real, tested case.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/temporal.api-conformance.test.ts`).

## m-navigate-018-exists-temporal-hop

```ts
buildFindOperation(Policy.coverages.exists(Coverage.amount.gte(600.0)), {
temporal: { asOf: { transactionTime: "latest", validTime: "latest" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-navigate-023-exists-temporal-hop-defaulted

```ts
Policy.coverages.exists(Coverage.amount.gte(600.0))
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-001-as-of-latest-defaulted

```ts
buildFindOperation(all())
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-002-as-of-latest-explicit

```ts
buildFindOperation(all(), {
temporal: { asOf: { transactionTime: "latest" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-003-as-of-past-instant

```ts
buildFindOperation(all(), {
temporal: { asOf: { transactionTime: at("2024-04-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-004-history

```ts
buildFindOperation(new Predicate({ eq: { attr: "Balance.id", value: 1 } }), {
temporal: { history: ["transactionTime"]
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-005-as-of-latest-with-predicate

```ts
buildFindOperation(Balance.acctNum.eq("A"), {
temporal: { asOf: { transactionTime: "latest" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-006-as-of-range

```ts
buildFindOperation(all(), {
temporal: {
  range: {
    transactionTime: {
      start: at("2024-06-15T00:00:00+00:00"),
      end: at("2024-07-01T00:00:00+00:00")
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-007-as-of-boundary-exclusive

```ts
buildFindOperation(all(), {
temporal: { asOf: { transactionTime: at("2024-06-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-008-as-of-boundary-inclusive

```ts
buildFindOperation(all(), {
temporal: { asOf: { transactionTime: at("2024-06-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-013-bitemporal-as-of-latest-both-dimensions

```ts
buildFindOperation(all(), {
temporal: { asOf: { transactionTime: "latest", validTime: "latest" }
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-014-bitemporal-valid-time-past-transaction-time-latest

```ts
buildFindOperation(all(), {
temporal: {
  asOf: { transactionTime: "latest", validTime: at("2024-03-01T00:00:00+00:00")
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-015-bitemporal-both-axes-past

```ts
buildFindOperation(all(), {
temporal: {
  asOf: {
    transactionTime: at("2024-02-01T00:00:00+00:00"),
    validTime: at("2024-03-01T00:00:00+00:00")
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-016-bitemporal-history

```ts
buildFindOperation(new Predicate({ eq: { attr: "Position.id", value: 1 } }), {
temporal: { history: ["transactionTime", "validTime"]
const rows = await px.entity(entity).find(base, options).toArray();
```

## m-temporal-read-017-bitemporal-omitted-transaction-time-default

```ts
buildFindOperation(all(), {
temporal: { asOf: { validTime: at("2024-03-01T00:00:00+00:00") }
const rows = await px.entity(entity).find(base, options).toArray();
```
