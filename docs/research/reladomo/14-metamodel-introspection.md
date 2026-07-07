# A runtime metamodel-introspection seam (`RelatedFinder` + `ReladomoClassMetaData`) lets non-core modules map the model without XML

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The serialization (`reladomoserial`) and GraphQL (`reladomographql`) modules build JSON serializers and
GraphQL schemas at runtime purely by introspecting the **generated** metamodel — no XML is read at the
point of use. Both depend on the same two-level seam, which is itself a core capability worth noting for
any extraction:

- **`RelatedFinder`** (`mithra/finder/RelatedFinder.java`) — the generated per-class singleton, the live
  runtime descriptor. Key introspection methods: `getPersistentAttributes()` → `Attribute[]`,
  `getPrimaryKeyAttributes()`, `getAsOfAttributes()` → `AsOfAttribute[]`, `getSourceAttribute()`,
  `getRelationshipFinders()` / `getDependentRelationshipFinders()`, `getAttributeByName(String)`,
  `getRelationshipFinderByName(String)`, `getFinderClassName()`, plus query entry points `all()` /
  `findMany(Operation)`. The **`Attribute` subclass hierarchy itself is the runtime type system** — both
  modules dispatch via `instanceof StringAttribute`/`IntegerAttribute`/`TimestampAttribute`/… rather than
  reading a stored type string, and read values generically via `Attribute.valueOf(object)`.
- **`ReladomoClassMetaData`** (`com/gs/reladomo/metadata/ReladomoClassMetaData.java`) — a cached facade
  over `RelatedFinder` adding Java-class resolution (`fromFinder` 86, `fromBusinessClass` 110,
  `fromFinderClassName` 96; `getBusinessImplClass`, `getRelationshipSetter`, `getNumberOfDatedDimensions`).
- **Class registry** — `MithraManager.getRuntimeCacheControllerSet()` enumerates every configured class;
  each `MithraRuntimeCacheController` exposes `getFinderInstance()`. There is **no separate "exposed
  classes" config** in either module — both walk this set.

**Serialization** has its shared engine in the *core* package `mithra/util/serializer/` (not in
`reladomoserial`): `SerializationNode.withDefaultAttributes(finder)` calls `getPersistentAttributes()`/
`getAsOfAttributes()` (`SerializationNode.java:87-111`); `ReladomoSerializationContext.serializeAttributes()`
calls `attribute.zWriteSerial(...)` per attribute and `serializeRelationships()` calls
`relatedFinder.valueOf(obj)` to navigate (`ReladomoSerializationContext.java:245-284`); the format-specific
`SerialWriter` just emits tokens. `reladomoserial` is thin glue: `JacksonReladomoSerializer.serialize()`
gets the finder via `obj.zGetPortal().getFinder()` and delegates into the core engine; Gson mirrors it.
Deserialization (`ReladomoDeserializer` + `DeserializationClassMetaData`, also core) uses
`getAttributeByName`/`getRelationshipFinderByName` to route incoming fields.

**GraphQL**: `SDLGenerator` walks the cache-controller set and, per class, calls
`getPersistentAttributes()`/`getAsOfAttributes()`/`getSourceAttribute()`/`getRelationshipFinders()` to emit
SDL (`reladomographql/.../SDLGenerator.java`); relationship cardinality comes from
`AbstractRelatedFinder.zGetMapper().isToMany()`. `SchemaProvider` parses that SDL and wires
`ReladomoQueryFetcher`/`ReladomoMutationFetcher`/`AttributeDataFetcher` per class. `FilterQueryBuilder`
translates a GraphQL filter map into an `Operation` tree by resolving keys via `getAttributeByName` /
`getRelationshipFinderByName` and calling the fluent operation methods on the typed attribute.

## Testing patterns

`reladomoserial` and `reladomographql` carry their own module test suites (e.g. round-trip
serialize/deserialize tests and schema-generation/fetch tests); these were not enumerated in depth as
they are non-core modules.

## Code references

- `mithra/finder/RelatedFinder.java`, `AbstractRelatedFinder.java` — the generated per-class descriptor (getPersistentAttributes/getAsOfAttributes/getRelationshipFinders/getAttributeByName)
- `com/gs/reladomo/metadata/ReladomoClassMetaData.java` — cached class-aware facade (fromFinder 86, fromBusinessClass 110)
- `mithra/util/serializer/` — core serialization engine: `SerializationConfig.java`, `SerializationNode.java` (87-111), `ReladomoSerializationContext.java` (245-284), `SerialWriter.java`, `ReladomoDeserializer.java`, `DeserializationClassMetaData.java`
- `reladomoserial/` — Jackson/Gson glue: `JacksonReladomoModule.java`, `JacksonReladomoSerializer.java`, `JacksonReladomoWrappedDeserializer.java`, `GsonWrappedSerializer.java`, `GsonReladomoSerialWriter.java`
- `reladomographql/` — `SDLGenerator.java`, `SchemaProvider.java`, `ReladomoQueryFetcher.java`, `ReladomoMutationFetcher.java`, `FilterQueryBuilder.java`, `AttributeDataFetcher.java`
