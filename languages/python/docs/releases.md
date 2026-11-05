# Release notes

## Unreleased

These changes are not part of any published release.

Typed include paths now reach any depth the read engine supports:
`Ticket.parking.vehicle.dealer` authors and executes with dotted syntax, and each
name past the first relationship is resolved against the serving model's Entity
Classes when an operation binds the query. One- and two-hop class-backed includes
need no migration.

A Typed include that continues past its first relationship now needs a class-backed
serving model. On a model built without Entity Classes, such a path passed to
`db.wire.find(...)` raises `QueryDefinitionError(query-expression-invalid)` instead of
composing a canonical spelling from Python names. Migrate those reads to a canonical
Wire query, which states each segment's owner. Includes of a single relationship and
canonical Wire input are unaffected.

A continuation naming no relationship of the class it reaches now raises
`QueryDefinitionError(query-path-invalid)` before I/O, in place of the `ValueError`
that composed spelling reached at the read gate. Stream reads report it on entry.

`view` and `is_view_loaded` now find a narrowed view by the key the read planned, so
a path narrowed to an abstract Entity, or to a concrete sharing its local name with
another in its family, reads the view its include loaded instead of reporting it
unloaded. A retained node answers under the Model Edition that published it.

`parallax.core.db_port.JsonDocument` is removed. A database adapter now receives a
structured-document bind as `StructuredDocument`, exported from the same module,
and reads its value from `document` rather than `value`. SQL NULL still binds as a
bare `None`.

## 0.1.0

First coordinated release for early adopters.

The release includes the common runtime, Snapshot application API, PostgreSQL
adapter, model evolution and schema deltas, descriptor interchange, and optional
AWS credential providers. The conformance distribution remains unpublished.
Install the packages your application needs using
[Getting started](guide/01-getting-started.md#install).

The public baseline includes immutable Typed and Wire query results, explicit
transactions, bounded conflict retries, optimistic and locking writes, temporal
history, model evolution and explicit database resource ownership. The
[Python binding](../spec/python.md) and executable guide define the supported
surface, including the implemented errors and temporal-bound interfaces.

The [compatibility and maintenance policy](releasing.md#compatibility-and-maintenance)
explains coordinated versions, backward-compatible patch releases, migration
guidance for breaking pre-1.0 minor changes and newest-minor-only maintenance.
Environment support is declared by the metadata and binding links in
[Getting started](guide/01-getting-started.md#install).

All production wheels and sdists carry the Apache-2.0 licence and attribution
notice. See the [repository licence](../../../LICENSE).
