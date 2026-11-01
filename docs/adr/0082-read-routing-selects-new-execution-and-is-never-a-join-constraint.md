# Read routing selects new execution and is never a join constraint

This supersedes the forecast in
[ADR 0065](0065-boundary-option-defaults-belong-to-the-database-root.md) that
reader/writer routing would be a **constraint**, always effective and always
compared on a join. The rest of ADR 0065 — the option defaults, their
field-wise resolution, and read-only execution's place in its taxonomy —
stands.

Read routing is its own dimension, carried beside the transaction options and
execution authority rather than inside either (`m-execution` *Read routing*). A
root and every scope carry one read policy — `writer-only`, `reader-only`, or
`reader-preferred` — that new execution requests: a standalone read, row read,
or stream page, and each attempt of a new read-only transaction. A writable
transaction always requests the writer. Work joining an active transaction runs
on that attempt's connection, so it neither consults nor compares the joining
scope's routing, and routing can never make a join conflict. A scope-level read
inside a callback stays standalone and honors its own scope's policy.

Policies and routes are two vocabularies. A runtime declares the routes it
serves — `writer` always, `reader` optionally — by what a caller can observe
there rather than by topology (`m-db-port`), and a policy names how an
acquisition chooses among them. A policy no declared route can honor is refused
where it is named, without I/O. An operation that fell back from the reader
stays on the writer for every later page or permitted retry.

A join constraint was rejected because the active transaction already fixes the
connection, and with it the route, before any joining call arrives. Comparing
the joiner's routing could only refuse joins over a choice that is no longer
open, so a request-scoped `writer-only` view could not call into code that opens
its own transaction through a reader-defaulted root. Folding routing into the
options record was rejected for the same reason in the other direction: options
are resolved once for an invocation and compared on joins, while routing is
requested per acquisition and may move to the writer between them.
