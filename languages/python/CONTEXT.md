# Python terminology

Python-specific spelling and public semantics live in the
[binding documents](spec/python.md). Portable terms are indexed in the
[root glossary](../../CONTEXT.md).

| Term | Meaning | Binding |
|---|---|---|
| Entity Class | Class-authored mapping and the type of its values | [Declarations](spec/declarations.md) |
| Attribute / Relationship Declaration | `Attr[T]` / `Rel[T]` and their declaration helpers | [Declarations](spec/declarations.md) |
| Value Object | A frozen structured value used in an entity | [Declarations](spec/declarations.md) |
| Domain Model | An explicit set of accepted model declarations | [Declarations](spec/declarations.md) |
| Descriptor Frontend | The optional descriptor interchange boundary | [Declarations](spec/declarations.md) |
| Object Query | The typed query built from entity expressions | [Queries and results](spec/queries-and-results.md) |
| Snapshot | The typed result envelope over published entity values | [Queries and results](spec/queries-and-results.md) |
| Wire | Canonical serialized input or output at an explicit boundary | [Queries and results](spec/queries-and-results.md) |
| Database / Scoped Database | Resource ownership versus authority-selected execution | [Execution](spec/execution.md) |
| Transaction | The callback's explicit read/write surface | [Execution](spec/execution.md) |
| Edit | A copy-based write input derived from an entity value | [Execution](spec/execution.md) |

Private implementation names belong in their defining code, not this glossary.
