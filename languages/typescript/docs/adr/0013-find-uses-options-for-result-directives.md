# Find uses options for result directives

The TypeScript `find` API accepts result-shaping directives such as `includes`, `orderBy`, `limit`, and `distinct` in an options object rather than exposing a separate query-builder chain. This keeps the first read surface small while still mapping directly to the core operation directives. Eager relationship loading is named `includes` rather than core's `deepFetch` because it is more natural in contemporary TypeScript APIs; it maps to the same deep-fetch behavior and round-trip guarantees.

Ordering uses generated sort keys produced from attribute expressions:

```ts
await px.orders.find(Order.status.eq("processing"), {
  orderBy: [Order.createdAt.desc(), Order.id.asc()],
  limit: 50,
});
```

Sort keys are query expressions in V1, not JavaScript comparator callbacks.
