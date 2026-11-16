# m-pk-gen — Primary-Key Generation

`m-pk-gen` is the **primary-key allocation strategy** a normalized Attribute
may declare. Its behavior consumes `m-metamodel`; the canonical descriptor is
only an authoring/serde adapter.

A primary-key Attribute MAY declare how its value is allocated.
`application-assigned` (the default) means the application supplies it;
`key-sequence` hands keys out of blocks a native database sequence reserves (see
[Native key sequences](#native-key-sequences)).

| Strategy | Meaning |
|---|---|
| `application-assigned` | application-assigned (default) |
| `key-sequence` | native pooled sequence (`name`, `batchSize` = 100, `initialValue` = 1, `incrementSize` = 1) |

Accepted metadata uses
`NotPrimaryKey | PrimaryKey(ApplicationAssigned | KeySequence(...))`.
Descriptor `primaryKey: true` with omitted `pkGeneration` normalizes to
Application Assigned; `pkGeneration` on `primaryKey: false` is invalid. This
sum prevents a non-primary-key Attribute from carrying a generation strategy.

`KeySequence` is legal only on an `Int32` or `Int64` Attribute: a native
sequence holds integers, so a non-integral generated key has no meaning.
`ApplicationAssigned` follows [Metamodel key eligibility](m-metamodel.md#attributes-and-primary-keys).

Invalid generator/type combinations are unconstructible in normalized Attribute Metadata before the Unresolved Metamodel seam. Public descriptors reject them through the schema's attribute `type` conditional; native language declarations translate construction failure at their declaration boundary.
KeySequence defaults are resolved there as well (`batchSize` 100,
`initialValue` and `incrementSize` 1, fixed by the schema).

## Logical allocators

A `key-sequence` declaration's `name` is a **logical allocator key**: an exact,
case-sensitive, model-wide key, independent of Entity Namespaces and of the
Table that stores the declaring Entity. It names an allocator, not a physical
database object; where an allocator physically lives is a deployment fact the
model does not carry. Declarations with equal keys deliberately share one
allocator, so they MUST agree on everything that allocator hands out: the
batch size, the initial value, the increment size, and the key's declared
neutral type, which together fix the key range. A disagreeing declaration is
reported at its own Attribute as `pk-gen-key-sequence-conflict`, related to the
first declaration of the key in canonical Entity order and then declaration
order; every disagreeing declaration is reported.

A family's primary key and its generation are declared once, by the ancestor
that introduces the key (`m-inheritance`), and every position of the family
inherits that one declaration. It therefore counts once toward this rule
however many positions inherit it, including under a table-per-concrete-subtype
root that owns no table, and the family resolves one allocator even when its
concrete tables are stored apart. A subtype that declares a `key-sequence` key
of its own is refused as `pk-gen-key-sequence-subtype-override`: a family has no
per-subtype allocator.

`m-pk-gen` contributes this Model Formation Rule Set and no facet. The rules
read only declared metadata; they neither create nor consult a database
object.

## Native key sequences

A `key-sequence` allocator hands keys out of blocks reserved from one native
database sequence, which the database binding places (`m-database-binding`).
The sequence advances by `batchSize × incrementSize` per reservation; a
reservation's first value is its block's first key, and later keys of the block
follow `incrementSize` apart. Every positive batch size, `1` included, uses the
same allocator. Keys never leave the effective key range — the key type's
values intersected with what the backend's sequences hold — and never wrap: a
final block is clipped to the range, its remaining keys are handed out, and the
next reservation reports exhaustion. `initialValue` is where a newly created
sequence starts; it is never a requirement on a live sequence's position.

A key is **supplied** or **omitted**, decided by whether the member was set and
never by its value: an explicit `0` is supplied, and an explicit null is refused
by the key's own non-null type. Only a key-sequence key may be omitted, and only
by an insert (`m-unit-work`); a supplied key is used as given under either
strategy and is never checked against reserved blocks, so keyed writes behave
alike whichever strategy is configured. A supplied key the sequence has not yet
reached can collide with a later block; preventing that is the deployment's
responsibility, as is adopting an existing sequence whose position is safe for
the stored data.

An insert of a row whose key is omitted allocates the key **at the insert
call**, after the row's preparation has admitted it and before the row is
buffered under the object its key names: a refused row spends no key, and a
failed allocation buffers nothing. Each such insert allocates a fresh key,
including a repeated insert of one draft. A key handed out once is never handed
out again, a rolled-back insert does not return it, and keys that a root
reserved but never handed out are abandoned when the root closes or its process
ends; gaps are expected, and keys promise neither commit order nor consecutive
numbering.

Each Database root holds at most one reservation per physical sequence and
allocation settings, shared by everything the root runs. Handing out a key the
reservation still holds runs no statement and takes no connection. Refilling
runs one statement on its own writer acquisition, outside the application's
transaction and committed on its own, under the deployment's database login
(`m-execution-authority`); that statement reserves the block and reads back the
live sequence's increment, bounds, cycling, and type, and the block is handed
out only once the live definition matches the declaration: the increment equals
`batchSize × incrementSize`, the bounds lie within the key range, and the
sequence does not cycle. A reservation that finds no sequence is refused as
`key-sequence-missing`, one whose live definition differs as
`key-sequence-mismatch`, and one past the key range as `key-sequence-exhausted`;
none is retried, and none hands out a key. A refill that cannot finish within the
provider's acquisition budget, or whose outcome is uncertain, publishes no key
and leaves the next reservation to start anew.
