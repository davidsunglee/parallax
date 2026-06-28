# JSON serialization produces domain snapshots

Managed TypeScript domain objects are not plain JavaScript objects, so serialization is a first-class API. `JSON.stringify` produces a synchronous scalar-only shape without lazy-loading relationships, while async snapshot APIs can select attributes with `attributes`, exclude default attributes with `excludeAttributes`, and opt into relationship paths with `relationships`.

Snapshot output includes all scalar and value-object attributes by default and no relationships by default. `attributes` and `excludeAttributes` are mutually exclusive, relationship paths are opt-in, and there is no `excludeRelationships` option because omitted relationships are already excluded.

Async snapshot APIs may lazy-load requested relationship paths because the caller explicitly asked for them. List-level snapshot serialization should batch-load requested relationship paths where possible, equivalent to query includes, so common REST collection serialization does not devolve into N+1 queries.
