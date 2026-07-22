# Relationship formation belongs to m-relationship

The Metamodel preserves validated, identity-resolved Defining and Reverse
Relationship Declarations instead of synthesizing symmetric Relationship
Metadata itself. The active `m-relationship` module owns their whole-model
rules and compiles the symmetric Relationship Facet consumed by navigation,
deep fetch, cascade behavior, SQL correlation, and graph materialization;
`m-metamodel` owns only the common declaration vocabulary, reference
resolution, local storage, and lookup.

This keeps relationship validation and derivation in one deep module without
making read-oriented `m-navigate` the owner of shared association semantics.
The generic Metadata Compiler therefore never pairs directions, swaps joins,
or inverts cardinality, and canonical descriptor export can retain the original
defining-versus-reverse declaration structure. The facet offers total
constant-time identity lookup and declaration-ordered per-Entity enumeration;
the latter distinguishes an unknown Entity from a known Entity with no
relationships.
