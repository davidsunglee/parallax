/**
 * `@parallax/dialect` conformance suite (Docker-free, pure) — the shared battery
 * of assertions every concrete {@link Dialect} must satisfy, run over the
 * `dialects` table. Phase 1 parametrizes it over `postgresDialect` alone; Phase 3
 * adds `mariadbDialect` to the same table with its own expectations.
 *
 * This is where the reified interface earns its first *direct* unit tests: today
 * `quoteIdentifier` / `columnType` / the value parsers are only exercised
 * indirectly downstream. Each catalog method is asserted through the `Dialect`
 * object (not the underlying free functions), so the object wiring itself is
 * proven.
 */
import { INFINITY, ParallaxDecimal, Temporal } from "@parallax/core";
import { type Dialect, postgresDialect } from "@parallax/dialect";
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
  /** `infinityBind()`. */
  readonly infinityBind: unknown;
  /** `toPositionalPlaceholders("… ? … ?")`. */
  readonly placeholders: string;
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
      int64: "bigint",
      "decimal(18,2)": "numeric(18,2)",
      timestamp: "timestamptz",
      bytes: "bytea",
      uuid: "uuid",
    },
    infinityBind: INFINITY,
    placeholders: "select t0.a from t0 where t0.a = $1 and t0.b = $2",
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
        const category = dialect.classifyErrorCode(spec.id === "postgres" ? "23505" : 1062);
        expect(category).toBe("uniqueViolation");
        expect(dialect.violatesUniqueIndex(category)).toBe(true);
        expect(dialect.isRetriable(category)).toBe(false);
        expect(dialect.isTimedOut(category)).toBe(false);
      });

      it("classifies a deadlock and answers isRetriable", () => {
        const category = dialect.classifyErrorCode(spec.id === "postgres" ? "40P01" : 1213);
        expect(category).toBe("deadlock");
        expect(dialect.isRetriable(category)).toBe(true);
        expect(dialect.violatesUniqueIndex(category)).toBe(false);
      });

      it("classifies a lock-wait timeout and answers isTimedOut (not retriable)", () => {
        const category = dialect.classifyErrorCode(spec.id === "postgres" ? "55P03" : 1205);
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

      it("timestamp → Temporal.Instant, passing the infinity sentinel through", () => {
        expect(dialect.parsers.timestamp("infinity")).toBe(INFINITY);
        const instant = dialect.parsers.timestamp("2024-03-01 12:00:00+00");
        expect(instant).not.toBe(INFINITY);
        expect(
          Temporal.Instant.compare(
            instant as Temporal.Instant,
            Temporal.Instant.from("2024-03-01T12:00:00Z"),
          ),
        ).toBe(0);
      });

      it("bytes → Uint8Array from the hex rendering", () => {
        expect(Array.from(dialect.parsers.bytes("\\xdeadbeef"))).toEqual([0xde, 0xad, 0xbe, 0xef]);
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

    describe("toPositionalPlaceholders", () => {
      it("rewrites `?` placeholders to this dialect's driver syntax", () => {
        expect(
          dialect.toPositionalPlaceholders("select t0.a from t0 where t0.a = ? and t0.b = ?"),
        ).toBe(spec.placeholders);
      });
    });
  });
}
