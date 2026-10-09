# m-write-payload — Persisted Write Payloads

`m-write-payload` specifies how the values a Planned Write stores are assembled:
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

## Preparation is demand-driven and model-scoped

```text
WritePayloadPreparer(model)
  assignments(entity, PlannedAssignments) -> AssignmentPayload
  row(entity, WriteRow)                   -> RowPayload
  proven_unequal_non_interval(entity, WriteRow, WriteRow) -> Boolean
  equal_non_interval(RowPayload, RowPayload)              -> Boolean
  rebound(RowPayload, WriteRow)                           -> RowPayload
```

The interface and its result vocabulary are `m-write-plan`'s; this module
implements them. Preparation is pure and runs when something needs its result:
a statement about to be lowered, or a comparison that needs complete state. A
narrow update demands its assignments alone and never a complete row or its
predecessor. Nothing prepares a whole plan, a later execution unit, or every row
of a Materialized Write Group in advance, and repeating a demand without
retained backing may prepare again rather than consult a cache.

A **Row Payload** holds one Write Row's persisted cells in Table Layout slot
order, and an **Assignment Payload** the values one revising step writes, in the
same order. Each cell names its contributor by model identity — a member, the
Table's shared Structured Column, or the table-per-hierarchy discriminator —
never by physical column. Each payload is bound to the inputs it was prepared
from (`m-write-plan` *Write payloads*).

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
and an assigned occurrence's complete encoded document or JSON null, so every key the step does not name survives. Within one
preparation, the same prepared values are what a document patched from them
holds and what the statement assigns; nothing encodes them a second time. A
revising step whose successor was also prepared whole for a comparison retains
none of that comparison's backing, so its own lowering prepares its assignments
again.

## Comparing persisted state

`equal_non_interval` answers whether two prepared rows persist identical cells
outside their temporal interval. Scalars compare as stored at their Neutral
Type; documents — the shared Structured Column, Value Object columns, scalar
collection columns, and `json` members — compare by the codec's exact persisted
equality, so unknown keys,
presence, array order, JSON kinds, and exact numeric meaning all participate. A
row that leaves some Column to the database's default, or holds a generated
value, establishes no known state and equals nothing. Object identity and
Transaction-Time bounds are the caller's eligibility questions, not this one.

`proven_unequal_non_interval` is a cheap, sound inequality check over two
finalized Write Rows: it compares scalar members both rows state, which are
exact managed values at their Neutral Type — a scalar collection element by
element in order — without preparing any document.
`true` proves the persisted states differ; `false` proves nothing, and a caller
needing equality must compare the prepared rows. Interval members, generated
values, members only one row states, and occurrences decide nothing here.

## Rebinding prepared cells to a merged interval

`rebound` answers a Row Payload's cells for a Write Row that states exactly what
the payload was prepared from outside its temporal interval — the same origin,
executed selection, occurrences, and every other Attribute value — and a
different interval: the prepared values stay, and only the interval cells take
the row's own. That is how a row merged from identical produced rows
(`m-temporal-write` *Merging produced successors*) stores the cells its
comparison already prepared, without finalizing, encoding, or comparing them
again. A row stating anything else outside its interval is refused rather than
given cells prepared from other inputs.
