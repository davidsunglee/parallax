# Python terminology

Python-specific spelling and public semantics live in the
[binding documents](spec/python.md). Portable terms are indexed in the
[root glossary](../../GLOSSARY.md).

| Term | Meaning | Binding |
|---|---|---|
| Entity Class | Class-authored mapping and the type of its values | [Declarations](spec/declarations.md) |
| Attribute / Relationship Declaration | `Attr[T]` / `Rel[T]` and their declaration helpers | [Declarations](spec/declarations.md) |
| Value Object | A frozen structured value used in an entity | [Declarations](spec/declarations.md) |
| Domain Model | An explicit set of accepted model declarations | [Declarations](spec/declarations.md) |
| Descriptor Frontend | The optional descriptor interchange boundary | [Declarations](spec/declarations.md) |
| Database Binding | The core [Database Binding](../../GLOSSARY.md), authored as `PostgresBinding` from typed values, JSON, or YAML, and required by `prepare_model`, `connect` with a Domain Model, and `evolve` | [Execution](spec/execution.md#models-roots-and-scopes) |
| Object Query | The typed query built from entity expressions | [Queries and results](spec/queries-and-results.md) |
| Snapshot | The typed result envelope over published entity values | [Queries and results](spec/queries-and-results.md) |
| Wire | Canonical serialized input or output at an explicit boundary | [Queries and results](spec/queries-and-results.md) |
| Temporal infinity | The core [temporal infinity](../../core/spec/m-core.md#temporal-infinity), spelled `TemporalBound.INFINITY` in an end member | [Declarations](spec/declarations.md) |
| Database / Scoped Database | Snapshot's facades over a Database Root and an authority-selected Execution Scope ([m-execution](../../core/spec/m-execution.md)) | [Execution](spec/execution.md) |
| Writable / Read-Only Transaction Context | The callback's capability-specific surface within one transaction attempt | [Execution](spec/execution.md) |
| Edit | A copy-based write input derived from an entity value | [Execution](spec/execution.md) |
| Insertion source | The inserted instance, its later edits, or the node a Wire insert answered | [Execution](spec/execution.md) |
| Source write | A mutation of the object a published or inserted value addresses, under that source's authority | [Execution](spec/execution.md) |
| Target write | The core [target write](../../GLOSSARY.md), spelled by the `*_if` verbs | [Execution](spec/execution.md) |
| Application API | A name an application must spell to construct, implement, annotate, catch, or match | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| First-party | Use of a name by another Parallax distribution, within `parallax-core`, or by conformance; never application API | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| Distribution root | A distribution's top-level package, which publishes what an application calls | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| Vocabulary module | An application module publishing a closed family an application matches on | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| Extra module | An application module whose dependencies only its distribution's extra installs | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| Accepted Metamodel | The concrete, first-party `Metamodel` formation accepts; owners read their facets from it | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| Entity Metadata | The resolved, read-only metadata `model.entity(key)` returns, with declared and effective profiles | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |
| Compiled Entity | Python's `CompiledEntity`, the core's local declaration view of Entity Metadata; first-party | [ADR 0016](docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md) |

Private implementation names belong in their defining code, not this glossary.
