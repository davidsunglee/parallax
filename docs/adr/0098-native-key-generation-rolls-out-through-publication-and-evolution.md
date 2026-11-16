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

Every Coordinated Evolution now also generates a **Coordinated Migration**
(`m-schema-delta` *Coordinated migration*): ordered steps, each a generated
statement or a manual step the deployment performs, each naming the operations
that asked for it. Generation starts from the coordination requirements rather
than from the physical comparison alone, so every requirement is named by some
step, and it reuses the Schema Delta planner and renderer for whatever ordinary
change the evolution's other operations ask for. The native sequence is the one
thing a migration changes that no Schema Delta may: it is created for an existing
Entity joining an allocator, altered when a surviving allocator's settings change,
moved forward past every stored key of every consuming table when a populated
table joins it or its physical step shrinks, and dropped once its final model
reference is gone. Everything Parallax cannot do safely stays manual: draining the
earlier roots, relocating, transforming stored data, and updating code.

An empty table joining an allocator, a new Entity or leaf, needs no positioning
and stays unilateral. A shrunken
step positions the sequence past the last block reserved under the earlier step,
because a drained root's abandoned keys may already be stored. Dropping a
sequence drains first, because earlier roots still reserve from it.

Two choices depart from the design this followed. The manual vocabulary gains
`UpdateAuthoringSurface` beside `DrainEarlierRoots`, `TransformStoredData`, and
`Relocate`, so an authoring-only operation is attributed to a step without
inventing a drain, a data transformation, or a database-migration reason. And
steps are ordered prerequisite-first rather than relocation-first: the one drain
precedes every relocation, transformation, and statement, because a combined
relocation, settings change, and strategy move must not run any of its database
work while an earlier root still serves.

A coordinated corpus case therefore carries its migration, per dialect, as a
unilateral one carries its Schema Delta, and the reference harness executes it
where its manual steps leave the database to its statements, comparing sequences
as well as tables against the later model's own provisioning.

**Considered options.** Refusing only relocations and letting a settings change
publish was rejected: a root would keep handing out a block computed under the
old stride or range, overlapping what a root under the new settings reserves.
Comparing allocator names rather than physical identity and settings was
rejected because tenants share names and not sequences. Generating coordinated
migrations from the unilateral physical comparison alone was rejected because it
would emit statements a requirement's manual work must precede, such as a
required column added to rows that hold no value for it, and would leave
requirements no step names. Positioning a sequence at the largest stored key at
run time was rejected because roots may hold reservations past it. Classifying every
generation change as an authoring change, as before, was rejected because it
hides the migration a populated table joining a sequence needs and invents an
authoring change where callers lose nothing.

**Superseded decisions.** This supersedes ADR 0093's limit of publication
refusal to a backend change or a relocation, and ADR 0063's listing of generated
primary keys among framework-owned write capabilities. ADR 0093's statement that
Parallax generates no statement that provisions a sequence is superseded for
native allocators' creation in a unilateral schema delta; moving, renaming, and
altering a surviving sequence remain outside schema generation. ADR 0063's
statements that a Coordinated Evolution prescribes no migration procedure, that
a coordinated corpus expectation omits every per-dialect cell, and that
coordinated cases are therefore dialect-independent are superseded: coordinated
migration derives ordered steps from the description, and a coordinated case
carries one migration cell per supported dialect. Altering, positioning, and
dropping a native sequence are generated in a coordinated migration; moving or
renaming one remains manual.
