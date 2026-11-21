# One preparation entry per write family

Every write reaches the Unit of Work through one preparation entry per write
family: `prepare_insert`, `prepare_keyed_write`, `prepare_target_write`, and
`prepare_predicate_write`. Each takes the already-resolved target, a
representation, and what the write states, and returns the write in its
prepared form. Each entry's body is its family's judgment order from
[`m-unit-work`](../../../../core/spec/m-unit-work.md#serialized-write-elaboration),
written as a short sequence of shared steps rather than a generic driver with
per-family hooks, so the order can be read against the specification line by
line.

A write states the specification's complete or partial payload, explicit
assignments, or, for a predicate-selected deletion, nothing beyond its
selection. The binding's choice is the carrier. A complete payload is one
iterable of values in member order, read once, so a Typed instance's member
iterator goes in uncopied unless member names must be judged before its values.
A partial payload is `(position, value)` pairs in authored order. Both carry the
names their caller stated that the target does not list, so preparation can
refuse them in the specification's order. Only the Typed edit chain marks a
partial payload as already judged, because `edit()` judged those assignments
([ADR 0057](../../../../docs/adr/0057-typed-and-wire-are-peer-interfaces-over-one-transaction.md));
explicit Typed assignments travel unresolved beside the payload and are judged
in core. Typed callers read an instance's values by position when the model
proved its class lays them out in member order, and by name otherwise; Wire
callers and conformance build payloads once from name mappings through the
Entity's preparation, which converts no value.

Typed and Wire differ only by a representation constant, `TYPED` or `WIRE`. It
selects the value converter and whether a complete payload's framework-owned
and replacement-excluded cells are state the instance carries or cells the
caller authored and preparation judges
([ADR 0054](../../../../docs/adr/0054-framework-owned-members-are-refused-by-one-assignment-rule.md)).
No production caller names the codec's lane index. There is no third
representation: conformance prepares case writes as a Wire caller, so a case
payload is judged exactly as a real Wire payload is.

Judgment of the resolved inputs passed to the four entries has one owner.
Adapters still resolve their inputs first and refuse what cannot become one:
for example, an undeclared Entity class, an instance member the connected model
does not declare, or a predicate-selected replacement of an Entity other than
the selected target. The instructions module keeps only the Write Instruction
document form: the mutation vocabulary, the instruction records, the rejection
codes, the observation-key guard that document constructors and Wire adapters
apply before preparation, and `serialize`/`deserialize`. The preparation module
holds the payloads, representations, per-Entity preparation, the four entries,
every judgment step over their resolved inputs, and the prepared results with
their private factories. Preparation imports the document vocabulary, never the
reverse, so a reader finds every rule that judges a resolved write in one place
and no record exists only so core can unpack it. Prepared results remain frozen
`init=False` records built only by that module's factories, so holding one
still proves the write was judged.

Keeping the five earlier entries as thin wrappers was rejected: their names
would still encode the representation and each would remain a shallow module. A
single `prepare(instruction, representation)` entry was rejected because it
forces records Typed callers do not have and needs overloads to type its
result. Building every payload from names was rejected because it reverses the
Typed positional path into positions, names, and positions again. Deferring
assignments through caller-supplied callbacks was rejected because it splits the
judgment order across adapters; core resolves assignments when its order
reaches the payload. Marking the edit skip on the representation was rejected
because explicit Typed assignments must still be judged.

This supersedes [ADR 0013](0013-prepared-write-admissibility.md), whose two
producers, temporal single-row rule, and error classes no longer exist. Its
prepared-result construction boundary stands.
