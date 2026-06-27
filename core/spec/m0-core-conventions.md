# M0 — Core Conventions

The normative primitives the whole spec rests on: the neutral data-type set, the
timezone/UTC rules, and (introduced in a later phase) the temporal-infinity
representation. `M0` depends on nothing; every other module depends, directly or
transitively, on it.

## Neutral data types

An implementation **MUST** support the neutral type set below and **MUST** map
each to the Postgres type shown. The neutral name is what appears in a model
descriptor's `attribute.type`; the concrete column type is owned by the M11
dialect seam.

| Neutral type | Description | Postgres type | Notes |
|---|---|---|---|
| `boolean` | true / false | `boolean` | |
| `int32` | 32-bit signed integer | `integer` | |
| `int64` | 64-bit signed integer | `bigint` | |
| `float32` | 32-bit IEEE-754 | `real` | |
| `float64` | 64-bit IEEE-754 | `double precision` | |
| `decimal(p,s)` | exact fixed-point | `numeric(p,s)` | money / exact math; precision `p` and scale `s` are REQUIRED |
| `string` | variable-length text | `text` / `varchar(n)` | optional `maxLength` ⇒ `varchar(n)`; UTF-8 |
| `bytes` | binary blob | `bytea` | |
| `date` | calendar date, no time | `date` | timezone-naive (wall-clock) |
| `time` | time of day, no date | `time` | timezone-naive (wall-clock) |
| `timestamp` | absolute instant | `timestamptz` | UTC-normalized (see below) |
| `uuid` | 128-bit UUID | `uuid` | in core (Postgres-native) |

> The walking-skeleton phase exercises `int64`/`int32`, `string`, and (in the
> schema) the full set. `boolean`, `decimal(p,s)`, and the temporal/`json` types
> gain dedicated fixtures in later phases.

**Deferred (optional / extension, not in the core type set yet):** `int16`,
`int8`, `char`, and an embedded-value `json` type (maps to `jsonb`; introduced
with the metamodel's `valueObject` element in a later phase).

## Timezone handling

- All `timestamp` (instant) columns **MUST** use `timestamp with time zone`
  (`timestamptz`) and the framework **MUST** normalize values to **UTC** at the
  boundary. Geographically distributed applications store and compare in UTC and
  convert only at presentation.
- `date` and `time` are **wall-clock and timezone-naive** by definition; no
  timezone normalization is applied to them.
- There is **no per-attribute timezone-conversion knob** (Reladomo's
  `timezoneConversion` is dropped): timestamps are UTC-normalized globally.

## Temporal infinity

The open upper bound of a temporal interval (the `to`/`thru`/`out` column) is
represented by the **database's native infinity**, not a `9999-12-01` sentinel
and not `NULL`. The metamodel declares that a temporal dimension *has* an
infinity sentinel; the **M11 dialect seam owns the concrete representation**
(Postgres → native `'infinity'::timestamptz`; a future dialect lacking native
infinity maps to a documented max-sentinel — earmarked for the MariaDB phase).
The full temporal interval model and milestone-chaining writes are M7.

Benefits of native infinity over a `9999` sentinel or `NULL`: correct
ordering/comparison, no Y9999 cliff, no `NULL`-in-predicate/index complications,
and a clear current-row predicate (`to = infinity`).

**As-of business date is a UTC `timestamp`.** Both temporal axes — processing and
business — use the `timestamp` (instant) type, UTC-normalized like every other
instant, so interval math is uniform across axes. A date-granular business date
is a `timestamp` at UTC midnight by convention.
