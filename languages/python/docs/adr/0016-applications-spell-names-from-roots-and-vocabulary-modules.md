# Applications spell names from roots and vocabulary modules

Python's exported surface serves two audiences. **Application** code builds
models, runs transactions, and evolves schemas. **First-party** code is one
Parallax distribution using another, code within `parallax-core`, and
conformance. There is no third audience: Parallax publishes no extension
interface for third-party frontends, facet compilers, or adapters, so a name an
application never writes needs no application home.

A name is application API only if an application must spell it: to construct,
implement, annotate, catch, or match it. A value an application only holds or
passes along stays unexported. The rule is deliberately not transitive. Applied
through every type an application can reach, it publishes roughly 770 names,
including `FacetKey`, and so turns every first-party seam that happens to appear
in a signature into a compatibility promise.

## Application modules

You call things from a distribution root, and you match on things from a
vocabulary module. The application modules are each distribution's root and
three vocabulary modules: `parallax.core.execution_lifecycle`, for the
execution event family a handler matches; `parallax.core.introspection`, for the
resolved metadata an application reads; and `parallax.evolution.operations`, for
the operation, detail, impact, and fact families an evolution result carries.
One extra module, `parallax.aws.postgres`, stays public because its
dependencies come from the `parallax-aws[postgres]` extra: importing it from
`parallax.aws` would break the base install, and a lazy module `__getattr__`
would put a name in `__all__` whose import can fail. Every other module is
first-party. A leading underscore keeps meaning private to its scope; a
first-party module that is not scope-private belongs under its distribution's
`internal` package, so a public path outside the application modules is an
error rather than an undeclared surface.

Every application name has exactly one home, chosen by its role. Calls,
configuration, provider seams, errors and their codes, and every value family an
application writes live at the root; a closed family an application only reads
and matches lives in its vocabulary module, which re-exports the defining
objects rather than wrappers. A family stays together at the root when an
application can write any member of it, so a value written and read back is the
same class. Where a member's name would clash with a name applications
commonly import beside Parallax, that member is renamed rather than the family
split: the column type the core calls `Decimal` is Python's `Numeric`, because
model files import `decimal.Decimal` for their carriers. The core
specification's portable families, such as the execution lifecycle's
transitions and outcomes, stay whole; only aliases an application can neither
construct nor match leave application exports.

Publishing every useful name from one module was rejected: roots would mix what
an application calls with what it matches on, and a vocabulary of a hundred
operation types would bury the dozen calls and results. Publishing first-party
modules beside an allowlist was rejected because an allowlist no check derives
from source drifts silently; the API snapshot instead discovers public modules
and records exactly the application modules.

## A concrete first-party Metamodel

The accepted Metamodel is a concrete, sealed class rather than a structural
Protocol, constructed only through `accept_metamodel` and read only through
`entities` and `entity(identity)`, the members
[`m-metamodel`](../../../../core/spec/m-metamodel.md) gives it. Generic facet
access is private to the metamodel package; each owner reads its facet through a
typed accessor beside the constructor that builds it, and `FacetKey` is not
exported. `CompiledMetadata` and the Metadata Compiler's per-Entity product stay
Protocols, so a test supplies fake compiled metadata and accepts it into a real
Metamodel.

A structural `Metamodel` let any object with three members pose as an accepted
model, and tests maintained an independent implementation, with casts, that
formation never produced. Sealing the class makes formation and
`accept_metamodel` the only producers while keeping the formation seam a
Protocol where independent implementations are useful. Runtime constructor or
subclass guards were rejected as machinery for an audience that does not exist;
types and first-party review cover a stray construction.

`Metamodel` and `model_of` are first-party. Applications hold one model type,
`DomainModel`: `evolve`, `prepare_model`, and descriptor export all take it, and
an evolution result's endpoints are Metamodels an application only holds.

## Resolved application introspection

The Metadata Compiler's per-Entity product, Python's `CompiledEntity`, is the
formation seam: the output of compilation and the input to every facet
compiler. By the core contract it keeps relationships as unpaired declarations
and never copies effective facts, because pairing and inheritance belong to
their owners. Applications instead read resolved metadata:
`model.entity(key)` and `model.entities` return `EntityMetadata`, whose
`declared` and `effective` profiles share one shape. The Entity frontend builds
each value once, when a model is published, from the canonical structures the
relationship, inheritance, and temporal owners already compiled, and returns
the authoring classes an application wrote.

Republishing the compiled seam was rejected. Every application would repeat
the owners' resolution, such as following a reverse relationship declaration to
recover its cardinality, and members would come back asymmetrically as
metadata for attributes and declarations for relationships. A separate lookup
for inherited members was rejected in favor of the `effective` profile, so one
call and one Entity type answer both local and in-force questions.

Formation inputs, the Metamodel, compiled metadata, and owner facets remain
first-party: their shapes can change with the owners that compute them without
changing what an application imports.
