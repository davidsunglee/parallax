# A temporal table's physical key uses the axis end columns

A temporal table's Physical Primary Key is its model primary key plus each As-Of
Axis's **end** Attribute in canonical dimension order — `(id, thru_z, out_z)`
for a Bitemporal Entity, `(id, out_z)` for a Transaction-Time-Only one. It was
previously composed from each axis's start Attribute.

The end columns are the ones the engine's own SQL pins. Latest is spelled as an
equality on the exclusive upper bounds — `thru_z = ? and out_z = ?`,
`out_z = ?` for an audit-only read — and a Milestone Target addresses the row to
close by the primary key plus one exclusive upper bound per axis. A start-keyed
index contributes one usable column to those predicates and then scans every
milestone of the business key; an end-keyed one makes both the dominant read and
every close a key hit.

Uniqueness is preserved because at most one milestone per business key is open
on all axes at once: two rows of one key that share every end value would have
to be the same milestone. The corpus's hardest fixture confirms it —
`DepositRate`'s two Transaction-Time milestones for one key are
`(1, ∞, 2024-02-01)` and `(1, ∞, ∞)`, distinct under `(id, thru_z, out_z)`.

The same key makes one corruption unconstructible. A close addresses its
Milestone Target by the primary key plus one exclusive upper bound per axis,
which is now exactly the physical key, so no out-of-band insert can leave a
correctly addressed close matching two rows — storage refuses the second current
milestone of a key the way the temporal invariant always did. The excess side of
ADR 0044's cardinality expectation stays specified and stays reachable, since
corruption can arrive from a writer that never went through Parallax, but it can
no longer be staged through storage, so the compatibility case that staged it by
inserting a second current milestone was retired rather than rewritten around a
constraint whose purpose is to forbid its premise.

Reladomo composes its generated DDL key the same way, appending each as-of
attribute's `to` column to the declared key and never its `from` column, so
`TINY_BALANCE_PK` is `(BALANCE_ID, THRU_Z, OUT_Z)`. Its rationale is the same
operational one: every chained mutation closes the row whose `to` is infinity,
so `to` is the discriminator the WHERE clause must pin.

Nothing else moves. The four temporal columns keep their canonical positions in
the physical column sequence and their `not null` answers, which come from
declared nullability rather than key selection. The identity map is unaffected:
its interning key is `(family, primary key, lowered as-of coordinate per axis)`
computed from the declaration, and it never reads index metadata. Read
projection order — `from_z, thru_z, in_z, out_z` — is a Column Tier
consequence and does not follow the key.

The alternative of keeping the key start-composed and adding a second, end-keyed
unique index was rejected: it costs two indices and two write-time maintenance
paths per temporal table, and it leaves `<table>_pk` naming something that is
not the primary key.
