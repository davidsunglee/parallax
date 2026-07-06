# The module DAG is enforced by dependency-cruiser

The TypeScript build enforces the normative module DAG (`core/spec/modules.md`)
with dependency-cruiser, run as a standalone `depcruise --validate` step: the
legal edges form an `allowed` allowlist of `{ from, to }` package pairs, and any
unmatched dependency fails the build as `not-in-allowed`. The workspace packages
themselves participate in the layering — each package's `package.json` lists only
the sibling packages it is permitted to depend on, and dependency-cruiser is the
mechanical gate that fails the build if an `import` crosses an edge the map does
not declare. Packages implement module *sets*, so the authoritative
package ↔ module map lives in the TypeScript implementation spec §9
(`languages/typescript/spec/01-implementation-spec.md`), not here.

**Considered options.** `eslint-plugin-boundaries` was the alternative: it
classifies files into element types and enforces dependency rules inside ESLint,
which ties the boundary check to the ESLint run and the flat-config element
taxonomy. dependency-cruiser was preferred because its `allowed` from/to contract
encodes the DAG edges directly and runs decoupled from lint configuration and
lint-rule churn, keeping the DAG check a first-class build step that mirrors the
reference harness's dedicated dep-graph check (`dep_graph_check.py`).
