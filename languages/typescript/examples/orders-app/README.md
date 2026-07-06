# orders-app — minimal `#parallax` sample

A minimal application that exercises the Phase 9 developer surface: the generated
`#parallax` barrel, the `parallax(...)` factory, and a typed `find` (spec §2).

## Layout

- `parallax/orders.yaml` — the canonical descriptor (serialized m-descriptor metamodel).
- `parallax.config.js` — the generator config (`defineParallaxConfig`).
- `src/main.ts` — imports `#parallax`, builds `px`, runs a typed `find`.
- `.parallax/generated/` — the generated barrel (gitignored; `parallax generate`
  materializes it behind the `#parallax` import alias — ADR-0003).

## Try it

```sh
pnpm --filter @parallax/example-orders-app exec parallax generate      # writes .parallax/generated/index.ts
pnpm --filter @parallax/example-orders-app exec parallax generate --check   # validate only, no write
```

`Order.id.eq(42)` (the generated entity symbol) serializes to the SAME canonical
operation the conformance adapter compiles, so the developer surface and the
graded runtime never diverge (design Q1 Option B).
