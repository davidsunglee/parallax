# Runtime model replacement and schema evolution: the portal is a static slot per generated Finder that a repeat configuration read either leaves alone or destroys and rebuilds; DDL is full `create table` scripts with no diff or migration; a row's subclass is decided by joined-table presence or a hand-written hook, never by a discriminator

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The three questions this finding answers: whether the runtime can add or replace object
definitions after startup and what an in-flight transaction sees when it does; what the code
generator emits for DDL and whether any diff, migration, or model-version facility exists; and how
the runtime treats a stored row that does not fit the loaded metadata — a subclass the model cannot
name, or a null the model forbids. The short answers: the runtime can re-read configuration and, on
request, tear a class's portal down and rebuild it in place, but there is no model-level notion of
"replace a definition" — the generated classes are the definition, loaded once by the JVM; DDL is a
set of full `create table` scripts per table, with no diff, alter, or migration support and no
runtime schema check; Reladomo has no inheritance discriminator at all, so an "unknown subclass" can
only arise in the joined-table strategy, where the row silently hydrates as its root class.

## Runtime model replacement

### The definition is the generated class; the registry is a static field per Finder

Every generated Finder holds its own portal in a `static volatile` field, initialized to a
placeholder:

```java
// reladomogen/src/main/templates/readonly/Finder.jsp:91
private static volatile MithraObjectPortal objectPortal = new UninitializedPortal("<%= wrapper.getPackageName() %>.<%= wrapper.getClassName() %>");
```

Every lookup goes through that field. `Finder.getMithraObjectPortal()` returns
`objectPortal.getInitializedPortal()` (`Finder.jsp:307-314`); the `RelatedFinder` instance's
`getMithraObjectPortal()` delegates to the same static (`Finder.jsp:940-943`); and a non-temporary
domain object's `zGetPortal()` re-resolves through the static on every call rather than caching a
reference (`reladomogen/src/main/templates/transactional/Abstract.jsp:1313-1324`). There is no
central `Map<String, MithraObjectPortal>`: `MithraConfigurationManager` reaches a class by
`Class.forName(className + "Finder")` and wraps it in a `MithraRuntimeCacheController`
(`mithra/util/MithraConfigurationManager.java:1075-1094`). The configuration manager keeps only two
bookkeeping structures — a `uninitialized` map of class name to `Config` and an `initializedClasses`
set of names (`MithraConfigurationManager.java:97-98`).

The placeholder self-initializes. `UninitializedPortal.initializeNow` calls
`MithraManager.initializePortal(className)` on first use and throws
`MithraConfigurationException("Could not ... did you forget to add it to the configuration XML?")`
if no configuration was ever registered for that class
(`mithra/portal/UninitializedPortal.java:59-72`, entry at `:429-432`). A real portal's
`getInitializedPortal()` returns itself (`mithra/portal/MithraAbstractObjectPortal.java:249-252`).
Because the placeholder resolves lazily, a class named in configuration but never touched is never
instantiated — `initializeRuntime` eagerly builds only classes configured as full-cache or
database-replicated (`MithraConfigurationManager.java:317-331`); everything else waits for first use
or for an explicit `fullyInitialize()` (`:1193-1214`, exposed at `mithra/MithraManager.java:208-211`).

`MithraManager` itself is a process singleton whose `configManager` field is replaceable through a
public setter (`mithra/MithraManager.java:78`, `:127-135`), but replacing it does not touch the
static Finder slots; a second manager would merely lose the first's bookkeeping.

### `readConfiguration` may be called repeatedly; a programmatic flag decides replace-versus-ignore

`readConfiguration(InputStream)` is parse-then-`initializeRuntime` (`MithraConfigurationManager.java:278-282`,
delegated from `MithraManager.java:740-748`). `initializeRuntime` first registers every configured
class lazily (`:343-349` → `:685-719` → `:881-957`), building one `LocalObjectConfig` per
`<MithraObjectConfiguration>` and handing it to `addUnitialized` with the runtime type's
`destroyExistingPortal` flag (`:956`). That method is the entire replace-or-ignore policy:

```java
// mithra/util/MithraConfigurationManager.java:1033-1067
private void addUnitialized(Config config, boolean destroyExistingPortal)
{
    boolean reset = false;
    synchronized (initializedClasses)
    {
        if (initializedClasses.contains(config.className))
        {
            if (!destroyExistingPortal)
            {
                return; // nothing to do
            }
            initializedClasses.remove(config.className);
            reset = true;
        }
    }
    if (reset)
    {
        try
        {
            Class finderClass = Class.forName(config.className + "Finder");
            this.invokeStaticMethod(finderClass, "zResetPortal");
            synchronized (this)
            {
                runtimeCacheControllerSet.remove(new MithraRuntimeCacheController(finderClass));
            }
        }
        catch (Exception e)
        {
            //ignore, we were trying to reset the portal
        }
    }
    synchronized (uninitialized)
    {
        this.uninitialized.put(config.className, config);
    }
}
```

Three consequences follow:

- **A class already initialized is ignored by default.** A second `readConfiguration` naming a
  class whose portal exists returns early, so the new `Config` (a different connection manager,
  cache type, or table name) is dropped without a log line or error.
- **With `destroyExistingPortal`, the old portal is torn down and the class is re-queued.**
  `zResetPortal` destroys the portal and reinstalls a fresh `UninitializedPortal`
  (`Finder.jsp:1462-1468`); the next touch rebuilds it from the newly queued `Config`.
- **A class configured but not yet initialized is silently overwritten.** `uninitialized.put`
  replaces the queued `Config`, so the last configuration read wins for any class nobody has used.

`destroyExistingPortal` is a plain Java property on the parsed runtime type
(`mithra/mithraruntime/MithraRuntimeType.java:17-33`); the string does not occur in
`reladomo/src/main/xsd/mithraruntime.xsd`, so it cannot be set from XML. Its one caller in the tree
is the test harness, which sets it when a test resource is configured to delete-on-create
(`reladomo/src/test-util/java/com/gs/fw/common/mithra/test/MithraTestResource.java:1171-1175`).

The re-queued `Config` is initialized through the same path as the first one:
`initializeObject` pops it from `uninitialized`, calls `Config.initializeObject`, and records the
name in `initializedClasses` (`:817-841`). A `LocalObjectConfig` that was already initialized
returns the existing portal without rebuilding (`:1469-1475`); otherwise it instantiates the
`DatabaseObject`, builds the full or partial cache, and reads the portal back from the Finder
(`:1476-1506`). The Finder's generated `initializePortal` constructs the new portal, destroys
whatever the static slot held, and assigns the new one (`Finder.jsp:1329-1368`, destroy-then-assign
at `:1364-1367`). `initializePortal(className)` on the manager then loads the cache — on a separate
thread if the caller is inside a transaction (`MithraConfigurationManager.java:1226-1250`).

### Unloading a portal

Unloading exists only as the teardown half of replacement. `cleanUpRuntimeCacheControllers()`
resets every initialized class through the same reflective `zResetPortal` call and clears the
manager's sets (`MithraConfigurationManager.java:239-246`, `:843-860`); the set-scoped overload
resets only the named classes (`:248-258`, `:862-879`). Both are public on `MithraManager`
(`mithra/MithraManager.java:670-678`) and are what the test harness calls in `tearDown` and when it
prunes classes a test did not use (`MithraTestResource.java:594`, `:305-320`).

`destroy()` on a real portal nulls its collaborators rather than marking a state:

```java
// mithra/portal/MithraAbstractObjectPortal.java:392-400
public synchronized void destroy()
{
    this.cache.destroy();
    this.queryCache.destroy();
    this.queryCache = null;
    this.cache = null;
    this.objectFactory = null;
    this.mithraObjectReader = null;
    this.mithraTuplePersister = null;
```

The identity cache's `destroy` destroys its indices (`mithra/cache/AbstractNonDatedCache.java:1732-1738`)
and the query cache nulls its index (`mithra/querycache/QueryCache.java:101-105`). No "destroyed"
flag is checked anywhere; a later call through a stale reference dereferences a null field.

### What an in-flight transaction sees

Nothing guards replacement against open transactions. The evidence is in who holds a direct
reference to the old portal object versus who re-resolves through the static slot:

- **Domain objects re-resolve.** A non-temporary object's `zGetPortal()`/`zGetCache()` call
  `Finder.getMithraObjectPortal()` each time (`Abstract.jsp:1300-1324`), so an object loaded before
  the swap routes its next read or write through the new portal — and its new, empty cache.
- **Transaction bookkeeping holds the old object.** Each buffered `TransactionOperation` carries the
  portal it was created with (`mithra/transaction/TransactionOperation.java:41-47`), and the
  transaction keeps a `customPortals` set of portals whose participation mode it overrode
  (`mithra/transaction/MithraLocalTransaction.java:64`), iterating them at cleanup to call
  `clearTxParticipationMode` (`:340-350`). Those references survive `destroy()` and point at a
  portal whose `cache` and `queryCache` are null.
- **Cache loading of the replacement portal is pushed off-thread** when the initializer is inside a
  transaction (`MithraConfigurationManager.java:1233-1247`), which prevents the load from enrolling
  in that transaction but does not synchronize it with anything.

The test harness sidesteps the question rather than testing it: `tearDown` rolls back any
transaction still open before it resets portals (`MithraTestResource.java:569-594`).

### Other entry points

`initializePortal(className)` is also called by the temp-object context to push a temp
configuration into its Finder (`mithra/tempobject/TempContextContainer.java:200`) and by
`OverlapDetector` to obtain a portal by name (`mithra/overlap/OverlapDetector.java:52`). Neither adds
a definition; both resolve one the configuration already named. `isClassConfigured(className)`
answers whether a name is in either bookkeeping structure (`MithraConfigurationManager.java:805-815`).

## DDL and schema evolution in the generator

### Where DDL lives and what it emits

The core generator (`reladomogen`) emits no DDL. DDL generation is a separate Ant task in the
`reladomogenutil` module: `MithraDbDefinitionGenerator extends AbstractMithraGenerator`
(`reladomogenutil/src/main/java/com/gs/fw/common/mithra/generator/dbgenerator/MithraDbDefinitionGenerator.java:27`;
the base is an `org.apache.tools.ant.Task`, `generator/AbstractMithraGenerator.java:33`) wrapping
`CoreMithraDbDefinitionGenerator`. Its `execute()` parses and validates the object XMLs, then for
each object in dependency order skips anything not in an optional build list (`:195-198`), skips
any object without a `DefaultTable` (`:201-204`), and calls `generateDbDefinition(wrapper, true)`
(`CoreMithraDbDefinitionGenerator.java:185-221`). That method always regenerates: the local
`outFileExists` is hard-coded `false` (`:149`), so the generation-log comparison that would skip an
unchanged table is dead code (`:162-168`), and the three writers run unconditionally (`:173-175`).

Per table, three files are written (`AbstractGeneratorDatabaseType.java:55-59`, `:63-73`):

| File | Content | Postgres rendering |
|---|---|---|
| `<TABLE>.ddl` | drop-if-exists (dialect permitting) + `create table` with the full column list | `PostgresGeneratorDatabaseType.java:49-67` |
| `<TABLE>.idx` | primary-key constraint, then `drop index if exists` + `create [unique] index` per declared index | `:70-98`, with a 63-character name-shortening rule at `:100-121` |
| `<TABLE>.fk` | `alter table ... add constraint ... foreign key` per eligible relationship | `AbstractGeneratorDatabaseType.java:118-122` onward |

Foreign keys are emitted only for directly joined, unparameterized, unfiltered one-to-many or
many-to-one relationships, never toward a dated object or through an as-of attribute
(`AbstractGeneratorDatabaseType.java:134-146`, `:196-205`), and never for pure objects (`:122`).

### Diff, alter, migrate: none

The `.ddl` file is a full-replace script. The only statements the generator can produce are
`drop table`, `create table`, `drop index`, `create index`, and `alter table ... add constraint`
for primary and foreign keys; there is no `alter table ... add/alter/drop column`, no comparison
against an existing schema, and no import of anything that reads a live database in the `dbgenerator`
package (`AbstractGeneratorDatabaseType.java:17-40` imports only generator model and `java.io`
types). The drop prefix itself is dialect-specific: Postgres and H2 emit `drop table if exists`
(`PostgresGeneratorDatabaseType.java:54`, `H2GeneratorDatabaseType.java:54`), Sybase emits a
`sysobjects` existence check followed by `drop table` and `GO`
(`SybaseGeneratorDatabaseType.java:53-63`), and Oracle emits a bare `create table` with no drop at
all (`OracleGeneratorDatabaseType.java:49-62`). The bundled DocBook page describes the output as
"scripts ... stored in .ddl, .idx and .fk files" (`reladomo/src/doc/docbook/mithraddl/ReladomoDdlGenerator.xml:34`)
and documents no other mode.

### Nullability and defaults per database type

The column line is built once, in the abstract base, from four inputs
(`AbstractGeneratorDatabaseType.java:75-103`):

1. **SQL type** from `JavaType.getSqlDataType(CommonDatabaseType, boolean nullable)`
   (`generator/type/JavaType.java:92`). The `nullable` flag changes the type in exactly one case:
   `BooleanJavaType` asks for `getSqlDataTypeForNullableBoolean()` when nullable and
   `getSqlDataTypeForBoolean()` otherwise (`generator/type/BooleanJavaType.java:76-82`); every
   other type ignores the flag (e.g. `IntJavaType.java:67-69`, `StringJavaType.java:94-96`). The
   per-dialect vocabulary is the fifteen-method `CommonDatabaseType` interface
   (`generator/databasetype/CommonDatabaseType.java:19-55`); the Postgres implementation maps
   `int`→`int`, `long`→`bigint`, `String`→`varchar`, `BigDecimal`→`numeric`, `byte[]`→`bytea`,
   `char`→`varchar(1)`, both booleans→`boolean` (`generator/databasetype/PostgresDatabaseType.java:33-110`).
2. **Identity suffix** from the *runtime* `DatabaseType.getIdentityTableCreationStatement()`
   (`AbstractGeneratorDatabaseType.java:81-84`): `" identity"` by default
   (`mithra/databasetype/AbstractDatabaseType.java:551-554`), `" GENERATED BY DEFAULT AS IDENTITY"`
   on H2 (`mithra/databasetype/H2DatabaseType.java:453-456`); Postgres does not override, so it
   inherits the Sybase-style `identity` keyword.
3. **Length or precision**: `varchar(n)` from `maxLength`, defaulting to 255 when unset (`:85-93`,
   constant at `:43`); `(precision,scale)` appended to `numeric`/`number`/`decimal` (`:94-99`).
4. **Null clause**: `" not null"` when the attribute is non-nullable, nothing otherwise:

```java
// reladomogenutil/.../dbgenerator/AbstractGeneratorDatabaseType.java:112-116
protected void generateNullStatement(PrintWriter writer, Attribute[] attributes, String attributeSqlType, int i)
{
    writer.println("    " + attributes[i].getColumnNameWithEscapedQuote() + " " + attributeSqlType +
            (attributes[i].isNullable() ? "" : " not null") + ((i < attributes.length - 1) ? "," : ""));
}
```

The only dialect override of that clause is H2's, which differs solely in using the raw rather
than the quote-escaped column name (`H2GeneratorDatabaseType.java:152-156`). No dialect emits an
explicit `null` keyword for nullable columns; each relies on the database's own default.

**Column defaults are never rendered.** No `DEFAULT` clause appears in any `dbgenerator` class —
the only "default" tokens in the package are the varchar-length constant and `getDefaultTable()` —
and `defaultIfNull`, the model's read-side substitute value, is not referenced anywhere in
`reladomogenutil`. The DDL therefore encodes nullability alone; the model's `defaultIfNull` remains
a Java-side getter behavior (see [26](26-stored-nullability-violations.md)).

### Model version: a per-class CRC that guards caches and remote peers, never the database

The generator does compute a version, but of the *class shape*, not of the schema:

```java
// generator/MithraObjectTypeWrapper.java:3513-3538
protected int computeSerialId()
{
    CRC32 crc = new CRC32();
    if (this.hasSourceAttribute())
    {
        crc.update(0x78);
    }
    if (this.hasAsOfAttributes())
    {
        crc.update(0x12);
        AsOfAttribute[] asOfAttributes = this.getAsOfAttributes();
        Arrays.sort(asOfAttributes);
        for (int i = 0; i < asOfAttributes.length; i++)
        {
            crc.update(this.convertStringToByteArray(asOfAttributes[i].getName()));
        }
    }
    Attribute[] normalAttributes = this.getAttributes();
    Arrays.sort(normalAttributes);
    for (int i = 0; i < normalAttributes.length; i++)
    {
        crc.update(this.convertStringToByteArray(normalAttributes[i].getName()));
        crc.update(normalAttributes[i].isNullable() ? 0x43 : 0x98);
        crc.update(normalAttributes[i].isPrimaryKey() ? 0x93 : 0x15);
        crc.update(this.convertStringToByteArray(normalAttributes[i].getTypeAsString()));
    }
    return (int) crc.getValue();
}
```

It hashes attribute names, nullability, primary-key membership, and Java type — not column names,
table names, lengths, or indices — and is baked into the Finder as `getSerialVersionId()`
(`Finder.jsp:781-783`). Its three consumers all compare one JVM's model to another artifact of the
same model:

- **Cache archives.** The archive writer stores it (`mithra/util/MithraArchiveWriter.java:55`;
  `mithra/util/MithraRuntimeCacheController.java:223`), and the reader throws
  `MithraBusinessException("Wrong serial version for class ...")` on mismatch (`:302-307`).
- **Remote client/server.** The client compares the server's advertised serial id to its own
  Finder's and records an initialization error on mismatch
  (`MithraConfigurationManager.java:1686-1690`; server value captured at `:421`, `:513`).

Nothing compares it to the physical schema. The separate `MithraVersion` template
(`reladomogen/src/main/templates/MithraVersion.tmpl`) is the library's own version constant,
consumed by `mithra/util/MithraProcessInfo.java:31`, not a model version.

### Runtime schema check

None at startup. `readConfiguration` boots portals without database introspection; the
`verifyTable` method exists but has no runtime call site; and the offline `DatabaseTableValidator`
and `NullableColumnValidator` Ant tasks are the only drift detectors. This is documented with
citations in [26 — Schema drift](26-stored-nullability-violations.md#schema-drift-no-runtime-verification)
and is not repeated here.

## Stored data that violates loaded metadata

### There is no discriminator

The word "discriminator" does not occur in `reladomo/src/main`, `reladomogen/src/main`, or
`reladomogenutil/src/main`. Inheritance is declared by `superClassType` on `<MithraObject>`, with
three strategies (`reladomogen/src/main/xsd/mithraobject.xsd:92-104`, enumeration at `:835-844`):

| `superClassType` | Physical shape | How a row's class is decided |
|---|---|---|
| `table-per-subclass` | each concrete subclass has its own table; the superclass may not declare a `DefaultTable` (`generator/MithraObjectTypeWrapper.java:1334-1337`) | never — each table's Finder yields only its own class; the superclass Finder template is a 15-line license stub (`reladomogen/src/main/templates/transactional/superclass/Finder.jsp`) |
| `table-per-class` | root table plus one table per subclass, keyed by the same primary key | presence of a matching row in a subclass table, read through `LEFT JOIN` |
| `table-for-all-subclasses` | one table | a hand-written `construct<Class>` hook the generator declares abstract; the XSD says "differentiated typically by some attribute. It is up to the implementation to override the database object's createObject method" (`mithraobject.xsd:96-98`) |

### `table-per-class`: subclass by joined-row presence; no match means the root class

The portal carries the hierarchy as Finder arrays and a depth (`mithra/portal/MithraAbstractObjectPortal.java:128-133`),
supplied by the generated `initializePortal` (`Finder.jsp:1337-1341`). A query on a class with
joined subclasses emits `FROM root JOIN ...supers... JOIN self` and then `LEFT JOIN` for each subclass
table (`mithra/finder/SqlQuery.java:417-455`, `LEFT JOIN` at `:445-452`; the database-object path
repeats it at `mithra/database/MithraAbstractDatabaseObject.java:2182-2198`). Hydration then probes
the subclass tables' primary-key columns in reverse declaration order and instantiates the first
subclass whose key is non-null:

```jsp
<%-- reladomogen/src/main/templates/CommonDatabaseObjectAbstract.jspi:372-399 --%>
<% if (subClasses != null) { %>
int _spos = 1;
<%= wrapper.getClassName() %>Data _data = null;
<% for(int i=subClasses.length - 1; i >=0; i--) {
        Attribute currentAttribute = subClasses[i].getPrimaryKeyAttributes()[0]; %>
if (_data == null)
{
    ...
    <%=currentAttribute.getResultSetGetter("_spos")%>;
    if (!_rs.wasNull())
    {
        _data = new <%= subClasses[i].getDataClassName()%>();
    }
    ...
    _spos++;
}
<% } %>
if (_data == null)
{
    _data = new <%= wrapper.getOnHeapDataClassName() %>();
}
```

Non-key subclass columns are inflated only into the chosen `Data` class; the other subclasses'
column positions are skipped (`CommonDatabaseObjectAbstract.jspi:441-456`). Object construction
mirrors the data class: the generated `createObject` calls `construct<Class>(newData)`, whose
generated body for a table-per-class root returns `new <Sub>()` when `data instanceof <Sub>Data`
and otherwise `new <Root>Impl()` (`reladomogen/src/main/templates/CommonNonDatedDatabaseObjectAbstract.jspi:27-42`,
`:49-57`). Consequently:

- **A root row with no matching subclass row is the root class.** Every table-per-class root has
  a `DefaultTable` (the "not specified" validation at `MithraObjectTypeWrapper.java:1338-1341`
  applies to it), so the root is concrete and the row hydrates silently as a root instance. There
  is no error, log, or "unknown subclass" state; the runtime cannot distinguish "this row was never
  a subclass" from "this row belongs to a subclass the loaded model does not know about."
- **A subclass row whose root row is missing is invisible** to every Finder: the subclass's own
  query starts from the root table and inner-joins down (`SqlQuery.java:422-435`).
- **A row present in two subclass tables** resolves to whichever subclass the reverse-order probe
  reaches first; nothing detects the conflict.
- Subclass caches are typed views over the root portal's cache
  (`reladomogen/src/main/templates/CommonObjectFactory.jspi:89-95`), so the root/sub decision made
  at hydration is also the identity-cache decision.

### `table-for-all-subclasses`: the runtime delegates the decision entirely

For this strategy the generated `construct<Class>` is abstract in the non-dated database object
(`CommonNonDatedDatabaseObjectAbstract.jspi:46-47`) and in the dated object factory, where it also
receives the as-of timestamps (`reladomogen/src/main/templates/CommonDatedObjectFactoryAbstract.jspi:49-55`).
The hand-written concrete database object must implement it; the generated `createObject` then
applies the same `instanceof <Sub>Data` copy loop as above (`CommonNonDatedDatabaseObjectAbstract.jspi:27-42`).
There is no generated column read, no configured discriminator attribute, and therefore no
generated behavior for an unrecognized value — whatever the hook returns is the object. The only
in-tree implementation returns the base class unconditionally:

```java
// reladomo/src/test/java/com/gs/fw/common/mithra/test/domain/TestDatedTableForAllSubclassesWithGenerateInterfaceDatabaseObject.java:25-31
public class TestDatedTableForAllSubclassesWithGenerateInterfaceDatabaseObject extends TestDatedTableForAllSubclassesWithGenerateInterfaceDatabaseObjectAbstract
{
    @Override
    protected TestDatedTableForAllSubclassesWithGenerateInterfaceImpl constructTestDatedTableForAllSubclassesWithGenerateInterfaceImpl(MithraDataObject data, Timestamp businessDate, Timestamp processingDate)
    {
        return new TestDatedTableForAllSubclassesWithGenerateInterfaceImpl(businessDate, processingDate);
    }
}
```

Its descriptor declares no subclasses and no type column
(`reladomo/src/test/reladomo-xml/TestDatedTableForAllSubclassesWithGenerateInterface.xml:20-31`).

### Stored null in a non-nullable column

Covered in full by [26](26-stored-nullability-violations.md): the check is a per-row
`ResultSet.wasNull()` at hydration, dispatched on Java type, raising a bare `MithraBusinessException`
for `char`, primitives, `BigDecimal`, `Date`, `Time`, and `byte[]` while admitting a Java `null`
for `String` and `Timestamp`; the failure aborts the whole result set after earlier batches have
already been cached. The same `InflateAttributes.jspi` include is what the subclass-column loop
above emits per non-key subclass attribute (`CommonDatabaseObjectAbstract.jspi:450`), so a
non-nullable subclass column behaves identically to a root column once the subclass has been chosen.
Nothing about the subclass choice itself consults nullability metadata: the probe at
`:380-392` reads the subclass key column and tests `wasNull()` directly, with no
`checkNullPrimitive`.

## Testing patterns

- **Runtime replacement.** No test calls `readConfiguration` twice against a live class to assert
  the ignore-or-replace behavior; the behavior is exercised only indirectly, through
  `MithraTestResource`, which sets `destroyExistingPortal` for delete-on-create resources
  (`MithraTestResource.java:1171-1175`) and resets portals in `tearDown` after forcing any open
  transaction to roll back (`:569-594`). No test opens a transaction, replaces a portal, and then
  continues the transaction.
- **DDL.** The `dbgenerator` package has no unit tests in the tree; the H2 test schema the suite
  runs against is maintained separately from generator output (see
  [12](12-test-infrastructure.md)).
- **Inheritance.** `ReadOnlyAnimal.xml` (`table-per-class`), `InventoryItem.xml` and
  `TestAbstractMessage.xml` (`table-per-subclass`), and the single `table-for-all-subclasses`
  fixture above are the fixture families (`reladomo/src/test/reladomo-xml/`). No test seeds a
  table-per-class root row with no subclass row and asserts the resulting class, and none seeds a
  row in two subclass tables.

## Code references

- Portal slot and lifecycle: `reladomogen/src/main/templates/readonly/Finder.jsp:91, 307-314, 1329-1368, 1462-1468`;
  `mithra/portal/UninitializedPortal.java:59-72, 429-432`; `mithra/portal/MithraAbstractObjectPortal.java:249-252, 392-400`
  ([permalink](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/portal/MithraAbstractObjectPortal.java#L392))
- Configuration read and replace policy: `mithra/util/MithraConfigurationManager.java:97-98, 239-258, 278-334, 805-879, 881-957, 1033-1067, 1193-1250, 1469-1506`
  ([permalink to `addUnitialized`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/util/MithraConfigurationManager.java#L1033));
  `mithra/mithraruntime/MithraRuntimeType.java:17-33`; `mithra/MithraManager.java:78, 127-135, 208-211, 670-678, 707-748`
- In-flight references: `reladomogen/src/main/templates/transactional/Abstract.jsp:1300-1324`;
  `mithra/transaction/TransactionOperation.java:41-47`; `mithra/transaction/MithraLocalTransaction.java:64, 340-350`;
  `reladomo/src/test-util/java/com/gs/fw/common/mithra/test/MithraTestResource.java:305-320, 569-594, 1171-1175`
- DDL generator: `reladomogenutil/src/main/java/com/gs/fw/common/mithra/generator/dbgenerator/CoreMithraDbDefinitionGenerator.java:141-221`;
  `.../AbstractGeneratorDatabaseType.java:43, 55-116, 118-205`
  ([permalink](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogenutil/src/main/java/com/gs/fw/common/mithra/generator/dbgenerator/AbstractGeneratorDatabaseType.java#L75));
  `.../PostgresGeneratorDatabaseType.java:49-121`; `.../H2GeneratorDatabaseType.java:49-60, 152-156`;
  `.../SybaseGeneratorDatabaseType.java:53-63`; `.../OracleGeneratorDatabaseType.java:49-62`
- Type mapping: `generator/type/JavaType.java:92`; `generator/type/BooleanJavaType.java:76-82`;
  `generator/databasetype/CommonDatabaseType.java:19-55`; `generator/databasetype/PostgresDatabaseType.java:33-110`;
  `mithra/databasetype/AbstractDatabaseType.java:551-554`; `mithra/databasetype/H2DatabaseType.java:453-456`
- Serial version id: `generator/MithraObjectTypeWrapper.java:3505-3538`
  ([permalink](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/java/com/gs/fw/common/mithra/generator/MithraObjectTypeWrapper.java#L3513));
  `mithra/util/MithraRuntimeCacheController.java:223, 302-307`; `mithra/util/MithraArchiveWriter.java:55`;
  `mithra/util/MithraConfigurationManager.java:421, 513, 1686-1690`
- Inheritance: `reladomogen/src/main/xsd/mithraobject.xsd:92-104, 835-844`;
  `generator/MithraObjectTypeWrapper.java:667-670, 1334-1341, 2702-2716`;
  `reladomogen/src/main/templates/CommonNonDatedDatabaseObjectAbstract.jspi:25-57`;
  `reladomogen/src/main/templates/CommonDatedObjectFactoryAbstract.jspi:28-55`;
  `reladomogen/src/main/templates/CommonDatabaseObjectAbstract.jspi:366-397, 441-456`
  ([permalink](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/templates/CommonDatabaseObjectAbstract.jspi#L372));
  `reladomogen/src/main/templates/CommonObjectFactory.jspi:89-95`;
  `mithra/finder/SqlQuery.java:417-455`; `mithra/database/MithraAbstractDatabaseObject.java:2182-2198`;
  `mithra/portal/MithraAbstractObjectPortal.java:128-133, 1472-1484`

## Open questions

- Whether the early return in `addUnitialized` for an already-initialized class is meant as a
  guard against accidental double configuration or as deliberate support for merging several
  runtime XMLs is unattested; the `// nothing to do` comment is the only annotation.
- The hard-coded `outFileExists = false` in `generateDbDefinition` leaves a generation-log skip
  path unreachable; whether that is a disabled feature or a leftover is not recorded.
- No source of the `remoteSerialId` protocol beyond the two capture sites was read; the wire
  format for the client/server version exchange is out of scope here.
- The per-dialect `dbgenerator` classes were read for Postgres, H2, Sybase, and Oracle; Maria and
  Udb82 were only listed.
