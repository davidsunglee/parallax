/**
 * porsager (`postgres`) OID registration for `@parallax/db-postgres`.
 *
 * The adapter owns **only driver registration** — which Postgres type codes
 * (`RAW_TEXT_OIDS`, an adapter-local map now that OIDs are a driver concern, Q3-A)
 * to read as raw text, mapped to the neutral parser key — and delegates every parse
 * decision to `postgresDialect.parsers` (the pure dialect layer stays the single
 * source of parse logic; M11 decomposition). Registering a custom type per OID
 * forces porsager to hand that column back as raw text so the dialect parser
 * materializes it into a **managed** scalar (`bigint` / `ParallaxDecimal` /
 * `Temporal.*` / `Uint8Array` / string) at the adapter boundary (§3.2.1), rather
 * than the driver default (a ms-precision `Date`, a binary-float `numeric`, …).
 *
 * There is **no wire / grading logic here** — an adapter emits managed types
 * only (*managed at the boundary, wire at the grader*).
 */
import { postgresDialect } from "@parallax/dialect";

/**
 * The Postgres OIDs whose driver-default parse would violate an M0 contract, so the
 * adapter registers a raw-text parser for each. An OID is a **driver / adapter**
 * concern — a real Postgres catalog type-number the wire protocol stamps on each
 * returned column (`numeric`→1700, `int8`→20, `timestamptz`→1184, …) — so the map
 * lives here (Q3-A); the *parse logic* keyed by neutral type lives on the dialect.
 */
const RAW_TEXT_OIDS = {
  /** `int8` — `bigint`. JS `number` cannot hold the full int64 range. */
  int8: 20,
  /** `numeric` — exact decimal. The driver default is a lossy binary float. */
  numeric: 1700,
  /** `timestamptz` — UTC instant. The driver default is a ms-precision `Date`. */
  timestamptz: 1184,
  /** `timestamp` — same precision concern as `timestamptz`. */
  timestamp: 1114,
  /** `bytea` — `Uint8Array`, parsed from the `\x…` hex rendering. */
  bytea: 17,
  /** `date` — `Temporal.PlainDate` (calendar date, no time / offset). */
  date: 1082,
  /** `time` — `Temporal.PlainTime` (wall-clock time, no date / offset). */
  time: 1083,
  /** `uuid` — a canonical lowercase string (no managed carrier). */
  uuid: 2950,
} as const;

/** A porsager custom-type registration keyed by its serializer + parser. */
interface PorsagerType {
  readonly to: number;
  readonly from: readonly number[];
  readonly serialize: (v: unknown) => unknown;
  readonly parse: (raw: string) => unknown;
}

/**
 * The default text serializer for a custom type on the **bind** path. porsager
 * looks up the serializer by the prepared statement's parameter OID, so
 * registering a custom `int8` / `numeric` / `date` type means our serializer runs
 * when a value binds to that column. The wire protocol is text, so a scalar
 * stringifies (porsager's own `int8` / `numeric` defaults likewise stringify) and
 * a `null` binds as SQL NULL untouched.
 */
function textSerialize(v: unknown): unknown {
  return v === null || v === undefined ? v : String(v);
}

/**
 * Serialize a `bytea` bind to Postgres' `\xDEADBEEF` hex wire form (the same form
 * porsager's native `bytea` serializer produces). A fixture `payload` loaded from
 * a YAML `!!binary` tag arrives as a `Buffer` / `Uint8Array`; the default
 * `String(v)` serializer would flatten it to `""`, so `bytea` overrides it. This
 * is **load-bearing** on the fixture-insert bind path — do not regress it to a
 * blanket string coercion.
 */
export function serializeBytea(v: unknown): unknown {
  if (v === null || v === undefined) {
    return v;
  }
  return `\\x${Buffer.from(v as Uint8Array).toString("hex")}`;
}

/** A custom type forcing `oid` to be read as raw text and parsed by `parse`. */
function rawType(
  oid: number,
  parse: (raw: string) => unknown,
  serialize: (v: unknown) => unknown = textSerialize,
): PorsagerType {
  return { to: oid, from: [oid], serialize, parse };
}

/**
 * The porsager custom-type map that normalizes every driver-precision-sensitive
 * column to its **managed** carrier via the dialect parse functions. `int8` /
 * `numeric` arrive as raw text by porsager default; they are registered
 * explicitly so the contract is owned here, not implicit. `date` / `time` /
 * `uuid` are registered so those OIDs read as text too (their driver defaults
 * would not be the managed carrier).
 */
export function managedTypes(): Record<string, PorsagerType> {
  const { parsers } = postgresDialect;
  return {
    int8: rawType(RAW_TEXT_OIDS.int8, (raw) => parsers.int8(raw)),
    numeric: rawType(RAW_TEXT_OIDS.numeric, (raw) => parsers.numeric(raw)),
    timestamptz: rawType(RAW_TEXT_OIDS.timestamptz, (raw) => parsers.timestamp(raw)),
    timestamp: rawType(RAW_TEXT_OIDS.timestamp, (raw) => parsers.timestamp(raw)),
    bytea: rawType(RAW_TEXT_OIDS.bytea, (raw) => parsers.bytes(raw), serializeBytea),
    date: rawType(RAW_TEXT_OIDS.date, (raw) => parsers.date(raw)),
    time: rawType(RAW_TEXT_OIDS.time, (raw) => parsers.time(raw)),
    uuid: rawType(RAW_TEXT_OIDS.uuid, (raw) => parsers.uuid(raw)),
  };
}
