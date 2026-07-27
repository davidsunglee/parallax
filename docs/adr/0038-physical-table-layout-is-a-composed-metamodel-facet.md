# Physical Table Layout is a composed Metamodel Facet

Physical table shape is owned by the deep `m-storage-layout` module rather than
by inheritance or by each storage consumer. For every physical Table, its
immutable Table Layout identifies the container, provides the complete ordered
Column Slot sequence and physical primary key, preserves each slot's contributor
provenance and Entity applicability, and resolves effective nullability. Read
projection, write shaping, DDL derivation, fixture provisioning, and table
read-back consume that one view instead of reconstructing physical shape.

Column order is table-wide and semantic. The canonical tiers are identity,
discriminator, domain, temporal, audit, then document. Declaration order remains
stable within a tier, but tiers take precedence over declaring ancestry. A
table-per-hierarchy layout considers the complete shared-table superset; each
table-per-concrete-subtype layout considers the concrete Entity's complete
ancestry-derived shape. The resulting order may place descendant domain
attributes before root-owned temporal or audit attributes. Preserving an older
per-ancestor or pre-capability column sequence as a prefix is not a contract.

A Column Slot records its physical column, tier, contributing Attribute, Value
Object occurrence, or inheritance discriminator, declaring owner, effective
nullability, and applicable Entity set. The Physical Primary Key is an ordered
selection of designated slots across tiers: the model primary-key Attribute
slots followed by each temporal dimension's start Attribute slot. It never
truncates the key to the identity tier or restates independent columns. Two
distinct contributors claiming one column in the same Table fail Model Formation as
`storage-layout-column-collision`; no storage consumer chooses a winner.
Inheritance continues to own `inheritance-materialization-key-collision`
because `familyVariant`, relationship views, and materialized object keys occupy
the result keyspace rather than physical table storage.

The module participates in both validation and compilation without changing
Model Formation's phase boundary. Its Rule Set receives only the Candidate
Metamodel and emits `storage-layout-column-collision`. It obtains table
boundaries from a pure, total validation-time projection owned by
`m-inheritance`, not from the Inheritance Facet. That projection returns only
unambiguous standalone and family table groups; the Inheritance Rule Set reports
malformed or ambiguous topology, and Storage Layout neither duplicates those
issues nor guesses a table. This collaboration shares the topology walk without
introducing validation-time facets or ordered Rule Set execution.

After every Rule Set succeeds, the `m-storage-layout` Model Compiler consumes
Compiled Metadata and the Inheritance Facet and produces the immutable
TableLayout Facet. Temporal axes and Audit Metadata, when present, designate
already declared Attribute Identities for their tiers; absence leaves the
corresponding tier empty. The compiler makes no validity decision and emits no
issue. In particular, `m-storage-layout` does not depend on
`m-audit-provenance`; audit behavior depends on the resulting layout. The
temporal `revisionInstantAttribute` alias of Transaction-Time start therefore
produces one temporal slot and no duplicate audit slot.

The direct dependency direction is:

```text
m-storage-layout --> m-metamodel
m-storage-layout --> m-model-formation
m-storage-layout --> m-inheritance

m-sql --> m-storage-layout
m-audit-provenance --> m-storage-layout
```

Inheritance retains family topology, strategy, concrete applicability,
discriminator semantics, and ancestry. Storage Layout asks those questions
through the validation-time projection during its Rule Set and through the
Inheritance Facet during its Model Compiler, and owns only the composed
physical-table answer.

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

This keeps a small interface over the full storage-shape complexity while
allowing future structural contributors to add an optional tier or slot
classification without coupling every consumer to that contributor.
