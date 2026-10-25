# Model evolution

A domain model changes after it is deployed, while processes keep serving it. Parallax
splits that change into parts with different owners. It describes the difference
between two models and generates the schema change that difference needs. The
application applies that schema change and decides when each process starts serving the
new model. Every execution runs under exactly one model from start to finish. This page
explains editions and how executions adopt them, how a change is described and
classified, why the application owns migrations, and what happens while two editions
serve one database.

Each section names the specification that owns it. This page explains and links; when
it and a specification seem to disagree, the specification is right.

## Editions and the Serving Model

A **Model Edition** is an opaque, nonempty token naming one accepted model. Editions are
compared only for equality and never ordered, so nothing about a token says which
edition is newer. A **Model Selection** pairs a model with its edition and is fully
prepared: everything the runtime derives from the model, such as row layouts and write
planning, is worked out before the selection can be served, so a model that can't be
prepared fails before it serves anything rather than on a request
([Model Editions](../../core/spec/m-execution.md#model-editions)).

A Database Root's **Serving Model** holds the one selection it currently serves.
Reading it costs nothing: no compilation, no I/O and no callback. Publishing replaces
the held selection atomically, but only when the publisher names the exact selection it
expected to replace. The comparison is by identity, not by edition, so a publisher that
lost a race to another is refused, told which selection is actually held, and replaces
nothing. Holding a root doesn't confer the right to publish: the Serving Model is a
separate object, and whoever holds it controls what the root serves. Why preparation,
publication and adoption have separate owners is recorded in
[ADR 0062](../adr/0062-transactions-adopt-one-model-edition-at-open.md).

## Every execution adopts one edition

An execution **adopts** the held selection once and keeps it until it completes
([Model Editions](../../core/spec/m-execution.md#model-editions)):

- a transaction attempt adopts before its database transaction begins, and a call that
  joins the transaction inherits that edition;
- a retry is a new attempt, so it adopts afresh;
- a standalone read adopts before it starts, and a stream adopts when it is entered and
  keeps that edition for every page.

A publication that lands after adoption changes nothing already adopted:

```text
 Serving Model   holds A ──────────── publish B ───────────────────────────
                     │                    │
 transaction 1       open: adopts A ──────┼───── reads, writes ── commit    A throughout
                                          │
 transaction 2                            └─ open: adopts B ── commit       B throughout
```

So one transaction can never mix two models. Every result keeps the edition it was read
under, and a failure reports the edition of the execution it ended, which lets the
application correlate what it sees with the state of a rollout.

## Changes are described in the model's own terms

An **Evolution** describes the whole difference between two accepted models
([the evolution algebra](../../core/spec/m-model-evolution.md#the-evolution-algebra)).
It is a pure function of the two models: nothing is applied, and no database is
consulted. The description lists **Evolution Operations** named in the terms the model
was authored in, such as an Entity added, an Attribute altered or an Index removed,
rather than tables and columns. Declarations are matched by identity, so a rename is
never inferred: it is one removal and one addition. An operation that adds or removes a
whole declaration also covers everything inside it.

Describing the change at the model's altitude, rather than as a column-level change set,
is deliberate: the same description serves classification, a review that shows a team
what it is about to change in its own vocabulary, a relational schema generator, and a
store with no tables at all
([consumer contract](../../core/spec/m-model-evolution.md#consumer-contract)). The two
models are always describable, and the same pair always gives the same description.
Comparing a model with itself gives an empty description, and an explicit **absent**
earlier model describes provisioning a fresh database.

## Classification: can a live database take it?

Every Evolution is one of two kinds
([classification](../../core/spec/m-model-evolution.md#classification)):

|  | Unilateral Evolution | Coordinated Evolution |
| -- | -- | -- |
| What it preserves | every query and write that was valid under the earlier model, with the same identities, inputs, types and result shapes | not all of them, or not without transforming stored data |
| Stored data and schema | no destructive transformation | needs authoring, data or rollout coordination |
| Can be applied while the earlier edition runs | yes | no |
| Schema Delta | generated from it | none: it is not an input to schema generation |
| Carries | Behavioral Impacts and Overlap-Visible Operations | Behavioral Impacts and one Coordination Requirement per operation that needs it |

A Coordination Requirement names its operation and the reasons it needs coordination:
**an authoring surface change**, when a previously valid query or write shape has to
change, and **a database migration**, when no prefix-safe schema change can carry the
database across without destroying data or staging compatibility. One operation can need
both. A Coordinated Evolution is a complete, valid description, not a refusal; it
prescribes no procedure, because how to coordinate is the application's decision.

Some boundaries in the specification, in brief: adding a nullable member, an index, a
relationship or a concrete subtype is unilateral; removing a model-facing declaration,
changing a type, a key or a stored location, and narrowing what a member admits all need
coordination. "Destructive" means destructive to data or to the schema the earlier
edition depends on, not merely a statement that drops something: removing a secondary
index, a rebuildable access path no query names, is unilateral.

## Behavioral Impacts: what changes behind the surface

A unilateral change can still change behaviour. **Behavioral Impacts** report it, for
both kinds of Evolution, in a closed vocabulary
([Behavioral Impacts](../../core/spec/m-model-evolution.md#behavioral-impacts)):

| Impact | What differs |
| -- | -- |
| Uniqueness enforcement | the set of uniqueness rules on a surviving Entity |
| Value admissibility | the type, nullability or maximum length a value path admits |
| Delete propagation | whether deleting along a Relationship propagates |
| Concurrency control | how an Entity is protected under the optimistic preference: versioned, gated by Transaction Time, or falling back to locks |
| Query result membership | the concrete Entities and temporal shape a query over an Entity covers, or a Relationship's target and join |
| Query result ordering | a Relationship's ordering rule |
| Write capability | whether an Entity accepts writes, and how a caller may write an Attribute |

Each impact carries its earlier and later facts and the operations that caused it. They
are derived from the two models alone, so an impact is reported even where no stored row
would show it, and the absence of an impact asserts that those facts are equal. Impacts
prescribe no severity or remedy.

## Why the application owns migrations

A **Schema Delta** is the ordered list of dialect statements that carries a database from
a Unilateral Evolution's earlier model to its later one
([the generation algebra](../../core/spec/m-schema-delta.md#the-generation-algebra)).
Parallax generates it and never applies it, for three reasons recorded in
[ADR 0063](../adr/0063-model-evolution-is-described-at-model-altitude-and-applied-by-the-application.md):
generation stays a pure function that returns results rather than producing effects;
schema statements are not transactional on every database; and a database is served by
many processes, whose roots would otherwise race to migrate it on the request path.

The statements are built so the application can apply them safely
([statements are prefix-safe](../../core/spec/m-schema-delta.md#statements-are-prefix-safe-and-deliberately-not-idempotent)):

- **Prefix-safe.** Every prefix of the returned order can be applied to a database at
  the earlier edition, so a migration that stops partway leaves a database the earlier
  edition still operates against.
- **Deliberately not idempotent.** A delta states what must happen to a database at a
  known edition. It never says "if not exists", because a statement that silently did
  nothing would leave the later edition published over a schema that never received it.
- **Forward only.** No inverse is produced, because the inverse of a unilateral change
  is not generally unilateral.
- **Validating.** Creating a unique index is the check that stored rows satisfy it; if
  they don't, the statement fails and the later edition is not published.

The delta also records each index it creates under its physical name, so a uniqueness
violation reported later can be traced to the rollout that created the index
([consumer contract](../../core/spec/m-schema-delta.md#consumer-contract)).

A rollout therefore runs in one order: describe, generate, apply, then publish.

```text
 deployment (once per database)      database                each running process
 ──────────────────────────────      ────────                ────────────────────
 Evolution: deployed → release
   ├ Coordinated → no Schema Delta;
   │   the application coordinates
   └ Unilateral
        │ Schema Delta
        ▼
   statements ──────────────────────→ applied in order,
                                      stop at first failure
                                            │ all succeeded
                                            ▼
                                      schema satisfies
                                      both editions ──────→ prepare the release
                                                              fails → earlier keeps serving
                                                            publish, expecting the held one
                                                              stale → refused, no change
                                                            later executions adopt it
```

Publishing asserts that the schema already satisfies the release; Parallax checks no
schema and coordinates nothing between processes.

## The overlap window

Processes publish independently, so for a while some serve the earlier edition and some
the later one, against the same database. That is **Edition Overlap**, and draining a
single process cannot end it. Parallax classifies what can happen during it rather than
preventing it
([ADR 0062](../adr/0062-transactions-adopt-one-model-edition-at-open.md)).

What the two editions must agree on is the schema, and a Unilateral Evolution guarantees
that agreement: the migrated database still satisfies every query and write the earlier
edition can make. Within that agreement they may still differ:

- **Behaviour may differ.** A Behavioral Impact applies to whichever edition is running.
  A unique index created for the later edition can refuse a write the earlier edition
  makes; the failure carries the violated index's physical name and the edition the
  transaction adopted, and it is not retried automatically.
- **The later edition may store what the earlier one can't admit.** An
  **Overlap-Visible Operation**
  ([Overlap-Visible Operations](../../core/spec/m-model-evolution.md#overlap-visible-operations))
  lets a later writer store a value the earlier model doesn't allow: a member made
  nullable, a maximum length widened or removed, or a new subtype in a family stored in
  one table, whose discriminator value an earlier reader doesn't know. Where the earlier
  edition checks such a value as it reads it, as it does a discriminator, it reports the
  row as stored data violating its model, together with its own edition
  ([Invalid stored data](../../core/spec/m-read-delivery.md#invalid-stored-data)).

A Coordinated Evolution has no overlap-visible operations because it never goes through
this path.

## Common use cases

- **Adding a feature.** A new Entity, a nullable Attribute, a new subtype or an index:
  unilateral. Generate the delta, apply it, then publish.
- **A release check.** Describe the change between the model last deployed and the
  candidate, and fail the build when it is coordinated or carries an impact the team
  hasn't reviewed.
- **Removing or reshaping something.** A removed Attribute, a type change or a new
  required member on an existing Entity needs coordination. Parallax generates no Schema
  Delta for it, so the application plans and applies that change itself.
- **Provisioning a database.** The evolution from the absent model creates the complete
  schema.
- **Diagnosing a rollout.** Results and failures carry the edition they ran under, and
  created indices carry the names a violation reports, so a failure can be traced to the
  rollout that caused it.

## Do it →

- [Model Editions](../../languages/python/docs/guide/07-model-evolution.md#model-editions)
- [Describing a change](../../languages/python/docs/guide/07-model-evolution.md#describing-a-change)
- [Generating the schema change](../../languages/python/docs/guide/07-model-evolution.md#generating-the-schema-change)
- [Rolling out a new model](../../languages/python/docs/guide/07-model-evolution.md#rolling-out-a-new-model)
