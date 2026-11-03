# Concurrency policy is a model Facet that Unit of Work reads directly

Which Effective Concurrency Strategy an Entity participates under, its family's
version source, what its existing-row writes settle against, and the version
arithmetic are facts of the accepted model. They belong to one module,
`m-concurrency` (formerly `m-opt-lock`), which compiles them into the
Concurrency Facet at model formation and also states what each strategy
promises. The module holds no transaction state and applies nothing.

The dependency between this policy and Unit of Work is reversed:
`m-unit-work --> m-concurrency`. Unit of Work reads the Facet from the model it
already holds, as it reads the Temporal Facet, and applies the answers to its
own attempt state: admission, retained observations, claims, version
sufficiency, acquisition, settlement, and affected-row interpretation. The
injected strategy and write-evidence ports, and the adapter that filled them,
are removed rather than relocated.

The standalone read-lock module, `m-read-lock`, is removed. A read's owner
decides **whether** it takes the shared row lock from the Facet's strategy for
the Entity it reads: read delivery for each object-find level, and Unit of Work
for its acquisition reads. SQL lowering receives only that yes-or-no request,
and the dialect decides **where and how** the lock attaches. The read-lock
module's rules move to the owners that already apply them; in particular the
rule that every returned observation describes the physical row state its lock
protects, at Read Committed included, moves whole to `m-unit-work` beside the
Locking-write licence and the isolation composition. The cases of both former
families become one `m-concurrency` family.

The rules are stated in [`m-concurrency`](../../core/spec/m-concurrency.md),
[`m-unit-work`](../../core/spec/m-unit-work.md), and
[`m-dialect`](../../core/spec/m-dialect.md).

## Why

The ports existed because the policy module sat above Unit of Work, so Unit of
Work could reach it only through interfaces it declared. Every production and
test call site supplied the same single adapter, so the seams never varied, and
the policy module had to import attempt types to answer through them. Placing
the policy below Unit of Work, as a model Facet, removes both the seams and the
cycle pressure: the policy answers model questions with model types, and the
attempt-shaped rules — the observed-version requirement, what a write settles
against in a given attempt — sit with the state they judge. Model formation,
the Entity frontend, the descriptor hub, and model evolution consequently no
longer reach Unit of Work or the Database Port through the policy.

The read-lock module hid no decision: it mapped an already-derived strategy to
an identical dialect vocabulary, while the actual decision was made three
different ways by three different reads. Having each read's owner decide once,
and SQL receive only the result, states the decision where it is made and keeps
strategy vocabulary out of SQL lowering and the dialect.

## Alternatives

Keeping the ports with Unit of Work as their declaring module was rejected: it
preserves seams with one adapter and keeps the policy importing attempt types.
Absorbing the policy into Unit of Work was rejected because version sources and
strategy derivation are accepted-model facts that model formation, read
delivery, batch writes, and model evolution consume without any transaction.
Moving the read-lock decision into the dialect, as ADR 0012 had it, was rejected
because the dialect would need the strategy vocabulary and the model to decide
something it only renders.

This supersedes in part [ADR 0041](0041-write-finalization-is-centralized-behind-a-typed-planner.md)
and [ADR 0012](0012-in-transaction-read-locks-apply-to-object-finds-not-aggregations.md).
