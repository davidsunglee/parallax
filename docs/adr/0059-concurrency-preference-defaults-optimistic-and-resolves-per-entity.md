# Concurrency preference defaults optimistic and resolves per Entity

Parallax resolves one `locking` or `optimistic` Concurrency Preference at the
outer Unit Work boundary, defaulting to `optimistic`, then combines that
preference with each Entity's Optimistic Lock Facet to derive its Effective
Concurrency Strategy. An explicit version or Transaction-Time-derived key uses
lock-free reads and an observation-bound gate under the optimistic preference;
an unversioned Non-Temporal Entity falls back to shared-lock participation in
that same transaction. An explicit locking preference forces the Locking
strategy for every lockable Entity. Optimistic-conflict retry remains a separate
opt-in policy, while deadlock and serialization retry remain automatic.

This replaces the earlier transaction-uniform, locking-default rule. Uniform
locking imposed blocking and deadlock exposure even where the model supplied a
safe optimistic gate; uniform optimistic either left unversioned writes unsafe
or required rejecting them. Reladomo demonstrates that class-specific
participation strategies can coexist within one transaction. Parallax adopts
that semantic capability without its per-Finder configuration surface: the
model supplies capability, the Unit Work supplies one workflow preference, and
the runtime derives the safe result.

The consequence is that `concurrency="optimistic"` means gate-preferred rather
than universally lock-free. Current-transaction read participation remains
mandatory whenever the derived strategy is Locking, including the unversioned
fallback; authentic standalone Typed or Wire evidence is sufficient only when a
version or milestone gate makes the Entity effectively Optimistic. An accepted
Execution Lifecycle root reports the resolved preference on its outer
Transaction Invocation, while Database Call events expose the actual mixed
locking and gated statements transiently.
