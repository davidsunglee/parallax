# Generated entity inputs provide validation helpers

Generated TypeScript entity input types include validation helpers for unknown input. These helpers validate plain create payloads before persistence; they do not create managed objects, parse detached entities, parse snapshots, or replace `tx.entity.create(...)`.

The generated surface is:

```ts
const input = OrderInput.parse(req.body);

const result = OrderInput.safeParse(req.body);
if (!result.ok) {
  return response.status(400).json(result.error);
}
```

`parse` returns a typed entity input or throws `ParallaxValidationError`. `safeParse` returns a discriminated result and does not throw for validation failures. Validation errors accumulate issues using the public validation issue shape.

This supports REST handlers, UI draft validation, tests, seed-data checks, and bulk imports that need to validate JSON before opening a transaction or attempting a write. Persistence-time validation still runs inside `create`, because database constraints, relationship options, temporal options, and transaction state can add errors that shape validation alone cannot know.

`OrderInput` is distinct from `OrderSnapshot`. A snapshot is an output/read shape that Parallax can emit from managed objects. An entity input is the input/create validation shape that Parallax accepts for constructing a new managed object. The shapes may overlap for simple entities, but they remain separate so server-owned fields such as database-generated IDs, read-only attributes, version fields, and processing timestamps are not accidentally accepted from clients.

Create itself follows the same plain-payload stance: it accepts plain create payloads rather than constructed or managed entity instances, and returns the managed object. Nested relationship data in a payload must be handled explicitly — `relationships` lists dependent relationship paths to create from the payload, `ignoreRelationships` lists payload relationship paths to ignore, and any remaining nested relationship data is rejected to avoid silent data loss.
