# Transactions are callback-only; all writes happen inside one

The only transaction demarcation is `db.transact(fn, ...)`; no context-manager
form ships, the handle has no write methods, and `db.transact` inside a
transaction body joins the active transaction. The core unit-of-work boundary
MUST offer bounded automatic retry defined as re-executing the closure against
fresh state — a Python `with` block cannot be re-executed, which is why
Django's `transaction.atomic` and SQLAlchemy's `session.begin` offer no retry
and their ecosystems bolt it on by wrapping the body in a callable anyway
(CockroachDB's `run_transaction`, Spanner's `run_in_transaction`). Offering a
`with` form alongside would make the most familiar spelling the semantically
weaker one.

Requiring the transaction for every write is principled for this slice
because temporal writes are multi-statement by definition (close-and-chain,
rectangle split), and every claimed write semantic — buffering, batching,
FK ordering, read-your-own-writes, abort, value-withheld-on-commit-failure,
retry — is defined at the boundary. The one-off cost is a single lambda:
`db.transact(lambda tx: tx.insert(order))`. Reladomo permits implicit
per-operation transactions; we deliberately do not. A decorator form is a
possible additive extension.

Nested calls join the active transaction, as Reladomo and the TypeScript
target do (TS ADR 0022; repo ADR 0005): the inner closure receives the same
transaction — no savepoint, no independent commit — and commit, abort, and
the bounded retry loop belong to the outermost boundary only, so an inner
failure aborts the whole transaction and an inner body re-executes only as
part of the outermost retry. Raising on nesting was considered and rejected:
it breaks transaction-owning helpers composing into larger transactions while
adding no safety (independent inner commit is the ambiguity, and joining
removes it). A joining call cannot re-negotiate the boundary — an explicit
`concurrency` differing from the active mode raises, and explicit `retries`
or `retry_optimistic_conflicts` arguments on a joining call raise; omitted
arguments join the active settings.
