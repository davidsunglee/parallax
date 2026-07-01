/**
 * `@parallax/locking` unit tests (Docker-free, pure) — the M10 versioned-UPDATE
 * discipline and the `updatedRows != 1` conflict signal, in isolation.
 *
 * Pins the exact canonical versioned UPDATE (the `0703`/`0704`/`0708` golden and
 * the `0707` version-only bump) and the outcome classification (1 → success,
 * 0 → conflict, anything else → error).
 */
import { classifyOutcome, type VersionedTarget, versionedUpdate } from "@parallax/locking";
import { describe, expect, it } from "vitest";

/** The `account` versioned target (table account, pk id, version column). */
const ACCOUNT: VersionedTarget = {
  table: "account",
  pkColumn: "id",
  versionColumn: "version",
};

describe("versionedUpdate — gate on the read version, advance it", () => {
  it("writes a domain column AND the version, gating on pk + version (0703/0704)", () => {
    expect(versionedUpdate(ACCOUNT, ["balance"])).toBe(
      "update account set balance = ?, version = ? where id = ? and version = ?",
    );
  });

  it("writes ONLY the version for a version-only bump (0707)", () => {
    expect(versionedUpdate(ACCOUNT, [])).toBe(
      "update account set version = ? where id = ? and version = ?",
    );
  });

  it("always keys on pk AND the version, never a blind pk update", () => {
    const sql = versionedUpdate(ACCOUNT, ["balance"]);
    expect(sql).toMatch(/where id = \? and version = \?$/);
  });
});

describe("classifyOutcome — the affected-row conflict signal", () => {
  it("classifies exactly one affected row as success (0704)", () => {
    expect(classifyOutcome(1)).toBe("success");
  });

  it("classifies zero affected rows as a conflict (0703)", () => {
    expect(classifyOutcome(0)).toBe("conflict");
  });

  it("rejects any other affected-row count (a pk-keyed update touches 0 or 1)", () => {
    expect(() => classifyOutcome(2)).toThrow(/affected 2 rows/);
  });
});
