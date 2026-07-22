# Accepted metamodel introspection has generic and typed layers

The durable TypeScript decision is to expose two introspection layers over one
accepted `m-metamodel` graph: a generic reader for arbitrary formed models and
typed accessors generated onto each Entity symbol. Both layers delegate to the
same immutable Metadata and facet values; neither treats the serialized
`m-descriptor` document as the runtime protocol or retains a mirrored descriptor
graph.

The generic layer is reached through the `Parallax` handle as `px.metamodel`.
The generator, canonical serde boundary, and conformance adapter require a
representation-independent reader because they operate without generated
symbols. The typed layer provides the application-facing convenience surface
and delegates to that same reader rather than duplicating Metadata.

The exact fields, identities, ordering, absence rules, and local-versus-derived
division come from `core/spec/m-metamodel.md` and its compiled facets, not from
the descriptor schema. A typed-only design remains unsuitable for tooling; a
generic-only design remains needlessly awkward for application code.

The currently shipped `Metamodel` / `EntityMetadata` reader still predates the
complete formation contract, but COR-45 removes its retired Relationship and
Value Object projection. It preserves the canonical defining/reverse declaration
union, compiles directional relationship behavior into one Relationship Facet,
keeps the target solely in the structured join, and exposes Value Object
`multiplicity` directly. A later TypeScript formation slice must make the
compiler-produced Metamodel graph the owner of these declarations and facets;
the reader must delegate to that graph rather than reconstruct it.
