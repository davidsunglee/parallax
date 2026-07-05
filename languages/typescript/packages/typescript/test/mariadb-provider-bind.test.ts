/**
 * Pure (Docker-free) unit test for the MariaDB conformance provider's untyped→managed
 * bind seam, `toManagedBind` (Finding 1). The grader-side provider — not the shipped
 * adapter — owns lifting an untyped ISO-instant corpus STRING to a `Temporal.Instant`
 * (mirroring the Python reference's `_to_db_bind` / `_parse_iso_instant`, which run in
 * the provider, not the driver). Every non-instant value is left untouched for the
 * adapter's own handling.
 */
import { Temporal } from "@parallax/core";
import { describe, expect, it } from "vitest";
import { toManagedBind } from "../src/conformance/mariadb-provider.js";

describe("toManagedBind — the grader-side untyped→managed coercion", () => {
  it("materializes a full ISO-8601 instant STRING to a Temporal.Instant", () => {
    const managed = toManagedBind("2024-03-01T12:00:00+00:00");
    expect(managed).toBeInstanceOf(Temporal.Instant);
    expect(
      (managed as Temporal.Instant).equals(Temporal.Instant.from("2024-03-01T12:00:00Z")),
    ).toBe(true);
  });

  it("leaves the `infinity` sentinel and non-instant strings alone", () => {
    // `"infinity"` has no `T` → stays a string for the adapter's isInfinity branch.
    expect(toManagedBind("infinity")).toBe("infinity");
    // A `T`-carrying non-instant fails to parse → stays text.
    expect(toManagedBind("Trent")).toBe("Trent");
    // A bare date / uuid / business string is untouched.
    expect(toManagedBind("2024-03-01")).toBe("2024-03-01");
    expect(toManagedBind("A")).toBe("A");
  });

  it("passes non-strings — including an already-typed Temporal.Instant — through unchanged", () => {
    const instant = Temporal.Instant.from("2024-03-01T12:00:00Z");
    expect(toManagedBind(instant)).toBe(instant);
    expect(toManagedBind(42)).toBe(42);
    expect(toManagedBind(null)).toBe(null);
    expect(toManagedBind(true)).toBe(true);
  });
});
