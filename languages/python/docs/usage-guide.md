# Parallax Python — Usage Guide

The usage guide is now the [Parallax Python Guide](guide/README.md). Its chapters are:

- [Getting started](guide/01-getting-started.md): installing, creating tables from a
  model, connecting, choosing an Execution Scope, and a first write and read.
- [Modeling](guide/02-modeling.md): entities and keys, relationships, value objects,
  inheritance families, temporality profiles, optimistic-lock versions and storage
  layouts.
- [Reading and querying](guide/03-reading.md): predicates, ordering, relationship
  quantifiers, subtype narrowing, optional relationships, streaming, as-of reads, read-only
  transactions and Wire publication.
- [Writing](guide/04-writing.md): inserts, keyed amendments and deletes, unversioned
  writes, Bitemporal `amend ... until`, target writes, predicate writes and Wire writes.
- [Transactions](guide/05-transactions.md): running and joining transactions, isolation
  levels, optimistic and locking concurrency, retries, and option defaults.
- [Execution authority](guide/06-execution-authority.md): running work as the service
  login or as an application user under a database role, credentials that refresh per
  connection, and which actor a transaction keeps.
