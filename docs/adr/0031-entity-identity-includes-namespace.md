# Entity identity includes namespace

An Entity Identity is the language-neutral `(namespace, name)` pair, unique
within one Metamodel. Its canonical external spelling is
`<namespace>.<name>`, or the bare `<name>` when namespace is absent; a namespace
may contain dot-separated segments, while an entity name may not contain a dot
and an empty namespace is invalid. Consequently `sales.Order`, `billing.Order`,
and an unnamespaced `Order` are three distinct identities.

Relationships, inheritance parents, operations, formation indexes, and
compiled facets resolve to Entity Identity rather than carrying bare names.
This belongs to core because descriptor namespaces and cross-entity references
must mean the same thing in every implementation. A language frontend may bind
an identity to its native realization—for example, Python binds it to one
Entity Class—but that binding is not part of identity and cannot redefine it.
Core retains the full `EntityIdentity`, `AttributeIdentity`, and
`RelationshipIdentity` names. It does not abbreviate them to `*Id`: in an ORM,
an Entity ID denotes an instance's primary-key value, while these values
identify model declarations.

Entity Reference is exactly `RelativeEntityReference(local name) |
ExactEntityReference(EntityIdentity)`. Within an Unresolved Entity Declaration,
Relative resolves to `(owner.namespace, local name)` and Exact resolves
unchanged; the reference never stores the owner. Native class targets are
Exact, bare declaration strings are Relative, and qualified declaration
strings parse directly to Exact. There is no global unique-name fallback
because adding an entity in another namespace must not change an existing
reference's meaning.

Ownerless core operations consume resolved Entity Identity rather than
Relative Entity Reference. A language string facade may parse canonical
identity spelling separately: bare means the exact unnamespaced identity and
qualified means the exact namespaced identity. The foundational resolution
gate either collects all identity/reference issues or produces a Candidate
Metamodel whose declarations carry only Entity Identity values. Canonical
descriptor and operation export always emits qualified spelling for namespaced
identities.

Whenever a complete Metamodel enumerates entities as a set, their canonical
total order is ascending `(namespace or "", name)`, compared codepoint by
codepoint. Constructor order, descriptor file order, and class import order do
not affect that enumeration.
