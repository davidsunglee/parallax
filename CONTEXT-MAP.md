# Context Map

## Contexts

- [Parallax Core](./CONTEXT.md) - language-neutral ORM contract, runtime semantics, and shared vocabulary.
- [Parallax Python](./languages/python/CONTEXT.md) - Python-specific class-first authoring, snapshot-lifecycle API surface, and idioms.

## Relationships

- **Parallax Python -> Parallax Core**: The Python implementation realizes the core contract's snapshot lifecycle with class-authored models over a metamodel hub; descriptors are derived output on the developer path and direct input on the conformance path.
