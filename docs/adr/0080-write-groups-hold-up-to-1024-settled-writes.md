# Write Groups hold up to 1,024 settled writes

A Write Group now holds at most 1,024 settled writes rather than 64, and lays
its effects out shape by shape (`m-unit-work` *Write Group formation*). This
supersedes two parts of
[ADR 0076](0076-write-groups-run-every-effect-before-any-insert.md): its
64-write bound, and its statement that an effect never moves past another
effect. Every effect still runs before any insert, each write's own steps keep
their order, and ADR 0076's reasons for bounding a group at all stand.

When ADR 0076 chose 64, a group's effects reached the database through ordered
transport, so the bound changed how many calls a flush made but not how many
statements it ran. Compatible effects of one group now execute as one
array-bound statement per effect shape, so the bound decides how many
statements a run of like writes costs: a 1,000-object amendment of one shape
was sixteen groups and becomes one grouped statement, two where each write also
inserts its successors. Paired measurements against PostgreSQL found 1,024
faster than 64 at that size, and faster than or within noise of 256, over
loopback and over a relayed connection, with no slowdown for flushes of a few
objects.

Compatible effects share a statement only if they are contiguous, so an effect
may now move past another object's effect of a different shape: effects of
distinct objects can run out of authored order across shapes. An effect that
assigns a unique key member other than the primary key keeps its authored
place, because a unique value one object hands another must be released in
order. A grouped effect's statement failure can therefore overtake another
object's refused gate, which widens the failure precedence ADR 0076 accepted
(`m-execution` *Flush execution*).

The accepted cost of the larger bound is the one ADR 0076 bounded. A failing
insert waits behind the effects of up to 1,024 settled writes, which have
already executed and hold their locks, and a group's grouped statement carries
the cells of that many writes at once. The attempt is doomed either way, so
correctness does not depend on the bound, and a grouped statement gathers each
write's cells as the write is appended rather than retaining every write's
prepared payload. The bound remains the planner's own constant: execution's
per-call statement and row caps, and the acquisition span's bound, are
unchanged, so a dialect without array binds still presents a group's effects in
ordered invocations of at most 64 statements.

256 was rejected: it caps what a failing insert wastes at a quarter of 1,024's,
but costs a 1,000-object amendment four statements, or eight with successor
inserts, and was nowhere measurably faster. An unbounded group stays rejected
for ADR 0076's reason.
