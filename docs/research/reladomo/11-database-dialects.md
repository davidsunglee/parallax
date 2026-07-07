# Database portability is isolated behind `DatabaseType`, obtained from the connection manager at query time

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

All SQL-dialect variation lives behind `DatabaseType` (`mithra/databasetype/DatabaseType.java`, extends
`CommonDatabaseType` which declares the 14 `getSqlDataTypeFor*` mappings). Each dialect is a singleton
extending `AbstractDatabaseType` (which provides defaults and recursive SQLException-chain walkers).
Concrete dialects: `PostgresDatabaseType`, `H2DatabaseType`, `OracleDatabaseType`, `SybaseDatabaseType`,
`SybaseIqDatabaseType`, `SybaseIqNativeDatabaseType`, `MsSqlDatabaseType`, `MariaDatabaseType`,
`Udb82DatabaseType` (DB2), `SnowflakeDatabaseType`, `DerbyDatabaseType`, and a stub `GenericDatabaseType`.

The seam: connection managers return the `DatabaseType` (`SourcelessConnectionManager.getDatabaseType()`,
`ObjectSourceConnectionManager.getDatabaseType(Object)`). `MithraAbstractDatabaseObject` obtains it via
the generated `getDatabaseTypeGenericSource(source)` and calls it at every SQL decision point —
`getSelect` (line 1653), `limitRowCount` (477), temp-table DDL (619), `refresh` lock suffix (2229),
aggregate SELECT (2349), multi/batch/bulk insert (4636+), error classification (1831), timestamp
bind/read (in generated inflation). Nothing uses a registry; the dialect always comes from the
connection manager.

What varies (capability matrix, abbreviated):

| Concern | Postgres | H2 | Oracle | Sybase ASE | MsSql | DB2 (Udb82) | Snowflake |
|---|---|---|---|---|---|---|---|
| Row limit | `LIMIT n+1` | `ROWNUM()<=n` | `ROWNUM<=n` | `TOP n+1` | `TOP n+1` | `FETCH FIRST n+1 ROWS` | `LIMIT n+1` |
| `SET ROWCOUNT` | no | no | no | yes | yes | no | no |
| Read lock | `FOR SHARE OF t0` | (none) | `FOR UPDATE OF col` | `holdlock` per-table | `WITH(serializable)` | `WITH RR…` | none |
| Temp table | `CREATE TEMPORARY … ON COMMIT DROP/PRESERVE` | `CREATE GLOBAL TEMPORARY` | `CREATE GLOBAL TEMPORARY … ON COMMIT DELETE/PRESERVE` | `CREATE TABLE #name` | `#name` | `DECLARE GLOBAL TEMPORARY SESSION.name` | `CREATE TEMPORARY` |
| Bulk load | none | none | none | BCP (`JtdsBcpBulkLoader`) | none | none | none |
| Multi-insert | none | optional VALUES | none | `UNION ALL SELECT` | `VALUES(...)` | `VALUES(...)` | none |
| Deadlock code | states 40P01/40001 | 40001 | 40001 | 1205 | 1205/1211 | -911 / 57033 | never |
| Unique-violation | state 23505 | 23505/23001 | 23001 | 2601 | 2601 | -803 | 23505 |
| Max IN clauses | 240 | 240 | 240 | 420 | 2000 | 1000 | 240 |

`MariaDatabaseType` (not shown in the matrix) uses `LIMIT n+1` for row-limit and `LOCK IN SHARE MODE`
for read locking; it disables multi-insert — both `hasSelectUnionMultiInsert()` and `hasValuesMultiInsert()`
return `false` (`MariaDatabaseType.java:341-349`), so inserts fall back to standard single-row JDBC
batching (`getMaxPreparedStatementBatchCount()` = 100).

**PostgreSQL specifics** (`mithra/databasetype/PostgresDatabaseType.java`): types `boolean`, `bytea`,
`float8/float4`, `int2/int8`, unbounded `varchar`, `numeric` (lines 225-295); pagination via
`LIMIT n+1` appended in `getSelect` (line 111) with `hasTopQuery()=true`; row lock `FOR SHARE OF t0`
(no `FOR UPDATE`); capped DELETE via a `ctid = any(array(select ctid … limit n))` trick (line 139);
temp tables `ON COMMIT DROP` in-tx else `PRESERVE ROWS`, auto-dropped (`nonSharedTempTablesAreDroppedAutomatically=true`);
`UPDATE … FROM tempTable t1 WHERE …` join syntax (no `t0.` prefix in SET); error codes 40P01/40001
(deadlock) and 23505 (unique); **no bulk loader** (`hasBulkInsert()=false`); `EXTRACT(... )` and
`AT TIME ZONE` for date/timezone extraction; a settable `tempSchema`.

## Testing patterns

Dialect logic is mostly exercised through H2 (the default in-memory DB). Unit tests: `SybaseDatabaseTypeTest`
(connection-dead/deadlock classification), `H2DatabaseTypeForTests` (test subclass that can suppress
temp-table DDL). Real-DB integration scaffolding: `MithraPostgresTestAbstract` + `PostgresTestConnectionManager`
(see §12).

## Code references

- `DatabaseType.java`, `AbstractDatabaseType.java`, `mithra/util/CommonDatabaseType.java`
- `PostgresDatabaseType.java`, `H2DatabaseType.java`, `OracleDatabaseType.java`, `SybaseDatabaseType.java`, `SybaseIqDatabaseType.java`, `SybaseIqNativeDatabaseType.java`, `MsSqlDatabaseType.java`, `MariaDatabaseType.java`, `Udb82DatabaseType.java`, `SnowflakeDatabaseType.java`, `DerbyDatabaseType.java`, `GenericDatabaseType.java`
- `mithra/connectionmanager/` — `SourcelessConnectionManager.java`, `ObjectSourceConnectionManager.java`, `IntSourceConnectionManager.java`, `ConnectionManagerWrapper.java`, `XAConnectionManager.java`
- `mithra/database/MithraCodeGeneratedDatabaseObject.java`
