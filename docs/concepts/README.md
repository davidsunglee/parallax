# Concepts

These pages explain how Parallax behaves and why, in the domain terms of the
[glossary](../../GLOSSARY.md), with the common cases each feature is for. They are
shared by every language implementation and explain rather than specify: the
[core specification](../../core/spec/00-overview.md) owns the exact contracts, and each
page links the part it explains. Each page ends with links into the
[Python Guide](../../languages/python/docs/guide/README.md) for doing it.

- [The read flow](read-flow.md): how an Object Query becomes immutable values, where
  eager and streamed delivery share the work and where they part, and which reads can
  license a later write.
- [The write flow](write-flow.md): how a write is judged, licensed, combined with the
  transaction's other writes and turned into statements, and why a keyed write that
  cannot show what it overwrites is refused.
- [The temporal model](temporal-model.md): Transaction Time and Valid Time, the
  milestones that record history, and how a temporal write composes over coverage.
- [Transactions, concurrency and retry](transactions.md): invocations and attempts,
  why a keyed write needs a licence, how one preference becomes a strategy per Entity,
  what each isolation level promises, which failures are retried, and what joining a
  transaction means.
- [Execution authority and audit](execution-authority-and-audit.md): who a database
  operation runs as, why that is chosen once per scope, how it reaches the database, and
  what audit provenance is reserved to record.
- [Model evolution](model-evolution.md): Model Editions and how every execution adopts
  one, how a change between two models is described and classified, why the application
  applies migrations, and what two editions serving one database must agree on.
