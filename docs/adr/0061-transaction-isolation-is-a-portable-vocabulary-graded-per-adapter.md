# Transaction isolation is a portable vocabulary graded per adapter

Parallax names three Isolation Levels — Read Committed, Repeatable Read, and
Serializable — as one portable vocabulary carried from the transaction option
through the database port to every adapter. Each level is defined by the
anomalies it forbids, not by any vendor's implementation, and each adapter maps
the requested level to whatever its database needs to forbid those anomalies
for exactly one Transaction Attempt. An adapter that cannot forbid them reports
a Boundary Failure rather than opening the attempt at a weaker level. Omission
requests nothing and keeps the adapter's own default; Read Uncommitted and
vendor-specific levels are not portable and are refused at the option.

This lifts a deliberate deferral. The port previously carried the caller's
string in the concrete database's own spelling and defined no vocabulary, so
that no level's behavior had to be graded before an adapter existed to grade
it. That stance could not survive a second database: MariaDB's Repeatable Read
is a session variable choreographed around each attempt, not a spelling, so an
adapter must interpret the request either way. Keeping the vocabulary at the
port gives the Transaction Invocation descriptor, logs, errors, and
compatibility cases one set of names, and puts the mapping where it is graded.

The alternatives were an execution-surface translation to dialect strings, which
cannot express MariaDB's choreography and would spread level knowledge across
the dialect module and every adapter, and a portable value beside a native
escape string, which would put two vocabularies through one option with graded
semantics for only one of them.

*Superseded in part (2026-10, [ADR 0065](0065-boundary-option-defaults-belong-to-the-database-root.md)):*
omitting the isolation keyword no longer requests nothing. The transaction
inherits the Isolation Level of its scope's options record, which the Database
Root defaults to Read Committed. The portable vocabulary and its per-adapter
grading stand.
