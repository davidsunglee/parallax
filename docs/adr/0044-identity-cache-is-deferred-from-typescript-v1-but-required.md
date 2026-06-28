# Identity cache is deferred from TypeScript v1 but required

The initial TypeScript implementation may defer the `M8` identity-cache and query-cache guarantees, but they remain required Parallax behavior. This is a staged implementation decision, not a weakening of the core contract.

Until the TypeScript implementation claims the `M8` conformance slice, repeated reads of the same primary key are not guaranteed to return the same JavaScript object instance, even inside a `ParallaxTransaction`. A resolved `ParallaxList` still remains stable for its own materialized result, but that is a local list guarantee rather than the core identity-cache guarantee.

The post-v1 target is the core `M8` contract: within a cache scope, reads of the same primary key resolve to the same logical managed object, repeated equal operations are served from the query cache, and cache hits preserve object identity. TypeScript APIs should not introduce V1 shortcuts that make this later identity cache difficult to add.

The `Parallax` handle itself should not imply an unbounded long-lived identity map in V1. The eventual cache scope and lifecycle should be made explicit enough to avoid surprising memory retention while still satisfying `M8`.
