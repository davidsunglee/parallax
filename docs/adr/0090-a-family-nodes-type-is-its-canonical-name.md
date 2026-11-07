# A family node's type is its canonical name

A Wire node of an inheritance participant carries `_type`, holding the canonical name
of its concrete Entity, in place of `familyVariant` and its variant spelling. This
replaces only the tag's spelling and reservation from
[ADR 0089](0089-a-nodes-shape-says-what-it-is-not-how-it-was-read.md); every family
node still carries the tag, whatever read reached it.

`familyVariant` had two weaknesses. It was a legal member name, so it needed a
reservation across every kind of member. Its value also moved: a node read `Dog` until
a second concrete subtype of that local name joined the family from another namespace,
and then every existing Dog node silently read `catalog.Dog`.

`_type` removes both. A member name begins with a lowercase letter, so no member can
spell it, and `familyVariant` is an ordinary name again. A canonical name does not
depend on the family's other members. The cost is a longer value on every family node,
and a client matching on it states a full name.

A Column is the one remaining collision, because a Column name can be any string and a
flat row is keyed by Column. So no Entity may store an Attribute or a Value Object in a
Column spelled `_type`, whether or not it is in a family. That costs almost nothing now,
means no such Column can block an Entity from joining a family later, and keeps `_type`
on every node possible. It does stop a model from mapping an existing Column of that
name. Neither a tag Column nor a shared Structured Column renders under its own
spelling, so neither is refused.

The variant spelling stays where it is not a node's type: in narrowed view keys such as
`pets[Cat,Dog]`, and in the `family_variant` literal of a table-per-concrete-subtype
`union all`. Reading a row maps that literal to its concrete Entity, so a Wire change
alters no statement.

`_type` stays off nodes outside a family. On every node, a generic client could decode
any node alone, and an Entity joining a family would keep its Wire format. We chose not
to do that, because it adds a permanent cost to every node, roughly 60% more JSON on a
narrow row by arithmetic rather than measurement. Outside a family the caller already
knows the type from its query or relationship, and joining a family is rare, already
modeled as `InheritanceChanged`, and adds one key. Moving to every node later is purely
additive, so it should wait for generic clients to be real and for payload and memory
measurements.
