# Future Document Collection Storage Sketch

Status: provisional and non-normative.

This note preserves the possible future design for mapping Entity instances
into a document collection. It informs future specification work but does not
add the capability to the current Metamodel, operation runtime, or provider
adapter seams. Parallax specifications remain authoritative.

## Scope

A Document Collection is a Storage Container whose stored records are
themselves structured documents. It is analogous to a MongoDB-style collection,
not a relational Table containing a structured column. Each collection has one
Parallax Metamodel shape per Entity even when the provider permits heterogeneous
records.

The design must eventually answer whether document collections fit behind the
existing relational execution seams or require a deeper provider-neutral
persistence interface. This sketch does not assume that SQL, relational
transactions, foreign keys, or table DDL remain available.

## Reserved extension seam

The current design names an Entity-level Storage Container independently from
member placement. Document Collection support could extend the container
algebra:

```text
StorageContainer =
    Table(name: string)
  | DocumentCollection(name: string)

DocumentRoot = ContainerDocument

DocumentPath
  root: DocumentRoot
  path: nonempty sequence<string>
```

The collection is declared once for the Entity. Member paths never repeat its
name. A Document Path is always structured; dotted strings, JSON Pointers, and
provider-native path strings are not alternate model forms.

These shapes and the descriptor keys below remain provisional. Future
specifications may rename or reshape them while preserving the separation
between Entity identity, its Storage Container, and member placement.

## Descriptor sketch

An Entity could declare a collection whose stored record is the document root:

```yaml
entity:
  name: Customer
  collection: customers

  attributes:
    - name: id
      type: int64
      primaryKey: true

    - name: displayName
      type: string
```

```text
container = DocumentCollection("customers")

id          -> DocumentPath(ContainerDocument, ("id",))
displayName -> DocumentPath(ContainerDocument, ("displayName",))
```

An omitted path would derive from the member's canonical logical containment
path. A conventionally nested Value Object member such as `address.city` would
derive:

```text
DocumentPath(ContainerDocument, ("address", "city"))
```

Provider-specific identity conventions such as MongoDB's `_id` field are not
decided by this sketch.

## Settled constraints for future work

- A collection remains an Entity-level Storage Container and is never copied
  into every member placement.
- Model identities remain independent of physical containers and paths.
- A reusable Value Object shape remains storage-neutral. Each occurrence
  receives its own derived path.
- Document collections have one Parallax Metamodel shape per Entity even if a
  provider permits heterogeneous records.
- Document Collection support must not weaken the semantics claimed by an
  accepted Conformance Slice. Unsupported relational assumptions need explicit
  capability design rather than silent approximation.

## Open questions

- How are primary-key identity and provider-specific identity fields mapped?
- Which relationship forms are supported across collections, and where are
  referential and dependency rules enforced?
- What transaction and atomicity guarantees must a provider expose?
- How do Valid Time, Transaction Time, optimistic locking, and history behave
  without relational rows and SQL?
- How are schema creation, validation, migrations, and collection indexes
  represented without weakening Parallax's one-shape-per-Entity rule?
- Which Predicate algebra and query capabilities can a document adapter
  implement faithfully, and how are unsupported capabilities classified?
- Does Document Collection support belong behind the existing database port, or
  does it require a provider-neutral persistence interface above relational SQL?
- Which compatibility and conformance slices demonstrate a complete first
  tracer bullet?

## Future work

[COR-49 — Design document-collection Entity storage](https://linear.app/flimflam/issue/COR-49/design-document-collection-entity-storage)
begins with provider-capability and transaction-semantics research before
proposing implementation slices.
