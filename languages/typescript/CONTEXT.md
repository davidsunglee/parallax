# Parallax TypeScript

Parallax TypeScript provides an idiomatic TypeScript API and generator surface for the language-neutral Parallax core contract.

## TypeScript API Glossary

### Generated API Surface

**Entity Symbol**:
A generated TypeScript API object for a mapped entity, exposing typed attributes, relationships, and entity-level operations.
_Avoid_: model singleton, finder class

**Parallax**:
The generated TypeScript handle type returned by `parallax(...)` and used as the application entry point for reads and transactions.
_Avoid_: client, database connection, global session, ambient context

**Domain Function**:
An application-owned TypeScript function that implements domain behavior over generated domain objects, snapshots, `Parallax`, or `ParallaxTransaction`.
_Avoid_: custom generated-object method, entity subclass

### Result And Relationship APIs

**ParallaxList**:
An async, operation-backed TypeScript result collection returned by `find`; it may resolve to zero, one, or many objects.
_Avoid_: array, result array

**Relationship Reference**:
A TypeScript runtime object that represents navigation, loading, or mutation of a relationship without exposing relationship data as a promise-valued property.
_Avoid_: async property, lazy promise, raw array property

### Input And Validation

**Entity Input**:
A generated TypeScript type and validation namespace, such as `OrderInput`, for validating unknown input as a create payload without creating a managed object or opening a transaction.
_Avoid_: detached object parser, snapshot parser, create namespace
