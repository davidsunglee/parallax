# m-write-payload — Persisted Write Payloads

`m-write-payload` specifies how the values a Planned Step stores are assembled:
where each member is placed, how each document a row or assignment stores is
composed, and how two prepared rows compare as persisted state. It is the one
assembler of write payloads. Per the dependency graph it depends on
`m-write-plan`, whose Write Rows and assignments it prepares and whose payload
vocabulary it answers in; on `m-storage-layout`, which places every member; on
`m-document-codec`, which encodes, patches, and compares documents; and on
`m-core` and `m-metamodel` for values and identities. It chooses no authority,
preservation, topology, or coalescing eligibility, and emits no SQL. The surface
that executes writes constructs one preparer per accepted model and hands it to
the Write Planner it configures; `m-sql` renders and binds what it prepares.

## Preparation

Preparation is pure. What a row or assignment persists depends only on the write
and the accepted model. Whether two effects share a grouped effect is decided
from the effects themselves, before any payload exists, so it never varies with
anything an implementation caches.

## Row assembly

A row stores every member it names at the slot the model's Storage Layout gives
it. A Value Object occurrence or a scalar collection with a Column of its own
stores its whole encoded document there — a collection's encoded array — and an
unnamed `many` of either kind stores `[]` (`m-value-object`, `m-document-codec`). Every
document-resident member collapses into the Table's one shared Structured
Column, which every row stores, the empty object included (`m-storage-layout`).
A table-per-hierarchy row stores its concrete subtype's discriminator.

The shared Structured Column's document depends on where the row's state came
from:

- A **new lineage**, or a row whose observation retained no raw document,
  composes the document from the row's own complete member set through the
  codec, so presence stays the codec's classification.
- A **carried or changed** row whose predecessor retained its raw document is
  that document patched at the row's **executed** members alone
  (`m-write-plan` *Write Rows*), in canonical placement order. Every other key —
  an unassigned member's stored spelling, and a key no member declares — rides
  forward as stored. An executed member is written whatever value it assigns:
  an executed occurrence replaces its stored subtree whole even where its
  declared members equal what is stored, and the undeclared keys inside it are
  gone.

A row's executed members are the only assignments preparation reads. It never
infers them from value inequality or from whether a cell is its predecessor's
own object.

## Assignment assembly

A revising step writes only what it assigns. A directly stored member takes its
own slot; a scalar collection there takes its whole encoded array. The shared Structured Column takes the ordered patches of its assigned
paths, prepared once by the codec (`m-document-codec` *Patching*): an assigned
leaf's encoded value or JSON null, an assigned scalar collection's encoded array,
and an assigned occurrence's complete encoded document or JSON null, so every key the step does not name survives.

## Comparing persisted state

Two prepared rows have **equal persisted state** where they persist identical
cells outside their temporal interval. Scalars compare as stored at their Neutral
Type; documents — the shared Structured Column, Value Object columns, scalar
collection columns, and `json` members — compare by the codec's exact persisted
equality, so unknown keys,
presence, array order, JSON kinds, and exact numeric meaning all participate. A
row that leaves some Column to the database's default, or holds a generated
value, establishes no known state and equals nothing. Object identity and
Transaction-Time bounds are the caller's eligibility questions, not this one.
