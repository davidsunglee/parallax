# Null placement is explicit and defaults to last

Every ordering term has one Sort Direction and one Null Placement. Sort
Direction is Ascending or Descending; Null Placement is Nulls First or Nulls
Last. Omitted direction means Ascending, and omitted placement means Nulls Last
for either direction.

The values are shared across canonical operation Sort Keys and declared
relationship ordering. The operation `orderBy` key and the Metamodel
relationship-order term both admit an optional `nulls: first | last` field.
Omission retains the default while an explicitly requested placement is what
the query observes. Language frontends may provide idiomatic builders, but they
do not define provider-specific placement rules.

SQL lowering makes placement portable. A dialect with native `NULLS
FIRST`/`NULLS LAST` syntax uses it; another dialect emits an equivalent
null-rank ordering expression before the value key. Provider-native defaults
never determine observable null ordering.

Python uses the same values for query and declaration authoring. A bare
Attribute Sort Key means ascending with nulls last. `.asc()` and `.desc()`
choose direction; only the resulting Sort Key exposes one single-shot
`.nulls_first()` or `.nulls_last()` placement modifier.
Relationship declaration terms returned by `asc("member")` and
`desc("member")` expose the same placement modifiers.

Keeping one normalized value pair prevents query ordering and relationship
collection ordering from drifting while allowing callers to request either
portable placement without introducing raw SQL or dialect branches.

The two terms keep their own member spellings — `attr` on an operation Sort Key
and `attribute` on a declaration — because the spelling tracks a scoping
difference the placement field does not change. They also normalize differently,
and deliberately: an operation Sort Key preserves omitted-versus-explicit `last`
through canonical round-trip, while the Metamodel term normalizes omission to
Nulls Last at the accepted boundary and canonical descriptor form omits it again,
so a declaration cannot spell the default at all.

The contract change lands atomically across the Metamodel and operation
schemas, specifications, compatibility cases, dialect renderers, and claiming
language frontends — no intermediate state exists in which a schema admits a
placement that a frontend does not author or a dialect does not lower, and no
frontend introduces an interim private field or provider-specific behavior.
