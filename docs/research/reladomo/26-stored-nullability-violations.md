# Stored nullability violations: hydration raises per row for most types but silently admits `null` for `String`/`Timestamp`; INSERT enforces the mirror-image subset; embedded values carry no absent-versus-null distinction

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The question this finding answers: when a row already in the database holds SQL NULL in a column the
XML declares non-nullable, what does Reladomo do? The short answer is that it does not trust the
schema — it emits an explicit per-row `wasNull()` check at hydration — but the coverage is dispatched
on Java type rather than applied uniformly, and the two most common reference types are omitted.

## Declaration

`nullable` is an XSD boolean on `<Attribute>` defaulting to `true`, documented as inverting for
primary keys (`reladomogen/src/main/xsd/mithraobject.xsd:441-446`, repeated for the Pure variant at
`:1251-1256`). The inversion is implemented in Java, not the schema:

```java
// generator/AbstractAttribute.java:352-355
return this.getAttributeType().isNullable() && (this.getAttributeType().isNullableSet() || !this.getAttributeType().isPrimaryKey());
```

A primary key that does not *explicitly* declare `nullable="true"` therefore becomes non-nullable.
`AsOfAttribute` is unconditionally non-nullable (`generator/AsOfAttribute.java:110-113`). A
superclass `nullable` propagates to a subclass only where the subclass never set it
(`generator/AbstractAttribute.java:572-578`).

The generator's decisive choice is that **a nullable primitive stays a primitive**. A
`javaType="int" nullable="true"` attribute generates a raw `int` field, never an `Integer`
(`reladomogen/src/main/templates/readonly/common/AttributesAndGetters.jspi:30-32`;
`generator/AbstractAttribute.java:805-808`). Absence is tracked out of band in a shared bitmask field
`isNullBitsN`, sized `byte`/`short`/`int`/`long` to the count of nullable primitives on the class
(`AttributesAndGetters.jspi:24-28`; `generator/MithraBaseObjectTypeWrapper.java:277-323, 415-436`,
bit expressions at `:226-260`). Only nullable primitives receive a bit index
(`generator/MithraObjectTypeWrapper.java:981-990`), so a non-nullable attribute has no
representable null state at all.

Consequences visible in generated code:

- `isXxxNull()` is generated for **every** attribute, but its body differs by case: literal
  `return false;` for a non-nullable primitive, `getter() == null` for any non-primitive, and a real
  bit check for a nullable primitive (`AttributesAndGetters.jspi:38-56`).
- `setXxxNull()` on a non-nullable primitive is generated with the body
  `throw new RuntimeException("should never be called")`
  (`reladomogen/src/main/templates/readonly/DataOnHeap.jspi:113-122`).
- **No null sentinel encoding exists for ordinary primitives.** The two sentinels in the codebase
  serve unrelated mechanisms: `TimestampPool.OFF_HEAP_NULL` (`mithra/util/TimestampPool.java:43`)
  for off-heap encoding of a nullable `Timestamp` object, and `NullDataTimestamp`
  (`mithra/util/NullDataTimestamp.java:23-56`) for as-of infinity.
- Reading a nullable primitive whose bit is set throws `MithraNullPrimitiveException` (a
  `MithraBusinessException` subclass) unless the XML declared `defaultIfNull`, in which case the
  field already holds the configured value and the getter returns it
  (`reladomogen/src/main/templates/readonly/Abstract.jsp:184-196`;
  `reladomogen/src/main/templates/transactional/Abstract.jsp:307-314`;
  `mithra/MithraNullPrimitiveException.java:34-37`).

## Read path: the check is at hydration, and is type-dispatched

There is exactly one hydration template, included at all five inflate sites
(`reladomogen/src/main/templates/CommonDatabaseObjectAbstract.jspi:411, 431, 437, 450, 612` →
`reladomogen/src/main/templates/InflateAttributes.jspi`). Its branch structure decides the behavior:

| Java type | Non-nullable column holds SQL NULL | `InflateAttributes.jspi` |
|---|---|---|
| `char` | throws `MithraBusinessException` inline | `:22-56`, throw at `:54` |
| `String` | **no check — hydrates to Java `null`** | `:58-63` |
| `Timestamp` | **no check — hydrates to Java `null`**, except an as-of "to" column with `infinityIsNull=false`, which throws | `:65-80`, conditional throw at `:69-73` |
| numeric and boolean primitives, `BigDecimal`, `Date`, `Time`, `byte[]` | throws `MithraBusinessException` via `checkNullPrimitive` | `:81-105`, call at `:103` |

The raising helper is a plain `ResultSet.wasNull()` test:

```java
// mithra/database/MithraAbstractDatabaseObject.java:2588-2594
protected void checkNullPrimitive(ResultSet rs, MithraDataObject data, String name) throws SQLException
{
    if (rs.wasNull())
        throw new MithraBusinessException("attribute '" + name + "' is null in database but is not marked as nullable in mithra xml for primary key / "
                + data.zGetPrintablePrimaryKey());
}
```

Type classification is confirmed at
`generator/type/{String,Timestamp,BigDecimal,Date,Time,ByteArray}JavaType.java` (`isPrimitive()`
returns `false`) and `generator/type/PrimitiveWrapperJavaType.java:26-29` (returns `true`). The
`else` branch at `InflateAttributes.jspi:102-104` gates on `isNullable()` alone, so
`checkNullPrimitive` also covers the non-primitive types reaching that branch — `BigDecimal`,
`Date`, `Time`, `byte[]` — since `wasNull()` applies to object getters too.

Three properties of this design matter beyond the table:

- **No dedicated exception type.** The violation surfaces as a bare `MithraBusinessException`
  carrying a message string. `MithraNullPrimitiveException` is a *different* condition — an
  attribute legitimately nullable in the model, read at access time with no `defaultIfNull` — and is
  unreachable for a non-nullable primitive, because hydration has already thrown.
- **Enforcement is spent entirely at hydration.** A non-nullable attribute has no null bit
  (`generator/MithraObjectTypeWrapper.java:981-990`), so no downstream accessor could detect the
  violation even in principle.
- **Failure granularity is one row.** The throw occurs while inflating a single result-set row;
  other rows in the same result are unaffected.

A second, unrelated read path for tuple and temp-object columns returns `null` on `wasNull()` with
no nullability check whatsoever (`mithra/attribute/SingleColumnIntegerAttribute.java:351-354`, called
from `mithra/tempobject/TupleTempContext.java:433`).

## Write path: the mirror-image subset

Both directions enforce, incompletely, and each has the blind spot the other covers.

**INSERT checks non-primitives and skips primitives.** The generated `setInsertAttributes` emits,
for a non-nullable attribute:

```jsp
<%-- reladomogen/src/main/templates/CommonTransactionalDatabaseObjectAbstract.jspi:47-52 --%>
<% } else { %>
   <% if (!attributes[i].isPrimitive()) { %>
      if(data.<%=attributes[i].getNullGetter()%>) { throwNullAttribute("<%=attributes[i].getName()%>"); }
   <% } %>
```

```java
// mithra/database/MithraAbstractDatabaseObject.java:5251-5257
protected void throwNullAttribute(String name)
{
    if(this.checkNullOnInsert) { throw new MithraBusinessException("the field '" + name + "' must not be null in class "+getDomainClassName()); }
}
```

So a non-nullable `String` left null **is** caught on insert — precisely the case hydration does not
catch — while a non-nullable primitive is **not** checked on insert, since a Java primitive cannot be
null and an unset `int` persists silently as `0`. That is the case hydration *does* catch. The
insert check is globally disableable by system property:
`this.checkNullOnInsert = !"false".equals(System.getProperty("mithra.checkNullOnInsert"));`
(`mithra/database/MithraAbstractDatabaseObject.java:175, 209`), with call sites at `:3580-3601`
(single) and `:4754, 4757, 4811, 4813` (batch).

**UPDATE does not enforce.** The `*UpdateWrapper` classes bind `ps.setNull(...)` unconditionally
without consulting nullability (`mithra/attribute/update/StringUpdateWrapper.java:44-56`), deferring
entirely to the database's own `NOT NULL` constraint.

## Embedded values: no absent-versus-null distinction

`<EmbeddedValue>` is Reladomo's composite-attribute mechanism, and it carries no notion of a
composite being absent as distinct from its members being null.

- Nullability is declarable only per **member column** (`EmbeddedValueMappingType.nullable`), never
  on the embedded object as a whole: neither `EmbeddedValueType`/`NestedEmbeddedValueType`
  (`reladomogen/src/main/xsd/mithraobject.xsd:335-373`) nor `MithraEmbeddedValueObjectType`
  (`:1331-1394`) declares a `nullable` attribute.
- `EmbeddedValueMapping extends Attribute`, and its `isNullable()` is the identical per-column
  formula (`generator/EmbeddedValueMapping.java:163-166`). `EmbeddedValue.resolveMappings()`
  registers each mapping as an ordinary attribute of the **owning** object
  (`generator/EmbeddedValue.java:361-379`), so every member column flows through the same
  `InflateAttributes.jspi` dispatch independently of its siblings, under the same type-dispatched
  rules as any other column.
- Nothing collapses "all N member columns are SQL NULL" into a null reference. The generated
  owner-side getter lazily constructs and caches a wrapper and **can never return null**
  (`reladomogen/src/main/templates/readonly/Abstract.jsp:82-92`), and `setValueNull` on an embedded
  value throws `UnsupportedOperationException("setValueNull should not be called on embedded value
  objects.")` (`reladomogen/src/main/templates/embeddedvalue/Abstract.jsp:246-250`).
- `EmbeddedValueExtractor` exposes only `valueOf`/`setValue` — no `isAttributeNull`/`setValueNull`,
  unlike the column extractors (`mithra/extractor/EmbeddedValueExtractor.java:20-25`).

Because an embedded value is stored as flat columns, a column always exists and SQL NULL is its only
not-present state. There is no missing-member state for a column to be in, so the question of
distinguishing absence from null does not arise in this mechanism.

The one place SQL NULL carries a domain meaning rather than absence is `infinityIsNull="true"` on
`<AsOfAttribute>` (`reladomogen/src/main/xsd/mithraobject.xsd:1063-1067`).
`AsOfAttributeInfiniteNull.isInfinityNull()` returns `true`
(`mithra/attribute/AsOfAttributeInfiniteNull.java:48-51`), SQL NULL in the THRU/OUT column is
translated to and from the fixed `NullDataTimestamp` sentinel at the object boundary
(`mithra/attribute/TimestampAttributeAsOfAttributeToInfiniteNull.java:652-688`), and the generated
predicate ORs it in explicitly: `(TO_COL = ? or TO_COL is null)`
(`AsOfAttributeInfiniteNull.java:81-114`). This is a sentinel encoding for one virtual attribute
derived from two real columns, not an absent-versus-null distinction.

## Schema drift: no runtime verification

Shape drift is not checked at runtime; only value-level drift is, through the hydration path above.

- `MithraConfigurationManager.readConfiguration(...)`
  (`mithra/util/MithraConfigurationManager.java:278`) boots portals without database introspection.
- A verification method exists — `MithraAbstractDatabaseObject.verifyTable(Object source)`
  (`mithra/database/MithraAbstractDatabaseObject.java:2634-2660`), comparing column count, type,
  size, and nullability via `DatabaseType.getTableColumnInfo(...)` and `TableColumnInfo.hasColumn(attr)`
  (`mithra/util/TableColumnInfo.java:310-366`) — but **it has no runtime call site**. The only
  reference is an unused test-domain override
  (`reladomo/src/test/java/com/gs/fw/common/mithra/test/domain/bcp/BcpSimpleWithIdentityDatabaseObject.java:30`).
  It is available-but-unwired API.
- Drift detection ships instead as offline Ant tasks in the separate `reladomogenutil` module:
  `DatabaseTableValidator` detects missing tables, missing columns, and type/size mismatches
  (`reladomogenutil/src/main/java/com/gs/fw/common/mithra/generator/objectxmlgenerator/DatabaseTableValidator.java:182-229`,
  extending `org.apache.tools.ant.Task` at `:36`), and `NullableColumnValidator` diffs database
  nullability against XML nullability and can autofix the XML
  (`.../NullableColumnValidator.java:161-171`, `Task` at `:32`, throwing at `execute()` `:100`).
  Both are build-time and opt-in, not part of the runtime jar.
- SELECT SQL lists columns explicitly (`generator/MithraObjectTypeWrapper.java:3297, 3309, 3330`),
  and driver exceptions are wrapped into `MithraDatabaseException` by
  `analyzeAndWrapSqlExceptionGenericSource` (`mithra/database/MithraAbstractDatabaseObject.java:2477-2513`,
  wrap at `:2487`).

## Testing patterns

No test in the Reladomo suite asserts the stored-nullability-violation behavior. The message
`"is null in database but is not marked as nullable"` appears only at its three definition sites
(`reladomogen/src/main/templates/InflateAttributes.jspi:54, 72` and
`mithra/database/MithraAbstractDatabaseObject.java:2592`) and at no assertion.

## Open questions

- Whether the `String`/`Timestamp` omission from the hydration check is deliberate or an oversight is
  **unattested in either direction** — there is no test, comment, or changelog entry covering it.
- The `*UpdateWrapper` family was sampled (`ObjectUpdateWrapper`, `StringUpdateWrapper` read in full,
  the directory grepped) rather than read exhaustively across all subclasses.
- The build step producing the JAXB-style `AttributeType` base, which is the source of
  `isNullableSet()` used by the primary-key inversion above, is not in the checked-in tree.
- That a missing column manifests as a driver `SQLException` follows from the explicit column list
  and the generic wrapper, but was not exercised against a live drifted schema.
