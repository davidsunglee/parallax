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

# the normative module-dependency graph is a DAG with legal edge directions
just dep-graph

# the full suite — boots Postgres via Testcontainers
just test

# everything required before merge
just verify

# the compatibility-matrix report (implementations × databases)
just matrix
```

## The compatibility case at a glance

Each case is YAML carrying three independent things the harness cross-checks:

- **`goldenSql`** — the optimized SQL an implementation is *expected to emit*
  (keyed by dialect from day one, e.g. `postgres:`).
- **`expectedRows`** — the result the query must return against the fixture data.
- **`referenceSql`** — a deliberately naive, obviously-correct second
  formulation; an independent oracle (required for non-trivial cases, optional
  for trivial single-table predicates).

See [`core/spec/00-overview.md`](core/spec/00-overview.md) for the spec map and
[`core/spec/m12-compatibility-harness.md`](core/spec/m12-compatibility-harness.md)
for the full case contract.

## Status

Built incrementally in vertical slices (one phase = one thin slice through every
layer). Phase 1 establishes the walking skeleton: a single non-temporal object
queried by `all()` and one `eq`, proven end-to-end against real Postgres.
