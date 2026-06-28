# Flush is not a public TypeScript API

The TypeScript API does not expose `tx.flush()` in the first version. Flushing is an internal unit-of-work mechanism: commit flushes automatically, and reads that depend on pending writes are made correct by the framework through auto-flush or unit-of-work state rather than by requiring users to force a flush.
