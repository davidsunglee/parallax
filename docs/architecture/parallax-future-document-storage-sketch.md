# Future Document Storage Sketch

Status: provisional and non-normative.

This note preserves design sketches for two possible future storage forms:
mapping most Entity members into one relational document column, and mapping
Entity instances into a document collection. It informs future specification
work but does not add either capability to the current Metamodel Hub tickets.
Parallax specifications remain authoritative.

## Accepted extension seam

The current design separates the Entity-level container from member-level
locations:

```text
StorageContainer = Table(name: string)

StorageLocation = Column(name: string)
```

Python `table=` and descriptor `table` are authoring forms for `Table(name)`.
A conventional direct-column mapping is omitted in authoring and normalized to
`Column(member_name)`; accepted Metadata never contains an absent or unresolved
Storage Location.

The design reserves these future shapes without making them constructible:

```text
StorageContainer =
    Table(name: string)
  | DocumentCollection(name: string)

DocumentRoot =
    Column(name: string)
  | ContainerDocument

StorageLocation =
    Column(name: string)
  | DocumentPath(
      root: DocumentRoot,
      path: nonempty sequence<string>,
    )
```

An Entity declares its Storage Container once. Member Storage Locations never
repeat its table or collection. A Document Path is always structured; dotted
strings, JSON Pointers, and string concatenation are not alternate forms.

## Provisional Entity storage layout

A future Entity-level layout could supply the convention that derives omitted
member locations:

```text
StorageLayout =
    Columns
  | Document(root: DocumentRoot)
```

`StorageLayout`, `Columns`, `Document`, and the descriptor keys shown below are
provisional. The future specifications may rename or reshape them while
preserving the accepted container/location separation.

## Descriptor sketches

### Relational table with columns

An omitted layout means conventional direct columns. An omitted attribute
`column` means the Attribute name; `column` is present only for an override.

```yaml
entity:
  name: Customer
  table: customer

  attributes:
    - name: id
      type: int64
      primaryKey: true

    - name: displayName
      type: string

    - name: legacyCode
      type: string
      column: CUST_CD
```

```text
container = Table("customer")
layout = Columns

displayName -> Column("displayName")
legacyCode  -> Column("CUST_CD")
```

### Relational table with a document column

The Entity declares the document-bearing column once. An omitted member path
is its logical containment path; `path` is present only for an override.
Primary-key, relationship-join, and temporal placement is provisional and must
be specified by the future work.

```yaml
entity:
  name: Customer
  table: customer

  layout:
    document:
      column: payload

  attributes:
    - name: id
      type: int64
      primaryKey: true

    - name: displayName
      type: string

    - name: legacyCode
      type: string
      path:
        - legacy
        - customerCode
```

```text
container = Table("customer")
layout = Document(Column("payload"))

id          -> Column("id")
displayName -> DocumentPath(Column("payload"), ("displayName",))
legacyCode  -> DocumentPath(
                 Column("payload"),
                 ("legacy", "customerCode"),
               )
```

A conventionally nested Value Object member would extend the same structured
path. For example, `address.city` would derive
`DocumentPath(Column("payload"), ("address", "city"))` without an authored
path.

### Document collection

The collection is the Entity's Storage Container and each stored record is the
document root. An omitted member path is again its logical containment path.

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

    - name: legacyCode
      type: string
      path:
        - legacy
        - customerCode
```

```text
container = DocumentCollection("customers")
layout = Document(ContainerDocument)

id          -> DocumentPath(ContainerDocument, ("id",))
displayName -> DocumentPath(ContainerDocument, ("displayName",))
legacyCode  -> DocumentPath(
                 ContainerDocument,
                 ("legacy", "customerCode"),
               )
```

Provider-specific identity conventions such as a MongoDB `_id` field are not
decided by this sketch.

## Settled constraints for future work

- A table or collection remains an Entity-level Storage Container and is never
  copied into every member Storage Location.
- Model identities remain independent of physical containers and locations.
- Relational document columns and document-collection records use the same
  structured Document Path vocabulary with different Document Roots.
- Conventional authoring may omit a column or path, but normalized Metadata is
  always explicit.
- A reusable Value Object shape remains storage-neutral. Each occurrence
  receives its own derived location.
- Document collections have one Parallax Metamodel shape per Entity even if a
  provider permits heterogeneous documents.

## Questions for relational document-column storage

- Which semantic roles must remain direct columns: primary keys, relationship
  join attributes, temporal bounds, optimistic-lock attributes, or others?
- May an ordinary member explicitly escape the document into a direct column?
- Are inserts and updates whole-document writes, path-level writes, or both?
- How are defaults, read-only attributes, edited copies, net-zero updates, and
  temporal milestone chaining encoded?
- How do ordinary, expression, and document-native indices compose?
- How do inheritance strategies place document columns and subtype members?
- Which dialect capabilities and unsupported-capability errors are required?
- Which compatibility cases prove descriptor, operation, read, and write
  behavior end to end?

## Questions for document-collection storage

- How are primary-key identity and provider-specific identity fields mapped?
- Which relationship forms are supported across collections, and where are
  referential and dependency rules enforced?
- What transaction and atomicity guarantees must a provider expose?
- How do Valid Time, Transaction Time, optimistic locking, and history behave
  without relational rows and SQL?
- How are schema creation, validation, migrations, and collection indices
  represented without weakening Parallax's one-shape-per-Entity rule?
- Which operation algebra and query capabilities can a document adapter
  implement faithfully, and how are unsupported capabilities classified?
- Does document-collection support belong in the existing Snapshot adapter
  seam or require a deeper provider-neutral persistence interface?
- Which compatibility and conformance slices demonstrate a complete first
  tracer bullet?

## Future work

The future tickets remain independent and related to the Metamodel redesign
rather than blocking its current implementation chain:

- [COR-48 — Specify relational document-column Entity storage](https://linear.app/flimflam/issue/COR-48/specify-relational-document-column-entity-storage)
  specifies the hybrid table/document layout.
- [COR-49 — Design document-collection Entity storage](https://linear.app/flimflam/issue/COR-49/design-document-collection-entity-storage)
  begins with design and provider-capability research before proposing
  implementation slices.
