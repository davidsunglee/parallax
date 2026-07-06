# Optimized data structures are non-normative with no V1 decision

TypeScript records no decision about the optional optimized data structures for V1, and marks the area explicitly non-normative. There is nothing to optimize: the identity cache and query cache (`m-process-cache`) are deferred from TypeScript V1 (TS-0027), and these structures exist only to back those caches, so committing to one now would invent a premature decision against a deferred module.

The optional techniques the template lists — open-addressing map/set analogues (`UnifiedMap` / `UnifiedSet`) for the identity / query caches, and a key-derived hashing analogue (`HashingStrategy`) to index domain objects by a derived key without allocating wrapper key objects — are Reladomo implementation techniques for the JVM. The core itself states they are optional and non-normative: a language may hit its performance targets any way it likes.

A post-V1 note records the expected JS baseline so the area is not silently empty when `m-process-cache` lands: a built-in `Map` keyed by a canonical primary-key string is the idiomatic JavaScript baseline for the identity / query caches. The Java open-addressing and no-wrapper-key-allocation techniques have no compelling direct JavaScript analogue — short strings are effectively interned by the engine and V8 `Map`s are already compact, so a composite-PK string key captures the same benefit without a custom hashing strategy or open-addressing table. This is guidance for the future, not a V1 commitment; the decision is deferred with `m-process-cache` and will be made when it is implemented.

Recording an intended choice now was rejected: it would bind V1 to a structure for a cache that V1 does not build.
