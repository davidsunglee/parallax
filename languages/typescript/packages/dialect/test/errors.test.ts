/**
 * `@parallax/dialect` unit tests (Docker-free, pure) — SQLSTATE → neutral-category
 * error classification (M11), the TypeScript peer of the reference harness
 * `errors.py`.
 *
 * The retriable set is `{deadlock}` — a true deadlock (`40P01`) OR a serialization
 * failure (`40001`), both folded into `deadlock`, both retriable. A lock-not-
 * available timeout (`55P03`) is `lockWaitTimeout` and is NOT retriable. These
 * assertions mirror the normative reference model exactly.
 */
import { classifyErrorCode, isRetriableCategory } from "@parallax/dialect";
import { describe, expect, it } from "vitest";

describe("classifyErrorCode (M11 SQLSTATE map, errors.py parity)", () => {
  it("classifies the Postgres SQLSTATEs the reference model does", () => {
    expect(classifyErrorCode("23505")).toBe("uniqueViolation");
    expect(classifyErrorCode("40P01")).toBe("deadlock");
    expect(classifyErrorCode("40001")).toBe("deadlock"); // serialization_failure -> deadlock
    expect(classifyErrorCode("55P03")).toBe("lockWaitTimeout");
  });

  it("returns unknown for an unrecognized or missing code", () => {
    expect(classifyErrorCode("99999")).toBe("unknown");
    expect(classifyErrorCode(null)).toBe("unknown");
    expect(classifyErrorCode(undefined)).toBe("unknown");
  });

  it("accepts a numeric code (coerced to its string form)", () => {
    expect(classifyErrorCode(23505)).toBe("uniqueViolation");
  });
});

describe("isRetriableCategory (retry loop's question)", () => {
  it("treats only deadlock (deadlock + serialization failure) as retriable", () => {
    expect(isRetriableCategory("deadlock")).toBe(true);
    // 55P03 lock-wait timeout is NOT retriable (the session-3 correction).
    expect(isRetriableCategory("lockWaitTimeout")).toBe(false);
    expect(isRetriableCategory("uniqueViolation")).toBe(false);
    expect(isRetriableCategory("connectionDead")).toBe(false);
    expect(isRetriableCategory("unknown")).toBe(false);
  });
});
