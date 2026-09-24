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
| Database Root | Resource owner from which execution scopes are derived | [Execution authority](core/spec/m-execution-authority.md) |
| Execution Scope | Authority-selected view through which modeled work is invoked | [Execution authority](core/spec/m-execution-authority.md) |
| Principal / Execution Actor | Application input versus captured execution authority | [Execution authority](core/spec/m-execution-authority.md) |
| Unit of Work | Transactional buffering and settlement boundary | [Unit of work](core/spec/m-unit-work.md) |
| Concurrency Preference / Strategy | Requested policy versus the strategy resolved for an entity | [Read locks](core/spec/m-read-lock.md) |
| Transaction Time / Valid Time | Audit history versus effective-world history | [Temporal reads](core/spec/m-temporal-read.md) |
| Snapshot | A published value graph with explicit loading state | [Snapshot reads](core/spec/m-snapshot-read.md) |
| Execution Activity | An observable unit of execution work | [Execution lifecycle](core/spec/m-execution-lifecycle.md) |
| Model Edition / Serving Model | Model evolution identity and the published model holder | [Model evolution](core/spec/m-model-evolution.md) |
| Conformance Slice | An exact corpus claim, not a package or implementation layer | [Slices](core/spec/slices.md) |
| Behavioral Module / Enforcement Scope / Artifact | Portable behavior, checked source boundary, and shipped package | [Modules](core/spec/modules.md) |

Use the owner's vocabulary when changing its surface. Introduce new terms there
instead of copying its detailed rules into this index.
