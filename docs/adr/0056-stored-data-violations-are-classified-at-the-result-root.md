# Stored-data violations are classified at the result root

A read represents stored state that violates the accepted model as an ordered
root-level `T | InvalidData[T]` union. Any issue in a root's requested include
tree classifies that root as `InvalidData`; the record carries every
deterministically ordered `StoredDataIssue` and carries the hydrated root only
when hydration requires no invented value. Ordinary result access raises with
the same complete records, while a checked view returns the union; neither view
silently drops, repairs, or publishes a node-level invalid value. This preserves
root position and atomic graph publication while allowing diagnosis and
caller-authored remediation, unlike fatal decoding, a delayed side collection,
node-level unions, pruning, or silent inclusion.
