# Entanglement check: remote and XML are cleanly separable; off-heap is medium-coupled; source-attribute/sharding is highly coupled

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The four features the ticket proposes to exclude differ sharply in how deeply they are woven in.

**(a) Source attributes / sharding — HIGH coupling.** An `Object source` parameter threads through the
entire database layer. The generated `MithraCodeGeneratedDatabaseObject` interface declares 12
`*GenericSource` methods (`mithra/database/MithraCodeGeneratedDatabaseObject.java:40-58`), emitted by
`generator/templates/CommonDatabaseObjectAbstract.jspi:64-185` even for sourceless objects (returning
null). `MithraAbstractDatabaseObject` derives `source` and passes it into `getDatabaseTypeGenericSource`/
`getConnectionGenericSource`/`getSchemaGenericSource` at ~25 read/write/helper sites. `SqlQuery` tracks
a `SourceOperation` per query (`getNumberOfSources()` drives a per-source execution loop); every
`AtomicEqualityOperation` implements `SourceOperation`. `RelatedFinder` exposes `getSourceAttribute()`/
`getSourceAttributeType()`, every `Attribute` has `isSourceAttribute()`, the connection-manager
contract is split three ways (`Sourceless`/`IntSource`/`ObjectSource`), and `CacheRefresher`/`cacheloader`/
transaction ops segregate by source. There is no seam to compile source-awareness out.

**(b) Client-server / remote mode — LOW–MEDIUM coupling.** `remote/` (54 files) is a drop-in alternate
implementation of `MithraObjectReader`/`MithraDatedObjectPersister` (`remote/RemoteMithraObjectPersister.java`).
The portal holds a single `mithraObjectReader` field and dispatches uniformly — **no `instanceof Remote`
branching anywhere in the portal**. The only fork is at config-init time in the generated
`Finder.initializeClientPortal` (chosen when `config.isThreeTierClient()`). The residual coupling:
`MithraConfigurationManager` imports `RemoteMithraService`/`RemoteMithraObjectConfig` and `MithraManager`
imports `MithraRemoteTransactionProxy`, so config/transaction code has compile-time references to the
remote package even in local-only deployments.

**(c) XML configuration — LOW coupling.** Two XML layers: object-definition XML is **compile-time only**
(consumed by `reladomogen`; the generated runtime contains no XML logic), and runtime-config XML is
**load-time only**. The runtime parse is a thin skin: `MithraRuntimeUnmarshaller` (FreyaXml-generated)
is called once in `MithraConfigurationManager.parseConfiguration()` producing a plain `MithraRuntimeType`
bean graph, and `initializeRuntime(MithraRuntimeType)` is a **public, XML-free entry point**. Tests prove
a fully programmatic path (`test/overlap/AbstractOverlapFixerTest.java:72-81` builds `MithraRuntimeType`/
`ConnectionManagerType` in pure Java; `MithraTestResource` accepts a pre-built `MithraRuntimeType`). After
load, no portal/finder/attribute holds XML types.

**(d) Off-heap storage — MEDIUM coupling.** Off-heap caches (`OffHeapFullDatedCache`,
`OffHeapFullDatedTransactionalCache`, `NonUniqueOffHeapIndex`, `OffHeapSemiUniqueDatedIndex`) are
parallel subclasses behind `AbstractDatedCache` and the `Cache`/`Index`/`SemiUniqueDatedIndex`
interfaces (only dated objects can be off-heap). But there are three leaks into the common contract:
`MithraDataObject.zCopyOffHeap()` is on the root interface (importing `MithraOffHeapDataObject`) and
every generated data class implements it (throwing when off-heap is off); `AbstractDatedCache`'s
constructor and two abstract factory methods carry `OffHeapDataStorage` in their signatures even for
on-heap subclasses (which pass/ignore null); and `Cache.isOffHeap()` + four size methods are on the
interface. The on-heap cache body itself has only two `isOffHeap()` hash-dispatch branches.

| Feature | Isolation mechanism | Coupling | Key entanglement points |
|---|---|---|---|
| Source attributes / sharding | `Object source` generic routing; 3-way connection-manager split | **HIGH** | 12 `*GenericSource` methods; ~25 DB-layer sites; `SourceOperation` in `SqlQuery`; `getSourceAttribute()` on `RelatedFinder`; `isSourceAttribute()` on every `Attribute` |
| Client-server / remote | `MithraObjectReader`/persister interface; portal dispatches uniformly | **LOW–MEDIUM** | `MithraConfigurationManager`/`MithraManager` compile-time imports; generated `initializeClientPortal` fork |
| XML configuration | `MithraRuntimeType` bean graph; `initializeRuntime(MithraRuntimeType)` public entry | **LOW** | XML parse isolated to `parseConfiguration`; programmatic path proven by tests |
| Off-heap storage | parallel cache/index subclasses behind `Cache`/`AbstractDatedCache` | **MEDIUM** | `MithraDataObject.zCopyOffHeap()` on root interface; `OffHeapDataStorage` in `AbstractDatedCache` signatures; `Cache.isOffHeap()` |

## Testing patterns

Source/sharding: tests using `*StringSource*`/`*IntSource*` data files and source-attributed XML
(`DatedAccount.xml`). Remote: `multivm/` suites + `TestClientPortal`. Off-heap: `offheap/` package run
via `MithraConfigOffHeapFullCache.xml` as a third `MithraTestSuite` pass. Programmatic config:
`AbstractOverlapFixerTest`.

## Code references

- Source: `mithra/database/MithraCodeGeneratedDatabaseObject.java`, `MithraAbstractDatabaseObject.java`, `finder/SourceOperation.java`, `finder/SqlQuery.java`, `finder/RelatedFinder.java`, `attribute/SingleColumn{String,Integer}Attribute.java`, `cache/CacheRefresher.java`, `connectionmanager/{Object,Int}SourceConnectionManager.java`, `reladomographql/docs/source-attribute.md`
- Remote: `mithra/remote/` (54 files; `RemoteMithraObjectPersister.java`, `RemoteMithraService.java`), `portal/MithraObjectReader.java`, `util/MithraConfigurationManager.java` (lazyInitRemoteObjects 392)
- XML: `mithra/mithraruntime/` (`MithraRuntimeUnmarshaller.java`, `MithraRuntimeType.java`), `util/MithraConfigurationManager.java` (parseConfiguration 1101, initializeRuntime 284), `test/overlap/AbstractOverlapFixerTest.java`
- Off-heap: `mithra/MithraDataObject.java` (zCopyOffHeap 75), `cache/Cache.java` (isOffHeap 263), `cache/AbstractDatedCache.java` (114, 287-289), `cache/offheap/`, `generator/templates/readonly/Data*.jspi`
