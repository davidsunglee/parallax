# TypeScript v1 is descriptor-first with a generated API

The first TypeScript implementation uses canonical Parallax YAML/JSON descriptors as the source of truth and generates the TypeScript entity symbols, domain types, entity input types, snapshot types, and operation accessors from them. The generated API is derived output rather than user-owned source. Decorators and TypeScript schema builders may be added later as descriptor-authoring conveniences, but v1 starts from the same serialized metamodel used by the compatibility corpus.

The TypeScript generator configuration calls these inputs `descriptors`, not `specs` or `models`. "Spec" is reserved for normative core and language specifications, while "model" is overloaded with generated domain types.
