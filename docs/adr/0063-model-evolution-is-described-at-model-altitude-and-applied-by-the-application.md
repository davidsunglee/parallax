# Model evolution is described at model altitude and applied by the application

Carrying a live tenant from one accepted Metamodel to the next is two deep
modules with a real seam between them. `m-model-evolution` exposes
`evolve(earlier: Metamodel | absent, later: Metamodel)`, returning the closed
choice of Unilateral Evolution or Coordinated Evolution: a total, ordered
description of every difference as Evolution Operations named in the model's
own terms. The result retains both accepted endpoints and names any
Overlap-Visible operations. An
Unilateral Evolution is the only kind a live tenant may apply through this
path: it requires no destructive schema or data transformation and preserves
the addressed identities, input shapes, target types, and result shapes of
previously valid model-facing operations, while permitting behavior to change
behind that surface. `m-schema-delta` exposes
`schema_delta(evolution: UnilateralEvolution, dialect: Dialect)`, resolves the
bound evolution against its later model's Storage Layout, and returns a Schema
Delta; Coordinated Evolution is not an accepted input. Provisioning a fresh
database is the unilateral evolution from no model, so one generator serves both.
The application applies the statements and only then publishes the new Model
Edition; Parallax never applies schema change itself.
The absent earlier endpoint is an explicit fresh-provisioning sentinel, never
an inference from an empty accepted model or physical-schema inspection. It
always produces Unilateral Evolution, with one canonical entity-level addition
for every target Entity: `ConcreteSubtypeAdded` for a concrete subtype and
`EntityAdded` for every other Entity role. Those parent operations suppress
their members, and provisioning carries no behavioral impacts or
overlap-visible operations because there is no surviving earlier scope. The
Schema Delta creates the complete target schema. The application owns the
precondition that this is a fresh physical target; conflicting existing objects
surface as ordinary native DDL failures.
Evolution between equal accepted models returns an `UnilateralEvolution` with
empty operations, behavioral impacts, and overlap-visible operations while
still retaining both endpoints. Its Schema Delta is empty. `evolve` therefore
remains total without a third no-evolution result or nullable return.

A Coordinated Evolution carries nonempty `coordination_requirements`, not
blockers: the evolution is valid, but each requirement associates an exact
Evolution Operation with structured reasons that unilateral application is
unavailable. It prescribes no migration procedure. A Unilateral Evolution can
carry no coordination requirement.
The closed reason vocabulary is `AuthoringSurfaceChangeRequired`, for a
previously valid query or write shape that must change, and
`DatabaseMigrationRequired`, for a transition that cannot be expressed as a
prefix-safe Schema Delta without destructive transformation or a staged
compatibility mechanism. One operation may require both; its own field deltas
carry the more detailed explanation.
`coordination_requirements` contains exactly one requirement for each operation
that requires coordination, in canonical operation order. The requirement
retains that operation and a nonempty reason set in fixed reason order, so an
operation requiring both kinds appears once and consumers never regroup
duplicate entries.

Both evolution variants carry ordered `behavioral_impacts`: endpoint-wide facts
whose closed alternatives are `UniquenessEnforcementChanged`,
`ValueAdmissibilityChanged`, `DeletePropagationChanged`,
`ConcurrencyControlChanged`, `QueryResultMembershipChanged`,
`QueryResultOrderingChanged`, and `WriteCapabilityChanged`. Each impact carries
its earlier and later facts and a nonempty, canonically ordered `caused_by`
operation sequence. The analysis is semantic rather than declaration-based: a
uniqueness impact ignores authored Index identity and component order, and
equivalent surviving unique Indices collapse to one enforcement rule.

Behavioral Impacts summarize continuity risks on scopes present in the earlier
endpoint rather than expanding every declaration inside a parent addition. A
wholly new Entity's key, required members, and unique Indices therefore remain
described by `EntityAdded` without separate impacts. A Unilateral Evolution also
carries ordered `overlap_visible_operations`, naming operations that may let the
later edition store a value an earlier edition cannot admit. These payloads
prescribe no retry, severity, remediation, or rollout policy.
They are derived only from the two accepted models: an impact is emitted when
the semantic facts change even if current database contents would not exhibit
it, and `evolve` performs no provider or database call.
The closed alternatives are exhaustive within their stated categories, so the
absence of one category asserts that its effective endpoint facts are equal; it
does not mean the analysis omitted a possible known change. This is not a claim
to enumerate consequences outside the closed Behavioral Impact vocabulary.
`UniquenessEnforcementChanged` is emitted once per surviving Entity whose
semantic set of authored secondary uniqueness rules differs. Its `earlier` and
`later` values are canonically ordered sets of `UniqueTuple` values, each itself
a canonical identity-ordered representation of an unordered Attribute set;
Index identity and component order do not participate. Its `caused_by` sequence
contains every causal Index operation. Derived primary-key uniqueness is
excluded.
`ValueAdmissibilityChanged` is emitted once per surviving value-bearing path
whose accepted domain differs. Scalar Attribute and Value Object leaf facts
contain Neutral Type, nullability, and maximum String length where applicable;
top-level and nested Value Object occurrence facts contain nullability alone.
Member addition and removal remain their own operations, occurrence multiplicity
remains structural, and defaulting behavior is outside this impact.
`DeletePropagationChanged` is emitted once per surviving Relationship Identity
whose effective dependency policy changes. Its `earlier` and `later` facts are
the closed values `Propagates` and `DoesNotPropagate`; the retained endpoint
models already identify the relationship target. A join change that alters which
target rows are reached belongs to `QueryResultMembershipChanged`, not delete
propagation, while changing a relationship's target may cause both impacts.
`ConcurrencyControlChanged` is emitted once per surviving Entity Identity whose
model-derived behavior under the `optimistic` Concurrency Preference changes.
Its endpoint facts are `LockingFallback`, `VersionGated` carrying the explicit
version Attribute Identity, or `TransactionTimeGated` carrying the
Transaction-Time start Attribute Identity. This states whether reads use shared
locks and writes use no gate, or reads avoid shared locks and writes use the
named gate. An explicit `locking` preference always resolves to Locking and is
therefore unaffected by model evolution. The per-Entity grain remains explicit
even though the Optimistic Lock Facet is family-uniform: a coordinated hierarchy
change can move a surviving Entity between effective families, and Coordinated
Evolution retains Behavioral Impacts alongside its coordination requirements.
`QueryResultMembershipChanged` compares the reusable, predicate-free selection
rules of surviving query positions. Its scope is the closed choice of an Entity
Selection, identified by Entity Identity, and a Relationship Selection,
identified by Relationship Identity. Entity endpoint facts contain the effective
concrete Entity set and Temporal Shape, including axis Attribute Identities;
Relationship endpoint facts contain the target Entity Identity and effective
Relationship Join. Changes to an authored predicate's meaning after a type or
surface change are outside this category, while ordering is reported exclusively
through `QueryResultOrderingChanged`.
`QueryResultOrderingChanged` is emitted once per surviving Relationship Identity
whose normalized effective `order_by` sequence changes. Its endpoint facts are
the ordered `RelationshipOrder` values, each carrying its target Attribute
Identity, Sort Direction, and Null Placement. Declaration order, Index component
order, primary-key changes, unspecified physical row order, and caller-authored
Object Query Sort Keys are not model-defined result ordering. A value-domain
change alone does not cause this impact when the relationship ordering rule is
unchanged.
`WriteCapabilityChanged` has the closed scope of Entity Writes, identified by
Entity Identity, and Attribute Writes, identified by Attribute Identity. Entity
endpoint facts are `Disabled` or `Enabled` carrying the effective
`NonTemporal`, `TransactionTimeOnly`, or `Bitemporal` write shape. Attribute
endpoint facts are `FrameworkOwned`, `CallerInsertOnly`, or
`CallerInsertAndUpdate`: generated primary keys, optimistic versions, Audit
Attributes, and As-Of Axis endpoints are framework-owned; application-assigned
primary keys and read-only Attributes are insert-only; ordinary editable
Attributes admit both caller insert and update input. An Entity-level change in
Persistence Mode or temporal write shape dominates its members and suppresses
the resulting Attribute impacts. When the Entity write surface is unchanged,
surviving Attributes whose effective input capability changes receive their own
impact.
Behavioral Impacts are ordered first by their closed variant order as listed
above and then by the structured identity of their scope. Each `caused_by`
sequence contains all and only Evolution Operations whose changed facts
contribute to that impact, deduplicated and ordered by canonical Evolution
Operation order. One operation may cause several impacts. Impact order never
implies severity or coordination status.

The evolution is described at model altitude because the differ has more than
one consumer: classification walks its operations, a schema-change surface
shows a team what it is about to do in the words it authored, and a
non-relational adapter can consume the same operations and produce no table
statements. A column-level change set would serve only the relational generator
and duplicate what the Storage Layout facet already knows. The evolution
retains the later Metamodel so the generator cannot accidentally be handed an
unrelated target; a private physical delta separates resolution from rendering
inside the generator. That private physical-operation algebra owns executable
dependency order; a dialect renderer receives primitive syntax facts and is
selected by composition rather than by branching on a dialect name.
Physical operations form a dependency graph whose deterministic topological
sort produces statement order. A Table creation precedes every operation on
that Table's Columns and Indices; a Column addition precedes every new Index
that references it; and creation of an altered Index's target definition
precedes removal of its earlier definition. Statements emitted for one physical
operation remain contiguous and preserve renderer order. Independent operations
use stable physical-location and operation-kind tie-breakers rather than a
global phase order.
The private physical-operation algebra is the closed choice of `CreateTable`,
`AddColumn`, `ExpandColumnDomain`, `CreateIndex`, and `DropIndex`.
`CreateTable` carries the complete target Table Layout, including Columns and
the inline derived primary key but excluding authored secondary Indices.
`AddColumn` carries its target Column Slot. `ExpandColumnDomain` carries the
earlier and later physical Column facts and may only relax nullability, widen a
bounded String, remove its bound, or combine those expansions; it is not a
generic column alteration. Index operations carry the target or earlier
Physical Index definition respectively. Schema-neutral unilateral operations
lower to no physical operation. Drop-table, drop-column, rename,
primary-key-alteration, and arbitrary-SQL variants are deliberately absent
because they cannot arise from Unilateral Evolution.
Before rendering, `schema_delta` checks the complete physical plan against the
selected Dialect. Its successful return type is only `SchemaDelta`. If any
operation is unsupported, it raises one atomic
`UnsupportedSchemaEvolutionError` containing the Dialect Identity and the
complete nonempty sequence of `UnsupportedSchemaOperation` records in
deterministic physical-operation order. Each record carries the operation kind,
physical location, and its causal Evolution Operations in canonical operation
order. No partial Schema Delta is returned. This does not reclassify the
dialect-independent Unilateral Evolution as coordinated; renderer support is a
deployment capability rather than a model-semantic fact.
Relationship operations still describe accepted local
declarations, but unilateral classification compares the effective relationship
shape so a preserved relationship identity may not silently change its target
Entity or One-versus-Many result shape. `m-model-evolution` therefore depends on
`m-inheritance` and `m-relationship` as well as `m-metamodel`; it never
re-derives either facet.

An existing inheritance declaration is classified by its effective consequences,
not automatically by a raw parent change. Interposing a new abstract subtype is
unilateral when every earlier subtype-selection containment remains valid, each
earlier position keeps compatible physical facts, and any inherited member
additions are independently unilateral. A position leaving the ancestry
withdraws the members that position declared from rows that stay where they
are, and each is classified at the descendant exactly as a member cut out of it
would be, so a required one also requires database migration. Queries narrow to
named Entity positions whose effective concrete sets are compared; they do not
encode direct hierarchy edges. Moving an existing subtype out of an earlier
branch requires coordination because a narrowing through that branch becomes
invalid, as do strategy, tag, or storage changes that require physical
transformation.
Only concrete subtypes own rows, so the stored shape a classification speaks
about at a position is the one both editions denote there. That set is empty
where the position composes no concrete subtype, and equally where the shape it
denoted leaves it in the same edition, reparented out from under it or removed
outright. Every classification phrased over stored rows, over a write the later
edition must still accept, or over a value a later writer may store is therefore
silent about such a position — a required member arriving on it or cut out of it
has no row to backfill and no insert the later model still demands the value of,
a write flag moving over it withdraws no caller input, contracting a member's
admitted value domain reaches no stored value, and moving it between branches or
Tables carries no data across. Nothing on it is Overlap-Visible either, which is
a claim about a later writer and so is equally silent on a family the later
edition holds read-only. A shape arriving under the position is answered for
where it arrives — a newly added concrete subtype by its own addition, which
creates it complete, and a surviving one reparented in at its own inheritance
alteration — and one departing is answered for at the alteration that moves it,
so neither is this position's to report. What a read of it still
addresses are the members its ancestry makes applicable, so losing one of those
remains an authoring surface change.
Adding a concrete subtype is unilateral under either supported inheritance
strategy, and so is turning a surviving abstract position concrete, which adds a
shape to the family and withdraws none. Both are Overlap-Visible under
table-per-hierarchy because a later writer can place a new discriminator value in
the shared Table that an earlier reader cannot admit; an abstract position owns
no rows, so admitting it as a concrete subtype introduces its discriminator value
exactly as adding one does. Neither is Overlap-Visible under
table-per-concrete-subtype because the new shape occupies a separate Table the
earlier edition never reads, nor where the later family's effective Persistence
Mode is `ReadOnly`, because then no writer exists to place that value, nor where
the family arrives whole around the shape, because then no earlier reader holds a
position of it — which is what a surviving position keeping the root it had
distinguishes from one taking another.

Attribute classification likewise compares the effective caller contract rather
than treating a raw flag change as decisive. Making an editable Attribute
read-only, or changing a caller-authored Attribute into a framework-owned one,
requires coordination because it invalidates an existing write operation. The
inverse changes are unilateral when they require no destructive physical
transformation; changing optimistic-locking behavior alone does not require
coordination.
Persistence Mode is an Entity alteration classified by the same directional
rule over the whole family: `ReadWrite` to `ReadOnly` requires coordination
because it removes valid persistence operations, while `ReadOnly` to `ReadWrite`
is unilateral. The root-owned change is reported once rather than repeated for
each descendant whose effective mode changes.
Changing an accepted declaration's effective Table, Column, or structured
storage location requires coordination because the two editions cannot address both
locations through the same compiled operation surface. The evolution reports a
storage field change on the surviving logical declaration; authored forms that
normalize to the same accepted Storage Location produce no change.
Every change to an Attribute's accepted Neutral Type requires coordination because it
changes accepted operands, write inputs, or decoded result values. The differ
does not infer safe widening between type families; String maximum length is a
separate field whose widening may be unilateral.
Every change to primary-key membership or Primary-Key Generation also requires
coordination. The change remains a precise field delta on the surviving
Attribute, but it changes physical constraints, entity identity, lookup shape,
or caller-supplied insert inputs and therefore blocks the unilateral path.
For constraints within one unchanged Neutral Type, expanding the admitted value
domain is unilateral and contracting it requires coordination. Making an Attribute
nullable, increasing its String maximum length, or removing that limit is also
Overlap-Visible; reversing any of those changes requires coordination.

Evolution matches declarations by structured identity and never guesses a
rename; a renamed declaration is one removal and one addition until the model
has an authored identity that survives renaming. Adding or removing a whole
declaration suppresses operations for its contained declarations, and one
alteration groups the closed, canonically ordered field changes at one logical
location. An Entity parent operation therefore suppresses operations for all of
its members, a Value Object occurrence parent operation suppresses its nested
members, and adding a concrete subtype is represented by `ConcreteSubtypeAdded`
rather than a generic `EntityAdded`. The operation sequence is ordered by canonical model location for
inspection, independently of the executable dependency order the schema
generator derives. The later Metamodel is never normalized against its
predecessor: declaration reordering is reported honestly but, where it
preserves the model-facing operation surface, is unilateral and produces no schema
statement. Reordering compares the relative order of only those declaration
identities that survive in both endpoints, so inserting a new member between two
existing members is addition rather than reordering. A nullable Attribute may be
inserted anywhere in authored order; database catalog column ordinal is not part
of schema satisfaction.
The closed Evolution Operation algebra is `EntityAdded`, `EntityRemoved`,
`EntityAltered`, `ConcreteSubtypeAdded`, `ConcreteSubtypeRemoved`,
`AttributeAdded`, `AttributeRemoved`, `AttributeAltered`,
`ValueObjectOccurrenceAdded`, `ValueObjectOccurrenceRemoved`,
`ValueObjectOccurrenceAltered`, `ValueObjectAttributeAdded`,
`ValueObjectAttributeRemoved`, `ValueObjectAttributeAltered`,
`RelationshipAdded`, `RelationshipRemoved`, `RelationshipAltered`,
`AsOfAxisAdded`, `AsOfAxisRemoved`, `AsOfAxisAltered`, `IndexAdded`,
`IndexRemoved`, `IndexAltered`, and `DeclarationOrderChanged`. The generic
Entity add/remove variants exclude concrete-subtype add/remove; a surviving
concrete subtype uses `EntityAltered`. Value Object occurrence operations cover
both top-level and nested occurrences. Add/remove operations carry their
structured identity and resolve their declaration through the retained endpoint;
alter operations carry the identity and a nonempty, canonically ordered field-
delta sequence. The algebra covers the accepted Metamodel Interface as it exists;
a later metamodel feature such as Attribute defaults extends its owning delta
algebra when that feature lands.
`EntityAltered` carries the closed, fixed-order delta union
`StorageContainerChanged`, `PersistenceChanged`, `StorageLayoutChanged`, and
`InheritanceChanged`. Each delta carries its earlier and later accepted value,
including absence where the Entity's role admits it. `InheritanceChanged`
retains the complete `InheritanceMetadata` value, so role, parent, strategy, the
table-per-hierarchy tag Column, and a concrete subtype's tag value cannot be
reported as contradictory parallel changes. Child declarations, As-Of Axes, and
declaration order retain their own operations; optimistic locking remains an
Attribute fact.
`AttributeAltered` carries the accepted field-order delta union `TypeChanged`,
`StorageChanged`, `PrimaryKeyChanged`, `NullabilityChanged`,
`MaximumLengthChanged`, `ReadOnlyChanged`, and `OptimisticLockingChanged`. Every
delta carries its earlier and later accepted value. `PrimaryKeyChanged` retains
the complete `NotPrimaryKey | PrimaryKey(PrimaryKeyGeneration)` value so key
membership and generation cannot form an invalid combination. The derived
`framework_owned` fact is not a parallel delta: optimistic-locking and As-Of
Axis operations report its independent causes, while `WriteCapabilityChanged`
reports the resulting caller-facing behavior.
`ValueObjectOccurrenceAltered` carries `StorageChanged`,
`MultiplicityChanged`, and `NullabilityChanged`, each with earlier and later
values in that fixed order. Storage change is valid only for a top-level
occurrence because a nested occurrence has no independent Storage Location.
`ValueObjectAttributeAltered` carries only `TypeChanged` and
`NullabilityChanged`. A Value Object scalar leaf has no Column, maximum length,
key, read-only, locking, or generation fact. Child changes and declaration order
remain separate operations.
`RelationshipAltered` carries the closed delta union
`DeclarationFormChanged`, `CardinalityChanged`, `JoinChanged`,
`ReverseOfChanged`, `DependencyChanged`, and `OrderingChanged`.
`DeclarationFormChanged` retains the complete earlier and later declaration as
`DefiningRelationshipFacts | ReverseRelationshipFacts` and is exclusive: no
other Relationship delta accompanies it. Otherwise, applicable deltas are
emitted in the order listed and each carries its earlier and later value.
Defining Relationships own cardinality, join, and dependency; Reverse
Relationships own `reverseOf`; both forms own ordering. Classification and
behavioral-impact derivation compare the symmetric effective Relationship facet
rather than treating the two declaration forms as though they exposed identical
fields.
Evolution Operations use the repository's existing canonical Model Location
order for inspection: Entity, Attribute, Relationship, Value Object occurrence,
Value Object Attribute, As-Of Axis, and Index. Entity Identity is the outer key;
structured identities compare codepoint by codepoint, Value Object containment
paths compare lexicographically, and Valid Time precedes Transaction Time.
`DeclarationOrderChanged` operations follow all declaration operations and sort
by owner identity, collection kind, and containment path. Add, remove, and alter
cannot tie at one logical identity. A rename's independently identified removal
and addition therefore remain in identity order rather than forcing removal
first. This inspection order does not constrain executable schema ordering.
One `DeclarationOrderChanged` operation describes each reordered local
collection. Its location is the closed choice of Entity Attributes, Entity Value
Objects, Entity Relationships, Entity Indices, Value Object Attributes, or
Nested Value Objects, with the owning Entity or Value Object Identity. Its
`earlier` and `later` sequences contain only declaration identities present in
both endpoints and are emitted only when their relative order differs. Top-level
Entity enumeration is canonically identity-ordered. Relationship `order_by`,
Index component order, and As-Of Axis dimension rank retain their distinct
semantic contracts and never become declaration-order operations.

An As-Of Axis is a first-class evolution location identified by its Entity and
Temporal Dimension, with added, removed, and altered operations. It is not
buried in an Entity alteration because its endpoint Attributes, framework-owned
behavior, and physical-key consequences belong to the axis declaration. A
parent Entity addition or removal still suppresses its child axis operations.
Adding or altering an axis on an existing Entity requires Coordinated Evolution:
it changes the temporal operation surface, framework ownership of its endpoints,
the derived physical primary key, or the valid bounds required of existing rows.
Changing Temporal Dimension is a removal and addition because the dimension is
part of axis identity. An axis on a wholly new Entity remains part of the
unilateral parent addition.
`AsOfAxisAltered` carries the closed, fixed-order delta union
`StartAttributeChanged` and `EndAttributeChanged`. Each delta carries the
earlier and later Attribute Identity. Changing both endpoints emits both deltas
in that order; changing the Temporal Dimension cannot be an alteration because
the dimension participates in axis identity.

Removing any model-facing declaration requires Coordinated Evolution because it
invalidates a previously valid authored operation. This includes an Entity,
Concrete Subtype, Attribute, Value Object occurrence or member, Relationship
direction, and As-Of Axis. Authored secondary Indices are the sole exception
because model-authored operations never address them.
Whether a removal ALSO requires database migration follows what becomes of the
stored shape. A removal that takes its whole stored shape with it — an Entity, a
Concrete Subtype, or a Relationship direction, which stores no value of its own
— requires the authoring surface alone, because the objects the earlier edition
addressed may simply be left in place. An abstract inheritance position stores
nothing of its own either, and the members it handed down are stored by each
descendant, so its removal leaves them behind: every surviving descendant
reports what it loses on its own inheritance alteration, by the member rule
below. A member cut out of a stored shape that
SURVIVES is directional in the same fact its addition is: removing a required
Attribute, Value Object occurrence, or Value Object member also requires
database migration, because the surviving shape still demands a value the later
model no longer describes and the object enforcing it must be relaxed or removed
before a later write is accepted, while removing a nullable one leaves a stored
form the later edition simply stops writing. The rule reads the accepted
required-ness rather than the physical object that happens to enforce it, so it
holds whether the member occupied a direct Column or an existing Structured
Column — exactly as the addition rule does, and for the same reason: this is a
model-altitude classification that consults no Storage Layout.
Removing an As-Of Axis always requires both, and the sharper consequence is not
a Column. Its end Attributes contribute to the derived physical primary key, so
the later logical identity is narrower than the one the surviving rows were
written under and that history collides beneath it; no prefix of a Schema Delta
reconciles that without transforming the rows themselves.

The Schema Delta is an immutable value containing its ordered dialect statements
as plain strings and an ordered `createdIndices` provenance sequence. Statements
have no public wrapper or per-statement causal metadata: the physical-operation
algebra stays private, while the applying application already holds the
Evolution and observes the failing statement. Created-Index provenance is the
sole exception because it must support diagnosis after application. Each
provenance item retains
the Physical Index Name, physical Table, logical Index Identity, and uniqueness
for one newly created Index. Fresh provisioning creates each Table
with all of its target Columns and derived primary key, then creates every
authored secondary Index as a separate, explicitly named statement; an
incremental delta uses the same index form. Each Physical Index Name is
`pxi_<readable-prefix>_<fingerprint>`. The readable input concatenates the
physical Table, complete declaring Entity Identity, authored Index name, and a
unique/non-unique marker; ASCII letters are lowercased, digits are retained,
each maximal remaining run becomes one underscore, surrounding underscores are
trimmed, and an empty result becomes `index`. The fingerprint is the first 128
bits of SHA-256 over a versioned sequence of length-prefixed UTF-8 fields for
the physical Table, the structured declaring Entity Identity, authored Index
name, ordered structured Attribute Identities, and uniqueness, rendered as 32
lowercase hexadecimal characters. Only the readable prefix is truncated to
satisfy the Dialect's byte limit; the fingerprint is never truncated. The
generator rejects a collision between distinct physical definitions across all
earlier and later Indices that can coexist during any statement prefix rather
than silently renaming either definition. A definition's name is therefore
stable independently of other Indices in the model.
Name collision raises one aggregated `PhysicalIndexNameCollisionError` carrying
the Dialect Identity and every collision group in Physical Index Name order.
Each group retains the shared Physical Index Name and at least two colliding
definitions in canonical logical-identity order; each definition names its
physical Table, logical Index Identity, ordered components, uniqueness, and
whether it occurs in the earlier endpoint, later endpoint, or both. This is a
defensive backstop for an unexpected 128-bit fingerprint collision, not an
ordinary control path or a dialect-capability error.
This lets a host correlate a later unique-index violation with the rollout
without exposing the generator's internal physical-operation algebra, and gives
an altered definition a distinct name so its target Index can be created and
validated before the earlier Index is dropped.
Every addition, removal, or alteration of an authored secondary Index is
unilateral, including changes to its components or uniqueness. Such a change
affects only a rebuildable physical access path or enforcement rule, destroys no
stored domain data, and invalidates no earlier model-authored operation. It may
change whether a write succeeds. An alteration creates the target definition
first and drops the earlier Index only after target creation succeeds. If the
target Index is unique, its creation is the authoritative validation of existing
data; the generator performs no preflight data query. Failure leaves the earlier
definition intact and prevents publication.
`IndexAltered` carries the closed, fixed-order delta union `ComponentsChanged`
and `UniquenessChanged`. The component delta retains the earlier and later
nonempty ordered Attribute Identity tuples because component order changes the
physical access path. The uniqueness behavioral impact independently treats a
tuple as semantically unordered. If both fields change, both deltas appear in
the order above. An authored Index name participates in `IndexIdentity`, so a
rename is `IndexRemoved` followed by `IndexAdded`, never an alteration.
Derived primary-key Indices never receive Index evolution operations because
they are not independently authored. Their changes are reported through the
causal primary-key Attribute or As-Of Axis operation, while a parent Entity
addition owns a newly derived key; the later Storage Layout supplies the
physical primary key to the schema generator. A destructive migration therefore
means a destructive change to domain data or compatibility-bearing schema, not
merely a statement whose SQL verb is `DROP`.

Schema Delta statement order is prefix-safe: every successfully applied prefix
leaves the earlier edition operable and destroys no domain data. The guarantee
permits the enforcement and outcome differences already allowed by Unilateral
Evolution; it does not publish the later edition until every statement succeeds.
Statements are deterministic but deliberately not idempotent and never suppress
an unexpected existing or missing object with `IF EXISTS` or `IF NOT EXISTS`.
Native failures remain visible. The application owns its migration ledger and,
after an ambiguous interruption, reconciles actual schema state before resuming
or publishing.

Storage-neutral does not by itself mean unilateral. Adding a Relationship is
unilateral, removing one requires coordination, and an alteration is unilateral only while every
preserved relationship identity retains its target Entity and One-versus-Many
result shape. Join, dependency, ordering, and source-side cardinality behavior
may change behind that surface; Attribute and Index changes accompanying the
Relationship change remain independent Evolution Operations with their own
classifications. Value Object lowering follows accepted Storage Layout rather
than flattening leaves: under conventional Columns layout one top-level
occurrence owns one Structured Column, while Relational Document Layout uses
its existing shared Structured Column. A leaf or nested occurrence therefore
changes no physical Column, but adding one as required still requires coordination
because existing stored documents would not satisfy the later model.

Adding a required member to any existing stored shape requires coordination
until a separate default and backfill contract makes the existing data satisfy
the later model. This applies to scalar Attributes and to Value Object members
regardless of whether they occupy a direct Column or an existing Structured
Column. Nullable additions are unilateral. A wholly new Entity may contain
required members because its parent addition creates a complete empty Table and
suppresses separate child operations.

Changing a top-level or nested Value Object occurrence between `ONE` and `MANY`
requires coordination because an existing authored path changes between one
object and a collection. Occurrence nullability remains directional: required
to nullable is unilateral and Overlap-Visible, while nullable to required
requires coordination.

Applying schema change stays with the application because the generator returns
results rather than producing effects, because schema statements are not
transactional on every adapter, and because a tenant runs many processes whose
handles would otherwise race to migrate the same database on the request path.
The alternatives were leaving schema change entirely external, which makes
every service reverse-engineer table layouts the framework already compiled,
and one module for evolution and statements together, which would hand the
differ a dependency on dialect and layout it does not need and force any future
non-relational consumer through relational DDL.

An authored unique Index is unilateral even though installing it can reject
existing data and, once installed, can reject a write made under an earlier
edition. The application publishes no edition when index creation fails.
Parallax later reports a write failure as facts — the unique-violation category,
the violated Physical Index Name, native diagnostics, and the transaction's
Adopted Edition — without consulting the provider or retrying. The host owns
rollout correlation and any replay of the whole use case because only it knows
whether its non-database effects are safe to repeat.
The runtime `DatabaseError` contract therefore carries the optional violated
Physical Index Name in addition to its neutral category, native code, and native
diagnostics. Primary-key or unrelated uniqueness failures may name a physical
object absent from `createdIndices`; absence of a match is an ordinary negative
correlation result, not an error. Other overlap-visible failures already surface
through `InvalidData` with logical Entity, member, path, and rejected-value
facts. Other Behavioral Impacts describe outcomes or logical validation rather
than a database failure whose physical identity needs translation, so Schema
Delta exposes no additional provenance for them.
`m-dialect` owns `PhysicalIndexName` as a small validated physical-identifier
value and owns dialect identifier limits, allowing both `m-schema-delta` and
`m-db-error` to depend downward on the same type. `m-schema-delta` owns the
deterministic naming policy. A concrete database adapter extracts an available
name from structured driver diagnostics and passes it across the port boundary;
`m-db-error` preserves it without parsing message text. `m-dialect` performs
neither driver access nor rollout correlation.

The compatibility corpus adds one pure `evolution` case shape. Its
`when.evolve` action names an earlier model descriptor or explicit absence and a
later model descriptor. `then.evolution` asserts the complete result together:
kind, ordered operations, ordered Behavioral Impacts, ordered Overlap-Visible
Operations, and coordination requirements. A unilateral expectation also
carries `then.schema`, keyed by Dialect Identity. Each dialect value is the
closed choice of `delta`, containing that dialect's complete ordered statements
and `createdIndices`, or `unsupported`, containing the complete ordered
Unsupported Schema Operations. Statement count and support may differ between
dialects; evolution DDL therefore does not use the ordinary corpus convention
that pairs corresponding dialect texts inside one statement entry. A
coordinated expectation must omit `then.schema`. Splitting one transition across
classification-only or operation-only case shapes is not conforming because the
returned Evolution is one internally consistent value.
For every unilateral case, the keys under `then.schema` must equal the complete
supported Dialect catalog. The harness invokes `schema_delta` for every matrix
cell and asserts either the complete successful delta or the complete
unsupported-operation error; an omitted dialect is never an implicit skip.
Adding a Dialect therefore makes every unilateral evolution case incomplete
until its expected cell is authored. Coordinated cases remain dialect-independent
because their value cannot be passed to `schema_delta`.

The portable proof includes at least one witness for every Evolution Operation,
field delta, Behavioral Impact, coordination reason, and private physical
operation a pair of model descriptors can express. A name only an accepted
Metamodel reaching `m-metamodel` directly can produce is witnessed by the
implementation's own suite instead, and the corpus proves it unreachable rather
than asserting the exemption. `AsOfAxisAltered` and its two deltas are that
case: a descriptor derives every As-Of Axis from its Temporality Profile with
framework-fixed endpoint Attributes, so two descriptors agreeing on an axis
position agree on its endpoints too. They stay in the closed vocabulary because
the accepted Metamodel admits endpoints no descriptor can spell, and a total
description of two such models needs the name.
Directional boundaries exercise both directions where classification differs,
including nullability, maximum length, persistence, effective caller write
ownership, Value Object occurrence nullability, and member removal from a
surviving stored shape. Structural witnesses
cover rename as removal plus addition, parent suppression, equal-model
evolution, provisioning, genuine declaration reorder, and insertion without
reorder. Inheritance and layout witnesses distinguish table-per-hierarchy from
table-per-concrete-subtype addition and Columns from Relational Document Layout.
Schema witnesses include an empty delta, dependency order, create-before-drop
Index replacement, `createdIndices`, and aggregation of multiple unsupported
operations. Adapter integration additionally proves that a unique violation
retains its Physical Index Name and correlates with newly created unique-Index
provenance. These obligations do not require their Cartesian product; focused
implementation tests may compose invariants beyond the portable witnesses.
Every supported Dialect also has a real-backend, non-mock contract test for its
declared maximum Index-identifier length. The test applies a generated name
exactly at the limit and inspects the database catalog to prove the backend
preserved it exactly; a long readable input proves truncation remains within the
limit without changing the fingerprint suffix. Because generated Physical Index
Names are ASCII, byte- and character-count limits agree for this contract. The
collision detector has a focused synthetic unit proof independent of this live
boundary test.
