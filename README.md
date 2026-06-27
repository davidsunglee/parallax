# parallax

A **language-neutral core specification** plus a **machine-readable compatibility
suite** for a bitemporal object-relational mapping framework, extracted from the
Goldman Sachs [Reladomo](https://github.com/goldmansachs/reladomo) Java ORM.

The goal: hand an agent the **core spec + a language spec + this compatibility
suite**, and have it build an idiomatic implementation in any language that
proves parity by running the suite against real databases.

## What this repository is

This is a **polyglot monorepo**. The only things shared across language modules
are *data* (the compatibility fixtures) and *docs* (the spec) — there is no
compiled cross-language dependency, so there is deliberately **no unified build
system** (no Bazel). Each language module uses its own idiomatic toolchain; a
thin root layer (`just` + a CI matrix + commit hooks) ties them together.

```text
/                          # monorepo root
├── package.json           # dev-tooling only: husky, commitlint, markdownlint, lint-staged
├── commitlint.config.js   # conventional-commit rules
├── .husky/                # commit-msg → commitlint; pre-commit → lint-staged
├── justfile               # root orchestration: just lint / test / verify / matrix
├── .github/workflows/     # CI: lint + dep-graph + suite across the DB matrix
├── core/                  # language-neutral data + docs (NO runtime code)
│   ├── spec/              # M0–M13 capability modules + dependency graph
│   ├── schemas/           # metamodel · operation · compatibility-case JSON Schemas
│   └── compatibility/     # the suite: models/ · cases/ · benchmarks/
├── reference-harness/     # the M12 runner (Python + uv + sqlglot) — tooling, NOT an ORM
└── (future) python/ java/ typescript/ …   # per-language { spec, impl }
```

## What the reference harness is — and is not

`reference-harness/` is the canonical **M12 compatibility runner**. It is
**tooling, not an ORM**. It **never compiles operations to SQL** — that is
precisely what a real implementation must do and prove against the golden SQL.

What it *does*, per compatibility case, against a freshly-provisioned real
database (selected through the **database-provider seam**):

1. **Schema conformance** — the model descriptor, the operation encoding, and
   the case envelope all validate against their JSON Schemas.
2. **Triple equivalence** — `exec(goldenSql[dialect]) == exec(referenceSql) ==
   expectedRows`. The independent, naively-written `referenceSql` is an oracle
   that catches a case that is self-consistent but wrong.
3. **Normalization determinism** — `normalize(goldenSql) == goldenSql` via
   sqlglot, per the M3 canonical rules.
4. **Serde round-trip** — `serialize(deserialize(x)) == x` for **both** the
   operation encoding and the model descriptor, in **both** JSON and YAML.

The harness is Python + uv + sqlglot. Its *contract* is language-neutral, so
other ecosystems can re-implement the runner.

## How to run the suite

Prerequisites: [`uv`](https://docs.astral.sh/uv/), [`just`](https://github.com/casey/just),
Node.js (for commit/lint hooks), and a running **Docker** daemon (Testcontainers
boots real databases).

```sh
# one-time: install dev-tooling hooks
npm install

# static checks (no Docker): ruff, markdownlint, schema + meta-schema, sqlglot-parse
just lint

# the module-dependency graph is a legal DAG AND the coverage gate is green
# (every in-scope module has at least one fixture tagged to it)
just dep-graph

# the full suite — boots Postgres AND MariaDB via Testcontainers
just test

# everything required before merge
just verify

# the compatibility-matrix report (implementations × databases:
# reference × {postgres, mariadb})
just matrix
```

Run against a single database with `PARALLAX_DATABASES=postgres` (or `mariadb`).

## The compatibility case at a glance

Each case is YAML carrying three independent things the harness cross-checks:

- **`goldenSql`** — the optimized SQL an implementation is *expected to emit*
  (keyed by dialect from day one, e.g. `postgres:` / `mariadb:`).
- **`expectedRows`** — the result the query must return against the fixture data.
- **`referenceSql`** — a deliberately naive, obviously-correct second
  formulation; an independent oracle (required for non-trivial cases, optional
  for trivial single-table predicates).

See [`core/spec/00-overview.md`](core/spec/00-overview.md) for the spec map and
[`core/spec/m12-compatibility-harness.md`](core/spec/m12-compatibility-harness.md)
for the full case contract.

## Contributor guide

### How to add a case

1. Author (or reuse) a model descriptor under `core/compatibility/models/` (an
   instance of `metamodel.schema.json`) and its fixture rows under
   `core/compatibility/fixtures/<model-stem>.yaml`.
2. Add a YAML file under `core/compatibility/cases/` carrying the case envelope —
   `model`, `tags`, `operation` (or `writeSequence` / `scenario` / `coherence` /
   the conflict shape), `goldenSql` (keyed by dialect), `binds`, `referenceSql`
   (required for non-trivial cases), and `expectedRows` / `expectedGraph` /
   `expectedTableState`. See
   [`m12-compatibility-harness.md`](core/spec/m12-compatibility-harness.md) for
   the full field list.
3. **Tag it for coverage.** The first tag is the owning module (`m2`, `m7`, …);
   add feature tags as needed. The coverage gate (below) keys off these tags.
4. Run `just lint` (schema + sqlglot-parse), then `just test` (real databases).

### How to add a module

1. Add the spec file under `core/spec/` (e.g. `m14-….md`) and register it in
   [`00-overview.md`](core/spec/00-overview.md).
2. Add the module to the **normative module-dependency graph** —
   [`dependency-graph.md`](core/spec/dependency-graph.md): a row in the module
   table **and** edges in the fenced ```` ```dependency-graph ```` block (each
   edge `A --> B` means "A depends on B"; the graph MUST stay an acyclic DAG with
   legal directions).
3. Place it in a tier in
   [`scope-and-tiers.md`](core/spec/scope-and-tiers.md). If it is MVP /
   fast-follow / definitely-do, the **coverage gate** now requires at least one
   fixture tagged to it.
4. Ship fixtures tagged to the new module.

### How the gates work

Every normative claim is a mechanical check (nothing is "trust me"):

- **Schema gate** — `just lint` validates every fixture against its JSON Schema
  and parses all golden/reference SQL with sqlglot.
- **Dependency-graph gate** — `just dep-graph` asserts the module graph is an
  acyclic DAG with legal edge directions.
- **Coverage gate** — `just dep-graph` *also* runs
  `dep_graph_check --coverage`: it reads the in-scope tiers (MVP / fast-follow /
  definitely-do) from `scope-and-tiers.md` and asserts **every in-scope module
  has at least one fixture tagged to it** (the un-numbered cross-process-coherence
  capability is covered by the `coherence` tag). Might-do and won't-do tiers —
  including the RFC-2119 MAY temporal mutations — are excluded by construction. A
  missing fixture for an in-scope module fails the build and names the gap.
- **Suite gate** — `just test` boots Postgres + MariaDB and runs every case
  through triple-equivalence + normalization + serde round-trip.

`just verify` runs all of them; the same set runs in CI.

### How to read the matrix

`just matrix` emits the **compatibility-matrix report** — implementations ×
databases. Round 1 has one implementation (the reference harness) across two
databases, so the matrix proves `reference × {postgres, mariadb}` green. Each
future language implementation adds a row; each new dialect behind the M11 seam
adds a column.

## Status

Built incrementally in vertical slices (one phase = one thin slice through every
layer). The core spec (`M0`–`M13` + cross-process coherence), the schemas, the
compatibility suite, and the reference harness are in place; the suite runs
against Postgres **and** MariaDB, and the dependency-graph + coverage gates are
green. The language-spec template
([`core/spec/language-spec-template.md`](core/spec/language-spec-template.md)) and
the scope-and-tiers boundary
([`core/spec/scope-and-tiers.md`](core/spec/scope-and-tiers.md)) close the frame:
handed the core spec + a language spec + this suite, an agent can build an
idiomatic implementation and prove parity by running the suite.
