# Compact Pydantic state uses a framework-owned instance-state seam

Published compact Entity and Value Object instances remain instances of the
user's actual Pydantic class, so their alternate backing must compose with
Pydantic's compiled serializer and every supported authored serializer without
changing the object those extensions observe. The seam that achieves it is a
**presentation of instance state**: pydantic-core reads a model's physical state
by interned attribute name — `__dict__`, `__pydantic_fields_set__`,
`__pydantic_extra__` — in both its serializer and its validator, and never
through CPython's dict-slot pointer. So one shared framework root binds data
descriptors under the first two names, and `Entity` and `ValueObject` extend it.
A published value answers `__dict__` with a mapping built from its row and
`__pydantic_fields_set__` with a set synthesized from its bitmap, never touching
its real storage; an ordinary value answers with its real storage by identity, so
a caller writing through it still reaches the value. Pydantic's own equality,
hashing, repr, iteration, JSON Schema, and compiled serializer then read what
they believe is an instance dictionary and are correct by construction. Entity
and Value Object declarations reserve `__dict__` and `__pydantic_fields_set__`,
because the seam's integrity rests on the framework being the only thing bound
under those names; other supported Pydantic extension points remain authored
behavior.

The integration must serialize the original instance directly. A transient
ordinary same-class proxy was rejected because instance-bound serializers and
computed fields observe the proxy as `self`; temporarily populating the compact
object's ordinary Pydantic state was rejected because it mutates shared frozen
state and adds allocation and exception-restoration hazards; replacing the
compiled serializer by hand was rejected because it would have to reproduce
Pydantic's evolving composition rules; a `core_schema` wrap serializer was
rejected on evidence, because field serialization needs the model context only
the model serializer establishes and that serializer reads the instance
dictionary, so no wrap handler can be fed compact values.

**A framework-owned core-schema seam was built first, and replaced.** It restated
every declared field as a `computed_field` so pydantic-core reached values
through the member descriptor, with a presence filter above it restoring
`exclude_unset` and `exclude_defaults`, and it needed a second owned hook,
`__get_pydantic_json_schema__`, because a computed field is always required in
serialization mode. Two defects decided against it, both reproduced: an authored
wrap `@model_serializer` silently ignored `exclude_unset` and `exclude_defaults`
on both backings, because the schema assigned a serialization schema where
pydantic-core expected a core schema; and serialization permanently materialized
a published node's instance dictionary, roughly 91 bytes per node, adding back a
third of the footprint the work removes. The presentation dissolves both rather
than patching them — pydantic-core runs its own field serializer, and nothing
asks the value for a real mapping — and deletes the presence filter, the
computed-field restatement, both owned schema hooks, and the Parallax
reimplementations of equality, hashing, repr, and the populated-member set that
existed to work around not having the descriptors.
`__get_pydantic_core_schema__` stays reserved although the framework installs
none, because a later claim may install a Parallax-owned serializer and needs
that seam unambiguously the framework's.

**The proof passed.** On pydantic 2.13.0 with pydantic-core 2.46.0 (the declared
floor) and on the repository lock, on CPython 3.13 and 3.14, three arms —
compact, ordinary, and a hand-written plain `BaseModel` twin — agree byte for
byte across the full serialization option cross-product in both modes, nesting,
`TypeAdapter` containers, plain and discriminated unions, `serialize_as_any`,
polymorphic serialization over a runtime subtype, `RootModel`, generic, recursive
and self-referencing models, both JSON Schema modes, equality, hashing, repr,
iteration, `from_attributes`, and validation of an already-published value. The
corpus grades output rather than mechanism, which is why the mechanism could be
replaced underneath it, and why a future pydantic-core change of route breaks
loudly in the gate rather than silently in production.

**What the seam costs is part of its Interface, and is stated rather than left to
be discovered.** Measured over the six canonical scenarios of
`docs/instance-state-baseline.md`, a published node retains a little over two
fifths of what an ordinary one does — 43.8% on CPython 3.14 and 41.0% on 3.13,
against an ordinary arm built by the validating constructor, which carries no
lifecycle state because a plainly constructed instance has none. The claim's own
target is stated over a different pair, the publication path before and after
this change, and that reduction is 51.8% on 3.14 and 54.7% on 3.13 against the
33% the claim accepts. It pays for both at two reads, and at construction. A
published value's `model_dump` runs about 2.2x an ordinary value's, because
pydantic-core reads `__dict__` twice per instance per dump and each read builds a
presentation; `docs/deferred-ledger.md` D-82 is the optimization path and what is
known about taking it. A published value's declared-member read runs about 3.2x
an ordinary one's on 3.14 and 3.4x on 3.13, because a published node has no
instance dictionary and the read resolves through the member descriptor instead
of a C-level dictionary hit; D-83 carries that one. Publishing one more node also
costs about 3.5x validating one more ordinary instance — the marginal cost of an
additional node on both sides, with the `construct` call a caller pays for a graph
and never pays for a constructor outside it and beside it. Against the publication
path this change replaced — the other of the two comparisons, and the one the 33%
target is stated over — construction moved by about a tenth: 1.10x on both 3.14
and 3.13 measured like for like, inside the 20% the claim reviews at, with
the recorded document stating what each of those two comparisons divides. Both are confined to published values: an ordinary value's
member read is a plain Pydantic model's, unchanged, which is the trade the claim
forbids making silently and therefore makes explicitly.
