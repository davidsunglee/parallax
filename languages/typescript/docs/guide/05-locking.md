<!-- AUTO-GENERATED from the showcase tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Locking

In-transaction reads take a shared row lock **automatically** — you write no locking SQL. Version-column optimistic locking is caller-driven: read the object (capturing its `version`), then `update` gates on that version; a concurrent change throws `ParallaxOptimisticLockError`, which you catch and retry on the fresh version.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/showcase/locking.showcase.test.ts`).

## 0603: a transaction-scoped read takes the automatic shared lock and returns the row

```ts
const account = await f.px.transaction((tx) =>
tx.entity("Account").find(Account.id.eq(2)).single(),
```

## 0703: a stale-version update conflicts (affects 0 rows) — the row is unchanged

```ts
await f.px.transaction(async (tx) => {
    .update(new Predicate({ eq: { attr: "Account.id", value: 2 } }), {
```

## 0704: an update on the fresh version succeeds (affects 1 row)

```ts
const result = await f.px.transaction((tx) =>
tx.entity("Account").update(new Predicate({ eq: { attr: "Account.id", value: 2 } }), {
```

## 0707: a version-only bump advances the version with no domain change

```ts
const result = await f.px.transaction((tx) =>
tx.entity("Account").update(new Predicate({ eq: { attr: "Account.id", value: 2 } }), {
```

## 0708: a retry re-reads the fresh version after the conflict and succeeds

```ts
const result = await f.px.transaction(async (tx) => {
    .update(pred, { set: [Account.balance.set(dec("250.00"))], expectedVersion: 1 });
  const fresh = await tx.entity(account).find(pred).single();
  return tx.entity(account).update(pred, {
```
