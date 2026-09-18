---
date: 2026-09-09
git_commit: 112c9dddeb237f5b44cce48ea0b892c1398edbb7
topic: "Python complexity, duplication, and dependency hygiene tooling"
type: research
tags: [research, python, quality, complexity, duplication, dependencies]
status: complete
---

# Python Static-Quality Tooling

## Scope and recommendation

The two targets are the standalone `reference-harness` project and the six-package
uv workspace under `languages/python`. Both target Python 3.13 and already run Ruff;
both lock Ruff 0.16.6 ([harness lock](../../reference-harness/uv.lock),
[language lock](../../languages/python/uv.lock)). The language workspace uses six
PEP 420 distributions sharing the `parallax` top-level namespace.

Adopt this stack:

| Concern | Recommended tool | Initial hard policy | Target policy |
|---|---|---|---|
| Cyclomatic complexity | Ruff `C901` | Maximum 15 per function | Maximum 10 after existing violations are removed |
| Cognitive complexity | Complexipy, initially report-only | Report functions over 15 | Gate at 15 only if its findings add value beyond `C901` |
| Duplicate code | jscpd v5 | 100 tokens and 10 lines; no more than 1% duplicated lines per production target | Keep 1%; reject any newly introduced actionable clone even when the aggregate passes |
| Runtime dependency hygiene | deptry, once per distribution | Zero unexplained `DEP001`-`DEP005` findings | Keep zero; exceptions must name a package and reason |

Ruff plus jscpd plus deptry is the recommended gate. Complexipy is a useful
one-month trial, not a prerequisite: two complexity metrics should not become two
ways of reporting the same refactoring request.

## Complexity

### Ruff `C901`: primary gate

Ruff's `C901` computes McCabe complexity as one plus the number of decision points
and reports a function only when it exceeds `lint.mccabe.max-complexity`. Its
default maximum is 10 ([rule](https://docs.astral.sh/ruff/rules/complex-structure/),
[setting](https://docs.astral.sh/ruff/settings/#lint_mccabe_max-complexity)). This is
the best first integration because Ruff is already installed, configured, and
invoked for both targets. No new runner or report parser is required.

Recommended configuration:

```toml
[tool.ruff.lint]
select = ["...", "C901"]

[tool.ruff.lint.mccabe]
max-complexity = 15
```

Apply it to handwritten source, tests, and tools. Exclude only generated or vendored
code, not whole architectural areas. Ruff supports file-pattern exclusions and
`per-file-ignores`, and its output formats include concise text, JSON, JSON Lines,
JUnit, GitHub, GitLab, Azure, and SARIF
([configuration and CLI formats](https://docs.astral.sh/ruff/configuration/)). Prefer
a narrowly scoped `# noqa: C901` on a function with an exceptional state-machine or
protocol rationale over a file-wide ignore.

A local scan at this note's commit found 53 harness functions and 43 language
production/tool functions over 10; including language tests raised the latter to 50.
At 15 it found 15 and 13 production/tool violations respectively, with no additional
test violations; at 20 it found 7 and 4. The maximums were 45 and 28. Therefore 15
is a meaningful but tractable first hard ceiling. Ten remains the design target; 20
would preserve too much of the current tail. Clear or explicitly justify the 28
initial violations before making the gate blocking, then lower the ceiling rather
than accumulating suppression debt.

Ruff is actively maintained: the repository is already locked to 0.16.6, and the
official current integration examples use the same version
([Ruff integrations](https://docs.astral.sh/ruff/integrations/)).

### Complexipy: cognitive-complexity trial

Complexipy measures cognitive rather than path complexity, increasing scores for
nesting and flow that is difficult for a reader. Version 6.0 corrected the algorithm
to conform to SonarSource's Cognitive Complexity white paper; 6.2.0 is the latest
release as of this note ([official releases](https://github.com/rohaquinlop/complexipy/releases)).
It defaults to a maximum of 15, supports TOML configuration, glob exclusions,
function-level ignores, snapshots, Git-reference diffs, and JSON, CSV, GitLab, and
SARIF output ([official README](https://github.com/rohaquinlop/complexipy)).

Run it report-only with `max-complexity-allowed = 15`, across the same handwritten
paths as Ruff, and inspect whether it finds deeply nested code that `C901` misses.
Its snapshot/diff mode is attractive for ratcheting existing code, but a committed
snapshot is another quality artifact to maintain. Adopt it as a hard gate only if
the trial produces distinct, actionable findings; otherwise keep Ruff alone.

### SonarQube: capable but disproportionate alternative

SonarQube 26.7.0 was the current Community Build release in July 2026
([official releases](https://github.com/SonarSource/sonarqube/releases)). It computes
both cyclomatic and cognitive complexity and performs duplication analysis
([metric definitions](https://docs.sonarsource.com/sonarqube-server/user-guide/code-metrics/metrics-definition)).
Its function-level complexity rules and new-code model are stronger than aggregate
metrics, and its built-in quality gate caps duplication on new code at 3%
([2026.1 quality gate](https://docs.sonarsource.com/sonarqube-server/2026.1/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/)).
It is not recommended here because it introduces a server, scanner, quality-profile
administration, and a second lint system to obtain checks that lightweight tools can
run inside the existing uv/just build.

## Duplicate-code detection

### jscpd v5: primary gate

jscpd v5.0.10 is a maintained Rust rewrite, published for npm and crates.io in June
2026 ([official release](https://github.com/kucherenko/jscpd/releases/tag/v5.0.10)).
It accepts multiple paths and a `.jscpd.json` file. The exact controls needed here
are:

- `minTokens` and `minLines` define the smallest clone; defaults are 50 and 5.
- `threshold` is the maximum aggregate duplication percentage and the threshold
  reporter exits 1 when it is exceeded.
- `mode` selects `mild`, `weak`, or `strict`; `mild` is the default.
- `format`, `ignore`, and ignored-block markers control scope.
- console, JSON, XML, CSV, HTML, Markdown, SARIF, and other reporters are available.

These options and output paths are specified in the
[official v5 documentation](https://github.com/kucherenko/jscpd/blob/master/docs/rust.md).

Use two independently gated scans so a large target cannot dilute a smaller one:

1. `reference-harness/src/reference_harness`.
2. Every `languages/python/packages/*/src` tree plus `languages/python/tools`.

Use `format: ["python"]`, `mode: "mild"`, `minTokens: 100`, `minLines: 10`,
`threshold: 1`, and console + threshold reporters. The 100-token,
10-line floor intentionally matches Sonar's non-Java clone definition
([Sonar metric definition](https://docs.sonarsource.com/sonarqube-server/user-guide/code-metrics/metrics-definition#duplications));
jscpd's 50-token, five-line defaults are more likely to flag routine Python idioms.
Sonar's maintained new-code quality gate uses 3%, but that is too loose for an
aggregate whole-tree gate over these already-clean targets. At this note's commit,
jscpd 5 reported 0.16% duplicated harness lines and 0.30% duplicated language
production/tool lines, so 1% leaves useful operating room without permitting a
tenfold regression. jscpd's current threshold is aggregate rather than diff-aware,
so first run it report-only, remove or review the baseline, then enable the hard
ceiling. Keep human review responsible for a new actionable clone below 1%.

Do not put tests in the production percentage: compatibility cases and fixture setup
are intentionally repetitive. Scan tests separately, report-only, with the same
100-token/10-line floor. Exclude only generated artifacts, vendored code, and an
individually reviewed required repetition. Do not ignore directories merely because
they currently contain findings.

## Unused and misdeclared dependencies

### deptry: primary external-dependency gate

Deptry 0.25.1 is the current release; 0.25.0 added inline suppressions,
non-development dependency-group selection, and improved PEP 621 group handling
([official releases](https://github.com/osprey-oss/deptry/releases)). It reports:

| Code | Meaning |
|---|---|
| `DEP001` | Imported package is missing from direct dependencies |
| `DEP002` | Declared runtime dependency is unused |
| `DEP003` | Code imports a transitive dependency directly |
| `DEP004` | Production code imports a development dependency |
| `DEP005` | A declared dependency is in the standard library |

Deptry treats `[project.dependencies]` and optional-dependency groups as runtime
dependencies, and PEP 735 `[dependency-groups]` as development dependencies. It
deliberately does not apply `DEP002` to development dependencies such as pytest,
Ruff, type stubs, or command-line build tools
([usage](https://deptry.com/usage/),
[dependency-manager support](https://deptry.com/supported-dependency-managers/),
[rules](https://deptry.com/rules-violations/)). That behavior fits both projects:
an import scan cannot prove that a CLI-only development tool is unused. The harness
also declares `dev` under `[project.optional-dependencies]`; configure
`optional_dependencies_dev_groups = ["dev"]` so deptry classifies that copy as
development rather than reporting every CLI-only tool as unused. This option exists
specifically for PEP 621 optional groups used as development groups
([configuration](https://deptry.com/usage/#optional-dependencies-dev-groups)).

Run with zero allowed findings. For the harness, scan `src` against its own
`pyproject.toml`. For the language implementation, do **not** scan only the workspace
root: it is a virtual coordinating project with no corresponding source and its
runtime list intentionally aggregates workspace members. Instead invoke deptry once
for each `packages/*/src`, with `--config` pointing at that member's `pyproject.toml`.
Deptry documents both multiple source paths and an explicit config path, but not
automatic uv-workspace traversal ([official usage](https://deptry.com/usage/)). Put
common flags in the just recipe or repeat a small `[tool.deptry]` table in each member;
deptry cannot currently read dependencies and configuration from different
`pyproject.toml` files
([open upstream request](https://github.com/osprey-oss/deptry/issues/1292)).

There is an important limit: deptry 0.25.1 collapses native namespace-package imports
to their top-level name. When several distributions share that name, one sibling can
satisfy imports from all of them
([open PEP 420 issue](https://github.com/osprey-oss/deptry/issues/1528)). All Parallax
Python distributions share `parallax`, so deptry must not own sibling-package
dependency correctness. Set `known_first_party = ["parallax"]` to prevent false
missing/transitive reports, ignore declared `parallax-*` distributions for `DEP002`,
and retain the existing generated import-linter DAG and distribution/install tests
as authorities for those edges. Because `known_first_party` necessarily hides real
missing sibling declarations, add or retain one repository-owned canary that compares
full `parallax.<distribution>` imports with each member's declared sibling
dependencies. Deptry remains authoritative for external runtime dependencies such as
Pydantic, PyYAML, jsonschema, psycopg, and testcontainers.

The local 0.25.1 baseline confirms this boundary. With `parallax` treated as first
party and the documented import-name mappings `pyyaml = "yaml"` and
`psycopg-pool = "psycopg_pool"`, the meaningful residuals were:

- harness: `referencing` imported transitively (`DEP003`);
- core: `pydantic_core` imported transitively (`DEP003`);
- conformance: unused `jsonschema` (`DEP002`) and transitive imports of `psycopg`,
  `yaml`, and `pydantic` (`DEP003`);
- descriptor, evolution, postgres, and snapshot: no external findings.

These are the useful decisions the gate should force: remove an actually unused
runtime dependency, or directly declare a distribution whose API is imported. They
should not be converted into blanket ignores. Deptry officially supports explicit
distribution-to-import mappings for names that cannot be derived mechanically
([package-module map](https://deptry.com/usage/#package-module-name-map)).

Deptry supports per-rule package/module ignores, regex path exclusions, extension of
its default exclusions, a PEP 420 discovery mode, and JSON output
([configuration](https://deptry.com/usage/#configuration)). It recognizes literal
`importlib.import_module("package")`, but not a module name held in a variable
([dynamic-import behavior](https://deptry.com/usage/#dynamic-imports)). Policy for
exceptions should therefore be:

- keep normal imports visible to the analyzer;
- for computed dynamic imports, plugin entry points, providers loaded from metadata,
  or dependencies needed only for packaging/runtime capability, add a package-specific
  `DEP002` ignore with a durable rationale and a test that exercises discovery;
- use inline `# deptry: ignore[DEP001]` only on an exceptional import; inline ignores
  cannot suppress `DEP002`, which is reported at the manifest;
- never disable `DEP002` globally, and never let test imports make a production
  dependency look used. Deptry excludes `tests` by default for this reason.

Deptry intentionally cannot decide whether a development-only distribution is still
needed. Keep a small repository-owned dev inventory canary that classifies each entry
as a test import, a command invoked by a just/CI owner, a type-stub provider, or other
metadata/plugin use. This is also the correct authority for removing CLI-only tools;
forcing them through `DEP002` would create exceptions without proving use.

### FawltyDeps: credible alternative, weaker fit

FawltyDeps 0.20.0 is maintained and supports pyproject files, PEP 735 groups,
regular source files, notebooks, explicit source/dependency paths, and wildcard
ignore lists ([project docs](https://tweag.github.io/FawltyDeps/),
[official release](https://github.com/tweag/FawltyDeps/releases/tag/v0.20.0)). It can
gate undeclared and unused dependencies separately. However, its uv-workspace support
remains an open upstream question, with correct name mapping dependent on running in
the project environment
([workspace issue](https://github.com/tweag/FawltyDeps/issues/507)). More importantly
for this repository, it treats PEP 735 group entries like other declarations and
expects corresponding imports, producing noise for CLI-only dev tools
([0.19 release notes](https://github.com/tweag/FawltyDeps/releases/tag/v0.19.0)).
Deptry's explicit runtime/development distinction makes it the better CI fit,
subject to the shared-namespace limitation above.

## Rollout order

1. Add Ruff `C901` at 15 and remediate or individually justify the 28 current
   source/tool violations; retain 10 as the lowering target.
2. Baseline jscpd independently on harness production code and language production
   code, review clones, then gate each at 1% with 100 tokens and 10 lines.
3. Add deptry as one harness invocation plus six member invocations, at zero findings,
   with `parallax` first-party handling, explicit `parallax-*` `DEP002` exceptions,
   and internal-distribution and dev-tool inventory canaries covering what static
   top-level import matching cannot prove.
4. Trial Complexipy at 15 in report-only mode and keep it only if it identifies a
   distinct class of readability problems.
