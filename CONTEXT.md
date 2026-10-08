# Parallax terminology

This is a navigation aid. Definitions and behavior belong to the linked
contract owners; this index does not add requirements.

| Term | Distinction | Contract owner |
|---|---|---|
| Descriptor | Serialized model input, distinct from the runtime model view | [Descriptor](core/spec/m-descriptor.md) |
| Metamodel Interface | Language-neutral view of accepted model declarations | [Metamodel](core/spec/m-metamodel.md) |
| Entity Identity | Namespace/name identity of a declaration, not a row's primary key | [Metamodel](core/spec/m-metamodel.md) |
| Attribute / Relationship Identity | A member's declaration identity | [Metamodel](core/spec/m-metamodel.md) |
| Neutral Type / Neutral Value | Portable logical types and their managed values | [Core](core/spec/m-core.md) |
| Model Formation | Validation and composition of model declarations | [Formation](core/spec/m-model-formation.md) |
| Inheritance Family | One closed tree of entity declarations | [Inheritance](core/spec/m-inheritance.md) |
| Storage Layout | Mapping from logical members to physical storage | [Storage](core/spec/m-storage-layout.md) |
| Value Object | A structured value embedded in an entity | [Value objects](core/spec/m-value-object.md) |
| Predicate | The portable selection algebra | [Predicates](core/spec/m-predicate.md) |
| Object Query | An authored read, including its result and traversal choices | [Queries](core/spec/m-object-query.md) |
| Execution Runtime | The lifecycle-neutral root, scopes, and attempts that run reads and writes | [Execution](core/spec/m-execution.md) |
| Database Root | Resource owner from which execution scopes are derived, configured with option defaults | [Execution](core/spec/m-execution.md) |
| Execution Scope | Authority-selected view through which modeled work is invoked | [Execution authority](core/spec/m-execution-authority.md) |
| Attempt | The execution state of one physical transaction attempt, wired before any callback sees it | [Execution](core/spec/m-execution.md) |
| Principal / Execution Actor | Application input versus captured execution authority | [Execution authority](core/spec/m-execution-authority.md) |
| Unit of Work | Transactional buffering and settlement boundary | [Unit of work](core/spec/m-unit-work.md) |
| Row Acquisition | A write's read of the existing rows it needs, described by the unit of work and executed by the runtime | [Unit of work](core/spec/m-unit-work.md) |
| Retained Starting Row | The row a Locking target write's acquisition read whole, kept as pending data its range reuses while no earlier unit changed it | [Unit of work](core/spec/m-unit-work.md) |
| Observed / Insertion-Authoring Write | A write authorized by genuine read provenance versus one authorized by an admitted insertion's own source | [Unit of work](core/spec/m-unit-work.md) |
| Target Write | A caller-addressed patch or replacement, conditioned by the revision its caller states rather than by any source | [Unit of work](core/spec/m-unit-work.md) |
| Planned Write | One finalized semantic execution step, distinct from the SQL that lowers it | [Write plan](core/spec/m-write-plan.md) |
| Object Key / Observed State Key | An object across its states versus one exact state a read observed | [Write plan](core/spec/m-write-plan.md) |
| Write Observation / Predecessor Row | The evidence a write against existing state retains, and the complete observed row a temporal one carries | [Write plan](core/spec/m-write-plan.md) |
| Write Row / executed assignments | One represented row before its realization is chosen, and the members it states explicitly rather than carries | [Write plan](core/spec/m-write-plan.md) |
| Write payload | What a planned write persists, prepared once and rendered by SQL lowering | [Write payload](core/spec/m-write-payload.md) |
| Predecessor / Successor | An existing milestone a temporal write acts on, versus a row derived from exactly one predecessor over part of its coverage | [Temporal writes](core/spec/m-temporal-write.md) |
| Coverage Transform / Coverage Segment | What an object's composed writes do to its existing coverage, and one requested window of it | [Temporal writes](core/spec/m-temporal-write.md) |
| Coverage Gap | Part of a replacement's extent no existing coverage holds, opened as a new lineage rather than a successor | [Temporal writes](core/spec/m-temporal-write.md) |
| Predecessor Expansion | The per-milestone rules that settle one predecessor's effect and successors | [Temporal writes](core/spec/m-temporal-write.md) |
| Unchanged Milestone / Guard | A milestone a write leaves exactly as it was and keeps, versus the write that proves it still stands as observed | [Temporal writes](core/spec/m-temporal-write.md) |
| Concurrency Preference / Strategy | Requested policy versus the strategy resolved for an entity | [Read locks](core/spec/m-read-lock.md) |
| Transaction Time / Valid Time | Audit history versus effective-world history | [Temporal reads](core/spec/m-temporal-read.md) |
| Read Delivery | Turning a validated read into a judged Page, delivered whole or streamed | [Read delivery](core/spec/m-read-delivery.md) |
| Page / Entity State | One read's bounded occurrence table, and the judged member row it holds for one logical object | [Read delivery](core/spec/m-read-delivery.md) |
| Publication | The lifecycle behavior delivery invokes to turn Page states into values | [Read delivery](core/spec/m-read-delivery.md) |
| Snapshot | A published value graph with explicit loading state | [Snapshot reads](core/spec/m-snapshot-read.md) |
| Execution Activity | An observable unit of execution work | [Execution lifecycle](core/spec/m-execution-lifecycle.md) |
| Model Edition / Serving Model | Model evolution identity and the published model holder | [Execution](core/spec/m-execution.md) |
| Conformance Slice | An exact corpus claim, not a package or implementation layer | [Slices](core/spec/slices.md) |
| Behavioral Module / Enforcement Scope / Artifact | Portable behavior, checked source boundary, and shipped package | [Modules](core/spec/modules.md) |

Use the owner's vocabulary when changing its surface. Introduce new terms there
instead of copying its detailed rules into this index.
