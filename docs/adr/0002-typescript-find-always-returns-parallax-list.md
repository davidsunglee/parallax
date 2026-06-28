# TypeScript find always returns ParallaxList

The initial TypeScript read API exposes `find` as the only finder operation, and it always returns a `ParallaxList` that may contain zero, one, or many objects. This avoids early API branching around `findOne`, `findMany`, and required-result variants while preserving the operation-backed list semantics required by Parallax.
