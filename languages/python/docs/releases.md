# Release notes

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
