/**
 * `@parallax/dialect` conformance suite (Docker-free, pure) — the shared battery
 * of assertions every concrete {@link Dialect} must satisfy, run over the
 * `dialects` table — now parametrized over BOTH `postgresDialect` and
 * `mariadbDialect`, each with its own expectations (the quote character, NULL
 * placement, read-lock spelling, column-type map, errno-vs-SQLSTATE classification,
 * infinity representation, and the per-dialect raw value-parse wire forms).
 *
 * This is where the reified interface earns its first *direct* unit tests: today
 * `quoteIdentifier` / `columnType` / the value parsers are only exercised
 * indirectly downstream. Each catalog method is asserted through the `Dialect`
 * object (not the underlying free functions), so the object wiring itself is
 * proven.
 */
import { INFINITY, ParallaxDecimal, Temporal } from "@parallax/core";
import {
  type Dialect,
  MARIADB_INFINITY_SENTINEL,
  mariadbDialect,
  postgresDialect,
} from "@parallax/dialect";
import { describe, expect, it } from "vitest";

/**
 * The per-dialect expected values for the shared battery. One entry per concrete
 * dialect; adding a dialect = adding one row (plus its object to `@parallax/dialect`).
 */
interface DialectSpec {
  readonly dialect: Dialect;
  readonly id: string;
  /** `quoteIdentifier("order")` — the reserved word quoted this dialect's way. */
  readonly quotedReserved: string;
  /** `orderByTerm("t0.shipped_on", "asc")`. */
  readonly orderAsc: string;
  /** `orderByTerm("t0.shipped_on", "desc")`. */
  readonly orderDesc: string;
  /** `applyReadLock(objectRead, { locking: true, projection: false })` suffix appended. */
  readonly readLockSuffix: string;
  /** The neutral→column-type expectations. */
  readonly columnTypes: Readonly<Record<string, string>>;
  /** `bytesProjection("t0.payload", "payload_hex")` — the dialect's hex projection + binds. */
  readonly bytesProjection: { readonly sql: string; readonly binds: readonly unknown[] };
  /** `infinityBind()`. */
  readonly infinityBind: unknown;
  /** `toPositionalPlaceholders("… ? … ?")`. */
  readonly placeholders: string;
  /** The native error codes this dialect classifies (SQLSTATE string vs vendor errno). */
  readonly errorCodes: {
    readonly uniqueViolation: string | number;
    readonly deadlock: string | number;
    readonly lockWaitTimeout: string | number;
  };
  /** The raw wire forms the value parsers consume (they diverge per dialect). */
  readonly rawValues: {
    /** The raw `timestamp` text that materializes to the `infinity` sentinel. */
    readonly infinityTimestamp: string;
    /** A finite raw `timestamp` text that materializes to `2024-03-01T12:00:00Z`. */
    readonly finiteTimestamp: string;
    /** A raw `bytes` hex rendering that materializes to `[0xde,0xad,0xbe,0xef]`. */
    readonly bytesHex: string;
  };
}

const OBJECT_READ = "select t0.id, t0.owner from account t0 where t0.id = ?";
const DISTINCT_READ = "select distinct t0.owner from account t0";

const dialects: readonly DialectSpec[] = [
  {
    dialect: postgresDialect,
    id: "postgres",
    quotedReserved: '"order"',
    orderAsc: "t0.shipped_on asc",
    orderDesc: "t0.shipped_on desc nulls last",
    readLockSuffix: " for share of t0",
    columnTypes: {
      boolean: "boolean",
      int64: "bigint",
      float32: "real",
      float64: "double precision",
      "decimal(18,2)": "numeric(18,2)",
      timestamp: "timestamptz",
      bytes: "bytea",
      uuid: "uuid",
    },
    // Postgres encodes bytes to hex with the `'hex'` format carried as a bind.
    bytesProjection: { sql: "encode(t0.payload, ?) payload_hex", binds: ["hex"] },
    infinityBind: INFINITY,
    placeholders: "select t0.a from t0 where t0.a = $1 and t0.b = $2",
    errorCodes: { uniqueViolation: "23505", deadlock: "40P01", lockWaitTimeout: "55P03" },
    rawValues: {
      infinityTimestamp: "infinity",
      finiteTimestamp: "2024-03-01 12:00:00+00",
      bytesHex: "\\xdeadbeef",
    },
  },
  {
    dialect: mariadbDialect,
    id: "mariadb",
    // The one genuine cross-dialect divergence in the quote CHARACTER: backticks.
    quotedReserved: "`order`",
    // MariaDB has no `NULLS LAST` syntax: `asc` forces NULLs last with a leading
    // `is null,` term; `desc` is bare (its native default already trails NULLs).
    orderAsc: "t0.shipped_on is null, t0.shipped_on asc",
    orderDesc: "t0.shipped_on desc",
    // MariaDB has no `for share` (MDEV-17514); the shared lock is unaliased.
    readLockSuffix: " lock in share mode",
    columnTypes: {
      boolean: "tinyint(1)",
      int64: "bigint",
      float32: "float",
      float64: "double",
      "decimal(18,2)": "decimal(18,2)",
      timestamp: "datetime(6)",
      bytes: "longblob",
      uuid: "char(36)",
    },
    // MariaDB's `hex(...)` takes no format argument, so the projection is bind-free.
    bytesProjection: { sql: "hex(t0.payload) payload_hex", binds: [] },
    // MariaDB's `DATETIME` has no native infinity; the open upper bound binds the
    // documented max-sentinel datetime.
    infinityBind: MARIADB_INFINITY_SENTINEL,
    // The MariaDB driver takes native `?`, so the placeholder rewrite is identity.
    placeholders: "select t0.a from t0 where t0.a = ? and t0.b = ?",
    // MariaDB keys on the vendor errno (an int), not a SQLSTATE string.
    errorCodes: { uniqueViolation: 1062, deadlock: 1213, lockWaitTimeout: 1205 },
    rawValues: {
      // The max-sentinel round-trips back to the `infinity` sentinel.
      infinityTimestamp: MARIADB_INFINITY_SENTINEL,
      // A MariaDB `DATETIME` carries no offset (treated as UTC).
      finiteTimestamp: "2024-03-01 12:00:00",
      // MariaDB `hex(...)` yields bare hex (no `\x` prefix).
      bytesHex: "deadbeef",
    },
  },
];

for (const spec of dialects) {
  describe(`Dialect conformance — ${spec.id}`, () => {
    const { dialect } = spec;

    it("reports its stable id (keys goldenSql / expectedNativeCode)", () => {
      expect(dialect.id).toBe(spec.id);
    });

    describe("quoteIdentifier", () => {
      it("quotes a reserved word", () => {
        expect(dialect.quoteIdentifier("order")).toBe(spec.quotedReserved);
      });

      it("leaves a simple non-reserved identifier bare", () => {
        expect(dialect.quoteIdentifier("id")).toBe("id");
        expect(dialect.quoteIdentifier("shipped_on")).toBe("shipped_on");
      });
    });

    describe("orderByTerm (NULL placement)", () => {
      it("emits the ascending term", () => {
        expect(dialect.orderByTerm("t0.shipped_on", "asc")).toBe(spec.orderAsc);
      });

      it("emits the descending term with this dialect's NULL placement", () => {
        expect(dialect.orderByTerm("t0.shipped_on", "desc")).toBe(spec.orderDesc);
      });
    });

    describe("rowLimit", () => {
      it("appends the row-limit clause with a `?` bind", () => {
        expect(dialect.rowLimit("select t0.id from account t0")).toBe(
          "select t0.id from account t0 limit ?",
        );
      });
    });

    describe("applyReadLock", () => {
      it("applies the shared read-lock to a locking object find", () => {
        expect(dialect.applyReadLock(OBJECT_READ, { locking: true, projection: false })).toBe(
          `${OBJECT_READ}${spec.readLockSuffix}`,
        );
      });

      it("returns a projection/aggregation read unchanged (no base row to lock)", () => {
        expect(dialect.applyReadLock(DISTINCT_READ, { locking: true, projection: true })).toBe(
          DISTINCT_READ,
        );
      });

      it("returns any read unchanged when not locking", () => {
        expect(dialect.applyReadLock(OBJECT_READ, { locking: false, projection: false })).toBe(
          OBJECT_READ,
        );
      });
    });

    describe("bytesProjection", () => {
      it("lowers a bytes column to this dialect's hex projection + binds", () => {
        expect(dialect.bytesProjection("t0.payload", "payload_hex")).toEqual(spec.bytesProjection);
      });
    });

    describe("columnType", () => {
      it("maps neutral base and parametric types to this dialect's vocabulary", () => {
        for (const [neutral, expected] of Object.entries(spec.columnTypes)) {
          expect(dialect.columnType(neutral)).toBe(expected);
        }
      });

      it("maps a bounded string to a length-qualified type and unbounded to the fallback", () => {
        // Both dialects use varchar(n)/text for string; asserted through the object.
        expect(dialect.columnType("string", 20)).toMatch(/\(20\)$/);
        expect(dialect.columnType("string")).toBeTypeOf("string");
      });
    });

    describe("error classification + predicates", () => {
      it("classifies a unique violation and answers violatesUniqueIndex", () => {
        const category = dialect.classifyErrorCode(spec.errorCodes.uniqueViolation);
        expect(category).toBe("uniqueViolation");
        expect(dialect.violatesUniqueIndex(category)).toBe(true);
        expect(dialect.isRetriable(category)).toBe(false);
        expect(dialect.isTimedOut(category)).toBe(false);
      });

      it("classifies a deadlock and answers isRetriable", () => {
        const category = dialect.classifyErrorCode(spec.errorCodes.deadlock);
        expect(category).toBe("deadlock");
        expect(dialect.isRetriable(category)).toBe(true);
        expect(dialect.violatesUniqueIndex(category)).toBe(false);
      });

      it("classifies a lock-wait timeout and answers isTimedOut (not retriable)", () => {
        const category = dialect.classifyErrorCode(spec.errorCodes.lockWaitTimeout);
        expect(category).toBe("lockWaitTimeout");
        expect(dialect.isTimedOut(category)).toBe(true);
        expect(dialect.isRetriable(category)).toBe(false);
      });

      it("returns unknown for an unrecognized/missing code, all predicates false", () => {
        for (const code of ["99999", null, undefined] as const) {
          const category = dialect.classifyErrorCode(code);
          expect(category).toBe("unknown");
          expect(dialect.isRetriable(category)).toBe(false);
          expect(dialect.violatesUniqueIndex(category)).toBe(false);
          expect(dialect.isTimedOut(category)).toBe(false);
        }
      });
    });

    describe("parsers (normalize-at-boundary)", () => {
      it("int8 → bigint beyond the JS safe-integer range", () => {
        expect(dialect.parsers.int8("9223372036854775807")).toBe(9223372036854775807n);
      });

      it("numeric → exact ParallaxDecimal (no binary-float drift)", () => {
        const parsed = dialect.parsers.numeric("19.99");
        expect(parsed).toBeInstanceOf(ParallaxDecimal);
        expect(parsed.equals(ParallaxDecimal.from("19.99"))).toBe(true);
      });

      it("timestamp → Temporal.Instant, mapping this dialect's infinity form through", () => {
        expect(dialect.parsers.timestamp(spec.rawValues.infinityTimestamp)).toBe(INFINITY);
        const instant = dialect.parsers.timestamp(spec.rawValues.finiteTimestamp);
        expect(instant).not.toBe(INFINITY);
        expect(
          Temporal.Instant.compare(
            instant as Temporal.Instant,
            Temporal.Instant.from("2024-03-01T12:00:00Z"),
          ),
        ).toBe(0);
      });

      it("bytes → Uint8Array from the hex rendering", () => {
        expect(Array.from(dialect.parsers.bytes(spec.rawValues.bytesHex))).toEqual([
          0xde, 0xad, 0xbe, 0xef,
        ]);
      });

      it("date → Temporal.PlainDate", () => {
        expect(dialect.parsers.date("2024-03-01").toString()).toBe("2024-03-01");
      });

      it("time → Temporal.PlainTime", () => {
        expect(dialect.parsers.time("12:34:56").toString()).toBe("12:34:56");
      });

      it("uuid → canonical string", () => {
        expect(dialect.parsers.uuid("2f8a2c9e-0000-4000-8000-000000000000")).toBe(
          "2f8a2c9e-0000-4000-8000-000000000000",
        );
      });
    });

    describe("infinityBind", () => {
      it("returns this dialect's infinity bind representation", () => {
        expect(dialect.infinityBind()).toBe(spec.infinityBind);
      });
    });

    describe("bindValue", () => {
      it("normalizes ordinary scalar binds to wire values", () => {
        expect(dialect.bindValue("decimal(18,2)", ParallaxDecimal.from("19.99"))).toBe("19.99");
        expect(dialect.bindValue("int64", 9223372036854775807n)).toBe("9223372036854775807");
      });

      it("normalizes timestamp binds for this dialect's adapter boundary", () => {
        const instant = Temporal.Instant.from("2024-03-01T12:00:00Z");
        const boundInstant = dialect.bindValue("timestamp", instant);
        const boundWireString = dialect.bindValue("timestamp", "2024-03-01T12:00:00+00:00");

        if (spec.id === "mariadb") {
          expect(boundInstant).toBe(instant);
          expect(boundWireString).toBeInstanceOf(Temporal.Instant);
          expect(Temporal.Instant.compare(boundWireString as Temporal.Instant, instant)).toBe(0);
        } else {
          expect(boundInstant).toBe("2024-03-01T12:00:00+00:00");
          expect(boundWireString).toBe("2024-03-01T12:00:00+00:00");
        }
      });

      it("preserves the neutral infinity sentinel as a timestamp bind", () => {
        expect(dialect.bindValue("timestamp", INFINITY)).toBe(INFINITY);
      });

      it("keeps a `bytes` value as its raw carrier (never hex TEXT)", () => {
        // A `Uint8Array` must reach the adapter as raw bytes, not `toWire`'s hex
        // rendering: porsager infers `bytea` and mysql2 wraps a `Buffer`, whereas a
        // hex string would be stored as its ASCII characters on both drivers.
        const payload = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
        expect(dialect.bindValue("bytes", payload)).toBe(payload);
      });
    });

    describe("toPositionalPlaceholders", () => {
      it("rewrites `?` placeholders to this dialect's driver syntax", () => {
        expect(
          dialect.toPositionalPlaceholders("select t0.a from t0 where t0.a = ? and t0.b = ?"),
        ).toBe(spec.placeholders);
      });
    });
  });
}
