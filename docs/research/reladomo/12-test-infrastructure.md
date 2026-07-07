# The test suite is an H2-based, no-mock integration harness; the same tests re-run on real vendors via swapped connection managers

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The ~1,700-file test tree:

```text
reladomo/src/test/
├── java/.../test/
│   ├── MithraTestSuite.java            # master H2 suite (~70 classes)
│   ├── MithraTestAbstract.java         # base for H2 tests
│   ├── Mithra<DB>TestAbstract.java     # Postgres/Oracle/Sybase/Db2/Maria/MsSql/Snowflake/SybaseIq bases
│   ├── Mithra<DB>TestSuite.java        # per-vendor suite → Test<DB>GeneralTestCases
│   ├── <DB>TestConnectionManager.java  # per-vendor CM
│   └── aggregate/ attribute/ cacheloader/ domain/(828 gen files) offheap/ multivm/ pure/ …
├── reladomo-xml/                       # 407 object definitions
└── resources/
    ├── MithraConfig{Partial,Full,OffHeapFull}Cache.xml   # H2 runtime configs
    ├── Mithra<DB>TestConfig.xml                          # per-vendor configs
    ├── credentials.properties                            # all real-DB creds = "unpublished"
    └── testdata/*.txt                                    # flat-file fixtures
reladomo/src/test-util/.../test/
    ├── MithraTestResource.java          # the harness
    ├── ConnectionManagerForTests.java   # H2/Derby in-memory CM
    └── MithraTestDataParser.java        # flat-file parser
```

**No-mock harness** (`MithraTestResource`): on `setUp()` it starts H2 (just
`Class.forName("org.h2.Driver")`), parses the runtime config
(`MithraManager.parseConfiguration`), wires connection managers to generated database objects, creates
tables (`verifyTable` → `dropTestTable` → `createTestTable`), and inserts flat-file data parsed by a
`StreamTokenizer` state machine (`class <FQN>` header, comma-separated attribute row, then data rows).
`tearDown()` rolls back, deletes all rows, and resets. Each logical "source" gets its own
`jdbc:h2:mem:<schema>` database.

**Cross-database** testing reuses the *same* behavioral test logic: each `Test<DB>GeneralTestCases`
extends `Mithra<DB>TestAbstract` (which constructs `MithraTestResource` with the vendor's `DatabaseType`
and connection manager) and **delegates** to the shared H2 test instances as plain method calls
(e.g. `new CommonVendorTestCases().testRollback()`). Verification uses `validateMithraResult(op, sql, minSize)`:
run the ORM query with `setBypassCache(true)` and the caller-supplied raw SQL, then compare row-by-row
via a `ResultSetComparator`.

Two precise behavioral assertion patterns recur:

- **Retrieval-count**: `getRetrievalCount()` (= `MithraManager.getDatabaseRetrieveCount()`) before/after
  an operation asserts the exact number of DB round-trips (cache hit ⇒ unchanged; deep fetch ⇒ +N).
- **Expected-SQL**: `Log4JRecordingAppender` captures the generated SQL string and tests assert its
  structure (e.g. count of `"left join"`).

**Agnostic vs dialect-specific split.** The default build runs `MithraTestSuite` on H2 (partial + full,
and a third off-heap pass) — the vast majority of behavior. The 8 vendor suites live in a separate Ant
target (`mithra-vendor-test-suite`) not chained by any CI target, and are *implicitly gated* because all
`credentials.properties` entries are `"unpublished"`, so the vendor connection pools simply fail to
initialize. Vendor suites cover CRUD, large-IN chunking, batch/bulk DML, BigDecimal/timestamp precision,
rollback — plus genuinely dialect-specific tests with no H2 equivalent (e.g. Sybase BCP).

## Testing patterns

This section *is* the testing-patterns documentation; the harness itself is the unit under study.

## Code references

- `reladomo/src/test-util/.../test/MithraTestResource.java`, `ConnectionManagerForTests.java`, `AbstractMithraTestConnectionManager.java`, `TestDatabaseConfiguration.java`, `MithraTestDataParser.java`, `H2DbServer.java`
- `reladomo/src/test/.../test/MithraTestSuite.java`, `MithraTestAbstract.java`, `Mithra<DB>TestAbstract.java`, `Mithra<DB>TestSuite.java`, `<DB>TestConnectionManager.java`, `CommonVendorTestCases.java`, `util/Log4JRecordingAppender.java`
- `reladomo/src/test/resources/` — `MithraConfig{Partial,Full,OffHeapFull}Cache.xml`, `Mithra<DB>TestConfig.xml`, `credentials.properties`, `testdata/`
- Notable behavioral suites: `TestDatedBitemporal.java`, `TestAdhocDeepFetch.java`, `TestOptimisticTransactionParticipation.java`, `TestDetached.java`, `TestCache.java`, `TestPartialCache.java`, `aggregate/AggregateTestSuite.java`, `multivm/MultiVmNotificationsTestSuite.java`
