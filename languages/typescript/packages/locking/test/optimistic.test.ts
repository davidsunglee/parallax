/**
 * `@parallax/locking` unit tests (Docker-free, pure) — the M10 versioned-UPDATE
 * discipline and the `updatedRows != 1` conflict signal, in isolation.
 *
 * Pins the exact canonical versioned UPDATE forms — the OPTIMISTIC-mode gated
 * `0703`/`0704`/`0708` golden and the LOCKING-mode ungated version-advancing
 * `0611` golden — and the outcome classification (1 → success, 0 → conflict,
 * anything else → error).
 */
import {
  classifyOutcome,
  type VersionedTarget,
  versionAdvancingUpdate,
  versionedUpdate,
} from "@parallax/locking";
import { describe, expect, it } from "vitest";

/** The `account` versioned target (table account, pk id, version column). */
const ACCOUNT: VersionedTarget = {
  table: "account",
  pkColumn: "id",
  versionColumn: "version",
};

describe("versionedUpdate — optimistic mode: gate on the observed version, advance it", () => {
  it("writes a domain column AND the version, gating on pk + version (0703/0704)", () => {
    expect(versionedUpdate(ACCOUNT, ["balance"])).toBe(
      "update account set balance = ?, version = ? where id = ? and version = ?",
    );
  });

  it("always keys on pk AND the version, never a blind pk update", () => {
    const sql = versionedUpdate(ACCOUNT, ["balance"]);
    expect(sql).toMatch(/where id = \? and version = \?$/);
  });
});

describe("versionAdvancingUpdate — locking mode: advance the version WITHOUT a gate", () => {
  it("writes a domain column AND the version, keyed on pk ONLY (0611)", () => {
    expect(versionAdvancingUpdate(ACCOUNT, ["balance"])).toBe(
      "update account set balance = ?, version = ? where id = ?",
    );
  });

  it("emits no `and version = ?` gate (the shared read lock makes it correct)", () => {
    const sql = versionAdvancingUpdate(ACCOUNT, ["balance"]);
    expect(sql).not.toContain("and version = ?");
    expect(sql).toMatch(/where id = \?$/);
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
