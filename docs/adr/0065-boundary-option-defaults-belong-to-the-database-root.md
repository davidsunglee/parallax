# Boundary option defaults belong to the Database Root

The four transaction options — the retry bound, the Concurrency Preference,
the optimistic-conflict retry opt-in, and the Isolation Level — are configured
as defaults on the Database Root, the configured owner of one runtime. The root
is connected with one immutable options record; a derived Execution Scope
carries one complete effective record after any scope-level patches. An outer
transaction resolves each option as its explicit argument, else the invoking
scope's effective value; every physical attempt and every joining call observes
the invocation's resolved record; and the transaction exposes that record, of
the same type the root and scope carry, so a joiner or a component reads one
value. The root's built-in record is
ten re-executions, the optimistic preference, the conflict opt-in off, and Read
Committed.

Only omission inherits. An omitted argument on an outer call takes the invoking
scope's effective value and an omitted argument on a joining call takes the active
transaction's resolved value; an explicit value is held to its field's
contract — a nonnegative integer that is not a boolean, a boolean, a member of
the closed vocabulary — and `null` is an invalid value for every field rather
than a second spelling of omission. Joins keep the rule ADR 0005 and the
per-option decisions since it established: an explicit value equal to the
active resolved value is accepted, a different one is refused before the joined
callback runs. Neither the invoking scope's effective defaults nor the root
record behind them participates in that comparison on its own, so a join naming
either value under an outer call that overrode it is a conflict.

Read Committed is a concrete default, not the absence of a request. An
scope retaining an unconfigured root's record asks the port for Read Committed
on every attempt, even where
the database's configured default is stronger, because a default a transaction
inherits from the connection is a default for whichever transaction runs next
on it, and a level Parallax resolved is one it can report and compare. The
port's lower-level no-request form remains for callers below the root, and the
connection-intake floor of ADR 0061 is unchanged: a connection whose configured
default is weaker than Read Committed is still refused when the adapter takes
it, before any boundary asks it for anything.

The decision fixes a taxonomy the features that inherit it must keep. The
four options are **defaults**: configured on the root, partially patchable on a
derived scope, overridable per call, and compared on a join only when explicit.
Future **constraints** — read-only
execution, reader/writer routing — are always effective and always compared on
a join, so a configured view carrying one can do less than its root and never
more. **Execution authority** — which Principal runs and which database
privileges govern the operation — is a separate, mandatory dimension and never
a field of the options record. ADR 0066 introduces Execution Scopes and their
partial patches; this record supplies the complete root record and field-wise
resolution rule those scopes compose over.

Two alternatives were rejected. A nullable isolation default, with `None`
meaning "ask for nothing", would make the record incomplete, force every join
to compare an explicit level against an absence, and hide a stronger configured
database default behind a resolved-looking record. A second, transaction-local
options representation beside the root record would duplicate the same four
fields, and an omission marker inside the record would make every reader check
for it; instead one record type holds concrete values everywhere and omission
lives only in the transaction keyword, as a private typed marker the runner
resolves before anything is opened.
