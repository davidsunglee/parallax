# Identity columns: `identity="true"` omits the PK from INSERT and reads it back post-insert via a per-dialect `getLastIdentitySql` query — never JDBC `getGeneratedKeys`

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The XSD (`reladomogen/src/main/xsd/mithraobject.xsd:436-440`, repeated for pure objects at
1240-1244) defines `identity` as a boolean attribute flag, default `false`: "Must be set to true if
this is an identity column. It's usually part of the primary key as well." It is a **separate** flag
from `primaryKeyGeneratorStrategy` ("Max"/"SimulatedSequence", xsd:430-435); an identity attribute
sets neither strategy — the two mechanisms coexist as independent XSD attributes with no
generator-time cross-validation between them. Only `int` and `long` attributes may be identity:
`JavaType.mayBeIdentity()` defaults to `false` (`generator/type/JavaType.java:226-229`) and is
overridden to `true` only in `IntJavaType.java:96` and `LongJavaType.java:88`.

## Generator treatment

- `MithraObjectTypeWrapper.addAttribute` collects identity attributes into `identityAttributeList`
  (`generator/MithraObjectTypeWrapper.java:972-975`); `getIdentityAttribute()` returns the first
  (2289-2298) — the runtime contract assumes at most one per class.
- **Hard validation**: identity + as-of attributes is a generation error — "cannot and must never be
  combined with as-of-attributes. This is a serious violation of temporal semantics and will never
  be supported" (`generator/MithraObjectTypeWrapper.java:894-897`). This is the only identity
  exclusivity rule; there is no check against `primaryKeyGeneratorStrategy`.
- **INSERT omits the identity column**: `getInsertFields()` and `getInsertQuestionMarks()` skip any
  `isIdentity()` attribute (`generator/MithraObjectTypeWrapper.java:2248-2276`), as does the
  generated `setInsertAttributes` (`reladomogen/src/main/templates/CommonTransactionalDatabaseObjectAbstract.jspi:25`).
- The generated DatabaseObject overrides `hasIdentity()` to return `true`
  (`templates/CommonDatabaseObjectAbstract.jspi:545-550`) and generates a `setIdentity(Connection,
  Object, MithraDataObject)` method (`templates/CommonNonDatedDatabaseObjectAbstract.jspi:61-91`).
- The generated Data class implements three hooks (`templates/readonly/DataCommon.jspi:235-249`):
  `zGetIdentityValue()` (boxes the current value), `zHasIdentity()` (constant true/false), and
  `zSetIdentity(Number)` (calls the ordinary setter with `intValue()`/`longValue()`). The interface
  contract is `mithra/MithraDataObject.java:59-61`. The setter itself stays public; the flag is also
  baked into the runtime attribute metadata as an extra constructor parameter for int/long extractors
  (`generator/AbstractAttribute.java:1513-1517`, consumed by
  `mithra/attribute/SingleColumnLongAttribute.java:77-81` and `SingleColumnIntegerAttribute.java:77-81`).

## Runtime insert path

`MithraAbstractDatabaseObject.zInsert` (`mithra/database/MithraAbstractDatabaseObject.java:3580-3631`)
executes the identity-column-free INSERT, then — on the **same connection** — reads the key back:

```java
if (dataToInsert.zHasIdentity())      // line 3612
{
    this.setIdentity(con, source, dataToInsert);
}
```

The base `setIdentity` is a no-op (`MithraAbstractDatabaseObject.java:2601-2603`); the generated
override runs `dt.getLastIdentitySql(tableName)` as a separate `PreparedStatement`, requires exactly
one row, and writes column 1 onto the data object via the identity attribute's setter
(`CommonNonDatedDatabaseObjectAbstract.jspi:62-91`). JDBC `Statement.getGeneratedKeys` is never used
functionally — it appears only as pass-through in `DelegatingStatement.java:150` and
`PrintablePreparedStatement.java:413`. Because the key is set on the in-flight `MithraDataObject`
before `zSetInserted()` runs (`mithra/transaction/InsertOperation.java:34-38`), commit-time cache
indexing sees the DB-assigned primary key, and the test suite asserts the value is visible while the
transaction is still open.

**Batching**: identity inserts are never batched. `MithraRootTransaction.addInsert`
(`mithra/transaction/MithraRootTransaction.java:244-279`) flushes the operation buffer immediately
(`executeBufferedOperations()`) whenever `zGetTxDataForRead().zHasIdentity()` is true, so
`insertAll()` on an identity class degenerates to per-row `zInsert` + key read-back;
`zBatchInsert`/`BatchInsertOperation` contain no identity code. In the 3-tier (remote) topology the
server ships the value back: `RemoteMithraObjectPersister.insert` calls
`result.getIdentityValue()` / `mithraDataObject.zSetIdentity(...)`
(`mithra/remote/RemoteMithraObjectPersister.java:463-478`; `RemoteInsertResult.java:127-129`).

## DatabaseType support matrix

`DatabaseType` declares three methods (`mithra/databasetype/DatabaseType.java:59-63`):
`getLastIdentitySql(tableName)`, `getIdentityTableCreationStatement()` (DDL suffix, used by
`SingleColumnLongAttribute.appendColumnDefinition`, `mithra/attribute/SingleColumnLongAttribute.java:292-300`),
and `getAllowInsertIntoIdentityStatementFor(tableName, onOff)` (used only by the test-data loader
`insertData`, `MithraAbstractDatabaseObject.java:1703,1745`). Defaults in `AbstractDatabaseType`:
DDL suffix `" identity"` (Sybase/MSSQL syntax, line 551-554) and empty allow-insert statement (556-559).

| Dialect | `getLastIdentitySql` | DDL suffix | identity-insert toggle |
|---|---|---|---|
| Sybase (`SybaseDatabaseType.java:794-802`) | `select @@identity` | inherited `" identity"` | `SET IDENTITY_INSERT <t> ON/OFF` |
| MsSql (`MsSqlDatabaseType.java:502-510`) | `select @@identity` | inherited `" identity"` | `SET IDENTITY_INSERT <t> ON/OFF` |
| H2 (`H2DatabaseType.java:350-353,453-456`) | `select IDENTITY()` | `GENERATED BY DEFAULT AS IDENTITY` | inherited empty |
| Postgres (`PostgresDatabaseType.java:371-374`) | `select IDENTITY()` (H2 string, not valid Postgres SQL) | inherited | inherited |
| Maria (`MariaDatabaseType.java:356-359`) | `select IDENTITY()` (not valid MariaDB SQL) | inherited | inherited |
| Oracle (`OracleDatabaseType.java:507-510`) | `select IDENTITY()` (not valid Oracle SQL) | inherited | inherited |
| Derby (`DerbyDatabaseType.java:148-151`) | `values IDENTITY_VAL_LOCAL()` | inherited | inherited |
| Udb82/DB2 (`Udb82DatabaseType.java:325-340`) | `SELECT IDENTITY_VAL_LOCAL() FROM <t>` | `GENERATED ALWAYS AS IDENTITY` | `<t> OVERRIDING SYSTEM VALUE` |
| Snowflake (`SnowflakeDatabaseType.java:503-506`) | returns `null` | inherited | inherited |
| Generic (`GenericDatabaseType.java:152-160`) | throws `RuntimeException("not implemented")` | throws | inherited |

Only Sybase, MsSql, H2, Derby, and DB2 return read-back SQL that is valid for their engine;
Postgres/Maria/Oracle carry a copy of the H2 string. Sybase bcp bulk-insert additionally skips
identity columns when building column metadata (status bit 128,
`SybaseDatabaseType.java:1010-1015`).

## Testing patterns

`TestIdentityTable` (`reladomo/src/test/java/com/gs/fw/common/mithra/test/TestIdentityTable.java`,
in `MithraTestSuite.java:215`, H2-backed) covers single insert, `insertAll`, batch/multi update, and
delete; the key assertions are `it.getObjectId()!=0` inside the open transaction (lines 44-57 for
one row, 59-80 for a 3-element list). The fixture object never sets `objectId` before insert
(151-159). `TestSybaseIdentityTable` repeats the six scenarios against real Sybase. The metadata
fixture is `reladomo/src/test/reladomo-xml/IdentityTable.xml`: `objectId` is
`javaType="long" primaryKey="true" identity="true"` in a three-column composite PK.
`BcpSimpleWithIdentity.xml` exercises Sybase bulk-copy with an identity column.

## Code references

- `reladomogen/src/main/xsd/mithraobject.xsd` (436-440, 1240-1244)
- `generator/MithraObjectTypeWrapper.java` (as-of conflict 894, addAttribute 972, getInsertFields 2248, getIdentityAttribute 2289, getTotalColumnsInInsert 2306); `generator/AbstractAttribute.java` (isIdentity 428, extractor params 1513, mayBeIdentity 1520); `generator/type/{JavaType:226, IntJavaType:96, LongJavaType:88}`
- `reladomogen/src/main/templates/CommonNonDatedDatabaseObjectAbstract.jspi` (setIdentity 61-91), `CommonDatabaseObjectAbstract.jspi` (hasIdentity 545), `CommonTransactionalDatabaseObjectAbstract.jspi` (25), `readonly/DataCommon.jspi` (235-249)
- `mithra/MithraDataObject.java` (59-61); `mithra/database/MithraAbstractDatabaseObject.java` (insertData identity toggle 1703/1745, hasIdentity 2596, setIdentity 2601, zInsert 3580-3631, zBatchInsert 4611)
- `mithra/transaction/MithraRootTransaction.java` (addInsert 244-279), `mithra/transaction/InsertOperation.java` (34-38)
- `mithra/remote/RemoteMithraObjectPersister.java` (463-478), `mithra/remote/RemoteInsertResult.java` (127-129)
- `mithra/databasetype/DatabaseType.java` (59-63), `AbstractDatabaseType.java` (551-559), plus per-dialect lines in the matrix above; `mithra/attribute/SingleColumnLongAttribute.java` (77-81, 292-300)
- Tests: `reladomo/src/test/java/com/gs/fw/common/mithra/test/TestIdentityTable.java`, `TestSybaseIdentityTable.java`; fixtures `reladomo/src/test/reladomo-xml/IdentityTable.xml`, `BcpSimpleWithIdentity.xml`
