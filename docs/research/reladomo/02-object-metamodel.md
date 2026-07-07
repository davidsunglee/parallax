# A domain object is defined once in XML (`mithraobject.xsd`); runtime behavior is bound separately in a runtime-config XML

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The object-definition schema is `reladomogen/src/main/xsd/mithraobject.xsd`. It defines five root
elements (lines 24-29): `<MithraObject>` (DB-backed), `<MithraPureObject>` (in-memory only),
`<MithraTempObject>` (session temp table), `<MithraInterface>`, and `<MithraEmbeddedValueObject>`.
The `objectType` attribute has exactly two legal values — `read-only` (default) and `transactional`
(lines 724-740). "Dated" is **not** a separate `objectType`; an object becomes dated when it declares
one or two `<AsOfAttribute>` children, which the generator detects via `hasAsOfAttributes()` and
prepends `"dated"` to the template category (`generator/MithraObjectTypeWrapper.java:645-650`).

What an object definition captures:

- **`<Attribute>`** (xsd 300-333): `name`, `javaType` (primitive/`String`/`Timestamp`/`Date`/`Time`/`BigDecimal`/`byte[]`), `columnName`, `primaryKey`, `nullable`, `maxLength`, `readonly`, `useForOptimisticLocking`, `identity`, `timezoneConversion`, `timestampPrecision`, and `primaryKeyGeneratorStrategy` (`Max` or `SimulatedSequence`).
- **`<SimulatedSequence>`** (xsd 862-906): `sequenceName`, `sequenceObjectFactoryName`, `batchSize`, `initialValue`, `incrementSize`, `hasSourceAttribute`.
- **`<AsOfAttribute>`** (xsd 278-298): `name`, `fromColumnName`, `toColumnName`, `infinityDate` (a Java code snippet in `[...]`), `infinityIsNull`, `toIsInclusive`, `isProcessingDate`, `defaultIfNotSpecified`, `timezoneConversion`.
- **`<Relationship>`** (xsd 541-627): the element body is a join-predicate expression (e.g. `this.accountNum = Account.accountNum`); attributes include `relatedObject`, `cardinality`, `reverseRelationshipName`, `relatedIsDependent`, `orderBy`, `parameters`, `foreignKey`.
- **`<Index>`** (xsd 673-689): comma-separated attribute names; `unique="true"` enables the cache fast path.
- **`<SourceAttribute>`** and inheritance (`superClassType` ∈ `table-per-subclass`/`table-for-all-subclasses`/`table-per-class`).

A real bitemporal example (`reladomo/src/test/reladomo-xml/TinyBalance.xml:28-34` and
`samples/reladomo-graphql-test-service/.../Balance.xml`):

```xml
<MithraObject objectType="transactional">
    <PackageName>...</PackageName><ClassName>Balance</ClassName><DefaultTable>BALANCE</DefaultTable>
    <AsOfAttribute name="businessDate"   fromColumnName="FROM_Z" toColumnName="THRU_Z" toIsInclusive="false"
                   infinityDate="[...DefaultInfinityTimestamp.getDefaultInfinity()]"/>
    <AsOfAttribute name="processingDate" fromColumnName="IN_Z"   toColumnName="OUT_Z"  isProcessingDate="true"
                   infinityDate="[...]" defaultIfNotSpecified="[...]"/>
    <Attribute name="id" javaType="int" columnName="BAL_ID" primaryKey="true"
               primaryKeyGeneratorStrategy="SimulatedSequence">...</Attribute>
    <Attribute name="accountNum" javaType="String" columnName="ACCT_NUM"/>
    <Attribute name="value"      javaType="double" columnName="VAL"/>
    <Relationship name="account" relatedObject="Account" cardinality="many-to-one">
        this.accountNum = Account.accountNum
    </Relationship>
</MithraObject>
```

**Runtime config is a separate XML** (`reladomo/src/main/xsd/mithraruntime.xsd`). `<MithraRuntime>`
contains `<ConnectionManager className="...">` blocks (each with `<Property>` and one or more
`<MithraObjectConfiguration>`), plus `<PureObjects>`, `<RemoteServer>`, and
`<MasterCacheReplicationServer>`. `<MithraObjectConfiguration>` (xsd 97-123) binds a fully-qualified
class name to a connection manager and declares `cacheType` (`partial`/`full`/`none`), `txParticipation`
(`full`/`readOnly`), `offHeapFullCache`, `cacheTimeToLive`, `loadCacheOnStartup`, etc. This separation
is deliberate: the same generated class is configured differently in prod vs. test.

```xml
<MithraRuntime>
  <ConnectionManager className="sample.util.H2ConnectionManager">
    <MithraObjectConfiguration cacheType="none"    className="sample.domain.ObjectSequence"/>
    <MithraObjectConfiguration cacheType="partial" className="sample.domain.Person"/>
  </ConnectionManager>
  <PureObjects notificationIdentifier="not">
    <MithraObjectConfiguration cacheType="full" className="sample.domain.PureBalance" offHeapFullCache="true"/>
  </PureObjects>
</MithraRuntime>
```

## Testing patterns

The metamodel is validated end-to-end by `reladomogenutil`'s `GeneratorTestSuite`
(`reladomogenutil/src/test/.../generator/GeneratorTestSuite.java`): `MaxLenValidatorTest`,
`DatabaseTableValidatorTest` (boots H2, asserts the validator detects missing tables/columns/
`maxLength`), `DatabaseIndexValidatorTest`. The integration corpus uses ~407 pre-generated objects
from `reladomo/src/test/reladomo-xml/` whose generated sources live in `.../test/domain/`.

## Code references

- `reladomogen/src/main/xsd/mithraobject.xsd` — object schema (roots 24-29; objectType 724-740; AsOfAttribute 278-298; Attribute 300-333; Relationship 541-627; SimulatedSequence 862-906)
- `reladomo/src/main/xsd/mithraruntime.xsd` — runtime config schema (MithraObjectConfiguration 97-123)
- Examples: `samples/reladomo-sample-simple/.../Person.xml`, `samples/reladomo-graphql-test-service/.../Balance.xml`, `reladomo/src/test/reladomo-xml/TinyBalance.xml`, `.../DatedAccount.xml`
