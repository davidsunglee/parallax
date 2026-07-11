# Python is class-first over a metamodel hub

The Python implementation inverts the TypeScript v1 direction (TS ADR 0001,
descriptor-first with generated API): developers author SQLModel-style frozen
Pydantic entity classes, and the canonical YAML/JSON descriptor is derived
output, never hand-written application input. The in-memory metamodel is the
single hub with two frontends — entity classes on the developer path, direct
ingestion of canonical YAML on the conformance path — so the adapter compiles
and runs corpus cases without any Python model classes existing, and no code
generation exists anywhere.

Drift between the two frontends is prevented by the API Conformance Suite's
descriptor-equality guard (idiomatic class exports must structurally equal the
corpus descriptor) and the operation no-drift guard, not by a generator.
Canonical identifiers stay camelCase per the core schema; Python fields are
snake_case with a deterministic snake-to-camel export conversion, a
class-definition-time collision check, and an explicit `Field(name=...)`
override. Only the export direction is needed, so camel-to-snake ambiguity
never arises.
