---
status: superseded by ADR-0065
---

# Optimistic lock conflicts are caller-driven

TypeScript optimistic-lock conflicts surface as `ParallaxOptimisticLockError`. The runtime does not automatically retry the transaction or write. A conflict means another transaction committed a newer version first, so application code should re-read the current state, decide whether the intended change still makes sense, and then explicitly retry if appropriate.

This follows the core `M10` contract: optimistic-lock conflicts must be retriable, but the choice between automatic and caller-driven retry is per-language policy. TypeScript chooses caller-driven retry because automatic replay can hide domain decisions, duplicate side effects, and apply stale intent over state the user has not inspected.

Managed-object writes that expect exactly one versioned row and affect zero rows throw `ParallaxOptimisticLockError`. Set-based `update` and `delete` operations continue to return result objects such as `{ affectedRows }` unless a later API adds explicit expected-count or conflict-policy options.

Database transient failures such as serialization failures or deadlocks are a separate concern from optimistic-lock conflicts. A future transaction retry policy may address those failures, but it should not silently retry semantic optimistic-lock conflicts.
