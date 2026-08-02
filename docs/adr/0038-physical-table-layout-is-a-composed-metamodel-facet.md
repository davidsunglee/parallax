# Physical Table Layout is a composed Metamodel Facet

Physical table shape and logical member placement are owned by the deep
`m-storage-layout` module rather than by inheritance or by each storage
consumer. For every physical Table, its immutable Table Layout identifies the
container, provides the complete ordered Column Slot sequence and physical
primary key, preserves each slot's contributor provenance and Entity
applicability, resolves effective nullability, and locates each applicable
top-level member through a Direct Column or Document Path. Read projection,
write shaping, DDL derivation, fixture provisioning, and table read-back consume
that one view instead of reconstructing physical shape or reclassifying members.

Column order is table-wide and semantic. The canonical tiers are identity,
discriminator, domain, temporal, audit, then document. Declaration order remains
stable within a tier, but tiers take precedence over declaring ancestry. A
table-per-hierarchy layout considers the complete shared-table superset; each
table-per-concrete-subtype layout considers the concrete Entity's complete
ancestry-derived shape. The resulting order may place descendant domain
attributes before root-owned temporal or audit attributes. Preserving an older
per-ancestor or pre-capability column sequence as a prefix is not a contract.

A Column Slot records its physical column, tier, contributor, declaring owner,
effective nullability, and applicable Entity set. In conventional Columns
layout, each scalar Attribute contributes a direct slot and each top-level Value
Object contributes one Structured Column slot. In Relational Document Layout,
the root-owned layout contributes one shared Structured Column slot per governed
Table while every document-resident member points to that slot through its
canonical logical Document Path. The Physical Primary Key is an ordered
selection of designated slots across tiers: the model primary-key Attribute
slots followed by each temporal dimension's start Attribute slot. It never
truncates the key to the identity tier or restates independent columns.

The Direct Column role set in Relational Document Layout is closed: primary-key
Attributes, both endpoints of every accepted Relationship Join, temporal
Attributes, Audit Attributes, an explicit Non-Temporal optimistic-lock
Attribute, and the table-per-hierarchy tag remain direct. All other Attributes
and top-level Value Objects reside only in the shared Structured Column. A
standalone Entity or inheritance root owns the layout; descendants cannot repeat
or override it.

`Table(name)` is a name-only structural identity with exactly one independent
mapping owner: a standalone Entity, one complete table-per-hierarchy family
represented by its root, or one table-per-concrete-subtype concrete mapping.
Participants within one TPH family are not competing owners. A later independent
owner of an already-owned Table fails as
`storage-layout-table-mapping-collision` at its mapping `EntityLocation` with
the first owner's `EntityLocation` related. Within the uniquely owned Table,
two distinct contributors claiming one column fail as
`storage-layout-column-collision`; no storage consumer chooses a winner.
Inheritance continues to own `inheritance-materialization-key-collision`
because `familyVariant`, relationship views, and materialized object keys occupy
the result keyspace rather than physical table storage.

The module participates in both validation and compilation without changing
Model Formation's phase boundary. Its Rule Set receives only the Candidate
Metamodel and owns table-mapping and physical-column collisions, non-root layout
declarations, contradictory document-resident Column Overrides, and Indexes
that name document-resident Attributes. It obtains table boundaries and
accepted-join candidates from pure, total validation-time projections owned by
`m-inheritance` and `m-relationship`, not from their compiled facets. Those
projections return only bounded unambiguous facts; their owner Rule Sets report
malformed topology and relationships, while Storage Layout neither duplicates
those issues nor guesses. Mapping owners are visited in canonical Entity order
so equal Table values reject the later independent owner before Column
validation. This collaboration shares the necessary walks without introducing
validation-time facets or ordered Rule Set execution.

After every Rule Set succeeds, the `m-storage-layout` Model Compiler consumes
Compiled Metadata, the Inheritance Facet, and the Relationship Facet and
produces the immutable TableLayout Facet. Temporal axes, accepted Relationship
Joins, optimistic-lock facts, and Audit Metadata designate already declared
Attribute Identities for direct placement; absence leaves the corresponding
role empty. The compiler makes no validity decision and emits no issue. In
particular, `m-storage-layout` does not depend on `m-audit-provenance`; accepted
Audit Metadata is compiler input and audit behavior depends on the resulting
layout. The temporal `revisionInstantAttribute` alias of Transaction-Time start
therefore produces one temporal slot and no duplicate audit slot.

The direct dependency direction is:

```text
m-storage-layout --> m-metamodel
m-storage-layout --> m-model-formation
m-storage-layout --> m-inheritance
m-storage-layout --> m-relationship

m-sql --> m-storage-layout
m-audit-provenance --> m-storage-layout
```

Inheritance retains family topology, strategy, concrete applicability,
discriminator semantics, and ancestry. Relationship retains symmetric
relationship meaning and accepted joins. Storage Layout asks those questions
through validation-time projections during its Rule Set and through the
accepted facets during its Model Compiler, and owns only the composed
physical-table and member-placement answer.

`m-sql` consumes TableLayout directly for read projection and all keyed,
predicate, and batch DML physical ordering. `m-audit-provenance` consumes it
directly for audit-slot discovery and finalized assignment decoration. The
conformance family declares no behavioral edge: under its existing harness
exception, `m-case-format` exercises TableLayout for the reference oracle's
physical fixture/write cells and table shapes, while `m-conformance-adapter`
exercises it for model-derived DDL, fixture loading, and table-state read-back.
Batch planning remains expressed in semantic Attribute Identities and therefore
has no direct
`m-batch-write --> m-storage-layout` edge; `m-sql` applies physical order during
lowering. `m-dialect` formats already-selected columns and likewise does not
interpret TableLayout.

This keeps a small interface over the full storage-shape complexity. Separating
physical slots from logical placements lets one Structured Column carry many
members without leaking document-role classification into every consumer, while
still allowing future structural contributors to add an optional tier or slot
classification without coupling every consumer to that contributor.
