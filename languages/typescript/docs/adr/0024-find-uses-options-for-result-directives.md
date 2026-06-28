# Find uses options for result directives

The TypeScript `find` API accepts result-shaping directives such as `includes`, `orderBy`, `limit`, and `distinct` in an options object rather than exposing a separate query-builder chain. This keeps the first read surface small while still mapping directly to the core operation directives.

Ordering uses generated sort keys produced from attribute expressions:

```ts
await px.orders.find(Order.status.eq("processing"), {
  orderBy: [Order.createdAt.desc(), Order.id.asc()],
  limit: 50,
});
```

Sort keys are query expressions in V1, not JavaScript comparator callbacks.
