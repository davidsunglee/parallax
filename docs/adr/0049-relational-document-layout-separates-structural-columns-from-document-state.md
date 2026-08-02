# Relational Document Layout separates structural columns from document state

Parallax supports a root-owned Relational Document Layout in which each
governed relational Table retains direct columns for primary keys, both
Relationship Join endpoints, temporal bounds, Audit Attributes, explicit
Non-Temporal optimistic locking, and the table-per-hierarchy variant tag, while
one required Structured Column contains every other Entity Attribute and
top-level Value Object. PostgreSQL realizes that column as `jsonb` and MariaDB
as `json`; the stored object remains a relational row and this decision does not
introduce Document Collection semantics.

This closed structural role set keeps joins, referential DDL, temporal
addressing, optimistic gates, and Audit Provenance relational without turning
layout into an unbounded per-member placement language; `m-storage-layout` owns
the resulting placements, and selecting or changing the layout remains an
external schema migration rather than a runtime dual-layout protocol.
