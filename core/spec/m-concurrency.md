# m-concurrency — Concurrency Policy

`m-concurrency` decides which **Effective Concurrency Strategy** each Entity
participates under, and states what each strategy promises. It owns the
Concurrency Preference and strategy vocabulary, each family's **version
source**, the derivation that combines the two, what an existing-row write
settles against, and the version arithmetic that runs under both strategies.

These are facts of the accepted model. The module holds no transaction state and
applies nothing: `m-read-delivery` decides each find level's lock from them;
`m-unit-work` applies the strategy to an attempt's acquisition reads, admission,
claims, and settlement; `m-write-plan`, `m-temporal-write`, and `m-sql` state and
render the gates; `m-auto-retry` replays a recoverable conflict. `m-concurrency` depends on `m-metamodel`, `m-model-formation`,
`m-inheritance`, and `m-temporal-read`, and names no attempt, write-plan, or SQL
construct.

## Model-formation contribution

The module's Rule Set judges the Candidate Metamodel, and its Model Compiler
consumes the Inheritance Facet and the Temporal Facet through
`m-model-formation`. The Rule Set owns exactly two Issue Codes:

- `concurrency-multiple-version-attributes` — a declaring position names more
  than one explicit version Attribute (`optimisticLocking: true`, `m-descriptor`);
- `concurrency-temporal-explicit-version` — a declaring position with a
  Transaction-Time As-Of Axis also declares an explicit version Attribute.

A version Attribute declared below its family root is refused by
`m-inheritance` (`inheritance-optimistic-locking-not-root-owned`), so a family
is versioned together or not at all.

## Per-Entity concurrency facts

The accepted model's Concurrency Facet answers, for each Entity, its Effective
Concurrency Strategy under a Concurrency Preference, its version source, and what
its existing-row writes settle against. Each answer is uniform across an
inheritance family, whose root decides it. A Concurrency Preference and an
Effective Concurrency Strategy are each `locking` or `optimistic`.

### Version sources

A family has exactly one version source: **explicit version**,
**Transaction-Time version**, or **Unversioned**.

- **Explicit version** names the family root's `optimisticLocking: true`
  Attribute, and every descendant reports the root's identity.
- **Transaction-Time version** applies to every Entity whose Temporal Shape
  declares Transaction Time and names that axis's start Attribute: the observed
  `txStart` (physical `in_z`) of a milestone is its version, and a fresh
  milestone's start is the advance. No column holds a version number.
- **Unversioned** is the remaining case: a Non-Temporal family with no version
  Attribute.

The two versioned variants are mutually exclusive, because a Transaction-Time
Entity declaring an explicit version is refused
(`concurrency-temporal-explicit-version`), and every supported temporal
formation contains Transaction Time.

## Strategy derivation

A unit of work resolves one Concurrency Preference (`m-execution` *Option
resolution*). The preference is a request, not the correctness mechanism: it is
combined with each Entity's version source to derive that Entity's Effective
Concurrency Strategy.

| Concurrency Preference | Version source | Effective Concurrency Strategy |
|---|---|---|
| `locking` | any | **Locking** |
| `optimistic` | explicit version | **Optimistic** — gates on the observed version |
| `optimistic` | Transaction-Time version | **Optimistic** — gates on the observed `txStart` |
| `optimistic` | Unversioned | **Locking** — the fallback |

`optimistic` therefore means **use optimistic concurrency wherever the model
supplies a version, with a locking fallback where it does not**. It never means
that a heterogeneous transaction is universally lock-free. An explicit `locking`
preference is the workflow-level override that makes every lockable Entity
participate pessimistically, so the same versioned or temporal Entity can be
gated in one workflow and locked in another.

The strategy belongs to the Entity a read or write addresses. An object read
resolves the strategy of the Entity it materializes, and separate deep-fetch
levels resolve independently, so one transaction may read a versioned root
optimistically and an unversioned included Entity under a shared lock.

Reladomo is prior art for mixed participation, but exposes the choice per
transaction and object portal or class. Parallax deliberately keeps one ergonomic
preference and derives the safe per-Entity result instead of exposing per-Entity
overrides.

## What each strategy promises

- **Locking.** A participating object find **MUST** take a shared row lock on
  what it reads, with no locking SQL from the caller, and holds it until the
  transaction ends, so a concurrent transaction cannot mutate the row out from
  under a read-then-write. An observation-requiring write is `Ungated`: the lock
  its required observation took is what makes it correct (`m-unit-work` *What
  licenses a Locking write*). A target write has no source, so its own
  acquisition takes that lock; a live read holding it may stand in, which
  `m-unit-work` *Target writes* permits and does not require.
- **Optimistic.** A participating object find takes no lock. An
  observation-requiring write gates on the version or `txStart` its observation
  carries, so the database detects an intervening write.
- **Both.** An observation-requiring write — a versioned keyed `UPDATE`, a
  versioned keyed `DELETE`, and a temporal milestone close — must hold its
  observation under either strategy, and an explicit version advances on every
  `UPDATE` issued against it.

Which reads participate, and that standalone and read-only reads take no lock,
belongs to `m-unit-work` and `m-execution`. Whether a participating read takes
the lock is decided by its owner from this strategy: `m-read-delivery` for an
object find, `m-unit-work` for a write's acquisition read. Where and how a lock
attaches belongs to `m-dialect` and `m-sql`.

### Effective Concurrency Strategy determines the gate uniformly

Whether a write carries its observation-bound gate is decided by the target
Entity's Effective Concurrency Strategy **alone**, never by the mutation kind:
Optimistic gates every observation-requiring write, and Locking gates none of
them. Only what the statement renders differs; the observation requirement does
not.

An implementation **MUST NOT** make gate presence depend on the verb. A keyed
`DELETE` that retained its observed-version predicate under Locking would give
the gate two meanings under one strategy and let a Locking shortfall surface as
an optimistic conflict. The uniform goldens are `m-sql`'s (*Versioned UPDATE and
DELETE*); the gate shapes are `m-write-plan`'s
([Write Gate](m-write-plan.md#write-gate-and-the-concurrency-decision)).

## What a write settles against

An existing-row write of a family settles against, and therefore claims
(`m-unit-work` *Observed-State Coalescing*):

- a versioned or temporal family's write settles against the state its source
  **observed**, because two writes of one key that observed two different states
  are two independent intents;
- an Unversioned family's write settles against its **object**: the shared row
  lock its evidence is held on the object and covers every state the row can be
  in, so two such writes can never have observed two different states.

An insert opens a row rather than writing against one, so it settles against
nothing whatever the family; that distinction is the unit of work's, from the
write's own mutation.

## Version arithmetic

Versions are framework-owned (`m-unit-work` *Version values are
framework-owned*). Every explicitly versioned insert opens at version **1**,
ignoring any row-carried value, and every successful `UPDATE` stores the
observed version **plus one**, under both strategies.

## What the suite pins down

The formation rules and every Facet answer are proven by each language's own
suite over the corpus models.
