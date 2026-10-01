# Gap-starting writes and insert overlap: insertion checks a transaction-active point; additive insertion and explicit composition are separate from full-payload replacement

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/`; **`test/`** =
> `reladomo/src/test/java/com/gs/fw/common/mithra/test/`.
>
> Source and first-party test definitions inspected on 2026-10-01. No Reladomo tests,
> database reproducer, or Parallax merge gate were executed in this research pass.

## Finding and evidence limits

Reladomo has no dedicated one-step complete-payload operation identified in the inspected
dated-object API that starts in a business-time gap, fills that gap, and replaces later existing
coverage. Ordinary `insert`/`insertUntil` insert one row rather than closing and splitting
overlapping predecessors. `insertWithIncrement[Until]` resolves later coverage but applies
numeric additions. Existing-state setters can replace a larger business range, and an application
can compose termination of overlapping coverage with full insertion; the latter sequence is
source-derived, not an executed guarantee. These conclusions follow the
[public temporal API](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/MithraDatedTransactionalObject.java#L26-L106),
[ordinary and additive director paths](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L71-L280),
and [bounded update and termination](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1011-L1259).

The inspected ordinary insertion chain does **not** establish a whole-range nonoverlap invariant.
The concrete counter-scenario is an existing current-processing row `[June, infinity)` and an
ordinary `insertUntil` of `[April, July)` for the same logical key. April is empty; the proposed
row has a different business end from the existing row. The director issues neither a range
resolution nor predecessor closure. The generated schema supplies no exclusion constraint.
Acceptance and resulting overlapping coverage are therefore an inference from those paths,
not a database reproducer. Custom application validation or custom DDL can provide stronger
guarantees than the standard inspected runtime/schema.
[insertion check and enqueue](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L71-L103),
[bounded insertion delegates insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L260-L280),
[Postgres generated keys/indexes](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogenutil/src/main/java/com/gs/fw/common/mithra/generator/dbgenerator/PostgresGeneratorDatabaseType.java#L49-L97).

## Ordinary insertion call chain and validation

For business-dated generated objects, `insertUntil(until)` obtains write behavior and delegates
to `DatedInMemorySameTxBehavior.insertUntil`; that behavior calls
`cache.getOrCreateContainer(txData)`, then the temporal director. Unbounded `insert` follows the
same behavior/container/director shape. Outside a transaction the in-memory no-transaction
behavior refuses insertion; enrollment inside a transaction copies or allocates data and switches
to the same-transaction behavior.
[generated bounded entrypoint](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/templates/datedtransactional/Abstract.jsp#L199-L208),
[runtime entrypoints](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java#L699-L726),
[same-transaction dispatch](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/inmemory/DatedInMemorySameTxBehavior.java#L67-L109),
[write enrollment](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/inmemory/DatedInMemoryTxEnrollBehavior.java#L55-L64),
[outside-transaction rejection](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/inmemory/DatedInMemoryNoTxBehavior.java#L64-L87).

The bitemporal director checks that processing as-of is infinity and business as-of is finite.
It rejects insertion if `container.getActiveDataFor(businessDate)` is non-null, stamps processing
start/end, defaults unset business boundaries, activates one new row and queues insertion.
`insertUntil` sets the business end, or checks that a pre-set end agrees with `until`, then
delegates to `insert`. These routines do not call `getObjectsForRange`,
`checkDatesAreWithinRange`, or the overlap detector. No business `from < until` validation
appears in this inspected director chain. Recovery has separate, stronger date checks and must
not be used as evidence for ordinary insertion.
[ordinary insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L71-L103),
[until consistency](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L260-L280),
[as-of validation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1305-L1339),
[recovery validation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L804-L856).

Business-only `GenericNonAuditedTemporalDirector` has the same point-check structure and a
database-check TODO. Processing-only `AuditOnlyTemporalDirector` does not support the
business-bounded/additive family.
[business-only insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericNonAuditedTemporalDirector.java#L55-L89),
[processing-only unsupported operations](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/AuditOnlyTemporalDirector.java#L109-L122).

The final queueing step is `MithraRootTransaction.insert` → `addInsert`, optionally immediate
flush. It does not add a logical-key or range-exclusion read.
[transaction insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraRootTransaction.java#L406-L425).

## Cache modes and what the point check actually sees

`getActiveDataFor` scans **activeDataList**, not all committed rows. `addCommittedData` adds
persisted rows to **committedDataList** and **inTxObjects**. `addObjectForTx` activates newly
inserted/current successor data. Thus the point check catches an own-transaction activated row
covering the insertion's starting coordinate. Seeding a container with cached committed rows
alone does not populate the list it checks.
[active point scan and activation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/AbstractTemporalContainerWithBusinessDate.java#L119-L164),
[committed and active lists](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/AbstractTemporalContainerWithBusinessDate.java#L262-L294),
[current-processing committed filter](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/BiTemporalTransactionalDataContainer.java#L40-L48).

The cache creates a per-transaction container keyed by the non-dated primary key. It seeds
that container from the semi-unique index only when participation does **not** require
transactional participation on read; otherwise it can initialize an empty container with
`setAnyData`. The path performs no missing-data query. Full and partial cache knowledge
therefore must not be mistaken for a mandatory fresh database collision check.
[container construction](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/AbstractDatedTransactionalCache.java#L564-L594),
[cached committed seeding](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/FullSemiUniqueDatedIndex.java#L1468-L1490).

`cache.put` writes transaction-local data into the semi-unique dated index and the object identity
index. The transaction-local semi-unique index delegates to `FullSemiUniqueDatedIndex.put`,
whose dated bucket replaces an exact dated key or retains another entry; it does not reject
intersecting intervals. Pairwise overlap collection is a separate API. First-party full/partial
cache tests intentionally insert overlapping rows and then collect them.
[cache insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/AbstractDatedTransactionalCache.java#L68-L104),
[transaction-local insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/TransactionalSemiUniqueDatedIndex.java#L264-L285),
[dated bucket insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/FullSemiUniqueDatedIndex.java#L438-L480),
[separate overlap detection](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/FullSemiUniqueDatedIndex.java#L185-L213),
[full transactional cache overlap test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/FullDatedTransactionalCacheTest.java#L41-L90),
[partial cache overlap tests](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/PartialDatedCacheTest.java#L35-L123).

## Physical uniqueness and concurrency

Generated physical primary keys append every as-of **to** column to the declared primary key.
For `TinyBalance`, these are business `THRU_Z` and processing `OUT_Z`. Standard PostgreSQL
generation emits ordinary keys/indexes, not a temporal exclusion constraint.
Two current-processing rows with different `THRU_Z` values can therefore satisfy physical
uniqueness while overlapping in business time.
[physical key construction](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/java/com/gs/fw/common/mithra/generator/MithraObjectTypeWrapper.java#L1121-L1201),
[TinyBalance mapping](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/reladomo-xml/TinyBalance.xml#L26-L38),
[Postgres generation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogenutil/src/main/java/com/gs/fw/common/mithra/generator/dbgenerator/PostgresGeneratorDatabaseType.java#L49-L97).

Range-modifying paths call `getObjectsForRange`; missing coverage knowledge triggers a persisted
range query. That query requests dialect-dependent read locking according to participation mode.
This protects resolved predecessors in the ways described in
[transaction concurrency scope](09-transactions-locking.md#bitemporal-concurrency-scope).
Ordinary insertion does not issue that range query and has no fixed scalar absence precondition
in the inspected API. Transaction-local containers, row-version gates on existing predecessors,
and exact-row primary-key uniqueness are not whole-range phantom protection. Serializable
isolation cannot make a non-issued overlap query validate already existing later coverage.
For concurrently created distinct-end intervals, no unconditional exclusion mechanism was found
in the traced ordinary insert path; actual conflict behavior can depend on custom constraints,
isolation, and prior queries. No concurrency reproducer was executed.
[range resolution](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/AbstractTemporalContainerWithBusinessDate.java#L294-L344),
[locking range query](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java#L117-L201),
[transaction-local containers](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/AbstractDatedTransactionalCache.java#L564-L594).

## Alternatives and their boundaries

`insertWithIncrementUntil` requires no transaction-active state at the start, resolves later
overlapping coverage, and inserts from the starting date to the earliest later segment's start.
Each nonzero double or BigDecimal in the new payload becomes an increment applied to existing
coverage inside the range. If no later segment exists, it delegates to ordinary bounded insertion.
It does not assign all supplied fields to later rows, and it does not establish one continuous
full-payload interval across arbitrary later gaps.
[bounded additive insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L184-L258),
[numeric increment segment behavior](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L875-L964).

There is a tested **composition**: insert-with-increment, flush, then change a field through an
ordinary setter. `testInsertWithIncrementOneSegmentThenUpdate` changes quantity from 12.5 to
15.8 and expects the later segment also to become 15.8.
This demonstrates crossing from a newly inserted foothold into later existing coverage, but
is neither a one-step replacement nor a test of the exact bounded full-payload scenario.
[compound test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java#L3154-L3201).

A bounded setter's equality optimization is conditional: it skips an equal value only when
the starting row's business end reaches `until`. A foothold ending in June with an `until`
in July therefore still invokes range update even for an equal-at-start assignment.
The detached attribute-copy path instead compares supplied/start values unconditionally and
can skip such a field. These are different paths; neither should be presented as an arbitrary
full-payload command contract.
[bounded setter](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java#L1045-L1053),
[generated end-aware equality guard](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/templates/datedtransactional/Abstract.jsp#L550-L555),
[bounded attribute-copy equality](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java#L1307-L1316).

The bounded director update constructs one successor using the **starting object's** payload,
closes all overlapping predecessors, and sets the successor to the entire requested range.
It can fill internal gaps and carry starting-state unassigned fields across later intervals.
This is not Parallax's proposed preserve-each-interval sparse patch behavior.
[starting payload and predecessor handling](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1011-L1110),
[continuous successor](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1112-L1124).

The named detached merge is also not a gap-overwrite alternative. Generated entrypoints dispatch
according to object state. A new in-memory object's bounded merge delegates to ordinary
`insertUntil`. A genuinely detached existing object's merge finds its original, throws if
absent, then copies values into that live object.
[generated merge dispatch](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/templates/datedtransactional/Abstract.jsp#L410-L419),
[new-object bounded merge](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/inmemory/DatedInMemoryBehavior.java#L179-L187),
[detached existing merge](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DatedDetachedSameTxBehavior.java#L186-L224).

For the concrete `[June, infinity)` → full `[April, July)` scenario, an application can
source-derive a sequence: resolve the June state, `terminateUntil(July)`, then insert a new
April object with full values using `insertUntil(July)` in the same transaction. Bounded
termination preserves the July residual and processing history, so the subsequent insert
has no surviving overlap in this example. Generalizing requires resolving/terminating all
overlapping coverage and coordinating absent coverage concurrently. No test of this exact
sequence was identified or executed; it does not imply a fixed caller absence/range guarantee.
[bounded termination and residual preservation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1185-L1259),
[bounded insertion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L260-L280).

## Scenario matrix and test coverage

The matrix is source-derived unless its evidence cell names a test. Dates use half-open
business intervals and current processing time.

| Scenario | Ordinary insert/insertUntil | Evidence status |
| --- | --- | --- |
| New key, insert April–July | Inserts one bounded row | `testInsertUntil`, `TestDatedBitemporal:3376–3411`; definition inspected |
| Another own-transaction active row covers April | Point check rejects | Director + active-list scan; no targeted rejection test found |
| Persisted state covers April | Not a guaranteed fresh collision check; committed-list/cache distinction applies | Container and cache source; no rejection reproducer |
| April is a gap, June–infinity exists, insert April–July | No whole-range check or safe overwrite; distinct-end overlap can survive standard physical uniqueness | Source inference, no reproducer |
| New row ends exactly when next row starts | Point/range geometry permits adjacency; physical uniqueness depends on distinct end tuple | `AsOfAttribute` interval predicates; no targeted insertion adjacency test found |
| Gap-start additive insert, later existing coverage | Inserts foothold and adds numeric payload to later segments | `testInsertWithIncrementUntilOneSegment`, `TestDatedBitemporal:3477–3525`; definition inspected |
| Same transaction: insert, flush, increment, earlier additive insert | Transaction-active segmentation is reused | `testTripleIncrement`, `TestDatedBitemporal:225–273`; definition inspected |
| Two concurrent insertions overlap but have different ends | No universal runtime/standard-schema exclusion found | No targeted concurrent different-end test identified or executed |

The cited ordinary/additive definitions are
[bounded ordinary test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java#L3376-L3411),
[bounded additive test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java#L3477-L3525),
[same-transaction composition](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java#L225-L273);
adjacency geometry comes from
[interval predicates](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/attribute/AsOfAttribute.java#L548-L577).
Equivalent additive definitions exist under optimistic participation
([optimistic bounded additive test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporalOptimisticLocking.java#L2749-L2797))
and for business-only objects
([business-only bounded additive test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedNonAudited.java#L2349-L2398)).
The suite registers the temporal tests under its selected runtime configuration;
full/partial cache selection is configuration-dependent, not a test executed in this pass
([suite cache-mode selection](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/MithraTestSuite.java#L50-L56),
[temporal suite registration](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/MithraTestSuite.java#L160-L196)).

Overlap collection/repair is separate retrospective machinery; see
[temporal repair and recovery](18-temporal-repair-and-recovery.md).
No new Parallax semantics are adopted by this descriptive prior-art note.
