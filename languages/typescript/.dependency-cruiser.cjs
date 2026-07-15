"use strict";

const { join } = require("node:path");

/**
 * dependency-cruiser allowlist for the TypeScript workspace.
 *
 * This is the trimmed + corrected encoding of the module DAG from
 * `core/spec/modules.md`, mapped onto the `@parallax/*` packages by
 * `languages/typescript/spec/01-implementation-spec.md` §9.
 *
 * Trimmed (design Q4): only the 13 packages the `slice-mvp-1`
 * slice actually implements are scaffolded, so `lifecycle` (`m-detach`),
 * `benchmark` (`m-perf-bench`), and `coherence` (`m-coherence`) — and every edge
 * that touches them — are intentionally absent. They are added when their slice
 * lands; an allowlist edge exists only when there is an implementation behind
 * it.
 *
 * Corrected (design Q5): the `relationships -> bitemporal`
 * (`m-navigate -> m-temporal-read`) edge that core declares (as-of binds
 * propagate per relationship hop) but the spec's §9.3 transcription previously
 * omitted is present here.
 *
 * Re-pinned (core amendment, ADR 0025 — mechanical maintenance, not design
 * input): `modules.md` inverted the lifecycle-result-surface edges, so
 * `relationships` (`m-navigate` + `m-deep-fetch`) now depends on `operation`
 * (`m-op-algebra`) directly instead of on `lists`, and `lists` (`m-op-list`)
 * now depends on `relationships` (a lazy list is populated by deep fetch — the
 * same relationship `m-snapshot-read` already has with deep fetch).
 *
 * Semantics: with an `allowed` array, any dependency that matches no rule is
 * reported as `not-in-allowed`. `allowedSeverity: "error"` makes that fail the
 * build. The list therefore enumerates every legal dependency: same-package
 * imports, npm / built-in imports, and the legal cross-package edges below.
 */

// Path fragment that matches a workspace package directory. dependency-cruiser
// tests this with `RegExp.test` against each module path (which may be reported
// relative to the cwd or with a `languages/typescript/` prefix), so it is left
// unanchored and free of unbounded wildcards (which the ReDoS guard rejects).
const PKG = "(?:^|/)packages/";

/** A legal cross-package edge `from -> to`. */
function edge(from, to) {
  return {
    from: { path: `${PKG}${from}/` },
    to: { path: `${PKG}${to}/` },
  };
}

module.exports = {
  allowed: [
    // Same-package imports: from package X to the same package X. dependency-
    // cruiser interpolates the `from.path` capture group into `to.path` as `$1`
    // (group interpolation, not an in-regex backreference, which it rejects as
    // unsafe).
    {
      from: { path: `${PKG}([^/]+)/` },
      to: { path: `${PKG}$1/` },
    },

    // Anything that is not a workspace package (npm packages, node: builtins,
    // type-only references, etc.) is always allowed.
    {
      from: { path: `${PKG}[^/]+/` },
      to: { pathNot: PKG },
    },

    // `@parallax/core` is the foundational leaf (`m-core` conventions + the shared
    // adapter-envelope types). It depends on nothing, so depending on it can
    // never create a wrong-direction edge. Like the `serde` edges, this is an
    // explicit package-topology allowance, not an addition to the module DAG —
    // the DAG only declares `m-descriptor -> m-core` and `m-dialect -> m-core`,
    // but the envelope types live here and are consumed across the build (e.g.
    // `@parallax/conformance` builds a `DescribeOk`). The reverse — `core`
    // importing any sibling — stays forbidden, which is what the negative
    // boundary test plants and asserts.
    {
      from: { path: `${PKG}[^/]+/` },
      to: { path: `${PKG}core/` },
    },

    // --- Support package edges (@parallax/serde) ---
    edge("metamodel", "serde"),
    edge("operation", "serde"),

    // --- Database port/adapter support edges (@parallax/db, @parallax/db-postgres) ---
    // The database seam is normatively decomposed (core spec
    // `m-dialect.md` / `m-db-port.md`) into the pure dialect layer
    // (`@parallax/dialect` = `m-dialect`), an abstract runtime port
    // (`@parallax/db` = `m-db-port`; a leaf reaching only `core`, already allowed by
    // the universal core rule above), and N concrete adapters
    // (`@parallax/db-postgres` = a `m-db-port` adapter). A concrete adapter depends
    // ONLY on the port and the pure dialect layer; only the composition root may
    // depend on a concrete adapter. These are language-impl support edges (like the
    // `serde` edges), NOT new DAG modules — the whole seam already shares the one
    // `m-dialect --> m-core` edge, so `modules.md` is unchanged.
    edge("db-postgres", "db"), //      adapter -> port
    edge("db-postgres", "dialect"), // adapter -> pure dialect layer
    edge("db-mariadb", "db"), //       adapter -> port (MariaDB, the second concrete adapter)
    edge("db-mariadb", "dialect"), //  adapter -> pure dialect layer (its matching strategy, mariadbDialect)

    // --- Composition package edges (@parallax/typescript) ---
    // The composition root may import any scaffolded package. lifecycle /
    // benchmark / coherence are intentionally absent from this `to` set
    // because they are not scaffolded for the slice. `db` (the port) and
    // `db-postgres` (the concrete adapter) are added: the composition root is the
    // only layer allowed to depend on a concrete adapter.
    {
      from: { path: `${PKG}typescript/` },
      to: {
        path: `${PKG}(?:core|metamodel|operation|sql|relationships|lists|bitemporal|transactions|locking|dialect|db|db-postgres|db-mariadb|conformance|serde)/`,
      },
    },

    // --- Module edges from core/spec/modules.md ---
    edge("metamodel", "core"), //      m-descriptor -> m-core
    edge("dialect", "core"), //        m-dialect -> m-core
    edge("operation", "metamodel"), // m-op-algebra -> m-descriptor
    edge("sql", "operation"), //       m-sql -> m-op-algebra
    edge("sql", "dialect"), //         m-sql -> m-dialect (compile() consults the Dialect contract — ORDER BY / NULL placement, row-limit, read-lock)
    edge("transactions", "operation"), // m-unit-work -> m-op-algebra
    // Note: m-read-lock -> m-dialect (transactions -> dialect) is spec-legal but
    // omitted here — the in-transaction read-lock application moved into
    // `@parallax/dialect` (delta 09 D3) and `@parallax/transactions` now imports
    // nothing from it, so per the same policy the package edge is absent; the
    // composition root applies the read lock via the dialect. The core DAG keeps
    // m-read-lock -> m-dialect.
    edge("lists", "operation"), //     m-op-list -> m-op-algebra
    edge("lists", "transactions"), //  m-op-list -> m-unit-work
    edge("lists", "relationships"), // m-op-list -> m-deep-fetch (ADR 0025 re-pin)
    edge("relationships", "operation"), // m-navigate -> m-op-algebra (ADR 0025 re-pin)
    edge("relationships", "transactions"), // m-navigate -> m-unit-work
    edge("relationships", "bitemporal"), //   m-navigate -> m-temporal-read  (design Q5 correction)
    edge("bitemporal", "transactions"), //    m-audit-write -> m-unit-work
    // Note: m-opt-lock -> m-unit-work (locking -> transactions) is spec-legal but
    // omitted here — the `@parallax/locking` package renders versioned-UPDATE text
    // only and does not import the unit of work, so per the "an edge exists only
    // when there is an implementation behind it" policy above it is absent until
    // locking's code uses transactions. The core DAG keeps m-opt-lock -> m-unit-work.
    edge("conformance", "operation"), //      m-case-format -> m-op-algebra
    edge("conformance", "sql"), //            m-case-format -> m-sql
    edge("conformance", "dialect"), //        m-case-format -> m-dialect (harness applies dialect DDL / quoting / read-lock rules)
    edge("conformance", "db"), //             m-case-format -> m-db-port (the `error`/concurrency runner consumes the portable ParallaxTransientError surface)
    edge("conformance", "relationships"), //  m-case-format -> m-navigate
    edge("conformance", "bitemporal"), //     m-case-format -> m-temporal-read
    edge("conformance", "transactions"), //   m-case-format -> m-unit-work  (write-sequence / scenario shapes)
    edge("conformance", "locking"), //        m-case-format -> m-opt-lock
  ],
  allowedSeverity: "error",
  options: {
    doNotFollow: { path: "node_modules" },
    // Resolve the solution tsconfig relative to this config file so the check
    // works regardless of the cwd it is invoked from (repo root or this dir).
    tsConfig: { fileName: join(__dirname, "tsconfig.json") },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "types", "node", "default"],
    },
  },
};
