/**
 * MariaDB **compile-golden lane** (Docker-free) — the second dialect proven by SQL
 * text, independent of any driver or container.
 *
 * Phase 3 adds `mariadbDialect` and proves the abstraction earns its keep at the
 * SQL/value-rule level: for the corpus cases that genuinely DIVERGE in SQL text,
 * compiling the operation against `mariadbDialect` must emit `goldenSql.mariadb`
 * byte-for-byte. The three witnesses:
 *
 *  - `0006` — the quote CHARACTER: MariaDB backticks (`` t0.`order` ``) vs Postgres
 *    double-quotes, applied per identifier (the standalone read-projection quoting
 *    helpers now thread the injected dialect — the deferred Phase-2 conversion);
 *  - `0323` — NULL ordering: MariaDB's leading `is null,` term (no `NULLS LAST`
 *    syntax), exercised on the deep-fetch CHILD level via `mariadbDialect.orderByTerm`;
 *  - `1001` — the read-lock spelling: MariaDB's unaliased ` lock in share mode`.
 *
 * These compile BELOW the harness claim gate (which claims Postgres only — the
 * `slice-sweep` honesty test pins `runCompile(…, "mariadb")` → `unsupported-dialect`),
 * so this lane drives the same `@parallax/sql` visitor the runner uses, injecting
 * `mariadbDialect` directly. The full end-to-end MariaDB round-trip (a driver +
 * Testcontainers provider) lands in Phase 4.
 */
import { mariadbDialect } from "@parallax/dialect";
import { parseOperation } from "@parallax/operation";
import { compile } from "@parallax/sql";
import { describe, expect, it } from "vitest";
import { buildDeepFetchPlan } from "../src/deepfetch-plan.js";
import { discoverCasePaths, type LoadedCase, loadCase } from "../src/discover.js";
import { schemaForReadCase } from "../src/schema-resolver.js";

/** Load a corpus case by its four-digit id (throws if the id is not discovered). */
function caseById(id: string): LoadedCase {
  const path = discoverCasePaths().find((p) => new RegExp(`/${id}-`).test(p));
  if (path === undefined) {
    throw new Error(`no corpus case with id '${id}'`);
  }
  return loadCase(path);
}

/** The MariaDB golden a case pins (a single string, or the per-level array). */
function mariadbGolden(loaded: LoadedCase): string | readonly string[] {
  const golden = (loaded.raw.goldenSql as { mariadb?: string | readonly string[] } | undefined)
    ?.mariadb;
  if (golden === undefined) {
    throw new Error(`${loaded.casePath} carries no goldenSql.mariadb`);
  }
  return golden;
}

/** Compile a flat read case's single statement against `mariadbDialect`. */
function compileFlat(loaded: LoadedCase): string {
  const operation = parseOperation(loaded.raw.operation);
  const schema = schemaForReadCase(loaded, operation, mariadbDialect);
  const { sql } = compile(operation, schema, mariadbDialect, {
    locking: loaded.tags.includes("read-lock"),
  });
  return sql;
}

describe("MariaDB compile-golden lane — emitted === goldenSql.mariadb (Docker-free)", () => {
  it("0006 quotes a reserved-word identifier with backticks (per identifier)", () => {
    const loaded = caseById("0006");
    expect(compileFlat(loaded)).toBe(mariadbGolden(loaded));
  });

  it("1001 appends MariaDB's ` lock in share mode` shared read-lock", () => {
    const loaded = caseById("1001");
    expect(compileFlat(loaded)).toBe(mariadbGolden(loaded));
  });

  it("0323 orders a nullable deep-fetch level with the leading `is null,` term", () => {
    const loaded = caseById("0323");
    const golden = mariadbGolden(loaded) as readonly string[];
    const plan = buildDeepFetchPlan(loaded, mariadbDialect);

    // The deep-fetch ROOT statement (level 0) — no ordering divergence, but proves
    // the plan roots against the injected dialect.
    expect(plan.root.sql).toBe(golden[0]);

    // The single CHILD level carries the `is null,` ordering. Docker-free, its SQL
    // text is fully determined by the key COUNT (2 parent keys ⇒ `in (?, ?)`); the
    // authored root binds `[1, 42]` fix that arity.
    const child = plan.tree[0];
    if (child === undefined) {
      throw new Error("0323 deep-fetch plan has no child level");
    }
    const level = child.compileLevel([1, 42]);
    expect(level.sql).toBe(golden[1]);
  });
});
