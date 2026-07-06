# m-cascade-delete — Cascade Delete

`m-cascade-delete` specifies the **minimal dependent cascade-delete witness**:
deleting an owning root deletes its dependent child rows before the root row. Per
the dependency graph, `m-cascade-delete` depends on `m-op-list` and `m-unit-work`
— it is layered *above* lists (it traverses dependents) so the graph stays
acyclic.

## Minimal dependent cascade-delete witness

The compatibility corpus includes one **minimal `cascadeDelete` witness** over an
`m-descriptor` `dependent: true` relationship graph. The case is intentionally
narrow: deleting an owning root deletes dependent child rows **before** the root
row, then asserts the remaining table state. It pins the observable dependent-delete
ordering without claiming support for Reladomo's full cascade surface.

The witness reuses the `m-case-format` `writeSequence` shape. Its `cascadeDelete`
mutation name documents intent; the harness applies the authored ordered DML and
compares the resulting rows.

## Beyond current scope

Broad cascade — `cascadeInsertAll` / `cascadeDeleteAll` / `cascadeTerminateAll`,
which walk **dependent** relationships across the full Reladomo API surface — is
out of scope for this revision. It is named here so the module boundary is clear;
its golden-SQL forms and fixtures land with the cascade fast-follow, apart from the
minimal witness above.
