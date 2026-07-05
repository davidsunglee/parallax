/**
 * `selectedProviders` **selection-parsing** unit test (Docker-free): the
 * `PARALLAX_DATABASES` env → provider-list resolution never silently drops
 * coverage. It exercises only the pure parsing branches (default, single, list,
 * unknown-key throw, and the empty-after-filter throw for a comma-only value), so
 * it runs in the fast lane without booting a container — `selectedProviders()`
 * touches Docker only through `.start()`, which these cases never call.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { selectedProviders } from "./_providers.js";

/** Set `PARALLAX_DATABASES` to `value`, or delete it when `undefined`. */
function setDatabases(value: string | undefined): void {
  if (value === undefined) {
    delete process.env.PARALLAX_DATABASES;
  } else {
    process.env.PARALLAX_DATABASES = value;
  }
}

describe("selectedProviders", () => {
  let saved: string | undefined;

  beforeEach(() => {
    saved = process.env.PARALLAX_DATABASES;
  });
  afterEach(() => {
    setDatabases(saved);
  });

  it("defaults to postgres when unset", () => {
    setDatabases(undefined);
    expect(selectedProviders().map((p) => p.dialect)).toEqual(["postgres"]);
  });

  it("defaults to postgres for an empty or pure-whitespace value (unchanged default path)", () => {
    setDatabases("");
    expect(selectedProviders().map((p) => p.dialect)).toEqual(["postgres"]);
    setDatabases("   ");
    expect(selectedProviders().map((p) => p.dialect)).toEqual(["postgres"]);
  });

  it("selects the named databases (trimming a comma-separated list)", () => {
    setDatabases("mariadb");
    expect(selectedProviders().map((p) => p.dialect)).toEqual(["mariadb"]);
    setDatabases(" postgres , mariadb ");
    expect(selectedProviders().map((p) => p.dialect)).toEqual(["postgres", "mariadb"]);
  });

  it("throws on an unknown key (a typo never silently drops coverage)", () => {
    setDatabases("postgres,mysql");
    expect(() => selectedProviders()).toThrow(/unknown PARALLAX_DATABASES entry 'mysql'/);
  });

  it("throws — never returns zero providers — for a non-empty value that resolves to no keys", () => {
    setDatabases(",");
    expect(() => selectedProviders()).toThrow(/selects no databases/);
    setDatabases(" , ");
    expect(() => selectedProviders()).toThrow(/selects no databases/);
  });
});
