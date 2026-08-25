# Fixed-slot data objects: the layout is the generated class, null is an out-of-band bitmap over nullable primitives only, and population is a metadata-driven position walk that may stop short

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`; **`templates/`** =
> `reladomogen/src/main/templates/`.

The question this finding answers: how does Reladomo physically lay out one row's worth of state,
how does it record which of those positions hold nothing, and what happens when only part of a row
is read? Three notes already touch the edges — [03](03-code-generation.md) records that a
`[Name]Data.java` is emitted per object and calls it a "plain data carrier for cache copy-on-write",
[26](26-stored-nullability-violations.md) records the `isNullBitsN` mask as one consequence of
keeping a nullable primitive unboxed, and [10](10-object-lifecycle.md) records the persistence-state
machine that owns the carrier. None of them describes the layout itself. This one does, and closes
with what Parallax adopts, adapts, and rejects — so it is an **applied** note in the sense
[00-index.md](00-index.md) already uses for [25](25-cascade-operations.md), not a descriptive one.

## The layout is the generated class: fixed Java fields, no map, no per-instance descriptor

A row's state does not live on the object a caller holds. `MithraTransactionalObjectImpl` — the
hand-written base every generated `Abstract` class extends — carries two fields and nothing else of
the row: a state byte and a pointer to the carrier.

```java
// mithra/superclassimpl/MithraTransactionalObjectImpl.java:49-51
protected volatile byte persistenceState = PersistenceState.IN_MEMORY;
protected volatile MithraDataObject currentData;
```

The carrier is `[Name]Data`, generated from `templates/readonly/Data.jsp`, which includes
`templates/readonly/common/AttributesAndGetters.jspi` for the state itself. Every attribute becomes
one declared Java field of its own storage type, and every embedded value object one field of the
nested type:

```jsp
<%-- templates/readonly/common/AttributesAndGetters.jspi:30-36 --%>
<% for (AbstractAttribute attribute : attributes) { %>
    private <%= attribute.getStorageType() %> <%= attribute.getName() %>;
<% } %>
<% for (EmbeddedValue evo : embeddedValueObjects) { %>
    private <%= evo.getType() %> <%= evo.getNestedName() %>;
<% } %>
```

There is no map, no array of values, and no per-instance layout object. The layout is the class:
positions are Java field offsets the JVM assigns, and the metadata that decided them is consumed at
generation time and never consulted again at runtime.

**Relationships are a separate fixed-width array, and it is lazily allocated.** A relationship that
can be held at all gets a position in one `Object[]`, sized to the count of such relationships on
the class, and the array is created on the first write rather than with the carrier:

```jsp
<%-- templates/readonly/DataOnHeap.jspi:19-21, 442-465 --%>
private Object[] _relationships;
...
public Object <%= rel.getGetter() %>()
{
    if (_relationships != null) { return _relationships[<%= rel.getPositionInObjectArray() %>]; }
    return null;
}
public void <%= rel.getSetter() %>(Object related)
{
    if (_relationships == null) { _relationships = new Object[<%= wrapper.getSettableRelationshipCount() %>]; }
    _relationships[<%= rel.getPositionInObjectArray() %>] = related;
}
```

A relationship the generator classifies as a *direct reference* is excluded from that array and gets
a dedicated field instead (`generator/RelationshipAttribute.java:1260-1273`,
`templates/readonly/DataOnHeap.jspi:37-40`), so the two storage kinds are decided per relationship
at generation time. `clearRelationships()` drops the whole array by nulling the field
(`DataOnHeap.jspi:373-377`).

**Three index spaces run through the layout, and no two of them agree.** This matters more than any
single one of them, because a generator that conflated them would produce a class that reads the
wrong column into the wrong field:

| Index space | Order | Where it is assigned |
|---|---|---|
| Java field declaration | attribute name, ascending | `getSortedNormalAndSourceAttributes()` (`generator/MithraObjectTypeWrapper.java:3424-3429`) over `AbstractAttribute.compareTo` (`generator/AbstractAttribute.java:931-939`), which compares names alone |
| Null-bit index | XML declaration order, nullable primitives only | `addAttribute` calls `setOnHeapNullableIndex(nullablePrimitiveAttributes.size())` as it walks (`MithraObjectTypeWrapper.java:968-990`) |
| ResultSet / SQL column position | primary keys first, then declaration order, then one block per inheritance level | `getColumnListWithDefaultAlias` (`MithraObjectTypeWrapper.java:3330-3362`) and the `_pos` walk below |
| Relationship array position | relationship name, ascending, over the storable ones only | `MithraObjectTypeWrapper.java:320-340` |

The inheritance rule inside the column list is the one Parallax's own member layout also arrives at
independently: the family root's primary keys, then the root's own non-key columns, then each
superclass level in turn, then this class, then the child classes
(`MithraObjectTypeWrapper.java:3340-3360`). Root-first, one contiguous block per contributor.

**The off-heap layout is the same idea with explicit byte offsets, computed once per class.** It is
the one place Reladomo writes the layout down as numbers, and the shape it writes down is a bitmap
header followed by fixed field offsets:

```java
// generator/MithraObjectTypeWrapper.java:1555-1613, assignOffHeapAttributeOffsets
// attributes sorted primary-key-first, then by name
int currentNullBitsOffset = 0, currentNullBitsPosition = 0;
if (hasAsOfAttributes()) currentNullBitsOffset += 4;      // the data-version int leads
for (AbstractAttribute attr : normalAndInheritedAttributes)
    if (attr.isNullablePrimitive() && !attr.getType().isBoolean())
    { attr.setOffHeapNullBitsOffset(...); attr.setOffHeapNullBitsPosition(...); /* 32 bits per int */ }
int currentOffset = /* past the null bits */;
for (AbstractAttribute attr : normalAndInheritedAttributes)
{ attr.setOffHeapFieldOffset(currentOffset); currentOffset += attr.getType().getOffHeapSize(); }
this.offHeapSize = currentOffset;                          // rounded up to even
```

Reading one off-heap field is then `zIsNull(_storage, <null-bits offset>, <bit position>)` and a
typed read at `<field offset>` — two constants the generator baked in, and no lookup
(`templates/readonly/DataOffHeap.jspi:58-80`).

## Null is a bitmask over nullable primitives only, and "set" means null

The generator's decisive choice, already recorded in [26](26-stored-nullability-violations.md), is
that a `nullable="true"` primitive stays a raw Java primitive. Absence is therefore unrepresentable
in the field itself and has to live somewhere else:

```jsp
<%-- templates/readonly/common/AttributesAndGetters.jspi:20-28 --%>
<% for (int i = 0; i < nullBitsHolders.length; i++) { %>
    private <%= nullBitsHolders[i].getType() %> <%= nullBitsHolders[i].getName() %> = <%= nullBitsHolders[i].getInitialValue() %>;
<% } %>
```

`initializeNullBitHolders(count)` (`generator/MithraBaseObjectTypeWrapper.java:277-301`) allocates
`ceil(count / 64)` holders named `isNullBits0`, `isNullBits1`, …, each widened to the number of bits
it actually carries — `byte` to 8, `short` to 16, `int` below 32, `long` to 64
(`getTypeForSize`, `:303-323`). Bit `i` lives in holder `i / 64` at position `i % 64`, and the mask
is emitted as a literal shift, promoted to `long` at 31 and above:

```java
// generator/MithraBaseObjectTypeWrapper.java:226-275
getNullGetterExpressionForIndex(i)  →  "(isNullBits<i/64> & <mask>) != 0"
getNullSetterExpressionForIndex(i)  →  "isNullBits<n> = (isNullBits<n> | <mask>)"
getNotNullSetterExpressionForIndex(i) → "isNullBits<n> = isNullBits<n> & ~(<mask>)"
```

Four properties of that design are worth stating exactly, because each is a decision rather than an
accident:

- **Only nullable primitives get a bit.** A reference-typed attribute answers `getter() == null`, a
  non-nullable primitive answers a literal `return false`, and neither consumes an index
  (`AttributesAndGetters.jspi:38-56`; `MithraObjectTypeWrapper.java:981-990`). The bitmap is
  therefore *narrower* than the field list and its indices do not correspond to field positions.
- **The polarity is "set means null".** The default initial value is `0`
  (`MithraBaseObjectTypeWrapper.java:287`), so a freshly constructed carrier reports every primitive
  as *not* null, holding Java's zero. `initializePrimitivesToNull="true"` on the object flips that
  by pre-setting every bit (`:288-296`; `reladomogen/src/main/xsd/mithraobject.xsd:62-66`), and the
  XSD documents it as a per-object opt-in defaulting to false.
- **It records nullity, not population.** Nothing distinguishes "this column was read and was NULL"
  from "this position was never filled". The two are the same bit, and which one a given carrier
  means is a property of the call site that built it.
- **The serialized form leads with it.** `zSerializeFullData` writes every null-bits holder first
  and then each field in the fixed order (`AttributesAndGetters.jspi:58-83`), so the wire form is a
  bitmap header followed by fixed positions — the same shape as the off-heap layout.

## Population is a metadata-driven position walk, and it can stop after the primary key

Hydration never names a column. It advances one cursor, `_pos`, in the order the generated column
list fixed, and every per-attribute read is `_pos++`:

```jsp
<%-- templates/InflateAttributes.jspi:60-63, 84-104 (the String and default arms) --%>
_data.<%= currentAttribute.getSetter() %>(<%= currentAttribute.getResultSetGetterForString("_pos++") %>);
...
_data.<%= currentAttribute.getSetter() %>(<%= currentAttribute.getResultSetGetter("_pos++") %>);
<% if (currentAttribute.isNullable() && currentAttribute.isPrimitive()) { %>
    if (_rs.wasNull()) { _data.<%= currentAttribute.getSetter() %>Null(); }
<% } else { %>
    checkNullPrimitive(_rs, _data, "<%= currentAttribute.getName() %>");
<% } %>
```

The walk is split in two, and the split is what makes partial population expressible:

```jsp
<%-- templates/CommonDatabaseObjectAbstract.jspi:358-365 --%>
public <%= cls %>Data inflate<%= cls %>Data(ResultSet rs, DatabaseType dt)
{
    <%= cls %>Data data = inflate<%= cls %>PkData(rs, dt);
    inflateNonPk<%= cls %>Data(<%= wrapper.getNonPkResultSetStart() %>, data, rs, dt);
    return data;
}
```

`inflate…PkData` allocates the carrier — choosing the concrete subclass by probing the leading
per-child discriminator columns, `CommonDatabaseObjectAbstract.jspi:371-400` — and fills the primary
key positions alone. `inflateNonPk…Data` takes a **starting position** as its first parameter and
fills the rest. Two facts follow:

- **A primary-key-only read produces a genuinely partial carrier.** The mass-delete path selects
  `getPkColumnList(...)` and calls `inflatePkDataGenericSource(rs, source, dt)` with no second
  stage, using the result purely as a cache lookup key
  (`mithra/database/MithraAbstractDatabaseObject.java:3521-3528`). Every non-key field is left at
  its Java default with the null bitmap in its initial state, and nothing on the object records that
  it is partial.
- **A position walk can skip a block whose width the metadata knows.** Under table-per-class
  inheritance the non-key stage tests the carrier's runtime type per child level and, where it does
  not match, advances the cursor past that child's columns without reading them:

  ```jsp
  <%-- templates/CommonDatabaseObjectAbstract.jspi:440-455 --%>
  if (_datax instanceof <%= subClasses[s].getDataClassName() %>) { /* inflate that block */ }
  else { _pos += <%= subClasses[s].getNonPkAttributeCount() %>; }
  ```

The refresh paths reuse the same second stage against an existing carrier
(`MithraAbstractDatabaseObject.java:2265`, `MithraAbstractDatedDatabaseObject.java:346`,
`MithraAbstractDatedTransactionalDatabaseObject.java:200`), which is the same statement from the
other side: positions are addressable independently of the object's history, because the metadata
alone decides where each one is.

## What Parallax adopts, adapts, and rejects

Reladomo is prior art here, not authority. The correspondence is close enough that the differences
are the informative part.

**Adopted.**

- *Fixed positions derived once per class from metadata, never per instance and never per read.* The
  publication plan is computed at class creation and shared by every published instance, exactly as
  a generated field offset is shared by every carrier of its class.
- *A bitmap header ahead of the positions.* The off-heap layout and the serialized form both put the
  null bits first and the fields after; Parallax's compact tuple puts the presence bitmap at
  position 0 and the fields after it, for the same reason — one header whose width is a property of
  the class.
- *No per-instance layout pointer, wrapper, or name-keyed presence.* A Reladomo carrier holds no
  reference to its metadata; a compact Parallax object holds no reference to its plan. Both resolve
  the ordinal from the class.
- *An ordinary read indexes a position and consults no presence state.* `getXxx()` on a Reladomo
  carrier returns the field; only `isXxxNull()` touches the bitmap. Parallax's field descriptors
  read their tuple index directly, and the bitmap is reached only by `model_fields_set` and
  serialization.
- *Root-first, one contiguous block per inheritance contributor.* Reladomo's column list and
  Parallax's `EntityLayout` member order arrive at the same ordering rule independently.
- *Distinct index spaces, kept distinct.* Reladomo runs four that never coincide; Parallax runs two
  — bit index `i` and tuple index `i + 1`, with the relationship tail past both — and the design
  states them separately for the same reason.

**Adapted.**

- *Polarity and coverage of the bitmap.* Reladomo's bit means "is null" and exists only for nullable
  primitives; Parallax's bit means "the read carried this member" and exists for every declared
  field. Parallax cannot borrow the narrower form, because `model_fields_set` and `exclude_unset`
  require distinguishing a carried explicit null from an absent optional — a distinction Reladomo's
  bitmap deliberately does not carry, since it records nullity rather than population.
- *One immutable tuple in place of typed fields.* CPython cannot generate per-class slots at the
  cost a Java field costs, and the published object must remain the user's actual Pydantic class
  rather than a generated subclass, so the fixed positions live in one tuple attached to a slot.
  The tuple is written exactly once; a Reladomo carrier is mutable by design.
- *Relationships share the tuple's tail instead of a lazily allocated side array.* Reladomo defers
  the `Object[]` until a relationship is written, which is cheap for objects whose relationships are
  never resolved. Parallax writes every declared broad relationship at publication — `UNLOADED`
  where the read did not load one — because the closed-world unloaded sentinel is what makes an
  ordinary relationship read able to raise, and a second allocation would cost more than the tail.
- *Partial population is refused rather than represented.* Reladomo's primary-key-only carrier is a
  first-class shape whose partiality nothing records. Parallax rejects a publication row missing a
  required field at population time, by one mask comparison, so no read pays a presence check and no
  published object is partial.

**Rejected.**

- *The carrier-plus-business-object split.* `currentData` means two heap objects per row, which is
  the opposite of this work's direction: Parallax's compact state is backing *underneath* the user's
  own instance, not a second object it points at.
- *The mutable managed lifecycle around the carrier* — the persistence-state machine, copy-on-write
  into a new `Data`, `getDetachedCopy`, and merge-back ([10](10-object-lifecycle.md)). A published
  Parallax value is frozen and an edit produces ordinary validated backing.
- *Portals, identity caches, and query caches* ([08](08-caching.md)). Nothing process-wide keyed by
  instance count survives a Parallax graph becoming unreachable.
- *Off-heap storage* ([08](08-caching.md), [19](19-cache-operations.md)). The offset computation is
  the useful prior art; the storage machinery is out of scope.
- *Code generation as a build step.* Reladomo's layout is decided by a JSP template run before
  compilation ([03](03-code-generation.md)). Parallax derives the equivalent plan at class creation
  from the declaration the author already wrote, so there is no generated artifact to keep in sync.

## Code references

- `templates/readonly/Data.jsp` — the carrier's whole generated shape; `:9` selects
  `getSortedNormalAndSourceAttributes()` as the field order
- `templates/readonly/common/AttributesAndGetters.jspi:20-83` — the null-bits holders, the attribute
  and embedded-value fields, the per-case null getters, and `zSerializeFullData`
- `templates/readonly/DataOnHeap.jspi:16-40,250-260,370-380,435-470` — the data-version byte, the
  lazily allocated relationship array, direct-reference fields, `clearRelationships`, and the
  relationship accessors
- `templates/readonly/DataOffHeap.jspi:19-80` — off-heap storage and the per-attribute null tests at
  generated offsets
- `templates/InflateAttributes.jspi` — the per-attribute `_pos++` hydration arms, including the
  `wasNull()` check and the non-nullable `checkNullPrimitive` refusal
- `templates/CommonDatabaseObjectAbstract.jspi:145-158,330-345,358-465` — the generic inflate entry
  points, the column list, the two-stage inflate, and the subclass block skip
- `generator/MithraBaseObjectTypeWrapper.java:28,226-323,415-450` — the holder name prefix, the bit
  masks, holder sizing, and the `NullBitsHolder` record
- `generator/MithraObjectTypeWrapper.java:320-340,968-990,1550-1613,2579-2588,3330-3429` —
  relationship array positions, null-bit index assignment, off-heap offsets, the settable
  relationship count, the column list, and the sorted field order
- `generator/AbstractAttribute.java:352-355,805-808,931-939` — the nullable inversion for primary
  keys, the unboxed storage type, and the name-only comparator
- `generator/RelationshipAttribute.java:1260-1273` — direct reference versus array storage
- `mithra/superclassimpl/MithraTransactionalObjectImpl.java:49-51` — the two fields a business
  object carries of its row
- `mithra/database/MithraAbstractDatabaseObject.java:2265,3521-3528` — the refresh path's non-key
  reuse and the primary-key-only inflate
- `reladomogen/src/main/xsd/mithraobject.xsd:62-66` — `initializePrimitivesToNull`
