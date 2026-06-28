# The module DAG is enforced by dependency-cruiser over an M0–M13 package map

The TypeScript build enforces the normative module-dependency graph
(`core/spec/dependency-graph.md`) with dependency-cruiser, run as a standalone
`depcruise --validate` step. The legal edges of the DAG are transcribed
one-to-one into `.dependency-cruiser.js`, so a wrong-direction or otherwise
unlisted module-to-module dependency fails the build — the same property the
Python reference harness gets from `dep_graph_check.py`.

Each core module maps to one pnpm-workspace package under `packages/`, named for
its responsibility and tagged with its core `M`-number. The packages are real
workspace packages rather than path-ruled directories so the workspace graph
itself participates in the layering: a package only lists in its `package.json`
the sibling packages it is permitted to depend on, and dependency-cruiser is the
mechanical gate that fails the build if an `import` crosses an edge the DAG does
not declare.

```text
M0  core conventions (types · infinity · tz)   →  @parallax/core           (M0)
M1  domain model & metamodel (+ serde)          →  @parallax/metamodel      (M1)
M2  query/operation/aggregation algebra         →  @parallax/operation      (M2)
M3  SQL generation contract                     →  @parallax/sql            (M3)
M4  relationships & deep fetch                   →  @parallax/relationships  (M4)
M5  lists & bulk/set operations                  →  @parallax/lists          (M5)
M7  bitemporal / milestoning                     →  @parallax/bitemporal     (M7)
M8  transactions, UoW & identity/query cache     →  @parallax/transactions   (M8)
M9  object lifecycle & detach                     →  @parallax/lifecycle      (M9)
M10 optimistic locking                           →  @parallax/locking        (M10)
M11 database seam & portability                  →  @parallax/dialect        (M11)
M12 compatibility harness                        →  @parallax/conformance    (M12)
M13 performance & benchmark harness              →  @parallax/benchmark      (M13)
```

`M6` deliberately has no package: aggregation is folded into `M2`, and the gap is
preserved to keep cross-references to the core numbering stable. The shared
`@parallax/serde` package is part of the `M1`/`M2` slice (the canonical serde
seam) rather than a numbered module of its own, so it does not add an edge to the
graph.

dependency-cruiser is preferred over `eslint-plugin-boundaries` because its
`forbidden`/`allowed` from/to contract encodes the DAG edges directly — an
`allowed` allowlist of legal `{ from, to }` pairs, with any unmatched
module-to-module dependency reported as `not-in-allowed` — and it runs decoupled
from ESLint, so the layering gate is independent of lint configuration and lint
rule churn. `eslint-plugin-boundaries` was the considered alternative; it
classifies files into element types and enforces dependency rules inside ESLint,
which ties the boundary check to the ESLint run and the flat-config element
taxonomy. dependency-cruiser's standalone `depcruise --validate` keeps the DAG
check a first-class build step that mirrors the reference harness's dedicated
`dep_graph_check.py`.
