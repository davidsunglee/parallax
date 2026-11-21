# One preparation entry per write family

Every write reaches the Unit of Work through one preparation entry per write
family: `prepare_insert`, `prepare_keyed_write`, `prepare_target_write`, and
`prepare_predicate_write`. Each takes the already-resolved target, a
representation, and one payload, and returns one judged row in its prepared
form. Each entry's body is its family's judgment order from
[`m-unit-work`](../../../../core/spec/m-unit-work.md), written as a short
sequence of shared steps rather than a generic driver with per-family hooks, so
the order can be read against the specification line by line.

A payload takes one of the specification's two shapes. A complete payload
states an opening's or a replacement's whole state, one value per member in
member order, and is read once, so a Typed instance's member iterator goes in
uncopied. A partial payload states an amendment's members or a destructive
write's identity as `(position, value)` pairs in authored order. Both carry the
names their caller stated that the target does not list, so a sibling-branch or
derived member is refused as such before an undeclared one. Only the Typed edit
chain marks a partial payload as already judged, because `edit()` judged those
assignments ([ADR 0057](../../../../docs/adr/0057-typed-and-wire-are-peer-interfaces-over-one-transaction.md));
explicit Typed assignments travel unresolved beside the payload and are judged
in core. Typed callers build payloads from member positions; Wire callers and
conformance build them once from name mappings through the Entity's
preparation, which converts no value.

Typed and Wire differ only by a representation constant, `TYPED` or `WIRE`. It
selects the value converter and whether a complete payload's framework-owned
and replacement-excluded cells are state the instance carries, read as
unstated, or cells the caller authored, each judged and a framework-owned one
refused ([ADR 0054](../../../../docs/adr/0054-framework-owned-members-are-refused-by-one-assignment-rule.md)).
The codec's lane index stays inside preparation. There is no third
representation: conformance prepares case writes as a Wire caller, so a case
payload is judged exactly as a real Wire payload is.

Judgment has one owner. The instructions module keeps only the Write Instruction
document form: the mutation vocabulary, the instruction records, the rejection
codes and observation-key guard, and `serialize`/`deserialize`. The preparation
module holds the payloads, representations, per-Entity preparation, the four
entries, every judgment step, and the prepared results with their private
factories. Preparation imports the document vocabulary, never the reverse, so a
reader finds every rule that can refuse a write in one place and no record
exists only so core can unpack it. Prepared results remain frozen `init=False`
records built only by that module's factories, so holding one still proves the
write was judged.

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
