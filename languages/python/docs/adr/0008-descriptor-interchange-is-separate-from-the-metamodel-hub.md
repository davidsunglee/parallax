# Descriptor interchange is separate from the Metamodel Hub

The common Python runtime owns `MetamodelHub`, including its fixed model scope,
sealing lifecycle, accepted metadata, facets, and introspection. Its public
constructor accepts the complete Entity Class set. An optional descriptor
distribution instead owns decoded-document, JSON, and YAML ingestion; canonical
document, JSON, and YAML export; and every descriptor-specific error. It
depends on the common runtime and reaches Hub construction through a narrow
first-party source seam:
`MetamodelHub._from_unresolved(source: UnresolvedMetamodel)`. The seam is
private but versioned with the first-party distributions; it is not a
supported third-party frontend extension point.

`MetamodelHub` therefore exposes no descriptor factory or export methods. The
descriptor distribution's ingestion functions create unsealed hubs, and its
export functions accept sealed hubs. This keeps the common runtime independent
of optional parsing, schema, YAML, and serialization dependencies while
preserving one Hub lifecycle and one accepted-metadata truth for class-backed
and descriptor-backed models.

The public ingestion functions are `hub_from_document`, `hub_from_json`, and
`hub_from_yaml`; the public export functions are `export_document`,
`export_json`, and `export_yaml`. JSON and YAML inputs and outputs are text,
while document input and output use the canonical decoded document value.
These functions perform no filesystem or stream I/O: callers own acquisition
and persistence.

`hub_from_document` accepts a decoded `Mapping[str, object]`;
`hub_from_json` and `hub_from_yaml` accept `str | bytes`, with bytes decoded as
UTF-8. Malformed UTF-8 is a descriptor syntax error for the selected format.
Successful ingestion converts input into immutable descriptor-owned records
and retains no caller-owned mutable document. `export_document` returns a
fresh tree of ordinary mappings, lists, and JSON-compatible scalar values;
the text exporters return `str`.

The descriptor distribution declares `parallax-core`, `pyyaml`, and
`jsonschema` as mandatory runtime dependencies. The common runtime retains
`pydantic` but no descriptor parser or schema dependency. Descriptor schema
validation is therefore always available when descriptor interchange is
installed; it has no optional-import failure mode. The development-only
conformance distribution depends on the descriptor distribution wherever it
consumes descriptor interchange.

The language-neutral `core/schemas/metamodel.schema.json` file remains the
authoritative schema source. Descriptor wheels and source distributions embed
a byte-for-byte copy as package data, loaded with `importlib.resources`; runtime
code never searches repository-relative paths. Build and artifact checks fail
when the packaged resource differs from the authoritative source, so there is
no independently maintained second schema.

`parallax.descriptor` publicly exports the ingestion base
`DescriptorError(ValueError)` and its `DescriptorSyntaxError`,
`DescriptorSchemaError`, and `DescriptorValueError` subclasses, together with
the frozen `DescriptorSchemaViolation` and `DescriptorValueViolation` records.
It separately exports `DescriptorExportError(RuntimeError)`: export failure is
an adapter defect, not invalid caller input. Supplying an unsealed, internally
sealing, or rejected hub to an exporter raises the common runtime's
`MetamodelStateError`. The common runtime re-exports no descriptor errors or
violation records.

Those functions and error values are the complete public descriptor surface.
Descriptor record classes, serde helpers, schema machinery, type-spelling
conversion, the Unresolved Metamodel adapter, and accepted-model export
conversion remain private. The common runtime owns and exposes no descriptor
record graph or compatibility re-export; its runtime consumers use core
Metamodel values.

The Python source/enforcement scope for the language-neutral `m-descriptor`
module is `parallax.descriptor`. It depends inward on
`parallax.core.base` and `parallax.core.metamodel`. Its private child support
scope `parallax.descriptor._hub` alone depends on `parallax.core.entity` for
the Hub-construction seam.
`parallax.conformance` may depend on `parallax.descriptor`; common-runtime,
Snapshot, and Postgres source may not. There is no
`parallax.core.descriptor` compatibility scope or reverse production edge.

We rejected convenience methods on `MetamodelHub`: implementing them would
require the common runtime to depend on the optional descriptor distribution
or introduce registration, discovery, or lazy imports whose availability
depends on ambient process state. We also rejected a descriptor-owned parallel
model container because it would duplicate lifecycle and introspection
semantics. We rejected a public generic source factory because it would make
the internal formation protocol a third-party compatibility promise.
