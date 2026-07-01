"use strict";

const { join } = require("node:path");

/**
 * dependency-cruiser allowlist for the TypeScript workspace.
 *
 * This is the trimmed + corrected encoding of the module DAG from
 * `core/spec/dependency-graph.md`, mapped onto the `@parallax/*` packages by
 * `languages/typescript/spec/01-implementation-spec.md` §7.
 *
 * Trimmed (design Q4): only the 13 packages the `first-implementation-mvp`
 * slice actually implements are scaffolded, so `lifecycle` (M9),
 * `benchmark` (M13), and `coherence` (M14) — and every numbered edge that
 * touches them — are intentionally absent. They are added when their slice
 * lands; an allowlist edge exists only when there is an implementation behind
 * it.
 *
 * Corrected (design Q5): the `relationships -> bitemporal` (M4 -> M7) edge that
 * core declares (as-of binds propagate per relationship hop) but the spec's
 * §7.3 transcription previously omitted is present here.
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

    // `@parallax/core` is the foundational leaf (M0 conventions + the shared
    // adapter-envelope types). It depends on nothing, so depending on it can
    // never create a wrong-direction edge. Like the `serde` edges, this is an
    // explicit package-topology allowance, not an addition to the numbered
    // module DAG — the numbered DAG only declares `M1 -> M0` and `M11 -> M0`,
    // but the envelope types live here and are consumed across the build (e.g.
    // `@parallax/conformance` builds a `DescribeOk`). The reverse — `core`
    // importing any sibling — stays forbidden, which is what the negative
    // boundary test plants and asserts.
    {
      from: { path: `${PKG}[^/]+/` },
      to: { path: `${PKG}core/` },
    },

    // --- Non-numbered support package edges (@parallax/serde) ---
    edge("metamodel", "serde"),
    edge("operation", "serde"),

    // --- Non-numbered composition package edges (@parallax/typescript) ---
    // The composition root may import any scaffolded package. lifecycle /
    // benchmark / coherence are intentionally absent from this `to` set
    // because they are not scaffolded for the slice.
    {
      from: { path: `${PKG}typescript/` },
      to: {
        path: `${PKG}(?:core|metamodel|operation|sql|relationships|lists|bitemporal|transactions|locking|dialect|conformance|serde)/`,
      },
    },

    // --- Numbered module edges from core/spec/dependency-graph.md ---
    edge("metamodel", "core"), //      M1  -> M0
    edge("dialect", "core"), //        M11 -> M0
    edge("operation", "metamodel"), // M2  -> M1
    edge("sql", "operation"), //       M3  -> M2
    edge("sql", "dialect"), //         M3  -> M11
    edge("transactions", "operation"), // M8 -> M2
    edge("transactions", "dialect"), //   M8 -> M11
    edge("lists", "operation"), //     M5  -> M2
    edge("lists", "transactions"), //  M5  -> M8
    edge("relationships", "lists"), // M4  -> M5
    edge("relationships", "transactions"), // M4 -> M8
    edge("relationships", "bitemporal"), //   M4 -> M7  (design Q5 correction)
    edge("bitemporal", "transactions"), //    M7 -> M8
    // Note: M10 -> M8 (locking -> transactions) is spec-legal but omitted here —
    // the M10 package renders versioned-UPDATE text only and does not import the
    // M8 unit of work, so per the "an edge exists only when there is an
    // implementation behind it" policy above it is absent until locking's code
    // uses transactions. The core DAG keeps M10 -> M8.
    edge("conformance", "operation"), //      M12 -> M2
    edge("conformance", "sql"), //            M12 -> M3
    edge("conformance", "relationships"), //  M12 -> M4
    edge("conformance", "bitemporal"), //     M12 -> M7
    edge("conformance", "transactions"), //   M12 -> M8  (write-sequence / scenario / read-lock shapes)
    edge("conformance", "locking"), //        M12 -> M10
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
