<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Locking

The correctness strategy is a per-unit-of-work mode: `px.transaction(body, { concurrency })`. In the default `locking` mode, in-transaction reads take a shared row lock **automatically** — you write no locking SQL — and a versioned `update` advances the version with no gate. In `optimistic` mode reads take no lock and a versioned `update` gates on the version the unit of work observed. Version values are **framework-owned**: you read the object, then `update` — never passing a raw version. A stale gate throws `ParallaxOptimisticLockError`, which you catch and retry after re-reading the fresh row; a no-op `update` (no changed attribute) issues no DML.

The boundary also offers **bounded automatic retry**: `px.transaction(body, { retries, retryOptimisticConflicts })`. On a retriable failure it rolls back, discards the unit of work's observed state, and re-executes the body against fresh state — up to `retries` re-executions (default 10; `0` disables). Transient database failures (deadlock / serialization) are retried automatically; an optimistic-lock conflict is retried only with `retryOptimisticConflicts: true`, in which case the re-executed body re-reads the fresh version and succeeds with **no caller retry code**. The loop-mechanics cases live in `boundary.api-conformance.test.ts`.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/locking.api-conformance.test.ts`).

## m-read-lock-001: a transaction-scoped read takes the automatic shared lock and returns the row

```ts
const account = await f.px.transaction((tx) =>
tx.entity("Account").find(Account.id.eq(2)).single(),
```

## a distinct/projection read in a locking transaction proceeds unlocked and returns rows

```ts
const rows = await f.px.transaction((tx) =>
tx.entity("Account").find(Account.id.eq(2), { distinct: true }).toArray(),
```

## m-read-lock-002: an object find inside a locking transaction returns the row (it takes the shared lock)

```ts
const account = await f.px.transaction(
(tx) => tx.entity("Account").find(Account.id.eq(2)).single(),
```

## m-read-lock-003: a projection read inside a locking transaction proceeds unlocked and returns rows

```ts
const rows = await f.px.transaction(
(tx) => tx.entity("Account").find(all(), { distinct: true }).toArray(),
```

## m-read-lock-004: a deep fetch inside a locking transaction locks every level and returns the graph

```ts
const rows = await f.px.transaction(
    .find(all(), { includes: [new NavigationPath(["OrderItem.order"])] })
    .toArray(),
```

## m-read-lock-005: reads inside an optimistic transaction take no lock and return rows

```ts
const account = await f.px.transaction(
(tx) => tx.entity("Account").find(Account.id.eq(2)).single(),
```

## m-opt-lock-001: a versioned update that changes no attribute issues no DML

```ts
const observed = await f.px.transaction(async (tx) => {
const accounts = tx.entity("Account");
await accounts.find(Account.id.eq(2)).single();
const result = await accounts.update(accountPk(2), { set: [] });
return accounts.find(Account.id.eq(2)).toArray();
```

## m-opt-lock-002: a locking-mode update advances the version with no gate

```ts
const result = await f.px.transaction(async (tx) => {
const accounts = tx.entity("Account");
await accounts.find(Account.id.eq(2)).single();
return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
```

## m-opt-lock-004: a versioned set-based update materializes into per-object version-advancing updates

```ts
const observed = await f.px.transaction(
  const accounts = tx.entity("Account");
  const result = await accounts.update(Account.balance.lt(200), {
  return accounts.find(Account.balance.lt(200)).toArray();
```

## m-opt-lock-003: a versioned set-based update materializes into per-object GATED updates

```ts
const observed = await f.px.transaction(
  const accounts = tx.entity("Account");
  const result = await accounts.update(Account.balance.lt(200), {
  return accounts.find(Account.balance.lt(200)).toArray();
```

## m-opt-lock-005: a stale-version update conflicts (affects 0 rows) — the row is unchanged

```ts
await f.px.transaction(
    const accounts = tx.entity("Account");
    await accounts.find(Account.id.eq(2)).single();
    await accounts.update(accountPk(2), { set: [Account.balance.set(dec("250.00"))] });
```

## m-opt-lock-006: an update on the fresh version succeeds (affects 1 row)

```ts
const result = await f.px.transaction(
  const accounts = tx.entity("Account");
  await accounts.find(Account.id.eq(2)).single();
  return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
```

## m-opt-lock-007: a retry re-reads the fresh version after the conflict and succeeds

```ts
const result = await f.px.transaction(
  const accounts = tx.entity("Account");
  await accounts.find(Account.id.eq(2)).single(); // observes version 1
    return await accounts.update(accountPk(2), {
    await accounts.find(Account.id.eq(2)).single();
    return accounts.update(accountPk(2), { set: [Account.balance.set(dec("250.00"))] });
```

## m-temporal-read-009: an optimistic close on a fresh observed in_z closes exactly the current milestone

```ts
const result = await f.px.transaction(
  const balances = tx.entity("Balance");
  await balances.find(Balance.id.eq(2)).single();
  return balances.update(balancePk(2), { set: [Balance.value.set(dec("250.00"))] });
```

## m-temporal-read-010: an optimistic close on a STALE observed in_z conflicts (a current row still exists)

```ts
await f.px.transaction(
    const balances = tx.entity("Balance");
    await balances.find(Balance.id.eq(2)).single();
    await balances.update(balancePk(2), { set: [Balance.value.set(dec("250.00"))] });
```

## m-temporal-read-011: a retry re-reads the fresh current in_z after the temporal conflict and succeeds

```ts
const result = await f.px.transaction(
  const balances = tx.entity("Balance");
  await balances.find(Balance.id.eq(2)).single(); // observes in_z 2024-02-01
    return await balances.update(balancePk(2), {
    await balances.find(Balance.id.eq(2)).single();
    return balances.update(balancePk(2), { set: [Balance.value.set(dec("250.00"))] });
```

## m-temporal-read-012: a locking-mode close that finds no current row raises (never silent)

```ts
await f.px.transaction((tx) => tx.entity("Balance").terminate(balancePk(2)), {
* `px.transaction` holds the connection would deadlock.
```
