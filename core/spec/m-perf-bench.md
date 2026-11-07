# m-perf-bench — Shared Performance Workloads

`m-perf-bench` owns portable performance workload definitions: the model,
deterministic dataset, Object Query, and delivery page sizes an implementation
measures through its own execution path. It depends on `m-case-format` for
canonical dataset row identities and on `m-object-query` for the query envelope.

## Workload fixtures

A workload fixture is a YAML document under `core/compatibility/benchmarks/`.
It MUST carry:

- `tags`, including `m-perf-bench`;
- `model`, a descriptor path relative to `core/compatibility/`;
- `dataset`, either inline `rows` keyed by canonical Entity spelling or a
  `generate` mapping naming a deterministic `recipe`, positive `rows` count,
  and positive `fanout` where the recipe has child rows;
- `objectQuery`, the canonical Object Query the implementation executes;
- `delivery.pageSizes`, the positive page sizes at which streamed delivery is
  measured beside eager delivery of the same result.

A target's own measurements MUST use the fixture's recipe, `objectQuery`, and
`delivery.pageSizes`, and MUST preserve the selected dataset's Entity counts,
parent-child fan-out, key relationships, traversal order, and fixed member values.
A target
MAY construct rows lazily and use host-native carriers after canonical Wire
conversion. Any deterministic key translation used for provisioning MUST
preserve relationships and ordering, and be identified in workload provenance.

## Deterministic dataset recipes

Each emitted row contains exactly the listed members; a model member not listed
is absent. The fixture fixes the scale; the recipe fixes the shape and values.

- `orders-tree` emits Orders for `id = 1..rows`. Their `name` is
  `order-<id>` with the decimal ID zero-padded to six digits; `sku` is `A-100`,
  `qty` is `5`, `price` is `10.50`, `active` is true, and `orderedOn` is
  `2024-01-05`. Each Order emits `fanout` OrderItems in parent-then-child
  order, with independently sequential IDs, the parent `orderId`, `sku` `SKU`,
  `quantity` `1`, and `shippedOn` `2024-02-01`. Each item likewise emits
  `fanout` OrderStatuses with independently sequential IDs, its Order's
  `orderId`, its parent `orderItemId`, and `code` `OPEN`.
- `travelers-tree` emits Travelers for `id = 1..rows`: `displayName` is
  `traveler-<id>`, `score` is `id`, `joinedOn` is `2026-01-15`, `note` is
  `note-<id>`, `address` is `{city: Oslo, geo: {country: NO}}`, and `tags`
  contains `fanout` documents `{label: tag-<offset>}` for zero-based offset.
  It also emits `fanout` Trips per Traveler in parent-then-child order: IDs are
  global and sequential, `travelerId` is the parent ID, `destination` is
  `destination-<offset>`, and `nights` is `offset + 1`.
- `versioned-documents` emits Ledgers for `id = 1..rows`: `version` is `1`,
  `label` is `ledger-<id>`, `balance` is `10.00`, and `details` is
  `{code: OPEN}`.
- `bitemporal-current` emits Charters for `id = 1..rows`: `route` is
  `route-<id>`, `terms` is `{clause: standard}`, both `validStart` and
  `txStart` are `2026-01-01T00:00:00+00:00`, and both `validEnd` and `txEnd`
  are `infinity`.
- `materialization-stress` emits Owners for zero-based `index = 0..rows-1`.
  The Owner's `id` is `1000 + index`, `name` is `owner-<index>`, and
  `favoriteId` is `10000 + index * 10`. Each Owner emits `fanout` Nodes for
  zero-based `offset`: `id` is `favoriteId + offset`, `ownerId` is the
  Owner ID, `label` is `node-<index>-<offset>`, and `tags` is empty. Offsets
  below `2` are Alpha and the rest Beta; offset `0` is the favorite.
- `customer-locations` emits Customers for `id = 1..rows`: `name` is
  `customer-<id>` and `address` is null. Each Customer emits `fanout`
  Locations and `fanout` Depots in parent-then-child order, each Entity with
  independently sequential IDs and the parent `customerId`, for zero-based
  `offset`. A Location's `label` is `location-<offset>` and its `address` is
  `{street: <id> Quay, city: Oslo, geo: null, phones: []}`, except that a
  Location whose ID is a multiple of 10 omits `street`, which its model
  requires, so every tenth Location is stored data a read classifies as
  invalid. A Depot's `label` is `depot-<offset>` and its `address` is
  `{line: line-<offset>, postcode: "0150"}`.

## Measurement ownership

Each language target owns its measurement protocol, sampling, numeric targets,
report format, instruments, and execution environment. It MUST identify the
workload inputs and measured production path so comparisons can distinguish
changed work from changed implementation cost. Live database delivery and
provider-free execution windows MUST be distinguishable in its evidence.

The shared workload definition does not establish a common timing or memory
unit across runtimes. Comparisons MUST state their measurement boundaries,
units, runtime/environment differences, and sampling limitations. Correctness
and Database Call discipline remain compatibility properties graded against
independent expectations; performance observations do not replace them.
