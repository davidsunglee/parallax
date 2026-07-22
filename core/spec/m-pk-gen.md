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

Invalid generator states are unconstructible in normalized Metadata: the
descriptor schema or language declaration frontend rejects them before the
Unresolved Metamodel seam. Sequence defaults are resolved there as well.
`m-pk-gen` therefore contributes no Model Formation Rule Set, Issue Code, or
facet.

## What the suite pins down

`max` and `sequence` are exercised by `writeSequence` cases
(`m-pk-gen-001`–`m-pk-gen-013`). `max` is self-describing — its
`coalesce(max(...),0)+1` golden SQL (`m-sql`) needs no oracle. For a
`sequence`-strategy insert the harness derives an independent **PK-generation
oracle** (`m-case-format`): it re-derives the allocated primary keys and the
registry counter from the declared `initialValue` / `incrementSize` / `batchSize`
and asserts both against the post-write database state, proving block reservation,
gap-on-unused, and stride follow the declared strategy.
