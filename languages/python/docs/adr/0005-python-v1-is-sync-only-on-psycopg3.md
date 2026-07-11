# Python v1 is sync-only on psycopg 3

The v1 developer surface is synchronous: `db.find` and `db.transact` block,
and the driver is psycopg 3 in sync mode. A dual sync/async surface would
double the API Conformance Suite, Usage Guide, and no-drift wiring for zero
additional conformance credit, and async-only would tax every non-async
context (scripts, notebooks, the CLI conformance adapter) while coloring
every documented example. Async apps bridge with `asyncio.to_thread`
meanwhile.

psycopg 3 is chosen specifically because it keeps async additive: one driver
with sync and async connection classes sharing SQL, binds, and error
semantics, so a future `AsyncHandle` extension reuses the dialect strategy,
error mapping, and the entire I/O-free statement/serde/SQL-generation stack
unchanged. "Async developer surface" is recorded as a deferral in the
language spec, not a rejection.
