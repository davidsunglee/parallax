<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Transactions and writes

All writes run inside `px.transaction(async tx => …)`. `create` / `update` / `delete` buffer and flush set-based at commit (FK-safe). Audit-only entities chain milestones: `create` opens `[now, ∞)`, `update` closes the current row and chains a new one, `terminate` closes only — the prior values survive as the audit trail.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/transactions.api-conformance.test.ts`).

## 0004: a timestamp insert stores as UTC

```ts
await f.px.transaction(async (tx) => {
await tx.entity("Event").create({ id: 1n, occurredAt: at("2024-03-01T05:30:00+05:30") });
```

## 0005: a timestamp insert keeps microsecond precision

```ts
await f.px.transaction(async (tx) => {
  .create({ id: 1n, occurredAt: at("2024-03-01T12:00:00.123456+00:00") });
```

## 0510: create opens an audit milestone [txInstant, infinity)

```ts
await f.px.transaction(async (tx) => {
await tx.entity("Balance").create({ id: 1n, acctNum: "A", value: dec("100.00") });
```

## 0511: update closes the current milestone and chains a new one (audit trail)

```ts
await f.px.transaction(async (tx) => {
await tx.entity("Balance").create({ id: 1n, acctNum: "A", value: dec("100.00") });
await later.transaction(async (tx) => {
  .update(Balance.id.eq(1), { set: [Balance.value.set(dec("150.00"))] });
```

## 0512: terminate closes the current milestone and inserts nothing

```ts
await f.px.transaction(async (tx) => {
await tx.entity("Balance").create({ id: 1n, acctNum: "A", value: dec("100.00") });
await later.transaction(async (tx) => {
await tx.entity("Balance").terminate(Balance.id.eq(1));
```

## 0604: buffered inserts + updates flush as set-based SQL

```ts
await f.px.transaction(async (tx) => {
const wallets = tx.entity("Wallet");
await wallets.create({ id: 10n, owner: "Mira", balance: dec("100.00") });
await wallets.create({ id: 11n, owner: "Omar", balance: dec("20.00") });
await wallets.create({ id: 12n, owner: "Nell", balance: dec("30.00") });
await wallets.update(Wallet.id.eq(10), { set: [Wallet.balance.set(dec("500.00"))] });
await wallets.update(Wallet.id.eq(11), { set: [Wallet.balance.set(dec("500.00"))] });
```

## 0607: a dependent find observes the buffered insert (read-your-own-writes)

```ts
const observed = await f.px.transaction(async (tx) => {
const accounts = tx.entity("Account");
await accounts.create({ id: 7n, owner: "Newton", balance: dec("5.00"), version: 1 });
return accounts.find(Account.id.eq(7)).toArray();
```

## 0608: an aborted transaction discards its writes (rollback)

```ts
f.px.transaction(async (tx) => {
  const accounts = tx.entity("Account");
  await accounts.find(Account.id.eq(1)).single();
  await accounts.update(Account.id.eq(1), { set: [Account.balance.set(dec("999.00"))] });
  const midTx = await accounts.find(Account.id.eq(1)).toArray();
const observed = await f.px.transaction(async (tx) =>
tx.entity("Account").find(Account.id.eq(1)).toArray(),
```

## 0612: a referenced parent is inserted before its child (FK ordering)

```ts
await f.px.transaction(async (tx) => {
await tx.entity("Order").create({
await tx.entity("OrderItem").create({ id: 200n, orderId: 100n, sku: "X-1", quantity: 3 });
```

## 0613: distinct new values flush as one keyed UPDATE per key

```ts
await f.px.transaction(async (tx) => {
const wallets = tx.entity("Wallet");
await wallets.update(Wallet.id.eq(1), { set: [Wallet.balance.set(dec("111.00"))] });
await wallets.update(Wallet.id.eq(2), { set: [Wallet.balance.set(dec("222.00"))] });
```
