---
date: 2026-09-15
git_commit: 681ce91fa06f185ee57ebe8889ccd4445d4c86cc
topic: "Parallax eager and streamed delivery at 681ce91f against SQLAlchemy 2.0.52"
type: research
tags: [research, benchmark, performance, memory, streaming, sqlalchemy, parallax]
status: complete
---

# Parallax vs SQLAlchemy Delivery, 2026-09-15

## Summary

Parallax at `681ce91f` closed most of the gap to SQLAlchemy 2.0.52 on the one
shape the original comparison treats as a fair implementation calibration,
conventional fan-out, moving from 2.01× to 1.32× of SQLAlchemy's eager wall
time. Parallax now streams duplicate-include graphs faster than SQLAlchemy,
publishes its first root sooner than SQLAlchemy on every shape except
conventional fan-out, and peaks below SQLAlchemy's traced Python memory on
every eager and streamed shape. The versioned and bitemporal ratios shrank but
remain the largest, and the original caveat stands: those SQLAlchemy cells omit
Source Hints, write evidence, and temporal edges, so they are upper bounds on
implementation opportunity rather than targets.

The SQLAlchemy columns are the 2026-09-11 figures unchanged. Nothing on that
side moved, so it was not rerun.

## Conditions

Both runs used CPython 3.14.7 on darwin/arm64, PostgreSQL 18.6 in
Testcontainers through the `pg-full` profile, 200 roots, fan-out four, and
page sizes 1, 8, 32, and 128. Timings are medians of five live operations
after three warm-ups, or ten provider-free operations. Wall time includes
provider wait; CPU time is process CPU. Memory is `tracemalloc` over Python
allocations only, started after database and model preparation, reporting
retained, transient, and peak bytes for one delivery. It excludes PostgreSQL,
driver-owned C buffers, and process RSS.

SQLAlchemy figures come from SQLAlchemy 2.0.52 with compiled extensions, a
fresh `Session` per operation, `selectinload` for relationships, and the ORM
`yield_per` option for streaming. Its bitemporal cell needed a custom
`timestamptz` infinity loader merely to read the same rows.

| Workload | Shape |
|---|---|
| conventional-fanout | Columns-layout Order roots plus one to-many include; 1,000 logical nodes |
| duplicate-include | The same graph with the same 800 children projected through two include paths; 1,800 projections merge to 1,000 logical nodes |
| document-heavy | Relational Document Layout Traveler roots, nested One/Many Value Objects, one to-many include; 1,000 logical nodes |
| versioned-document | Relational Document Layout Ledger roots carrying optimistic versions and retained write evidence |
| bitemporal-current | Current rectangles from a Bitemporal Position table, including both temporal edges |

## Primary comparison

Live PostgreSQL wall milliseconds. Stream rows use page size 32. First is the
time to the first root whose selected relationships are populated.

| Workload | Parallax eager 09-11 → 09-15 | SQLAlchemy eager | Parallax stream 09-11 → 09-15 | SQLAlchemy stream | Parallax first 09-11 → 09-15 | SQLAlchemy first |
|---|---:|---:|---:|---:|---:|---:|
| conventional-fanout | 17.25 → 11.28 | 8.57 | 29.62 → 16.97 | 8.60 | 3.31 → 1.23 | 1.54 |
| duplicate-include | 28.22 → 16.38 | 12.67 | 40.69 → 21.44 | 38.65 | 4.54 → 1.61 | 6.51 |
| document-heavy | 31.87 → 23.36 | 11.49 | 43.51 → 27.77 | 10.53 | 5.39 → 1.95 | 2.01 |
| versioned-document | 7.28 → 6.35 | 1.83 | 12.44 → 9.74 | 1.99 | 1.64 → 0.70 | 0.66 |
| bitemporal-current | 8.38 → 4.95 | 1.22 | 17.30 → 8.88 | 2.13 | 2.16 → 0.79 | 0.69 |

Parallax wall time as a multiple of SQLAlchemy's, eager / page-32 stream:

| Workload | 2026-09-11 | 2026-09-15 |
|---|---:|---:|
| conventional-fanout | 2.01× / 3.44× | 1.32× / 1.97× |
| duplicate-include | 2.23× / 1.05× | 1.29× / 0.55× |
| document-heavy | 2.77× / 4.13× | 2.03× / 2.64× |
| versioned-document | 3.98× / 6.25× | 3.47× / 4.90× |
| bitemporal-current | 6.87× / 8.12× | 4.06× / 4.17× |

## Page-size curve

Each cell is whole-delivery wall milliseconds / first-root milliseconds on live
PostgreSQL.

Parallax at `681ce91f`:

| Workload | Page 1 | Page 8 | Page 32 | Page 128 | Eager |
|---|---:|---:|---:|---:|---:|
| conventional-fanout | 128.34 / 0.63 | 33.56 / 0.82 | 16.97 / 1.23 | 11.86 / 2.47 | 11.28 / 11.28 |
| duplicate-include | 144.73 / 0.72 | 44.02 / 1.22 | 21.44 / 1.61 | 16.36 / 3.84 | 16.38 / 16.38 |
| document-heavy | 139.70 / 0.70 | 47.95 / 1.23 | 27.77 / 1.95 | 24.20 / 5.61 | 23.36 / 23.36 |
| versioned-document | 82.42 / 0.38 | 15.87 / 0.41 | 9.74 / 0.70 | 6.86 / 1.40 | 6.35 / 6.35 |
| bitemporal-current | 89.04 / 0.44 | 15.71 / 0.47 | 8.88 / 0.79 | 5.33 / 1.40 | 4.95 / 4.95 |

Parallax on 2026-09-11:

| Workload | Page 1 | Page 8 | Page 32 | Page 128 | Eager |
|---|---:|---:|---:|---:|---:|
| conventional-fanout | 490.44 / 2.44 | 63.85 / 2.28 | 29.62 / 3.31 | 24.57 / 8.71 | 17.25 / 17.24 |
| duplicate-include | 278.16 / 1.56 | 105.62 / 3.37 | 40.69 / 4.54 | 37.07 / 14.47 | 28.22 / 28.21 |
| document-heavy | 596.53 / 2.83 | 118.47 / 3.96 | 43.51 / 5.39 | 39.64 / 17.14 | 31.87 / 31.87 |
| versioned-document | 86.91 / 0.62 | 25.39 / 1.22 | 12.44 / 1.64 | 9.61 / 4.07 | 7.28 / 7.28 |
| bitemporal-current | 280.36 / 1.33 | 36.72 / 1.78 | 17.30 / 2.16 | 9.54 / 3.82 | 8.38 / 8.38 |

SQLAlchemy 2.0.52 on 2026-09-11:

| Workload | Page 1 | Page 8 | Page 32 | Page 128 | Eager |
|---|---:|---:|---:|---:|---:|
| conventional-fanout | 133.38 / 1.11 | 20.63 / 1.23 | 8.60 / 1.54 | 7.68 / 4.35 | 8.57 / 7.99 |
| duplicate-include | 245.32 / 1.62 | 36.69 / 1.87 | 38.65 / 6.51 | 21.95 / 12.77 | 12.67 / 11.94 |
| document-heavy | 155.66 / 1.22 | 24.54 / 1.44 | 10.53 / 2.01 | 11.32 / 6.41 | 11.49 / 10.39 |
| versioned-document | 19.88 / 0.52 | 3.70 / 0.63 | 1.99 / 0.66 | 1.49 / 0.86 | 1.83 / 1.46 |
| bitemporal-current | 20.59 / 0.59 | 3.54 / 0.59 | 2.13 / 0.69 | 1.75 / 1.02 | 1.22 / 1.02 |

Page-1 wall readings vary materially between container runs and should be
read as order of magnitude. Both systems remain round-trip dominated there.

## Statement topology

For a 200-root page-32 delivery, SQLAlchemy executes the root statement once
over an open server-side cursor and each relationship loader once per batch:
eight statements for conventional and document shapes, fifteen for duplicate
include, one for the single-table shapes. Parallax executes the root and every
include once per keyset page: fourteen, twenty-one, and seven respectively.
That difference is a contract, not only an optimization. Parallax's page
progression has an explicit continuation coordinate and releases each root
page before fetching the next.

## Memory

Page-32 readings, retained / transient / peak KiB.

| Workload | Parallax eager 09-11 | Parallax eager 09-15 | SQLAlchemy eager | Parallax stream 09-11 | Parallax stream 09-15 | SQLAlchemy stream |
|---|---:|---:|---:|---:|---:|---:|
| conventional-fanout | 751.8 / 767.3 / 1,519.1 | 634.6 / 569.3 / 1,203.9 | 1,213.8 / 640.6 / 1,854.5 | 4.1 / 296.5 / 300.6 | 3.9 / 196.6 / 200.4 | 65.8 / 359.6 / 425.4 |
| duplicate-include | 767.5 / 1,281.1 / 2,048.6 | 650.2 / 523.6 / 1,173.9 | 1,351.4 / 759.2 / 2,110.6 | 4.2 / 456.7 / 460.9 | 3.8 / 307.0 / 310.8 | 123.8 / 415.3 / 539.2 |
| document-heavy | 912.4 / 1,348.9 / 2,261.4 | 754.3 / 658.8 / 1,413.1 | 1,711.9 / 608.9 / 2,320.8 | 38.2 / 495.9 / 534.1 | 7.3 / 256.8 / 264.1 | 74.9 / 444.4 / 519.3 |
| versioned-document | 250.2 / 276.4 / 526.6 | 200.0 / 94.4 / 294.4 | 334.4 / 55.6 / 390.0 | 15.8 / 140.0 / 155.7 | 2.5 / 66.4 / 68.9 | 2.7 / 136.2 / 138.9 |
| bitemporal-current | 308.9 / 145.5 / 454.5 | 193.3 / 98.4 / 291.8 | 256.9 / 63.6 / 320.5 | 12.9 / 148.3 / 161.2 | 6.4 / 64.6 / 71.0 | 4.4 / 120.3 / 124.7 |

Provider-free medians at `681ce91f`: conventional-fanout eager 12.67 ms and
page-32 stream 15.10 ms with first root at 1.03 ms; duplicate-include eager
18.49 ms and page-32 stream 21.04 ms with first root at 1.55 ms. On
2026-09-11 these were 15.10 / 18.77 / 1.57 and 22.24 / 26.88 / 2.69.

## Reading

1. **Conventional fan-out** is the useful implementation calibration because
   both sides run one root projection and one child projection and publish
   complete child collections. The eager gap narrowed from 2.01× to 1.32×. The
   remaining page-32 stream gap tracks statement topology rather than decode
   or graph cost.
2. **Duplicate include** streaming now beats SQLAlchemy by nearly half.
   SQLAlchemy's identity-map merge across two loaders costs more than
   Parallax's page-bounded merge of duplicate projections.
3. **Document-heavy** still combines implementation cost with a stronger
   contract: Parallax classifies document members, checks canonical Wire
   values, and constructs declared nested Value Objects, where SQLAlchemy keeps
   driver-decoded dictionaries and lists.
4. **Versioned and bitemporal** ratios fell from 3.98× and 6.87× to 3.47× and
   4.06× on eager delivery. They remain upper bounds because the SQLAlchemy
   cells carry no Source Hint, no copy-based write evidence, and no temporal
   edge model.
5. **Time to first root** is now below SQLAlchemy's on four of five shapes,
   and streamed peak memory fell by a third to a half since 2026-09-11.

## Harness repairs

The Parallax script's provider-free fake port had drifted from the current read
path and needed two repairs before the provider-free phase would run. It read
the keyset seek from `binds[-2]`, but the current page statement is a
union-all whose binds are `[seek, seek, limit, limit, limit]`, so every
streamed provider-free delivery restarted at the same page and never
terminated; it now reads `binds[0]`. The eager path also calls
`execute_pipeline`, which the port lacked; it now runs each pipeline statement
in order, as the shared test double does. Neither repair touches the live
PostgreSQL cells, which go through the real adapter. The scripts in
`scripts/` carry these repairs.

## Data

- [data/2026-09-15-parallax-681ce91f.json](data/2026-09-15-parallax-681ce91f.json)
  is the raw matrix this run emitted, including per-page timings, memory, and
  the top profile contributors.
- [data/2026-09-11-parallax.json](data/2026-09-11-parallax.json) and
  [data/2026-09-11-sqlalchemy-2.0.52.json](data/2026-09-11-sqlalchemy-2.0.52.json)
  are rebuilt from the COR-146 and COR-147 task reports, whose raw output was
  not retained.

## Reproduction

Run from `languages/python` so the workspace environment resolves the
packages. Docker must be running for the `pg-full` profile.

```sh
cd languages/python
.venv/bin/python ../../docs/research/delivery-benchmarks/scripts/measure_parallax_delivery.py \
  > ../../docs/research/delivery-benchmarks/data/<date>-parallax-<short-sha>.json
```

The SQLAlchemy comparator installs the measured release outside the project
environment:

```sh
uv pip install --target /tmp/sqlalchemy-site SQLAlchemy==2.0.52
cd languages/python
PYTHONPATH=/tmp/sqlalchemy-site .venv/bin/python \
  ../../docs/research/delivery-benchmarks/scripts/measure_sqlalchemy_delivery.py \
  > ../../docs/research/delivery-benchmarks/data/<date>-sqlalchemy-<version>.json
```
