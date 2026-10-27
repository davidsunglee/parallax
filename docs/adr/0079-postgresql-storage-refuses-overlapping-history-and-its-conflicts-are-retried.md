# PostgreSQL storage refuses overlapping temporal history, and its conflicts are retried

This refines ADR 0078 and supersedes its second layer of enforcement, the
in-statement guard on caller-keyed new lineages, as a decision for now. The
other two layers stand: a close must follow its predecessor's stored
Transaction-Time start, and PostgreSQL tables Parallax generates constrain
interval validity and equal-key non-overlap natively.

Every temporal table Parallax generates on PostgreSQL carries an immediate,
non-deferrable GiST exclusion: no two rows of one logical key overlap on every
axis at once (`m-storage-layout` *Temporal history constraints*;
`m-schema-delta` *Temporal constraints*). It refuses a superset of what the
lineage guard would have: a reinsertion behind a terminated milestone, an insert
over current coverage, and two transactions filling one gap, from Parallax and
from any other writer. The guard's own value on such a table would be an
earlier, typed refusal, and it would be the only protection for MariaDB and for
tables not yet migrated. That value did not justify its cost now: every
caller-keyed insert would change its statement form, the probe's access path was
unproven, write groups would carry contribution facts through many modules, and
separating caller, derived, and mixed inserts could split a 64-row batch into as
many statements. It is deferred, with statement-aware error translation and a
typed coverage-exists error, to a separate decision.

Without attribution, the exclusion's refusal cannot tell a caller's mistake from
a race. A violation of the failing statement's own table exclusion is therefore
a recoverable conflict, recognized by the exact compiled name and the exclusion
failure kind and retried as a new attempt (`m-auto-retry`). The caller still
sees the original database error, never a translated one. Races and clock-behind
reinsertions recover with no new user-visible error. The accepted cost is that a
refusal no retry can resolve — an insert over coverage that is already current
with a different Valid-Time end, or a planner defect — spends the whole retry
bound before it surfaces. A primary-key duplicate, a check, a lock-wait timeout,
and an exclusion of any other name keep their categories' policy.

Deferring enforcement to commit was rejected: each statement of a flush must
leave history legal, which Parallax's statement order provides, and a deferred
failure would lose the statement it came from. A runtime switch, schema
discovery at connect, and automatic migration of existing tables were rejected
as in ADR 0078. Existing tables adopt the constraints through a documented
manual migration.
