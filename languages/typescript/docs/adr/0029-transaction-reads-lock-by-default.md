# Transaction reads lock by default

TypeScript reads performed through a `ParallaxTransaction` use the core in-transaction read-lock behavior by default, while reads through the outer `Parallax` handle do not. This matches Parallax's read-then-write correctness contract and avoids making callers remember locking options before mutating managed objects.

V1 does not expose a `lock: false` escape hatch on transaction reads. A lock-disabling option is easy to use as a performance knob while accidentally weakening correctness. Read-only work that does not need transactional locking should use the outer `Parallax` handle rather than a `ParallaxTransaction`.
