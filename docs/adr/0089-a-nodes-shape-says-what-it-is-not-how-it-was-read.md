# A node's shape says what it is, not how it was read

A Wire node of an inheritance participant carries `familyVariant` whatever read
delivered it, and every node in a `then.graph` holds only its own concrete variant's
members, at every level. Before this, the contract tied both to the read: a concrete
target or a single-concrete narrowed view carried no tag because "the caller already
knows the variant", and a polymorphic node in a read with Includes was authored with
its siblings' columns as `null`.

One object therefore had several shapes. The same Dog was tagged under `pets` and
untagged under `pets[Dog]` in one graph, and had an `indoor: null` key at a child level
that it did not have at the top. Code consuming a node had to know which query
produced it. A Wire mapping has no `type()`, so the tag is its equivalent of the class
a Typed result always gives, and "the caller already knows" fails for any consumer
shared across reads. A Typed `Dog` has no `indoor` member, so padding also broke the
rule that Typed and Wire publish one shape.

The sources had already drifted apart. Python published the per-variant, tagged node
everywhere. Some goldens agreed and others did not, and two mechanisms kept the
mismatch quiet: a recorded residual excused child-level differences, and the flat-row
lane dropped the tag, so a test asserting its absence could not fail. Both are gone, so
these shapes are now graded exactly.

`then.rows` keeps its fixed superset. It is the flat view of a read's columns rather
than a node, and it stays a statement about SQL. The tag is still never projected as
SQL: it comes from the node's concrete Entity.

The name is now reserved on every Entity: no Attribute, Attribute column, Value Object
occurrence, Value Object storage column, or relationship may be spelled `familyVariant`,
whether or not its Entity is in a family. This replaces a permission to store a Value
Object in a column of that spelling and a reservation limited to family members. Under
those, one key could mean the tag or domain data depending on the Entity, code had to
ask which before reading it, and a row keyed by physical column could need two values
at one key. Whether a node carries the tag still depends on being in a family, but the
name means one thing everywhere.

The alternative for each was to change Python to match the older text: stop tagging by
read position, and pad every node. That would give an object a key it does not have,
and make its shape depend on the query that fetched it.
