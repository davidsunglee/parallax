# Stored-data violations are classified at the result root

A read represents stored state that violates the accepted model as an ordered
root-level `T | InvalidData[T]` union. Any issue in a root's requested include
tree classifies that root as `InvalidData`; the record carries every
unique `StoredDataIssue` in a frozenset and carries the hydrated root only
when hydration requires no invented value. Ordinary result access raises with
the same complete records, while a checked view returns the union; neither view
silently drops, repairs, or publishes a node-level invalid value. This preserves
root position and atomic graph publication while allowing diagnosis and
ordinary caller-authored writes, unlike fatal decoding, a delayed side
collection, node-level unions, pruning, or silent inclusion.

When `data` is present, it is an ordinary observed write source rather than a
repair command. Ordinary ingress semantics remain unchanged: a Typed assignment
equal to the hydrated collapse is still a no-op, and a keyed Wire assignment is
compared with the corresponding value in its frozen hydrated source. The Wire
verb retains only explicitly changed-member originals rather than a duplicate
read result. An effective ordinary write may incidentally replace malformed
storage, but the API does not promise that every issue is repairable through
ordinary writes and retains no repair-sensitive bookkeeping. A subsequent read
classifies the stored state that remains. The `InvalidData` wrapper is never
writable, and `data=None` supplies no write source. Storage-aware administrative
repair lies outside this API contract.

Classification diagnostics never retain write authority. A non-hydrating
`InvalidData(data=None)` creates no eligible observation claim even when its
Object Key, version, or Edge is decodable; there is no materialized Entity node
whose liveness could own one, and a reconstructed ordinary mapping is not a
keyed write source. Hydratable invalid data follows the ordinary per-node
source-liveness rule, so each materialized independently writable node retains
its own claim.

The checked union is the complete result surface. A finite caller may partition
it with ordinary collection operations, but Parallax adds no valid/invalid
partition method or second collection shape.

`m-snapshot-read` owns the public `StoredDataIssueCode` vocabulary and issue
identity because classified violations arise at several lower seams, not
only document decoding. Each lower module still detects the facts in its own
domain; Snapshot Read translates those findings into the one stable result
taxonomy without re-judging them.

Each public issue consists only of its stable code, an `EntityIdentity`, an
optional affected `ObjectKey`, an optional `MemberIdentity`, the entity-relative
logical path of the rejected occurrence, and the immutable rejected value itself.
The Object Key is absent when the affected object's primary key cannot be decoded
or its family tag does not resolve; the member is absent only for the
invalid-family-tag case. No cause, mutable details mapping, or separately
authoritative message crosses the result seam.

The rejected value is the one raw value admitted through it, and only as
diagnosis. It crosses immutable and detached from every provider carrier, is
reachable by explicitly asking an issue for it, and is excluded from default
renderings, exception messages, lifecycle events, SQL emissions, default logging,
and automatic formatting. It confers no write, repair, observation, key,
physical-address, raw-row, or privileged-storage authority: handing it to an
ordinary write is an ordinary validated write, and it is never a cursor, a
managed value, a predicate literal, or a repair token. The decoding cause that
produced it stays unpublished, so the code vocabulary remains the whole public
classification. Every other constraint here stands unchanged.

An `InvalidData` record carries the issue frozenset, optional hydrated root,
optional result-root `ObjectKey`, optional observed version, optional milestone `Edge`,
and its always-present zero-based result ordinal. Version and Edge are mutually
exclusive. These fields distinguish repeated versioned and temporal results for
diagnosis but do not constitute an internal `ObservedStateKey` or grant write
authority.

Python's default eager view raises `InvalidDataError(RuntimeError)`, whose sole
machine-readable report is the nonempty result-ordered
`invalid_data: tuple[InvalidData[object], ...]`. It exposes no singular code,
flattened issue collection, duplicate records alias, or decoding cause; its message is
a derived summary.
