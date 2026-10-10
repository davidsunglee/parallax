# Python declarations

This document owns Python authoring choices beyond the portable
[Metamodel](../../../core/spec/m-metamodel.md),
[Model Formation](../../../core/spec/m-model-formation.md), and
[Wire](../../../core/spec/m-wire.md) contracts. Public signatures and their
types are defined in the exported Python modules; executable examples live in
the [API suite](../tests/api/).

## Classes and names

Applications declare Pydantic-based `Entity`, `TxTemporal`, `Bitemporal`, and
`ValueObject` classes. An Entity has exactly one Parallax base; unrelated mixins
and multiple Parallax bases are refused. Domain Entity inheritance requires an
explicit `inheritance=` role. Class creation validates Python declaration shape;
`DomainModel` construction judges model-wide relationships and formation rules.
There is no global model registry and no generated class surface.

Entity `name=` overrides the class name verbatim. `namespace=` is local to each
class and is never inherited from a base or module. Entity tables are explicit.
The class header uses exceptional `persistence=READ_ONLY` and
`layout=Document(column=...)`; omission means Read Write and Columns. Descendants
cannot redeclare a family's persistence or layout. Inheritance uses
`AbstractRoot(strategy)`, `AbstractSubtype`, and `ConcreteSubtype`; a TPH concrete
subtype supplies `tag_value=`, while a TPCS concrete subtype supplies its table.

`Document`'s column defaults to `payload` at authoring; accepted metadata and
descriptor output always contain that resolved name. `Document` and
`Document()` are equivalent, as are other all-optional variant classes and
their zero-argument instances. Required-argument variants must be instantiated.

Python member names become canonical names by removing each underscore and
capitalizing the following character. `attr(name=...)` and `rel(name=...)`
override that conversion; collisions are rejected at class creation. Storage
selection follows identity selection: explicit `column=` wins, otherwise the
portable `default_column_name` is applied to the resolved canonical name.
Descriptor input already uses canonical names and is never reverse-converted.
Strings in `join`, `reverse_of`, `order_by`, and `index` use Python declaration
names, not canonical spellings. Indices name local scalar members only, in
declared component order; inherited members and Value Object paths are excluded.

Mapped names cannot shadow framework query, inspection, edit, serialization,
Pydantic state, or object-layout members, nor any operation a member expression
answers itself (`any`, `all`, `none`, `element`, `exists`, `is_a`, the scalar
operation methods, and the like): such a member keeps its canonical name under a
free Python name through explicit renaming. `model_*` and `__parallax_*` names are
reserved, including unannotated class-body bindings. Framework temporal members
cannot be redeclared. The exact rejected spellings are pinned by declaration
tests and the frontend's reserved-name checks.

`TxTemporal` supplies `tx_start` / `tx_end`, stored in `in_z` / `out_z`;
`Bitemporal` also supplies `valid_start` / `valid_end`, stored in
`from_z` / `thru_z`. They use ordinary member-name conversion and are
framework-owned: direct construction and edits cannot author them. There is no
public temporal-axis declaration or column override. Valid Time and Transaction
Time are the only accepted vocabulary; no business/processing aliases exist.

## Attributes and relationships

`Attr[T]` is the member annotation for scalars and Value Objects. Its assignment
slot may contain `attr(...)`, never a bare default value. Nullability comes only
from the annotation (`T | None`); there is no `nullable=` option. `int` means
Int64 and `float` means Float64; `type=Int32` and `type=Float32` narrow those
families. Decimal requires both `precision=` and `scale=`. `primary_key=True`
means application-assigned; `MAX` and `Sequence(...)` imply an integer primary
key. No free-form JSON member annotation exists.

Ineligible key types and incompatible generation fail at class creation with `EntityDefinitionError` and code `entity-option-context-invalid`, before a `DomainModel` can be constructed. Eligibility belongs to the [Metamodel](../../../core/spec/m-metamodel.md#attributes-and-primary-keys). Public descriptor inputs reject serialized key-policy violations in the schema phase instead.

`Rel[T]` requires `rel(...)`. Its defining form names `cardinality`, `join`,
optional `dependent`, `order_by`, and `name`; its reverse form names
`reverse_of`, optional `order_by`, and `name`. Mixing the forms is refused.
A class or qualified string reference is exact; a bare string is relative to
the declaring namespace. Resolution uses the Domain Model's candidates, never
module globals or `eval`.

`Rel[T]` and `Rel[T | None]` are to-one; `Rel[tuple[T, ...]]` is to-many and
never nullable. Annotation optionality must exactly match the model's
loaded-null possibility. Mismatches are reported together at model construction
as `entity-relationship-annotation-mismatch`. Unloaded is never `None`.
Relationship ordering uses target-local names, with `asc` / `desc` for direction
and optional single-shot null placement. A bare name is ascending; omitted null
placement is last in either direction.

`Attr[tuple[T, ...]]` over a scalar `T` declares a scalar collection: its
element type is `T` after the ordinary type-shaping options (`type=`,
`precision=`, `scale=`), which apply to each element. It defaults to `()`, is
never nullable, and accepts exactly a `tuple`, as a Value Object Many does;
`max_length`, `primary_key`, and `optimistic_locking` are refused, while
`column` and `read_only` keep their Entity meaning. Value Object scalars use the
same spelling. Its whole value is assigned through `edit(...)` or `.set(...)`, and
a scalar comparison, membership, range, string, null-check, or ordering
expression over it is refused at authoring.

`ValueObject` classes are frozen and discovered through Entity occurrences;
they are not registered as model candidates. `Attr[VO]`, `Attr[VO | None]`, and
`Attr[tuple[VO, ...]]` spell One, nullable One, and Many. A Many is never nullable
and uses `()` when empty. Value Object scalars accept naming and scalar-shaping
options, but no Entity storage, key, locking, generation, or length options.
Only an Entity-level occurrence may name its storage column.

## Python scalar carriers

These are developer-input choices; serialized literals follow core Wire rules.

| Neutral value | Python carrier and input policy |
|---|---|
| Boolean | `bool` only |
| Integer | `int` within the declared width; `bool` is rejected |
| Float | finite `float`; integral input only when exactly representable at the declared width |
| String / bytes | `str` / `bytes` |
| Decimal | `decimal.Decimal` or `int`, never `float`; declared precision and scale apply |
| Date / time | `datetime.date` / timezone-free `datetime.time` |
| Timestamp | timezone-aware `datetime`, normalized to UTC at microsecond precision; the UTC instant must be representable |
| UUID | `uuid.UUID` or canonical UUID string |
| Value Object | an instance of the declared class, never a raw dictionary |
| Scalar collection | a `tuple` of the element type's carriers; a read publishes an immutable `tuple` |

Float32 reads use Python's binary64 carrier widened from the actual binary32
value. A Python `float` written to a Float32 member, as a Typed value or as a
Wire number, names the number its shortest round-trip spelling (`repr`) names,
which is the number JSON serialization writes for it, and that number rounds
once to binary32. So fractional input may round, both APIs store the same value
for the same `float`, and a published Float32 value writes back as itself. A
Wire number parsed from JSON text keeps its authored digits and rounds from
those instead. Integer input cannot lose precision. Direct construction runs
application Pydantic validators. Database materialization does not run those
validators or authored constructors.

## Editing, presence, and serialization

`edit(**changes)` is the copying operation for Entity and Value Object values.
It validates authored changes and returns a frozen copy; `model_copy`, legacy
`copy`, `copy.copy`, and `copy.deepcopy` refuse with `EditError(edit-use-edit)`.
An empty edit is legal and preserves an existing Change Record. Entity edits
carry read provenance and already-loaded relationship objects, including a view
of the old target when the edit changes a join endpoint.

Application state outside declared members is shallow-carried without invoking
assignment hooks. Every `functools.cached_property` cache is dropped on every
edit, including an empty edit. A manually seeded cache has no such declaration
and is carried. Value Object presence is reflected by `model_fields_set`:
omission and explicit `None` remain distinct through nested hydration and edits.

Materialized Entity values, including their edited copies, refuse pickling with
`pickle.PicklingError`; ordinary constructed Entity values and Value Objects
retain their ordinary data serialization. Serialization does not transfer write
authority. Public sentinels such as `LATEST`, `UNLOADED`, and
`MISSING_STORED_VALUE` preserve identity through construction, copying, and
pickling, and use their exported names in `repr`. Zero-field algebra values such
as `MAX` have equality semantics, not singleton identity semantics.

## Descriptor and metadata boundary

`parallax.descriptor` accepts documents, JSON, or YAML and exports canonical
descriptors. Text decoding failures are `DescriptorSyntaxError`; document input
starts at schema validation. A descriptor-backed model has no Entity Classes
and supports Wire execution without Typed materialization.

`model.meta(...)` accepts a composed Entity Class, canonical identity spelling,
or `EntityIdentity`. It returns local immutable metadata, not flattened inherited
members or effective convenience aliases. Invalid spelling and unknown identity
raise `MetamodelLookupError` with `metamodel-invalid-entity-reference` and
`metamodel-entity-not-found`, respectively. The underlying class-free lookup
protocol continues to answer absence.
