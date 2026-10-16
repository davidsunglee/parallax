# Internal optimistic conflicts replay automatically

An Optimistic Lock Conflict Error — a gate bound to an observation of the
attempt that came up short because a concurrent writer moved the row first — is
a recoverable conflict, replayed by the bounded retry loop on the same terms as a
deadlock or serialization failure. No option selects which failures are
replayed: `retryOptimisticConflicts` is gone from the root defaults, the
invocation, and the join. `max_retries` remains the only control, and `0` still
runs the callback once.

The opt-in made the same lost update surface or replay depending on the
isolation level. At Read Committed a stale gate matches no row and raised the
conflict, which surfaced unless the caller opted in; at Repeatable Read the same
schedule fails as a serialization error, which was always replayed. Since source
writes are admitted only by a read of the current attempt
([ADR 0072](0072-source-writes-are-admitted-only-by-a-read-of-the-current-attempt.md)),
every gate that can come up short binds a revision the replay reads again, so a
replay rebuilds the work from fresh state rather than repeating a stale write. A
caller holding an earlier observation states it through a caller-addressed
write, whose failed precondition stays terminal because a replay restates the
same revision.

The boundary classifies an attempt's failure once, after its rollback, and the
attempt reports that verdict while the loop acts on it. Replaying conflicts
immediately lets contending invocations collide again, so the loop waits a
bounded randomized delay before each re-execution, only after the failed attempt
has released its connection. The delay's window scales with the failed
attempt's own measured duration, within absolute bounds: how long a conflicting
writer holds its rows depends on round trips and application work that a delay
fixed in milliseconds cannot anticipate, and with no public setting a caller
could not correct one for their environment. Its timing is internal policy
selected from contention evidence rather than a public setting.

This supersedes the opt-in clause of
[ADR 0008](0008-unit-of-work-retry-is-bounded-and-automatic.md): optimistic
conflicts no longer surface by default. ADR 0008's bounded, automatic,
rollback-and-replay loop stands.

Alternatives considered: keeping the opt-in, which keeps isolation-dependent
treatment of one lost update; surfacing every conflict to the caller, which
ADR 0008 already rejected for transient failures and which now has no
caller-held revision to protect; and a delay fixed in milliseconds, which suits
only the environment its constants were measured in.

The contract lives in `core/spec/m-auto-retry.md` and `core/spec/m-opt-lock.md`
(*Retry contract*).
