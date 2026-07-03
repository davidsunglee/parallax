<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Locking

The correctness strategy is a per-unit-of-work mode: `px.transaction(body, { concurrency })`. In the default `locking` mode, in-transaction reads take a shared row lock **automatically** — you write no locking SQL — and a versioned `update` advances the version with no gate. In `optimistic` mode reads take no lock and a versioned `update` gates on the version the unit of work observed. Version values are **framework-owned**: you read the object, then `update` — never passing a raw version. A stale gate throws `ParallaxOptimisticLockError`, which you catch and retry after re-reading the fresh row; a no-op `update` (no changed attribute) issues no DML.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/locking.api-conformance.test.ts`).

## 0603: a transaction-scoped read takes the automatic shared lock and returns the row

```ts
const account = await f.px.transaction((tx) =>
tx.entity("Account").find(Account.id.eq(2)).single(),
```

## 0609: a versioned update that changes no attribute issues no DML

```ts
const observed = await f.px.transaction(async (tx) => {
const accounts = tx.entity("Account");
await accounts.find(Account.id.eq(2)).single();
const result = await accounts.update(accountPk(2), { set: [] });
return accounts.find(Account.id.eq(2)).toArray();
```

## 0611: a locking-mode update advances the version with no gate

```ts
const result = await f.px.transaction(async (tx) => {
const accounts = tx.entity("Account");
await accounts.find(Account.id.eq(2)).single();
return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
```

## 0703: a stale-version update conflicts (affects 0 rows) — the row is unchanged

```ts
await f.px.transaction(
    const accounts = tx.entity("Account");
    await accounts.find(Account.id.eq(2)).single();
    await accounts.update(accountPk(2), { set: [Account.balance.set(dec("250.00"))] });
```

## 0704: an update on the fresh version succeeds (affects 1 row)

```ts
const result = await f.px.transaction(
  const accounts = tx.entity("Account");
  await accounts.find(Account.id.eq(2)).single();
  return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
```

## 0708: a retry re-reads the fresh version after the conflict and succeeds

```ts
const result = await f.px.transaction(
  const accounts = tx.entity("Account");
  await accounts.find(Account.id.eq(2)).single(); // observes version 1
    return await accounts.update(accountPk(2), {
    await accounts.find(Account.id.eq(2)).single();
    return accounts.update(accountPk(2), { set: [Account.balance.set(dec("250.00"))] });
* `px.transaction` holds the connection would deadlock.
```
