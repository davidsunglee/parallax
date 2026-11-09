# Release notes

## Unreleased

These changes are not part of any published release.

`pin_of` now accepts a Wire node as `edge_of` does: any node a Wire read published,
direct or projected, answers the `Pin` its read retained, with no I/O and no write
authority. A non-temporal node raises `snapshot-pin-unavailable`, and anything no read
published raises `snapshot-node-required`.

`read_rows` is gone from `ScopedDatabase`, `TxnContext`, and `ReadOnlyTxnContext`, and
`parallax.core.read_delivery` no longer exports `RowsResult` or `PublishedRow`. Migrate
each read to `find` for Typed nodes or `wire.find` for canonical published mappings.
Wire nodes are keyed by logical member name rather than by storage column: read
`node["payload"]`, not `row["payload_hex"]`. Their values are canonical Wire spellings
rather than native Python values. Both reads project the Entity's Value Objects, so a
row whose Value Object holds invalid stored data now arrives as `InvalidData` where
`read_rows` never looked at it, and either read inside a transaction can retain Read
Evidence where `read_rows` retained none.

`parallax.snapshot.WireValue` is now `parallax.core.wire.WireValue`. Its object member is
`Mapping[str, WireValue]` rather than `dict[str, WireValue]`, so an immutable mapping
type-checks where a `WireValue` is expected, and code that treated a value as a `dict`
statically needs a `Mapping` annotation or a narrowing check. Runtime values are
unchanged.

Typed include paths now reach any depth the read engine supports:
`Ticket.parking.vehicle.dealer` authors and executes with dotted syntax, and each
name past the first relationship is resolved against the serving model's Entity
Classes when an operation binds the query. One- and two-hop class-backed includes
need no migration.

A Typed include that continues past its first relationship now needs a class-backed
serving model. On a model built without Entity Classes, such a path passed to
`db.wire.find(...)` raises `UsageError(query-expression-invalid)` instead of
composing a canonical spelling from Python names. Migrate those reads to a canonical
Wire query, which states each segment's owner. Includes of a single relationship and
canonical Wire input are unaffected.

A continuation naming no relationship of the class it reaches now raises
`UsageError(query-path-invalid)` before I/O, in place of the `ValueError`
that composed spelling reached at the read gate. Stream reads report it on entry.

`view` and `is_view_loaded` now find a narrowed view by the key the read planned, so
a path narrowed to an abstract Entity, or to a concrete sharing its local name with
another in its family, reads the view its include loaded instead of reporting it
unloaded. A retained node answers under the Model Edition that published it.

`parallax.core.db_port.JsonDocument` is removed. A database adapter now receives a
structured-document bind as `StructuredDocument`, exported from the same module,
and reads its value from `document` rather than `value`. SQL NULL still binds as a
bare `None`.

Starting with `0.2.0`, Parallax no longer supports Intel macOS or musl Linux, including
Alpine, and publishes no `parallax-postgres` wheels for them. Published `0.1.0` wheels
remain available. Move Intel macOS deployments to a supported host and Alpine
deployments to a glibc-based Linux environment. Building from source on a removed
platform does not make it supported.

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
