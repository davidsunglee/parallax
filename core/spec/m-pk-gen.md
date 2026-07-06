# m-pk-gen — Primary-Key Generation

`m-pk-gen` is the **primary-key allocation strategy** a metamodel attribute may
declare. It depends on `m-descriptor` (the attribute it annotates).

A primary-key attribute MAY declare how its value is allocated. `none` (the
default) is application-assigned; `max` allocates `max(col)+1`; `sequence` is a
*simulated sequence* (Reladomo-style): a registry table whose counter is advanced
by `batchSize × incrementSize` per allocation, reserving a block of ids the
application hands out (a partially-consumed block leaves a gap). The simulated
sequence is realized in portable SQL (a table plus an `UPDATE`), so it carries no
dialect seam.

| Strategy | Meaning |
|---|---|
| `none` | application-assigned (default) |
| `max` | `max(col)+1`-style allocation |
| `sequence` | simulated sequence (`sequenceName`, `batchSize`, `initialValue`, `incrementSize`) |

## What the suite pins down

`max` and `sequence` are exercised by `writeSequence` cases
(`m-pk-gen-001`–`m-pk-gen-013`). `max` is self-describing — its
`coalesce(max(...),0)+1` golden SQL (`m-sql`) needs no oracle. For a
`sequence`-strategy insert the harness derives an independent **PK-generation
oracle** (`m-case-format`): it re-derives the allocated primary keys and the
registry counter from the declared `initialValue` / `incrementSize` / `batchSize`
and asserts both against the post-write database state, proving block reservation,
gap-on-unused, and stride follow the declared strategy.
