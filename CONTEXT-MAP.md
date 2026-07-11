# Context Map

## Contexts

- [Parallax Core](./CONTEXT.md) - language-neutral ORM contract, runtime semantics, and shared vocabulary.
- [Parallax TypeScript](./languages/typescript/CONTEXT.md) - TypeScript-specific API surface, generator vocabulary, and idioms.
- [Parallax Python](./languages/python/CONTEXT.md) - Python-specific class-first authoring, snapshot-lifecycle API surface, and idioms.

## Relationships

- **Parallax TypeScript -> Parallax Core**: The TypeScript implementation realizes the core contract with TypeScript-specific generated APIs, runtime types, and tooling.
- **Parallax Python -> Parallax Core**: The Python implementation realizes the core contract's snapshot lifecycle with class-authored models over a metamodel hub; descriptors are derived output on the developer path and direct input on the conformance path.
