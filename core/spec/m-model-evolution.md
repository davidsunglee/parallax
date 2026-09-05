# m-model-evolution — Model Evolution

`m-model-evolution` describes the difference between two accepted Metamodels at
**model altitude**: a total, ordered description of every change, named in the
terms the model was authored in, classified by whether a live tenant may apply it
without coordination, and annotated with the behavior that changes behind that
surface. It applies nothing, coordinates nothing, and reaches nothing: the
description is a pure function of two accepted models.

It depends on `m-metamodel` for the accepted declarations, structured
identities, and canonical Model Location order it reuses, and on
`m-inheritance`, `m-relationship`, `m-temporal-read`, and `m-opt-lock` for the
**effective** facts classification and Behavioral Impacts compare. Each of those
is read through its owner's compiled facet and re-derived nowhere. Physical
statements are not this module's: a relational consumer lowers a Unilateral
Evolution against the later endpoint's Storage Layout.

The decision record is
[ADR 0063](../../docs/adr/0063-model-evolution-is-described-at-model-altitude-and-applied-by-the-application.md).

## The evolution algebra

```text
evolve(earlier: Metamodel | ABSENT, later: Metamodel) -> Evolution

Evolution = UnilateralEvolution | CoordinatedEvolution

UnilateralEvolution
  earlier                      the accepted earlier endpoint, absent only for ABSENT
  later                        the accepted later endpoint
  operations                   canonical Model Location order
  behavioralImpacts            closed variant order, then scope identity
  overlapVisibleOperations     canonical operation order

CoordinatedEvolution
  earlier, later               both accepted endpoints
  operations                   canonical Model Location order
  behavioralImpacts            closed variant order, then scope identity
  coordinationRequirements     nonempty; one per coordinated operation,
                               in canonical operation order
```

`evolve` is **total**: two equal accepted models produce an empty
`UnilateralEvolution` that still retains both endpoints, so there is no third
no-evolution result and no nullable return. Both variants retain their endpoints,
so a consumer resolves any identity an operation names without holding a model of
its own, and a generator cannot be handed an unrelated target.

`ABSENT` is the **explicit fresh-provisioning sentinel**. It is authored, never
inferred from an accepted model that happens to declare nothing and never from
inspecting a physical schema. Provisioning is always unilateral: one entity-level
addition per target Entity — `ConcreteSubtypeAdded` for a concrete subtype and
`EntityAdded` for every other Entity role — which suppresses that Entity's
members, and no Behavioral Impact and no Overlap-Visible Operation, because no
earlier scope survives for one to hold on.

A Coordinated Evolution is a **complete, valid description**, not a refusal. Each
requirement associates one exact operation with the structured reasons unilateral
application is unavailable; it prescribes no migration procedure.

## Evolution Operations

Declarations are matched by structured identity. A rename is never inferred: it
is one removal and one addition, until the model has an authored identity that
survives renaming. A parent addition or removal **suppresses** every operation
for the declarations it contains — an Entity operation suppresses its members, a
Value Object occurrence operation suppresses its nested members — and one
alteration groups the closed field changes at one logical location.

### Evolution Operation vocabulary

```text
EntityAdded
EntityRemoved
EntityAltered
ConcreteSubtypeAdded
ConcreteSubtypeRemoved
AttributeAdded
AttributeRemoved
AttributeAltered
ValueObjectOccurrenceAdded
ValueObjectOccurrenceRemoved
ValueObjectOccurrenceAltered
ValueObjectAttributeAdded
ValueObjectAttributeRemoved
ValueObjectAttributeAltered
RelationshipAdded
RelationshipRemoved
RelationshipAltered
AsOfAxisAdded
AsOfAxisRemoved
AsOfAxisAltered
IndexAdded
IndexRemoved
IndexAltered
DeclarationOrderChanged
```

The generic Entity add and remove variants **exclude** concrete-subtype add and
remove; a surviving concrete subtype uses `EntityAltered`. Value Object
occurrence operations cover both top-level and nested occurrences. An add or
remove carries its structured identity alone and resolves its full declaration
through the retained endpoint; an alteration carries the identity plus a nonempty
field-delta sequence.

An As-Of Axis is a first-class location identified by its Entity and Temporal
Dimension, because its endpoint Attributes, framework ownership, and
physical-key consequences belong to the axis declaration rather than to an Entity
alteration. The dimension participates in axis identity, so changing it is a
removal and an addition. Derived primary-key Indices never receive Index
operations: they are not independently authored, and their changes are reported
through the causal primary-key Attribute or As-Of Axis operation.

`DeclarationOrderChanged` describes one local collection whose surviving
declarations changed relative order. Its `earlier` and `later` sequences contain
only identities present in **both** endpoints, so inserting a new member between
two existing ones is addition rather than reordering, and the later model is
never normalized back into the earlier order. Top-level Entity enumeration is
canonically identity-ordered and so is never reordered. Relationship ordering
terms, Index component order, and As-Of Axis dimension rank keep their own
semantic contracts and never become declaration-order operations.

### Declaration collection vocabulary

```text
entityAttributes
entityRelationships
entityValueObjects
entityIndices
valueObjectAttributes
nestedValueObjects
```

## Field deltas

Every delta carries its earlier and later **accepted** value, including absence
where the declaration's role admits it. A delta name has exactly one value type
wherever it appears, so one name serves every alteration that carries it.

### Field delta vocabulary

```text
StorageContainerChanged
PersistenceChanged
StorageLayoutChanged
InheritanceChanged
TypeChanged
StorageChanged
PrimaryKeyChanged
NullabilityChanged
MaximumLengthChanged
ReadOnlyChanged
OptimisticLockingChanged
MultiplicityChanged
DeclarationFormChanged
CardinalityChanged
JoinChanged
ReverseOfChanged
DependencyChanged
OrderingChanged
StartAttributeChanged
EndAttributeChanged
ComponentsChanged
UniquenessChanged
```

Each alteration draws from its own closed subset, and emits the applicable deltas
in the fixed order below.

| Alteration | Field deltas, in fixed order |
|---|---|
| `EntityAltered` | `StorageContainerChanged`, `PersistenceChanged`, `StorageLayoutChanged`, `InheritanceChanged` |
| `AttributeAltered` | `TypeChanged`, `StorageChanged`, `PrimaryKeyChanged`, `NullabilityChanged`, `MaximumLengthChanged`, `ReadOnlyChanged`, `OptimisticLockingChanged` |
| `ValueObjectOccurrenceAltered` | `StorageChanged`, `MultiplicityChanged`, `NullabilityChanged` |
| `ValueObjectAttributeAltered` | `TypeChanged`, `NullabilityChanged` |
| `RelationshipAltered` | `DeclarationFormChanged`, `CardinalityChanged`, `JoinChanged`, `ReverseOfChanged`, `DependencyChanged`, `OrderingChanged` |
| `AsOfAxisAltered` | `StartAttributeChanged`, `EndAttributeChanged` |
| `IndexAltered` | `ComponentsChanged`, `UniquenessChanged` |

Four of those deltas retain a **whole** accepted value rather than a fragment, so
that a combination the model cannot hold is unrepresentable in the description:
`InheritanceChanged` retains the complete Inheritance Metadata, so role, parent,
strategy, the table-per-hierarchy tag Column, and a concrete subtype's tag value
are never reported as contradictory parallel changes; `PrimaryKeyChanged` retains
the complete key value, so membership and generation cannot form an invalid pair;
`DeclarationFormChanged` retains both complete Relationship declarations and is
**exclusive**, admitting no accompanying Relationship delta, because the defining
and reverse forms do not expose the same fields; and `ComponentsChanged` retains
both ordered component tuples, because component order changes the physical
access path.

A Value Object occurrence's storage change is valid only for a top-level
occurrence, a nested one owning no independent Storage Location. A Value Object
scalar leaf has no Column, maximum length, key, read-only, locking, or generation
fact, which is why its delta union is the narrowest. The derived `frameworkOwned`
fact is never a parallel delta: the optimistic-locking and As-Of Axis operations
report its independent causes.

## Canonical operation order

Operations are ordered for **inspection**, reusing `m-metamodel`'s canonical
Model Location order. Entity Identity is the outer key; within one Entity the
member ranks are Entity, Attribute, Relationship, Value Object occurrence, Value
Object Attribute, As-Of Axis, Index; structured identities compare codepoint by
codepoint, Value Object containment paths compare lexicographically, and Valid
Time precedes Transaction Time.

Add, remove, and alter cannot tie at one logical identity, so the order carries
no operation-kind rank: a rename's independently identified removal and addition
stay in identity order rather than being forced removal-first. Every
`DeclarationOrderChanged` operation sorts after every declaration operation, by
its owner's Model Location key and then by collection.

Inspection order says nothing about executable order. A schema generator derives
its own dependency order, and the two are independent.

## Classification

A **Unilateral Evolution** preserves the addressed identities, input shapes,
target types, and result shapes of previously valid model-authored queries and
writes, and requires no destructive transformation of domain data or of
compatibility-bearing schema. Behavior may change behind that surface. A
**Coordinated Evolution** requires authoring, data, or rollout coordination.

Destructive means destructive to domain data or to compatibility-bearing schema —
not merely a statement whose SQL verb is `DROP`.

### Coordination reason vocabulary

```text
AuthoringSurfaceChangeRequired
DatabaseMigrationRequired
```

`AuthoringSurfaceChangeRequired` names a previously valid query or write shape
that must change; `DatabaseMigrationRequired` names a transition that cannot be
expressed as a prefix-safe Schema Delta without destructive transformation or a
staged compatibility mechanism. One operation may require both, and appears once
with both reasons in that order, so consumers never regroup duplicate entries.

The boundaries, each compared against **effective** facts rather than raw
declarations. Only concrete subtypes own rows (`m-inheritance`), so the stored
shape a boundary speaks about at a position is the one **both** editions denote
there: the concrete subtypes in its effective concrete set at either endpoint.
Every boundary phrased over an existing stored shape, over a write the later
edition must still accept, or over a value a later writer may store is silent
where that set is empty — whether the position composes no concrete subtype at
all, or the shape it denoted leaves it in the same edition — because a shape
arriving under the position is answered for where it arrives, a newly added
concrete subtype by its own addition, which creates it complete, and a surviving
one reparented in at its own inheritance alteration, and one departing is
answered for at the alteration that moves it. A boundary phrased
over a previously valid authored operation alone, such as a removed declaration
or a narrowing that reached the position, reads the earlier endpoint by itself;
what a read of a position denoting nothing still addresses are the members its
ancestry makes applicable.

- **Removal.** Removing any model-facing declaration requires coordination,
  because it invalidates a previously valid authored operation: an Entity, a
  concrete subtype, an Attribute, a Value Object occurrence or member, a
  Relationship direction, an As-Of Axis. Authored secondary Indices are the sole
  exception, because model-authored operations never address them. Whether the
  removal *also* requires database migration follows what becomes of the stored
  shape. One that takes its shape with it — an Entity, a concrete subtype, or a
  Relationship direction, which stores no value of its own — needs the authoring
  surface alone, because the objects the earlier edition addressed may be left in
  place. An abstract inheritance position stores nothing of its own and its
  members are stored by each descendant, so its removal leaves them behind and
  every surviving descendant reports what it loses on its own inheritance
  alteration. A **required** member cut out of a shape that survives needs both,
  because the surviving shape still demands a value the later model no longer
  describes and the object enforcing it must be relaxed or removed before a later
  write is accepted; a nullable one leaves a stored form the later edition simply
  stops writing. The verdict reads accepted required-ness rather than the
  physical object enforcing it, so it holds for a direct Column and an existing
  Structured Column alike — the mirror of the addition boundary below.
- **Addition.** Adding a nullable member is unilateral. Adding a **required**
  member to an existing stored shape requires coordination until a default and
  backfill contract makes existing data satisfy the later model — for scalar
  Attributes and Value Object members alike, whether they occupy a direct Column
  or an existing Structured Column. Where an insert the caller could author
  carries the value it needs the authoring surface too, because every previously
  valid insert omits an input the later model demands. A framework-owned member
  needs the database alone, since no caller ever supplied it, and so does any
  member arriving on an Entity whose family was already effectively `ReadOnly`,
  which has no previously valid insert to invalidate. A wholly new Entity may
  contain required members, because its parent addition creates a complete empty
  Table.
- **Value domain.** Within one unchanged Neutral Type, expanding the admitted
  domain is unilateral and contracting it requires coordination. Required to
  nullable, a widened String maximum length, and a removed length bound are
  unilateral; every reverse direction requires coordination.
- **Type and storage.** Every change to an accepted Neutral Type requires
  coordination, and the description infers no safe widening between type
  families. So does every change to an effective Table, Column, or structured
  storage location, because the two editions cannot address both locations
  through one compiled operation surface; authored forms normalizing to the same
  accepted Storage Location produce no change at all.
- **Keys.** Every change to primary-key membership or Primary-Key Generation
  requires coordination.
- **Write surface.** Making an editable Attribute read-only, or a caller-authored
  Attribute framework-owned, requires coordination; the inverses are unilateral
  where they need no destructive transformation. The gating behavior an
  optimistic version brings with it is not a second reason of its own: an
  Entity's concurrency control changing is a Behavioral Impact behind the
  preserved surface, and it is the member's own move between caller-authored and
  framework-owned that decides coordination, on an Entity whose family accepted
  caller writes in the earlier edition: one already effectively `ReadOnly`
  carried no input for the move to withdraw, while one that becomes read-only
  did. Persistence Mode follows the same
  directional rule over the whole family — `ReadWrite` to `ReadOnly` requires
  coordination, `ReadOnly` to `ReadWrite` is unilateral — and the root-owned
  change is reported once rather than repeated per descendant.
- **Value Objects.** Changing an occurrence between `ONE` and `MANY` requires
  coordination, because an authored path changes between one object and a
  collection. Occurrence nullability stays directional.
- **Relationships.** Adding one is unilateral and removing one requires
  coordination. An alteration is unilateral only while the preserved identity
  retains its effective target Entity and its One-versus-Many result shape; join,
  dependency, ordering, and source-side cardinality behavior may change behind
  that surface. Accompanying Attribute and Index changes remain independent
  operations with their own classifications.
- **Indices.** Every addition, removal, and alteration of an authored secondary
  Index is unilateral, including component and uniqueness changes: it affects
  only a rebuildable access path or enforcement rule, destroys no stored data,
  and invalidates no authored operation. It may change whether a write succeeds.
- **As-Of Axes.** Adding, altering, or removing an axis on an existing Entity
  requires coordination for both reasons: it changes the temporal operation
  surface, framework ownership of its endpoints, the derived physical primary
  key, or the bounds required of existing rows. Removal is not the mirror of a
  member removal that leaves a Column behind — the axis end Attributes leave the
  derived physical key, so the later logical identity is narrower than the one
  the surviving history was written under and that history collides beneath it.
  An axis on a wholly new Entity is part of the unilateral parent addition.
- **Inheritance.** An existing declaration is classified by its effective
  consequences, never automatically by a raw parent change. Interposing a new
  abstract subtype is unilateral when every earlier subtype-selection containment
  remains valid, each earlier position keeps compatible physical facts, and any
  inherited member additions are independently unilateral. A position leaving the
  ancestry withdraws the members that position declared from rows that stay where
  they are; each is classified at the descendant exactly as a member cut out of it
  would be, so a required one also requires database migration. Moving an existing
  subtype out of an earlier branch requires coordination, as do strategy, tag, or
  storage changes needing physical transformation. An abstract position whose role
  turns concrete adds a shape to the family and withdraws none, so every earlier
  narrowing stays valid and it is unilateral; the reverse withdraws the shape a
  narrowing denoted and requires the authoring surface, while leaving the rows
  carrying that discriminator value in place, as a concrete subtype's removal does.
- **Concrete subtypes.** Adding one is unilateral under either supported
  strategy.
- **Declaration order.** Reordering preserves the model-facing operation surface
  and is unilateral.

## Overlap-Visible Operations

An Overlap-Visible Operation may let the later edition store a value an earlier
edition cannot admit — the risk that exists only while two editions run against
one database. It is **narrower** than behavioral change and narrower than
coordination: a Unilateral Evolution names them, and a Coordinated Evolution
carries none, because it is not applied through this path at all.

The overlap-visible operations are making a member nullable, widening or removing
a String maximum length, and giving a family a new shape under
**table-per-hierarchy**, where a later writer can place a new discriminator value
in the shared Table that an earlier reader cannot admit. A family gains a shape
by an added concrete subtype, and equally by a surviving abstract position whose
role turns concrete: an abstract position owns no rows, so admitting it as a
concrete subtype introduces its discriminator value exactly as adding one does.
Under table-per-concrete-subtype neither is overlap-visible, because the new
shape occupies a separate Table the earlier edition never reads; and neither is a
shape whose family arrives whole around it, under either strategy, because
visibility is a claim about an earlier reader and the earlier edition holds no
position of that family, so neither its Table nor a selection through it. A
surviving position keeping the root it had stays in the family the earlier
edition already held; one taking another root is judged in the family it joins
on exactly the terms an added concrete subtype is, visible to whatever positions
of that family the earlier edition already held and to nobody where the family
arrives whole around it.

None of them is overlap-visible where no later writer can place the value: a
family whose later effective Persistence Mode is `ReadOnly` admits no writer at
all. A member expansion needs, in addition, a shape both editions denote to place
the value in, because it widens what an already stored shape admits rather than
introducing a shape. A unique-constraint violation, a DDL failure, and an
ordinary behavior difference are not overlap visibility.

## Behavioral Impacts

Both variants carry ordered Behavioral Impacts: endpoint-wide facts about what
changes behind the preserved surface. Each carries its earlier and later facts
and a nonempty `causedBy` sequence containing **all and only** the operations
whose changed facts contribute to it, deduplicated and in canonical operation
order. One operation may cause several impacts.

Impacts are derived from the two accepted models alone: an impact is emitted when
the semantic facts change even where current database contents would not exhibit
it, and no provider or database is consulted. They prescribe no severity,
remediation, retry, or rollout policy. They hold on scopes present in the
**earlier** endpoint, so a wholly new Entity's key, required members, and unique
Indices stay described by its own addition rather than expanded into impacts.

### Behavioral Impact vocabulary

```text
UniquenessEnforcementChanged
ValueAdmissibilityChanged
DeletePropagationChanged
ConcurrencyControlChanged
QueryResultMembershipChanged
QueryResultOrderingChanged
WriteCapabilityChanged
```

The alternatives are exhaustive **within their stated categories**, so the
absence of one asserts that its effective endpoint facts are equal. It is not a
claim to enumerate consequences outside this vocabulary.

| Impact | Scope | Endpoint facts |
|---|---|---|
| `UniquenessEnforcementChanged` | one surviving Entity | the canonically ordered set of secondary uniqueness rules, each an unordered Attribute set; Index identity and component order do not participate, equivalent rules collapse, and derived primary-key uniqueness is excluded |
| `ValueAdmissibilityChanged` | one surviving value-bearing path | Neutral Type, nullability, and maximum String length at a scalar leaf; nullability alone at a Value Object occurrence |
| `DeletePropagationChanged` | one surviving Relationship | the effective dependency policy, `Propagates` or `DoesNotPropagate` |
| `ConcurrencyControlChanged` | one surviving Entity | its model-derived behavior under the `optimistic` Concurrency Preference: `LockingFallback`, `VersionGated` naming the explicit version Attribute, or `TransactionTimeGated` naming the Transaction-Time start Attribute |
| `QueryResultMembershipChanged` | one surviving Entity or Relationship position | for an Entity, the effective concrete Entity set and Temporal Shape including its axis Attributes; for a Relationship, the target Entity and effective join |
| `QueryResultOrderingChanged` | one surviving Relationship | the normalized effective ordering terms, each with its target Attribute, Sort Direction, and Null Placement |
| `WriteCapabilityChanged` | one surviving Entity or Attribute | for an Entity, `Disabled` or `Enabled` carrying the effective `NonTemporal`, `TransactionTimeOnly`, or `Bitemporal` write shape — `Enabled` only where the family admits writes and the Entity is itself a write handle, which an abstract root and an abstract subtype are not (`m-inheritance`); for an Attribute, `FrameworkOwned`, `CallerInsertOnly`, or `CallerInsertAndUpdate` |

Impacts are ordered first by the closed variant order above, then by the
structured identity of their scope. That order never implies severity or
coordination status.

Four boundaries between the categories are normative. A join change that alters
which target rows are reached is membership, not delete propagation, though
changing a Relationship's target may cause both. Ordering is reported exclusively
through `QueryResultOrderingChanged`, and a value-domain change alone does not
cause it while the ordering rule is unchanged; declaration order, Index component
order, primary-key changes, unspecified physical row order, and caller-authored
Sort Keys are not model-defined result ordering. Member addition and removal stay
their own operations rather than becoming admissibility impacts, and occurrence
multiplicity stays structural. An Entity-level change in Persistence Mode or
temporal write shape dominates its members and suppresses the resulting Attribute
write impacts; where the Entity write surface is unchanged, a surviving Attribute
whose effective input capability changes receives its own impact.

An explicit `locking` Concurrency Preference always resolves to Locking and is
therefore unaffected by evolution. `ConcurrencyControlChanged`'s per-Entity grain
stays explicit even though the Optimistic Lock Facet is family-uniform, because a
coordinated hierarchy change can move a surviving Entity between effective
families — and a Coordinated Evolution retains its Behavioral Impacts alongside
its requirements.

## Consumer contract

**`m-schema-delta`.** Consumes a `UnilateralEvolution` and nothing else: it
reads the operations, both retained endpoints, and — through `m-storage-layout` —
their physical shapes. It never re-derives the MODEL difference, never
re-classifies an operation, and never asks whether an evolution "should" be
applied; all three questions are already answered by the value it is handed. What
the two physical shapes differ by is a different question and the generator's
own. A Coordinated Evolution is not one of its inputs, so a coordination reason
is never a schema-generation concern, and a Behavioral Impact is never one
either: an impact reports what changes behind the surface, which no statement
expresses.

The generator refusing a Dialect does not travel back here. Renderer support is a
deployment capability rather than a model-semantic fact, so an unsupported
physical operation leaves the Evolution unilateral.

**A non-relational consumer.** Consumes the same operations and produces no
statements at all — a schema-change surface showing a team what it is about to do
in the words it authored, or an adapter for a store with no tables. That second
consumer is the reason the description is at model altitude: a column-level change
set would serve only the relational generator and would duplicate what the Storage
Layout facet already knows.

**Every consumer.** Resolves the identities an operation names in the endpoint the
operation belongs to — the later endpoint for an addition or an alteration, the
earlier one for a removal — using the endpoints the Evolution retains rather than
a model of its own.

## Rule Set boundary

`m-model-evolution` contributes no Model Formation Rule Set, no Issue Codes, no
Model Compiler, and no facet. It consumes only **accepted** models, so every
question of validity is already settled before it runs; two accepted endpoints
are always describable, and there is no evolution the description refuses.
