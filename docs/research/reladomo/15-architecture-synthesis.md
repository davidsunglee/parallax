# Architecture synthesis

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

Reladomo's defining architectural decision is **code generation as the binding layer**: a single XML
descriptor produces a typed, compile-time-checked Java surface (Object/Data/Finder/List/DatabaseObject),
but all behavior is delegated to hand-written runtime base classes. This keeps the runtime free of
reflection in hot paths (the generated `Finder` holds concrete `Attribute` instances; the generated
`DatabaseObject` does column binding/inflation in straight-line code) while letting the model — not Java
boilerplate — be the source of truth. The generated/runtime boundary is a clean inheritance seam
(`<Name>Abstract extends MithraTransactionalObjectImpl`).

The runtime is organized around **per-type portals coordinated by a global manager**. The portal is the
single hub that ties a type's identity cache, query cache, finder/metadata, and database object together;
every read and write flows through it, so the cache-first read path (query cache → identity cache → DB)
and the buffered-write path are uniform across all types. The `MithraManager` singleton owns only the
truly global concerns (current transaction, config, notification, retrieval counter).

Two cross-cutting concepts pervade the design. First, **identity and freshness via caching**: objects are
interned to one-per-PK, query results are cached as `CachedQuery` lists of those interned objects, and
invalidation is decoupled through monotonic `UpdateCountHolder` version tokens plus a cross-JVM
notification bus — so a write anywhere expires dependent cached queries without enumerating them. Second,
**bitemporality as a first-class dimension**: as-of attributes are virtual attributes over column pairs,
queries get defaulted as-of predicates injected automatically, and writes never update in place — they
chain milestone rows through `TemporalDirector`s.

Portability and extension points are expressed as **interface seams obtained from configuration, not
registries**: the `DatabaseType` comes from the connection manager; the persister/reader can be a local
`MithraAbstractDatabaseObject` or a `RemoteMithraObjectPersister` chosen at config-init time; cache
variants (Full/Partial/Dated/OffHeap) are selected per-class in the runtime config. Transactions layer on
JTA with automatic correctness (pessimistic read locks or optimistic version checks) and a retry loop, so
application code expresses intent (`executeTransactionalCommand`) while the framework handles
locking/ordering/batching. The deliberate counter-example is **source-attribute sharding**, which —
unlike the other extension points — is plumbed as an `Object source` parameter through the database layer
and metadata interfaces rather than hidden behind a single seam.
