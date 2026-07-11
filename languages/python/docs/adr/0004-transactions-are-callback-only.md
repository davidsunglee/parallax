# Transactions are callback-only; all writes happen inside one

The only transaction demarcation is `db.transact(fn, ...)`; no context-manager
form ships, the handle has no write methods, and `db.transact` inside a
transaction body raises rather than nesting. The core unit-of-work boundary
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
per-operation transactions; we deliberately do not. A decorator form and
re-entrancy semantics are possible additive extensions.
