# Native key generation rolls out through publication and evolution

A model that generates keys from native sequences (ADR 0097) changes what a
running root holds: a block of keys reserved under one physical sequence and one
set of allocation settings. Publication, model evolution, and schema generation
each have to know which changes invalidate that state.

One comparison decides it. The binding foundation's relocation comparison widens
into a comparison of **breaking changes**: a surviving table or sequence that
moved, or a surviving allocator whose batch size, stride, or key range changed
(`m-database-binding` *Breaking changes*). `ServingModel.publish` refuses a
candidate with any, naming each, as `publication-breaking-change-refused` before
it checks for a stale selection, and leaves the held selection serving; `evolve`
classifies each as `DatabaseMigrationRequired`. The refusal's code changes from
`publication-relocation-refused` because one refusal now names relocations and
settings changes together. Adding or removing an allocator, changing only its
initial value, and moving an Entity between strategies all publish: none of them
changes a sequence a surviving reservation draws from.

Classification reads a generation change's direction (`m-model-evolution`
*Keys*). Joining an allocator withdraws no caller input, so it carries no
authoring reason, but a populated table's keys must be passed by the sequence
before it allocates, so it needs a migration; so does moving to a different
allocator. Leaving one withdraws keyless construction. A generated key is
caller-omittable rather than framework-owned, so a strategy move no longer
changes an attribute's write capability.

Schema generation creates each new allocator's sequence once, from the binding's
resolved definition, and never touches a surviving one: adding a consumer of an
existing allocator neither recreates nor resets its sequence, and an initial
value only places a sequence not yet created (`m-schema-delta`). A Coordinated
Evolution handed to schema generation is refused at run time rather than
rendered as an incomplete delta.

**Considered options.** Refusing only relocations and letting a settings change
publish was rejected: a root would keep handing out a block computed under the
old stride or range, overlapping what a root under the new settings reserves.
Comparing allocator names rather than physical identity and settings was
rejected because tenants share names and not sequences. Classifying every
generation change as an authoring change, as before, was rejected because it
hides the migration a populated table joining a sequence needs and invents an
authoring change where callers lose nothing.

**Superseded decisions.** This supersedes ADR 0093's limit of publication
refusal to a backend change or a relocation, and ADR 0063's listing of generated
primary keys among framework-owned write capabilities. ADR 0093's statement that
Parallax generates no statement that provisions a sequence is superseded for
native allocators' creation in a unilateral schema delta; moving, renaming, and
altering a surviving sequence remain outside schema generation.
