# Set-based writes accept predicates or ParallaxLists

TypeScript set-based `update` and `delete` APIs accept either a predicate or a `ParallaxList` rather than separate `updateWhere` and `deleteWhere` methods. `update` separates its target from its changes with `update(target, { set: [attr.set(value)] })`; a `ParallaxList` target uses its backing operation when possible, preserving one-statement bulk behavior without adding another public query shape.
