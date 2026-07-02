<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->

# Reading data

Every read is a typed `find` over an entity finder. A predicate is built from the generated entity symbols (`Order.id.eq(42)`), which serialize to the same canonical operation the engine compiles — so the query you write is the query that runs. A `find` returns a lazy `ParallaxList` of **managed objects**: `id` is a `bigint`, `price` a `ParallaxDecimal`, a timestamp a `Temporal.Instant`. Each predicate below is a real, tested case.

Every snippet below is extracted from a test that runs it against a real Postgres through `@parallax/db-postgres` and asserts the shown result (`packages/typescript/test/api-conformance/reads.api-conformance.test.ts`).

## 0001-find-all

```ts
all()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0002-eq

```ts
Order.id.eq(42)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0003-scalar-types-roundtrip

```ts
all()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0006-quoted-reserved-identifier

```ts
Grade.ordinal.gt(1)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0201-not-eq

```ts
Order.qty.notEq(20)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0202-greater-than

```ts
Order.qty.gt(20)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0203-greater-than-equals

```ts
Order.qty.gte(20)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0204-less-than

```ts
Order.qty.lt(15)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0205-less-than-equals

```ts
Order.qty.lte(15)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0206-between

```ts
Order.price.between(20.0, 50.75)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0207-is-null

```ts
Order.sku.isNull()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0208-is-not-null

```ts
Order.sku.isNotNull()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0209-like

```ts
Order.sku.like("A-%")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0210-not-like

```ts
Order.sku.notLike("A-%")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0211-starts-with

```ts
Order.sku.startsWith("A-")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0212-ends-with

```ts
Order.sku.endsWith("00")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0213-contains-escape

```ts
Order.sku.contains("50%")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0214-like-case-insensitive

```ts
Order.name.like("ada", { caseInsensitive: true })
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0215-contains-case-insensitive

```ts
Order.name.contains("A", { caseInsensitive: true }
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0216-in

```ts
Order.id.in([1, 2, 42])
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0217-not-in

```ts
Order.id.notIn([1, 2, 42])
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0218-and

```ts
Order.active.eq(true).and(Order.qty.gt(10))
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0219-or

```ts
Order.qty.lt(10).or(Order.qty.gt(25))
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0220-not

```ts
Order.active.eq(true).not()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0221-none

```ts
new Predicate({ none: {} })
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0223-group-precedence-ungrouped

```ts
Order.qty.gte(25).or(Order.qty.lte(5).and(Order.active.eq(true))
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0224-order-by-limit

```ts
find(all(), { orderBy: [Order.qty.desc()], limit: 2 })
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0225-order-by-asc-limit

```ts
find(all(), { orderBy: [Order.id.asc()], limit: 3 })
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0227-not-eq-null-excluded

```ts
Order.sku.notEq("B-200")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0228-not-in-null-excluded

```ts
Order.sku.notIn(["A-100", "B-200"])
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0229-and-three-operands

```ts
Order.active.eq(true).and(Order.qty.gt(5), Order.qty.lt(30)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0230-order-by-multi-key

```ts
find(all(), {
  orderBy: [Order.active.desc(), Order.qty.asc()],
  limit: 2,
})
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0231-starts-with-escape

```ts
Order.sku.startsWith("C_")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0232-ends-with-escape

```ts
Order.sku.endsWith("50%")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0301-navigate-items-sku

```ts
Order.items.navigate(OrderItem.sku.eq("A-100"))
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0302-exists-items

```ts
Order.items.exists()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0303-not-exists-items

```ts
Order.items.notExists()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0304-exists-items-quantity

```ts
Order.items.exists(OrderItem.quantity.gte(4))
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0305-navigate-statuses-code

```ts
Order.statuses.navigate(OrderStatus.code.eq("SHIPPED")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0306-not-exists-items-and-active

```ts
Order.items.notExists().and(Order.active.eq(true)
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0307-navigate-to-one-parent-predicate

```ts
OrderItemRel.order.navigate(Order_.name.eq("Ada")
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0308-exists-multi-hop-items-status

```ts
Order.items.exists(OrderItemRel.statuses.exists(OrderStatus.code.eq("PACKED"))
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0309-exists-to-one

```ts
OrderStatus.orderItem.exists()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0317-not-exists-multi-hop

```ts
Order.items.notExists(OrderItemRel.statuses.exists()
const rows = await px.entity(entity).find(predicate).toArray();
```

## 0321-navigate-one-to-one

```ts
Person.passport.navigate(Passport.number.eq("P-AAA")
const rows = await px.entity(entity).find(predicate).toArray();
```
