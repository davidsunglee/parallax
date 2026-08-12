# Context Map

## Contexts

- [Parallax Core](./CONTEXT.md) - language-neutral ORM contract, runtime semantics, and shared vocabulary.
- [Parallax Python](./languages/python/CONTEXT.md) - Python-specific class-first authoring, snapshot-lifecycle API surface, and idioms.

## Relationships

- **Parallax Python -> Parallax Core**: The Python implementation realizes the
  core contract through a class-backed Typed interface and a class-independent
  Wire interface over one Domain Model and transaction. The optional Descriptor
  Frontend translates canonical descriptor input and output at the context seam
  without making interchange a runtime-model responsibility.
