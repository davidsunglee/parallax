# m-pk-gen — Primary-Key Generation

`m-pk-gen` is the **primary-key allocation strategy** a normalized Attribute
may declare. Its behavior consumes `m-metamodel`; the canonical descriptor is
only an authoring/serde adapter.

A primary-key Attribute MAY declare how its value is allocated.
`application-assigned` (the default) means the application supplies it; `max`
allocates `max(col)+1`; `sequence` is a
*simulated sequence* (Reladomo-style): a registry table whose counter is advanced
by `batchSize × incrementSize` per allocation, reserving a block of ids the
application hands out (a partially-consumed block leaves a gap). The simulated
sequence is realized in portable SQL (a table plus an `UPDATE`), so it carries no
dialect seam.

| Strategy | Meaning |
|---|---|
| `application-assigned` | application-assigned (default) |
| `max` | `max(col)+1`-style allocation |
| `sequence` | simulated sequence (`name`, `batchSize`, `initialValue`, `incrementSize`) |

Accepted metadata uses
`NotPrimaryKey | PrimaryKey(ApplicationAssigned | Max | Sequence(...))`.
Descriptor `primaryKey: true` with omitted `pkGeneration` normalizes to
Application Assigned; `pkGeneration` on `primaryKey: false` is invalid. This
sum prevents a non-primary-key Attribute from carrying a generation strategy.

`Max` and `Sequence` are legal only on an `Int32` or `Int64` Attribute:
`max` allocates `max(col)+1` and `sequence` advances an integer registry
counter, so a non-integral generated key has no meaning.
`ApplicationAssigned` follows [Metamodel key eligibility](m-metamodel.md#attributes-and-primary-keys).

Invalid generator/type combinations are unconstructible in normalized Attribute Metadata before the Unresolved Metamodel seam. Public descriptors reject them through the schema's attribute `type` conditional; native language declarations translate construction failure at their declaration boundary.
Sequence defaults are resolved there as well (`batchSize`, `initialValue`,
and `incrementSize` default to `1`, fixed by the schema).

## Logical allocators

A `sequence` declaration's `name` is a **logical allocator key**: an exact,
case-sensitive, model-wide key, independent of Entity Namespaces and of the
Table that stores the declaring Entity. It names an allocator, not a physical
database object; where an allocator physically lives is a deployment fact the
model does not carry. Declarations with equal keys deliberately share one
allocator, so they MUST agree on everything that allocator hands out: the
batch size, the initial value, the increment size, and the key's declared
neutral type, which together fix the key range. A disagreeing declaration is
reported as `pk-gen-sequence-conflict` at its own Attribute, related to the
first declaration of the key in canonical Entity order and then declaration
order; every disagreeing declaration is reported.

A family's primary key and its generation are declared once, by the ancestor
that introduces the key (`m-inheritance`), and every position of the family
inherits that one declaration. It therefore counts once toward this rule
however many positions inherit it, including under a table-per-concrete-subtype
root that owns no table, and the family resolves one allocator even when its
concrete tables are stored apart.

`m-pk-gen` contributes this Model Formation Rule Set and no facet. The rule
reads only declared metadata; it neither creates nor consults a database
object.
