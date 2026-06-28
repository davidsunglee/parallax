# Writes require explicit transactions

The TypeScript API exposes reads on the `Parallax` handle, but all writes are available only through a `ParallaxTransaction`. This eliminates implicit transaction behavior from the domain API, keeps cache invalidation and unit-of-work semantics visible, and gives Parallax one persistence boundary for simple writes, set-based writes, temporal writes, and managed object graph mutation.
