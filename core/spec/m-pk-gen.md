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
`m-pk-gen` therefore contributes no Model Formation Rule Set, Issue Code, or
facet.
