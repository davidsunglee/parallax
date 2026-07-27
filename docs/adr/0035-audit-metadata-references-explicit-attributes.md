# Audit Metadata references explicit attributes

Core Audit Metadata assigns provenance semantics to explicitly declared Attribute Identities rather than synthesizing hidden attributes during Model Formation. Its language-neutral attribute references use semantic names—`creationPrincipalAttribute`, `creationInstantAttribute`, `revisionPrincipalAttribute`, the Non-Temporal `revisionInstantAttribute`, the temporal `terminationPrincipalAttribute`, and the Bitemporal `stateChangePrincipalAttribute` / `stateChangeInstantAttribute`—independent of any frontend's property spellings.

Principal attribute references require unbounded neutral `string` attributes so opaque provider identities cannot be truncated, and instant attribute references require neutral `timestamp` attributes. Every applicable audit attribute is non-null except the temporal termination principal, which remains nullable until an explicit termination. A temporal revision instant resolves to the Transaction-Time start Attribute Identity rather than declaring duplicate storage.

A standalone Entity or inheritance root owns the declaration, every descendant inherits it unchanged, and a language frontend may offer concise audit authoring only by expanding that convenience into ordinary unresolved attribute declarations and Audit Metadata before formation, preserving the same accepted model a descriptor authors directly. Framework-owned audit attributes use the fixed `created_by`, `created_at`, `revised_by`, `revised_at`, `terminated_by`, `state_changed_by`, and `state_changed_at` physical columns where they apply, just as Python's framework-owned temporal attributes use fixed `from_z` / `thru_z` / `in_z` / `out_z` columns. The temporal `revised_at` alias therefore resolves to `in_z`, not a separate `revised_at` column. COR-36 introduces no independent column-customization path. This keeps collision validation, family-uniform provenance, frontend equivalence, and the Metamodel Interface's declared-facts contract visible while avoiding convention-dependent metadata mutation.

Frontend expansion appends generated audit attributes after the entity's existing scalar attributes, including generated temporal axes, preserving the pre-audit column sequence as a prefix. Their fixed relative order is creation principal, creation instant, revision principal, the Non-Temporal revision instant, the Bitemporal state-change principal and instant, and finally the temporal termination principal.

Audit Attributes are not indexed automatically. They participate in the
existing explicit Index Metadata grammar wherever that grammar permits, but
Audit Metadata introduces no implicit access path or audit-specific index
configuration.

Audit formation reuses the issue owner that already understands a defect.
The Python frontend rejects a collision with a generated audit property as
`entity-reserved-member-name`; the fixed resolver owns unresolved Attribute
Identity references; and `m-inheritance` continues to own member shadowing and
physical-column collisions. The `m-audit-provenance` Rule Set owns only
audit-specific invariants: whether each required Audit Metadata attribute
reference is present, whether an attribute applies to the Entity's temporal
shape, whether its Attribute has the required type and nullability, whether
one Attribute is assigned conflicting audit semantics, and whether Audit
Metadata is declared outside a standalone Entity or inheritance root. Its
closed Issue Code set is `audit-required-attribute-missing`,
`audit-attribute-inapplicable`, `audit-attribute-type`,
`audit-attribute-nullability`, `audit-attribute-conflict`, and
`audit-metadata-not-root-owned`.
